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


if __name__ == "__main__":
    unittest.main()
