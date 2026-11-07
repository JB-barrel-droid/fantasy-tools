"""JEG-1551: PR checks on known-good data, docs-only reporting, and the review receipt.

Jeremy, 2026-11-06, option A: tests run on frozen data, data refreshes don't
break code checks, no shared notes file in PRs, and green Codex-reviewed PRs
merge themselves through the merge queue (his yes only for deploys and value
math). Every rule below is checked against a case that must fail.
"""
import json
import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

from pipelines import ci_change_scope, ci_data_pin, review_receipt

ROOT = Path(__file__).resolve().parent.parent
GOOD = "a" * 40
HEAD = "c" * 40


def runs(*items):
    return {"workflow_runs": [dict(event="push", head_branch="main", conclusion="success",
                                   head_sha=GOOD) | i for i in items]}


def pr_payload():
    return {"pull_request": {"number": 7, "base": {"sha": "b" * 40}, "head": {"sha": HEAD}}}


def fake_api(files, run_payload):
    def fetch(path):
        if path.startswith("compare/"):
            return {"files": [{"filename": f} for f in files]}
        if path.startswith("actions/workflows/v2-render-test.yml/runs"):
            return run_payload
        raise AssertionError(path)
    return fetch


class DataPinTest(unittest.TestCase):
    def test_code_pr_pins_every_data_path(self):
        pin, paths, reason = ci_data_pin.plan("pull_request", pr_payload(),
                                              fake_api(["pipelines/x.py"], runs({})))
        self.assertEqual((pin, reason), (GOOD, "ok"))
        self.assertEqual(paths, list(ci_data_pin.DATA_PATHS))

    def test_pr_that_edits_data_keeps_its_own_version_of_that_path(self):
        pin, paths, _ = ci_data_pin.plan(
            "pull_request", pr_payload(),
            fake_api(["data/fixtures/current/players.json", "tests/t.py"], runs({})))
        self.assertEqual(pin, GOOD)
        self.assertNotIn("data/fixtures/current", paths)
        self.assertIn("data/ddf-two-tier", paths)

    def test_prefix_is_not_a_path_match(self):
        self.assertIn("output", ci_data_pin.paths_to_pin(["outputs/x.json"]))

    def test_merge_queue_is_pinned(self):
        payload = {"merge_group": {"base_sha": "b" * 40, "head_sha": HEAD}}
        pin, _, _ = ci_data_pin.plan("merge_group", payload, fake_api(["a.py"], runs({})))
        self.assertEqual(pin, GOOD)

    def test_push_to_main_tests_its_own_data(self):
        # The push run on main is the data check itself: it must never be pinned.
        pin, _, _ = ci_data_pin.plan("push", {}, fake_api([], runs({})))
        self.assertIsNone(pin)

    def test_only_a_passing_push_run_on_main_counts(self):
        bad = runs({"event": "pull_request"}, {"head_branch": "other"},
                   {"conclusion": "failure"})
        self.assertIsNone(ci_data_pin.known_good_sha(bad))
        mixed = runs({"conclusion": "failure", "head_sha": "f" * 40}, {})
        self.assertEqual(ci_data_pin.known_good_sha(mixed), GOOD)

    def test_doubt_keeps_the_checkout(self):
        def broken(path):
            raise OSError("down")
        self.assertIsNone(ci_data_pin.plan("pull_request", pr_payload(), broken)[0])
        many = [f"f{i}.py" for i in range(ci_data_pin.COMPARE_FILE_LIMIT)]
        self.assertIsNone(ci_data_pin.plan("pull_request", pr_payload(),
                                           fake_api(many, runs({})))[0])
        self.assertIsNone(ci_data_pin.plan("pull_request", pr_payload(),
                                           fake_api(["a.py"], {"workflow_runs": []}))[0])

    def test_apply_restores_pinned_data_and_removes_files_added_since(self):
        with tempfile.TemporaryDirectory() as tmp:
            def git(*args):
                return subprocess.run(["git", "-C", tmp, *args], check=True,
                                      capture_output=True, text=True)
            git("init", "-q")
            git("config", "user.email", "t@t"), git("config", "user.name", "t")
            data = Path(tmp, "data/fixtures/current")
            data.mkdir(parents=True)
            (data / "players.json").write_text("good\n")
            Path(tmp, "code.py").write_text("v1\n")
            git("add", "."), git("commit", "-qm", "good data")
            good = git("rev-parse", "HEAD").stdout.strip()
            (data / "players.json").write_text("broken rebuild\n")
            (data / "new.json").write_text("{}\n")
            Path(tmp, "code.py").write_text("v2\n")
            git("add", "."), git("commit", "-qm", "rebuild + code")
            calls = []

            def fake_git(*args):
                calls.append(args)
                if args[0] == "fetch":
                    return None
                return git(*args)

            def fetch(path):
                if path.startswith("compare/"):
                    return {"files": [{"filename": "code.py"}]}
                return {"workflow_runs": [{"event": "push", "head_branch": "main",
                                           "conclusion": "success", "head_sha": good}]}
            event = Path(tmp, "event.json")
            event.write_text(json.dumps(pr_payload()))
            pin, _, _ = ci_data_pin.apply(
                {"GITHUB_EVENT_NAME": "pull_request", "GITHUB_EVENT_PATH": str(event)},
                fetch_api=fetch, git=fake_git)
            self.assertEqual(pin, good)
            self.assertEqual((data / "players.json").read_text(), "good\n")
            self.assertFalse((data / "new.json").exists())
            self.assertEqual(Path(tmp, "code.py").read_text(), "v2\n")


