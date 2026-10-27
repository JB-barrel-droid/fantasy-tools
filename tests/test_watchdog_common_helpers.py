#!/usr/bin/env python3
"""Unit tests for the ops/watchdog/_common.py file-age and run-log helpers.

Covers age_days / is_today (fixed epoch mtimes, explicit fixed `now`) and
todays_run_lines / run_failed_time (fixed `day`). Stdlib unittest; hermetic.
The real clock is never read: every call passes an explicit aware `now` or
`day`, so the assertions are deterministic. classify_run_line's own cases
live in tests/test_trade_chart_pullers.py and are not duplicated here.
"""
import os
import sys
import tempfile
import unittest
from datetime import date, datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "..", "ops", "watchdog"))
from _common import CT, age_days, is_today, todays_run_lines, run_failed_time

DAY = date(2026, 10, 20)          # a Tuesday; CT is CDT (UTC-5) that week
STAMP = "2026-10-20"


class _TempFileMixin(unittest.TestCase):
    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._dir.cleanup)

    def path(self, name="f.txt"):
        return os.path.join(self._dir.name, name)

    def write(self, text, name="log.txt"):
        p = self.path(name)
        with open(p, "w") as f:
            f.write(text)
        return p

    def set_mtime(self, path, dt):
        """Set mtime to an aware datetime's epoch (deterministic, fixed)."""
        os.utime(path, (dt.timestamp(), dt.timestamp()))


class AgeDaysTests(_TempFileMixin):
    def test_missing_file_is_none(self):
        self.assertIsNone(age_days(self.path("nope.txt"),
                                   now=datetime(2026, 10, 20, 12, tzinfo=CT)))

    def test_fractional_age_in_days(self):
        p = self.write("x", name="aged.txt")
        self.set_mtime(p, datetime(2026, 10, 20, 0, 0, tzinfo=CT))
        now = datetime(2026, 10, 20, 12, 0, tzinfo=CT)  # 12h later
        self.assertAlmostEqual(age_days(p, now=now), 0.5, places=6)

    def test_age_crosses_midnight_ct(self):
        p = self.write("x", name="aged2.txt")
        # 11:30 PM CT on the 20th; now 12:30 AM CT on the 21st = 1h.
        self.set_mtime(p, datetime(2026, 10, 20, 23, 30, tzinfo=CT))
        now = datetime(2026, 10, 21, 0, 30, tzinfo=CT)
        self.assertAlmostEqual(age_days(p, now=now), 1.0 / 24.0, places=6)


class IsTodayTests(_TempFileMixin):
    def test_missing_file_is_false(self):
        self.assertFalse(is_today(self.path("nope.txt"),
                                  now=datetime(2026, 10, 20, 12, tzinfo=CT)))

    def test_same_ct_day_is_true(self):
        p = self.write("x", name="today.txt")
        self.set_mtime(p, datetime(2026, 10, 20, 23, 30, tzinfo=CT))
        now = datetime(2026, 10, 20, 23, 45, tzinfo=CT)
        self.assertTrue(is_today(p, now=now))

    def test_ct_date_boundary_is_false(self):
        # 11:30 PM CT on the 20th vs 12:30 AM CT on the 21st: next day.
        p = self.write("x", name="boundary.txt")
        self.set_mtime(p, datetime(2026, 10, 20, 23, 30, tzinfo=CT))
        now = datetime(2026, 10, 21, 0, 30, tzinfo=CT)
        self.assertFalse(is_today(p, now=now))


class TodaysRunLinesTests(_TempFileMixin):
    def test_missing_file_is_no_log(self):
        self.assertEqual(todays_run_lines(self.path("nope.log"), day=DAY),
                         ("no-log", []))

    def test_only_other_day_lines_is_did_not_run(self):
        p = self.write("2026-10-19 06:05 | OK | detail\n")
        self.assertEqual(todays_run_lines(p, day=DAY), ("did-not-run", []))

    def test_failed_then_ok_same_day_is_ok(self):
        p = self.write(
            "2026-10-20 06:05 | FAILED | boom\n"
            "2026-10-20 06:20 | OK | recovered\n")
        self.assertEqual(todays_run_lines(p, day=DAY), ("ok", [
            "2026-10-20 06:05 | FAILED | boom\n",
            "2026-10-20 06:20 | OK | recovered\n",
        ]))

    def test_failed_only_is_failed(self):
        p = self.write("2026-10-20 06:05 | FAILED | boom\n")
        self.assertEqual(todays_run_lines(p, day=DAY), ("failed", [
            "2026-10-20 06:05 | FAILED | boom\n"]))

    def test_unchanged_only_is_unchanged(self):
        p = self.write("2026-10-20 06:05 | OK | no update\n")
        self.assertEqual(todays_run_lines(p, day=DAY), ("unchanged", [
            "2026-10-20 06:05 | OK | no update\n"]))

    def test_other_day_lines_excluded_from_result(self):
        p = self.write(
            "2026-10-19 06:05 | FAILED | yesterday\n"
            "2026-10-20 06:05 | OK | detail\n"
            "2026-10-21 06:05 | FAILED | tomorrow\n")
        classified, lines = todays_run_lines(p, day=DAY)
        self.assertEqual(classified, "ok")
        self.assertEqual(lines, ["2026-10-20 06:05 | OK | detail\n"])


class RunFailedTimeTests(_TempFileMixin):
    def test_latest_failed_stamp_of_day(self):
        p = self.write(
            "2026-10-20 06:05 | FAILED | first\n"
            "2026-10-20 09:40 | OK | recovered\n"
            "2026-10-20 18:15 | FAILED | second\n")
        got = run_failed_time(p, day=DAY)
        self.assertEqual(got, datetime(2026, 10, 20, 18, 15, tzinfo=CT))
        self.assertEqual(got.utcoffset(), timedelta(hours=-5))

    def test_none_when_no_failed(self):
        p = self.write("2026-10-20 06:05 | OK | detail\n")
        self.assertIsNone(run_failed_time(p, day=DAY))

    def test_none_when_failed_only_on_other_day(self):
        p = self.write("2026-10-19 06:05 | FAILED | yesterday\n")
        self.assertIsNone(run_failed_time(p, day=DAY))

    def test_missing_file_is_none(self):
        self.assertIsNone(run_failed_time(self.path("nope.log"), day=DAY))


if __name__ == "__main__":
    unittest.main()
