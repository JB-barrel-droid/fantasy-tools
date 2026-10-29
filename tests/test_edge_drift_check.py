"""JEG-1049 / JEG-1256: the deployed-edge-function drift check (tools/edge_drift_check.mjs), against a local fake (no network).

Run: python3 -m unittest tests.test_edge_drift_check (also a line of make test-unit-modules).
The node harness pins exit 0 in sync, 1 drift, 2 could not compare for each fake reply.
"""
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class EdgeDriftCheckTests(unittest.TestCase):
    @unittest.skipIf(shutil.which("node") is None, "node not installed")
    def test_drift_check_against_fake_endpoints(self):
        out = subprocess.run(
            ["node", "--experimental-strip-types", "--no-warnings",
             str(ROOT / "tests/node/edge_drift_check.mjs")],
            capture_output=True, text=True, timeout=300,
        )
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertTrue(out.stdout.strip().endswith("ok"))


if __name__ == "__main__":
    unittest.main()
