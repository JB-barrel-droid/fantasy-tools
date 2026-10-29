"""JEG-1229: shared trade preferences and the immutable TradeContext reach every trade route the same way."""
from __future__ import annotations

import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class TradeContextTest(unittest.TestCase):
    def test_trade_context_contract(self):
        result = subprocess.run(["node", str(ROOT / "tests/node/trade_context_check.cjs")],
                                capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(" passed, 0 failed", result.stdout)


if __name__ == "__main__":
    unittest.main()
