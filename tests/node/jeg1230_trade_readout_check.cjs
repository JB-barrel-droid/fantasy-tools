// JEG-1230: the shared explicit-trade readout returns exactly what each trade page computes today, for the same deal.
// The route functions below copy the current call paths (v2.js compareConstructionInput, league.js sidePanel,
// finder.js lineupContext/impactBlock) so a drift in either the adapter or a route shows up here.
// Usage: node tests/node/jeg1230_trade_readout_check.cjs [--write-golden]
"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const ROOT = path.resolve(__dirname, "..", "..");
const F = require(path.join(ROOT, "app/v2/finder.js"));
const R = require(path.join(ROOT, "app/v2/trade-readout.js"));
const GOLDEN = path.join(ROOT, "tests/fixtures/jeg1230_trade_readout_golden.json");

// ---------- fixtures ----------
// One base value per player; each scoring scales positions the way PPR tilts value (receivers up). Engine rows only:
// rosterImpact never reads scoring, so the three scorings are three row sets on the same rosters.
const SCORING = {standard: {QB: 1, RB: 1.1, WR: 0.9, TE: 0.85}, half: {QB: 1, RB: 1, WR: 1, TE: 0.95}, ppr: {QB: 1, RB: 0.95, WR: 1.12, TE: 1.05}};
const CHARTS = F.CHART_KEYS;
const SPREAD = {usatoday: 1.04, fantasycalc: 0.97, fantasypros: 1.01, cbs: 0.98};
const r1 = n => Math.round(n * 10) / 10;
function player(key, pos, base, scoring, opts = {}) {
  const k = base === null ? null : r1(base * SCORING[scoring][pos]);
  const values = {ddf_value: opts.ddf !== undefined ? opts.ddf : k};
  CHARTS.forEach(c => { values[c] = k === null || (opts.noChart || []).includes(c) ? null : r1(k * SPREAD[c]); });
  values.ddf_value_projections = opts.noProjections || k === null ? null : r1(k * 0.93);
  F.PROJECTION_KEYS.forEach(p => { values[p] = values.ddf_value_projections; });
  return {player_key: key, name: key, pos, values, ...(opts.lowConfidence ? {ddfLowConfidence: true, ddfCount: 1} : {})};
}
const SHAPE_1QB = {QB: 1, RB: 2, WR: 2, TE: 1, FLEX: 1, SUPERFLEX: 0};
const SHAPE_SF = {QB: 1, RB: 2, WR: 3, TE: 1, FLEX: 1, SUPERFLEX: 1};
const MINE = [["mQB", "QB", 22], ["mQB2", "QB", 9], ["mRB1", "RB", 19], ["mRB2", "RB", 14], ["mRB3", "RB", 7], ["mWR1", "WR", 20],
  ["mWR2", "WR", 15], ["mWR3", "WR", 8], ["mWR4", "WR", 5], ["mTE", "TE", 11]];
const THEIRS = [["tQB", "QB", 18], ["tQB2", "QB", 12], ["tRB1", "RB", 24], ["tRB2", "RB", 10], ["tWR1", "WR", 17], ["tWR2", "WR", 13],
  ["tWR3", "WR", 9], ["tTE1", "TE", 14], ["tTE2", "TE", 6]];
const roster = (list, scoring, opts = {}) => list.map(([k, pos, v]) => player(k, pos, v, scoring, opts[k] || {}));

// Explicit deals. Each keeps one engine context across every route.
const SCENARIOS = [
  {id: "one_for_one", shape: SHAPE_1QB, give: ["mRB2"], receive: ["tWR1"]},
  {id: "two_for_one", shape: SHAPE_1QB, give: ["mRB1", "mWR1"], receive: ["tRB1"]},
  {id: "superflex_two_for_two", shape: SHAPE_SF, give: ["mQB2", "mWR2"], receive: ["tQB2", "tTE1"]},
  {id: "empty_te_slot", shape: SHAPE_1QB, give: ["mTE"], receive: ["tRB2"]},
  // Zero counts as a value; null is missing (never read as 0). Low-confidence DDF rows keep their flag.
  {id: "zero_vs_missing", shape: SHAPE_1QB, give: ["mWR3"], receive: ["tWR3"],
    mine: {mWR4: {ddf: 0}, mRB3: {ddf: null}}, theirs: {tWR3: {lowConfidence: true}}},
  // A team with no projection values anywhere: that side has no projections readout (null), the other side keeps its own.
  {id: "one_side_no_projections", shape: SHAPE_1QB, give: ["mRB2"], receive: ["tWR2"], mine: {mRB2: {noProjections: true}},
    theirs: Object.fromEntries(THEIRS.map(([k]) => [k, {noProjections: true}]))}
];

