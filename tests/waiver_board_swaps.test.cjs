const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const Module = require("node:module");
const zlib = require("node:zlib");
const crypto = require("node:crypto");
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

function decimalScenario(add, drop, policy) {
  const b = board();
  b.players.find(p => p.player_key === 7).value.ddf_value = drop;
  b.players[b.players.findIndex(p => p.player_key === 8)] = player(8, "TE", add);
  const opts = options({wireKeys: [8]});
  const request = {roster_keys: opts.rosterKeys, wire_keys: opts.wireKeys, wire_overrides: {add: [], remove: []},
    context: opts.context, gain_policy: policy};
  return {b, opts, request};
}

function singleUseScenario(adapter) {
  // RB 2 wins the initial open slot: weighted gain 1 versus TE 5's 0.5.
  // Then RB 2 is the cheapest bench drop for TE 5, with raw gain +3.
  // The used-drop guard is the reason that second move must be rejected.
  const b = boardOf([player(1, "QB", 10), player(2, "RB", 10), player(3, "WR", 10), player(4, "TE", 10),
    player(8, "RB", 2), player(9, "TE", 5)]);
  return adapter.buildSwapPlan(b, options({rosterKeys: [1, 2, 3, 4],
    context: {...context, shape: {...shape, BENCH: 1}, rosterSize: 5}}));
}

function assertSingleUse(plan) {
  const used = plan.swaps.flatMap(s => [s.add.player_key, ...(s.drop ? [s.drop.player_key] : [])]);
  assert.equal(new Set(used).size, used.length, "a player was used in more than one move");
}

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

test("decimal equality respects strict and inclusive caller boundaries", () => {
  for (const [add, minimum] of [[3.35, .1], [3.55, .3]]) {
    const {b, opts, request} = decimalScenario(add, 3.25, {minimum, comparison: "gt"});
    assert.deepEqual(A.buildSwapBlock(b, request).rows, []);
    assert.deepEqual(A.buildSwapPlan(b, {...opts, acceptGain: gain => gain > minimum}).swaps, []);
    request.gain_policy.comparison = "gte";
    assert.deepEqual(A.buildSwapBlock(b, request).rows, [{add: 8, drop: 7, gain: minimum}]);
    const included = A.buildSwapPlan(b, {...opts, acceptGain: gain => gain >= minimum});
    assert.equal(included.swaps[0].gain, minimum);
  }
});

test("decimal comparison preserves real differences and scientific notation", () => {
  for (const [add, comparison, count] of [[3.3500000001, "gt", 1], [3.3499999999, "gte", 0]]) {
    const {b, request} = decimalScenario(add, 3.25, {minimum: .1, comparison});
    assert.equal(A.buildSwapBlock(b, request).rows.length, count);
  }
  const {b, request} = decimalScenario(1e-7, 9e-8, {minimum: 1e-8, comparison: "gt"});
  assert.deepEqual(A.buildSwapBlock(b, request).rows, []);
  request.gain_policy.comparison = "gte";
  assert.deepEqual(A.buildSwapBlock(b, request).rows, [{add: 8, drop: 7, gain: 1e-8}]);
});

test("only supported fantasy positions can be added, even with an open slot", () => {
  for (const pos of [null, "FB", "FLEX", "rb", "", "K", "DST"]) {
    const b = board();
    b.players.find(p => p.player_key === 8).position = pos;
    for (const rosterKeys of [[1, 2, 3, 4], [1, 2, 3, 4, 5, 6, 7]]) {
      assert.deepEqual(A.buildSwapPlan(b, options({rosterKeys, wireKeys: [8]})).swaps, [], String(pos));
    }
    assert.deepEqual(A.buildSwapPlan(b, options({wireKeys: [8, 9]})).swaps.map(s => s.add.player_key), [9]);
  }
});

test("a priced roster player with unknown position is not a valid bench drop", () => {
  const b = board();
  b.players.find(p => p.player_key === 7).position = null;
  assert.deepEqual(A.buildSwapPlan(b, options({wireKeys: [8]})).swaps, []);
});

test("an added player cannot be reused as a later drop", () => {
  const out = singleUseScenario(A);
  assert.equal(out.swaps.length, 1);
  assert.equal(out.swaps[0].add.player_key, 8);
  assert.equal(out.swaps[0].drop, null);
  assert.equal(out.swaps[0].gain, out.swaps[0].add.values.ddf_value);
  assertSingleUse(out);
});

