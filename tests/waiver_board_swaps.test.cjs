const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const A = require("../app/v2/waiver-board-swaps.js");
const W = require("../app/v2/waivers.js");
const F = require("../app/v2/finder.js");
const player = (key, pos, value) => ({player_key: key, name: `${pos} ${key}`, position: pos, team: "AAA",
  value: {ddf_value: value}, this_week: {points: 999, on_bye: true}});
const boardOf = players => ({schema: "waiver-board", schema_version: "0.1.0", players});
const shape = {QB: 1, RB: 1, WR: 1, TE: 1, BENCH: 3};
const expected = Object.fromEntries(["QB", "RB", "WR", "TE"].map(pos => [pos, {lo: 1, hi: 2}]));
const context = {shape, expected, weights: {QB: .1, RB: .5, WR: .4, TE: .1}};
const board = () => boardOf([player(1, "QB", 100), player(2, "RB", 90), player(3, "WR", 80),
  player(4, "TE", 70), player(5, "RB", 6), player(6, "WR", 4), player(7, "TE", 2),
  player(8, "RB", 12), player(9, "WR", 10)]);
const options = extra => ({rosterKeys: [1, 2, 3, 4, 5, 6, 7], wireKeys: [8, 9], context,
  acceptGain: gain => gain > 0, ...extra});

test("hand-worked sequential swaps use raw DDF gain and distinct players", () => {
  const b = board();
  const original = JSON.stringify(b);
  const out = A.buildSwapPlan(b, options());
  assert.equal(out.available, true);
  assert.deepEqual(out.swaps.map(s => [s.add.player_key, s.drop.player_key, s.gain]), [[8, 7, 10], [9, 6, 6]]);
  assert.ok(Math.abs(out.swaps[0].evaluation.totalDelta - 5.8) < 1e-9);
  assert.notEqual(out.swaps[0].gain, out.swaps[0].evaluation.totalDelta);
  const used = out.swaps.flatMap(s => [s.add.player_key, s.drop.player_key]);
  assert.equal(new Set(used).size, used.length);
  assert.equal(JSON.stringify(b), original);
});

test("overrides add and remove by identity, dedupe, and exclude own players", () => {
  assert.deepEqual(A.applyWireOverrides([8, "8", 9, 1], {add: [10, "10", 2], remove: [9]}, [1, 2]), ["8", "10"]);
  const out = A.buildSwapPlan(board(), options({wireKeys: [8], wireOverrides: {add: [9], remove: [8]}}));
  assert.deepEqual(out.swaps.map(s => s.add.player_key), [9]);
  assert.throws(() => A.applyWireOverrides([], {add: [8], remove: ["8"]}), /both added/);
});

test("gain policy is explicit and caller supplied", () => {
  assert.throws(() => A.buildSwapPlan(board(), {...options(), acceptGain: undefined}), /policy is required/);
  assert.deepEqual(A.buildSwapPlan(board(), options({acceptGain: () => false})).swaps, []);
  const out = A.buildSwapPlan(board(), options({acceptGain: gain => gain >= 10}));
  assert.deepEqual(out.swaps.map(s => s.gain), [10]);
});

test("an added player cannot be reused as a later drop", () => {
  const b = boardOf([player(1, "QB", 10), player(2, "RB", 10), player(3, "WR", 10), player(4, "TE", 10),
    player(8, "RB", 1), player(9, "WR", 2)]);
  const out = A.buildSwapPlan(b, options({rosterKeys: [1, 2, 3, 4], context: {...context, rosterSize: 5}}));
  assert.equal(out.swaps.length, 1);
  assert.equal(out.swaps[0].drop, null);
  assert.equal(out.swaps[0].gain, out.swaps[0].add.values.ddf_value);
});

test("missing roster keys block; missing wire keys are reported", () => {
  assert.equal(A.buildSwapPlan(board(), options({rosterKeys: [1, 2, 3, 4, 999]})).available, false);
  const out = A.buildSwapPlan(board(), options({wireKeys: [999, 8]}));
  assert.deepEqual(out.unresolvedWireKeys, ["999"]);
  assert.deepEqual(out.swaps.map(s => s.add.player_key), [8]);
});

test("missing values never become zero; real zero remains priced", () => {
  const b = board();
  b.players.find(p => p.player_key === 8).value.ddf_value = null;
  assert.deepEqual(A.buildSwapPlan(b, options({wireKeys: [8]})).swaps, []);
  b.players.find(p => p.player_key === 7).value.ddf_value = null;
  const out = A.buildSwapPlan(b, options({wireKeys: [9]}));
  assert.deepEqual(out.swaps, []); // Waivers' unpriced best drop is not a zero-cost drop.
  b.players.find(p => p.player_key === 7).value.ddf_value = 0;
  const priced = A.buildSwapPlan(b, options({wireKeys: [9]}));
  assert.equal(priced.swaps[0].gain, 10);
});

