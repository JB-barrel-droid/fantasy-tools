#!/usr/bin/env python3
"""Tests for scheduler slip measurement (JEG-137 R10).

These tests verify:
1. Slip calculation for scheduled runs (not manual/push)
2. Bounded-history maximum for fresh measurements
3. 360-minute fallback for stale/missing measurements
4. Exactly 30d boundary (not stale)
5. Effective deadline calculation
6. JSON state output (not CLI exit codes)
"""

from __future__ import annotations

import json
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path


class TestIsScheduledRun(unittest.TestCase):
    """Test event classification."""

    def test_schedule_event_is_scheduled(self):
        from pipelines.measure_scheduler_slip import is_scheduled_run
        self.assertTrue(is_scheduled_run("schedule"))

    def test_workflow_dispatch_is_not_scheduled(self):
        from pipelines.measure_scheduler_slip import is_scheduled_run
        self.assertFalse(is_scheduled_run("workflow_dispatch"))

    def test_push_is_not_scheduled(self):
        from pipelines.measure_scheduler_slip import is_scheduled_run
        self.assertFalse(is_scheduled_run("push"))


class TestParseCronExpression(unittest.TestCase):
    """Test cron parsing."""

    def test_daily_cron_parsing(self):
        from pipelines.measure_scheduler_slip import parse_cron_expression
        result = parse_cron_expression("30 11 * * *")
        self.assertEqual(result, {"minute": 30, "hour": 11, "day_of_week": None})

    def test_weekly_cron_parsing(self):
        from pipelines.measure_scheduler_slip import parse_cron_expression
        result = parse_cron_expression("0 11 * * 3")
        self.assertEqual(result, {"minute": 0, "hour": 11, "day_of_week": 3})

    def test_hourly_cron_parsing(self):
        # "*" hour is not a single value -> unparseable (ambiguous)
        from pipelines.measure_scheduler_slip import parse_cron_expression
        result = parse_cron_expression("0 * * * *")
        self.assertIsNone(result)

    def test_unsupported_cron_returns_none(self):
        from pipelines.measure_scheduler_slip import parse_cron_expression
        self.assertIsNone(parse_cron_expression("invalid"))
        self.assertIsNone(parse_cron_expression("*/15 * * * *"))


class TestGetIntendedCronTime(unittest.TestCase):
    """Test intended cron time calculation."""

    def test_daily_cron_intended_time(self):
        from pipelines.measure_scheduler_slip import get_intended_cron_time

        # Reference: run started at 11:45 UTC
        reference = datetime(2026, 10, 2, 11, 45, 0, tzinfo=timezone.utc)
        cron = "30 11 * * *"  # 11:30 UTC

        result = get_intended_cron_time(cron, reference)

        self.assertIsNotNone(result)
        self.assertEqual(result.hour, 11)
        self.assertEqual(result.minute, 30)
        # Should be previous day's 11:30 since 11:45 > 11:30
        self.assertEqual(result.day, 2)

    def test_weekly_cron_intended_time(self):
        from pipelines.measure_scheduler_slip import get_intended_cron_time

        # Reference: Thursday Oct 1, 2026 at 11:15 UTC
        reference = datetime(2026, 10, 1, 11, 15, 0, tzinfo=timezone.utc)
        cron = "0 11 * * 3"  # Wednesday 11:00 UTC

        result = get_intended_cron_time(cron, reference)

        self.assertIsNotNone(result)
        self.assertEqual(result.hour, 11)
        self.assertEqual(result.minute, 0)
        # Should be previous Wednesday Sep 30
        self.assertEqual(result.day, 30)
        self.assertEqual(result.month, 9)

    def test_invalid_cron_returns_none(self):
        from pipelines.measure_scheduler_slip import get_intended_cron_time

        reference = datetime(2026, 10, 2, 12, 0, 0, tzinfo=timezone.utc)
        cron = "invalid"

        result = get_intended_cron_time(cron, reference)

        self.assertIsNone(result)


