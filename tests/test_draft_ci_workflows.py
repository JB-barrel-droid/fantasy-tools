"""Draft CI must defer heavy work without making required checks green."""

import io
import json
import os
import re
import subprocess
import tempfile
import unittest
from email.message import Message
from pathlib import Path
from unittest import mock
from urllib.error import HTTPError, URLError

from pipelines import ci_pr_gate
from pipelines.ci_pr_gate import decide, run
from tests.test_preview_workflow_matches_pages import job

ROOT = Path(__file__).resolve().parent.parent
EVENTS = ("opened", "synchronize", "reopened", "ready_for_review", "converted_to_draft")


def event(action="opened", draft=True, sha="a" * 40):
    return {"action": action, "pull_request": {
        "number": 7, "draft": draft, "head": {"sha": sha}}}


def live(draft=True, sha="a" * 40, state="open"):
    return {"number": 7, "draft": draft, "state": state, "head": {"sha": sha}}


class PrGateTest(unittest.TestCase):
    def test_draft_defers_and_ready_at_exact_head_runs(self):
        for action in EVENTS:
            with self.subTest(action=action):
                self.assertFalse(decide("pull_request", event(action), live())[0])
                self.assertTrue(decide("pull_request", event(action, False), live(False))[0])

    def test_stale_events_and_rapid_draft_toggles_fail_closed(self):
        for snapshot, current in (
            (event(draft=False), live(draft=True)),
            (event("converted_to_draft", True), live(False)),
            (event("ready_for_review", False), live(True)),
            (event(draft=False), live(False, sha="b" * 40)),
            (event(draft=False), live(False, state="closed")),
        ):
            with self.subTest(snapshot=snapshot, current=current):
                self.assertFalse(decide("pull_request", snapshot, current)[0])

    def test_unavailable_state_never_opens_gate(self):
        for current in (None, {}, {**live(False), "draft": None},
                        {**live(False), "head": {}}):
            with self.subTest(current=current):
                try:
                    allowed, _ = decide("pull_request", event(draft=False), current)
                except ValueError:
                    continue
                self.assertFalse(allowed)

    def test_push_and_manual_stay_full_verification(self):
        for name in ("push", "workflow_dispatch"):
            self.assertTrue(decide(name, {})[0])
        with self.assertRaises(ValueError):
            decide("unknown", {})

    def test_merge_group_runs_full_verification_without_a_live_pr(self):
        self.assertTrue(decide("merge_group", {"merge_group": {"head_sha": "b" * 40}})[0])
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "event.json").write_text(json.dumps({"merge_group": {"head_sha": "b" * 40}}))
            env = {"GITHUB_EVENT_PATH": str(root / "event.json"),
                   "GITHUB_EVENT_NAME": "merge_group", "GITHUB_OUTPUT": str(root / "output"),
                   "GITHUB_STEP_SUMMARY": str(root / "summary")}
            fetch = mock.Mock(side_effect=AssertionError("merge_group must not fetch a PR"))
            self.assertEqual(0, run("gate", env, fetch))
            self.assertIn("run_expensive=true", (root / "output").read_text())
            self.assertEqual(0, run("verify", env, fetch))
            fetch.assert_not_called()

    def test_live_api_error_fails_gate_and_final_verification(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "event.json").write_text(json.dumps(event(draft=False)))
            env = {"GITHUB_EVENT_PATH": str(root / "event.json"),
                   "GITHUB_EVENT_NAME": "pull_request", "GITHUB_REPOSITORY": "owner/repo",
                   "GH_TOKEN": "fake", "GITHUB_OUTPUT": str(root / "output"),
                   "GITHUB_STEP_SUMMARY": str(root / "summary")}

            def failed_fetch(*_args):
                raise OSError("API unavailable")

            for phase in ("gate", "verify"):
                with self.subTest(phase=phase), self.assertRaises(OSError), \
                        mock.patch("time.sleep"):
                    run(phase, env, failed_fetch)
            self.assertFalse((root / "output").exists())

    def test_final_verification_rechecks_head_and_draft(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "event.json").write_text(json.dumps(event(draft=False)))
            env = {"GITHUB_EVENT_PATH": str(root / "event.json"),
                   "GITHUB_EVENT_NAME": "pull_request", "GITHUB_REPOSITORY": "owner/repo",
                   "GH_TOKEN": "fake", "GITHUB_OUTPUT": str(root / "output"),
                   "GITHUB_STEP_SUMMARY": str(root / "summary")}
            self.assertEqual(0, run("gate", env, lambda *_: live(False)))
            self.assertIn("run_expensive=true", (root / "output").read_text())
            for changed in (live(True), live(False, sha="b" * 40)):
                with self.subTest(changed=changed), self.assertRaises(ValueError), \
                        mock.patch("time.sleep"):
                    run("verify", env, lambda *_: changed)
            self.assertEqual(0, run("verify", env, lambda *_: live(False)))


