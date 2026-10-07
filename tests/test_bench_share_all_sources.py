"""Decision feasible-bench-003 guard: no source withholds a position at any
bench-share step (JEG-432 R2).

tests/rendered_gate/bench_share_all_sources_harness.mjs sweeps every 0.001
step of the bench-share slider in all 12 league setups and checks that ESPN,
CBS ROS and Razzball each price all four positions, and that the chart says
in plain words when CBS ROS or Razzball is priced at its nearest workable
share.

Discrimination:
  test_catches_withholding_sources -- a dist copy where CBS ROS and Razzball
    go back to the downward-only fallback (the state before this decision)
    must FAIL on "sources" in several setups;
  test_catches_coded_note -- a dist copy whose note uses position codes must
    FAIL on "note".

Skips (does not fail) without dist/ or playwright-core, like the other
rendered checks in `make test-unit`.
"""
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
HARNESS = REPO / "tests" / "rendered_gate" / "bench_share_all_sources_harness.mjs"
DIST = REPO / "dist"
GATE_MODULES = REPO / "tests" / "rendered_gate" / "node_modules" / "playwright-core"

NEAREST = "const c = TwoTier.calibratePositionNearest(pool.tiers[pos], pies[pos],"
DOWNWARD_ONLY = "const c = TwoTier.calibratePositionFeasible(pool.tiers[pos], pies[pos],"
NAMES = 'const names = {QB: "quarterbacks", RB: "running backs", WR: "wide receivers", TE: "tight ends"};'
CODES = 'const names = {QB: "QB", RB: "RB", WR: "WR", TE: "TE"};'


def run_harness(dist):
    proc = subprocess.run(["node", str(HARNESS), str(dist)], capture_output=True, text=True,
                          timeout=600, env=os.environ.copy())
    if not proc.stdout.strip().startswith("{"):
        raise AssertionError(f"harness failed to start: rc={proc.returncode} stderr={proc.stderr[:1500]}")
    return proc.returncode, json.loads(proc.stdout)


def run_patched(old, new):
    widget = (DIST / "assets" / "curve-widget.js").read_text()
    if old not in widget:
        raise AssertionError(f"broken-state anchor missing from dist widget: {old[:70]}")
    with tempfile.TemporaryDirectory() as tmp:
        broken = Path(tmp) / "dist"
        shutil.copytree(DIST, broken)
        (broken / "assets" / "curve-widget.js").write_text(widget.replace(old, new, 1))
        return run_harness(broken)


class BenchShareAllSources(unittest.TestCase):
    def setUp(self):
        if not (DIST / "assets" / "curve-widget.js").exists():
            self.skipTest("dist/ not built; run `make sync` before this test")
        if not GATE_MODULES.exists():
            self.skipTest("playwright-core not installed; see preview.yml rendered gate step")

    def test_no_source_withholds_at_any_step(self):
        rc, report = run_harness(DIST)
        self.assertTrue(report.get("ok"), report.get("mismatches"))
        self.assertEqual(rc, 0)
        sweep = report["checks"]["sweep"]
        self.assertEqual(len(sweep), 12)
        self.assertGreater(sum(r["steps"] for r in sweep), 1500)
        # The guard is only meaningful while some source actually steps up.
        self.assertGreater(sum(r["stepped"] for r in sweep), 0)

    def test_catches_withholding_sources(self):
        rc, report = run_patched(NEAREST, DOWNWARD_ONLY)
        self.assertFalse(report.get("ok"), "harness passed with downward-only CBS ROS/Razzball fallback")
        self.assertNotEqual(rc, 0)
        sources = [m for m in report.get("mismatches", []) if m.startswith("sources:")]
        self.assertGreaterEqual(len(sources), 6, sources)

    def test_catches_coded_note(self):
        rc, report = run_patched(NAMES, CODES)
        self.assertFalse(report.get("ok"), "harness passed with position codes in the note")
        self.assertNotEqual(rc, 0)
        self.assertTrue(any(m.startswith("note: note uses codes") for m in report.get("mismatches", [])),
                        report.get("mismatches"))


if __name__ == "__main__":
    unittest.main()
