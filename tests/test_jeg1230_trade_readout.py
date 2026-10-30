"""JEG-1230: the shared explicit-trade readout matches Compare, Find a trade and the league finder on the same deal."""
from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))
import build_v2_page  # noqa: E402
from tests.test_build_v2_page import INDEX  # noqa: E402


class TradeReadoutParityTest(unittest.TestCase):
    def test_parity_golden_and_edge_cases(self):
        result = subprocess.run(["node", str(ROOT / "tests/node/jeg1230_trade_readout_check.cjs")],
                                capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
        self.assertIn("checks passed", result.stdout)

    def test_page_loads_the_readout_after_its_dependencies(self):
        html = build_v2_page.build_v2_html(INDEX, '<div id="v2App"></div>')
        at = lambda name: html.index(f'<script src="v2/{name}"')
        self.assertLess(at("finder.js"), at("trade-readout.js"))
        self.assertLess(at("lineup-comparison.js"), at("trade-readout.js"))
        self.assertLess(at("trade-readout.js"), at("league.js"))
        self.assertLess(at("trade-readout.js"), at("v2.js"))


if __name__ == "__main__":
    unittest.main()
