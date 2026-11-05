"""JEG-1479: week history reads pull timestamps on the New York clock.

The FantasyCalc writer labels a pull with the content week on the New York
calendar. build_week_history.week_of_day sliced the UTC date off the
timestamp instead, so the pull saved 2026-11-03T03:05:25Z (Monday Nov 2,
22:05 ET, week column 8) read as week 9. evidence_week failed closed
("fantasycalc: week column 8 but pulled in week 9") and the chain's week
history capture failed on every run from the Week 8 -> 9 flip on.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))

import build_week_history as H  # noqa: E402


class PullClockTest(unittest.TestCase):
    def test_monday_evening_et_pull_is_the_old_week(self):
        # The exact production row (Supabase source_trade_values,
        # bake fcwk8_2026-10-30... series, pulled_at as PostgREST returns it).
        for stamp in ("2026-11-03T03:05:25+00:00", "2026-11-03 03:05:25+00",
                      "2026-11-03T03:05:25Z"):
            with self.subTest(stamp=stamp):
                self.assertEqual(H.week_of_day(stamp), 8)

    def test_fantasycalc_week_8_pull_after_utc_midnight_is_accepted(self):
        entry = {"source": "fantasycalc", "week_evidence": {
            "rule": "week_column_pull", "week_column": 8,
            "pulled_at": "2026-11-03 03:05:25+00"}}
        self.assertEqual(H.evidence_week(entry), 8)

    def test_tuesday_et_pull_is_the_new_week(self):
        self.assertEqual(H.week_of_day("2026-11-03T10:05:34+00:00"), 9)
        entry = {"source": "fantasycalc", "week_evidence": {
            "rule": "week_column_pull", "week_column": 8,
            "pulled_at": "2026-11-03T10:05:34+00:00"}}
        with self.assertRaises(H.HistoryError):
            H.evidence_week(entry)  # still fails closed on a real mislabel

    def test_plain_dates_unchanged(self):
        self.assertEqual(H.week_of_day("2026-11-02"), 8)
        self.assertEqual(H.week_of_day("2026-11-03"), 9)
        self.assertIsNone(H.week_of_day(""))
        self.assertIsNone(H.week_of_day("not a date"))


if __name__ == "__main__":
    unittest.main()