function context(sc, scoring) {
  const mine = roster(MINE, scoring, sc.mine);
  const theirs = roster(THEIRS, scoring, sc.theirs);
  return {shape: sc.shape, mine, theirs, give: sc.give, receive: sc.receive, charts: CHARTS.slice()};
}

// ---------- the three routes' current call paths ----------
const lineup = l => ({starterValue: l.starterValue, benchValue: l.benchValue, total: l.total, counts: {...l.counts}, size: l.size,
  slots: Object.fromEntries(Object.entries(l.slots).map(([slot, rows]) => [slot, rows.map(r => String(r.player_key))])),
  bench: l.bench.map(r => String(r.player_key)), unvalued: l.unvalued.map(r => String(r.player_key)), empty: {...l.empty}});
const imp = i => (i ? {starterDelta: i.starterDelta, benchDelta: i.benchDelta, totalDelta: i.totalDelta, spotsOpened: i.spotsOpened,
  needLine: F.needLine(i), before: lineup(i.before), after: lineup(i.after)} : null);

// v2.js compareConstructionInput: DDF Value only, rows by key from the engine.
function compareRoute(cx) {
  const rowsByKey = new Map(cx.mine.concat(cx.theirs).map(r => [String(r.player_key), r]));
  const rosterRows = team => team.map(r => rowsByKey.get(String(r.player_key))).filter(Boolean);
  const giveRows = cx.give.map(k => rowsByKey.get(k));
  const receiveRows = cx.receive.map(k => rowsByKey.get(k));
  return {mine: {ddf: imp(F.rosterImpact(rosterRows(cx.mine), giveRows, receiveRows, cx.shape, "ddf_value"))},
    theirs: {ddf: imp(F.rosterImpact(rosterRows(cx.theirs), receiveRows, giveRows, cx.shape, "ddf_value"))}};
}
// league.js sidePanel: DDF Value and, with enough charts, the Trade chart average via withChartAverage on every list.
function leagueRoute(cx) {
  const market = cx.charts.length >= F.MIN_CHARTS ? cx.charts : null;
  const withAvg = list => (market ? F.withChartAverage(list, market) : list);
  const byKey = new Map(cx.mine.concat(cx.theirs).map(r => [String(r.player_key), r]));
  const leavingMine = cx.give.map(k => byKey.get(k));
  const arrivingMine = cx.receive.map(k => byKey.get(k));
  const side = (team, leaving, arriving) => {
    const out = {};
    [["ddf", F.OUR_KEY, rows => rows]].concat(market ? [["market", F.MARKET_KEY, withAvg]] : []).forEach(([view, key, convert]) => {
      out[view] = imp(F.rosterImpact(convert(team), convert(leaving), convert(arriving), cx.shape, key));
    });
    return out;
  };
  return {mine: side(cx.mine, leavingMine, arrivingMine), theirs: side(cx.theirs, arrivingMine, leavingMine)};
}
// finder.js lineupContext + impactBlock: DDF Value, market via byKey, and projections when the side has any.
function finderRoute(cx) {
  const market = cx.charts.length >= F.MIN_CHARTS ? cx.charts : null;
  const avg = rows => (market ? F.withChartAverage(rows, market) : null);
  const mineAvg = avg(cx.mine);
  const theirAvg = avg(cx.theirs);
  const byKey = new Map();
  (mineAvg || []).concat(theirAvg || []).forEach(r => byKey.set(String(r.player_key), r));
  const lc = {shape: cx.shape, market, mine: {ddf: cx.mine, market: mineAvg}, theirs: {ddf: cx.theirs, market: theirAvg}, byKey};
  const all = new Map(cx.mine.concat(cx.theirs).map(r => [String(r.player_key), r]));
  const giveRows = cx.give.map(k => all.get(k));
  const recvRows = cx.receive.map(k => all.get(k));
  const sideRows = (view, who) => {
    const pickRows = rows => (view === "ddf" ? rows : rows.map(r => lc.byKey.get(String(r.player_key)) || r));
    return {roster: lc[who][view], leaving: pickRows(who === "mine" ? giveRows : recvRows), arriving: pickRows(who === "mine" ? recvRows : giveRows)};
  };
  const out = {};
  ["mine", "theirs"].forEach(who => {
    out[who] = {};
    ["ddf"].concat(market ? ["market"] : []).forEach(view => {
      const s = sideRows(view, who);
      out[who][view] = imp(F.rosterImpact(s.roster, s.leaving, s.arriving, cx.shape, view === "ddf" ? F.OUR_KEY : F.MARKET_KEY));
    });
    const own = sideRows("ddf", who);
    out[who].projections = imp(F.hasProjections(own.roster.concat(own.arriving))
      ? F.rosterImpact(own.roster, own.leaving, own.arriving, cx.shape, F.PROJECTIONS_KEY) : null);
  });
  return out;
}

