"""JEG-1194: the board stopping must reach Jeremy.

The chain failed every run from 2026-10-26 15:42Z for about 44 hours and
nobody heard: the failure only went to the status file and the monitoring
table. pipelines/chain_stuck_alert.py opens one GitHub issue once the chain
has failed and the published fixture is STUCK_HOURS old, and closes it when
the chain publishes. GitHub calls are faked; nothing leaves the process.
"""
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pipelines"))
sys.path.insert(0, str(ROOT))
import chain_stuck_alert as alert  # noqa: E402

NOW = datetime(2026, 10, 28, 12, 0, tzinfo=timezone.utc)
BUILT = "2026-10-26T15:42:37.663230+00:00"  # the fixture that sat on week 7
STATUS = {
    "held": ["cbs"],
    "source_weeks": {"cbs": {"served_week": 7, "label_week": 7},
                     "usatoday": {"served_week": 8, "label_week": 8}},
    "post_rebuild_validation": {
        "status": "failed",
        "failed_tests": ["FAIL tests.test_superflex.SuperflexPage.test_live_page_superflex_control"],
        "detail": "FAIL tests.test_superflex..."},
}
HISTORY = {"fixture_built_at": BUILT, "served": {"cbs": {"week": 7}, "usatoday": {"week": 7}}}


class FakeGitHub:
    def __init__(self, issues=()):
        self.issues = list(issues)
        self.calls = []

    def __call__(self, method, path, token, payload=None):
        self.calls.append((method, path, payload))
        if method == "GET":
            return self.issues
        if method == "POST" and path.endswith("/issues"):
            return {"number": 77}
        return {}


class Decide(unittest.TestCase):
    def test_the_44_hour_outage_is_stuck(self):
        self.assertEqual(alert.decide("failure", BUILT, NOW), "open")

    def test_a_recent_failure_is_not_stuck_yet(self):
        built = (NOW - timedelta(hours=alert.STUCK_HOURS - 1)).isoformat()
        self.assertEqual(alert.decide("failure", built, NOW), "none")

    def test_a_failure_with_no_build_time_is_stuck(self):
        self.assertEqual(alert.decide("failure", None, NOW), "open")

    def test_a_published_run_closes(self):
        self.assertEqual(alert.decide("success", BUILT, NOW, published=True), "close")

    def test_success_without_publication_preserves_the_alert(self):
        for published in (False,):
            action = alert.decide("success", BUILT, NOW, published=published)
            gh = FakeGitHub([{"number": 5, "title": alert.TITLE}])
            alert.run(action, "", "o/r", "t", NOW, gh)
            self.assertEqual(action, "none")
            self.assertEqual(gh.calls, [])

    def test_status_only_push_cannot_close_alert(self):
        self.assertEqual(alert.decide("failure", BUILT, NOW, published=True), "open")

    def test_a_skipped_or_cancelled_run_does_nothing(self):
        for outcome in ("skipped", "cancelled", ""):
            self.assertEqual(alert.decide(outcome, BUILT, NOW), "none")


class Body(unittest.TestCase):
    def test_names_the_failing_check_held_sources_and_served_weeks(self):
        text = alert.body(STATUS, HISTORY, NOW)
        self.assertIn("test_live_page_superflex_control", text)
        self.assertIn("Held sources: cbs", text)
        self.assertIn("- cbs: week 7", text)
        self.assertIn("44 hours ago", text)
        self.assertIn("- usatoday: week 8", text)


