"""Selected-package composition preview (JEG-1275, part of JEG-1183): the view model in
app/v2/package-composition-preview.js, run under node (no browser) against tests/fixtures/package_composition_preview/
cases.json. The roster check is a mock that replays answers recorded from the JEG-1262 helper (PR 1116); the lineups are
written by hand for the test. Every fixture is synthetic and says so.

  * a valid three-counterparty package: counts of the shown composition, every trade in the order given, the roster check
    passed, and the supplied before/after lineups carried row for row (no recalculation);
  * the same package with no lineup adapter: final lineup unavailable, applyPackage never called, and none of the
    helper's rosters (which hold three recorded "RB" slots) reach the view;
  * duplicate team, duplicate player and unknown ids: the supplied errors kept in their order with their exact text,
    every trade still shown, each invalid trade flagged with its own errors, and no lineup;
  * the roster check missing, throwing or answering something unreadable: unavailable, never "passed";
  * an empty selection: nothing checked, no adapter called;
  * an incomplete supplied lineup: shown as incomplete with the supplied reasons and the empty slot named;
  * long names and four counterparties; refs given as strings, {key} and {player_key};
  * the preview never selects, ranks or re-orders: a reversed package renders reversed;
  * inputs are deep-frozen under strict mode and compare equal before and after; nothing is written anywhere.

Discrimination: test_checks_fail_on_broken_builds runs the same checks against mutated copies of the module (errors
sorted, only the first error kept, the helper's rosters shown as the final lineup, unavailable shown as passed, trades
sorted by team, invalid trades dropped) and requires each to fail.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
MODULE = REPO / "app" / "v2" / "package-composition-preview.js"
CASES = REPO / "tests" / "fixtures" / "package_composition_preview" / "cases.json"

CHECKS = r"""
"use strict";
const M = require(process.argv[1]);
const D = require(process.argv[2]);
const fails = [];
const fail = msg => fails.push(msg);
const clone = v => JSON.parse(JSON.stringify(v));
const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);
const eq = (a, b, what) => { if (!same(a, b)) fail(`${what}: got ${JSON.stringify(a)}, want ${JSON.stringify(b)}`); };
const deepFreeze = v => { if (v && typeof v === "object") { Object.values(v).forEach(deepFreeze); Object.freeze(v); } return v; };

// The injected JEG-1262 adapter and lineup adapter: mocks that replay the recorded answers and log every call.
function build(name, edit) {
  const c = clone(D.cases[name]);
  if (edit) edit(c);
  const a = c.adapter || {};
  const calls = [];
  const league = deepFreeze(clone(D.league));
  const trades = deepFreeze(clone(c.trades));
  const pkg = a.package === false ? null : {
    validatePackage(l, t) { calls.push(["validatePackage", l === league, t === trades]); if (a.throws) throw new Error(a.throws); return clone(a.validation); },
    applyPackage(l, t) { calls.push(["applyPackage", l === league, t === trades]); return clone(a.applied); }
  };
  const lineup = a.lineup ? {lineups(l, applied) { calls.push(["lineups", l === league, Boolean(applied && applied.teams)]); return clone(a.lineup); }} : null;
  const ctx = deepFreeze({fixture: D.fixture, league, trades, package: pkg, lineup});
  const before = JSON.stringify({league, trades});
  const vm = M.viewModel(ctx);
  if (JSON.stringify({league, trades}) !== before) fail(`${name}: inputs changed`);
  return {vm, calls, c};
}
const supplied = c => c.adapter.validation.errors.map(e => e.message);
const lineupText = side => ({starters: side.starters.map(r => [r.slot, r.name]), bench: side.bench.map(r => [r.slot, r.name])});
const suppliedText = side => ({starters: side.starters.map(r => [r.slot, r.name || r.key || "Empty"]), bench: side.bench.map(r => [r.slot, r.name || r.key || "Empty"])});
const keysIn = vm => JSON.stringify(vm);

