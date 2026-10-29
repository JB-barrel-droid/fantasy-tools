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
import tempfile
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


if __name__ == "__main__":
    unittest.main()
