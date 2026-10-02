"""JEG-103 regression test: bench-share slider must sync the Weights readout.

After moving the bench-share slider, the Weights panel readout must show the
new bench share value (not the stale default 15%). This test verifies that
setBenchShareFraction updates the internal benchShare variable, which is what
syncWeightsReadout() reads to generate the readout text.

The bug: slider handlers called setBenchShareFraction() and publishShared()
but never called syncWeightsReadout(), leaving the readout stale.
"""
import json
import subprocess
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
HARNESS = Path(__file__).resolve().parent / "bench_share_harness.js"


class TestBenchShareReadoutSync(unittest.TestCase):
    def test_setBenchShareFraction_updates_benchShare(self):
        """setBenchShareFraction must update the benchShare variable.

        This is the prerequisite for syncWeightsReadout() to show the new
        value. If benchShare stays at the default (0.15), the readout will
        say "15%" even after the slider moves.
        """
        # Test with a non-default bench share (20%)
        proc = subprocess.run(
            ["node", str(HARNESS)],
            input=json.dumps({"benchShare": 0.20}).encode(),
            capture_output=True,
            timeout=60,
        )
        self.assertEqual(proc.returncode, 0, f"harness failed: {proc.stderr.decode()[:500]}")
        result = json.loads(proc.stdout.decode())

        # The benchShare variable must reflect the new value.
        self.assertAlmostEqual(
            result["benchShare"], 0.20, places=3,
            msg=f"benchShare should be 0.20, got {result['benchShare']}"
        )
        self.assertTrue(
            result["success"],
            f"benchShare ({result['benchShare']}) did not match input (0.20)"
        )

    def test_setBenchShareFraction_handles_various_values(self):
        """Test multiple bench share values across the valid range."""
        test_values = [0.10, 0.15, 0.20, 0.25]
        for expected in test_values:
            with self.subTest(benchShare=expected):
                proc = subprocess.run(
                    ["node", str(HARNESS)],
                    input=json.dumps({"benchShare": expected}).encode(),
                    capture_output=True,
                    timeout=60,
                )
                self.assertEqual(proc.returncode, 0, f"harness failed: {proc.stderr.decode()[:500]}")
                result = json.loads(proc.stdout.decode())
                self.assertAlmostEqual(
                    result["benchShare"], expected, places=3,
                    msg=f"benchShare should be {expected}, got {result['benchShare']}"
                )


if __name__ == "__main__":
    unittest.main()
