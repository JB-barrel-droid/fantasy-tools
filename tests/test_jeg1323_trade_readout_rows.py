"""JEG-1323: the shared trade readout's second half (verdict, will they accept, sell gap, data labels, context line)."""
from __future__ import annotations

import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class TradeReadoutRowsTest(unittest.TestCase):
    def test_rows_golden_and_named_cases(self):
        result = subprocess.run(["node", str(ROOT / "tests/node/jeg1323_trade_readout_rows_check.cjs")],
                                capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
        self.assertIn("checks passed", result.stdout)


if __name__ == "__main__":
    unittest.main()
