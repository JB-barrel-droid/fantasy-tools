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

JEG-211 contract change (2026-10-03, 0ca6ab4): the old indexed-publisher
guard branch (indexedCurvesSatisfied over available publisher keys, added by
JEG-221) was retired from production with the K/DST honest exclusion and the
placeholder view-mode tabs. The guard now checks the computed default set
only: every defaultIndexedSourceKeys(inputs) key must be active or explicitly
user-deselected. The indexedAvailable scenarios below were removed with the
branch they tested; the remaining tests cover the live contract.
"""
import json
import subprocess
from pathlib import Path
import unittest

REPO = Path(__file__).resolve().parent.parent
HARNESS = Path(__file__).resolve().parent / "curve_guard_harness.js"
INPUTS = REPO / "app" / "trade-value-chart" / "assets" / "adjustment-inputs.json"


def run_case(active, deselected):
    payload = {"inputsPath": str(INPUTS), "active": active, "deselected": deselected}
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

    def test_toggle_handler_tracks_deselection(self):
        """The source-toggle change handler must maintain userDeselectedSources
        so the guard exemption reflects real user intent."""
        src = (REPO / "app" / "trade-value-chart" / "assets" / "curve-widget.js").read_text(encoding="utf-8")
        self.assertIn("userDeselectedSources.add(key)", src)
        self.assertIn("userDeselectedSources.delete(key)", src)
        self.assertIn("const defaultGroupedSources = defaultCurvesSatisfied(", src)


if __name__ == "__main__":
    unittest.main()
