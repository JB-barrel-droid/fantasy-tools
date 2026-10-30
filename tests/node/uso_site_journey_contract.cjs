// JEG-1240 / JEG-1264: the USO-shape trade journey, as a contract on the real page modules. Pure Node, no browser.
//
//   node tests/node/uso_site_journey_contract.cjs check <app dir> <league.json>
//       Runs the journey on modeled values and prints {ran, failures, facts}. Each failure is
//       {name, kind: "harness" | "continuity", message, cases: [{case, code}]}.
//   node tests/node/uso_site_journey_contract.cjs diff <origin.json> <destination.json> [tolerance]
//       Compares two trade-context envelopes (the render test reads them off the page) and prints {differences}.
//
// The journey: load the USO-shape league, read both sides' starters and bench by position, run the league-wide search
// with no candidate cap, find the trades that send Jaxon Smith-Njigba (key 3247), pick an equal, a throw-in and an
// explicit unequal package, then carry each one to a destination page and require the same settings, basis, bench
// level, sources, rosters, package, values, gains and starter/bench readout on arrival, or an explicit hold that names
// every difference. Nothing here asserts a fit label: JSN only has to be discoverable.
//
// Two kinds of check. Harness checks are green on every build: they prove the fixture, the search, the picks, the
// lineup math and that each kind of lost context fails with its own code. Continuity checks carry the trade through
// the site's codecs (the DDF state link, the pair finder link and, where app/v2 has it, the JEG-1259 trade context
// transfer) and are red until the site carries the context or holds the trade; they are never adjusted to pass.
//
// Destinations are built on their own state, never from the origin's: the same device (a deep copy of the origin's
// settings, basis, sources and saved league) and another device (PPR, 10 teams, WR 2, BN 7, a single-source basis,
// CBS unavailable, its own saved league with another "my team"). Values are MODELED (deterministic per player key,
// salted with the settings, basis and bench level in force; a chart is priced only where that device has the source),
// so a page that drops a piece of context shows different numbers. Never published or USO numbers.
// Where app/v2 has trade-readout.js (JEG-1260) the readout is its summary; otherwise the same lineup math from finder.js.
"use strict";
const path = require("path");
const fs = require("fs");
const assert = require("assert");

const CH = ["usatoday", "fantasycalc", "fantasypros", "cbs"];
const OUR_KEY = "ddf_value";
const MARKET_KEY = "chart_avg";
const PROJ_KEY = "ddf_value_projections";
const SKILL = ["QB", "RB", "WR", "TE"];
const DATA_VERSION = "fixture-2026-10-29";
// Differences that follow from a lost piece of context (the numbers moved because the context did).
const REPRICE = ["value-changed", "value-lost", "value-filled", "value-missing", "gains-changed", "gains-missing", "readout-changed", "readout-missing"];
// Differences that are themselves lost context. A hold must name each one it held for.
const CAUSES = ["settings-changed", "basis-changed", "level-changed", "sources-changed", "team-missing", "team-substituted",
  "not-evaluated-changed", "package-changed"];
// The JEG-1259 hold reasons (trade-context.js receive) that account for each cause.
const HOLD_COVERS = {
  "settings-changed": ["settings-changed"],
  "basis-changed": ["basis-changed", "overrides-changed"],
  "sources-changed": ["sources-changed"],
  "level-changed": ["level-missing", "level-changed", "rows-changed", "allocation-changed", "weights-changed"],
  "team-missing": ["team-missing", "context-missing"],
  "team-substituted": ["team-missing"],
  "not-evaluated-changed": ["team-missing"],
  "package-changed": ["package-missing"]
};

const isObject = v => Boolean(v) && typeof v === "object" && !Array.isArray(v);
function stable(value) {
  if (Array.isArray(value)) return `[${value.map(stable).join(",")}]`;
  if (isObject(value)) return `{${Object.keys(value).sort().filter(k => value[k] !== undefined).map(k => `${JSON.stringify(k)}:${stable(value[k])}`).join(",")}}`;
  return JSON.stringify(value === undefined ? null : value);
}
const clone = v => JSON.parse(JSON.stringify(v));
const num = v => (typeof v === "number" && Number.isFinite(v) ? v : null);

// ---------- one device's state ----------
// {settings: {scoring, teams, roster: {QB, RB, WR, TE, FLEX, SUPERFLEX, BENCH}}, basis (overrides.js basisRecord shape),
//  level: "modeled" | "league", sources: {key: {status, reason, version}} (trade-context.js normalizeSources shape)}.
function sourcesOf(off) {
  return Object.fromEntries(CH.map(k => [k, {status: (off && off[k]) || "available",
    reason: off && off[k] ? `${off[k]} on this device` : null, version: DATA_VERSION}]));
}
const availableCharts = state => CH.filter(k => state.sources && state.sources[k] && state.sources[k].status === "available");
const shapeOf = s => (s && s.roster ? {QB: s.roster.QB, RB: s.roster.RB, WR: s.roster.WR, TE: s.roster.TE, FLEX: s.roster.FLEX,
  SUPERFLEX: s.roster.SUPERFLEX} : null);
// As v2.js applyLinkLeague: a link league replaces the page's settings; a part the link leaves out keeps the page's.
function applyLeague(settings, league) {
  if (!league) return settings;
  return {scoring: league.scoring !== undefined ? league.scoring : settings.scoring, teams: league.teams !== undefined ? league.teams : settings.teams,
    roster: {...settings.roster, ...(league.roster || {})}};
}

// ---------- modeled values ----------
function hash(text) { let h = 2166136261; for (const c of String(text)) { h ^= c.charCodeAt(0); h = Math.imul(h, 16777619) >>> 0; } return h >>> 0; }
const unit = (key, salt) => (hash(`${key}:${salt}`) % 10000) / 10000;
const round1 = n => Math.round(n * 10) / 10;
// Deterministic DDF / charts / projections per key. DDF and projections lean with the settings, basis and level in
// force; a chart exists only where the device has that source. holes: {key: [value keys to drop]}.
function modeledRows(players, state, holes) {
  const salt = stable({settings: state.settings, basis: state.basis, level: state.level});
  const charts = availableCharts(state);
  const map = new Map();
  players.forEach(p => {
    if (String(p.key).startsWith("x:") || map.has(String(p.key))) return;
    const base = 4 + 36 * Math.pow(unit(p.key, "d"), 1.6);
    const ddf = round1(base * (0.85 + 0.3 * unit(p.key, salt)));
    const values = {[OUR_KEY]: ddf, [PROJ_KEY]: round1(ddf * (0.8 + 0.4 * unit(p.key, `p${salt}`)))};
    const market = 0.62 + 0.76 * unit(p.key, "m");
    charts.forEach(k => { values[k] = round1(base * market * (0.9 + 0.2 * unit(p.key, k))); });
    ((holes && holes[p.key]) || []).forEach(k => { delete values[k]; });
    map.set(String(p.key), {player_key: String(p.key), name: p.name, pos: p.pos, team: p.team || "", values});
  });
  return map;
}