class TestCalculateSlipMinutes(unittest.TestCase):
    """Test slip calculation."""

    def test_positive_slip(self):
        from pipelines.measure_scheduler_slip import calculate_slip_minutes

        actual = datetime(2026, 10, 2, 12, 0, 0, tzinfo=timezone.utc)
        intended = datetime(2026, 10, 2, 11, 30, 0, tzinfo=timezone.utc)

        result = calculate_slip_minutes(actual, intended)

        self.assertEqual(result, 30)

    def test_zero_slip(self):
        from pipelines.measure_scheduler_slip import calculate_slip_minutes

        actual = datetime(2026, 10, 2, 11, 30, 0, tzinfo=timezone.utc)
        intended = datetime(2026, 10, 2, 11, 30, 0, tzinfo=timezone.utc)

        result = calculate_slip_minutes(actual, intended)

        self.assertEqual(result, 0)

    def test_negative_becomes_zero(self):
        from pipelines.measure_scheduler_slip import calculate_slip_minutes

        # Run started slightly before cron
        actual = datetime(2026, 10, 2, 11, 28, 0, tzinfo=timezone.utc)
        intended = datetime(2026, 10, 2, 11, 30, 0, tzinfo=timezone.utc)

        result = calculate_slip_minutes(actual, intended)

        # Should be 0 (nonnegative)
        self.assertEqual(result, 0)

    def test_none_intended_returns_none(self):
        from pipelines.measure_scheduler_slip import calculate_slip_minutes

        actual = datetime(2026, 10, 2, 12, 0, 0, tzinfo=timezone.utc)

        result = calculate_slip_minutes(actual, None)

        self.assertIsNone(result)


class TestIsStale(unittest.TestCase):
    """Test stale detection."""

    def test_29_days_not_stale(self):
        from pipelines.measure_scheduler_slip import is_stale

        measurement_time = datetime(2026, 10, 2, 12, 0, 0, tzinfo=timezone.utc)
        check_time = datetime(2026, 10, 31, 12, 0, 0, tzinfo=timezone.utc)  # 29 days later

        result = is_stale(measurement_time, check_time)

        self.assertFalse(result)

    def test_30_days_not_stale(self):
        from pipelines.measure_scheduler_slip import is_stale

        measurement_time = datetime(2026, 10, 2, 12, 0, 0, tzinfo=timezone.utc)
        check_time = datetime(2026, 11, 1, 12, 0, 0, tzinfo=timezone.utc)  # Exactly 30 days later

        result = is_stale(measurement_time, check_time)

        # Exactly 30 days is NOT stale (boundary test)
        self.assertFalse(result)

    def test_31_days_is_stale(self):
        from pipelines.measure_scheduler_slip import is_stale

        measurement_time = datetime(2026, 10, 2, 12, 0, 0, tzinfo=timezone.utc)
        check_time = datetime(2026, 11, 2, 12, 0, 0, tzinfo=timezone.utc)  # 31 days later

        result = is_stale(measurement_time, check_time)

        self.assertTrue(result)


