"""JEG-1150: the QB miss_rate in the bench-seat discount, pinned in both twins.

The rate lives twice: pipelines/lib/roster_convention.py (_BENCH_MISS_RATE)
and the JEG-1121 stable block in app/trade-value-chart/assets/value-model.js
(VORP_MISS). A change to one without the other splits the site from the
Python reference, so the parity test fails first. The tier test pins the rate
Jeremy picked through the seat count it produces.
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "pipelines"))

from lib import roster_convention as rc  # noqa: E402
from lib.roster_convention import vorp_bench_allocate  # noqa: E402

JS = REPO / "app" / "trade-value-chart" / "assets" / "value-model.js"

# JEG-1150 option C (Jeremy's pick pending, 2026-10-29): QB 0.12 -> 0.15.
EXPECTED_QB_MISS = 0.15
# 12 teams, 1 QB: QB backups come in blocks of t1 = round(2 x c x 12),
# c = 1/17 + miss_rate. 0.12 gives t1 = 4; 0.15 gives 5.
EXPECTED_QB_T1 = 5


def js_miss_rates() -> dict[str, float]:
    m = re.search(r"var VORP_MISS = \{([^}]*)\}", JS.read_text())
    assert m, "VORP_MISS not found in value-model.js"
    return {k: float(v) for k, v in re.findall(r"(\w+):\s*([0-9.]+)", m.group(1))}


class TestQbMissRate(unittest.TestCase):
    def test_python_and_js_rates_match(self):
        self.assertEqual(js_miss_rates(), rc._BENCH_MISS_RATE)

    def test_qb_rate_is_the_picked_value(self):
        self.assertEqual(rc._BENCH_MISS_RATE["QB"], EXPECTED_QB_MISS)
        self.assertEqual(js_miss_rates()["QB"], EXPECTED_QB_MISS)

    def test_qb_backups_fill_in_blocks_of_t1(self):
        """Only QB and TE compete (12 starters each, 12 teams). Equal PPG within
        each position, so the QB tier boundary alone decides the split of 9
        seats: QB takes its first tier (t1 seats) ahead of TE's first tier,
        then TE's first tier beats the rest of QB."""
        teams = 12
        starters = {"QB": 12, "RB": 0, "WR": 0, "TE": 12, "K": 0, "DEF": 0}
        remaining = {"QB": [f"qb{i}" for i in range(20)],
                     "TE": [f"te{i}" for i in range(20)]}
        scores = {**{k: 18.0 for k in remaining["QB"]},
                  **{k: 10.0 for k in remaining["TE"]}}
        slots = {"QB": 1, "RB": 2, "WR": 2, "TE": 1, "K": 1, "DEF": 1}
        counts = vorp_bench_allocate(starters, remaining, scores, teams, 9, slots, False)
        self.assertEqual(counts["QB"], EXPECTED_QB_T1)
        self.assertEqual(counts["TE"], 9 - EXPECTED_QB_T1)


if __name__ == "__main__":
    unittest.main()
