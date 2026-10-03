"""DEFECT 1 regression test: the defaultGroupedSources guard must not throw
when the user deliberately unchecked a default curve.

Root cause (2026-10-01): runRegressionGuards() required every default curve
to be in activeSources. Unchecking any default curve (e.g. "USAT Adjusted")
then changing scoring/teams threw inside the guard BEFORE draw() and
publishShared(), so the comparison table never received the shared-change
event and froze on the old scoring with no visible error.

Fix: defaultCurvesSatisfied() exempts curves the user explicitly deselected
(tracked in userDeselectedSources by the toggle handler). A default that
vanishes WITHOUT the user asking still fails the guard.
"""
import json
import subprocess
from pathlib import Path
import unittest

REPO = Path(__file__).resolve().parent.parent
HARNESS = Path(__file__).resolve().parent / "curve_guard_harness.js"
INPUTS = REPO / "app" / "trade-value-chart" / "assets" / "adjustment-inputs.json"


def run_case(active, deselected, indexed_available=None):
    payload = {"inputsPath": str(INPUTS), "active": active, "deselected": deselected}
    if indexed_available is not None:
        payload["indexedAvailable"] = indexed_available
    proc = subprocess.run(
        ["node", str(HARNESS)],
        input=json.dumps(payload).encode(),
        capture_output=True,
        timeout=60,
    )
    assert proc.returncode == 0, f"harness failed: {proc.stderr.decode()[:500]}"
    return json.loads(proc.stdout.decode())


class TestDefaultCurvesSatisfied(unittest.TestCase):
    def test_user_deselected_default_does_not_throw(self):
        """DEFECT 1 repro: user unchecks USAT Adjusted, then changes scoring.
        The guard must be satisfied (no throw)."""
        res = run_case(
            active=["espn", "fantasycalc_adjusted", "fantasypros_adjusted", "cbs_adjusted"],
            deselected=["usatoday_adjusted"],
        )
        self.assertIn("usatoday_adjusted", res["defaults"])
        self.assertTrue(res["satisfied"],
                        "user-deselected default curve must not trip the guard")
        # Prove this test would have caught the original bug: the pre-fix
        # predicate throws in exactly this scenario.
        self.assertTrue(res["oldPredicateWouldThrow"],
                        "test must discriminate the pre-fix behavior")

    def test_missing_default_without_user_action_still_throws(self):
        """A default curve that vanished WITHOUT the user asking must still
        fail the guard (regression-catching power preserved)."""
        res = run_case(
            active=["espn", "fantasycalc_adjusted", "fantasypros_adjusted", "cbs_adjusted"],
            deselected=[],
        )
        self.assertFalse(res["satisfied"],
                         "unexplained missing default must still trip the guard")

    def test_all_defaults_active(self):
        res = run_case(
            active=["espn", "fantasycalc_adjusted", "usatoday_adjusted",
                    "fantasypros_adjusted", "cbs_adjusted"],
            deselected=[],
        )
        self.assertTrue(res["satisfied"])

    def test_indexed_publisher_selection_does_not_require_adjusted_defaults(self):
        result = run_case(["usatoday"], [], ["usatoday", "fantasycalc", "fantasypros", "cbs"])
        self.assertTrue(result["satisfied"])
        self.assertTrue(result["oldPredicateWouldThrow"])

    def test_indexed_empty_selection_requires_explicit_user_hiding(self):
        self.assertFalse(run_case([], [], ["usatoday", "cbs"])["satisfied"])
        self.assertFalse(run_case([], ["usatoday"], ["usatoday", "cbs"])["satisfied"])
        self.assertTrue(run_case([], ["usatoday", "cbs"], ["usatoday", "cbs"])["satisfied"])
        self.assertFalse(run_case(["espn"], [], ["usatoday", "cbs"])["satisfied"])

    def test_indexed_missing_coverage_does_not_pass_guard(self):
        self.assertFalse(run_case([], [], [])["satisfied"])

    def test_toggle_handler_tracks_deselection(self):
        """The source-toggle change handler must maintain userDeselectedSources
        so the guard exemption reflects real user intent."""
        src = (REPO / "app" / "trade-value-chart" / "assets" / "curve-widget.js").read_text()
        self.assertIn("userDeselectedSources.add(key)", src)
        self.assertIn("userDeselectedSources.delete(key)", src)
        self.assertIn("const defaultGroupedSources = indexedCurvesSatisfied(", src)


if __name__ == "__main__":
    unittest.main()