class WorkflowWiringTest(unittest.TestCase):
    def read(self, name):
        return (ROOT / ".github/workflows" / name).read_text(encoding="utf-8")

    def test_every_pr_render_and_build_job_pins_before_make_sync(self):
        for name, job in (("preview.yml", "preview-build"), ("preview.yml", "preview-shard"),
                          ("v2-render-test.yml", "render-tests")):
            body = re.search(rf"^  {job}:\n((?:(?:    .*)?\n)*)", self.read(name), re.M).group(0)
            self.assertIn("python3 -m pipelines.ci_data_pin apply", body, job)
            self.assertLess(body.index("ci_data_pin apply"), body.index("make sync"), job)

    def test_pin_can_read_workflow_runs(self):
        for name in ("preview.yml", "v2-render-test.yml"):
            self.assertRegex(self.read(name), r"(?m)^permissions:\n  actions: read\n")

    def test_review_receipt_runs_trusted_code_and_queues_only_behind_the_merge_queue(self):
        text = self.read("review-receipt.yml")
        self.assertIn("name: review-receipt", text)
        self.assertIn("merge_group:", text)
        self.assertIn("pull_request_review:", text)
        # The check runs the base branch's script, so a PR cannot edit it into passing.
        self.assertIn("ref: ${{ github.event.pull_request.base.sha || github.sha }}", text)
        self.assertIn("*,merge_queue,*) gh pr merge --auto --squash", text)
        self.assertNotIn("pull_request_target", text)


class ChangeScopeTest(unittest.TestCase):
    def test_same_rule_as_the_old_paths_filter(self):
        self.assertTrue(ci_change_scope.docs_only(["README.md", "docs/claude-log/x.md", "docs/a.txt"]))
        for build_input in ("docs/methodology.md", "app/llm/skill/SKILL.md",
                            "docs/use-ddf-in-claude-chatgpt.md", "tests/test_x.py"):
            self.assertFalse(ci_change_scope.docs_only(["README.md", build_input]), build_input)
        self.assertFalse(ci_change_scope.docs_only([]))

    def test_doubt_runs_the_full_check(self):
        env = {"GITHUB_EVENT_NAME": "pull_request", "GITHUB_EVENT_PATH": "/nonexistent"}
        self.assertFalse(ci_change_scope.decide(env)[0])
        self.assertFalse(ci_change_scope.decide({"GITHUB_EVENT_NAME": "merge_group"})[0])
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
            json.dump({"pull_request": {"number": 3}}, handle)
        try:
            env = {"GITHUB_EVENT_NAME": "pull_request", "GITHUB_EVENT_PATH": handle.name,
                   "GITHUB_REPOSITORY": "o/r", "GH_TOKEN": "t"}
            too_many = lambda *a: ["README.md"] * ci_change_scope.FILE_LIMIT
            self.assertFalse(ci_change_scope.decide(env, too_many)[0])
            self.assertTrue(ci_change_scope.decide(env, lambda *a: ["README.md"])[0])
        finally:
            os.unlink(handle.name)


