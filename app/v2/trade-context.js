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
  // sources: {key: {available, held?, reason?}} from the page. A source the page did not report is "unknown", never
  // assumed available.
  function normalizeSources(raw, warnings) {
    if (raw === undefined || raw === null) return {};
    if (!isObject(raw)) { warnings.push("sources: not an object, dropped"); return {}; }
    const out = {};
    Object.keys(raw).sort().forEach(key => {
      if (!SOURCE_KEY.test(key)) return;
      const s = raw[key];
      const status = !isObject(s) ? "unknown" : s.held ? "held" : s.available === true ? "available" : s.available === false ? "unavailable" : "unknown";
      out[key] = {status, reason: isObject(s) && typeof s.reason === "string" && s.reason ? s.reason : null};
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
  function savedTeam(ws, id) {
    if (id === null || id === undefined || id === "") return null;
    const team = isObject(ws) && Array.isArray(ws.teams) ? ws.teams.find(t => t && t.id === String(id)) : null;
    if (!team) return {id: String(id), name: null, provenance: "saved", missing: true, roster: []};
    return {id: team.id, name: team.name, provenance: "saved", missing: false, roster: cleanEntries(team.entries)};
  }
  // A roster that is not a saved team: pasted or edited on this page (local) or carried by a link. No saved ID: a link
  // from another device must not depend on the sender's private team IDs.
  function rosterTeam(entries, provenance, name) {
    return {id: null, name: name || null, provenance: PROVENANCE.includes(provenance) ? provenance : "local", missing: false, roster: cleanEntries(entries)};
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

  // ---------- the context ----------
  // input: {route, common (from normalizeCommon/resolveCommon), commonProvenance?, mine, theirs, opponents?, deal?,
  // controls?, provenance?}. mine/theirs/opponents are team refs from savedTeam/rosterTeam.
  function createContext(input) {
    const i = isObject(input) ? input : {};
    if (!ROUTES.includes(i.route)) throw new Error(`Unknown trade route: ${i.route}`);
    const caps = CAPABILITIES[i.route];
    const warnings = [];
    const common = NORMALIZED.has(i.common) ? i.common : normalizeCommon(i.common);
    const deal = normalizeDeal(i.deal);
    if (i.route === "compare" && isObject(i.controls) && Object.keys(i.controls).length) warnings.push("compare: discovery controls ignored");
    const opponents = caps.multipleOpponents ? (Array.isArray(i.opponents) ? i.opponents : []).filter(Boolean).map(freezeTeam) : [];
    const context = {
      v: VERSION, route: i.route, capabilities: {...caps},
      common: sealCommon({league: common.league, valuation: common.valuation, sources: common.sources}),
      commonProvenance: isObject(i.commonProvenance) ? {...i.commonProvenance} : null,
      teams: {mine: freezeTeam(i.mine || null), theirs: caps.multipleOpponents ? null : freezeTeam(i.theirs || null), opponents},
      deal,
      controls: routeControls(i.route, i.controls),
      provenance: PROVENANCE.includes(i.provenance) ? i.provenance : "saved",
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
      controls: "controls" in p ? p.controls : context.controls, provenance: p.provenance || context.provenance});
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
      return !context.commonProvenance || context.commonProvenance[part] === "saved";
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
    const team = t => (t ? {missing: t.missing, roster: t.rosterKey} : null);
    const readout = kind === "readout";
    const basis = context.common.valuation.basis;
    const canonicalBasis = basis && basis.mode === "blend" ? {...basis, sources: basis.sources.slice().sort()} : basis;
    return {v: VERSION, kind, route: kind === "discovery" ? context.route : null,
      league: context.common.league, valuation: {basis: canonicalBasis, overrides: context.common.valuation.overrides}, sources: context.common.sources,
      mine: team(context.teams.mine), theirs: team(readout ? dealPartner(context) : context.teams.theirs),
      // A readout is one explicit trade between two rosters: the league's other opponents do not change it.
      opponents: readout ? [] : context.teams.opponents.map(team).sort((a, b) => (a.roster < b.roster ? -1 : a.roster > b.roster ? 1 : 0)),
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

  // Pair finder (finder.js): view.mineId / view.theirId are saved team IDs (JEG-1219); without one, the side is the roster
  // on the page (pasted, edited or from a link). settings: ws.ui.finderSettings or the page's S.
  function fromPair(env, ws, view, settings) {
    const v = isObject(view) ? view : {};
    const side = (id, entries, provenance) => (id ? savedTeam(ws, id) : entries ? rosterTeam(entries, provenance) : null);
    return createContext({route: "pair", common: env.common, commonProvenance: env.commonProvenance, provenance: env.provenance,
      mine: side(v.mineId, v.mine, v.mineProvenance || env.provenance), theirs: side(v.theirId, v.theirs, v.theirsProvenance || env.provenance),
      deal: v.deal, controls: {finder: settings}});
  }
  // League finder (league.js): the starred team against every other saved team; controls from ws.ui.
  function fromLeague(env, ws) {
    const w = isObject(ws) ? ws : {teams: []};
    const teams = Array.isArray(w.teams) ? w.teams : [];
    const mine = w.myTeamId ? savedTeam(w, w.myTeamId) : null;
    const opponents = teams.filter(t => t && t.id !== w.myTeamId).map(t => savedTeam(w, t.id));
    const context = createContext({route: "league", common: env.common, commonProvenance: env.commonProvenance, provenance: env.provenance,
      mine, opponents, controls: w.ui, deal: env.deal});
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
      mine: ids.mineId ? savedTeam(ws, ids.mineId) : null, theirs: ids.theirId ? savedTeam(ws, ids.theirId) : null,
      deal: {give: t.give, get: t.receive || t.get}});
  }

  return {VERSION, ROUTES, CAPABILITIES, ROUTE_DISCREPANCIES, normalizeCommon, commonFromPage, leagueFromQuery, resolveCommon,
    savedTeam, rosterTeam, normalizeDeal, unresolvedDeal, routeControls, createContext, withChanges, selectTeam, beginVisit, maySave,
    cacheParts, cacheKey, commonKey, dealPartner, fromPair, fromLeague, fromCompare, stable};
});
