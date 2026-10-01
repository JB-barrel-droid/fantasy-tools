import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = ROOT / "data" / "fixtures" / "current"
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

    def test_jeg5_recorded_assertion_rejects_perturbed_fixture(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            for name in ("players.json", "comparison-sources-data.json"):
                shutil.copy2(FIXTURE_DIR / name, tmp_dir / name)

            comparison_path = tmp_dir / "comparison-sources-data.json"
            payload = json.loads(comparison_path.read_text())
            values = payload["sources"]["espn"]["combos"]["full_12"]["values"]
            values["jahmyr gibbs"] += 1.0
            comparison_path.write_text(json.dumps(payload, separators=(",", ":")))

            result = run_harness(
                "--fixture-dir",
                str(tmp_dir),
                "--simulate",
                "tier-mismatch",
                "--assert-bad",
                "--assert-jeg5-recorded",
            )

        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("simulated JEG-5 numbers drifted", result.stderr)


if __name__ == "__main__":
    unittest.main()
