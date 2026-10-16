"""JEG-534: the swap measurement on a hand-built season (tools/weekly_matchup_swaps.py)."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import weekly_matchup_swaps as wms  # noqa: E402


def season(bench_beats: bool) -> dict:
    """One QB season: 12 starters at 20 a week, then 12 bench players at 10. The first bench
    player outscores every starter in week 3 only when bench_beats is set."""
    players = {f"s{i}": {w: 20.0 for w in wms.WEEKS} for i in range(12)}
    players.update({f"b{i}": {w: 10.0 for w in wms.WEEKS} for i in range(12)})
    if bench_beats:
        players["b0"][3] = 30.0
    return {2024: {"QB": players, "RB": {}, "WR": {}, "TE": {}}}


class WeeklyMatchupSwaps(unittest.TestCase):
    def test_no_swaps_when_starters_always_project_higher(self):
        qb = wms.measure(season(False))["QB"]
        self.assertEqual(qb["swaps"], 0)
        self.assertEqual(qb["weeks_any"], 0)

    def test_one_bench_player_one_week_counts_once(self):
        qb = wms.measure(season(True))["QB"]
        self.assertEqual(qb["swaps"], wms.LOW_END)  # b0 beats each low-end starter in week 3
        self.assertEqual(qb["weeks_any"], 1)
        self.assertEqual(qb["pairs"], wms.BENCH * wms.LOW_END * len(wms.WEEKS))


if __name__ == "__main__":
    unittest.main()