def http_error(code, body=b"", **headers):
    message = Message()
    for name, value in headers.items():
        message[name.replace("_", "-")] = value
    return HTTPError("https://api.github.com/x", code, "error", message, io.BytesIO(body))


class Reads:
    """A fetch that replays failures and PR states in order, counting calls."""

    def __init__(self, *results):
        self.results, self.calls = list(results), 0

    def __call__(self, *_args):
        self.calls += 1
        result = self.results.pop(0) if len(self.results) > 1 else self.results[0]
        if isinstance(result, BaseException):
            raise result
        return result


class PrStateRetryTest(unittest.TestCase):
    """JEG-1292: one API blip must not leave an idle ready PR red."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.env = {"GITHUB_EVENT_PATH": str(self.root / "event.json"),
                    "GITHUB_EVENT_NAME": "pull_request", "GITHUB_REPOSITORY": "owner/repo",
                    "GH_TOKEN": "fake", "GITHUB_OUTPUT": str(self.root / "output"),
                    "GITHUB_STEP_SUMMARY": str(self.root / "summary")}
        self.write_event(event("ready_for_review", draft=False))
        sleep = mock.patch("time.sleep")
        self.sleep = sleep.start()
        self.addCleanup(sleep.stop)
        self.addCleanup(self.temp.cleanup)

    def write_event(self, payload):
        (self.root / "event.json").write_text(json.dumps(payload))

    def output(self):
        path = self.root / "output"
        return path.read_text() if path.exists() else ""

    def test_one_failed_read_then_ready_pr_opens_gate(self):
        fetch = Reads(URLError("connection reset"), live(False))
        self.assertEqual(0, run("gate", self.env, fetch))
        self.assertIn("run_expensive=true", self.output())
        self.assertEqual(2, fetch.calls)

    def test_transient_http_errors_are_retried_for_gate_and_verify(self):
        errors = (lambda: http_error(502), lambda: http_error(503), lambda: http_error(429),
                  lambda: http_error(403, X_RateLimit_Remaining="0"),
                  lambda: http_error(403, b'{"message": "You have exceeded a secondary rate limit."}'),
                  lambda: TimeoutError("timed out"), lambda: ConnectionResetError("reset"))
        for make in errors:
            for phase in ("gate", "verify"):
                error = make()
                with self.subTest(error=repr(error), phase=phase):
                    fetch = Reads(error, live(False))
                    self.assertEqual(0, run(phase, self.env, fetch))
                    self.assertEqual(2, fetch.calls)

    def test_persistent_failure_is_bounded_and_fails_closed(self):
        fetch = Reads(URLError("down"))
        for phase in ("gate", "verify"):
            with self.subTest(phase=phase):
                fetch.calls = 0
                self.assertEqual(1, ci_pr_gate.main([phase], self.env, fetch))
                self.assertEqual(3, fetch.calls)
        self.assertNotIn("run_expensive=true", self.output())
        self.assertLessEqual(sum(call.args[0] for call in self.sleep.call_args_list), 2 * 30)

    def test_not_found_and_permission_errors_are_not_retried(self):
        for error in (http_error(404), http_error(403, b'{"message": "Resource not accessible"}'),
                      http_error(401)):
            with self.subTest(code=error.code):
                fetch = Reads(error, live(False))
                self.assertEqual(1, ci_pr_gate.main(["gate"], self.env, fetch))
                self.assertEqual(1, fetch.calls)
        self.assertNotIn("run_expensive=true", self.output())

    def test_lagging_draft_flag_is_read_again_before_calling_it_stale(self):
        fetch = Reads(live(True), live(False))
        self.assertEqual(0, run("gate", self.env, fetch))
        self.assertIn("run_expensive=true", self.output())
        self.assertEqual(2, fetch.calls)

    def test_draft_flag_that_never_settles_still_fails_closed(self):
        fetch = Reads(live(True))
        self.assertEqual(0, run("gate", self.env, fetch))
        self.assertIn("run_expensive=false", self.output())
        self.assertNotIn("run_expensive=true", self.output())
        self.assertEqual(3, fetch.calls)
        with self.assertRaises(ValueError):
            run("verify", self.env, Reads(live(True)))

    def test_moved_head_is_not_waited_on(self):
        fetch = Reads(live(False, sha="b" * 40))
        self.assertEqual(0, run("gate", self.env, fetch))
        self.assertIn("run_expensive=false", self.output())
        self.assertEqual(1, fetch.calls)


class WorkflowTest(unittest.TestCase):
    def test_pr_events_gate_heavy_jobs_and_keep_required_names(self):
        for name, heavy, required in (("preview.yml", ("preview-build", "preview-shard"), "preview"),
                                      ("v2-render-test.yml", ("render-tests",), "v2-render")):
            text = (ROOT / ".github/workflows" / name).read_text()
            with self.subTest(workflow=name):
                self.assertIn("types: [" + ", ".join(EVENTS) + "]", text)
                self.assertIn("  workflow_dispatch:", text)
                self.assertIn("group: " + ("preview" if name == "preview.yml" else "v2-render") +
                              "-${{ github.event.pull_request.number || github.ref }}", text)
                state = job(text, "pr-state") or ""
                self.assertIn("python3 -m pipelines.ci_pr_gate gate", state)
                self.assertIn("Cheap draft CI guards", state)
                self.assertIn("run_expensive: ${{ steps.gate.outputs.run_expensive }}", state)
                for heavy_name in heavy:
                    body = job(text, heavy_name) or ""
                    self.assertIn("needs: pr-state", body)
                    self.assertIn("if: needs.pr-state.outputs.run_expensive == 'true'", body)
                    self.assertIsNone(re.search(r"^    continue-on-error: true$", body, re.M))
                    self.assertLess(body.index("Recheck PR state before expensive work"),
                                    body.index("actions/setup-python@v5"))
                    self.assertIn("python3 -m pipelines.ci_pr_gate verify", body)
                final = job(text, required) or ""
                self.assertIn(f"'workflow_dispatch' && '{required}-manual' || '{required}'", final)
                self.assertIn("    if: always()", final)
                self.assertIn("needs.pr-state.result", final)
                self.assertIn("needs.pr-state.outputs.run_expensive", final)
                self.assertIn("python3 -m pipelines.ci_pr_gate verify", final)
                self.assertIn('exit 1', final)
                for heavy_name in heavy:
                    self.assertIn(f"needs.{heavy_name}.result", final)

    def test_failed_skipped_cancelled_dependencies_cannot_pass(self):
        # Execute the actual finalizer script for each non-success dependency.
        for name, required, vars_ in (("preview.yml", "preview", ("BUILD_RESULT", "SHARD_RESULT")),
                                      ("v2-render-test.yml", "v2-render", ("RENDER_RESULT",))):
            text = (ROOT / ".github/workflows" / name).read_text()
            body = job(text, required) or ""
            with self.subTest(workflow=name):
                match = re.search(r"^        run: \|\n((?:          .*\n)+)", body, re.M)
                self.assertIsNotNone(match)
                script = "\n".join(line[10:] for line in match.group(1).splitlines())
                for var in ("STATE_RESULT", "RUN_EXPENSIVE", *vars_):
                    expected = "true" if var == "RUN_EXPENSIVE" else "success"
                    self.assertIn(f'[ "${var}" != "{expected}" ]', body)
                    for outcome in (("false",) if var == "RUN_EXPENSIVE" else
                                    ("failure", "skipped", "cancelled")):
                        with self.subTest(variable=var, outcome=outcome), tempfile.TemporaryDirectory() as tmp:
                            env = dict(os.environ, GITHUB_STEP_SUMMARY=str(Path(tmp) / "summary"),
                                       STATE_RESULT="success", RUN_EXPENSIVE="true",
                                       BUILD_RESULT="success", SHARD_RESULT="success",
                                       RENDER_RESULT="success")
                            env[var] = outcome
                            result = subprocess.run(["bash", "-e", "-c", script], env=env,
                                                    text=True, capture_output=True, check=False)
                            self.assertNotEqual(0, result.returncode, result.stdout + result.stderr)
                            self.assertIn("deferred or incomplete", (Path(tmp) / "summary").read_text())
                self.assertIn("exit 1", body)

    def test_pages_production_validation_is_unconditional(self):
        text = (ROOT / ".github/workflows/pages.yml").read_text()
        for name in ("build", "validate-shard"):
            body = job(text, name) or ""
            self.assertTrue(body, name)
            self.assertNotIn("run_expensive", body)
            self.assertNotIn("pr-state", body)
            self.assertNotIn("    if:", body)


if __name__ == "__main__":
    unittest.main()