// ---- valid, with a supplied lineup ----
{
  const {vm, calls, c} = build("valid_with_lineup");
  eq(vm.state, "valid", "valid state");
  eq(vm.legality.status, "passed", "valid legality");
  eq(vm.counts.text, "3 trades naming 3 other teams. Listed: 4 players you give, 4 players you get.", "valid counts");
  eq(vm.trades.map(t => t.opponent), ["Synthetic Team B", "Synthetic Team C", "Synthetic Team D"], "trade order and names");
  eq(vm.trades.map(t => [t.give, t.receive]), [[["WR Atlas"], ["RB Bravo"]], [["WR Aspen", "WR Azure"], ["WR Comet"]], [["TE Anchor"], ["TE Dawn", "WR Dart"]]], "players per trade");
  eq(vm.trades.some(t => t.invalid), false, "no invalid trades");
  eq(vm.lineup.status, "ready", "lineup ready");
  eq(lineupText(vm.lineup.before), suppliedText(c.adapter.lineup.before), "before lineup parity");
  eq(lineupText(vm.lineup.after), suppliedText(c.adapter.lineup.after), "after lineup parity");
  eq(calls, [["validatePackage", true, true], ["applyPackage", true, true], ["lineups", true, true]], "valid calls: inputs passed as given");
  if (!vm.fixture || vm.fixture.kind !== "synthetic" || !/Synthetic/.test(vm.fixture.label)) fail("valid: fixture not labelled synthetic");
  // Never selects, ranks or re-orders: a reversed package is shown reversed and counted the same.
  const rev = build("valid_with_lineup", x => { x.trades = x.trades.slice().reverse(); }).vm;
  eq(rev.trades.map(t => t.opponentId), ["d", "c", "b"], "reversed package shown reversed");
  eq(rev.counts.text, vm.counts.text, "counts do not depend on order");
}

// ---- valid, no lineup adapter: unavailable, helper rosters never shown ----
{
  const {vm, calls, c} = build("valid_no_lineup");
  eq(vm.state, "valid", "no-lineup state");
  eq(vm.lineup.status, "unavailable", "no-lineup lineup");
  if (!/no lineup was supplied/.test(vm.lineup.reason)) fail(`no-lineup reason: ${vm.lineup.reason}`);
  eq([vm.lineup.before, vm.lineup.after], [null, null], "no lineup rows");
  eq(calls, [["validatePackage", true, true]], "applyPackage not called without a lineup adapter");
  const rbSlots = c.adapter.applied.league.teams[0].entries.filter(e => e.slot === "RB").length;
  if (rbSlots !== 3) fail(`fixture should hold three recorded RB slots, has ${rbSlots}`);
  // Even with a lineup adapter whose answer is unreadable, the helper's rosters are not used as a lineup.
  const bad = build("valid_no_lineup", x => { x.adapter.lineup = {nonsense: true}; });
  eq(bad.vm.lineup.status, "unavailable", "unreadable lineup unavailable");
  if (/RB Amber/.test(JSON.stringify(bad.vm.lineup))) fail("helper roster leaked into the lineup view");
  const unapplied = build("valid_with_lineup", x => { x.adapter.applied = {ok: false, errors: [{code: "x", message: "synthetic"}]}; });
  eq([unapplied.vm.lineup.status, unapplied.calls.map(k => k[0])], ["unavailable", ["validatePackage", "applyPackage"]], "apply failure: no lineup asked");
}

// ---- invalid packages: supplied order and text, every row kept ----
for (const [name, flagged] of [["duplicate_team", [2]], ["duplicate_player", [1]], ["unknown_ids", [0, 1]]]) {
  const {vm, calls, c} = build(name);
  eq(vm.state, "invalid", `${name} state`);
  eq(vm.legality.errors.map(e => e.text), supplied(c), `${name} errors in supplied order and text`);
  eq(vm.trades.length, c.trades.length, `${name} every trade shown`);
  eq(vm.trades.filter(t => t.invalid).map(t => t.index), flagged, `${name} flagged trades`);
  vm.trades.forEach(t => eq(t.errors, c.adapter.validation.errors.filter(e => e.tradeIndex === t.index).map(e => e.message), `${name} trade ${t.index} errors`));
  eq(vm.lineup.status, "unavailable", `${name} no lineup`);
  eq(calls.map(k => k[0]), ["validatePackage"], `${name} only the check is called`);
  if (!vm.heading.includes(String(c.adapter.validation.errors.length))) fail(`${name} heading counts problems: ${vm.heading}`);
}
{
  const {vm} = build("duplicate_team");
  eq(vm.counts.text, "3 trades naming 2 other teams. Listed: 4 players you give, 3 players you get.", "duplicate team counts as shown");
  const u = build("unknown_ids").vm;
  eq(u.trades[0].opponent, "z", "unknown counterparty shown by its id");
  eq(u.trades[0].receive, ["s-z-rb9"], "unknown player shown by its key");
  eq(u.trades[1].give, ["QB Baker", "A player with no key"], "wrong-roster and keyless refs named, not dropped");
}

