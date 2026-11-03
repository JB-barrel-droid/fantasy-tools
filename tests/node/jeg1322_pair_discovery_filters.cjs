// Focused JEG-1322 component contract; no browser, search or value-model build.
"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const {createRequire} = require("node:module");
const V2 = path.resolve(__dirname, "../../app/v2");
const D = require(path.join(V2, "discovery-controls.js"));
const F = require(path.join(V2, "finder.js"));
const O = require(path.join(V2, "opportunities.js"));
const W = require(path.join(V2, "workspace.js"));
const modulePath = path.join(V2, "pair-discovery-filters.js");
// Optional source override lets the Python check prove a no-op filter is caught
// without changing any tracked implementation or its dependency resolution.
const source = fs.readFileSync(process.argv[2] || modulePath, "utf8");
const sandbox = {module: {exports: {}}, require: createRequire(modulePath)};
vm.runInNewContext(source, sandbox, {filename: modulePath});
const P = sandbox.module.exports;
const plain = value => JSON.parse(JSON.stringify(value));
const ids = groups => Array.from(groups, g => g.id);
const freeze = value => {
  if (value && typeof value === "object" && !Object.isFrozen(value)) {
    Object.freeze(value);
    Object.values(value).forEach(freeze);
  }
  return value;
};
const group = (id, label, edge, charts, viable) => ({id, core: {player_key: id},
  best: {give: [{player_key: id + "-give"}], receive: [{player_key: id + "-get"}], edge, rivalOkCount: charts},
  alternatives: [{label: "natural", edge: 99}], label, viable});
// Deliberately interleave fit labels: listing must preserve incoming rank.
const groups = freeze([group("force", "force", 8, 4, "High"), group("market", "market", 4, 2, "Medium"),
  group("unknown", null, null, null, null), group("natural", "natural", 2, 3, "High"),
  group("natural-low", "natural", 1, 1, null)]);
const fitOf = g => g.label ? {label: g.label} : null;
const viableOf = g => g.viable;
const cases = [];
const test = (name, fn) => cases.push([name, fn]);

