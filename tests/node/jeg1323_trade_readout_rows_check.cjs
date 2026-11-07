// JEG-1323: the readout's second half (verdict, will they accept, sell gap, data labels, context line) on one golden
// trade with a held source, a kicker, an unpriced player and a single-source player. Each row's value or stated reason
// is pinned in tests/fixtures/jeg1323_trade_readout_rows_golden.json, and the verdict and acceptance are checked against
// the league finder's own calls (league.js: tradeFit and viabilityLabel on chart-average rows) on the same deal.
// Usage: node tests/node/jeg1323_trade_readout_rows_check.cjs [--write-golden]
"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const ROOT = path.resolve(__dirname, "..", "..");
const F = require(path.join(ROOT, "app/v2/finder.js"));
const TS = require(path.join(ROOT, "app/v2/team-summary.js"));
const R = require(path.join(ROOT, "app/v2/trade-readout.js"));
const GOLDEN = path.join(ROOT, "tests/fixtures/jeg1323_trade_readout_rows_golden.json");

// ---------- the golden trade ----------
// 12 teams, Full PPR, 1QB. CBS is held this week (data check), so three charts are available: enough for the market
// view (F.MIN_CHARTS). Your team holds a kicker. Their team lists a player with no engine row this week. You receive a
// single-source player (one input prices them) and a throw-in with no FantasyPros value (so no Trade chart average).
const SHAPE = {QB: 1, RB: 2, WR: 2, TE: 1, FLEX: 1, SUPERFLEX: 0, K: 1, DST: 0, BENCH: 6};
const CHARTS = ["usatoday", "fantasycalc", "fantasypros"];
const SPREAD = {usatoday: 1.04, fantasycalc: 0.97, fantasypros: 1.01, cbs: 0.98};
const r1 = n => Math.round(n * 10) / 10;
// JEG-1340: every player's name differs from its key, so a key drawn where a name belongs shows up in the render check.
const NAMES = {mQB: "Avery Lund", mQB2: "Bo Kestrel", mRB1: "Cal Ormond", mRB2: "Dax Fenwick", mRB3: "Eli Strand", mWR1: "Flynn Ashby",
  mWR2: "Gus Harlow", mWR3: "Hal Pryce", mTE: "Ivo Marchetti", mTE2: "Jory Vale", mK: "Kit Leclair",
  tQB: "Lars Penhall", tQB2: "Milo Drayton", tRB1: "Nico Farrow", tRB2: "Otis Quill", tRB3: "Pax Hendry", tWR1: "Quinn Talbot",
  tWR2: "Rory Castellan", tWR3: "Sol Whitcombe", tTE1: "Tad Merriam", tTE2: "Uri Blackwood", tGhost: "Vance Okafor"};
