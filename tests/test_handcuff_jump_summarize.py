"""Unit tests for tools/handcuff_jump.py summarize() on synthetic rows (JEG-1167).

summarize() is pure: it reads only the keys of the row dicts it is handed, so
these tests build small rows by hand and check exact values. analyse() and
main() are deliberately not exercised here: they read the nflverse file.
"""
from __future__ import annotations

import os
import sys
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _sub in ("tools", "pipelines"):
    _p = os.path.join(REPO, _sub)
    if _p not in sys.path:
        sys.path.insert(0, _p)

import handcuff_jump as hj  # noqa: E402


def row(season=2020, team="AAA", rb1_sel_ppg=20.0, rb2_sel_ppg=10.0,
        with_lead=None, without=None, starter_line=10.0, waiver_line=5.0):
    return {"season": season, "team": team, "rb1_sel_ppg": rb1_sel_ppg,
            "rb2_sel_ppg": rb2_sel_ppg,
            "with_lead": list(with_lead) if with_lead else [],
            "without": list(without) if without else [],
            "starter_line": starter_line, "waiver_line": waiver_line}


class PooledTotalsTest(unittest.TestCase):
    """Pooled means and counts, and that an unpaired row still feeds them."""

    def setUp(self):
        self.rows = [
            # paired
            row(team="AAA", rb1_sel_ppg=20.0, with_lead=[4.0, 6.0], without=[12.0, 14.0]),
            # paired
            row(team="BBB", rb1_sel_ppg=18.0, with_lead=[2.0], without=[10.0]),
            # unpaired: no with_lead games -> excluded from paired, still pooled
            row(team="CCC", rb1_sel_ppg=16.0, with_lead=[], without=[8.0, 9.0]),
        ]

    def test_counts(self):
        s = hj.summarize(self.rows)
        self.assertEqual(s["team_seasons"], 3)
        self.assertEqual(s["games_with_lead"], 3)   # 2 + 1 + 0
        self.assertEqual(s["games_without_lead"], 5)  # 2 + 1 + 2

    def test_pooled_means_include_unpaired_row(self):
        s = hj.summarize(self.rows)
        # with_lead games: 4, 6, 2 -> mean 4.0
        self.assertAlmostEqual(s["rb2_ppg_with_lead"], 4.0)
        # without games: 12, 14, 10, 8, 9 -> 53/5 = 10.6 (row CCC counted)
        self.assertAlmostEqual(s["rb2_ppg_without_lead"], 10.6)

    def test_paired_backups_excludes_unpaired_row(self):
        s = hj.summarize(self.rows)
        self.assertEqual(s["paired_backups"], 2)

    def test_jumps(self):
        s = hj.summarize(self.rows)
        # A: 13.0 - 5.0 = 8.0 ; B: 10.0 - 2.0 = 8.0
        self.assertAlmostEqual(s["median_jump"], 8.0)
        self.assertAlmostEqual(s["mean_jump"], 8.0)

    def test_strict_starter_line(self):
        # A: 13.0 > 10.0 yes ; B: 10.0 > 10.0 no (strict)
        s = hj.summarize(self.rows)
        self.assertAlmostEqual(s["share_above_starter_line_when_lead_out"], 0.5)

    def test_strict_waiver_line(self):
        # A: 5.0 > 5.0 no (strict) ; B: 2.0 > 5.0 no
        s = hj.summarize(self.rows)
        self.assertAlmostEqual(s["share_above_waiver_line_with_lead"], 0.0)

    def test_promoted_and_lines(self):
        s = hj.summarize(self.rows)
        # mean(13/10, 10/10) = 1.15
        self.assertAlmostEqual(s["promoted_to_starter_line"], 1.15)
        self.assertAlmostEqual(s["mean_starter_line"], 10.0)
        self.assertAlmostEqual(s["mean_waiver_line"], 5.0)

    def test_three_rows_threshold_falls_back_to_lowest(self):
        # 3 rows in the season -> index min(11, 3-1)=2, the lowest rb1_sel_ppg,
        # so every paired row qualifies.
        s = hj.summarize(self.rows)
        self.assertEqual(s["top12_paired"], 2)
        self.assertAlmostEqual(s["top12_rb2_ppg_with"], 3.5)   # mean(5.0, 2.0)
        self.assertAlmostEqual(s["top12_rb2_ppg_without"], 11.5)  # mean(13.0, 10.0)
        self.assertAlmostEqual(s["top12_share_above_starter_line"], 0.5)
        self.assertAlmostEqual(s["top12_promoted_to_starter_line"], 1.15)


