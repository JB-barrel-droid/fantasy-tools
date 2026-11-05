"""JEG-1479: a FantasyCalc pull on Monday evening ET is accepted on either clock.

A pull on Monday evening ET is already Tuesday in UTC, the day the content
week flips. The FantasyCalc writer has labelled such pulls on both clocks:
2026-10-27T01:05Z (Mon Oct 26 21:05 ET) as week 8, which is the UTC week, and
2026-11-03T03:05Z (Mon Nov 2 22:05 ET) as week 8, which is the New York week.
build_week_history.evidence_week checked only the UTC week, raised
"fantasycalc: week column 8 but pulled in week 9", and the chain's week
history capture failed on every run after the Week 8 -> 9 flip. Without
Week 9 history the engine and the Python reference disagreed on all seven
sources, every source was held, and the board stayed on Week 8.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))

import build_week_history as H  # noqa: E402


def _fc(week, pulled_at):
    return {"source": "fantasycalc", "week_evidence": {
        "rule": "week_column_pull", "week_column": week, "pulled_at": pulled_at}}


class FantasyCalcPullClockTest(unittest.TestCase):
    def test_new_york_labelled_monday_night_pull(self):
        # The production row that blocked Week 9 (bake fcwk8_2026-11-03t0305_v1),
        # in the shapes PostgREST and the snapshot files carry.
        for stamp in ("2026-11-03 03:05:25+00", "2026-11-03T03:05:25+00:00",
                      "2026-11-03T03:05:25Z"):
            with self.subTest(stamp=stamp):
                self.assertEqual(H.evidence_week(_fc(8, stamp)), 8)

    def test_utc_labelled_monday_night_pull_still_accepted(self):
        # bake fcwk8_2026-10-27t0105_v1: labelled on the UTC calendar.
        self.assertEqual(H.evidence_week(_fc(8, "2026-10-27 01:05:23+00")), 8)

    def test_ordinary_pulls_unchanged(self):
        self.assertEqual(H.evidence_week(_fc(9, "2026-11-03 10:05:34+00")), 9)
        self.assertEqual(H.evidence_week(_fc(8, "2026-11-02 13:17:28+00")), 8)

    def test_real_mislabels_still_fail_closed(self):
        for week, stamp in ((8, "2026-11-03 10:05:34+00"),   # Tuesday morning ET, labelled 8
                            (9, "2026-11-02 13:17:28+00"),   # Monday midday, labelled 9
                            (7, "2026-11-03 03:05:25+00"),   # neither clock says 7
                            (0, "2026-11-03 03:05:25+00")):
            with self.subTest(week=week, stamp=stamp), self.assertRaises(H.HistoryError):
                H.evidence_week(_fc(week, stamp))

    def test_other_rules_keep_the_utc_date(self):
        self.assertEqual(H.week_of_day("2026-11-03 03:05:25+00"), 9)
        self.assertEqual(H.week_of_day("2026-11-02"), 8)


if __name__ == "__main__":
    unittest.main()
