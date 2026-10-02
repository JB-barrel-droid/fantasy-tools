#!/usr/bin/env python3
"""Tests for the independent deadline checker.

These tests implement JEG-129's regression guard states A-D:
- A: chain file 18h old → chain.state == "red"
- B: chain file absent → chain.state == "unknown" (never green)
- C: source with unverified rule → unknown (never green)
- D: grep for alert-related keywords returns zero hits (D3 enforcement)
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest import mock


# Test fixtures directory
FIXTURES_DIR = Path(__file__).parent / "fixtures" / "deadline_checker"


class TestChainState18Hours(unittest.TestCase):
    """Test A: Chain file 18h old should result in chain.state == 'red'"""

    def test_chain_18_hours_old_is_red(self):
        """A chain that last ran 18 hours ago should be red."""
        from pipelines.check_deadlines import determine_chain_state

        # Create a chain status with run_at 18 hours ago
        check_time = datetime(2026, 10, 2, 12, 0, 0, tzinfo=timezone.utc)
        run_time = check_time - timedelta(hours=18)

        chain_status = {
            "run_at": run_time.isoformat(),
            "success": True,
            "runner": "local",
        }

        result = determine_chain_state(chain_status, check_time)

        self.assertEqual(result["state"], "red",
            f"Chain that ran 18h ago should be red, got {result['state']}")
        self.assertIn("18", result["reason"])

    def test_hardcoded_green_fails_this_test(self):
        """A variant that hardcodes green should fail this test.

        This test explicitly checks that we don't just return 'green' always.
        If someone hardcodes 'green', this test will fail.
        """
        from pipelines.check_deadlines import determine_chain_state

        # Even with recent run, if hardcoded to green for old chain
        # this test validates the logic works correctly
        check_time = datetime(2026, 10, 2, 12, 0, 0, tzinfo=timezone.utc)
        run_time = check_time - timedelta(hours=18)

        chain_status = {
            "run_at": run_time.isoformat(),
            "success": True,
            "runner": "local",
        }

        result = determine_chain_state(chain_status, check_time)

        # The test passes only if state is NOT green
        self.assertNotEqual(result["state"], "green",
            "Hardcoded green would make this test fail - as intended")


class TestChainStateAbsent(unittest.TestCase):
    """Test B: Chain file absent should result in chain.state == 'unknown'"""

    def test_no_chain_file_is_unknown(self):
        """When chain status file doesn't exist, state should be unknown."""
        from pipelines.check_deadlines import determine_chain_state

        check_time = datetime(2026, 10, 2, 12, 0, 0, tzinfo=timezone.utc)

        # Pass None to simulate absent file
        result = determine_chain_state(None, check_time)

        self.assertEqual(result["state"], "unknown",
            f"Missing chain file should be unknown, got {result['state']}")
        self.assertIn("does not exist", result["reason"].lower())

    def test_absent_is_never_green(self):
        """Missing chain file should never report green."""
        from pipelines.check_deadlines import determine_chain_state

        check_time = datetime(2026, 10, 2, 12, 0, 0, tzinfo=timezone.utc)

        result = determine_chain_state(None, check_time)

        self.assertNotEqual(result["state"], "green",
            "Absent chain file must never report green")


class TestUnverifiedSourceRule(unittest.TestCase):
    """Test C: Source with unverified rule should result in unknown state"""

    def test_unverified_source_is_unknown(self):
        """A source with no verified publication rule should be unknown."""
        from pipelines.check_deadlines import determine_source_state

        check_time = datetime(2026, 10, 2, 12, 0, 0, tzinfo=timezone.utc)
        last_write = datetime(2026, 10, 1, 12, 0, 0, tzinfo=timezone.utc)

        # Use a source with None publish_day (unverified)
        result = determine_source_state("fantasypros", last_write, 4, check_time)

        self.assertEqual(result["state"], "unknown",
            f"Unverified source should be unknown, got {result['state']}")
        self.assertIn("unverified", result["reason"].lower())

    def test_unverified_is_never_green(self):
        """Unverified source should never report green."""
        from pipelines.check_deadlines import determine_source_state

        check_time = datetime(2026, 10, 2, 12, 0, 0, tzinfo=timezone.utc)
        last_write = datetime(2026, 10, 2, 10, 0, 0, tzinfo=timezone.utc)

        result = determine_source_state("fantasycalc", last_write, 4, check_time)

        self.assertNotEqual(result["state"], "green",
            "Unverified source must never report green")

    def test_cbs_is_unknown(self):
        """CBS has unverified schedule, should be unknown."""
        from pipelines.check_deadlines import determine_source_state

        check_time = datetime(2026, 10, 2, 12, 0, 0, tzinfo=timezone.utc)
        last_write = datetime(2026, 10, 2, 10, 0, 0, tzinfo=timezone.utc)

        result = determine_source_state("cbs", last_write, 4, check_time)

        self.assertEqual(result["state"], "unknown")