function player(key, pos, ddf, opts = {}) {
  const values = {ddf_value: ddf, ddf_value_charts: ddf === null ? null : r1(ddf * 1.02)};
  Object.entries(SPREAD).forEach(([c, k]) => {
    const scale = opts.market && opts.market[c] !== undefined ? opts.market[c] : k;
    values[c] = ddf === null || scale === null ? null : r1(ddf * scale);
  });
  values.ddf_value_projections = ddf === null ? null : r1(ddf * 0.95);
  F.PROJECTION_KEYS.forEach(p => { values[p] = values.ddf_value_projections; });
  return {player_key: key, name: opts.name || NAMES[key], pos, values,
    ...(opts.lowConfidence ? {ddfLowConfidence: true, ddfCount: 1, ddfConfidenceNote: "Only one source prices this player: ESPN."} : {}),
    ...(opts.estimated ? {estimated: opts.estimated} : {}),
    ...(opts.override !== undefined ? {valueOverride: ddf, ddfPipelineValue: opts.override, valueOverrideSpec: {type: "value"}} : {})};
}
const MINE = () => [
  player("mQB", "QB", 24), player("mQB2", "QB", 8), player("mRB1", "RB", 26), player("mRB2", "RB", 17), player("mRB3", "RB", 9),
  player("mWR1", "WR", 22, {market: {usatoday: 1.2, fantasycalc: 1.15, fantasypros: 1.18}}), player("mWR2", "WR", 16),
  player("mWR3", "WR", 7, {override: 5.5}), player("mTE", "TE", 12), player("mTE2", "TE", 4),
  {player_key: "mK", name: NAMES.mK, pos: "K", values: {}}
];
const THEIRS = () => [
  player("tQB", "QB", 19), player("tQB2", "QB", 10), player("tRB1", "RB", 28, {market: {usatoday: 0.85, fantasycalc: 0.88, fantasypros: 0.86}}),
  player("tRB2", "RB", 11), player("tRB3", "RB", 6), player("tWR1", "WR", 18, {lowConfidence: true}),
  player("tWR2", "WR", 14, {estimated: {fantasycalc: "Filled in from the other charts (VP-2.4)."}}),
  player("tWR3", "WR", 5, {market: {fantasypros: null}}), player("tTE1", "TE", 13), player("tTE2", "TE", 7)
];
// Their roster also lists a player the engine has no row for this week.
const THEIR_ENTRIES = rows => rows.map(r => ({key: r.player_key, name: r.name, pos: r.pos})).concat([{key: "tGhost", name: NAMES.tGhost, pos: "WR"}]);
const GIVE = ["mWR1", "mRB2"];
const RECEIVE = ["tRB1", "tWR1", "tWR3"];
const SOURCE_INFO = [
  {key: "usatoday", available: true}, {key: "fantasycalc", available: true}, {key: "fantasypros", available: true},
  {key: "cbs", available: false, excludedReason: "held: data check"},
  {key: "espn", available: true}, {key: "cbsros", available: true}, {key: "razzball", available: true}
];
// A 12-team allocation (rostered, in lineups, on benches, league-wide) as the engine's getAdjustmentWeights returns it.
const ALLOCATION = [{pos: "QB", rostered: 24, lineup: 12, bench: 12}, {pos: "RB", rostered: 60, lineup: 30, bench: 30},
  {pos: "WR", rostered: 66, lineup: 36, bench: 30}, {pos: "TE", rostered: 22, lineup: 14, bench: 8}];
const FIT = {expected: F.expectedDepth(ALLOCATION, 12), weights: {overall: 0.15, QB: 0.05, RB: 0.2, WR: 0.18, TE: 0.08}};
const CONTEXT = {scoring: "ppr", teams: 12, basis: {mode: "default"}, benchLevel: "modeled", week: 8};
const input = (over = {}) => {
  const mine = MINE();
  const theirs = THEIRS();
  return {shape: SHAPE, ourKey: F.OUR_KEY, chartKeys: CHARTS.slice(), sourceInfo: SOURCE_INFO,
    mine: {rows: mine, entries: mine.map(r => ({key: r.player_key, name: r.name, pos: r.pos}))},
    theirs: {rows: theirs, entries: THEIR_ENTRIES(theirs)}, give: GIVE, receive: RECEIVE, fit: FIT, context: CONTEXT, ...over};
};
let checks = 0;
const ok = (cond, msg) => { assert.ok(cond, msg); checks++; };
const eq = (a, b, msg) => { assert.deepEqual(a, b, msg); checks++; };

// ---------- the league finder's own calls on the same deal (league.js sidePanel / opportunities.js) ----------
function leagueRoute(inp) {
  const avg = rows => F.withChartAverage(rows, CHARTS);
  const mine = avg(inp.mine.rows);
  const theirs = avg(inp.theirs.rows);
  const byKey = new Map(mine.concat(theirs).map(r => [String(r.player_key), r]));
  const give = inp.give.map(k => byKey.get(k));
  const recv = inp.receive.map(k => byKey.get(k));
  const fit = F.tradeFit({mine: {roster: mine, leaving: give, arriving: recv}, theirs: {roster: theirs, leaving: recv, arriving: give}},
    {shape: SHAPE, expected: FIT.expected, weights: FIT.weights, ourKey: F.OUR_KEY, marketKey: F.MARKET_KEY, chartKeys: CHARTS, z: F.FIT_Z});
  const viability = F.viabilityLabel(fit, mine, theirs, give, recv, SHAPE, F.OUR_KEY, CHARTS);
  const combo = F.evaluateCombo(inp.give.map(k => inp.mine.rows.find(r => r.player_key === k)),
    inp.receive.map(k => inp.theirs.rows.find(r => r.player_key === k)), {ourKey: F.OUR_KEY, chartKeys: CHARTS, minCharts: 3});
  const gaps = TS.marketGaps(F.withChartAverage(give.concat(recv), CHARTS), 0);
  return {fit, viability, combo, gaps};
}