const adapterInput = cx => ({shape: cx.shape, ourKey: F.OUR_KEY, chartKeys: cx.charts, mine: {rows: cx.mine}, theirs: {rows: cx.theirs},
  give: cx.give, receive: cx.receive});
const pick = s => (s ? {starterDelta: s.starterDelta, benchDelta: s.benchDelta, totalDelta: s.totalDelta, spotsOpened: s.spotsOpened,
  needLine: s.needLine, before: s.before, after: s.after} : null);

function deepFreeze(o) {
  if (o && typeof o === "object" && !Object.isFrozen(o)) { Object.freeze(o); Object.values(o).forEach(deepFreeze); }
  return o;
}

// ---------- parity and golden ----------
const golden = {};
let checks = 0;
for (const sc of SCENARIOS) {
  for (const scoring of Object.keys(SCORING)) {
    const cx = context(sc, scoring);
    const routes = {compare: compareRoute(cx), league: leagueRoute(cx), finder: finderRoute(cx)};
    golden[`${sc.id}/${scoring}`] = routes.finder;
    const before = JSON.stringify(cx);
    deepFreeze(cx);
    const readout = R.summary(R.build(adapterInput(cx)));
    assert.equal(JSON.stringify(cx), before, `${sc.id}/${scoring}: inputs changed`);
    assert.equal(readout.ready, true, `${sc.id}/${scoring}: ${readout.reason}`);
    for (const [name, route] of Object.entries(routes)) {
      for (const who of ["mine", "theirs"]) {
        for (const [view, expected] of Object.entries(route[who])) {
          assert.deepEqual(pick(readout[who][view]), expected, `${sc.id}/${scoring}: ${name} ${who} ${view}`);
          checks++;
        }
      }
    }
  }
}
if (process.argv.includes("--write-golden")) {
  const lines = Object.entries(golden).map(([id, c]) => ` ${JSON.stringify(id)}: ${JSON.stringify(c)}`);
  fs.writeFileSync(GOLDEN, `{"ticket": "JEG-1230", "source": "finder.js rosterImpact on current main", "cases": {\n${lines.join(",\n")}\n}}\n`);
} else {
  const stored = JSON.parse(fs.readFileSync(GOLDEN, "utf8")).cases;
  assert.deepEqual(Object.keys(stored).sort(), Object.keys(golden).sort());
  for (const [id, expected] of Object.entries(stored)) { assert.deepEqual(golden[id], expected, `golden drift: ${id}`); checks++; }
}

// ---------- named cases ----------
const base = context(SCENARIOS[0], "half");
const build = over => R.build({...adapterInput(base), ...over});