test("default controls preserve every ranked group and package identity", () => {
  const fail = () => { throw Error("default controls must not evaluate fit/viability"); };
  const record = D.fromWorkspace(W.newWorkspace({id: "lg", now: 1}).ui);
  const selected = P.filterGroups(groups, record, fail, fail);
  assert.deepEqual(ids(selected), ids(groups));
  selected.forEach((g, i) => { assert.equal(g, groups[i]); assert.equal(g.best, groups[i].best); });
  assert.deepEqual(plain(selected), plain(groups));
});
test("missing controls keep all fits including force and unjudged", () => {
  assert.deepEqual(ids(P.filterGroups(groups)), ids(groups));
});
test("natural-only selects best-package natural fits without reranking", () => {
  assert.deepEqual(ids(P.filterGroups(groups, {filters: {fit: "natural"}}, fitOf)), ["natural", "natural-low"]);
});
test("natural plus market selects both labels, excluding force and unjudged", () => {
  assert.deepEqual(ids(P.filterGroups(groups, {filters: {fit: "naturalMarket"}}, fitOf)), ["market", "natural", "natural-low"]);
});
test("legacy naturalValue uses the shared naturalMarket normalization", () => {
  assert.deepEqual(ids(P.filterGroups(groups, {filters: {fit: "naturalValue"}}, fitOf)), ["market", "natural", "natural-low"]);
});
test("hide force retains unjudged groups and never promotes an alternative", () => {
  assert.deepEqual(ids(P.filterGroups(groups, {hideForce: true}, fitOf)), ["market", "unknown", "natural", "natural-low"]);
});
test("fit and hide-force compose with today's viable-only predicate", () => {
  const record = {filters: {fit: "naturalMarket"}, hideForce: true, viableOnly: true};
  assert.deepEqual(ids(P.filterGroups(groups, record, fitOf, viableOf)), ["market", "natural"]);
  assert.deepEqual(ids(P.filterGroups(groups, {viableOnly: true}, fitOf, viableOf)), ids(F.viableGroups(groups, viableOf)));
});
test("unavailable fit and viability stay unjudged rather than force or viable", () => {
  assert.deepEqual(ids(P.filterGroups(groups, {hideForce: true, viableOnly: true})), ids(groups));
  assert.deepEqual(ids(P.filterGroups(groups, {filters: {fit: "natural"}})), []);
});
test("another route's saved opponent never hides the pair's results", () => {
  const record = D.fromWorkspace({filters: {fit: "natural", opponent: "another-team"}});
  assert.equal(record.filters.opponent, "another-team");
  assert.deepEqual(ids(P.filterGroups(groups, record, fitOf)), ["natural", "natural-low"]);
  assert.equal(record.filters.opponent, "another-team");
});
test("shared capture and chart minima use best-package data and reject missing values", () => {
  const record = {filters: {minCapture: 2, minCharts: 3}};
  assert.deepEqual(ids(P.filterGroups(groups, record)), ["force", "natural"]);
});
test("each fit/hide/minimum combination agrees with league filterRows", () => {
  const rows = groups.map(g => ({id: g.id, overall: g.label, edge: g.best.edge, rivalOkCount: g.best.rivalOkCount}));
  for (const fit of ["all", "natural", "naturalMarket", "naturalValue", "invalid"]) {
    for (const hideForce of [false, true]) {
      for (const minCapture of [0, 2]) {
        for (const minCharts of [0, 3]) {
          const record = D.normalize({filters: {fit, minCapture, minCharts}, hideForce});
          const expected = O.filterRows(rows, record.filters, hideForce).map(r => r.id);
          assert.deepEqual(ids(P.filterGroups(groups, record, fitOf)), expected);
        }
      }
    }
  }
});
test("frozen controls/groups remain unchanged and empty input stays empty", () => {
  const record = D.normalize({filters: {fit: "naturalMarket", opponent: "ignored"}, hideForce: true, viableOnly: true});
  const before = JSON.stringify({groups, record});
  const selected = P.filterGroups(groups, record, fitOf, viableOf);
  selected.forEach(g => assert.ok(groups.includes(g)));
  assert.equal(JSON.stringify({groups, record}), before);
  assert.deepEqual(ids(P.filterGroups([], record, fitOf, viableOf)), []);
});
test("real tradeFit labels are consumed without redefining natural fit", () => {
  const charts = ["usatoday", "fantasycalc", "fantasypros", "cbs"];
  const player = (id, ddf, market, proj) => ({player_key: id, name: id, pos: "RB",
    values: {ddf_value: ddf, chart_avg: market, ddf_value_charts: ddf, ddf_value_projections: proj,
      ...Object.fromEntries(charts.map(c => [c, market]))}});
  const give = player("give", 10, 20, 15);
  const receive = player("receive", 20, 10, 15);
  const base = id => [player(id, 50, 50, 50)];
  const ctx = {shape: {QB: 0, RB: 1, WR: 0, TE: 0, FLEX: 0, SUPERFLEX: 0},
    weights: {RB: 0.15, overall: 0.15}, ourKey: "ddf_value", marketKey: "chart_avg", chartKeys: charts, z: 1};
  const fit = incoming => F.tradeFit({mine: {roster: [...base("m"), give], leaving: [give], arriving: [incoming]},
    theirs: {roster: [...base("t"), incoming], leaving: [incoming], arriving: [give]}}, ctx);
  const judged = [fit(receive), fit(player("falling-proj", 20, 10, 5)), fit(player("force", 20, 30, 15))];
  assert.deepEqual(judged.map(f => f.label), ["natural", "market", "force"]);
  const real = judged.map((f, i) => ({id: String(i), best: {edge: 10, rivalOkCount: 4}, fit: f}));
  assert.deepEqual(ids(P.filterGroups(real, {filters: {fit: "natural"}}, g => g.fit)), ["0"]);
  assert.deepEqual(ids(P.filterGroups(real, {hideForce: true}, g => g.fit)), ["0", "1"]);
});
test("browser global export works with the same lazy dependencies", () => {
  const browser = {TradeValueDiscoveryControls: D, TradeValueOpportunities: O, TradeValueFinder: F};
  browser.window = browser;
  vm.runInNewContext(source, browser, {filename: modulePath});
  assert.deepEqual(ids(browser.TradeValuePairDiscoveryFilters.filterGroups(groups, {hideForce: true}, fitOf)),
    ["market", "unknown", "natural", "natural-low"]);
});

let failed = 0;
for (const [name, fn] of cases) {
  try { fn(); console.log("PASS " + name); }
  catch (error) { failed++; console.error("FAIL " + name + "\n" + error.stack); }
}
console.log(`${cases.length - failed} passed, ${failed} failed`);
process.exitCode = failed ? 1 : 0;
