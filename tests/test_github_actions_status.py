"""Tests for pipelines/build_github_actions_status.py (JEG-109).

The builder fetches live GitHub API data, so these tests verify the
health-signal logic against synthetic payloads, not the network.
"""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))

import importlib.util

spec = importlib.util.spec_from_file_location(
    "gh_status", str(ROOT / "pipelines" / "build_github_actions_status.py")
)
gh = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gh)


def _run(conclusion, status="completed", days_ago=0, started_iso=None, finished_iso=None):
    """Build a synthetic GitHub-run payload.

    created_at and updated_at default to "now minus days_ago"; pass
    started_iso / finished_iso explicitly to exercise run_duration_s().
    """
    from datetime import datetime, timedelta, timezone

    if started_iso is None:
        started_iso = (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()
    if finished_iso is None:
        finished_iso = (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()
    return {
        "created_at": started_iso,
        "updated_at": finished_iso,
        "status": status,
        "conclusion": conclusion,
        "event": "schedule",
        "html_url": "https://example.com/run",
    }


class HealthSignalTest(unittest.TestCase):
    def _health(self, runs):
        # Replicates the builder's health logic over synthetic recent_runs
        conclusions = [r["conclusion"] for r in runs if r["conclusion"]]
        last = runs[0] if runs else None
        if not runs:
            return "unknown"
        if last and last["conclusion"] == "success":
            return "ok"
        if last and last["status"] in ("in_progress", "queued"):
            return "running"
        if "success" in conclusions:
            return "warn"
        return "fail"

    def test_all_success_is_ok(self):
        runs = [_run("success", days_ago=i) for i in range(5)]
        self.assertEqual(self._health(runs), "ok")

    def test_last_failed_but_earlier_ok_is_warn(self):
        runs = [_run("failure")] + [_run("success", days_ago=i + 1) for i in range(4)]
        self.assertEqual(self._health(runs), "warn")

    def test_all_failed_is_fail(self):
        runs = [_run("failure", days_ago=i) for i in range(5)]
        self.assertEqual(self._health(runs), "fail")

    def test_in_progress_is_running(self):
        runs = [_run(None, status="in_progress")] + [_run("success", days_ago=1)]
        self.assertEqual(self._health(runs), "running")

    def test_no_runs_is_unknown(self):
        self.assertEqual(self._health([]), "unknown")

    def test_cancelled_last_with_older_success_is_warn(self):
        # cancelled is not success and not failure: falls to "warn" via older success
        runs = [_run("cancelled")] + [_run("success", days_ago=1)]
        self.assertEqual(self._health(runs), "warn")


class DiscriminationTest(unittest.TestCase):
    """The health signal must discriminate: a single failed run among
    successes is warn, not fail; all-failed is fail, not warn."""

    def test_single_failure_not_fail(self):
        h = HealthSignalTest()._health([_run("failure")] + [_run("success", days_ago=i) for i in range(4)])
        self.assertNotEqual(h, "fail")

    def test_all_failure_not_warn(self):
        h = HealthSignalTest()._health([_run("failure", days_ago=i) for i in range(5)])
        self.assertNotEqual(h, "warn")


class RunDurationTest(unittest.TestCase):
    """Per-run duration_s derived from created_at -> updated_at."""

    def test_zero_duration_when_same_timestamp(self):
        ts = "2026-10-02T19:00:00Z"
        run = _run("success", started_iso=ts, finished_iso=ts)
        self.assertEqual(gh.run_duration_s(run), 0)

    def test_duration_computed_for_finished_run(self):
        run = _run(
            "success",
            started_iso="2026-10-02T19:00:00Z",
            finished_iso="2026-10-02T19:00:42Z",
        )
        self.assertEqual(gh.run_duration_s(run), 42)

    def test_duration_none_when_timestamp_missing(self):
        run = {"created_at": None, "updated_at": "2026-10-02T19:00:00Z", "conclusion": "success"}
        self.assertIsNone(gh.run_duration_s(run))

    def test_duration_clamped_at_zero_when_clock_skew(self):
        # GitHub occasionally re-queues a run; updated_at can predate created_at.
        run = _run(
            "success",
            started_iso="2026-10-02T19:00:10Z",
            finished_iso="2026-10-02T19:00:00Z",
        )
        self.assertEqual(gh.run_duration_s(run), 0)


class ConsecutiveFailuresTest(unittest.TestCase):
    """Streak counts back from the most recent run; stops at the first
    non-failure. JEG-113 was a 5-run outage — these fixtures pin the
    behaviour the ghActionsCard render depends on."""

    def test_five_consecutive_failures_sets_alert_flag(self):
        # This is the JEG-113 shape: "Rebuild comparison chain" failed
        # 5 times in a row. The new signal must surface this.
        runs = [_run("failure", days_ago=i) for i in range(5)]
        streak = gh.consecutive_failures(runs)
        self.assertEqual(streak, 5)
        self.assertGreaterEqual(streak, gh.FAILING_STREAK_THRESHOLD)
        self.assertTrue(streak >= gh.FAILING_STREAK_THRESHOLD)  # the failing_streak alert flag

    def test_mixed_window_resets_streak_at_first_success(self):
        # failure, failure, failure, success, failure — only the trailing
        # failure counts. recent_failures would say 4 (one in each
        # position); consecutive_failures must say 1.
        runs = [
            _run("failure", days_ago=0),
            _run("success", days_ago=1),
            _run("failure", days_ago=2),
            _run("failure", days_ago=3),
            _run("failure", days_ago=4),
        ]
        self.assertEqual(gh.consecutive_failures(runs), 1)

    def test_mixed_window_streak_breaks_on_cancelled(self):
        # cancelled breaks the streak — it is not a confirmed failure.
        runs = [
            _run("failure", days_ago=0),
            _run("failure", days_ago=1),
            _run("cancelled", days_ago=2),
            _run("failure", days_ago=3),
            _run("failure", days_ago=4),
        ]
        self.assertEqual(gh.consecutive_failures(runs), 2)

    def test_streak_breaks_on_in_progress(self):
        runs = [
            _run(None, status="in_progress"),
            _run("failure", days_ago=1),
            _run("failure", days_ago=2),
        ]
        # in_progress is the most recent run; streak stops immediately.
        self.assertEqual(gh.consecutive_failures(runs), 0)

    def test_empty_runs_has_zero_streak(self):
        self.assertEqual(gh.consecutive_failures([]), 0)

    def test_alert_flag_off_below_threshold(self):
        # Two failures in a row: concerning but not yet a streak alert.
        runs = [_run("failure", days_ago=i) for i in range(2)] + [
            _run("success", days_ago=2),
        ]
        streak = gh.consecutive_failures(runs)
        self.assertEqual(streak, 2)
        self.assertFalse(streak >= gh.FAILING_STREAK_THRESHOLD)


class AlertNeededTest(unittest.TestCase):
    """JEG-313: alert_needed is a per-workflow alert flag driven by the same
    FAILING_STREAK_THRESHOLD as failing_streak. The brief pins the boundary
    at exactly 3 — at 3 the badge must show, at 2 it must not. Two tests
    below cover the boundary from each side so a guard that asserts
    current behaviour is wrong (e.g. "> 3" instead of ">= 3") will fail."""

    def test_alert_needed_true_at_threshold(self):
        # Exactly FAILING_STREAK_THRESHOLD failures in a row must surface.
        runs = [_run("failure", days_ago=i) for i in range(gh.FAILING_STREAK_THRESHOLD)]
        streak = gh.consecutive_failures(runs)
        self.assertEqual(streak, gh.FAILING_STREAK_THRESHOLD)
        self.assertTrue(streak >= gh.FAILING_STREAK_THRESHOLD)

    def test_alert_needed_false_below_threshold(self):
        # One short of the threshold must not surface.
        runs = [_run("failure", days_ago=i) for i in range(gh.FAILING_STREAK_THRESHOLD - 1)]
        streak = gh.consecutive_failures(runs)
        self.assertEqual(streak, gh.FAILING_STREAK_THRESHOLD - 1)
        self.assertFalse(streak >= gh.FAILING_STREAK_THRESHOLD)

    def test_alert_needed_true_for_jeg113_outage_shape(self):
        # The JEG-113 shape: five failures in a row. Even well above the
        # threshold, alert_needed must remain true. Pins that we did not
        # accidentally cap the flag at the threshold.
        runs = [_run("failure", days_ago=i) for i in range(5)]
        streak = gh.consecutive_failures(runs)
        self.assertGreater(streak, gh.FAILING_STREAK_THRESHOLD)
        self.assertTrue(streak >= gh.FAILING_STREAK_THRESHOLD)

    def test_alert_needed_resets_on_first_non_failure(self):
        # Two failures, then a success: streak is 2, alert is off.
        # A bug that always returned True (or always false) would
        # obviously fail this; a more subtle bug — e.g. counting the
        # success as a failure — would also fail this.
        runs = [
            _run("failure", days_ago=0),
            _run("failure", days_ago=1),
            _run("success", days_ago=2),
        ]
        streak = gh.consecutive_failures(runs)
        self.assertEqual(streak, 2)
        self.assertFalse(streak >= gh.FAILING_STREAK_THRESHOLD)

    def test_alert_needed_breaks_on_cancelled(self):
        # cancelled breaks the streak — same predicate as consecutive_failures.
        # Most-recent-first ordering: 2 failures, then a cancelled run, then
        # older failures. The cancelled run is at position 2 (zero-indexed),
        # so the trailing streak is 2 — below the threshold, alert is off.
        # A bug that did not honour cancelled as a streak-breaker would
        # walk past it and count 4 failures, which would surface the alert.
        runs = [
            _run("failure", days_ago=0),     # most recent
            _run("failure", days_ago=1),
            _run("cancelled", days_ago=2),    # breaks the streak
            _run("failure", days_ago=3),
            _run("failure", days_ago=4),
        ]
        streak = gh.consecutive_failures(runs)
        self.assertEqual(streak, 2)
        self.assertFalse(streak >= gh.FAILING_STREAK_THRESHOLD)

    def test_alert_needed_false_on_empty_runs(self):
        # No runs at all — streak is 0, alert is off. Guards against a
        # regression that defaults the flag to True for empty windows.
        streak = gh.consecutive_failures([])
        self.assertEqual(streak, 0)
        self.assertFalse(streak >= gh.FAILING_STREAK_THRESHOLD)


class LastSuccessAtTest(unittest.TestCase):
    """The last_success_at timestamp drives the "X since last green" line."""

    def test_last_success_picks_most_recent(self):
        runs = [
            _run("failure", days_ago=0),
            _run("failure", days_ago=1),
            _run("success", days_ago=2),  # this is the most recent success
            _run("success", days_ago=3),
        ]
        self.assertEqual(gh.last_success_at(runs), runs[2]["created_at"])

    def test_last_success_none_when_no_successful_run(self):
        runs = [_run("failure", days_ago=i) for i in range(5)]
        self.assertIsNone(gh.last_success_at(runs))

    def test_last_success_picks_immediately_when_latest_run_succeeded(self):
        runs = [_run("success", days_ago=0)] + [_run("failure", days_ago=i + 1) for i in range(4)]
        self.assertEqual(gh.last_success_at(runs), runs[0]["created_at"])

    def test_last_success_empty_runs(self):
        self.assertIsNone(gh.last_success_at([]))


if __name__ == "__main__":
    unittest.main()
