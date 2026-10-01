"""Scale-blind guard regression test: the fixedPieIndexed ESPN anchor check must
unscale the 70/max display-scaled anchor total before comparing against the raw
tier-surplus pie.

Root cause (2026-10-01): the DDF-native ESPN anchor carries the 70/max display
scale (ddfTwoTierValues multiplies raw values by 70/max(raw)), while
espnTargetTotal returns the raw tier-surplus pie. The guard compared
display-scaled values (sum 2322.12) against the raw pie (sum 795.57) --
difference 1526.55 >> tolerance 2 -- so fixedPieIndexed failed on every league
config and blanked the chart ("Curves unavailable").

Fix: anchorScaleCorrectedCheck unscales the anchor total by the display scale
before comparing, so the guard verifies the economics (raw 795.57 vs raw pie
795.57) not the presentation scale.
"""
import json
import subprocess
from pathlib import Path
import unittest

REPO = Path(__file__).resolve().parent.parent
HARNESS = Path(__file__).resolve().parent / "scale_guard_harness.js"


def run_case(displayTotal, pieSum, displayScale, tolerance=2):
    payload = {
        "displayTotal": displayTotal,
        "pieSum": pieSum,
        "displayScale": displayScale,
        "tolerance": tolerance,
    }
    proc = subprocess.run(
        ["node", str(HARNESS)],
        input=json.dumps(payload).encode(),
        capture_output=True,
        timeout=60,
    )
    assert proc.returncode == 0, f"harness failed: {proc.stderr.decode()[:500]}"
    return json.loads(proc.stdout.decode())


class TestAnchorScaleCorrectedCheck(unittest.TestCase):
    def test_worker_numbers_pass_after_unscaling(self):
        """The 2026-10-01 production numbers: display total 2322.12, raw pie
        795.57, scale 2322.12/795.57. The guard must pass -- the economics
        match, only the presentation scale differs."""
        scale = 2322.12 / 795.57
        res = run_case(2322.12, 795.57, scale)
        self.assertTrue(res["ok"],
                        f"scale-corrected guard must pass on matching economics: {res}")
        self.assertAlmostEqual(res["total"], 795.57, places=2)

    def test_scale_blind_comparison_would_fail(self):
        """Prove the test discriminates the old bug: comparing the display
        total directly against the raw pie (no unscaling) fails."""
        # Simulate the pre-fix behavior: scale=1 means no unscaling.
        res = run_case(2322.12, 795.57, 1)
        self.assertFalse(res["ok"],
                         "without unscaling, 2322 vs 795 must fail the guard")

    def test_genuine_mismatch_still_fails(self):
        """A genuinely wrong anchor (raw economics don't match the pie) must
        still fail the guard after unscaling -- the fix must not blindly pass."""
        scale = 2322.12 / 795.57
        # Anchor raw total 800 vs pie 795.57: off by 4.43 > tolerance 2.
        res = run_case(800 * scale, 795.57, scale)
        self.assertFalse(res["ok"],
                         "genuine economic mismatch must still trip the guard")

    def test_unscaled_anchor_still_works(self):
        """When there is no display scale (scale=1), the check behaves like a
        plain total-vs-pie comparison."""
        res = run_case(795.0, 795.57, 1)
        self.assertTrue(res["ok"])
        res = run_case(800.0, 795.57, 1)
        self.assertFalse(res["ok"])


if __name__ == "__main__":
    unittest.main()
