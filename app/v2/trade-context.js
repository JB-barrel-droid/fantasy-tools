// JEG-1229: one trade context for Find a trade (your team), Find a trade (league-wide) and Compare.
//
// Jeremy's 5A (JEG-1220, 2026-10-29): common preferences are shared across the trade pages; page-specific controls stay
// separate. This module is pure (no DOM, no engine values, no storage writes). It normalizes:
//
//   common    league settings (scoring, team count, roster shape, shares, season weeks, advanced), value basis, player
//             overrides and source availability. The league part reuses DDFState's codec, so a page's leagueQuery()
//             and a DDF state read the same way.
//   teams     stable saved-team IDs and frozen roster snapshots, with provenance (saved / local / link).
//   deal      explicit give/get player keys.
//   controls  the route's own controls (pair finder settings, league filters; Compare has none).
//
// and returns a deep-frozen TradeContext. Nothing here changes a value, a fit rule, a default or a ranking: where the
// routes disagree today, ROUTE_DISCREPANCIES records it and each route keeps its own behavior.
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory(() => require("./ddf-state.js"), () => require("./workspace.js"));
  else root.TradeValueTradeContext = factory(() => root.DDFState, () => root.TradeValueWorkspace);
})(typeof window !== "undefined" ? window : globalThis, function (stateCodec, workspaceApi) {
  "use strict";

  const VERSION = 1;
  const ROUTES = ["pair", "league", "compare"];
  const PROVENANCE = ["saved", "local", "link"];
  // Discovery routes search for trades; Compare edits one explicit deal and never gets discovery filters.
  const CAPABILITIES = {
    pair: {discovery: true, explicitDeal: false, multipleOpponents: false},
    league: {discovery: true, explicitDeal: false, multipleOpponents: true},
    compare: {discovery: false, explicitDeal: true, multipleOpponents: false}
  };
  // Today's route behavior where the routes differ. Recorded, not unified: a unified default is Jeremy's decision.
  const ROUTE_DISCREPANCIES = Object.freeze([
    {id: "package-size-storage", routes: ["pair", "league"],
      detail: "Package size is stored twice: the pair finder keeps ui.finderSettings.maxSize (1 to 4), the league finder keeps ui.maxSize (2 to 4). Both start at 2."},
    {id: "keep-starters", routes: ["pair", "league"],
      detail: "Keep my starters and keep their starters are reader choices in the pair finder; the league finder always runs with both on."},
    {id: "guardrails", routes: ["pair", "league"],
      detail: "Protected positions, minimum backups and lineup minimums exist only in the pair finder."},
    {id: "opponent-default", routes: ["pair", "compare"],
      detail: "Compare fills Their team with the first other saved team that has players; the pair finder (JEG-1219) leaves it empty until chosen."},
    {id: "ranking-basis", routes: ["league"],
      detail: "Ranking by DDF Value or the Trade chart average is a league-finder control only."}
  ].map(Object.freeze));

  const isObject = v => Boolean(v) && typeof v === "object" && !Array.isArray(v);
  // Common preferences this module built (so a context can be rebuilt from one without reading it as raw input again).
  const NORMALIZED = new WeakSet();
  const sealCommon = common => { deepFreeze(common); NORMALIZED.add(common); return common; };
  const finite = n => typeof n === "number" && Number.isFinite(n);
  const SOURCE_KEY = /^[a-z0-9_]{1,24}$/;
  const PLAYER_KEY = /^[0-9A-Za-z_:.-]{1,80}$/;

  function deepFreeze(value) {
    if (value && typeof value === "object" && !Object.isFrozen(value)) {
      Object.freeze(value);
      Object.values(value).forEach(deepFreeze);
    }
    return value;
  }
  // Key-sorted JSON: the same content always gives the same text, whatever order it was built in.
  function stable(value) {
    if (Array.isArray(value)) return `[${value.map(stable).join(",")}]`;
    if (isObject(value)) return `{${Object.keys(value).sort().filter(k => value[k] !== undefined).map(k => `${JSON.stringify(k)}:${stable(value[k])}`).join(",")}}`;
    return JSON.stringify(value === undefined ? null : value);
  }
  // cyrb53: a short deterministic hash for cache keys (not security).
  function hash(text) {
    let h1 = 0xdeadbeef;
    let h2 = 0x41c6ce57;
    for (let i = 0; i < text.length; i += 1) {
      const ch = text.charCodeAt(i);
      h1 = Math.imul(h1 ^ ch, 2654435761);
      h2 = Math.imul(h2 ^ ch, 1597334677);
    }
    h1 = Math.imul(h1 ^ (h1 >>> 16), 2246822507) ^ Math.imul(h2 ^ (h2 >>> 13), 3266489909);
    h2 = Math.imul(h2 ^ (h2 >>> 16), 2246822507) ^ Math.imul(h1 ^ (h1 >>> 13), 3266489909);
    return (4294967296 * (2097151 & h2) + (h1 >>> 0)).toString(36);
  }

  // ---------- common preferences ----------
  // league: a DDFState league ({scoring, teams?, roster?, shares?, weeks?, inj?, conf?, bso?}). All or nothing, as in
  // DDFState: a bad scoring or team count drops the whole league, so a half-read league never prices a different one.
  function normalizeLeague(raw, warnings) {
    if (raw === undefined || raw === null) return null;
    const result = stateCodec().normalize({league: raw});
    (result.warnings || []).forEach(w => warnings.push(w));
    return result.state && result.state.league ? result.state.league : null;
  }
  // A page's leagueQuery() (the same parameters every share link carries).
  function leagueFromQuery(query) {
    const result = stateCodec().decodeQuery(String(query || "").replace(/^[#?&]+/, ""));
    return {league: result.state && result.state.league ? result.state.league : null, warnings: result.warnings || []};
  }
  // basis: overrides.js basisRecord(): {mode: "default"} | {mode: "single", source} | {mode: "blend", sources, weights}.
  // Missing means "not stated" (null), which is different from an explicit default.
  function normalizeBasis(raw, warnings) {
    if (raw === undefined || raw === null) return null;
    if (!isObject(raw)) { warnings.push("basis: not an object, dropped"); return null; }
    if (raw.mode === "default") return {mode: "default"};
    if (raw.mode === "single" && SOURCE_KEY.test(String(raw.source || ""))) return {mode: "single", source: String(raw.source)};
    if (raw.mode === "blend" && Array.isArray(raw.sources) && isObject(raw.weights)) {
      const sources = raw.sources.map(String).filter(k => SOURCE_KEY.test(k) && finite(Number(raw.weights[k])) && Number(raw.weights[k]) > 0);
      if (sources.length === raw.sources.length && sources.length) {
        return {mode: "blend", sources, weights: Object.fromEntries(sources.map(k => [k, Number(raw.weights[k])]))};
      }
    }
    warnings.push("basis: unknown shape, dropped");
    return null;
  }
  // overrides: {player_key: number | {type: "adjustment", delta}} as overrides.js holds them (already on its scale; this
  // module does not clamp). An absolute 0 is a real override; a missing or non-numeric value is not one.
  function normalizeOverrides(raw, warnings) {
    if (raw === undefined || raw === null) return null;
    if (!isObject(raw)) { warnings.push("overrides: not an object, dropped"); return null; }
    const out = {};
    Object.keys(raw).sort().forEach(key => {
      const v = raw[key];
      if (!/^\d+$/.test(key)) { warnings.push(`overrides: key ${key} dropped`); return; }
      if (finite(v) && v >= 0) out[key] = v;
      else if (isObject(v) && v.type === "adjustment" && finite(Number(v.delta)) && Number(v.delta) !== 0) out[key] = {type: "adjustment", delta: Number(v.delta)};
      else warnings.push(`overrides: ${key} has no usable value, dropped`);
    });
    return out;
  }
  // sources: {key: {available, held?, reason?, version?}} from the page. A source the page did not report is "unknown",
  // never assumed available. version is the page's own label for the data it loaded (an as-of date, a build tag); this
  // module only compares it, it never judges how old is too old.
  function normalizeSources(raw, warnings) {
    if (raw === undefined || raw === null) return {};
    if (!isObject(raw)) { warnings.push("sources: not an object, dropped"); return {}; }
    const out = {};
    Object.keys(raw).sort().forEach(key => {
      if (!SOURCE_KEY.test(key)) return;
      const s = raw[key];
      const status = !isObject(s) ? "unknown" : s.held ? "held" : s.available === true ? "available" : s.available === false ? "unavailable" : "unknown";
      const text = v => (typeof v === "string" && v ? v.slice(0, 80) : typeof v === "number" && Number.isFinite(v) ? String(v) : null);
      out[key] = {status, reason: isObject(s) ? text(s.reason) : null, version: isObject(s) ? text(s.version) : null};
    });
    return out;
  }
  // raw: {league, basis, overrides, sources}. Returns a frozen {league, valuation: {basis, overrides}, sources, warnings}.
  function normalizeCommon(raw) {
    const r = isObject(raw) ? raw : {};
    const warnings = [];
    const league = normalizeLeague(r.league, warnings);
    const valuation = {basis: normalizeBasis(r.basis, warnings), overrides: normalizeOverrides(r.overrides, warnings)};
    return sealCommon({league, valuation, sources: normalizeSources(r.sources, warnings), warnings});
  }
  // The browser pages' own state: TradeValueV2.leagueQuery(), DDFOverrides.snapshotContext() ({basis, values}).
  function commonFromPage(input) {
    const i = isObject(input) ? input : {};
    const parsed = leagueFromQuery(i.leagueQuery);
    const value = isObject(i.valueContext) ? i.valueContext : {};
    const common = normalizeCommon({league: parsed.league, basis: value.basis, overrides: value.values, sources: i.sources});
    return parsed.warnings.length ? sealCommon({...common, warnings: parsed.warnings.concat(common.warnings)}) : common;
  }
  // Which common preferences apply: a link beats this visit's local choice beats the saved one, section by section.
  // A link league applies whole (DDFState). A link value context marked complete (valuecontext=1) replays its basis and
  // overrides exactly, explicit default included; an incomplete one replaces only the parts it carries.
  // layers: {link?: {common, complete}, local?: common, saved?: common}. Returns frozen {common, provenance}.
  function resolveCommon(layers) {
    const l = isObject(layers) ? layers : {};
    const link = l.link && l.link.common ? l.link : null;
    const order = [["link", link && link.common], ["local", l.local], ["saved", l.saved]].filter(([, c]) => c);
    const pick = (fn, completeLink) => {
      for (const [name, c] of order) {
        if (name === "link" && completeLink) return [name, fn(c) === null ? defaultFor(fn) : fn(c)];
        const v = fn(c);
        if (v !== null && v !== undefined) return [name, v];
      }
      return [null, null];
    };
    const defaultFor = fn => (fn === basisOf ? {mode: "default"} : fn === overridesOf ? {} : null);
    const leagueOf = c => c.league;
    const basisOf = c => c.valuation && c.valuation.basis;
    const overridesOf = c => c.valuation && c.valuation.overrides;
    const complete = Boolean(link && link.complete);
    const [leagueFrom, picked] = pick(leagueOf, false);
    // As v2.js applyLinkLeague: a link without a team count keeps the reader's, and a roster slot the link leaves out keeps
    // the reader's. Weeks, shares and advanced settings a link leaves out mean the defaults (absent), as there.
    const below = order.filter(([name]) => name !== "link").map(([, c]) => c.league).find(Boolean);
    const league = leagueFrom === "link" && below
      ? {...picked, ...(picked.teams === undefined && below.teams !== undefined ? {teams: below.teams} : {}),
        ...(below.roster || picked.roster ? {roster: {...(below.roster || {}), ...(picked.roster || {})}} : {})}
      : picked;
    const [basisFrom, basis] = pick(basisOf, complete);
    const [overridesFrom, overrides] = pick(overridesOf, complete);
    // Source availability is what this reader's page loaded, never what a link says the sender saw.
    const own = [l.local, l.saved].find(c => c && c.sources && Object.keys(c.sources).length);
    const common = sealCommon({league, valuation: {basis, overrides}, sources: own ? own.sources : {}, warnings: []});
    return deepFreeze({common, provenance: {league: leagueFrom, basis: basisFrom, overrides: overridesFrom}});
  }

  // ---------- teams ----------
  const cleanEntries = list => workspaceApi().cleanEntries(list);
  const rosterKeys = roster => roster.map(e => e.key).sort();
  // A saved team by its stable ID. A rename keeps the ID (and shows the new name); a deleted ID stays an explicit missing
  // selection rather than falling back to another team or a name match.
  const findTeam = (ws, id) => (isObject(ws) && Array.isArray(ws.teams) ? ws.teams.find(t => t && t.id === String(id)) || null : null);
  const sameKeys = (a, b) => rosterKeys(a).join(",") === rosterKeys(b).join(",");
  function savedTeam(ws, id) {
    if (id === null || id === undefined || id === "") return null;
    const team = findTeam(ws, id);
    if (!team) return {id: String(id), name: null, provenance: "saved", missing: true, matchesSaved: false, roster: []};
    return {id: team.id, name: team.name, provenance: "saved", missing: false, matchesSaved: true, roster: cleanEntries(team.entries)};
  }
  // A roster that is not a saved team: pasted or edited on this page (local) or carried by a link. No saved ID: a link
  // from another device must not depend on the sender's private team IDs.
  function rosterTeam(entries, provenance, name) {
    return {id: null, name: name || null, provenance: PROVENANCE.includes(provenance) ? provenance : "local", missing: false, matchesSaved: null,
      roster: cleanEntries(entries)};
  }
  // The roster a page is showing (finder.js getMine()/getTheirs()), loaded from saved team `id` and perhaps edited since.
  // The shown snapshot is authoritative: the ID is origin metadata only and never reloads the saved roster over it, even
  // when the saved team changed, was emptied or was deleted. missing says the origin ID is gone; matchesSaved says
  // whether the snapshot still equals the saved roster. The saved team's name is used only while they match.
  function workingTeam(ws, id, entries, provenance, name) {
    const roster = cleanEntries(entries);
    if (id === null || id === undefined || id === "") return rosterTeam(roster, provenance, name);
    const team = findTeam(ws, id);
    const matches = Boolean(team) && sameKeys(roster, cleanEntries(team.entries));
    return {id: String(id), name: name || (matches ? team.name : null),
      provenance: PROVENANCE.includes(provenance) ? provenance : matches ? "saved" : "local",
      missing: !team, matchesSaved: matches, roster};
  }
  const freezeTeam = team => (team ? {...team, rosterKey: rosterKeys(team.roster).join(",")} : null);

  // ---------- deal ----------
  // Explicit give/get keys. Duplicates go; a key on both sides stays on give (as decodeFinderHash keeps it on "mine").
  function normalizeDeal(raw) {
    if (!isObject(raw)) return null;
    const side = list => {
      const seen = new Set();
      return (Array.isArray(list) ? list : []).map(p => (isObject(p) ? p.key : p)).filter(k => k !== undefined && k !== null)
        .map(String).filter(k => PLAYER_KEY.test(k) && !seen.has(k) && seen.add(k));
    };
    const give = side(raw.give);
    const giveSet = new Set(give);
    const get = side(raw.get || raw.receive).filter(k => !giveSet.has(k));
    return give.length || get.length ? {give, get} : null;
  }
  // Keys in the deal that the side's roster snapshot does not hold (Compare may add any player; the readout can say so).
  function unresolvedDeal(context) {
    if (!context.deal) return {give: [], get: []};
    const has = team => new Set(team ? team.roster.map(e => e.key) : []);
    const mine = has(context.teams.mine);
    const theirs = has(context.teams.theirs);
    return {give: context.teams.mine ? context.deal.give.filter(k => !mine.has(k)) : [],
      get: context.teams.theirs ? context.deal.get.filter(k => !theirs.has(k)) : []};
  }

  // ---------- route controls (page-specific, never shared) ----------
  const LEAGUE_SIZES = [2, 3, 4];
  // league.js offers all / natural / naturalMarket; an older saved "naturalValue" means naturalMarket (opportunities.js).
  const LEAGUE_FIT = ["all", "natural", "naturalMarket"];
  function routeControls(route, raw) {
    const r = isObject(raw) ? raw : {};
    if (route === "pair") return {finder: workspaceApi().normalizeFinderSettings(r.finder || r)};
    if (route === "league") {
      const f = isObject(r.filters) ? r.filters : {};
      const nonNeg = v => (finite(Number(v)) && Number(v) >= 0 ? Number(v) : 0);
      // league.js reads ws.ui.maxSize || 2 and always searches with both keep flags on.
      return {maxSize: LEAGUE_SIZES.includes(Number(r.maxSize)) ? Number(r.maxSize) : 2, keepMine: true, keepTheirs: true,
        rankBasis: r.rankBasis === "market" ? "market" : "fund", hideForce: Boolean(r.hideForce),
        filters: {fit: f.fit === "naturalValue" ? "naturalMarket" : LEAGUE_FIT.includes(f.fit) ? f.fit : "all", opponent: f.opponent === undefined || f.opponent === null ? "all" : String(f.opponent),
          minCapture: nonNeg(f.minCapture), minCharts: nonNeg(f.minCharts)}};
    }
    return {};
  }

  // ---------- pricing identity (which bench level priced the rows, and exactly which rows) ----------
  // JEG-1259 / JEG-1188 (#1105): with a whole league loaded, league.js prices DDF Value at the "ddf" level and the trade
  // charts at the "market" level (curve-widget getLeagueLevel); Compare and the pair finder price the "modeled" bench.
  // The identity of a level is a hash of the rows (every value of every player the trade touches), the allocation and the
  // weights that level produced. Two pages with the same identity show the same values and the same lineup gains; a page
  // that cannot reproduce it must hold the trade, never reprice it on another level.
  const LEVELS = ["ddf", "market", "modeled"];
  const PRICING_MODES = {league: ["ddf", "market"], modeled: ["modeled"]};
  // The players whose rows decide a readout: both rosters and the explicit deal (Compare may add a player off a roster).
  function pricingKeys(parts) {
    const p = isObject(parts) ? parts : {};
    const keys = new Set();
    [p.mine, p.theirs].forEach(list => (Array.isArray(list) ? list : []).forEach(e => keys.add(String(isObject(e) ? e.key : e))));
    if (isObject(p.deal)) ["give", "get"].forEach(s => (p.deal[s] || []).forEach(k => keys.add(String(k))));
    return [...keys].filter(k => PLAYER_KEY.test(k)).sort();
  }
  // level: "ddf" | "market" | "modeled". data: {rows (getAllRows() shape), allocation, weights, keys?}. With keys, only
  // those players' rows count. A player with no row is recorded as null, so a missing row is never the same as a zero.
  function levelIdentity(level, data) {
    if (!LEVELS.includes(level)) throw new Error(`Unknown bench level: ${level}`);
    const d = isObject(data) ? data : {};
    const byKey = new Map((Array.isArray(d.rows) ? d.rows : []).filter(isObject).map(r => [String(r.player_key), r]));
    const keys = Array.isArray(d.keys) ? d.keys.map(String).sort() : [...byKey.keys()].sort();
    const rows = keys.map(k => [k, byKey.has(k) ? (byKey.get(k).values || {}) : null]);
    const part = v => (v === undefined || v === null ? null : hash(stable(v)));
    return deepFreeze({level, rows: hash(stable(rows)), allocation: part(d.allocation), weights: part(d.weights),
      players: rows.filter(([, v]) => v !== null).length});
  }
  // raw: {mode: "league" | "modeled", levels: {level: levelIdentity}, rostered?, reserve?}. rostered / reserve are the
  // league's rostered and IR/taxi keys the league levels were run with, so another page can run the same levels.
  function normalizePricing(raw, warnings) {
    if (raw === undefined || raw === null) return null;
    if (!isObject(raw) || !PRICING_MODES[raw.mode] || !isObject(raw.levels)) { warnings.push("pricing: unknown shape, dropped"); return null; }
    const id = v => (typeof v === "string" && /^[0-9a-z]{1,16}$/.test(v) ? v : null);
    const levels = {};
    for (const level of PRICING_MODES[raw.mode]) {
      const l = raw.levels[level];
      if (!isObject(l) || !id(l.rows)) { warnings.push(`pricing: ${level} level has no row identity, dropped`); return null; }
      levels[level] = {level, rows: id(l.rows), allocation: id(l.allocation), weights: id(l.weights),
        players: Number.isInteger(l.players) && l.players >= 0 ? l.players : null};
    }
    const keys = list => (Array.isArray(list) ? [...new Set(list.map(String).filter(k => PLAYER_KEY.test(k)))].sort() : null);
    return {mode: raw.mode, levels, rostered: raw.mode === "league" ? keys(raw.rostered) : null,
      reserve: raw.mode === "league" ? keys(raw.reserve) || [] : null};
  }
  // Versions of what priced a context: a change in any of them means a cached or carried result no longer applies.
  function versionsOf(common, pricing) {
    const basis = common.valuation.basis;
    const canonical = basis && basis.mode === "blend" ? {...basis, sources: basis.sources.slice().sort()} : basis;
    return {settings: hash(stable(common.league)), basis: hash(stable({basis: canonical, overrides: common.valuation.overrides})),
      sources: hash(stable(common.sources)), pricing: pricing ? hash(stable(pricing)) : null};
  }

  // ---------- the context ----------
  // input: {route, common (from normalizeCommon/resolveCommon), commonProvenance?, mine, theirs, opponents?, deal?,
  // controls?, provenance?, workspaceId?, pricing?, origin?}. mine/theirs/opponents are team refs from savedTeam/rosterTeam.
  // pricing: normalizePricing's shape (which level priced the rows). origin: where a carried trade came from (receive).
  function createContext(input) {
    const i = isObject(input) ? input : {};
    if (!ROUTES.includes(i.route)) throw new Error(`Unknown trade route: ${i.route}`);
    const caps = CAPABILITIES[i.route];
    const warnings = [];
    const common = NORMALIZED.has(i.common) ? i.common : normalizeCommon(i.common);
    const deal = normalizeDeal(i.deal);
    if (i.route === "compare" && isObject(i.controls) && Object.keys(i.controls).length) warnings.push("compare: discovery controls ignored");
    const opponents = caps.multipleOpponents ? (Array.isArray(i.opponents) ? i.opponents : []).filter(Boolean).map(freezeTeam) : [];
    const pricing = isObject(i.pricing) && i.pricing.levels ? normalizePricing(i.pricing, warnings) : null;
    const sealed = sealCommon({league: common.league, valuation: common.valuation, sources: common.sources});
    const context = {
      v: VERSION, route: i.route, capabilities: {...caps},
      common: sealed,
      commonProvenance: isObject(i.commonProvenance) ? {...i.commonProvenance} : null,
      teams: {mine: freezeTeam(i.mine || null), theirs: caps.multipleOpponents ? null : freezeTeam(i.theirs || null), opponents},
      deal,
      controls: routeControls(i.route, i.controls),
      provenance: PROVENANCE.includes(i.provenance) ? i.provenance : "saved",
      workspaceId: typeof i.workspaceId === "string" && i.workspaceId ? i.workspaceId : null,
      pricing,
      versions: versionsOf(sealed, pricing),
      origin: isObject(i.origin) ? i.origin : null,
      discrepancies: ROUTE_DISCREPANCIES.filter(d => d.routes.includes(i.route)).map(d => d.id),
      warnings: (common.warnings || []).concat(warnings)
    };
    return deepFreeze(context);
  }
  // A new context with one change. Inputs are never mutated; the old context stays valid (that is Cancel / Undo).
  function withChanges(context, patch) {
    const p = isObject(patch) ? patch : {};
    return createContext({route: context.route, common: context.common, commonProvenance: context.commonProvenance,
      mine: "mine" in p ? p.mine : context.teams.mine, theirs: "theirs" in p ? p.theirs : context.teams.theirs,
      opponents: "opponents" in p ? p.opponents : context.teams.opponents, deal: "deal" in p ? p.deal : context.deal,
      controls: "controls" in p ? p.controls : context.controls, provenance: p.provenance || context.provenance,
      workspaceId: context.workspaceId, pricing: "pricing" in p ? p.pricing : context.pricing, origin: context.origin});
  }
  // Selecting a team is view state: it returns a new context and never touches the workspace, its roster or its star.
  function selectTeam(context, side, ws, id) {
    if (side !== "mine" && side !== "theirs") throw new Error(`Unknown side: ${side}`);
    return withChanges(context, {[side]: savedTeam(ws, id)});
  }
  // An incoming context (a link, a pasted state) for this visit. Cancel returns the previous context unchanged.
  function beginVisit(current, incoming) {
    return Object.freeze({context: incoming, previous: current, cancel: () => current});
  }
  // Whether a part of the context may be written back to saved storage. Link and local (visit) context never may: the
  // reader's saved rosters, star and preferences change only through their own saved edits.
  function maySave(context, part) {
    if (part === "league" || part === "basis" || part === "overrides") {
      // Per-section provenance when the page resolved it; otherwise the context's own provenance, so a link or local visit
      // built without commonProvenance can never save its league, basis or overrides.
      return context.commonProvenance ? context.commonProvenance[part] === "saved" : context.provenance === "saved";
    }
    if (part === "mine" || part === "theirs") {
      const team = context.teams[part];
      return context.provenance === "saved" && Boolean(team) && team.provenance === "saved" && !team.missing;
    }
    return false;
  }

  // ---------- cache keys ----------
  // Everything that can change a result, nothing that only changes a label: team names and provenance are left out, roster
  // order is not significant. purpose "discovery" adds the route's controls (so a changed control can never show stale
  // offers); "readout" adds the explicit deal and leaves the discovery controls out.
  // The other side of the explicit deal: Their team, or on the league finder the one opponent holding every received key.
  function dealPartner(context) {
    if (context.teams.theirs || !context.deal) return context.teams.theirs;
    const holders = context.teams.opponents.filter(o => context.deal.get.length && context.deal.get.every(k => o.roster.some(e => e.key === k)));
    return holders.length === 1 ? holders[0] : null;
  }
  function cacheParts(context, purpose) {
    const kind = purpose === "readout" ? "readout" : "discovery";
    if (kind === "discovery" && !context.capabilities.discovery) return null;
    const readout = kind === "readout";
    // Discovery keeps each team's stable ID with its roster: an ID-based control (the league opponent filter) picks a team
    // by ID, so two teams swapping rosters must change the key. A readout prices two rosters and stays identity-free.
    const team = t => (t ? (readout ? {roster: t.rosterKey} : {id: t.id, roster: t.rosterKey}) : null);
    const order = (a, b) => { const x = stable(a); const y = stable(b); return x < y ? -1 : x > y ? 1 : 0; };
    const basis = context.common.valuation.basis;
    const canonicalBasis = basis && basis.mode === "blend" ? {...basis, sources: basis.sources.slice().sort()} : basis;
    return {v: VERSION, kind, route: kind === "discovery" ? context.route : null,
      league: context.common.league, valuation: {basis: canonicalBasis, overrides: context.common.valuation.overrides}, sources: context.common.sources,
      mine: team(context.teams.mine), theirs: team(readout ? dealPartner(context) : context.teams.theirs),
      // A readout is one explicit trade between two rosters: the league's other opponents do not change it.
      opponents: readout ? [] : context.teams.opponents.map(team).sort(order),
      // The bench level and its exact rows: the same trade on another level, or on rebuilt rows, is another result.
      pricing: context.pricing,
      controls: kind === "discovery" ? context.controls : null,
      deal: kind === "readout" && context.deal ? {give: context.deal.give.slice().sort(), get: context.deal.get.slice().sort()} : null};
  }
  function cacheKey(context, purpose) {
    const parts = cacheParts(context, purpose);
    return parts ? `tc${VERSION}:${parts.kind[0]}:${hash(stable(parts))}` : null;
  }
  const commonKey = context => `tc${VERSION}:c:${hash(stable(context.common))}`;

  // ---------- route adapters ----------
  // Each page's current state shape in, one TradeContext out. env: {common, commonProvenance?, provenance?}.

  // Pair finder (finder.js): view.mine / view.theirs are the rosters the page shows (getMine()/getTheirs()) and are
  // authoritative; view.mineId / view.theirId are their origin saved-team IDs (JEG-1219). An ID with no shown roster reads
  // the saved team. settings: ws.ui.finderSettings or the page's S.
  function fromPair(env, ws, view, settings) {
    const v = isObject(view) ? view : {};
    // A shown roster (an array, even empty) wins over its origin ID; an ID alone reads the saved team.
    const side = (id, entries, provenance, name) => (Array.isArray(entries) ? workingTeam(ws, id, entries, provenance, name)
      : id ? savedTeam(ws, id) : null);
    return createContext({route: "pair", common: env.common, commonProvenance: env.commonProvenance, provenance: env.provenance,
      workspaceId: isObject(ws) ? ws.id : null, pricing: env.pricing,
      mine: side(v.mineId, v.mine, v.mineProvenance, v.mineName), theirs: side(v.theirId, v.theirs, v.theirsProvenance, v.theirName),
      deal: v.deal, controls: {finder: settings}});
  }
  // League finder (league.js): the starred team against every other saved team; controls from ws.ui.
  function fromLeague(env, ws) {
    const w = isObject(ws) ? ws : {teams: []};
    const teams = Array.isArray(w.teams) ? w.teams : [];
    const mine = w.myTeamId ? savedTeam(w, w.myTeamId) : null;
    const opponents = teams.filter(t => t && t.id !== w.myTeamId).map(t => savedTeam(w, t.id));
    const context = createContext({route: "league", common: env.common, commonProvenance: env.commonProvenance, provenance: env.provenance,
      workspaceId: w.id || null, pricing: env.pricing, mine, opponents, controls: w.ui, deal: env.deal});
    // A saved opponent filter whose team is gone: reported, not rewritten (league.js decides what to show).
    const opp = context.controls.filters.opponent;
    if (opp !== "all" && !opponents.some(o => o.id === opp)) {
      return deepFreeze({...context, warnings: context.warnings.concat(`league: opponent filter ${opp} is not a saved opponent`)});
    }
    return context;
  }
  // Compare (v2.js): TR.give / TR.receive are the explicit deal; compareTeams.mineId / theirId are view-only saved IDs.
  // Compare's own automatic opponent choice stays in v2.js (see ROUTE_DISCREPANCIES); this adapter takes the IDs it has.
  function fromCompare(env, ws, trade, teams) {
    const t = isObject(trade) ? trade : {};
    const ids = isObject(teams) ? teams : {};
    return createContext({route: "compare", common: env.common, commonProvenance: env.commonProvenance, provenance: env.provenance,
      workspaceId: isObject(ws) ? ws.id : null, pricing: env.pricing, mine: ids.mineId ? savedTeam(ws, ids.mineId) : null, theirs: ids.theirId ? savedTeam(ws, ids.theirId) : null,
      deal: {give: t.give, get: t.receive || t.get}});
  }

  // ---------- carrying one trade between pages (league → Compare / pair finder, reload, a shared link) ----------
  // JEG-1259. The sending page writes a transfer: the explicit deal, both roster snapshots with their origin IDs, the
  // league settings, basis, overrides, the sources it saw and the identity of the bench level(s) that priced it. The
  // receiving page resolves its own settings (applying the carried ones as a link layer), reruns the same level(s) and
  // calls receive(). Either everything that decides the values and gains matches, and it gets a context with the carried
  // rosters, or it gets an explicit hold that names what differs. It never reprices on another level and never writes
  // the reader's saved teams: a foreign device keeps the carried rosters as link rosters.
  const TRANSFER_VERSION = 1;
  const snapshot = team => (team ? {id: team.id || null, roster: team.roster.map(e => ({...e}))} : null);
  function toTransfer(context) {
    const partner = dealPartner(context);
    const body = {v: TRANSFER_VERSION, from: context.route, workspaceId: context.workspaceId,
      settings: context.common.league, valuation: context.common.valuation, sources: context.common.sources,
      versions: context.versions, pricing: context.pricing,
      mine: snapshot(context.teams.mine), theirs: snapshot(partner),
      partnerIds: partner && partner.id ? [partner.id] : [], deal: context.deal};
    return deepFreeze({...body, sum: hash(stable(body))});
  }
  // A transfer as one URL-safe parameter value (base64url of its JSON; names may be any Unicode).
  function encodeTransfer(transfer) {
    const json = JSON.stringify(transfer);
    const b64 = typeof Buffer !== "undefined" ? Buffer.from(json, "utf8").toString("base64")
      : globalThis.btoa(unescape(encodeURIComponent(json)));
    return b64.replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
  }
  function decodeTransfer(text) {
    if (typeof text !== "string" || !text || text.length > 200000 || !/^[A-Za-z0-9_-]+$/.test(text)) return null;
    try {
      const b64 = text.replace(/-/g, "+").replace(/_/g, "/");
      const json = typeof Buffer !== "undefined" ? Buffer.from(b64, "base64").toString("utf8") : decodeURIComponent(escape(globalThis.atob(b64)));
      const parsed = JSON.parse(json);
      return isObject(parsed) ? parsed : null;
    } catch (error) { return null; }
  }
  const hold = (reasons, carried) => deepFreeze({status: "hold", reasons, carried: carried || null, context: null});
  // transfer: toTransfer's object (or decodeTransfer's). here: {route: "compare" | "pair", common (this page's resolved
  // common, after applying the carried settings as a link), commonProvenance?, pricing (this page's identity of the same
  // level(s), run with the carried rostered set; null if it cannot run them), ws (this reader's workspace)}.
  // Returns frozen {status: "ok", context, carried} or {status: "hold", reasons: [{code, where, detail}], carried}.
  function receive(transfer, here) {
    const h = isObject(here) ? here : {};
    if (!isObject(transfer)) return hold([{code: "context-missing", where: "transfer", detail: "no trade context arrived with this page"}]);
    const {sum, ...body} = transfer;
    if (transfer.v !== TRANSFER_VERSION) return hold([{code: "context-unsupported", where: "transfer", detail: `transfer version ${transfer.v} is not ${TRANSFER_VERSION}`}]);
    if (sum !== hash(stable(body))) return hold([{code: "context-unreadable", where: "transfer", detail: "the trade context was changed or cut on the way"}]);
    if (!ROUTES.includes(h.route) || h.route === "league") throw new Error(`Cannot receive a trade on route: ${h.route}`);
    const reasons = [];
    const add = (code, where, detail) => reasons.push({code, where, detail});
    const json = v => stable(v === undefined ? null : v);
    const mineCommon = NORMALIZED.has(h.common) ? h.common : normalizeCommon(h.common);
    const warnings = [];
    const pricing = normalizePricing(transfer.pricing, warnings);
    const herePricing = normalizePricing(h.pricing, warnings);
    if (json(transfer.settings) !== json(mineCommon.league)) add("settings-changed", "settings", "this page's league settings differ from the trade's");
    const canonical = b => (b && b.mode === "blend" ? {...b, sources: b.sources.slice().sort()} : b);
    if (json(canonical((transfer.valuation || {}).basis)) !== json(canonical(mineCommon.valuation.basis))) add("basis-changed", "basis", "this page's value basis differs from the trade's");
    if (json((transfer.valuation || {}).overrides) !== json(mineCommon.valuation.overrides)) add("overrides-changed", "overrides", "this page's player overrides differ from the trade's");
    if (json(transfer.sources) !== json(mineCommon.sources)) add("sources-changed", "sources", "a source is unavailable, held or a different version here");
    if (!pricing) add("level-missing", "level", "the trade does not say which bench level priced it");
    else if (!herePricing || herePricing.mode !== pricing.mode) add("level-changed", "level", `the trade was priced at the ${pricing.mode} level(s); this page cannot run them`);
    else {
      Object.keys(pricing.levels).forEach(level => {
        const a = pricing.levels[level];
        const b = herePricing.levels[level];
        ["rows", "allocation", "weights"].forEach(part => {
          if (a[part] !== b[part]) add(`${part}-changed`, `level.${level}.${part}`, `the ${level} level's ${part} were rebuilt since the trade was priced`);
        });
        if (a.players !== b.players) add("rows-changed", `level.${level}.players`, `the ${level} level prices ${b.players} of the trade's players, not ${a.players}`);
      });
      // The league levels are run with both key sets: rostered (active depth) and reserve (IR / taxi, held but not depth).
      ["rostered", "reserve"].forEach(set => {
        if (json(pricing[set]) !== json(herePricing[set])) add("level-changed", `level.${set}`, `the league's ${set} players behind the levels differ`);
      });
    }
    if (!isObject(transfer.mine) || !Array.isArray(transfer.mine.roster)) add("team-missing", "mine", "your roster did not arrive");
    if (!isObject(transfer.theirs) || !Array.isArray(transfer.theirs.roster)) add("team-missing", "theirs", "the other team's roster did not arrive");
    const deal = normalizeDeal(transfer.deal);
    if (!deal) add("package-missing", "package", "the trade's players did not arrive");
    if (reasons.length) return hold(reasons, transfer);
    // Same device and workspace: the carried rosters keep their origin IDs (shown roster authoritative, saved only while it
    // still matches). Any other workspace: link rosters with no IDs, so the reader's own teams are never substituted.
    const ws = isObject(h.ws) ? h.ws : null;
    const sameWorkspace = Boolean(ws && transfer.workspaceId && ws.id === transfer.workspaceId);
    // On another workspace (another device, or the same league saved under other IDs) a carried roster is shown as the
    // reader's saved team only when exactly one of the reader's teams has exactly the same players; never by name.
    const exact = t => {
      if (!ws || !Array.isArray(ws.teams)) return null;
      const want = rosterKeys(cleanEntries(t.roster)).join(",");
      const hits = want ? ws.teams.filter(s => isObject(s) && rosterKeys(cleanEntries(s.entries)).join(",") === want) : [];
      return hits.length === 1 ? hits[0] : null;
    };
    const team = t => {
      if (sameWorkspace) return workingTeam(ws, t.id, t.roster);
      const hit = exact(t);
      return hit ? workingTeam(ws, hit.id, t.roster) : rosterTeam(t.roster, "link");
    };
    const context = createContext({route: h.route, common: mineCommon, commonProvenance: h.commonProvenance,
      provenance: sameWorkspace ? (PROVENANCE.includes(h.provenance) ? h.provenance : "local") : "link",
      // The receiving page's own pricing, now validated equal to the trade's in every compared part.
      workspaceId: ws ? ws.id : null, pricing: herePricing, mine: team(transfer.mine), theirs: team(transfer.theirs), deal,
      origin: {route: ROUTES.includes(transfer.from) ? transfer.from : null, workspaceId: transfer.workspaceId || null,
        mineId: transfer.mine.id || null, theirId: transfer.theirs.id || null,
        partnerIds: Array.isArray(transfer.partnerIds) ? transfer.partnerIds.map(String) : [], sameWorkspace}});
    return deepFreeze({status: "ok", context, carried: transfer, reasons: []});
  }

  // ---------- page adapters (browser engine shapes, no DOM) ----------
  // The engine's getSourceInfo() list as sources: available only when loaded and present in this build's data; version is
  // the source's week label plus its stale flag, compared only.
  function sourcesFromEngine(info) {
    const out = {};
    (Array.isArray(info) ? info : []).forEach(item => {
      if (!isObject(item) || !SOURCE_KEY.test(String(item.key))) return;
      const week = item.week === undefined || item.week === null || item.week === "" ? null : String(item.week);
      const version = [week, item.stale ? "stale" : null].filter(Boolean).join(" ") || null;
      out[item.key] = {available: item.available === true && !item.unavailable, held: Boolean(item.paused), version};
    });
    return out;
  }
  // This page's modeled bench pricing (every page on main today): the engine's rows, allocation and bench readout, the
  // same objects league.js mathContext() prices with. keys: pricingKeys() of the trade. null without an engine.
  function modeledPricing(engine, keys) {
    if (!engine || typeof engine.getAllRows !== "function") return null;
    const adjust = typeof engine.getAdjustmentWeights === "function" ? engine.getAdjustmentWeights() : null;
    const readout = typeof engine.getBenchShareReadout === "function" ? engine.getBenchShareReadout() : null;
    return {mode: "modeled", levels: {modeled: levelIdentity("modeled", {rows: engine.getAllRows(),
      allocation: adjust ? adjust.allocation : null, weights: readout, keys})}};
  }

  return {VERSION, ROUTES, CAPABILITIES, ROUTE_DISCREPANCIES, normalizeCommon, commonFromPage, leagueFromQuery, resolveCommon,
    savedTeam, rosterTeam, workingTeam, normalizeDeal, unresolvedDeal, routeControls, createContext, withChanges, selectTeam, beginVisit, maySave,
    cacheParts, cacheKey, commonKey, dealPartner, fromPair, fromLeague, fromCompare, stable,
    LEVELS, pricingKeys, levelIdentity, normalizePricing, TRANSFER_VERSION, toTransfer, encodeTransfer, decodeTransfer, receive,
    sourcesFromEngine, modeledPricing};
});