// ---------- golden ----------
const frozen = input();
const before = JSON.stringify(frozen);
const out = R.build(frozen);
eq(JSON.stringify(frozen), before, "inputs are never modified");
ok(out.ready, out.reason);
ok(out.rows, "the readout carries the second-half rows (JEG-1323)");
const rows = R.summary(out).rows;
const route = leagueRoute(input());

// Verdict: the golden deal's throw-in tWR3 has no Trade chart average, so there is no verdict (tradeFit would leave them
// out, as if they were worth 0); the reason names them and the missing series (Compare's "incomplete" rule).
eq(out.rows.verdict.status, "incomplete", "a moving player without a Trade chart average means no verdict");
eq(out.rows.verdict.missing, [{key: "tWR3", name: NAMES.tWR3, series: ["Trade chart average"]}], "who is missing, and in which series");
eq(out.rows.verdict.reason, `No verdict: ${NAMES.tWR3} has no Trade chart average value, and a missing value is never counted as 0.`);
ok(!("fit" in out.rows.verdict) && !out.rows.verdict.label, "no fit label from a partial deal");
// Will they accept, no profile and no verdict: no viability label, and the chart count is evaluateCombo's own (a chart
// counts only when it prices every moving player).
eq(out.rows.accept.basis, "viability");
eq(out.rows.accept.viability, null, "no viability without a verdict");
eq(out.rows.accept.charts, {even: route.combo.rivalOkCount, priced: route.combo.pricedCharts, available: 3}, "chart count = evaluateCombo");
ok(out.rows.accept.text.startsWith("Viability is not judged without a fit."), "and it says so");

// The same deal without the unpriced throw-in: tradeFit on the market rows, with which test failed.
{
  const pin = input({receive: ["tRB1", "tWR1"]});
  const priced = R.build(pin).rows;
  const proute = leagueRoute(input({receive: ["tRB1", "tWR1"]}));
  eq(priced.verdict.status, "available");
  eq(priced.verdict.label, proute.fit.label, "verdict label = league finder tradeFit");
  eq(priced.verdict.text, F.fitText(proute.fit), "verdict text = fitText");
  eq(priced.verdict.name, R.FIT_NAME[proute.fit.label]);
  eq(priced.verdict.tests.theirMarket.pass, proute.fit.theirOk, "their-market test is tradeFit's own theirOk (JEG-1340)");
  eq(priced.verdict.failed, ["construction", "yourValue", "theirMarket", "yourProjections", "theirProjections"].filter(id => !{construction: proute.fit.constructionOk,
    yourValue: proute.fit.yourValueOk, theirMarket: proute.fit.them.net >= -proute.fit.them.tau,
    yourProjections: proute.fit.natural.us.projections === true, theirProjections: proute.fit.natural.them.projections === true}[id]), "failed tests named");
  // Natural fit 1a (JEG-1324): both sides' projections are tests of the verdict, read from tradeFit's own `natural`.
  eq(priced.verdict.tests.yourProjections, {pass: proute.fit.natural.us.projections, net: proute.fit.natural.us.projNet}, "your projections test = tradeFit natural.us");
  eq(priced.verdict.tests.theirProjections, {pass: proute.fit.natural.them.projections, net: proute.fit.natural.them.projNet}, "their projections test = tradeFit natural.them");
  eq(priced.verdict.label === "natural", priced.verdict.failed.length === 0, "Natural exactly when no test failed (both sides)");
  // Their DDF Value (projections) falls, so it is not Natural under 1a even though the other tests pass.
  eq(priced.verdict.failed, ["theirProjections"], "only their projections fail");
  eq(priced.verdict.label, "market", "Market supported, not Natural");
  eq(priced.accept.viability, proute.viability, "viability = league.js viabilityLabel");
  eq(priced.accept.charts, {even: proute.combo.rivalOkCount, priced: proute.combo.pricedCharts, available: 3}, "chart count = evaluateCombo");
  // A moving player with no DDF Value at all blocks the verdict too, named with both series.
  const noDdf = input({receive: ["tRB1", "tWR1"]});
  const tw = noDdf.theirs.rows.find(r => r.player_key === "tWR1");
  Object.keys(tw.values).forEach(k => { if (k !== "ddf_value_projections" && !F.PROJECTION_KEYS.includes(k)) tw.values[k] = null; });
  const blocked = R.build(noDdf).rows.verdict;
  eq(blocked.status, "incomplete", "no DDF Value on a moving player: no verdict");
  eq(blocked.missing, [{key: "tWR1", name: NAMES.tWR1, series: ["DDF Value", "Trade chart average"]}]);
  // A kicker in the deal is not evaluated and does not block the verdict.
  const withK = R.build(input({give: ["mWR1", "mRB2", "mK"], receive: ["tRB1", "tWR1"]})).rows.verdict;
  eq(withK.status, "available", "a kicker in the deal never blocks the verdict");
}
// Sell gap: per player against the Trade chart average (marketGaps), the held chart excluded.
eq(out.rows.sellGap.basis, "market");
const gapOf = new Map(route.gaps.under.concat(route.gaps.over).map(g => [g.key, g.gap]));
out.rows.sellGap.players.filter(p => p.status === "priced").forEach(p => eq(p.gap, gapOf.get(p.key) || 0, `sell gap ${p.key} = marketGaps`));
eq(out.rows.sellGap.players.find(p => p.key === "tWR3"), {key: "tWR3", side: "receive", name: NAMES.tWR3, status: "unpriced",
  reason: "No Trade chart average value: left out of this series, not counted as 0."}, "unpriced throw-in keeps its reason");