def review(body, commit=HEAD, at="2026-11-07T01:00:00Z", state="COMMENTED"):
    return {"body": body, "commit_id": commit, "submitted_at": at, "state": state}


PR = {"draft": False, "head": {"sha": HEAD}, "labels": []}
never = lambda sha: False


class ReviewReceiptTest(unittest.TestCase):
    def test_pass_on_current_head(self):
        self.assertEqual(review_receipt.evaluate(PR, ["a.py"], [review("ddf-review: PASS")], never),
                         (True, []))

    def test_no_review_or_draft_fails(self):
        self.assertFalse(review_receipt.evaluate(PR, ["a.py"], [], never)[0])
        self.assertFalse(review_receipt.evaluate(PR | {"draft": True}, ["a.py"],
                                                 [review("ddf-review: PASS")], never)[0])

    def test_later_fail_wins_and_dismissed_is_ignored(self):
        reviews = [review("ddf-review: PASS"),
                   review("ddf-review: FAIL", at="2026-11-07T02:00:00Z")]
        self.assertFalse(review_receipt.evaluate(PR, ["a.py"], reviews, never)[0])
        reviews = [review("ddf-review: PASS", at="2026-11-07T03:00:00Z"),
                   review("ddf-review: FAIL", state="DISMISSED")]
        self.assertTrue(review_receipt.evaluate(PR, ["a.py"], reviews, never)[0])

    def test_old_head_counts_only_when_the_change_is_identical(self):
        old = [review("ddf-review: PASS", commit="d" * 40)]
        self.assertFalse(review_receipt.evaluate(PR, ["a.py"], old, never)[0])
        self.assertTrue(review_receipt.evaluate(PR, ["a.py"], old, lambda sha: True)[0])

    def test_net_change_compares_contents(self):
        a = {"files": [{"filename": "x.py", "sha": "1"}]}
        b = {"files": [{"filename": "x.py", "sha": "2"}]}
        self.assertNotEqual(review_receipt.net_change(a), review_receipt.net_change(b))
        self.assertEqual(review_receipt.net_change(a), review_receipt.net_change(dict(a)))

    def test_value_math_and_migrations_need_jeremy(self):
        passed = [review("ddf-review: PASS")]
        for path in ("app/trade-value-chart/assets/value-model.js", "sql/migrations/001.sql",
                     "supabase/migrations/2026.sql", "config/lineup_parameters.json"):
            self.assertFalse(review_receipt.evaluate(PR, [path], passed, never)[0], path)
            approved = PR | {"labels": [{"name": "jeremy-approved"}]}
            self.assertTrue(review_receipt.evaluate(approved, [path], passed, never)[0], path)

    def test_handoff_edit_is_flagged(self):
        passed = [review("ddf-review: PASS")]
        self.assertFalse(review_receipt.evaluate(PR, ["HANDOFF.md"], passed, never)[0])
        labelled = PR | {"labels": [{"name": "handoff-edit"}]}
        self.assertTrue(review_receipt.evaluate(labelled, ["HANDOFF.md"], passed, never)[0])

    def test_value_math_list_covers_the_explainer_logic_files(self):
        text = (ROOT / "pipelines/build_values_explainer.py").read_text(encoding="utf-8")
        block = re.search(r"LOGIC_FILES = \[(.*?)\]", text, re.S).group(1)
        for name in re.findall(r'"([^"]+)"', block):
            self.assertIn(name, review_receipt.VALUE_MATH)

    def test_merge_queue_passes_and_api_doubt_fails(self):
        self.assertTrue(review_receipt.check({"GITHUB_EVENT_NAME": "merge_group"})[0])
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
            json.dump({"pull_request": {"number": 5}}, handle)
        try:
            env = {"GITHUB_EVENT_NAME": "pull_request", "GITHUB_EVENT_PATH": handle.name}

            def broken(path):
                raise OSError("down")
            self.assertFalse(review_receipt.check(env, broken)[0])
        finally:
            os.unlink(handle.name)


if __name__ == "__main__":
    unittest.main()
