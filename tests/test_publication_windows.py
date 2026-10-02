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


class TestCbsSchedule(unittest.TestCase):
    def test_cbs_behind_past_grace_is_red(self):
        # JEG-131 R4a gave CBS a verified Wednesday schedule (1-day grace).
        # Tuesday 2026-09-29 is 6 days past the expected Wednesday publish,
        # so a Week-3 vintage against current Week 4 missed its window (red).
        from pipelines.lib.publication_windows import get_publication_status
        status, reason = get_publication_status(
            source="cbs", vintage_week=3, current_week=4,
            check_date=date(2026, 9, 29),
        )
        self.assertEqual(status, "red")
        self.assertIn("MISSED_WINDOW", reason)

    def test_cbs_behind_within_grace_is_yellow(self):
        # Wednesday 2026-09-30 is the publish day itself: within the 1-day
        # grace period, so the Week-3 vintage is awaiting publication (yellow).
        from pipelines.lib.publication_windows import get_publication_status
        status, reason = get_publication_status(
            source="cbs", vintage_week=3, current_week=4,
            check_date=date(2026, 9, 30),
        )
        self.assertEqual(status, "yellow")
        self.assertIn("AWAITING_PUBLICATION", reason)

    def test_espn_behind_is_stale(self):
        # ESPN is a daily live reference with no weekly publication schedule
        # (publish_day=None): a behind vintage is stale, never red/yellow.
        # This preserves the original no-schedule branch the old CBS test covered.
        from pipelines.lib.publication_windows import get_publication_status
        status, reason = get_publication_status(
            source="espn", vintage_week=3, current_week=4,
            check_date=date(2026, 9, 29),
        )
        self.assertEqual(status, "stale")
        self.assertIn("No verified publication schedule", reason)


if __name__ == "__main__":
    unittest.main()
