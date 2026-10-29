"""Draft CI must defer heavy work without making required checks green."""

import json
import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

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
                with self.subTest(phase=phase), self.assertRaises(OSError):
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
                with self.subTest(changed=changed), self.assertRaises(ValueError):
                    run("verify", env, lambda *_: changed)
            self.assertEqual(0, run("verify", env, lambda *_: live(False)))


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