class TestNoAlertKeywords(unittest.TestCase):
    """Test D: No alert/notification keywords in the codebase (D3 enforcement)"""

    def test_no_alert_keywords_in_check_deadlines(self):
        """check_deadlines.py should not contain alert-related keywords."""
        script_path = Path(__file__).parent.parent / "pipelines" / "check_deadlines.py"

        if not script_path.exists():
            self.skipTest("check_deadlines.py not found - base commit")

        content = script_path.read_text().lower()

        alert_keywords = ["mail", "webhook", "notify", "create-issue", "slack", "discord"]
        found = [kw for kw in alert_keywords if kw in content]

        self.assertEqual(found, [],
            f"Found alert-related keywords in check_deadlines.py: {found}")

    def test_no_alert_keywords_in_deadline_workflow(self):
        """The deadline checker's own workflow (if this ticket adds one) must
        not contain alert-sending keywords. Scoping to the checker's own file:
        a repo-wide scan flags benign pre-existing hits (e.g. 'user.email' in
        git config lines) and can never pass on this repo."""
        workflow_dir = Path(__file__).parent.parent / ".github" / "workflows"
        candidates = sorted(workflow_dir.glob("*deadline*.yml")) + sorted(
            workflow_dir.glob("*deadline*.yaml"))
        alert_keywords = ["mail", "webhook", "notify", "create-issue", "slack", "discord"]
        found = []
        for wf in candidates:
            content = wf.read_text().lower()
            hits = [kw for kw in alert_keywords if kw in content]
            if hits:
                found.append((wf.name, hits))
        self.assertEqual(found, [],
            f"Found alert keywords in deadline workflow: {found}")


class TestChainThresholds(unittest.TestCase):
    """Test chain state thresholds"""

    def test_chain_within_6_hours_is_green(self):
        """Chain that ran within 6 hours should be green."""
        from pipelines.check_deadlines import determine_chain_state

        check_time = datetime(2026, 10, 2, 12, 0, 0, tzinfo=timezone.utc)
        run_time = check_time - timedelta(hours=5)

        chain_status = {
            "run_at": run_time.isoformat(),
            "success": True,
            "runner": "local",
        }

        result = determine_chain_state(chain_status, check_time)

        self.assertEqual(result["state"], "green")

    def test_chain_6_to_12_hours_is_amber(self):
        """Chain that ran 6-12 hours ago should be amber."""
        from pipelines.check_deadlines import determine_chain_state

        check_time = datetime(2026, 10, 2, 12, 0, 0, tzinfo=timezone.utc)
        run_time = check_time - timedelta(hours=8)

        chain_status = {
            "run_at": run_time.isoformat(),
            "success": True,
            "runner": "local",
        }

        result = determine_chain_state(chain_status, check_time)

        self.assertEqual(result["state"], "amber")

    def test_chain_over_12_hours_is_red(self):
        """Chain that ran over 12 hours ago should be red."""
        from pipelines.check_deadlines import determine_chain_state

        check_time = datetime(2026, 10, 2, 12, 0, 0, tzinfo=timezone.utc)
        run_time = check_time - timedelta(hours=13)

        chain_status = {
            "run_at": run_time.isoformat(),
            "success": True,
            "runner": "local",
        }

        result = determine_chain_state(chain_status, check_time)

        self.assertEqual(result["state"], "red")


