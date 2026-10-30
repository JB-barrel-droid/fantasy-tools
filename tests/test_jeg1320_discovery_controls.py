"""JEG-1320: one stored record for the finders' discovery controls keeps each route's stored values and defaults."""
from __future__ import annotations

import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class DiscoveryControlsTest(unittest.TestCase):
    def test_discovery_controls_contract(self):
        result = subprocess.run(["node", str(ROOT / "tests/node/discovery_controls_check.cjs")],
                                capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(" passed, 0 failed", result.stdout)


if __name__ == "__main__":
    unittest.main()