class TestProcessWorkflowRuns(unittest.TestCase):
    """Test workflow run processing."""

    def test_no_runs_returns_fallback(self):
        from pipelines.measure_scheduler_slip import process_workflow_runs

        result = process_workflow_runs([], "ESPN scrape to Supabase")

        self.assertIsNone(result["slip_minutes"])
        self.assertTrue(result["is_stale"])
        self.assertEqual(result["fallback_used"], 360)

    def test_manual_runs_excluded(self):
        from pipelines.measure_scheduler_slip import process_workflow_runs

        runs = [
            {
                "workflow_name": "ESPN scrape to Supabase",
                "run_started_at": "2026-10-02T11:35:00Z",
                "event": "workflow_dispatch",  # Manual trigger
                "run_id": 123,
            }
        ]

        result = process_workflow_runs(runs, "ESPN scrape to Supabase")

        # Should have no valid measurements (only manual runs)
        self.assertEqual(result["n_observations"], 0)
        self.assertIsNone(result["slip_minutes"])

    def test_scheduled_runs_included(self):
        from pipelines.measure_scheduler_slip import process_workflow_runs

        # Cron is 30 11 * * * (11:30 UTC), run started at 11:35 UTC = 5 min slip
        runs = [
            {
                "workflow_name": "ESPN scrape to Supabase",
                "run_started_at": "2026-10-02T11:35:00Z",
                "event": "schedule",
                "run_id": 123,
            }
        ]

        result = process_workflow_runs(runs, "ESPN scrape to Supabase")

        self.assertEqual(result["n_observations"], 1)
        self.assertEqual(result["slip_minutes"], 5)

    def test_uses_max_slip_from_recent_runs(self):
        from pipelines.measure_scheduler_slip import process_workflow_runs

        runs = [
            {
                "workflow_name": "ESPN scrape to Supabase",
                "run_started_at": "2026-10-02T11:35:00Z",  # 5 min slip
                "event": "schedule",
                "run_id": 123,
            },
            {
                "workflow_name": "ESPN scrape to Supabase",
                "run_started_at": "2026-10-01T11:40:00Z",  # 10 min slip
                "event": "schedule",
                "run_id": 122,
            },
        ]

        result = process_workflow_runs(runs, "ESPN scrape to Supabase")

        # Should use maximum slip
        self.assertEqual(result["slip_minutes"], 10)

    def test_stale_measurement_returns_fallback(self):
        from pipelines.measure_scheduler_slip import process_workflow_runs

        # Run from 31 days ago
        runs = [
            {
                "workflow_name": "ESPN scrape to Supabase",
                "run_started_at": "2026-09-01T11:35:00Z",  # 31 days ago
                "event": "schedule",
                "run_id": 100,
            }
        ]

        result = process_workflow_runs(runs, "ESPN scrape to Supabase")

        self.assertTrue(result["is_stale"])
        self.assertIsNone(result["slip_minutes"])
        self.assertEqual(result["fallback_used"], 360)


class TestComputeSchedulerSlip(unittest.TestCase):
    """Test full slip computation."""

    def test_computes_workflow_and_source_measurements(self):
        from pipelines.measure_scheduler_slip import compute_scheduler_slip

        history = [
            {
                "workflow_name": "ESPN scrape to Supabase",
                "run_started_at": "2026-10-02T11:35:00Z",
                "event": "schedule",
                "run_id": 123,
            },
            {
                "workflow_name": "CBS ROS scrape to Supabase",
                "run_started_at": "2026-10-02T11:10:00Z",
                "event": "schedule",
                "run_id": 124,
            },
        ]

        result = compute_scheduler_slip(history)

        self.assertIn("workflows", result)
        self.assertIn("sources", result)

        # Check workflow measurements
        self.assertIn("ESPN scrape to Supabase", result["workflows"])
        self.assertIn("CBS ROS scrape to Supabase", result["workflows"])

        # Check source mapping
        self.assertIn("espn", result["sources"])
        self.assertIn("cbsros", result["sources"])

    def test_output_includes_measurement_details(self):
        from pipelines.measure_scheduler_slip import compute_scheduler_slip

        history = []

        result = compute_scheduler_slip(history)

        self.assertIn("measurement_details", result)
        details = result["measurement_details"]
        self.assertEqual(details["max_history_runs"], 10)
        self.assertEqual(details["stale_threshold_days"], 30)
        self.assertEqual(details["default_fallback_minutes"], 360)


