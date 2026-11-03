"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const D = require("../../app/v2/discovery-controls.js");
const A = require("../../app/v2/league-discovery-options.js");
const F = require("../../app/v2/finder.js");
const O = require("../../app/v2/opportunities.js");
const adapterSource = fs.readFileSync(require.resolve("../../app/v2/league-discovery-options.js"), "utf8");
const cases = [];
const test = (name, fn) => cases.push([name, fn]);
const plain = value => JSON.parse(JSON.stringify(value));
const shape = {QB: 1, RB: 1, WR: 1, TE: 0, FLEX: 0, SUPERFLEX: 0};
const ctx = {shape, charts: F.CHART_KEYS};
const row = (key, pos, value, market) => ({player_key: key, pos, values: {ddf_value: value,
  ...Object.fromEntries(F.CHART_KEYS.map(k => [k, market]))}});
const mine = [row("101", "RB", 10, 30), row("102", "WR", 1, 1), row("103", "QB", 1, 1)];
const theirs = [row("201", "RB", 8, 5), row("202", "WR", 20, 10), row("203", "QB", 1, 1)];
const options = record => A.finderOptions(record, ctx, mine, theirs);
const keys = result => result.trades.map(t => `${t.give.map(r => r.player_key)}|${t.receive.map(r => r.player_key)}`);
// Independent check of the protected-position invariant using the public starter picker.
function rbStarters(rows, rosterShape) {
  return F.pickStarters(rows, rosterShape, F.OUR_KEY).starters.filter(r => r.pos === "RB")
    .reduce((sum, r) => sum + r.values[F.OUR_KEY], 0);
}
function protectsRB(trade, roster, rosterShape) {
  const gone = new Set(trade.give.map(r => r.player_key));
  const after = roster.filter(r => !gone.has(r.player_key)).concat(trade.receive);
  return rbStarters(after, rosterShape) >= rbStarters(roster, rosterShape) - 0.05;
}

test("defaults preserve complete legacy pairing output", () => {
  const old = {chartKeys: ctx.charts, maxSize: 2, limit: Infinity,
    sanity: {shape, mine, theirs, keepMine: true, keepTheirs: true}};
  const expected = F.findTrades(mine, theirs, old);
  assert.ok(expected.trades.length > 0, "nonempty baseline");
  const actual = F.findTrades(mine, theirs, options(D.fromWorkspace({})));
  assert.deepEqual(actual, expected);
});
test("shared size and keep flags win over legacy ui.maxSize", () => {
  const record = D.fromWorkspace({maxSize: 4, finderSettings: {maxSize: 1, keepMine: false, keepTheirs: false}});
  const opts = options(record);
  assert.equal(opts.maxSize, 1);
  assert.equal(opts.sanity.keepMine, false);
  assert.equal(opts.sanity.keepTheirs, false);
  const found = F.findTrades(mine, theirs, opts);
  assert.ok(found.trades.length > 0);
  assert.ok(found.trades.every(t => t.give.length === 1 && t.receive.length === 1));
});
test("protect RB changes real finder output; omitted rails reproduce the bug", () => {
  const record = D.fromWorkspace({finderSettings: {maxSize: 1, keepMine: false, keepTheirs: false, protectedPositions: ["RB"]}});
  const opts = options(record);
  const guarded = F.findTrades(mine, theirs, opts);
  const without = F.findTrades(mine, theirs, {...opts, guardrails: undefined});
  assert.ok(without.trades.some(t => t.give.some(r => r.player_key === "101")), "baseline trades away the stronger RB");
  assert.ok(guarded.guardrailDropped > 0);
  assert.notDeepEqual(keys(guarded), keys(without));
  assert.ok(guarded.trades.every(t => protectsRB(t, mine, shape)));
});
test("all advanced fields and full rosters reach the existing guardrail engine", () => {
  const rails = {protectedPositions: ["TE"], minBackups: {QB: 1, RB: 2, WR: 3, TE: 1}, minDdfEdge: 2,
    minUserLineupGain: 0, minTheirLineupGain: 0};
  const record = D.fromWorkspace({finderSettings: rails});
  const opts = options(record);
  for (const key of D.GUARDRAIL_KEYS) assert.deepEqual(opts.guardrails[key], record[key], key);
  assert.strictEqual(opts.guardrails.mine, mine);
  assert.strictEqual(opts.guardrails.theirs, theirs);
  assert.strictEqual(opts.guardrails.shape, shape);
  assert.strictEqual(opts.guardrails.chartKeys, ctx.charts);
  assert.equal(opts.guardrails.ourKey, F.OUR_KEY);
  assert.equal(opts.limit, Infinity);
});
test("no shape retains null legacy sanity and does not mutate inputs", () => {
  const record = D.fromWorkspace({finderSettings: {maxSize: 1}});
  const before = plain({record, ctx, mine, theirs});
  assert.equal(A.finderOptions(record, {charts: ctx.charts, shape: null}, mine, theirs).sanity, null);
  options(record);
  assert.deepEqual(plain({record, ctx, mine, theirs}), before);
});
test("browser export uses the same shared contract", () => {
  const sandbox = {TradeValueDiscoveryControls: D};
  vm.runInNewContext(adapterSource, sandbox);
  assert.deepEqual(plain(sandbox.TradeValueLeagueDiscoveryOptions.finderOptions(D.DEFAULTS, ctx, mine, theirs)), plain(options(D.DEFAULTS)));
});

