"""GAP-CBSROS-8T-NO-QB: the browser's live CBS ROS two-tier path must price
quarterbacks at 8 teams, matching the chain-built CBS ROS section.

Root cause (2026-10-08): on the 2026-10-02 CBS ROS snapshot the 8-team QB
pool is so flat that the bench rate is negative at the 0.15 bench share (the
feasible window starts at ~0.160). The leg builders step UP to the lowest
feasible share (JEG-74), so the section priced every QB; the browser's
TwoTier.calibratePositionFeasible only searched DOWN, so it withheld the
whole position and CBS ROS showed no QB at any 8-team setup.

Negative-tested: on origin/main's curve-widget.js every *_8 combo reports QB
withheld and the section-pool comparison prices 0 of 62 QBs (both tests
below fail).
"""
from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / "tests" / "cbsros_live_section_harness.js"
COMBOS = [f"{s}_{t}" for s in ("full", "half", "standard") for t in (8, 10, 12, 14)]
# The section stores values rounded to 0.1 and natives rounded to 0.01; the
# observed residual with the leg's own pool is <= 0.2. A wrong share, pool
# or pie errs by whole points.
TOL = 0.25


def run_harness(mode: str) -> dict:
    out = subprocess.run(["node", str(HARNESS), mode], cwd=ROOT, capture_output=True,
                         text=True, timeout=120, check=True)
    return json.loads(out.stdout)


class CbsRosLivePricesEveryPosition(unittest.TestCase):
    def test_browser_pool_withholds_no_position(self):
        result = run_harness("browser-pool")
        for combo in COMBOS:
            with self.subTest(combo=combo):
                self.assertEqual(result[combo]["withheld"], [],
                                 f"{combo}: live CBS ROS withheld {result[combo]['withheld']}")
                qb = result[combo]["stats"]["QB"]
                self.assertGreater(qb["n"], 0, f"{combo}: no QB priced live")
                self.assertGreater(qb["top"]["live"], 0)

    def test_live_matches_section_on_leg_pool(self):
        # Same player set as the leg (identity-resolved), so any gap is the
        # calibration math: 8-team QB must match the section like every
        # other cell.
        result = run_harness("section-pool")
        for combo in COMBOS:
            for pos, stats in result[combo]["stats"].items():
                with self.subTest(combo=combo, pos=pos):
                    self.assertEqual(stats["n"], stats["nSection"],
                                     f"{combo} {pos}: {stats['n']} of {stats['nSection']} section players priced live")
                    self.assertLessEqual(stats["maxErr"], TOL,
                                         f"{combo} {pos}: max |live - section| {stats['maxErr']:.3f}")


if __name__ == "__main__":
    unittest.main()