class FourteenRowsTest(unittest.TestCase):
    """14 rows in one season -> only paired rows behind a top-12 rb1 count."""

    def setUp(self):
        # rb1_sel_ppg 100, 99, ..., 87 (14 distinct values, all in season 2020).
        # Each paired: a = i, b = i + 20. starter_line 20.0, waiver_line 5.0.
        self.rows = [
            row(team=f"T{i:02d}", rb1_sel_ppg=float(100 - i), rb2_sel_ppg=float(i),
                with_lead=[float(i)], without=[float(i + 20)],
                starter_line=20.0, waiver_line=5.0)
            for i in range(14)
        ]

    def test_threshold_is_twelfth_highest(self):
        # sorted desc [100..87], index min(11, 13) = 11 -> 89.0; rb1 >= 89 -> i 0..11
        s = hj.summarize(self.rows)
        self.assertEqual(s["team_seasons"], 14)
        self.assertEqual(s["paired_backups"], 14)
        self.assertEqual(s["top12_paired"], 12)

    def test_all_paired_jumps(self):
        s = hj.summarize(self.rows)
        self.assertAlmostEqual(s["median_jump"], 20.0)
        self.assertAlmostEqual(s["mean_jump"], 20.0)

    def test_shares_over_all_paired(self):
        s = hj.summarize(self.rows)
        # b = i + 20 > 20 -> i = 1..13 -> 13/14
        self.assertAlmostEqual(s["share_above_starter_line_when_lead_out"], 13 / 14)
        # a = i > 5 -> i = 6..13 -> 8/14
        self.assertAlmostEqual(s["share_above_waiver_line_with_lead"], 8 / 14)

    def test_top12_aggregates(self):
        s = hj.summarize(self.rows)
        # top12 rows are i = 0..11
        self.assertAlmostEqual(s["top12_rb2_ppg_with"], 5.5)      # mean(0..11)
        self.assertAlmostEqual(s["top12_rb2_ppg_without"], 25.5)  # mean(20..31)
        self.assertAlmostEqual(s["top12_share_above_starter_line"], 11 / 12)
        self.assertAlmostEqual(s["top12_promoted_to_starter_line"], 1.275)  # 25.5/20

    def test_promoted_and_lines(self):
        s = hj.summarize(self.rows)
        self.assertAlmostEqual(s["promoted_to_starter_line"], 1.325)  # 26.5/20
        self.assertAlmostEqual(s["mean_starter_line"], 20.0)
        self.assertAlmostEqual(s["mean_waiver_line"], 5.0)


class SeasonScopedThresholdTest(unittest.TestCase):
    """The top-12 threshold is computed within a season, not across rows."""

    def setUp(self):
        # 2020: 14 rows, threshold = 12th highest = 89.0 -> 12 paired qualify.
        self.rows = [
            row(season=2020, team=f"T{i:02d}", rb1_sel_ppg=float(100 - i),
                rb2_sel_ppg=float(i), with_lead=[float(i)],
                without=[float(i + 20)], starter_line=20.0, waiver_line=5.0)
            for i in range(14)
        ]
        # 2021: 3 rows, threshold falls back to the lowest (30.0) -> all 3 qualify.
        self.rows += [
            row(season=2021, team=f"U{i}", rb1_sel_ppg=float(v), rb2_sel_ppg=float(i),
                with_lead=[float(i)], without=[float(i + 5)],
                starter_line=20.0, waiver_line=5.0)
            for i, v in enumerate((50, 40, 30))
        ]

    def test_threshold_is_per_season(self):
        s = hj.summarize(self.rows)
        self.assertEqual(s["team_seasons"], 17)
        self.assertEqual(s["paired_backups"], 17)
        self.assertEqual(s["top12_paired"], 12 + 3)


if __name__ == "__main__":
    unittest.main()