// ---------- the envelope: everything a trade must keep between screens ----------
// env: {state, rowsByKey}. teams: {mine, theirs}, each {id, entries} or null. give / get: player keys.
// A view a player has no value in is null, never 0.
function readoutOf(F, R, env, teams, give, get) {
  const shape = shapeOf(env.state.settings);
  if (!shape || !teams.mine || !teams.theirs) return null;
  const rows = team => team.entries.map(e => env.rowsByKey.get(String(e.key))).filter(Boolean);
  const sortKeys = list => list.map(String).sort();
  const fromKeys = l => ({slots: Object.fromEntries(Object.keys(l.slots).sort().map(s => [s, sortKeys(l.slots[s])])), bench: sortKeys(l.bench)});
  const fromRows = l => fromKeys({slots: Object.fromEntries(Object.entries(l.slots).map(([s, rs]) => [s, rs.map(r => r.player_key)])),
    bench: l.bench.map(r => r.player_key)});
  if (R) {
    const s = R.summary(R.build({shape, ourKey: OUR_KEY, chartKeys: availableCharts(env.state),
      sourceInfo: CH.map(k => ({key: k, available: availableCharts(env.state).includes(k)})),
      mine: {rows: rows(teams.mine), entries: teams.mine.entries}, theirs: {rows: rows(teams.theirs), entries: teams.theirs.entries},
      give, receive: get}, {finder: F}));
    if (!s.ready) return {ready: false, reason: s.reason};
    const side = v => (v && v.ddf ? {before: fromKeys(v.ddf.before), after: fromKeys(v.ddf.after)} : null);
    return {ready: true, us: side(s.mine), them: side(s.theirs)};
  }
  const mineRows = rows(teams.mine), theirRows = rows(teams.theirs);
  const pick = (list, keys) => keys.map(k => list.find(r => String(r.player_key) === String(k)));
  const g = pick(mineRows, give), r = pick(theirRows, get);
  if (!give.length || !get.length || g.includes(undefined) || r.includes(undefined)) {
    return {ready: false, reason: !give.length || !get.length ? "Add a player to both sides to see how each roster changes."
      : "This trade includes players outside the selected rosters."};
  }
  const us = F.rosterImpact(mineRows, g, r, shape, OUR_KEY), them = F.rosterImpact(theirRows, r, g, shape, OUR_KEY);
  return {ready: true, us: {before: fromRows(us.before), after: fromRows(us.after)}, them: {before: fromRows(them.before), after: fromRows(them.after)}};
}

function envelope(F, R, env, teams, give, get) {
  const state = env.state;
  const shape = shapeOf(state.settings);
  const charts = availableCharts(state);
  const market = charts.length >= F.MIN_CHARTS ? charts : null;
  const wide = rows => (market ? F.withChartAverage(rows, market) : rows);
  const byKey = new Map(wide([...env.rowsByKey.values()]).map(r => [String(r.player_key), r]));
  const pick = keys => keys.map(k => byKey.get(String(k))).filter(Boolean);
  const rowsOf = team => wide(team.entries.map(e => env.rowsByKey.get(String(e.key))).filter(Boolean));
  // Priced players by key; K, DEF and anything that does not resolve to a row are counted, not valued.
  const priced = e => !F.isNotEvaluated(e) && env.rowsByKey.has(String(e.key));
  const side = team => (team ? {id: team.id || null, keys: team.entries.filter(priced).map(e => String(e.key)).sort(),
    notEvaluated: team.entries.filter(e => !priced(e)).length} : null);
  const values = {};
  give.concat(get).forEach(k => {
    const r = byKey.get(String(k));
    values[k] = r ? {ddf: num(r.values[OUR_KEY]), market: market ? num(r.values[MARKET_KEY]) : null, proj: num(r.values[PROJ_KEY])} : null;
  });
  const gains = {};
  if (shape && teams.mine && teams.theirs) {
    const g = (team, leaving, arriving, key) => F.rosterImpact(rowsOf(team), pick(leaving), pick(arriving), shape, key);
    const us = g(teams.mine, give, get, OUR_KEY);
    const them = g(teams.theirs, get, give, OUR_KEY);
    gains.us = {ddf: num(us.starterDelta), ddfBefore: num(us.before.starterValue)};
    gains.them = {ddf: num(them.starterDelta)};
    if (market) {
      gains.us.market = num(g(teams.mine, give, get, MARKET_KEY).starterDelta);
      gains.them.market = num(g(teams.theirs, get, give, MARKET_KEY).starterDelta);
    }
  }
  return {settings: state.settings || null, basis: state.basis === undefined ? null : state.basis, level: state.level === undefined ? null : state.level,
    sources: state.sources || null, mine: side(teams.mine), theirs: side(teams.theirs), give: give.map(String), get: get.map(String),
    values, gains, readout: readoutOf(F, R, env, teams, give.map(String), get.map(String))};
}