// ---- unavailable roster check ----
for (const name of ["unavailable_none", "unavailable_throws", "unavailable_unreadable"]) {
  const {vm} = build(name);
  eq([vm.state, vm.legality.status], ["unavailable", "unavailable"], `${name} state`);
  eq(vm.lineup.status, "unavailable", `${name} no lineup`);
  eq(vm.trades.length, 3, `${name} trades still shown`);
}
if (!/synthetic roster-check failure/.test(build("unavailable_throws").vm.legality.reason)) fail("throw reason not shown");
eq(build("valid_with_lineup", x => { x.adapter.validation = {ok: true, errors: [{message: "contradiction"}]}; }).vm.legality.status, "unavailable", "ok with errors is unreadable");
eq(build("valid_with_lineup", x => { x.adapter.validation = {ok: false, errors: []}; }).vm.legality.status, "unavailable", "failed with no errors is unreadable");

// ---- empty selection ----
{
  const {vm, calls} = build("empty_selection");
  eq([vm.state, vm.legality.status, vm.lineup.status, vm.trades.length], ["empty", "not_checked", "unavailable", 0], "empty");
  eq(vm.counts.text, "No trades selected.", "empty counts");
  eq(calls, [], "empty: no adapter called");
  eq(build("empty_selection", x => { x.trades = null; }).vm.state, "empty", "null selection is empty");
}

// ---- incomplete supplied lineup ----
{
  const {vm, c} = build("incomplete_lineup");
  eq(vm.lineup.status, "incomplete", "incomplete status");
  eq(vm.lineup.missing, ["Synthetic: no projection for TE Dawn this week.", "1 starting slot is empty in the supplied final lineup."], "incomplete reasons");
  eq(lineupText(vm.lineup.after), suppliedText(c.adapter.lineup.after), "incomplete after parity");
  eq(vm.lineup.after.starters.find(r => r.slot === "TE").name, "Empty", "empty slot shown as Empty");
}

// ---- long names, four counterparties, ref shapes ----
{
  const {vm} = build("long_names");
  eq(vm.state, "valid", "long names valid");
  eq(vm.counts.text, "4 trades naming 4 other teams. Listed: 4 players you give, 5 players you get.", "long names counts");
  if (!vm.trades[0].opponent.startsWith("Synthetic Team E With An Extraordinarily Long")) fail("long team name");
  eq(vm.trades[1].give, ["WR Azure"], "player_key ref named");
  eq(vm.trades[1].receive, ["RB Basil"], "{key} ref named from the roster");
}

