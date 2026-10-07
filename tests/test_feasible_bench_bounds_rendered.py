"""JEG-432 R2 rendered guard: the chart's bench controls clamp to the rule.

tests/rendered_gate/feasible_bench_bounds_harness.mjs loads the built page and
checks that the bench-share slider and the Bench stepper take their min/max
from ValueModel.feasibleBenchBounds, clamp out-of-range requests onto them,
pull the bench back when a league change shrinks the range, and that the
slider floor withholds no position.

Discrimination: test_harness_catches_fixed_ranges runs the same harness on a
copy of dist/ whose widget is put back to the pre-R2 fixed ranges (slider
[0.01, 0.30], stepper 0-14) and requires it to FAIL. A guard that passes on
the broken build would be worse than none.

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
HARNESS = REPO / "tests" / "rendered_gate" / "feasible_bench_bounds_harness.mjs"
DIST = REPO / "dist"
GATE_MODULES = REPO / "tests" / "rendered_gate" / "node_modules" / "playwright-core"

# Pre-R2 widget: fixed slider range and fixed stepper range.
BROKEN = [
    ("entry.bounds = feasible.benchShare ? [feasible.benchShare.min, feasible.benchShare.max] : null;",
     "entry.bounds = [0.01, 0.30];"),
    ("return b ? [b.min, b.max] : [ValueModel.BENCH_SLOTS_UI_MIN, ValueModel.BENCH_SLOTS_UI_MAX];",
     "return [0, 14];"),
]


def run_harness(dist):
    proc = subprocess.run(["node", str(HARNESS), str(dist)], capture_output=True, text=True,
                          timeout=180, env=os.environ.copy())
    if not proc.stdout.strip().startswith("{"):
        raise AssertionError(f"harness failed to start: rc={proc.returncode} stderr={proc.stderr[:1500]}")
    return proc.returncode, json.loads(proc.stdout)


class FeasibleBenchBoundsRendered(unittest.TestCase):
    def setUp(self):
        if not (DIST / "assets" / "curve-widget.js").exists():
            self.skipTest("dist/ not built; run `make sync` before this test")
        if not GATE_MODULES.exists():
            self.skipTest("playwright-core not installed; see preview.yml rendered gate step")

    def test_controls_follow_rule(self):
        rc, report = run_harness(DIST)
        self.assertTrue(report.get("ok"), report.get("mismatches"))
        self.assertEqual(rc, 0)
        for name in ("shareBounds", "shareClamp", "slotsBounds", "slotsClamp", "slotsLeague", "slotsBlocked"):
            self.assertIn(name, report["checks"], f"harness skipped {name}")

    def test_harness_catches_fixed_ranges(self):
        widget = (DIST / "assets" / "curve-widget.js").read_text()
        for old, _new in BROKEN:
            self.assertIn(old, widget, f"broken-state anchor missing from dist widget: {old[:60]}")
        with tempfile.TemporaryDirectory() as tmp:
            broken_dist = Path(tmp) / "dist"
            shutil.copytree(DIST, broken_dist)
            patched = widget
            for old, new in BROKEN:
                patched = patched.replace(old, new, 1)
            (broken_dist / "assets" / "curve-widget.js").write_text(patched)
            rc, report = run_harness(broken_dist)
        self.assertFalse(report.get("ok"), "harness passed on the pre-R2 fixed ranges")
        self.assertNotEqual(rc, 0)
        joined = " ".join(report.get("mismatches", []))
        # Each control's failure must be the one named, not an incidental error.
        self.assertIn("share-bounds", joined)
        self.assertIn("share-clamp", joined)
        self.assertIn("slots-bounds", joined)
        self.assertIn("slots-clamp", joined)


    def test_harness_catches_fail_open_stepper(self):
        """Decision feasible-bench-001: with no feasible bench size the stepper
        must be disabled with a reason. The pre-decision widget fell back to
        the 0-14 UI range and kept showing a number; the harness must fail it."""
        widget = (DIST / "assets" / "curve-widget.js").read_text()
        old = "out = rule.benchSlots || (rule.benchSlotsBlocked ? {blocked: rule.benchSlotsBlocked} : null);"
        self.assertIn(old, widget, "broken-state anchor missing from dist widget")
        with tempfile.TemporaryDirectory() as tmp:
            broken_dist = Path(tmp) / "dist"
            shutil.copytree(DIST, broken_dist)
            (broken_dist / "assets" / "curve-widget.js").write_text(
                widget.replace(old, "out = rule.benchSlots;", 1))
            rc, report = run_harness(broken_dist)
        self.assertFalse(report.get("ok"), "harness passed with a fail-open bench stepper")
        self.assertNotEqual(rc, 0)
        joined = " ".join(report.get("mismatches", []))
        self.assertIn("slots-blocked", joined)
        self.assertIn("stepper not disabled", joined)


if __name__ == "__main__":
    unittest.main()