eq(out.rows.sellGap.players.find(p => p.key === "mWR1").direction, "market-higher", "mWR1 is priced higher by the market");
eq(out.rows.sellGap.players.find(p => p.key === "tRB1").direction, "ddf-higher", "tRB1 is priced higher by DDF Value");
eq(out.rows.sellGap.players.find(p => p.key === "mRB2").direction, "even", "a gap inside team-summary's 2.0 noise floor names no lean");
eq(out.rows.sellGap.heldCharts, ["cbs"], "the held chart is named on the sell gap");
eq(out.rows.accept.heldCharts, ["cbs"], "and on the acceptance read");
// Data labels, the JEG-1221 words.
const labels = who => out.rows.dataLabels[who].map(l => `${l.key}:${l.kind}${l.series ? `:${l.series}` : ""}`).sort();
eq(labels("mine"), ["mK:not-evaluated", "mWR3:override"], "your team's labels: the kicker and your override");
eq(labels("theirs"), ["tGhost:no-value-this-week", "tWR1:single-source", "tWR2:estimated:fantasycalc", "tWR3:no-series-value:Trade chart average"].sort(),
  "their team's labels: no row this week, single source, estimated chart, missing series");
eq(out.rows.dataLabels.mine.find(l => l.key === "mK").text, "Not evaluated: kickers and defenses have no trade value. Kept on the roster, left out of every sum.", "S8");
eq(out.rows.dataLabels.theirs.find(l => l.key === "tGhost").text, "No value this week: not in this week's sources. Left out of every sum, not counted as 0.", "S9");
eq(out.rows.dataLabels.theirs.find(l => l.key === "tWR1").tag, "◐ 1 source", "GL-03 tag");
eq(out.rows.dataLabels.theirs.find(l => l.key === "tWR2").tag, "≈ estimated");
eq(out.rows.dataLabels.mine.find(l => l.key === "mWR3").text, "You set this player's value to 7.0 (was 5.5 from DDF Value). Reset on the Overrides tab.", "override, overrides.js words");
// Context line.
eq(out.rows.context.text, "Full PPR · 12 teams · 1QB · DDF Value basis · Standard bench · Week 8");
eq(out.rows.context.missing, []);
// The held source shows on its view, not as a zero anywhere.
eq(out.views.market.held, ["cbs"], "CBS is held");

