"""JEG-1240 / JEG-1264: the USO-shape trade journey as a Node contract on app/v2 (no browser).

tests/node/uso_site_journey_contract.cjs runs the journey on the real page modules with modeled values and returns
named failures, each with a kind and one code per carried case. Three classes:

  UsoJourneyHarnessTest     the fixture is synthetic and USO-shape; both sides' starters and bench by position; JSN
                            discoverable in the uncapped search; the exact equal, throw-in and explicit 2-for-1 packages;
                            the row gains and the readout equal to the lineup math; destinations built on their own state;
                            each lost piece of context (settings, basis, sources, level, a substituted or missing team,
                            the package) failing with its own code; unavailable values staying unavailable. Green on
                            every build.
  UsoJourneyContinuityTest  the trade carried through the DDF state link, the pair finder link and (where app/v2 has it)
                            the JEG-1259 trade context transfer to the same device and to another device with its own
                            settings, basis and sources. Red until the site carries the context or holds the trade naming
                            what differs. Never adjusted to pass; on main it names basis-changed and sources-changed on
                            another device and context-missing for the transfer (no trade-context.js yet).
  UsoJourneyMutationTest    broken copies of app/v2 compared with the build case by case: each must add its intended
                            code (or fail its intended check) and nothing outside that loss and its repricing.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app" / "v2"
LEAGUE = ROOT / "tests" / "fixtures" / "uso_site_journey" / "league.json"
CONTRACT = ROOT / "tests" / "node" / "uso_site_journey_contract.cjs"
HARNESS = ["test_fixture_is_uso_shape_and_synthetic", "test_both_sides_starters_and_bench_by_position",
           "test_jsn_discoverable_in_the_uncapped_search", "test_selected_candidates_are_exact",
           "test_league_row_gains_and_readout_match_the_lineup_math", "test_destination_state_is_independent",
           "test_dropped_context_fails_specifically", "test_unavailable_stays_unavailable", "test_diff_names_each_loss"]
CONTINUITY = ["test_state_link_carries_the_trade", "test_pair_link_carries_the_trade",
              "test_trade_context_transfer_carries_or_holds_the_trade"]
# The numbers that move when a piece of context is lost (tests/node/uso_site_journey_contract.cjs REPRICE).
REPRICE = {"value-changed", "value-lost", "value-filled", "value-missing", "gains-changed", "gains-missing", "readout-changed", "readout-missing"}


def check(app: Path) -> dict:
    out = subprocess.run(["node", str(CONTRACT), "check", str(app), str(LEAGUE)], capture_output=True, text=True, timeout=300, cwd=ROOT)
    if not out.stdout.strip():
        raise AssertionError(f"contract printed nothing: {out.stderr[-2000:]}")
    return json.loads(out.stdout.strip().splitlines()[-1])


_BUILD: dict | None = None


def build() -> dict:
    global _BUILD
    if _BUILD is None:
        _BUILD = check(APP)
    return _BUILD


def failure(out: dict, name: str) -> dict | None:
    return next((f for f in out["failures"] if f["name"] == name), None)


def triples(out: dict) -> set:
    return {(f["name"], c["case"], c["code"]) for f in out["failures"] for c in f.get("cases", [])}


class UsoJourneyHarnessTest(unittest.TestCase):
    def test_every_check_ran(self):
        self.assertEqual(build()["ran"], HARNESS + CONTINUITY)

    def test_harness_checks_pass(self):
        out = build()
        self.assertEqual([f for f in out["failures"] if f["kind"] != "continuity"], [])
        facts = out["facts"]
        self.assertEqual(facts["values"], "modeled")
        self.assertGreater(facts["candidates"], 0)
        self.assertGreater(facts["jsnCandidates"], 0)


class UsoJourneyContinuityTest(unittest.TestCase):
    def _carries(self, name):
        f = failure(build(), name)
        if f:
            self.fail(f["message"])

    def test_state_link_carries_the_trade(self):
        self._carries("test_state_link_carries_the_trade")

    def test_pair_link_carries_the_trade(self):
        self._carries("test_pair_link_carries_the_trade")

    def test_trade_context_transfer_carries_or_holds_the_trade(self):
        self._carries("test_trade_context_transfer_carries_or_holds_the_trade")


# name: (file, anchor, replacement, check, case filter, the code it must add, codes it may add beside it)
MUTATIONS = {
    "search capped at 10": ("opportunities.js", "limit: Infinity,", "limit: 10,",
                            "test_jsn_discoverable_in_the_uncapped_search", None, "none truncated", None),
    "state link without their roster": ("ddf-state.js", 'if (w.theirs) p.push("theirs=" + listToParam(w.theirs));', "",
                                        "test_state_link_carries_the_trade", "on same device", "team-missing", set()),
    "pair link without their roster": ("finder.js", "if (theirs) parts.push(`theirs=${theirs}`);", "",
                                       "test_pair_link_carries_the_trade", "on same device", "team-missing",
                                       {"package-changed", "package-not-rediscovered"}),
}


class UsoJourneyMutationTest(unittest.TestCase):
    def test_each_mutation_fails_for_its_reason(self):
        base = build()
        for name, (file, anchor, replacement, name_of_check, where, reason, beside) in MUTATIONS.items():
            with self.subTest(mutation=name), tempfile.TemporaryDirectory() as tmp:
                app = Path(tmp) / "v2"
                shutil.copytree(APP, app)
                body = (app / file).read_text(encoding="utf-8")
                self.assertIn(anchor, body, f"mutation anchor for {name!r} is stale")
                (app / file).write_text(body.replace(anchor, replacement, 1), encoding="utf-8")
                out = check(app)
                if where is None:
                    # A harness check: the mutant fails exactly that check, for the named reason, and no other harness check.
                    harness = [f for f in out["failures"] if f["kind"] == "harness"]
                    self.assertEqual([f["name"] for f in harness], [name_of_check], harness)
                    self.assertIn(reason, harness[0]["message"])
                    continue
                self.assertEqual([f for f in out["failures"] if f["kind"] == "harness"], [], "a continuity mutation broke the harness")
                self.assertIsNone(next((c for n, c, _ in triples(base) if n == name_of_check and where in c), None),
                                  f"the build already fails {name_of_check} {where}, so this mutation would prove nothing")
                new = triples(out) - triples(base)
                self.assertTrue(new, f"{name}: nothing new failed")
                self.assertEqual({n for n, _, _ in new}, {name_of_check}, f"{name}: other checks changed: {sorted(new)}")
                hit = {c for _, c, code in new if code == reason and where in c}
                self.assertTrue(hit, f"{name}: no {where} case names [{reason}]: {sorted(new)}")
                self.assertEqual({code for _, _, code in new} - {reason} - beside - REPRICE, set(), f"{name}: {sorted(new)}")


if __name__ == "__main__":
    unittest.main()
