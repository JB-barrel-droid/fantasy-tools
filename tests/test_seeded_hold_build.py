"""A build with seeded holds passes the gate (JEG-569).

Jeremy (JEG-520): "hold a source, never take the whole site down".
Jeremy (JEG-569 part 2, 2026-10-12): "gray out the source, run no calcs on
it, gray out its derivatives. No computation on old data."

This test seeds that state on the committed fixture: one published chart
(FantasyCalc) and one projection (Razzball) held, with validationHold set.
Combos are KEPT so the engine includes the held source in the pipeline
(weights, pie, universe) -- removing a source renormalizes every other
source's values.  The page hides a held source's curves via validationHold.

It requires:

1. held sections keep their combos and carry a validationHold;
2. the fixture-level gate checks pass on that build: tests.test_static_export
   (run on the seeded fixture) and the test_superflex identity check.

Tests that need an unheld baseline read tests/_holds.without_held_sources.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "pipelines"))

import fidelity_hold as fh  # noqa: E402

FIXTURE = ROOT / "data" / "fixtures" / "current" / "comparison-sources-data.json"
CHART, PROJECTION = "fantasycalc", "razzball"
HOLDS = {root: {"stage": "publisher_vs_stored", "reason": "fidelity: publisher_vs_stored",
                "identity": f"seeded-{root}", "since": "2026-10-10T21:40:15Z", "summary": "seeded hold"}
         for root in (CHART, PROJECTION)}


def seeded_build() -> tuple[dict, dict]:
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    for section in fixture["sources"].values():
        if isinstance(section, dict):
            section.pop("validationHold", None)
            section.pop("promotionHold", None)
    held, report = fh.apply_fidelity_holds(fixture, HOLDS, 5)
    return fixture, held


class SeededHoldBuildTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.current, cls.held = seeded_build()
        cls.tmp = tempfile.TemporaryDirectory()
        cls.path = Path(cls.tmp.name) / "comparison-sources-data.json"
        cls.path.write_text(json.dumps(cls.held), encoding="utf-8")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_held_chart_keeps_combos_and_has_hold(self):
        """JEG-569 part 2: combos are kept so the engine can include the held
        source in the pipeline (weights, pie, universe). The validationHold
        flag tells the page to gray it out."""
        section = self.held["sources"][CHART]
        self.assertTrue(section.get("combos"), f"{CHART} combos should be preserved (not stripped)")
        hold = section["validationHold"]
        self.assertEqual(hold["reason"], "fidelity: publisher_vs_stored")
        self.assertEqual(hold["root"], CHART)

    def test_held_projection_keeps_combos_and_has_hold(self):
        section = self.held["sources"][PROJECTION]
        self.assertTrue(section.get("combos"), f"{PROJECTION} combos should be preserved (not stripped)")
        hold = section["validationHold"]
        self.assertEqual(hold["reason"], "fidelity: publisher_vs_stored")
        self.assertEqual(hold["root"], PROJECTION)

    def test_unheld_source_keeps_its_combos(self):
        """At least one unheld source must keep its combos intact."""
        for key in ("usatoday", "fantasypros", "cbs", "espn", "cbsros"):
            section = self.held["sources"].get(key)
            if isinstance(section, dict) and not section.get("validationHold"):
                self.assertTrue(section.get("combos"), f"{key} combos should not be empty")
                return
        self.fail("no unheld source found to verify")

    def test_static_export_passes_on_the_held_build(self):
        env = {**os.environ, "STATIC_EXPORT_COMPARISON": str(self.path)}
        proc = subprocess.run([sys.executable, "-m", "unittest", "tests.test_static_export"], cwd=str(ROOT),
                              env=env, capture_output=True, text=True, timeout=600)
        tail = "\n".join(proc.stderr.splitlines()[-60:])
        self.assertEqual(proc.returncode, 0, f"test_static_export fails on a held build:\n{tail}")

    def test_superflex_identity_passes_on_the_held_build(self):
        from tests import test_superflex  # noqa: PLC0415
        original = test_superflex.FIXTURE
        test_superflex.FIXTURE = self.path
        try:
            problems = test_superflex.identity_problems()
        finally:
            test_superflex.FIXTURE = original
        self.assertEqual(problems, [], "\n".join(problems[:10]))


if __name__ == "__main__":
    unittest.main()