test("single-use regression detects removal of the used-drop guard", () => {
  const filename = require.resolve("../app/v2/waiver-board-swaps.js");
  const source = fs.readFileSync(filename, "utf8");
  const guard = "used.has(keyOf(drop)) || ";
  assert.equal(source.split(guard).length - 1, 1, "mutation must remove exactly the drop guard");
  const mutant = new Module(filename, module);
  mutant.filename = filename;
  mutant.paths = Module._nodeModulePaths(path.dirname(filename));
  mutant._compile(source.replace(guard, ""), filename);
  const broken = singleUseScenario(mutant.exports);
  assert.deepEqual(broken.swaps.map(s => [s.add.player_key, s.drop && s.drop.player_key, s.gain]),
    [[8, null, 2], [9, 8, 3]]);
  assert.throws(() => assertSingleUse(broken), /used in more than one move/);
  assertSingleUse(singleUseScenario(A));
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

const storedDir = path.join(__dirname, "fixtures", "waiver_board_swaps");
const stored = name => JSON.parse(zlib.gunzipSync(fs.readFileSync(path.join(storedDir, name))));
const storedRequest = () => JSON.parse(fs.readFileSync(path.join(storedDir, "request.json"), "utf8"));

test("real stored 741-player board reproduces the renderer handoff without repricing", () => {
  const board = stored("stored-default.json.gz"), opt = stored("stored-opt-in.json.gz");
  const provenance = JSON.parse(fs.readFileSync(path.join(storedDir, "provenance.json"), "utf8"));
  const bytes = zlib.gunzipSync(fs.readFileSync(path.join(storedDir, "stored-default.json.gz")));
  assert.equal(crypto.createHash("sha256").update(bytes).digest("hex"), provenance.default_board_sha256);
  assert.equal(board.players.length, 741);
  assert.equal(board.schema_version, "0.1.0");
  assert.equal(board.swaps.available, false);
  assert.equal(opt.schema_version, "0.2.0");
  assert.deepEqual(opt.players, board.players);
  assert.deepEqual(opt.sources, board.sources);
  assert.deepEqual(A.buildSwapBlock(board, storedRequest()), opt.swaps);
  assert.deepEqual(opt.swaps.rows, provenance.expected_rows);
  const keys = opt.swaps.rows.flatMap(r => [r.add, r.drop]);
  assert.equal(new Set(keys).size, keys.length);
});

test("repeated real-data selections recompute on the supplied roster without retaining used players", () => {
  const board = stored("stored-default.json.gz"), request = storedRequest();
  const before = JSON.stringify(board);
  const first = A.buildSwapBlock(board, request);
  const other = structuredClone(request);
  other.wire_overrides.remove = [1110];
  const changed = A.buildSwapBlock(board, other);
  assert.deepEqual(changed.rows.map(r => [r.add, r.drop]), [[2730, 786]]);
  assert.deepEqual(A.buildSwapBlock(board, request), first);
  const open = structuredClone(request);
  open.roster_keys = open.roster_keys.filter(key => key !== 786);
  open.wire_keys = [1110];
  assert.deepEqual(A.buildSwapBlock(board, open).rows,
    [{add: 1110, drop: null, gain: 58.25526367807355}]);
  assert.equal(JSON.stringify(board), before);
  assert.deepEqual(request.wire_overrides, {add: [], remove: []});
});

test("real Christian McCaffrey / Mark Andrews decimal boundary is exact", () => {
  const board = stored("stored-default.json.gz"), request = storedRequest();
  request.roster_keys = request.roster_keys.slice(0, 7).concat(324);
  request.context.shape.BENCH = 1;
  request.wire_keys = [3189];
  request.gain_policy = {minimum: 53.81534496610199, comparison: "gt"};
  assert.deepEqual(A.buildSwapBlock(board, request).rows, []);
  request.gain_policy.comparison = "gte";
  assert.deepEqual(A.buildSwapBlock(board, request).rows,
    [{add: 3189, drop: 324, gain: 53.81534496610199}]);
});

test("real-data negative copies do not invent missing values or positions", () => {
  const original = stored("stored-default.json.gz"), request = storedRequest();
  const before = JSON.stringify(original);
  request.wire_keys = [1110];
  for (const position of [null, "FB"]) {
    const board = structuredClone(original);
    board.players.find(p => p.player_key === 1110).position = position;
    assert.deepEqual(A.buildSwapBlock(board, request).rows, []);
  }
  const missing = structuredClone(original);
  const player = missing.players.find(p => p.player_key === 1110);
  player.value.ddf_value = null;
  assert.deepEqual(A.buildSwapBlock(missing, request).rows, []);
  assert.equal(player.value.ddf_value, null);
  const zero = original.players.find(p => p.value.ddf_value === 0);
  assert.ok(zero);
  assert.equal(zero.value.missing_reason.ddf_value, undefined);
  assert.equal(JSON.stringify(original), before);
});
