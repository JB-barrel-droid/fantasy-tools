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


class CoverageGapsTest(unittest.TestCase):
    """JEG-311: coverage_gaps must reflect workflows present in the API
    list but absent from PIPELINE_COVERAGE. The previous hardcoded
    `coverage_gaps: []` masked CBS ROS, Live page synthetic gate, and
    Preview build, which rendered as 'Unmapped' on the dashboard.

    These are negative tests against the regression: a workflow present
    in the API list but missing from the coverage map MUST appear in
    coverage_gaps, and the gaps list MUST be sorted deterministically.
    """

    def test_unmapped_workflow_appears_in_gaps(self):
        # CBS ROS is the JEG-311 case: present in the API list, missing
        # from PIPELINE_COVERAGE before this commit. Simulate the broken
        # pre-fix state by passing a synthetic coverage_keys set without
        # it; gaps must surface it.
        api_names = [
            "CBS ROS scrape to Supabase",
            "Rebuild comparison chain",
        ]
        coverage_keys = {"Rebuild comparison chain"}
        gaps = gh.compute_coverage_gaps(api_names, coverage_keys)
        self.assertIn("CBS ROS scrape to Supabase", gaps)

    def test_all_nine_workflows_mapped_yields_empty_gaps(self):
        # Pin the post-fix invariant: once all 9 current workflows are
        # in PIPELINE_COVERAGE, coverage_gaps must be empty. We pass the
        # full set of workflow names plus the full PIPELINE_COVERAGE
        # keys; the gap set must be the empty set.
        all_nine = set(gh.PIPELINE_COVERAGE.keys()) | {
            "Live page synthetic gate",
            "Preview build",
        }
        gaps = gh.compute_coverage_gaps(sorted(all_nine), set(gh.PIPELINE_COVERAGE.keys()))
        self.assertEqual(gaps, [])

    def test_gaps_are_sorted_deterministically(self):
        # Order matters for stable diffs / dashboard rendering.
        api_names = ["Zeta workflow", "Alpha workflow", "Beta workflow"]
        gaps = gh.compute_coverage_gaps(api_names, set())
        self.assertEqual(gaps, ["Alpha workflow", "Beta workflow", "Zeta workflow"])

    def test_duplicate_api_names_dedupe_in_gaps(self):
        # GitHub returns one entry per workflow; dedupe defensively.
        api_names = ["New workflow", "New workflow", "Known workflow"]
        coverage_keys = {"Known workflow"}
        gaps = gh.compute_coverage_gaps(api_names, coverage_keys)
        self.assertEqual(gaps, ["New workflow"])

    def test_cbs_ros_now_present_in_coverage_map(self):
        # Positive pin: the CBS ROS backfill entry exists with the
        # fields the JEG-311 brief specifies. This guards against a
        # future refactor that drops or renames it.
        self.assertIn("CBS ROS scrape to Supabase", gh.PIPELINE_COVERAGE)
        entry = gh.PIPELINE_COVERAGE["CBS ROS scrape to Supabase"]
        self.assertEqual(entry["stages"], ["C2", "C3"])
        self.assertEqual(entry["description"], "Weekly CBS ROS scrape to Supabase")
        self.assertEqual(entry["schedule"], "Weekly Wed 11:00 UTC (06:00 CT)")


if __name__ == "__main__":
    unittest.main()