// Each difference names what was lost or swapped. tol: numbers equal within it (the page shows one decimal).
// opts.ignore: codes a route cannot carry by design (the pair finder deals in skill players only).
function diff(a, b, tol, opts) {
  const t = tol === undefined ? 1e-9 : tol;
  const ignore = new Set((opts && opts.ignore) || []);
  const out = [];
  const add = (code, where, message) => { if (!ignore.has(code)) out.push({code, where, message}); };
  const same = (x, y) => (x === null || y === null ? x === y : Math.abs(x - y) <= t);
  const json = v => stable(v === undefined ? null : v);
  const text = v => JSON.stringify(v === undefined ? null : v);
  if (json(a.settings) !== json(b.settings)) add("settings-changed", "settings", `league settings ${text(a.settings)} became ${text(b.settings)}`);
  if (json(a.basis) !== json(b.basis)) add("basis-changed", "basis", `value basis ${text(a.basis)} became ${text(b.basis)}`);
  if (json(a.level) !== json(b.level)) add("level-changed", "level", `bench level ${text(a.level)} became ${text(b.level)}`);
  if (a.sources !== undefined && json(a.sources) !== json(b.sources)) {
    const keys = [...new Set(Object.keys(a.sources || {}).concat(Object.keys(b.sources || {})))].sort()
      .filter(k => json((a.sources || {})[k]) !== json((b.sources || {})[k]));
    add("sources-changed", "sources", `sources ${keys.map(k => `${k} ${((a.sources || {})[k] || {}).status || "unknown"} -> ${((b.sources || {})[k] || {}).status || "unknown"}`).join(", ") || text(b.sources)}`);
  }
  ["mine", "theirs"].forEach(s => {
    const x = a[s] || {}, y = b[s] || {};
    if (!b[s]) add("team-missing", s, `${s} roster did not arrive`);
    else if (json(x.keys) !== json(y.keys) || (x.id && y.id && x.id !== y.id)) {
      // Another device's teams have other ids (the browser test drops them), so say how far the players differ too.
      const shared = (x.keys || []).filter(k => (y.keys || []).includes(k)).length;
      add("team-substituted", s, `${s} roster${x.id ? ` ${x.id}` : ""} (${(x.keys || []).length} players) arrived as ${y.id || "a different roster"} (${(y.keys || []).length} players, ${shared} in common)`);
    } else if (x.notEvaluated !== y.notEvaluated) add("not-evaluated-changed", s, `${s} not-evaluated count ${x.notEvaluated} became ${y.notEvaluated}`);
  });
  // A package is a set of players: the order a screen lists them in is not part of it.
  const set = list => json((list || []).slice().sort());
  if (set(a.give) !== set(b.give) || set(a.get) !== set(b.get))
    add("package-changed", "package", `give ${text(a.give)} get ${text(a.get)} arrived as give ${text(b.give)} get ${text(b.get)}`);
  Object.keys(a.values || {}).forEach(k => {
    const x = a.values[k], y = (b.values || {})[k];
    if (y === undefined) { add("value-missing", `values.${k}`, `player ${k} has no value entry on arrival`); return; }
    if (x === null || y === null) { if (x !== y) add("value-changed", `values.${k}`, `player ${k} ${text(x)} became ${text(y)}`); return; }
    ["ddf", "market", "proj"].forEach(v => {
      if (x[v] === undefined) return;
      const yv = y[v] === undefined ? null : y[v];
      if (x[v] === null && yv !== null) add("value-filled", `values.${k}.${v}`, `player ${k} had no ${v} value and arrived with ${yv}`);
      else if (x[v] !== null && yv === null) add("value-lost", `values.${k}.${v}`, `player ${k} ${v} ${x[v]} arrived unavailable`);
      else if (!same(x[v], yv)) add("value-changed", `values.${k}.${v}`, `player ${k} ${v} ${x[v]} became ${yv}`);
    });
  });
  ["us", "them"].forEach(s => {
    const x = (a.gains || {})[s], y = (b.gains || {})[s];
    if (!x) return;
    if (!y) { add("gains-missing", `gains.${s}`, `${s} lineup gains did not arrive`); return; }
    Object.keys(x).forEach(v => {
      if (y[v] === undefined || (x[v] !== null && y[v] === null)) add("gains-missing", `gains.${s}.${v}`, `${s} ${v} gain ${x[v]} did not arrive`);
      else if (!same(x[v], y[v])) add("gains-changed", `gains.${s}.${v}`, `${s} ${v} gain ${x[v]} became ${y[v]}`);
    });
  });
  // The starter/bench readout by position, before and after, for both sides.
  if (a.readout) {
    if (!b.readout || b.readout.ready === false) {
      add("readout-missing", "readout", `the starters and bench readout did not arrive${b.readout && b.readout.reason ? `: ${b.readout.reason}` : ""}`);
    } else if (json(a.readout) !== json(b.readout)) {
      const where = [];
      ["us", "them"].forEach(s => ["before", "after"].forEach(when => {
        const x = ((a.readout[s] || {})[when]) || {}, y = ((b.readout[s] || {})[when]) || {};
        [...new Set(Object.keys(x.slots || {}).concat(Object.keys(y.slots || {})))].sort().forEach(slot => {
          if (json((x.slots || {})[slot]) !== json((y.slots || {})[slot])) where.push(`${s} ${when} ${slot}`);
        });
        if (json(x.bench) !== json(y.bench)) where.push(`${s} ${when} bench`);
      }));
      add("readout-changed", "readout", `starters and bench differ at ${where.join(", ") || "the readout"}`);
    }
  }
  return out;
}

// An arrival is {status: "ok", envelope} or a hold {status: "hold", reasons: [{code}], would: envelope}, where would is
// what the destination would have shown. A hold is right only when it names a reason for every lost piece of context
// and the destination really differs; anything else is a problem with its own code.
function judge(origin, arrival, tol, opts) {
  if (arrival.status === "ok") return diff(origin, arrival.envelope, tol, opts);
  const named = new Set((arrival.reasons || []).map(r => r.code));
  const would = diff(origin, arrival.would, tol, opts);
  if (!would.length) return [{code: "needless-hold", where: "hold", message: `held (${[...named].join(", ")}) though the destination shows the same trade`}];
  return [...new Set(would.map(d => d.code).filter(c => CAUSES.includes(c)))]
    .filter(cause => !HOLD_COVERS[cause].some(c => named.has(c)))
    .map(cause => ({code: "hold-incomplete", where: cause, message: `held for ${[...named].join(", ")} but not for ${cause}`}));
}

