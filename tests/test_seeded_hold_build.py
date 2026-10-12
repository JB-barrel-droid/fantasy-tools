"""A build with seeded holds passes the gate and serves the held sections (JEG-569).

Jeremy (JEG-520): "hold a source, never take the whole site down". On
2026-10-10 (rebuild-chain runs 38088565756 and 38089772479) the fidelity pulse
held FantasyCalc, pipelines/fidelity_hold.py restored its section from the
15:26Z build as designed, and post-rebuild `make validate` failed in
test_static_export (the restored chart's Indexed pie and _adjusted values are
on the 15:26Z anchor and fit cells, not this build's), test_superflex and
test_published_league_settings_engine (the same saved values against this
build's anchor) and test_ddf_composite_value (its baseline required an unheld
live fixture). The chain then published no
source at all.

This test seeds that state on the committed fixture: one published chart
(FantasyCalc) held and restored from a last good build whose values differ
from this one's, and one projection (Razzball) held on its current section.
It requires:

1. the held sections are served: the chart from its last good build, the
   projection on this build's section, both labelled validationHold;
2. the fixture-level gate checks pass on that build: tests.test_static_export
   (run on the seeded fixture) and the test_superflex identity check. The
   test_published_league_settings_engine fixture-leg check is no longer run
   here: JEG-539 retired it with the derivePublishedSetup engine code it
   pinned. The render tests (test_ddf_composite_value) strip holds from their
   own copy of dist/.

Tests that need an unheld baseline read tests/_holds.without_held_charts.
"""
from __future__ import annotations

import copy
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
LAST_GOOD_BUILT_AT = "2026-10-03T12:00:00+00:00"
CHART, PROJECTION = "fantasycalc", "razzball"
HOLDS = {root: {"stage": "publisher_vs_stored", "reason": "fidelity: publisher_vs_stored",
                "identity": f"seeded-{root}", "since": "2026-10-10T21:40:15Z", "summary": "seeded hold"}
         for root in (CHART, PROJECTION)}


def last_good_build(fixture: dict) -> dict:
    """An earlier build: the chart's values 7% off this build's, as after a
    week of publisher drift (so they are NOT on this build's anchor)."""
    good = copy.deepcopy(fixture)
    good["built_at"] = LAST_GOOD_BUILT_AT
    for sec in (CHART,):  # the *_adjusted sections are retired (JEG-539)
        for combo in good["sources"][sec]["combos"].values():
            for field in ("native", "reindexed", "values"):
                if isinstance(combo.get(field), dict):
                    combo[field] = {k: round(float(v) * 1.07, 4) if isinstance(v, (int, float)) else v
                                    for k, v in combo[field].items()}
    return good


def seeded_build() -> tuple[dict, dict, dict]:
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    for section in fixture["sources"].values():
        if isinstance(section, dict):
            section.pop("validationHold", None)
            section.pop("promotionHold", None)
    good = last_good_build(fixture)
    held, report = fh.apply_fidelity_holds(fixture, HOLDS, lambda root: good, 5)
    return fixture, good, held


class SeededHoldBuildTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.current, cls.good, cls.held = seeded_build()
        cls.tmp = tempfile.TemporaryDirectory()
        cls.path = Path(cls.tmp.name) / "comparison-sources-data.json"
        cls.path.write_text(json.dumps(cls.held), encoding="utf-8")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_held_chart_is_served_from_its_last_good_build(self):
        section = copy.deepcopy(self.held["sources"][CHART])
        hold = section.pop("validationHold")
        self.assertEqual(section, self.good["sources"][CHART])
        self.assertEqual(hold["reason"], "fidelity: publisher_vs_stored")
        self.assertEqual(hold["restored_from"], LAST_GOOD_BUILT_AT)
        self.assertEqual(hold["root"], CHART)

    def test_held_projection_keeps_this_builds_section_labelled(self):
        section = copy.deepcopy(self.held["sources"][PROJECTION])
        hold = section.pop("validationHold")
        self.assertEqual(section, self.current["sources"][PROJECTION])
        self.assertEqual((hold["reason"], hold["root"]), ("fidelity: publisher_vs_stored", PROJECTION))

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
