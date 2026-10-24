"""JEG-1031: the league -> engine-input mapping used by get-values (node, no network)."""
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class LeagueMappingTests(unittest.TestCase):
    @unittest.skipIf(shutil.which("node") is None, "node not installed")
    def test_mapping_and_clamps(self):
        out = subprocess.run(
            ["node", "--experimental-strip-types", "--no-warnings",
             str(ROOT / "tests/node/league_mapping_check.mjs")],
            capture_output=True, text=True, timeout=60,
        )
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertTrue(out.stdout.strip().endswith("ok"))


if __name__ == "__main__":
    unittest.main()