// ---------- the journey on the real modules ----------
// One line per lost piece of context; the numbers that moved because of it are counted per case, not listed.
class CaseFailure extends Error {
  constructor(cases) {
    const lines = [];
    [...new Set(cases.map(c => c.case))].forEach(where => {
      const mine = cases.filter(c => c.case === where);
      mine.filter(c => !REPRICE.includes(c.code)).forEach(c => lines.push(`${where}: [${c.code}] ${c.message}`));
      const moved = mine.filter(c => REPRICE.includes(c.code));
      if (moved.length) lines.push(`${where}: and ${moved.length} repriced (${[...new Set(moved.map(c => c.code))].join(", ")}), first: ${moved[0].message}`);
    });
    super(lines.join("\n"));
    this.cases = cases;
  }
}
const optional = (dir, file) => (fs.existsSync(path.join(dir, file)) ? require(path.join(dir, file)) : null);

function run(appDir, fixturePath) {
  const W = require(path.join(appDir, "workspace.js"));
  const F = require(path.join(appDir, "finder.js"));
  const O = require(path.join(appDir, "opportunities.js"));
  const S = require(path.join(appDir, "ddf-state.js"));
  const TC = optional(appDir, "trade-context.js");   // JEG-1259 (#1086)
  const R = optional(appDir, "trade-readout.js");    // JEG-1260 (#1088)
  const fx = JSON.parse(fs.readFileSync(fixturePath, "utf8"));
  const JSN = fx.focus.key;
  const players = [].concat(...fx.teams.map(t => t.players));
  const per = pos => fx.teams[0].players.filter(p => p.pos === pos).length;
  // Modeled league-wide seats for a shape: the dedicated starters, FLEX split RB/WR, the rest bench.
  const allocationFor = settings => SKILL.map(pos => {
    const n = settings.teams, shape = settings.roster;
    const lineup = n * (shape[pos] + (pos === "RB" || pos === "WR" ? shape.FLEX / 2 : 0));
    return {pos, rostered: n * per(pos), lineup, bench: n * per(pos) - lineup};
  });
  const weights = {overall: 0.3, QB: 0.2, RB: 0.3, WR: 0.3, TE: 0.25};
  const cache = new Map();
  const rowsFor = (state, holes) => {
    const id = stable({state, holes: holes || null});
    if (!cache.has(id)) cache.set(id, modeledRows(players, state, holes));
    return cache.get(id);
  };
  const device = (wsId, teamPrefix, myIndex) => {
    let ws = W.newWorkspace({id: wsId, name: "USO-shape journey"});
    fx.teams.forEach((t, i) => { ws = W.ops.addTeam(ws, t.name, {id: `${teamPrefix}-${String(i + 1).padStart(2, "0")}`, entries: t.players}); });
    return W.ops.setMyTeam(ws, ws.teams[myIndex].id);
  };

  const originState = {settings: {scoring: fx.settings.scoring, teams: fx.settings.teams, roster: {...shapeOf(fx.settings), BENCH: fx.settings.roster.BENCH}},
    basis: {mode: "default"}, level: "modeled", sources: sourcesOf()};
  const originWs = device("league-uso-origin", "team-o", fx.myTeamIndex);
  // Another device: its own league settings, value basis, source availability and saved league with another "my team".
  const foreignState = {settings: {scoring: "ppr", teams: 10, roster: {QB: 1, RB: 2, WR: 2, TE: 1, FLEX: 1, SUPERFLEX: 0, BENCH: 7}},
    basis: {mode: "single", source: "fantasycalc"}, level: "modeled", sources: sourcesOf({cbs: "unavailable"})};
  const foreignWs = device("league-uso-reader", "team-r", 4);
  const destinations = () => [
    {name: "same device", state: clone(originState), ws: clone(originWs)},
    {name: "another device", state: clone(foreignState), ws: clone(foreignWs)}
  ];
  const origin = {state: originState, rowsByKey: rowsFor(originState)};
  const shape = shapeOf(originState.settings);
  const teams = originWs.teams.map(t => ({id: t.id, name: t.name, entries: t.entries}));
  const mine = teams.find(t => t.id === originWs.myTeamId);
  const opps = teams.filter(t => t.id !== originWs.myTeamId);
  const teamOf = id => teams.find(x => x.id === id);
  const ctx = {rowsByKey: origin.rowsByKey, shape, expected: F.expectedDepth(allocationFor(originState.settings), originState.settings.teams), weights,
    charts: CH.slice(), market: CH.slice(), maxSize: 2, keepMine: true, keepTheirs: true};
  const facts = {values: "modeled", fixture: fx.fixture, players_as_of: fx.players_as_of, shape: fx.shape_source,
    tradeContext: TC ? "trade-context.js" : "absent", readout: R ? "trade-readout.js" : "finder.js lineup math"};

  const ran = [], failures = [], queue = [];
  const t = (name, kind, fn) => { ran.push(name); queue.push({name, kind, fn}); };
  let search = null;
  const searchOnce = async () => {
    if (!search) search = await O.runAll(mine, opps, ctx, {yieldFn: () => Promise.resolve(), budgetMs: 0});
    return search;
  };
  const gives = (r, key) => r.give.some(p => String(p.player_key) === key);
  const keysOf = list => list.map(p => String(p.player_key));
  let picks = null;
  const pickOnce = async () => {
    if (picks) return picks;
    const rows = (await searchOnce()).rows;
    const jsnRows = rows.filter(r => gives(r, JSN));
    const equal = jsnRows.find(r => !r.addedThrowIns && !r.unbalanced) || null;
    // Discovery evens the player counts with throw-ins (JEG-1108), so the unequal case is a package whose core was
    // unequal: the candidate keeps its throw-in, and the explicit deal without it is a true 2-for-1 for Compare.
    const thrownKeys = r => new Set((r.addedThrowIns || []).map(a => String(a.row.player_key)));
    const unequal = jsnRows.find(r => r.addedThrowIns && !thrownKeys(r).has(JSN)) || jsnRows.find(r => r.addedThrowIns)
      || rows.find(r => r.addedThrowIns) || null;
    let explicit = null;
    if (unequal) {
      const thrown = thrownKeys(unequal);
      explicit = {id: `${unequal.id}#explicit`, opponentId: unequal.opponentId, opponent: unequal.opponent,
        give: unequal.give.filter(p => !thrown.has(String(p.player_key))), receive: unequal.receive.filter(p => !thrown.has(String(p.player_key)))};
    }
    picks = {equal, unequal, explicit};
    return picks;
  };
  const originEnvelope = r => envelope(F, R, origin, {mine, theirs: teamOf(r.opponentId)}, keysOf(r.give), keysOf(r.receive));

  // A destination page given what a route carried: {league, basis, mine, theirs (entries or null), give, get, ids}.
  // The page's own settings stand where the link has no league, its own basis where the link has none, its own sources
  // always (a link never says what this reader loaded), its own bench level.
  const arriveWith = (dest, carried) => {
    const state = {...dest.state, settings: applyLeague(dest.state.settings, carried.league), basis: carried.basis || dest.state.basis};
    const env = {state, rowsByKey: rowsFor(state)};
    const side = (entries, id) => (entries ? {id: id || null, entries} : null);
    return {status: "ok", envelope: envelope(F, R, env, {mine: side(carried.mine, carried.mineId), theirs: side(carried.theirs, carried.theirId)},
      (carried.give || []).map(String), (carried.get || []).map(String)), env};
  };
  // A name-only entry (the codec keeps K and DEF by name) arrives unresolved: counted, never valued.
  const entryOf = p => (p.key !== undefined ? {key: String(p.key), name: p.name} : {key: `n:${p.name}`, name: p.name});
  const fullCarry = r => ({league: originState.settings, basis: originState.basis, mine: mine.entries.map(e => ({key: e.key, name: e.name})),
    theirs: teamOf(r.opponentId).entries.map(e => ({key: e.key, name: e.name})), give: keysOf(r.give), get: keysOf(r.receive),
    mineId: mine.id, theirId: r.opponentId});

  // Route 1: the site's DDF state link (view compare: the package, both rosters, the league; it carries no basis).
  const stateLinkArrival = (r, dest) => {
    const theirs = teamOf(r.opponentId);
    const query = S.encodeQuery({league: originState.settings, sources: availableCharts(originState),
      work: {view: "compare", give: keysOf(r.give).map(key => ({key})), get: keysOf(r.receive).map(key => ({key})),
        mine: mine.entries.map(e => ({key: e.key, name: e.name})), theirs: theirs.entries.map(e => ({key: e.key, name: e.name}))}});
    const {state} = S.decodeQuery(query);
    if (!state || !state.work) throw new Error(`the DDF state link decoded to no work: ${query.slice(0, 120)}`);
    const w = state.work;
    return arriveWith(dest, {league: state.league || null, basis: state.basis || null,
      mine: w.mine ? w.mine.map(entryOf) : null, theirs: w.theirs ? w.theirs.map(entryOf) : null,
      give: (w.give || []).map(p => p.key), get: (w.get || []).map(p => p.key)});
  };
  // Route 2: the pair finder's own link (both rosters' skill players, the league query); the destination reruns its own
  // search on its own values and must list the same package.
  const pairLinkArrival = (r, dest) => {
    const theirs = teamOf(r.opponentId);
    const skill = team => team.entries.filter(e => !F.isNotEvaluated(e)).map(e => ({key: e.key}));
    const link = F.encodeFinderHash({mine: skill(mine), theirs: skill(theirs), maxSize: 2, keepMine: true, keepTheirs: true},
      S.encodeQuery({league: originState.settings}));
    const got = F.decodeFinderHash(link, null);
    const league = S.decodeQuery(link.slice(link.indexOf("?") + 1)).state;
    const settings = applyLeague(dest.state.settings, league && league.league);
    const state = {...dest.state, settings};
    const rows = rowsFor(state);
    const side = list => (list || []).map(k => rows.get(String(k))).filter(Boolean);
    const mineRows = side(got.mine), theirRows = side(got.theirs);
    const res = F.findTrades(mineRows, theirRows, {chartKeys: availableCharts(state), maxSize: got.size, limit: Infinity,
      sanity: {shape: shapeOf(settings), mine: mineRows, theirs: theirRows, keepMine: got.keepMine, keepTheirs: got.keepTheirs}});
    const id = `${keysOf(r.give)}|${keysOf(r.receive)}`;
    const found = res.trades.find(x => `${keysOf(x.give)}|${keysOf(x.receive)}` === id) || null;
    const arrival = arriveWith(dest, {league: league && league.league, basis: null,
      mine: got.mine.length ? got.mine.map(k => ({key: String(k)})) : null, theirs: got.theirs.length ? got.theirs.map(k => ({key: String(k)})) : null,
      give: found ? keysOf(found.give) : [], get: found ? keysOf(found.receive) : []});
    arrival.extra = found ? [] : [{code: "package-not-rediscovered", where: "package",
      message: `the pair finder's own search (${res.total} trades) does not list ${id}`}];
    return arrival;
  };
  // Route 3: the JEG-1259 transfer (trade-context.js), when app/v2 has it. The destination resolves its common
  // preferences with the carried ones as a complete link layer, reruns its own bench level and calls receive().
  const commonOf = state => TC.normalizeCommon({league: state.settings, basis: state.basis, overrides: {},
    sources: Object.fromEntries(Object.entries(state.sources).map(([k, s]) => [k, {available: s.status === "available", held: s.status === "held",
      reason: s.reason, version: s.version}]))});
  const pricingFor = (state, rows, keys) => ({mode: "modeled", levels: {modeled: TC.levelIdentity("modeled",
    {rows: [...rows.values()], allocation: allocationFor(state.settings), weights, keys})}});
  const transferArrival = (r, dest, route) => {
    if (!TC) return {status: "missing"};
    const deal = {give: keysOf(r.give), get: keysOf(r.receive)};
    const keys = TC.pricingKeys({mine: mine.entries, theirs: teamOf(r.opponentId).entries, deal});
    const sent = TC.fromLeague({common: commonOf(originState), pricing: pricingFor(originState, origin.rowsByKey, keys), deal}, originWs);
    const decoded = TC.decodeTransfer(TC.encodeTransfer(TC.toTransfer(sent)));
    if (!decoded) throw new Error("the trade context transfer did not decode");
    const link = TC.normalizeCommon({league: decoded.settings, basis: (decoded.valuation || {}).basis, overrides: (decoded.valuation || {}).overrides});
    const resolved = TC.resolveCommon({link: {common: link, complete: true}, local: commonOf(dest.state)});
    const l = resolved.common.league;
    const state = {settings: {scoring: l.scoring, teams: l.teams, roster: {...l.roster}}, basis: resolved.common.valuation.basis,
      level: dest.state.level, sources: resolved.common.sources};
    const rows = rowsFor(state);
    const res = TC.receive(decoded, {route, common: resolved.common, pricing: pricingFor(state, rows, keys), ws: dest.ws});
    const env = {state, rowsByKey: rows};
    const team = t => (t ? {id: t.id || null, entries: t.roster.map(e => ({...e}))} : null);
    if (res.status === "ok") {
      return {status: "ok", envelope: envelope(F, R, env, {mine: team(res.context.teams.mine), theirs: team(TC.dealPartner(res.context))},
        res.context.deal.give, res.context.deal.get)};
    }
    return {status: "hold", reasons: res.reasons, would: envelope(F, R, env, {mine: team(decoded.mine), theirs: team(decoded.theirs)},
      (decoded.deal || {}).give || [], (decoded.deal || {}).get || [])};
  };

  // Carries each pick to both destinations; every problem is one case with one code.
  const carry = async (arrive, opts) => {
    const {equal, unequal, explicit} = await pickOnce();
    const list = [["equal", equal], ["throw-in", unequal]].concat(opts.unequal === false ? [] : [["unequal", explicit]]);
    const cases = [];
    list.forEach(([label, r]) => destinations().forEach(dest => {
      const where = `${label} ${r.id} on ${dest.name}`;
      const arrival = arrive(r, dest);
      if (arrival.status === "missing") { cases.push({case: where, code: "context-missing", message: "this build has no trade context to carry (trade-context.js)"}); return; }
      judge(originEnvelope(r), arrival, undefined, opts).concat(arrival.extra || [])
        .forEach(d => cases.push({case: where, code: d.code, message: d.message}));
    }));
    if (cases.length) throw new CaseFailure(cases);
  };

  // ---------- harness checks: green on every build ----------
  t("test_fixture_is_uso_shape_and_synthetic", "harness", () => {
    assert.strictEqual(fx.teams.length, 12, "12 teams");
    fx.teams.forEach(team => assert.strictEqual(team.players.length, 15, `${team.name}: 15 players (8 starters, K, DEF, 5 bench)`));
    assert.deepStrictEqual(originState.settings.roster, {QB: 1, RB: 2, WR: 3, TE: 1, FLEX: 1, SUPERFLEX: 0, BENCH: 5});
    assert.strictEqual(originState.settings.scoring, "half_ppr");
    assert.ok(mine.entries.some(e => e.key === JSN), "JSN is on the user's team");
    assert.ok(fx.teams.every(team => /^(My team|Team \d\d)$/.test(team.name)), "anonymized team names only");
    assert.ok(/synthetic/i.test(fx.note) && /not uso's rosters/i.test(fx.note), "the fixture says it is synthetic");
    assert.ok(/shape only/.test(fx.shape_source), "only the shape is attributed to USO");
    assert.ok(players.every(p => !("note" in p) && !("owner" in p)), "no roster note or owner on any player");
    const skill = players.filter(p => !String(p.key).startsWith("x:"));
    assert.strictEqual(skill.filter(p => !origin.rowsByKey.has(String(p.key))).length, 0, "every skill player has a row");
    assert.strictEqual(new Set(skill.map(p => p.key)).size, skill.length, "no player on two rosters");
  });

  t("test_both_sides_starters_and_bench_by_position", "harness", () => {
    const market = rows => F.withChartAverage(rows, CH);
    [mine].concat(opps).forEach(team => {
      const rows = team.entries.map(e => origin.rowsByKey.get(String(e.key))).filter(Boolean);
      [[OUR_KEY, rows], [MARKET_KEY, market(rows)]].forEach(([key, list]) => {
        const lv = F.lineupValue(list, shape, key);
        assert.strictEqual(lv.starters.length, 8, `${team.name} ${key}: 8 starters`);
        assert.strictEqual(lv.bench.length, 5, `${team.name} ${key}: 5 bench`);
        assert.deepStrictEqual(lv.empty, {}, `${team.name} ${key}: no empty slot`);
        assert.ok(lv.counts.QB === 1 && lv.counts.TE >= 1 && lv.counts.RB >= 2 && lv.counts.WR >= 3, `${team.name} ${key}: starters by position ${JSON.stringify(lv.counts)}`);
        assert.strictEqual(lv.counts.RB + lv.counts.WR + lv.counts.TE, 7, `${team.name} ${key}: one FLEX`);
        assert.ok(lv.starterValue > 0 && lv.benchValue > 0, `${team.name} ${key}: nonzero values`);
      });
      assert.strictEqual(team.entries.filter(e => F.isNotEvaluated(e)).length, 2, `${team.name}: K and DEF not evaluated`);
    });
  });

  t("test_jsn_discoverable_in_the_uncapped_search", "harness", async () => {
    const result = await searchOnce();
    assert.ok(result.rows.length > 0, "the league search found candidates");
    assert.strictEqual(result.perOpponent.length, 11, "every opponent searched");
    result.perOpponent.forEach(p => {
      const theirs = teamOf(p.id).entries.map(e => origin.rowsByKey.get(String(e.key))).filter(Boolean);
      const mineRows = mine.entries.map(e => origin.rowsByKey.get(String(e.key))).filter(Boolean);
      const direct = F.findTrades(mineRows, theirs, {chartKeys: CH, maxSize: 2, limit: Infinity,
        sanity: {shape, mine: mineRows, theirs, keepMine: true, keepTheirs: true}});
      assert.strictEqual(p.count, direct.total, `vs ${p.name}: every qualified candidate kept (${p.count} of ${direct.total}), none truncated`);
    });
    const jsn = result.rows.filter(r => gives(r, JSN));
    facts.candidates = result.rows.length;
    facts.jsnCandidates = jsn.length;
    facts.jsnOpponents = [...new Set(jsn.map(r => r.opponent))].length;
    assert.ok(jsn.length > 0, `JSN is not discoverable: 0 of ${result.rows.length} candidates send him`);
  });

  t("test_selected_candidates_are_exact", "harness", async () => {
    const {equal, unequal, explicit} = await pickOnce();
    assert.ok(equal, "a trade sending JSN with no throw-in exists");
    assert.ok(unequal, "a candidate whose core was unequal (a throw-in evens it) exists");
    assert.ok(explicit && explicit.give.length !== explicit.receive.length && explicit.give.length + explicit.receive.length >= 3,
      `the explicit deal without the throw-in is unequal: ${explicit && explicit.give.length}-for-${explicit && explicit.receive.length}`);
    [equal, unequal].forEach(r => {
      const [opp, give, get] = r.id.split("|");
      assert.strictEqual(opp, r.opponentId);
      assert.deepStrictEqual(give.split(","), keysOf(r.give), "row id names the exact give keys");
      assert.deepStrictEqual(get.split(","), keysOf(r.receive), "row id names the exact get keys");
      const own = new Set(mine.entries.map(e => e.key)), their = new Set(teamOf(r.opponentId).entries.map(e => e.key));
      assert.ok(keysOf(r.give).every(k => own.has(k)) && keysOf(r.receive).every(k => their.has(k)), "package comes off the two rosters");
    });
    facts.equal = {id: equal.id, opponent: equal.opponent};
    facts.unequal = {id: unequal.id, opponent: unequal.opponent, throwIns: unequal.addedThrowIns.map(a => `${a.side}:${a.row.player_key}`),
      explicit: [explicit.give.length, explicit.receive.length]};
  });

  t("test_league_row_gains_and_readout_match_the_lineup_math", "harness", async () => {
    const {equal, unequal, explicit} = await pickOnce();
    [equal, unequal].forEach(r => {
      const e = originEnvelope(r);
      assert.ok(Math.abs(e.gains.us.ddf - r.fit.us.starterDelta) < 1e-9, `${r.id}: league row's starter gain ${r.fit.us.starterDelta} equals the lineup math ${e.gains.us.ddf}`);
      const sum = (keys, v) => keys.reduce((s, k) => s + e.values[k][v], 0);
      assert.ok(Math.abs(sum(e.get, "ddf") - sum(e.give, "ddf") - r.edge) < 1e-9, `${r.id}: DDF capture is get minus give`);
      assert.ok(Math.abs(sum(e.give, "market") - sum(e.get, "market") - r.chartEdge) < 1e-9, `${r.id}: market edge is give minus get`);
      assert.ok(Math.abs(sum(e.get, "proj") - sum(e.give, "proj") - r.projEdge) < 1e-9, `${r.id}: projections edge is get minus give`);
    });
    [equal, unequal, explicit].forEach(r => {
      const teamsOf = {mine, theirs: teamOf(r.opponentId)};
      const readout = readoutOf(F, R, origin, teamsOf, keysOf(r.give), keysOf(r.receive));
      const direct = readoutOf(F, null, origin, teamsOf, keysOf(r.give), keysOf(r.receive));
      assert.ok(readout && readout.ready, `${r.id}: the readout is ready`);
      ["us", "them"].forEach(s => ["before", "after"].forEach(when => {
        const l = readout[s][when];
        const starters = Object.values(l.slots).reduce((n, keys) => n + keys.length, 0);
        assert.strictEqual(starters, 8, `${r.id} ${s} ${when}: 8 starters by position`);
        assert.ok(l.bench.length > 0, `${r.id} ${s} ${when}: a bench`);
      }));
      assert.strictEqual(stable(readout), stable(direct), `${r.id}: the readout (${facts.readout}) equals finder.js rosterImpact`);
    });
  });

  t("test_destination_state_is_independent", "harness", async () => {
    const {equal} = await pickOnce();
    const [same, other] = destinations();
    same.state.settings.scoring = "mutated";
    same.ws.teams[0].entries = [];
    assert.strictEqual(originState.settings.scoring, fx.settings.scoring, "the same-device destination is a copy, not the origin's object");
    assert.ok(originWs.teams[0].entries.length > 0, "the same-device workspace is a copy");
    ["settings", "basis", "sources"].forEach(k => assert.notStrictEqual(stable(other.state[k]), stable(originState[k]), `another device has its own ${k}`));
    assert.notStrictEqual(other.ws.id, originWs.id, "another device has its own saved league");
    assert.notStrictEqual(other.ws.myTeamId.slice(-2), originWs.myTeamId.slice(-2), "another device names another my team");
    // Each piece of context moves a number in the package, so a page that drops it cannot look the same.
    const keys = keysOf(equal.give).concat(keysOf(equal.receive));
    const values = state => { const rows = rowsFor(state); return keys.map(k => rows.get(k).values); };
    const base = stable(values(originState));
    [["settings", {settings: foreignState.settings}], ["basis", {basis: foreignState.basis}], ["level", {level: "league"}],
      ["sources", {sources: foreignState.sources}]].forEach(([what, patch]) => {
      assert.notStrictEqual(stable(values({...originState, ...patch})), base, `changing the ${what} moves a value in ${equal.id}`);
    });
  });

  t("test_dropped_context_fails_specifically", "harness", async () => {
    const {equal, explicit} = await pickOnce();
    const other = opps.find(o => o.id !== equal.opponentId && o.id !== explicit.opponentId);
    const cases = [
      ["scoring changed", "settings-changed", (d, c) => { d.state.settings.scoring = "ppr"; c.league = null; }],
      ["basis changed", "basis-changed", (d, c) => { d.state.basis = {mode: "single", source: "fantasycalc"}; c.basis = null; }],
      ["cbs held", "sources-changed", d => { d.state.sources.cbs = {status: "held", reason: "data check", version: DATA_VERSION}; }],
      ["level changed", "level-changed", d => { d.state.level = "league"; }],
      ["other team substituted", "team-substituted", (d, c) => { c.theirs = other.entries.map(e => ({key: e.key, name: e.name})); c.theirId = other.id; }],
      ["their roster missing", "team-missing", (d, c) => { c.theirs = null; }],
      ["get emptied", "package-changed", (d, c) => { c.get = []; }]
    ];
    const problems = [];
    [["equal", equal], ["unequal", explicit]].forEach(([label, r]) => {
      const before = originEnvelope(r);
      const baseline = diff(before, arriveWith(destinations()[0], fullCarry(r)).envelope);
      if (baseline.length) problems.push(`${label}: the full carry is not clean: ${baseline.map(d => d.code).join(", ")}`);
      cases.forEach(([name, code, mutate]) => {
        const dest = destinations()[0], carried = fullCarry(r);
        mutate(dest, carried);
        const codes = [...new Set(diff(before, arriveWith(dest, carried).envelope).map(d => d.code))];
        const stray = codes.filter(c => c !== code && !REPRICE.includes(c));
        if (!codes.includes(code) || stray.length) problems.push(`${label} ${name}: wanted [${code}], got [${codes.join(", ")}]`);
      });
      // A hold is judged by what it names: every lost piece of context, and only when something was lost.
      const would = arriveWith(destinations()[1], {...fullCarry(r), league: null, basis: null}).envelope;
      const lost = [...new Set(diff(before, would).map(d => d.code))].filter(c => CAUSES.includes(c));
      const reasonsFor = list => list.map(c => ({code: HOLD_COVERS[c][0]}));
      const verdicts = [
        ["hold naming every cause", judge(before, {status: "hold", reasons: reasonsFor(lost), would}), []],
        ["hold missing the basis", judge(before, {status: "hold", reasons: reasonsFor(lost.filter(c => c !== "basis-changed")), would}), ["hold-incomplete"]],
        ["hold with nothing lost", judge(before, {status: "hold", reasons: [{code: "settings-changed"}], would: before}), ["needless-hold"]],
        ["silent arrival on another device", judge(before, {status: "ok", envelope: would}), null]
      ];
      if (!lost.includes("basis-changed") || !lost.includes("settings-changed") || !lost.includes("sources-changed"))
        problems.push(`${label}: another device without the context should lose settings, basis and sources, lost [${lost.join(", ")}]`);
      verdicts.forEach(([name, got, want]) => {
        const codes = [...new Set(got.map(d => d.code))];
        if (want === null ? !codes.length : stable(codes) !== stable(want)) problems.push(`${label} ${name}: got [${codes.join(", ")}]`);
      });
    });
    assert.deepStrictEqual(problems, [], problems.join("\n"));
  });

  t("test_unavailable_stays_unavailable", "harness", async () => {
    const {equal} = await pickOnce();
    const hole = keysOf(equal.receive)[0];
    const holed = {state: originState, rowsByKey: rowsFor(originState, {[hole]: ["fantasypros"]})};
    const e = envelope(F, R, holed, {mine, theirs: teamOf(equal.opponentId)}, keysOf(equal.give), keysOf(equal.receive));
    assert.strictEqual(e.values[hole].market, null, "a player one chart does not price has no Trade chart average");
    assert.ok(e.values[hole].ddf !== null, "but keeps his DDF Value");
    const zero = clone(e);
    zero.values[hole].market = 0;
    assert.deepStrictEqual(diff(e, zero).map(d => d.code), ["value-filled"], "0 in place of unavailable is caught");
    assert.deepStrictEqual(diff(e, clone(e)), [], "unavailable on both sides is the same context");
  });

  t("test_diff_names_each_loss", "harness", async () => {
    const {explicit} = await pickOnce();
    const theirs = teamOf(explicit.opponentId);
    const base = originEnvelope(explicit);
    const other = opps.find(o => o.id !== theirs.id);
    const cases = [
      ["basis-changed", e => { e.basis = null; }],
      ["level-changed", e => { e.level = "league"; }],
      ["settings-changed", e => { e.settings = {...e.settings, scoring: "ppr"}; }],
      ["sources-changed", e => { e.sources.cbs.status = "held"; }],
      ["team-substituted", e => { e.theirs = {id: other.id, keys: other.entries.filter(x => !F.isNotEvaluated(x)).map(x => x.key).sort(), notEvaluated: 2}; }],
      ["team-missing", e => { e.theirs = null; }],
      ["package-changed", e => { const long = e.give.length > e.get.length ? "give" : "get"; e[long] = e[long].slice(1); }],
      ["value-changed", e => { const k = e.get[0]; e.values[k].ddf += 1; }],
      ["value-lost", e => { const k = e.give[0]; e.values[k].proj = null; }],
      ["gains-missing", e => { delete e.gains.them; }],
      ["gains-changed", e => { e.gains.us.ddf += 0.5; }],
      ["readout-changed", e => { const b = e.readout.us.after.bench; e.readout.us.after.bench = b.slice(1); }],
      ["readout-missing", e => { e.readout = null; }]
    ];
    assert.deepStrictEqual(diff(base, clone(base)), []);
    cases.forEach(([code, mutate]) => {
      const e = clone(base);
      mutate(e);
      const codes = [...new Set(diff(base, e).map(d => d.code))];
      assert.deepStrictEqual(codes, [code], `${code}: diff reported ${JSON.stringify(codes)}`);
    });
  });

  // ---------- continuity checks: red until the site carries the trade or holds it ----------
  t("test_state_link_carries_the_trade", "continuity", () => carry(stateLinkArrival, {}));
  // The pair finder carries skill players only (K and DEF are never searched), so their count is not part of its link.
  t("test_pair_link_carries_the_trade", "continuity", () => carry(pairLinkArrival, {unequal: false, ignore: ["not-evaluated-changed"]}));
  t("test_trade_context_transfer_carries_or_holds_the_trade", "continuity", () => carry((r, dest) => transferArrival(r, dest, "compare"), {}));

  return (async () => {
    for (const {name, kind, fn} of queue) {
      try { await fn(); } catch (error) {
        failures.push({name, kind, message: String((error && error.message) || error),
          cases: error instanceof CaseFailure ? error.cases.map(c => ({case: c.case, code: c.code})) : []});
      }
    }
    return {ran, failures, facts};
  })();
}

if (require.main === module) {
  const [mode, a, b, tol] = process.argv.slice(2);
  if (mode === "diff") {
    const read = p => JSON.parse(fs.readFileSync(p, "utf8"));
    process.stdout.write(JSON.stringify({differences: diff(read(a), read(b), tol === undefined ? 0.051 : Number(tol))}) + "\n");
  } else if (mode === "check") {
    run(path.resolve(a), path.resolve(b)).then(out => process.stdout.write(JSON.stringify(out) + "\n"),
      error => { process.stdout.write(JSON.stringify({ran: [], failures: [{name: "harness", kind: "harness", message: String((error && error.stack) || error), cases: []}]}) + "\n"); });
  } else {
    process.stderr.write("usage: uso_site_journey_contract.cjs check <app dir> <league.json> | diff <origin.json> <destination.json> [tolerance]\n");
    process.exit(2);
  }
}
module.exports = {envelope, diff, judge, modeledRows, run, CAUSES, REPRICE, HOLD_COVERS};