// Python supplies existing USO fixture rows priced by the same helper as the league trade tests.
// No browser, rebuild, fixture edits or broad suite is needed.
if (process.argv[2]) {
  const input = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
  test("USO: default pairing rows identical for every opponent; protect RB drops candidates", () => {
    const byKey = new Map(input.rows.map(r => [String(r.player_key), r]));
    const entries = keys => keys.map(key => ({key}));
    const rowsOf = keys => keys.map(k => byKey.get(String(k))).filter(Boolean);
    const mineRows = rowsOf(input.mine);
    const context = {rowsByKey: byKey, shape: input.shape, charts: F.CHART_KEYS, market: F.CHART_KEYS,
      maxSize: 2, keepMine: true, keepTheirs: true};
    let total = 0, dropped = 0;
    for (const [id, oppKeys] of Object.entries(input.opponents)) {
      const oppRows = rowsOf(oppKeys);
      const old = O.computePairing({id: "mine", entries: entries(input.mine)}, {id, entries: entries(oppKeys)}, context);
      const opts = A.finderOptions(D.fromWorkspace({}), context, mineRows, oppRows);
      const found = F.findTrades(mineRows, oppRows, opts);
      assert.deepEqual(found.trades.map(t => ({id: `${id}|${t.give.map(r => r.player_key)}|${t.receive.map(r => r.player_key)}`, edge: t.edge,
        charts: t.charts})), old.rows.map(r => ({id: r.id, edge: r.edge, charts: r.charts})), `vs ${id}`);
      total += found.trades.length;
      const rails = A.finderOptions(D.fromWorkspace({finderSettings: {protectedPositions: ["RB"]}}), context, mineRows, oppRows);
      const protectedResult = F.findTrades(mineRows, oppRows, rails);
      dropped += protectedResult.guardrailDropped;
      assert.ok(protectedResult.trades.every(t => protectsRB(t, mineRows, input.shape)), `protected RB vs ${id}`);
    }
    assert.ok(total > 0, "nonempty USO parity baseline");
    assert.ok(dropped > 0, "protect RB is exercised on USO");
    console.log(`USO ${Object.keys(input.opponents).length} opponents, ${total} identical default rows, ${dropped} guarded candidates dropped`);
  });
}
let failed = 0;
for (const [name, fn] of cases) {
  try { fn(); console.log(`ok ${name}`); }
  catch (err) { failed++; console.error(`FAIL ${name}\n${err.stack}`); }
}
console.log(`${cases.length - failed} passed, ${failed} failed`);
process.exitCode = failed ? 1 : 0;