if (process.argv.includes("--write-golden")) {
  fs.writeFileSync(GOLDEN, `${JSON.stringify({ticket: "JEG-1323", source: "trade-readout.js second-half rows", rows}, null, 1)}\n`);
} else {
  eq(JSON.parse(fs.readFileSync(GOLDEN, "utf8")).rows, JSON.parse(JSON.stringify(rows)), "golden drift");
}

// ---------- named cases ----------
// Data labels before a deal is ready read the market view's own charts: with nothing picked on one side the labels are
// the same as for the full deal, so a priced player never reads "No Trade chart average value".
{
  const notReady = R.build(input({give: []}));
  ok(!notReady.ready, "an empty side is not ready");
  eq(notReady.rows.dataLabels, out.rows.dataLabels, "labels do not depend on the deal being ready");
}
// Natural fit 1a: a moving player with no DDF Value (projections) leaves both sides not judged (null), never read as 0,
// and a side that is not judged is not Natural.
{
  const inp = input({receive: ["tRB1", "tWR1"]});
  const w = inp.mine.rows.find(r => r.player_key === "mWR1");
  w.values.ddf_value_projections = null;
  F.PROJECTION_KEYS.forEach(p => { w.values[p] = null; });
  const v = R.build(inp).rows.verdict;
  eq(v.tests.yourProjections, {pass: null, net: null}, "unjudged projections are null, not 0");
  eq(v.tests.theirProjections, {pass: null, net: null});
  ok(v.failed.includes("yourProjections") && v.failed.includes("theirProjections"), "an unjudged side counts as a failed test");
  ok(v.label !== "natural", "and the trade is not Natural");
}
// #1084 appeal band when the reader has a profile for this manager; an unknown band falls back to viability.
{
  const withBand = R.build(input({appeal: {band: "possible", likelihood: "Possible", why: ["By DDF Value, which you said they weigh a lot, they come out +1.2."]}}));
  eq(withBand.rows.accept.basis, "profile");
  eq(withBand.rows.accept.likelihood, "Possible");
  eq(withBand.rows.accept.text, "Possible: your own read of this manager from the Managers card, not a prediction.");
  eq(R.build(input({appeal: {band: "hidden", likelihood: "?"}})).rows.accept.basis, "viability", "an unknown band is not shown as a likelihood");
}
// #1105 league depth only when every team passes the completeness check; the reasons show when it does not.
{
  const gap = key => ({mWR1: {ours: 22, theirs: 25.5, gap: 3.5}, mRB2: {ours: 17, theirs: 16, gap: -1}, tRB1: {ours: 28, theirs: 28, gap: 0}}[key] || null);
  const league = R.build(input({leagueDepth: {check: {ok: true, reasons: []}, gapOf: gap, floor: 2}})).rows.sellGap;
  eq(league.basis, "league");
  eq(league.label, "League depth: DDF Value at your league's market level against its DDF level");
  eq(league.floor, 2);
  eq(league.players.map(p => [p.key, p.status, p.direction || null]), [["mWR1", "priced", "market-higher"], ["mRB2", "priced", "even"],
    ["tRB1", "priced", "even"], ["tWR1", "unpriced", null], ["tWR3", "unpriced", null]]);
  const held = R.build(input({leagueDepth: {check: {ok: false, reasons: ["2 teams not loaded"]}, gapOf: gap}})).rows.sellGap;
  eq(held.basis, "market", "a league that fails the check keeps the per-player gap");
  eq(held.leagueReasons, ["2 teams not loaded"]);
}
// K/DEF stay unevaluated on both sell-gap bases, even if a league-depth provider returns a number for them.
for (const pos of ["K", "DEF"]) {
  const inp = input({give: [...GIVE, "mK"]});
  inp.mine.rows.find(r => r.player_key === "mK").pos = pos;
  const market = R.build(inp).rows.sellGap.players.find(p => p.key === "mK");
  eq(market.status, "not-evaluated", `${pos}: market gap excludes unevaluated positions`);
  inp.leagueDepth = {check: {ok: true, reasons: []}, floor: 2,
    gapOf: () => ({ours: 10, theirs: 20, gap: 10})};
  const league = R.build(inp).rows.sellGap.players.find(p => p.key === "mK");
  eq(league, {key: "mK", side: "give", name: NAMES.mK, status: "not-evaluated", reason: R.STRINGS.notEvaluated},
    `${pos}: league-depth gap keeps S8 instead of a value`);
}
// The same explicit trade is supported under every scoring label; the adapter consumes caller-supplied values.
for (const [scoring, label] of [["standard", "Standard"], ["half_ppr", "Half PPR"], ["ppr", "Full PPR"]]) {
  const result = R.summary(R.build(input({context: {...CONTEXT, scoring}}))).rows;
  eq(result.context.text, `${label} · 12 teams · 1QB · DDF Value basis · Standard bench · Week 8`);
  const {context, ...tradeRows} = result;
  const {context: goldenContext, ...goldenTradeRows} = rows;
  eq(tradeRows, goldenTradeRows, `${scoring}: context does not recalculate the trade's numbers`);
}
// Too few charts: no verdict, no acceptance, no sell gap, each with the S13 reason, never a zero.
{
  const two = R.build(input({chartKeys: ["usatoday", "fantasycalc"]})).rows;
  eq(two.verdict, {status: "unavailable", reason: "Not enough trade charts this week (2 of 3 needed), so we can't judge whether they'd accept."});
  eq(two.accept.status, "unavailable");
  eq(two.sellGap.status, "unavailable");
  eq(two.sellGap.reason, "Trade chart average unavailable (2 of 3 charts).");
  eq(two.sellGap.players, []);
}
// No fit context (no expected depth): the verdict says why; acceptance still counts the charts.
{
  const noFit = R.build(input({fit: null})).rows;
  eq(noFit.verdict.status, "unavailable");
  eq(noFit.accept.basis, "viability");
  eq(noFit.accept.viability, null);
  ok(/charts have them winning or even/.test(noFit.accept.text), noFit.accept.text);
}
// Not ready: the deal rows say why; data labels and the context line still show.
{
  const empty = R.build(input({give: []})).rows;
  eq(empty.verdict, {status: "not-ready", reason: "Add a player to both sides to see how each roster changes."});
  eq(empty.accept.status, "not-ready");
  eq(empty.sellGap.status, "not-ready");
  eq(empty.context.text, "Full PPR · 12 teams · 1QB · DDF Value basis · Standard bench · Week 8");
}
// Context line: unknown parts are listed as missing, never guessed; a custom basis and league bench are named.
{
  eq(R.build(input({context: {}, shape: null})).rows.context, {status: "available", reason: null, scoring: null, teams: null, superflex: null,
    basis: null, benchLevel: null, week: null, missing: ["scoring", "teams", "superflex", "basis", "bench level", "week"], text: ""});
  eq(R.build(input({context: {...CONTEXT, basis: {mode: "blend"}, benchLevel: "league"}, shape: {...SHAPE, SUPERFLEX: 1}})).rows.context.text,
    "Full PPR · 12 teams · Superflex · Your basis, not ours · Bench from your league's rosters · Week 8");
}
// JEG-1340: null is unknown, never "1QB" or 0 teams.
{
  const c = R.build(input({context: {...CONTEXT, superflex: null, teams: null, week: null}, shape: null})).rows.context;
  eq([c.superflex, c.teams, c.week], [null, null, null]);
  eq(c.missing, ["teams", "superflex", "week"]);
  ok(!c.text.includes("1QB"), c.text);
}
// JEG-1340: a player listed twice on a roster gets each label once.
{
  const twice = input();
  twice.theirs.rows.push({...twice.theirs.rows.find(r => r.player_key === "tWR1")});
  twice.theirs.entries.push({key: "tGhost", name: NAMES.tGhost, pos: "WR"});
  eq(R.build(twice).rows.dataLabels.theirs.map(l => `${l.key}:${l.kind}`), out.rows.dataLabels.theirs.map(l => `${l.key}:${l.kind}`));
}
// TradeContext: inputFromContext fills the context line from common.league, the basis and pricing.mode.
{
  const all = MINE().concat(THEIRS());
  const ctx = {common: {league: {scoring: "half_ppr", teams: 10, roster: {SUPERFLEX: 1}}, valuation: {basis: {mode: "default"}, overrides: {}}, sources: {}},
    teams: {mine: {roster: MINE().map(r => ({key: r.player_key, name: r.name, pos: r.pos}))}, theirs: {roster: THEIRS().map(r => ({key: r.player_key, name: r.name, pos: r.pos}))}},
    deal: {give: GIVE, get: RECEIVE}, pricing: {mode: "league", levels: {}}};
  const inp = R.inputFromContext(ctx, {rowsByKey: new Map(all.map(r => [r.player_key, r])), shape: SHAPE, chartKeys: CHARTS, sourceInfo: SOURCE_INFO, week: 8, fit: FIT});
  eq(R.build(inp).rows.context.text, "Half PPR · 10 teams · Superflex · DDF Value basis · Bench from your league's rosters · Week 8");
  eq([R.build(inp).rows.verdict.status, R.build(inp).rows.verdict.reason], [out.rows.verdict.status, out.rows.verdict.reason],
    "the same deal from a TradeContext reads the same verdict");
}
// No weekly series is read: rows carrying weekly values give the same second half.
{
  const weekly = input();
  weekly.mine.rows.concat(weekly.theirs.rows).forEach(r => { r.values = {...r.values, weekly_ddf_value: 99, fp_weekly: 99}; });
  eq(JSON.stringify(R.summary(R.build(weekly)).rows), JSON.stringify(rows), "weekly values do not reach any row");
}
// The rows render in the spec's order, each with its value or its reason.
{
  const doc = fakeDocument();
  const node = R.renderRows(out, {document: doc});
  eq(node.children.map(c => c.dataset.row), ["verdict", "accept", "sell-gap", "data-labels", "context"]);
  const text = node.textContent;
  ok(text.includes(out.rows.verdict.reason), "the missing-value verdict draws its reason");
  ok(R.renderRows(R.build(input({receive: ["tRB1", "tWR1"]})), {document: doc}).textContent.includes(R.build(input({receive: ["tRB1", "tWR1"]})).rows.verdict.text),
    "a priced deal draws its verdict text");
  ok(text.includes("Sol Whitcombe (you get): No Trade chart average value"), "unpriced player drawn by name with its reason");
  ok(text.includes("Their team, Quinn Talbot: ◐ 1 source: Only one source prices this player: ESPN."), "single-source tag drawn by name");
  ok(text.includes("Their team, Vance Okafor: No value this week"), "a roster entry with no engine row is drawn by its entry name");
  // JEG-1340: no raw player key is drawn anywhere a name belongs (data-label and sell-gap lines included).
  const keysDrawn = Object.keys(NAMES).filter(key => new RegExp(`\\b${key}\\b`).test(text));
  eq(keysDrawn, [], "no player key in the rendered rows");
  out.rows.dataLabels.mine.concat(out.rows.dataLabels.theirs).forEach(item => eq(item.name, NAMES[item.key], `data label ${item.key} carries its name`));
  out.rows.sellGap.players.forEach(p => eq(p.name, NAMES[p.key], `sell gap ${p.key} carries its name`));
  ok(text.includes("Held this week (data check), not in the Trade chart average: CBS Sports."), "held chart drawn");
  ok(text.includes("Full PPR · 12 teams · 1QB · DDF Value basis · Standard bench · Week 8"), "context line drawn");
  const two = R.renderRows(R.build(input({chartKeys: ["usatoday"]})), {document: doc}).textContent;
  ok(two.includes("Not enough trade charts this week (1 of 3 needed)"), "an unavailable row draws its reason, not a zero");
}

function fakeDocument() {
  const make = tag => {
    const n = {tagName: tag, children: [], dataset: {}, className: "", _text: "",
      appendChild(c) { this.children.push(c); return c; },
      get textContent() { return this._text + this.children.map(c => c.textContent).join("\n"); },
      set textContent(v) { this._text = String(v); this.children = []; }};
    return n;
  };
  return {createElement: make};
}

console.log(`JEG-1323 readout rows: ${checks} checks passed`);