class TestEffectiveDeadline(unittest.TestCase):
    """Test effective deadline calculation."""

    def test_with_valid_slip(self):
        from pipelines.measure_scheduler_slip import calculate_effective_deadline

        # Publication deadline: Tuesday 2026-10-06 23:59 UTC
        deadline = datetime(2026, 10, 6, 23, 59, 0, tzinfo=timezone.utc)
        base_grace = 24 * 60  # 1 day in minutes
        slip = 30  # 30 minutes measured slip
        is_stale = False

        effective, reason = calculate_effective_deadline(deadline, base_grace, slip, is_stale)

        # Expected: deadline + base_grace + slip = 23:59 Tue + 24h + 30min = 00:29 Thu
        expected = deadline + timedelta(minutes=base_grace + slip)
        self.assertEqual(effective, expected)
        self.assertIn("slip(30min)", reason)

    def test_with_stale_uses_fallback(self):
        from pipelines.measure_scheduler_slip import calculate_effective_deadline

        deadline = datetime(2026, 10, 6, 23, 59, 0, tzinfo=timezone.utc)
        base_grace = 24 * 60
        slip = None  # No measurement
        is_stale = True

        effective, reason = calculate_effective_deadline(deadline, base_grace, slip, is_stale)

        # Should use fallback (360 minutes)
        expected = deadline + timedelta(minutes=base_grace + 360)
        self.assertEqual(effective, expected)
        self.assertIn("fallback(360min)", reason)
        self.assertIn("stale", reason)

    def test_with_no_measurement_uses_fallback(self):
        from pipelines.measure_scheduler_slip import calculate_effective_deadline

        deadline = datetime(2026, 10, 6, 23, 59, 0, tzinfo=timezone.utc)
        base_grace = 24 * 60
        slip = None
        is_stale = False

        effective, reason = calculate_effective_deadline(deadline, base_grace, slip, is_stale)

        expected = deadline + timedelta(minutes=base_grace + 360)
        self.assertEqual(effective, expected)
        self.assertIn("fallback(360min)", reason)


class TestGracePeriodDetermination(unittest.TestCase):
    """Test within-grace determination."""

    def test_within_grace_at_deadline_plus_360(self):
        # Fallback path: no valid slip measurement -> effective deadline is
        # publication deadline + base grace + 360min fallback, computed by
        # calculate_effective_deadline. is_within_grace then compares against it.
        from pipelines.measure_scheduler_slip import (
            calculate_effective_deadline, is_within_grace,
        )

        # Deadline + 360 minutes = exactly at grace (fallback, no measurement)
        deadline = datetime(2026, 10, 6, 12, 0, 0, tzinfo=timezone.utc)
        check_time = deadline + timedelta(minutes=360)
        base_grace = 0

        effective, _ = calculate_effective_deadline(deadline, base_grace, None, False)
        self.assertEqual(effective, deadline + timedelta(minutes=360))

        within, reason = is_within_grace(effective, check_time, base_grace, 0)
        self.assertTrue(within)

    def test_past_grace_at_deadline_plus_24h(self):
        from pipelines.measure_scheduler_slip import is_within_grace

        # Deadline + 24 hours = past 360 minute grace
        deadline = datetime(2026, 10, 6, 12, 0, 0, tzinfo=timezone.utc)
        check_time = deadline + timedelta(hours=24)
        base_grace = 0
        slip = 0

        within, reason = is_within_grace(deadline, check_time, base_grace, slip)

        self.assertFalse(within)
        self.assertIn("Past grace", reason)

    def test_slip_extends_grace(self):
        from pipelines.measure_scheduler_slip import is_within_grace

        # With 60 min slip, grace extends by 60 minutes
        deadline = datetime(2026, 10, 6, 12, 0, 0, tzinfo=timezone.utc)
        check_time = deadline + timedelta(minutes=400)  # 400 min past deadline
        base_grace = 0
        slip = 60  # 60 min slip extends grace

        within, reason = is_within_grace(deadline, check_time, base_grace, slip)

        # deadline + slip = 12:00 + 60min = 13:00
        # check_time = 12:00 + 400min = 18:40
        # So it's past grace
        self.assertFalse(within)