class Run(unittest.TestCase):
    def test_opens_one_issue_when_none_is_open(self):
        gh = FakeGitHub()
        self.assertEqual(alert.run("open", "x", "o/r", "t", NOW, gh), "opened #77")
        posts = [c for c in gh.calls if c[0] == "POST"]
        self.assertEqual(len(posts), 1)
        self.assertEqual(posts[0][2]["labels"], [alert.LABEL])

    def test_does_not_open_a_second_issue(self):
        recent = {"number": 5, "title": alert.TITLE, "updated_at": (NOW - timedelta(hours=1)).isoformat()}
        gh = FakeGitHub([recent])
        alert.run("open", "x", "o/r", "t", NOW, gh)
        self.assertEqual([c for c in gh.calls if c[0] != "GET"], [])

    def test_comments_on_a_stale_open_issue(self):
        old = {"number": 5, "labels": [{"name": alert.LABEL}], "updated_at": (NOW - timedelta(hours=alert.COMMENT_HOURS + 1)).isoformat()}
        gh = FakeGitHub([old])
        self.assertEqual(alert.run("open", "x", "o/r", "t", NOW, gh), "commented on #5")

    def test_closes_the_open_issue_on_publish(self):
        gh = FakeGitHub([{"number": 5, "title": alert.TITLE, "updated_at": BUILT}])
        self.assertEqual(alert.run("close", "", "o/r", "t", NOW, gh), "closed #5")
        self.assertIn(("PATCH", "/repos/o/r/issues/5", {"state": "closed", "state_reason": "completed"}),
                      gh.calls)

    def test_pull_requests_are_not_mistaken_for_the_issue(self):
        gh = FakeGitHub([{"number": 9, "pull_request": {}, "updated_at": BUILT}])
        self.assertEqual(alert.run("close", "", "o/r", "t", NOW, gh), "published; no open issue")

    def test_without_a_token_it_only_prints(self):
        gh = FakeGitHub()
        out = alert.run("open", "body text", "o/r", None, NOW, gh)
        self.assertTrue(out.startswith("dry run"))
        self.assertEqual(gh.calls, [])


class Robust(unittest.TestCase):
    def test_cli_requires_confirmed_push_to_close(self):
        from unittest.mock import patch
        for pushed, expected in (("false", "none"), ("", "none"), ("true", "close")):
            with self.subTest(pushed=pushed), patch.object(alert, "_read", return_value=HISTORY), patch.object(alert, "run", return_value="checked") as run:
                self.assertEqual(alert.main(["--chain-outcome", "success", "--published", pushed]), 0)
                self.assertEqual(run.call_args.args[0], expected)

    def test_an_unlabelled_issue_is_found_by_title(self):
        gh = FakeGitHub([{"number": 6, "title": alert.TITLE, "labels": [], "updated_at": BUILT}])
        self.assertEqual(alert.run("close", "", "o/r", "t", NOW, gh), "closed #6")

    def test_another_open_issue_is_left_alone(self):
        gh = FakeGitHub([{"number": 8, "title": "Something else", "labels": [], "updated_at": BUILT}])
        self.assertEqual(alert.run("close", "", "o/r", "t", NOW, gh), "published; no open issue")

    def test_malformed_status_never_fails_the_job(self):
        import json
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            st, hi = Path(d, "s.json"), Path(d, "h.json")
            st.write_text(json.dumps({"post_rebuild_validation": "oops", "held": 5}))
            hi.write_text(json.dumps({"fixture_built_at": BUILT, "served": {"cbs": 7}}))
            for outcome in ("failure", "success"):
                self.assertEqual(0, alert.main(["--chain-outcome", outcome, "--status", str(st),
                                                "--history", str(hi)]))


class Workflow(unittest.TestCase):
    def test_the_chain_workflow_runs_the_alert_with_issue_rights(self):
        wf = (ROOT / ".github" / "workflows" / "rebuild-chain.yml").read_text(encoding="utf-8")
        self.assertIn('--published "${{ steps.push.outputs.pushed }}"', wf)
        self.assertIn("issues: write", wf)
        self.assertIn("pipelines/chain_stuck_alert.py --chain-outcome", wf)
        step = wf.split("pipelines/chain_stuck_alert.py")[0].rsplit("- name:", 1)[1]
        self.assertIn("always()", step)
        self.assertIn("refs/heads/main", step)


if __name__ == "__main__":
    unittest.main()
