"""Preparatory JEG-1322 group filters; finder page integration remains separate."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
CHECK = ROOT / "tests/node/jeg1322_pair_discovery_filters.cjs"
MODULE = ROOT / "app/v2/pair-discovery-filters.js"


class PairDiscoveryFiltersTest(unittest.TestCase):
    def test_group_filters(self):
        result = subprocess.run(["node", str(CHECK)], capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("14 passed, 0 failed", result.stdout)

    def test_fit_and_hide_force_checks_catch_a_noop(self):
        source = MODULE.read_text(encoding="utf-8")
        anchor = "opportunities().filterRows(rows, filters, listing.hideForce)"
        self.assertIn(anchor, source)
        broken = source.replace(anchor, "rows", 1)
        with tempfile.TemporaryDirectory() as tmp:
            module = Path(tmp) / "pair-discovery-filters.js"
            module.write_text(broken, encoding="utf-8")
            result = subprocess.run(["node", str(CHECK), str(module)], capture_output=True, text=True, check=False)
        self.assertNotEqual(result.returncode, 0, "No-op listing filter must fail the contract")
        self.assertIn("FAIL natural-only", result.stderr)
        self.assertIn("FAIL hide force", result.stderr)


if __name__ == "__main__":
    unittest.main()
