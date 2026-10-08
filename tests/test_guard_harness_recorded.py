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


class GuardHarnessRecordedTest(unittest.TestCase):
    def test_jeg5_recorded_assertion_matches_current_fixture(self):
        result = run_harness(
            "--simulate",
            "tier-mismatch",
            "--assert-bad",
            "--assert-jeg5-recorded",
        )

        self.assertEqual(result.returncode, 0, result.stderr)

    # Until 2026-10-08 the harness pinned the simulated total/target/delta
    # and this test perturbed the fixture to show the pin moved. The pin went
    # red on every refresh, so the assertion is now recompute-based (see
    # EXPECTED_JEG5 in tools/guard_harness.mjs). These prove it still fails
    # in the states it exists to catch.

    def test_rejects_simulation_that_no_longer_misses_the_pie(self):
        # The JEG-392 failure mode: on ESPN (the primary leg) the published
        # and training tiers coincide, so the simulated bug moves the pie by
        # ~1.3, inside the tolerance -- the guard could no longer fail.
        result = run_harness(
            "--source", "espn", "--simulate", "tier-mismatch",
            "--assert-jeg5-recorded",
        )
        self.assertNotEqual(result.returncode, 0, result.stdout[-400:])
        self.assertIn("expected simulated JEG-5 state to fail fixedPieIndexed", result.stderr)

    def test_rejects_simulation_inside_the_required_margin(self):
        # A simulated miss smaller than the required margin must fail. The
        # current CBS miss (~60) is under 100x the tolerance of 2.
        result = run_harness(
            "--simulate", "tier-mismatch", "--assert-jeg5-recorded",
            "--min-miss-tolerances", "100",
        )
        self.assertNotEqual(result.returncode, 0, result.stdout[-400:])
        self.assertIn("simulated miss", result.stderr)


if __name__ == "__main__":
    unittest.main()
