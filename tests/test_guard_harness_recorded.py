"""tools/guard_harness.mjs: the fixed-pie guard (VP-5) passes on the current
fixture and fails on the simulated retired ESPN-anchor rule.

JEG-508 replaced the JEG-5 "tier-mismatch" simulation (live adjustment cells
partitioned by published tiers): the live cells, the ESPN anchor and the
two-tier leg are retired, so that bug class can no longer exist. The guard
now checks every source's eight group totals against pie x DDF weight, and
the simulation pays one source's groups at ESPN's own weights (the retired
"ESPN group totals as DDF weights" rule), whose TOTAL still equals the pie --
only the group check can catch it.
"""
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / "tools" / "guard_harness.mjs"


def run_harness(*args):
    return subprocess.run(
        ["node", str(HARNESS), *args],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


class GuardHarnessTest(unittest.TestCase):
    def test_current_state_passes(self):
        result = run_harness("--assert-good")
        self.assertEqual(result.returncode, 0, result.stderr[-2000:])
        self.assertIn("current fixedPieIndexed: PASS", result.stdout)

    def test_espn_anchor_simulation_fails_the_guard(self):
        result = run_harness("--simulate", "espn-anchor", "--assert-bad")
        self.assertEqual(result.returncode, 0, result.stderr[-2000:])
        self.assertIn("simulated espn-anchor: FAIL (expected)", result.stdout)

    def test_rejects_simulation_inside_the_required_margin(self):
        # A simulated miss smaller than the required margin must fail the
        # harness: a simulation that drifted towards passing would otherwise
        # keep the guard "proved" while it no longer discriminates.
        result = run_harness("--simulate", "espn-anchor", "--assert-bad", "--min-group-miss", "100000")
        self.assertNotEqual(result.returncode, 0, result.stdout[-400:])
        self.assertIn("simulated miss", result.stderr)


if __name__ == "__main__":
    unittest.main()