// Zero is a value, null is missing; K/DEF are not evaluated, not missing.
{
  const cx = context(SCENARIOS[4], "ppr");
  cx.mine.push({player_key: "mK", name: "mK", pos: "K", values: {}});
  const out = R.build({...adapterInput(cx), mine: {rows: cx.mine, entries: [{key: "mDEF", name: "mDEF", pos: "DEF"}, {key: "ghost", name: "Ghost", pos: "WR"}]}});
  const ddf = out.sides.mine.ddf;
  assert.ok(ddf.impact.before.bench.some(r => r.player_key === "mWR4"), "a zero DDF Value is a valued bench player");
  assert.deepEqual(ddf.rosterUnpriced, ["mRB3"], "null DDF Value is missing");
  assert.deepEqual(ddf.notEvaluated.sort(), ["mDEF", "mK"]);
  assert.deepEqual(ddf.unresolved, ["ghost"]);
  assert.equal(ddf.complete, false);
  assert.deepEqual(out.sides.theirs.ddf.lowConfidence, ["tWR3"]);
  checks += 6;
}
// The team with no projection values at all has no projections readout; the other team keeps its own.
{
  const out = R.build(adapterInput(context(SCENARIOS[5], "half")));
  assert.equal(out.sides.theirs.projections, null);
  assert.notEqual(out.sides.mine.projections, null);
  checks += 2;
}
// Empty starting slot after the trade is reported, not filled.
{
  const out = R.build(adapterInput(context(SCENARIOS[3], "standard")));
  assert.deepEqual(out.sides.mine.ddf.newlyEmpty, {TE: 1});
  assert.match(out.sides.mine.ddf.needLine, /TE slot left empty/);
  checks += 2;
}
// Too few charts: the market view is unavailable with a reason, its sides are null (never zeros).
{
  const out = build({chartKeys: ["usatoday", "cbs"]});
  assert.equal(out.views.market.status, "unavailable");
  assert.equal(out.views.market.reason, "Only 2 trade charts are available this week.");
  assert.equal(out.sides.mine.market, null);
  assert.equal(out.sides.theirs.market, null);
  assert.equal(build({chartKeys: []}).views.market.reason, "No trade chart is available this week.");
  checks += 5;
}
// Projections absent: unavailable, no readout, and held sources named.
{
  const strip = rows => rows.map(r => ({...r, values: {...r.values, ddf_value_projections: null}}));
  const held = F.PROJECTION_KEYS.map(key => ({key, available: false, excludedReason: "held: fidelity check"}));
  const out = build({mine: {rows: strip(base.mine)}, theirs: {rows: strip(base.theirs)}, sourceInfo: held});
  assert.equal(out.views.projections.status, "unavailable");
  assert.deepEqual(out.views.projections.held, F.PROJECTION_KEYS);
  assert.equal(out.views.projections.reason, "Projection sources are held this week (data check).");
  assert.equal(out.sides.mine.projections, null);
  const notHeld = build({mine: {rows: strip(base.mine)}, theirs: {rows: strip(base.theirs)}});
  assert.equal(notHeld.views.projections.reason, "No projection values for these rosters.");
  assert.deepEqual(R.sourceStatus([{key: "cbs", available: false, paused: true}], ["cbs"])[0].reason, "waiting on fresh inputs");
  checks += 6;
}
// Unresolved deal keys: not ready, no numbers.
{
  const out = build({give: ["nobody"]});
  assert.equal(out.ready, false);
  assert.deepEqual(out.outside, {give: ["nobody"], receive: []});
  assert.equal(out.reason, "This trade includes players outside the selected rosters.");
  assert.deepEqual(out.sides, {mine: {}, theirs: {}});
  assert.equal(build({receive: []}).reason, "Add a player to both sides to see how each roster changes.");
  assert.equal(build({shape: null}).ready, false);
  checks += 6;
}
// The ourKey basis is honoured (a reader's own basis reads a different series) without touching the other views.
{
  const out = build({ourKey: "fantasycalc"});
  assert.equal(out.sides.mine.ddf.valueKey, "fantasycalc");
  assert.deepEqual(imp(out.sides.mine.ddf.impact),
    imp(F.rosterImpact(base.mine, base.mine.filter(r => r.player_key === "mRB2"), base.theirs.filter(r => r.player_key === "tWR1"), base.shape, "fantasycalc")));
  checks += 2;
}
console.log(`JEG-1230 readout: ${checks} checks passed`);
