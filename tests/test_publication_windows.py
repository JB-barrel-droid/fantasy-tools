#!/usr/bin/env python3
"""Tests for source-specific publication windows."""

from __future__ import annotations

import unittest
from datetime import date


class TestUsaTodaySchedule(unittest.TestCase):
    def test_current_week_is_ok(self):
        from pipelines.lib.publication_windows import get_publication_status
        status, _ = get_publication_status(
            source="usatoday", vintage_week=4, current_week=4,
            check_date=date(2026, 9, 29),
        )
        self.assertEqual(status, "ok")

    def test_tuesday_within_window_is_yellow(self):
        from pipelines.lib.publication_windows import get_publication_status
        status, reason = get_publication_status(
            source="usatoday", vintage_week=3, current_week=4,
            check_date=date(2026, 9, 29),
        )
        self.assertEqual(status, "yellow")
        self.assertIn("AWAITING_PUBLICATION", reason)

    def test_thursday_missed_is_red(self):
        from pipelines.lib.publication_windows import get_publication_status
        status, reason = get_publication_status(
            source="usatoday", vintage_week=3, current_week=4,
            check_date=date(2026, 10, 1),
        )
        self.assertEqual(status, "red")
        self.assertIn("MISSED_WINDOW", reason)


class TestCbsUnknown(unittest.TestCase):
    def test_cbs_behind_is_stale(self):
        from pipelines.lib.publication_windows import get_publication_status
        status, reason = get_publication_status(
            source="cbs", vintage_week=3, current_week=4,
            check_date=date(2026, 9, 29),
        )
        self.assertEqual(status, "stale")
        self.assertIn("No verified publication schedule", reason)


class TestFantasyProsUnknown(unittest.TestCase):
    """JEG-187: FantasyPros has n_observations=0 -- publish_day=None.

    The pre-fix code (JEG-131 R4a) gave FantasyPros publish_day=1 (Tuesday)
    based on industry pattern. That violated the verified-not-assumed
    contract that JEG-179 already established for CBS. This test pins the
    strict branch: a behind vintage is stale, never red/yellow. The test
    fails on the pre-fix code (status="red") and passes on the post-fix
    code (status="stale").
    """

    def test_fantasypros_behind_is_stale(self):
        from pipelines.lib.publication_windows import get_publication_status
        status, reason = get_publication_status(
            source="fantasypros", vintage_week=3, current_week=4,
            check_date=date(2026, 9, 29),
        )
        self.assertEqual(status, "stale")
        self.assertIn("No verified publication schedule", reason)

    def test_fantasypros_one_week_behind_at_monday_is_stale(self):
        # Mirrors VerifyImportHealthTest.test_any_non_ok_source_fails_the_gate:
        # 2026-09-15 (Week 2) at current Week 3 on Monday 2026-09-21. With
        # publish_day=1 (Tuesday) the pre-fix code returned "red"
        # (6 days past Tuesday, past the 1-day grace). Post-fix (publish_day=None)
        # returns "stale".
        from pipelines.lib.publication_windows import get_publication_status
        status, reason = get_publication_status(
            source="fantasypros", vintage_week=2, current_week=3,
            check_date=date(2026, 9, 21),
        )
        self.assertEqual(status, "stale")
        self.assertIn("No verified publication schedule", reason)


class TestFantasyCalcUnknown(unittest.TestCase):
    """JEG-187: FantasyCalc treated as unverified per R4.

    The pre-fix code (JEG-131 R4a) claimed n_observations=3 with publish_day=1
    (Tuesday). The repo's gitignored data/raw/sources/fantasycalc/ does not
    corroborate a weekly cadence, and the gap-analysis section-4 audit lists
    FantasyCalc as an "undefined" freshness limit. Per R4 (verified-not-assumed)
    a source without a corroborated schedule reports stale. This test pins
    the strict branch and fails on the pre-fix code (status="red") while
    passing on the post-fix code (status="stale").
    """

    def test_fantasycalc_behind_is_stale(self):
        from pipelines.lib.publication_windows import get_publication_status
        status, reason = get_publication_status(
            source="fantasycalc", vintage_week=3, current_week=4,
            check_date=date(2026, 9, 29),
        )
        self.assertEqual(status, "stale")
        self.assertIn("No verified publication schedule", reason)

    def test_fantasycalc_one_week_behind_at_monday_is_stale(self):
        # Mirrors VerifyImportHealthTest.test_week2_vintage_stale_with_nfl_week_3:
        # Week 2 at current Week 3 on Monday. With publish_day=1 (Tuesday) the
        # pre-fix code returned "red". Post-fix returns "stale".
        from pipelines.lib.publication_windows import get_publication_status
        status, reason = get_publication_status(
            source="fantasycalc", vintage_week=2, current_week=3,
            check_date=date(2026, 9, 21),
        )
        self.assertEqual(status, "stale")
        self.assertIn("No verified publication schedule", reason)


if __name__ == "__main__":
    unittest.main()