process.stdout.write(JSON.stringify(fails));
"""

# Each mutant breaks one guarantee; the checks above must catch every one.
MUTANTS = {
    "errors sorted": ("errors: result.errors.map(", "errors: result.errors.slice().sort((x, y) => String(x.message).localeCompare(String(y.message))).map("),
    "first error only": ("errors: result.errors.map(", "errors: result.errors.slice(0, 1).map("),
    "helper rosters as lineup": (
        'return unavailable("Final lineup unavailable: no lineup was supplied',
        'const ap = ctx.package.applyPackage(ctx.league, trades); const mine = ap.league.teams[0].entries.map(e => ({slot: e.slot, key: e.key, name: e.name}));'
        ' return {status: "ready", reason: null, missing: [], before: {starters: mine, bench: []}, after: {starters: mine, bench: []}}; return unavailable("'),
    "unavailable shown as passed": ('return {status: "unavailable", errors: [], reason: "Roster check unavailable: no roster check',
                                    'return {status: "passed", errors: [], reason: "Roster check unavailable: no roster check'),
    "trades sorted": ("vm.trades = trades.map(", "vm.trades = trades.slice().sort((x, y) => String(x.opponentId).localeCompare(String(y.opponentId))).map("),
    "invalid trades dropped": ("vm.lineup = lineup(ctx, trades, vm.legality);", "vm.trades = vm.trades.filter(t => !t.invalid); vm.lineup = lineup(ctx, trades, vm.legality);"),
}


def run_checks(module: Path) -> list[str]:
    proc = subprocess.run(["node", "-e", CHECKS, str(module), str(CASES)], capture_output=True, text=True, timeout=60)
    if proc.returncode != 0:
        return [f"node exited {proc.returncode}: {proc.stderr[-600:]}"]
    return json.loads(proc.stdout)


@unittest.skipUnless(shutil.which("node"), "node is not installed")
class PackageCompositionPreviewContractTest(unittest.TestCase):
    def test_contract(self):
        self.assertEqual(run_checks(MODULE), [])

    def test_fixtures_are_labelled_synthetic(self):
        data = json.loads(CASES.read_text(encoding="utf-8"))
        self.assertEqual(data["fixture"]["kind"], "synthetic")
        self.assertIn("Synthetic", data["fixture"]["label"])
        self.assertTrue(all(t["name"].startswith("Synthetic Team") for t in data["league"]["teams"]))
        self.assertGreaterEqual(len({t["opponentId"] for t in data["cases"]["valid_with_lineup"]["trades"]}), 3)

    def test_module_has_no_storage_network_or_ranking(self):
        source = MODULE.read_text(encoding="utf-8")
        for word in ("localStorage", "sessionStorage", "indexedDB", "fetch(", "XMLHttpRequest", ".sort(", "TradePackageConstraints.", "require("):
            self.assertNotIn(word, source, f"{word} in the preview module")

    def test_checks_fail_on_broken_builds(self):
        source = MODULE.read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as tmp:
            for name, (old, new) in MUTANTS.items():
                with self.subTest(mutant=name):
                    self.assertEqual(source.count(old), 1, f"mutant anchor for {name!r} must match once")
                    path = Path(tmp) / f"mutant-{abs(hash(name))}.js"
                    path.write_text(source.replace(old, new), encoding="utf-8")
                    self.assertNotEqual(run_checks(path), [], f"checks did not catch: {name}")


SEARCH = REPO / "app" / "v2" / "trade-package-search.js"
SEARCH_CASES = REPO / "tests" / "jeg1183_package_cases.js"
SEARCH_CHECKS = r"""
"use strict";
const assert = require('node:assert/strict');
const S = require(process.argv[1]);
const {makeCase} = require(process.argv[2]);
const P = require(process.argv[3] + '/trade-package-constraints.js');
const F = require(process.argv[3] + '/finder.js');
const Preview = require(process.argv[3] + '/package-composition-preview.js');
const freeze = o => { if (o && typeof o === 'object') { Object.values(o).forEach(freeze); Object.freeze(o); } return o; };
const ids = r => r.trades.map(t => t.opponentId);
const test = process.argv[4];
if (test === 'three') {
  const {league, candidates, ctx} = makeCase();
  const before = JSON.stringify([league, candidates, [...ctx.rowsByKey]]);
  freeze(league); freeze(candidates); [...ctx.rowsByKey.values()].forEach(freeze); freeze(ctx);
  const r = S.selectPackage(league, candidates, ctx);
  assert.equal(r.status, 'ready');
  assert.deepEqual(ids(r), ['d', 'c', 'b']);
  assert.deepEqual(r.trades.map(t => t.edge), [13, 10, 7]);
  assert.deepEqual(r.trades.map(t => t.rank), [1, 2, 3]);
  assert.equal(r.edge, 30);
  assert.equal(P.validatePackage(league, r.trades).ok, true);
  const keys = r.trades.flatMap(t => t.give.concat(t.receive).map(p => p.player_key));
  assert.equal(new Set(keys).size, keys.length);
  assert.equal(new Set(ids(r)).size, 3);
  const sequential = r.trades.reduce((l, t) => P.applyTrade(l, t).league, league);
  assert.deepEqual(r.league, sequential);
  assert.deepEqual(r.league, P.applyPackage(league, r.trades).league);
  const rows = l => l.teams[0].entries.map(e => ctx.rowsByKey.get(e.key));
  assert.deepEqual(F.pickStarters(rows(r.league), ctx.shape, F.OUR_KEY), F.pickStarters(rows(sequential), ctx.shape, F.OUR_KEY));
  const side = l => {
    const p = F.pickStarters(rows(l), ctx.shape, F.OUR_KEY);
    const row = r => ({key: r.player_key, name: r.name, slot: r.pos});
    return {starters: p.starters.map(row), bench: p.bench.map(row)};
  };
  const vm = Preview.viewModel({league, trades: r.trades, package: P,
    lineup: {lineups: (before, after) => ({before: side(before), after: side(after)})}});
  assert.equal(vm.state, 'valid');
  assert.equal(vm.lineup.status, 'ready');
  assert.deepEqual(vm.lineup.after, side(sequential));
  assert.deepEqual(vm.lineup.after.starters.map(p => p.key), ['a-qb', 'a-rb', 'c-w', 'd-t']);
  assert.notDeepEqual(vm.lineup.before.starters, vm.lineup.after.starters);
  assert.deepEqual(ids(S.selectPackage(league, candidates.slice().reverse(), ctx)), ids(r));
  assert.equal(JSON.stringify([league, candidates, [...ctx.rowsByKey]]), before);
} else if (test === 'slot') {
  const {league, candidates, ctx} = makeCase('slot');
  ctx.keepMine = false; // Isolate the live viability gate from the optional keep-starters gate.
  for (const t of candidates) assert.equal(S.selectPackage(league, [t], ctx).trades.length, 1);
  const r = S.selectPackage(league, candidates, ctx);
  assert.deepEqual(ids(r), ['b']); // The second individually viable offer now empties RB.
  assert.ok(r.league.teams[0].entries.some(e => e.pos === 'RB'));
} else if (test === 'rerank') {
  const {league, candidates, ctx} = makeCase();
  // First gain makes the old WR starter expendable. C is initially Market, then
  // becomes Natural and must jump ahead of B; cached order would pick D,B,C.
  for (const p of ctx.rowsByKey.values()) p.values.ddf_value_projections = 0;
  ctx.rowsByKey.get('a-wr').values.ddf_value = 30;
  ctx.rowsByKey.get('d-t').pos = 'WR';
  Object.assign(league.teams[3].entries.find(e => e.key === 'd-t'), {pos: 'WR', slot: 'WR'});
  ctx.rowsByKey.get('d-t').values.ddf_value = 40;
  ctx.rowsByKey.get('c-w').pos = 'TE';
  Object.assign(league.teams[2].entries.find(e => e.key === 'c-w'), {pos: 'TE', slot: 'TE'});
  ctx.rowsByKey.get('c-w').values.ddf_value = 80;
  candidates[1].give = ['a-wr'];
  assert.equal(S.selectPackage(league, [candidates[1]], ctx).trades[0].overall, 'market');
  assert.equal(S.selectPackage(league, [candidates[0]], ctx).trades[0].overall, 'natural');
  const r = S.selectPackage(league, candidates, ctx);
  assert.deepEqual(ids(r), ['d', 'c', 'b']);
  assert.deepEqual(r.trades.map(t => t.overall), ['natural', 'natural', 'natural']);
  assert.deepEqual(r.trades.map(t => t.edge), [35, 50, 7]);
} else if (test === 'ties') {
  const {league, candidates, ctx} = makeCase();
  ctx.rowsByKey.get('b-r').values.ddf_value = 15;
  league.teams[1].name = 'Zebra'; league.teams[2].name = 'Alpha';
  assert.deepEqual(ids(S.selectPackage(league, candidates, ctx)), ['d', 'c', 'b']);
  assert.deepEqual(ids(S.selectPackage(league, candidates.slice().reverse(), ctx)), ['d', 'c', 'b']);
} else if (test === 'newly_viable') {
  const {league, candidates, ctx} = makeCase();
  league.teams[0].entries = league.teams[0].entries.filter(e => e.key !== 'a-r');
  candidates.splice(0, 1);
  candidates[0].give = ['a-rb'];
  ctx.rowsByKey.get('c-w').values.ddf_value = 80;
  ctx.rowsByKey.get('d-t').pos = 'RB';
  Object.assign(league.teams[3].entries.find(e => e.key === 'd-t'), {pos: 'RB', slot: 'RB'});
  ctx.keepMine = false;
  assert.equal(S.selectPackage(league, [candidates[0]], ctx).status, 'empty');
  // D supplies the RB that makes C possible, so initially rejected C is reconsidered.
  assert.deepEqual(ids(S.selectPackage(league, candidates, ctx)), ['d', 'c']);
} else if (test === 'arrival') {
  const {league, candidates, ctx} = makeCase();
  // The newly received D player cannot be traded onward, even to an unused team.
  ctx.rowsByKey.get('c-qb').values.usatoday = 1;
  ctx.rowsByKey.get('c-qb').values.fantasycalc = 1;
  ctx.rowsByKey.get('c-qb').values.fantasypros = 1;
  league.teams[2].entries.push({key: 'c-qb2', pos: 'QB', name: 'Synthetic backup QB'});
  ctx.rowsByKey.set('c-qb2', {...ctx.rowsByKey.get('c-qb'), player_key: 'c-qb2'});
  candidates.splice(1, 1, {opponentId: 'c', give: ['d-t'], receive: ['c-qb']});
  const r = S.selectPackage(league, candidates, ctx);
  assert.deepEqual(ids(r), ['d', 'b']);
  assert.equal(P.validatePackage(league, r.trades).ok, true);
} else if (test === 'conflicts') {
  const {league, candidates, ctx} = makeCase();
  candidates.push({opponentId: 'c', give: ['a-w'], receive: ['c-qb']}, // larger gain, still one counterparty
    {opponentId: 'd', give: ['a-r'], receive: ['d-qb']}, // conflicts with b's give
    {opponentId: 'c', give: ['d-t'], receive: ['c-t']}, // cannot re-trade an arrival
    {opponentId: 'missing', give: ['a-r'], receive: ['b-r']},
    {opponentId: 'b', give: [{key: 'a-r', player_key: 'a-w'}], receive: ['b-r']}, null);
  const r = S.selectPackage(league, candidates, ctx);
  assert.equal(r.ok, true);
  assert.equal(P.validatePackage(league, r.trades).ok, true);
  const keys = r.trades.flatMap(t => t.give.concat(t.receive).map(p => p.player_key));
  assert.equal(keys.length, new Set(keys).size);
  assert.equal(ids(r).length, new Set(ids(r)).size);
  assert.ok(r.trades.length >= 2);
} else if (test === 'unavailable') {
  const {league, candidates, ctx} = makeCase();
  assert.equal(S.selectPackage(league, [], ctx).status, 'empty');
  assert.equal(S.selectPackage(league, null, ctx).status, 'unavailable');
  assert.equal(S.selectPackage(null, candidates, ctx).status, 'unavailable');
  assert.equal(S.selectPackage(league, candidates, null).status, 'unavailable');
  assert.equal(S.selectPackage(league, candidates, {...ctx, market: []}).status, 'unavailable');
  ctx.rowsByKey.delete('a-qb');
  assert.equal(S.selectPackage(league, candidates, ctx).status, 'unavailable');
} else if (test === 'pricing') {
  const {league, candidates, ctx} = makeCase();
  candidates.forEach(t => { t.give = t.give.map(p => ({player_key: typeof p === 'string' ? p : p.key, values: {ddf_value: 999}})); });
  assert.deepEqual(ids(S.selectPackage(league, candidates, ctx)), ['d', 'c', 'b']);
  ctx.rowsByKey.get('d-t').values.ddf_value = null;
  assert.deepEqual(ids(S.selectPackage(league, candidates, ctx)), ['c', 'b']);
  ctx.rowsByKey.get('c-w').values.usatoday = null;
  assert.deepEqual(ids(S.selectPackage(league, candidates, ctx)), ['b']);
  league.teams[0].entries.push({key: 'x:DEF:NYJ', pos: 'DEF', name: 'Synthetic defense'});
  const r = S.selectPackage(league, candidates, ctx);
  assert.ok(r.league.teams[0].entries.some(e => e.key === 'x:DEF:NYJ'));
} else if (test === 'panel_lineups') {
  const Panel = require(process.argv[3] + '/trade-package-panel.js');
  const {league, candidates, ctx} = makeCase();
  ctx.shape.FLEX = 1; ctx.shape.SUPERFLEX = 1;
  league.teams.forEach(t => t.entries.forEach(e => { e.slot = 'RB'; }));
  const r = S.selectPackage(league, candidates, ctx);
  const unchanged = JSON.stringify([league, r.league]);
  const supplied = Panel.lineups(league, r.league, ctx);
  for (const [which, l] of [['before', league], ['after', r.league]]) {
    const expected = F.pickStarters(l.teams[0].entries.map(e => ctx.rowsByKey.get(e.key)), ctx.shape, F.OUR_KEY);
    assert.deepEqual(supplied[which].starters.map(p => p.key), expected.starters.map(p => p.player_key));
    assert.deepEqual(supplied[which].starters.map(p => p.slot), ['QB', 'RB', 'WR', 'TE', 'FLEX', 'SUPERFLEX']);
  }
  assert.equal(JSON.stringify([league, r.league]), unchanged);
  ctx.shape.RB = 20;
  assert.ok(Panel.lineups(league, r.league, ctx).after.starters.some(p => p.key === null && p.slot === 'RB'));
} else if (test === 'guardrails') {
  const {league, candidates, ctx} = makeCase();
  ctx.guardrails = {minDdfEdge: 10};
  assert.deepEqual(ids(S.selectPackage(league, candidates, ctx)), ['d']);
  const s = makeCase('slot');
  s.league.teams[0].entries.push({key: 'a-r3', name: 'Synthetic third RB', pos: 'RB'});
  s.ctx.rowsByKey.set('a-r3', {...s.ctx.rowsByKey.get('a-r1'), player_key: 'a-r3',
    values: {...s.ctx.rowsByKey.get('a-r1').values, ddf_value: 4}});
  s.ctx.guardrails = {minBackups: {RB: 1}};
  const guarded = S.selectPackage(s.league, s.candidates, s.ctx);
  assert.deepEqual(ids(guarded), ['b']); // C would consume the last RB backup.
  assert.ok(F.benchBackups(guarded.league.teams[0].entries.map(e => s.ctx.rowsByKey.get(e.key)), s.ctx.shape, F.OUR_KEY).RB >= 1);
} else { throw Error('unknown check ' + test); }
"""


@unittest.skipUnless(shutil.which("node"), "node is not installed")
class GreedyPackageSearchTest(unittest.TestCase):
    """Runs in the existing package-contract Makefile/CI lane."""

    def check_case(self, name, module=SEARCH):
        return subprocess.run(["node", "-e", SEARCH_CHECKS, str(module), str(SEARCH_CASES),
                               str(REPO / "app" / "v2"), name], capture_output=True, text=True, timeout=30)

    def test_greedy_selection_and_roster_invariants(self):
        for name in ("three", "slot", "rerank", "ties", "newly_viable", "arrival", "conflicts", "unavailable", "pricing", "guardrails", "panel_lineups"):
            with self.subTest(case=name):
                result = self.check_case(name)
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_missing_selector_fails_before(self):
        result = self.check_case("three", MODULE)  # The pre-change preview has no selector.
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("selectPackage is not a function", result.stderr)

    def test_coordinator_patch_applies_and_builds_the_panel_assets(self):
        """Apply only to temporary copies; shared owners retain their source files."""
        patch = REPO / "docs" / "integration" / "jeg1183-package-panel.patch"
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp)
            for name in ("app/v2/league.js", "pipelines/build_v2_page.py"):
                out = target / name
                out.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(REPO / name, out)
            result = subprocess.run(["git", "apply", str(patch)], cwd=target, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            league = (target / "app/v2/league.js").read_text(encoding="utf-8")
            self.assertIn('candidates: result.rows, ctx,', league)
            self.assertIn('UI.running || UI.timer ? {status: "pending"}', league)
            self.assertIn('TradePackageConstraints.applyPackage(ws, []).league', league)
            # Keep the real builder's root selectors, while executing the patched temporary source.
            source = (target / "pipelines/build_v2_page.py").read_text(encoding="utf-8")
            builder = types.ModuleType("jeg1183_patched_builder")
            builder.__file__ = str(REPO / "pipelines" / "build_v2_page.py")
            sys.path.insert(0, str(REPO / "pipelines"))
            exec(compile(source, builder.__file__, "exec"), builder.__dict__)
            from tests.test_build_v2_page import INDEX
            engine = target / "synthetic-engine.html"
            engine.write_text(INDEX, encoding="utf-8")
            built = builder.build(dist=target / "dist", engine_page=engine)
            html = built.read_text(encoding="utf-8")
            self.assertLess(html.index('src="v2/finder.js"'), html.index('src="v2/trade-package-search.js"'))
            self.assertLess(html.index('src="v2/trade-package-panel.js"'), html.index('src="v2/league.js"'))
            for name in ("trade-package-search.js", "trade-package-panel.js", "trade-package-panel.css",
                         "trade-package-constraints.js", "package-composition-preview.js", "package-composition-preview.css"):
                self.assertEqual((built.parent / name).read_bytes(), (REPO / "app" / "v2" / name).read_bytes())
                self.assertIn(f'v2/{name}', html)

    def test_final_lineup_mutation_is_caught(self):
        panel = REPO / "app" / "v2" / "trade-package-panel.js"
        source = panel.read_text(encoding="utf-8")
        anchor = "after: side(after)"
        self.assertEqual(source.count(anchor), 1)
        with tempfile.TemporaryDirectory() as tmp:
            mutant = Path(tmp) / "panel.js"
            mutant.write_text(source.replace(anchor, "after: side(before)").replace(
                'require("./', f'require("{REPO}/app/v2/'), encoding="utf-8")
            check = r"""