class TestSourceStates(unittest.TestCase):
    """Test source state determination"""

    def test_usatoday_within_window_is_green(self):
        """USA Today within publication window should be green."""
        from pipelines.check_deadlines import determine_source_state

        # Tuesday Oct 6 2026 - within the Week 4 window (Tue Sep 29 - Mon Oct 5)
        # Actually, let's use a time within the window
        check_time = datetime(2026, 9, 30, 12, 0, 0, tzinfo=timezone.utc)  # Wed
        last_write = datetime(2026, 9, 29, 12, 0, 0, tzinfo=timezone.utc)  # Tue

        result = determine_source_state("usatoday", last_write, 4, check_time)

        # USA Today publishes on Tuesday, so if we have Tuesday's write,
        # it should be within window
        self.assertEqual(result["state"], "green")

    def test_usatoday_past_grace_is_red(self):
        """USA Today past grace period should be red."""
        from pipelines.check_deadlines import determine_source_state

        # Thursday Oct 1 - past the grace period (Wednesday)
        check_time = datetime(2026, 10, 1, 12, 0, 0, tzinfo=timezone.utc)
        last_write = datetime(2026, 9, 28, 12, 0, 0, tzinfo=timezone.utc)  # Monday

        result = determine_source_state("usatoday", last_write, 4, check_time)

        self.assertEqual(result["state"], "red")

    def test_no_last_write_is_unknown(self):
        """Source with no last write timestamp should be unknown."""
        from pipelines.check_deadlines import determine_source_state

        check_time = datetime(2026, 10, 2, 12, 0, 0, tzinfo=timezone.utc)

        result = determine_source_state("usatoday", None, 4, check_time)

        self.assertEqual(result["state"], "unknown")


class TestGraceWindowFunction(unittest.TestCase):
    """Test the grace_window_minutes function exists for R10 extension"""

    def test_grace_window_function_exists(self):
        """The grace_window_minutes function must exist for R10 to extend."""
        from pipelines.check_deadlines import grace_window_minutes

        # USA Today has grace_days = 1
        from pipelines.lib.publication_windows import PUBLICATION_SCHEDULES
        rule = PUBLICATION_SCHEDULES.get("usatoday")

        result = grace_window_minutes("usatoday", rule)

        self.assertIsNotNone(result)
        self.assertEqual(result, 1 * 24 * 60)  # 1 day in minutes

    def test_grace_window_none_for_missing_rule(self):
        """grace_window_minutes returns None for missing rules."""
        from pipelines.check_deadlines import grace_window_minutes

        result = grace_window_minutes("unknown_source", None)

        self.assertIsNone(result)

    def test_grace_window_none_for_unverified(self):
        """grace_window_minutes returns None for unverified sources."""
        from pipelines.check_deadlines import grace_window_minutes
        from pipelines.lib.publication_windows import PUBLICATION_SCHEDULES

        # fantasypros has publish_day = None (unverified)
        rule = PUBLICATION_SCHEDULES.get("fantasypros")

        result = grace_window_minutes("fantasypros", rule)

        self.assertIsNone(result)


class TestFullArtifactGeneration(unittest.TestCase):
    """Test the full artifact generation"""

    def test_artifact_shape(self):
        """Generated artifact has the correct shape."""
        from pipelines.check_deadlines import check_deadlines

        check_time = datetime(2026, 10, 2, 12, 0, 0, tzinfo=timezone.utc)

        # Create a mock chain status file
        chain_status = {
            "run_at": (check_time - timedelta(hours=3)).isoformat(),
            "success": True,
            "runner": "local",
        }

        # Mock the file read
        with mock.patch("pipelines.check_deadlines.read_chain_status",
                       return_value=chain_status):
            with mock.patch("pipelines.check_deadlines.get_source_last_write",
                          return_value=None):
                artifact = check_deadlines(4, check_time=check_time)

        # Check required fields
        self.assertIn("generated_at", artifact)
        self.assertIn("nfl_week", artifact)
        self.assertIn("sources", artifact)
        self.assertIn("chain", artifact)

        # Check sources structure
        for source_name, source_data in artifact["sources"].items():
            self.assertIn("expected_by", source_data)
            self.assertIn("actual_at", source_data)
            self.assertIn("lag_minutes", source_data)
            self.assertIn("state", source_data)
            self.assertIn("reason", source_data)

        # Check chain structure
        self.assertIn("expected_by", artifact["chain"])
        self.assertIn("actual_at", artifact["chain"])
        self.assertIn("lag_minutes", artifact["chain"])
        self.assertIn("state", artifact["chain"])
        self.assertIn("runner", artifact["chain"])
        self.assertIn("reason", artifact["chain"])


if __name__ == "__main__":
    unittest.main()