class TestJsonOutputStructure(unittest.TestCase):
    """Test JSON output structure (acceptance criteria: unit tests assert JSON state)."""

    def test_output_has_required_fields(self):
        from pipelines.measure_scheduler_slip import compute_scheduler_slip

        history = [
            {
                "workflow_name": "ESPN scrape to Supabase",
                "run_started_at": "2026-10-02T11:35:00Z",
                "event": "schedule",
                "run_id": 123,
            }
        ]

        result = compute_scheduler_slip(history)

        # Check top-level fields
        self.assertIn("generated_at", result)
        self.assertIn("workflows", result)
        self.assertIn("sources", result)
        self.assertIn("measurement_details", result)

        # Check workflow structure
        espn_workflow = result["workflows"]["ESPN scrape to Supabase"]
        self.assertIn("workflow_name", espn_workflow)
        self.assertIn("source", espn_workflow)
        self.assertIn("cron", espn_workflow)
        self.assertIn("slip_minutes", espn_workflow)
        self.assertIn("slip_reason", espn_workflow)
        self.assertIn("n_observations", espn_workflow)
        self.assertIn("is_stale", espn_workflow)
        self.assertIn("runs", espn_workflow)

    def test_source_mapping_includes_slip_info(self):
        from pipelines.measure_scheduler_slip import compute_scheduler_slip

        history = [
            {
                "workflow_name": "ESPN scrape to Supabase",
                "run_started_at": "2026-10-02T11:35:00Z",
                "event": "schedule",
                "run_id": 123,
            }
        ]

        result = compute_scheduler_slip(history)

        espn_source = result["sources"]["espn"]
        self.assertIn("slip_minutes", espn_source)
        self.assertIn("slip_reason", espn_source)
        self.assertIn("is_stale", espn_source)
        self.assertIn("fallback_used", espn_source)
        self.assertIn("n_observations", espn_source)
        self.assertIn("workflow", espn_source)


class TestAmbiguousCronAttribution(unittest.TestCase):
    """Test that ambiguous cron attribution is unknown, not fabricated."""

    def test_unknown_workflow_returns_none_slip(self):
        from pipelines.measure_scheduler_slip import process_workflow_runs

        runs = [
            {
                "workflow_name": "Unknown Workflow",
                "run_started_at": "2026-10-02T11:35:00Z",
                "event": "schedule",
                "run_id": 123,
            }
        ]

        result = process_workflow_runs(runs, "Unknown Workflow")

        # Should return None slip (unknown, not fabricated)
        self.assertIsNone(result["slip_minutes"])
        self.assertEqual(result["slip_reason"], "no_valid_measurements")

    def test_unmatched_cron_returns_none(self):
        from pipelines.measure_scheduler_slip import get_intended_cron_time

        # A workflow not in WORKFLOW_CRON_SCHEDULES
        reference = datetime(2026, 10, 2, 12, 0, 0, tzinfo=timezone.utc)

        # This should return None because "Unknown" is not in the schedules
        result = get_intended_cron_time("Unknown", reference)

        # When cron is not found, it returns None
        self.assertIsNone(result)


class TestStaleBoundary(unittest.TestCase):
    """Test the exactly 30d boundary (acceptance criteria)."""

    def test_30_days_old_is_not_stale(self):
        """Exactly 30 days old should NOT be stale."""
        from pipelines.measure_scheduler_slip import is_stale, process_workflow_runs

        # Create a run that's exactly 30 days old
        run_time = datetime.now(timezone.utc) - timedelta(days=30)

        runs = [
            {
                "workflow_name": "ESPN scrape to Supabase",
                "run_started_at": run_time.isoformat(),
                "event": "schedule",
                "run_id": 123,
            }
        ]

        result = process_workflow_runs(runs, "ESPN scrape to Supabase")

        # Should NOT be stale (exactly 30 days is the boundary)
        self.assertFalse(result["is_stale"])
        self.assertIsNotNone(result["slip_minutes"])


if __name__ == "__main__":
    unittest.main()