const assert = require('node:assert/strict');
const Panel = require(process.argv[1]);
const c = require(process.argv[2]).makeCase();
const selected = require(process.argv[3]).selectPackage(c.league, c.candidates, c.ctx);
const actual = Panel.lineups(c.league, selected.league, c.ctx).after.starters.map(r => r.key);
assert.deepEqual(actual, ['a-qb', 'a-rb', 'c-w', 'd-t']);
"""
            result = subprocess.run(["node", "-e", check, str(mutant), str(SEARCH_CASES), str(SEARCH)],
                                    capture_output=True, text=True, timeout=30)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("AssertionError", result.stderr)

    def test_greedy_mutations_are_caught(self):
        source = SEARCH.read_text(encoding="utf-8")
        mutations = {
            "stale rosters": ("rowsFor(current.teams.find(t => t.id === current.myTeamId))",
                              "rowsFor(baseline.league.teams.find(t => t.id === current.myTeamId))", "slot"),
            "edge before fit": ("O.rankRows(ranked)[0]", "ranked.sort((a, b) => b.edge - a.edge)[0]", "rerank"),
            "retrade arrivals": ("P.validatePackage(league, trades.concat([candidate]))",
                                 "P.validatePackage(current, [candidate])", "arrival"),
            "skip viability": ("if (!viability) continue;", "if (false) continue;", "slot"),
        }
        with tempfile.TemporaryDirectory() as tmp:
            for name, (old, new, case) in mutations.items():
                with self.subTest(mutant=name):
                    self.assertEqual(source.count(old), 1)
                    path = Path(tmp) / "search.js"
                    changed = source.replace(old, new).replace('require("./', f'require("{REPO}/app/v2/')
                    path.write_text(changed, encoding="utf-8")
                    result = self.check_case(case, path)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn("AssertionError", result.stderr)


if __name__ == "__main__":
    unittest.main()