test("starters and required special positions are never proposed as bench drops", () => {
  const b = boardOf([player(1, "QB", 1), player(2, "RB", 10), player(3, "WR", 10), player(4, "TE", 10),
    player(7, "K", null), player(8, "RB", 30)]);
  const out = A.buildSwapPlan(b, options({rosterKeys: [1, 2, 3, 4, 7], wireKeys: [8],
    context: {...context, shape: {...shape, BENCH: 0, K: 1}}}));
  assert.deepEqual(out.swaps, []);
});

test("thin-position protection reads finder depth on each proposed swap", () => {
  const thin = {...context, expected: {...expected, TE: {lo: 2, hi: 2}}};
  const out = A.buildSwapPlan(board(), options({context: thin}));
  assert.deepEqual(out.swaps, []); // Waivers' best drop is TE 7; losing it thins TE.
});

test("missing depth context and partial rosters cannot promise depth protection", () => {
  assert.equal(A.buildSwapPlan(board(), options({context: {...context, expected: null}})).available, false);
  assert.equal(A.buildSwapPlan(board(), options({rosterKeys: [1]})).available, false);
});

test("weekly fields cannot change swap selection or gains", () => {
  const b = board();
  const first = A.buildSwapPlan(b, options());
  b.players.forEach(p => { p.this_week = {points: null, on_bye: false, injury_status: "Out"}; });
  assert.deepEqual(A.buildSwapPlan(b, options()), first);
});

test("malformed board identities, values and versions are refused", () => {
  assert.throws(() => A.rowsFromBoard({...board(), schema_version: "1.0.0"}), /0.1/);
  assert.throws(() => A.rowsFromBoard(boardOf([player(1, "RB", 2), player(1, "WR", 3)])), /unique/);
  assert.throws(() => A.rowsFromBoard(boardOf([player(1, "RB", NaN)])), /finite/);
  assert.throws(() => A.applyWireOverrides([null]), /resolved/);
});

for (const name of ["thin-rb", "deep-wr", "qb-streaming", "empty-slot-kdef", "no-chart-value", "all-worse"]) {
  test(`Waivers/finder sequential parity on existing ${name} fixture`, () => {
    const fx = JSON.parse(fs.readFileSync(path.join(__dirname, "fixtures", `waiver-${name}.json`), "utf8"));
    const all = fx.roster.concat(fx.candidates);
    const numeric = new Map(all.map((p, i) => [String(p.key), i + 1]));
    const b = boardOf(all.map(p => ({...player(numeric.get(String(p.key)), p.pos, p.ddf), name: p.name, team: p.team})));
    const ctx = {shape: fx.shape, expected: F.expectedDepth(fx.alloc, fx.teams), weights: fx.weights};
    const opts = {rosterKeys: fx.roster.map(p => numeric.get(String(p.key))), wireKeys: fx.candidates.map(p => numeric.get(String(p.key))),
      context: ctx, acceptGain: gain => gain > 0};
    const out = A.buildSwapPlan(b, opts);
    assert.equal(out.available, true);
    const adapted = A.rowsFromBoard(b);
    let roster = adapted.filter(p => opts.rosterKeys.includes(p.player_key));
    const remaining = new Set(opts.wireKeys);
    for (const swap of out.swaps) {
      const liveCtx = {...ctx, rosterSize: W.rosterSizeOf(ctx.shape), chartKeys: [], view: W.viewFor("ddf")};
      const ordered = W.orderResults(adapted.filter(p => remaining.has(p.player_key)).map(p => W.evaluateCandidate(liveCtx, roster, p)));
      const direct = ordered.find(r => r.candidate.player_key === swap.add.player_key);
      assert.deepEqual(swap.evaluation, direct);
      const impact = F.rosterImpact(roster, swap.drop ? [swap.drop] : [], [swap.add], ctx.shape, F.OUR_KEY);
      assert.ok(Math.abs(swap.gain - impact.totalDelta) < 1e-9);
      assert.equal(swap.gain, swap.add.values.ddf_value - (swap.drop ? swap.drop.values.ddf_value : 0));
      assert.ok(!swap.drop || impact.before.bench.some(p => p.player_key === swap.drop.player_key));
      assert.ok(Object.values(swap.evaluation.fit.depth).every(d => !(d.after < d.before && d.distAfter > d.distBefore)));
      remaining.delete(swap.add.player_key);
      roster = roster.filter(p => !swap.drop || p.player_key !== swap.drop.player_key).concat(swap.add);
    }
    if (name === "thin-rb" || name === "empty-slot-kdef") assert.ok(out.swaps.length > 0);
    if (name === "all-worse") assert.deepEqual(out.swaps, []);
  });
}

test("the merged board golden is read without mutation or repricing", () => {
  const b = JSON.parse(fs.readFileSync(path.join(__dirname, "fixtures", "waiver_board", "expected_half_ppr_12.json"), "utf8"));
  const rows = A.rowsFromBoard(b);
  assert.equal(rows.length, b.players.length);
  rows.forEach((r, i) => assert.equal(r.values.ddf_value, b.players[i].value.ddf_value));
});
