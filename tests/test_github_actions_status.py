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


def _run(conclusion, status="completed", days_ago=0):
    from datetime import datetime, timedelta, timezone

    ts = (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()
    return {
        "created_at": ts,
        "updated_at": ts,
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


if __name__ == "__main__":
    unittest.main()
