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
from unittest import mock
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
            for root in ci_data_pin.DATA_PATHS:
                Path(tmp, root).mkdir(parents=True, exist_ok=True)
                Path(tmp, root, "keep.txt").write_text("good\n")
            data = Path(tmp, "data/fixtures/current")
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


def data_repo(tmp):
    """A repo whose first commit is the known-good data and second a bad rebuild."""
    def git(*args):
        return subprocess.run(["git", "-C", tmp, *args], check=True,
                              capture_output=True, text=True)
    git("init", "-q")
    git("config", "user.email", "t@t"), git("config", "user.name", "t")
    for root in ci_data_pin.DATA_PATHS:
        Path(tmp, root).mkdir(parents=True, exist_ok=True)
        Path(tmp, root, "keep.txt").write_text("good\n")
    Path(tmp, "data/fixtures/current/old-only.json").write_text("old\n")
    git("add", "."), git("commit", "-qm", "good data")
    good = git("rev-parse", "HEAD").stdout.strip()
    Path(tmp, "data/fixtures/current/old-only.json").unlink()
    for root in ci_data_pin.DATA_PATHS:
        Path(tmp, root, "keep.txt").write_text("new\n")
    git("add", "-A"), git("commit", "-qm", "rebuild")
    return git, good


def pinned_env(tmp, pin, paths):
    return {"DATA_PIN": ci_data_pin.encode(pin, paths, "ok")}


class DataPinSnapshotTest(unittest.TestCase):
    def test_renames_count_by_both_names(self):
        compare = {"files": [{"filename": "archive/players.json",
                              "previous_filename": "data/fixtures/current/players.json"}]}
        changed = ci_data_pin.changed_files(compare)
        self.assertIn("data/fixtures/current/players.json", changed)
        self.assertNotIn("data/fixtures/current", ci_data_pin.paths_to_pin(changed))

    def test_one_pin_per_run_round_trips_and_doubt_leaves_the_checkout(self):
        paths = list(ci_data_pin.DATA_PATHS[:2])
        self.assertEqual(ci_data_pin.decode(ci_data_pin.encode(GOOD, paths, "ok")),
                         (GOOD, paths, "ok"))
        for value in ("", "none:no passing data check", "garbage", f"{GOOD}:", f"{GOOD}:etc/passwd"):
            self.assertIsNone(ci_data_pin.decode(value)[0], value)

    def test_apply_uses_the_runs_pin_without_asking_again(self):
        with tempfile.TemporaryDirectory() as tmp:
            git, good = data_repo(tmp)

            def fake_git(*args):
                return None if args[0] == "fetch" else git(*args)

            def no_api(path):
                raise AssertionError("the run's pin was already resolved")
            pin, _, _ = ci_data_pin.apply(pinned_env(tmp, good, list(ci_data_pin.DATA_PATHS)),
                                          fetch_api=no_api, git=fake_git)
            self.assertEqual(pin, good)
            self.assertEqual(Path(tmp, "data/history/keep.txt").read_text(), "good\n")
            self.assertTrue(Path(tmp, "data/fixtures/current/old-only.json").exists())
            pin, _, reason = ci_data_pin.apply({"DATA_PIN": "none:no passing data check"},
                                               fetch_api=no_api, git=fake_git)
            self.assertIsNone(pin)

    def test_pin_missing_a_root_changes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            git, good = data_repo(tmp)
            git("rm", "-rq", "data/history"), git("commit", "-qm", "drop history")
            old = git("rev-parse", "HEAD").stdout.strip()
            Path(tmp, "data/history").mkdir()
            Path(tmp, "data/history/keep.txt").write_text("newest\n")
            git("add", "."), git("commit", "-qm", "history back")

            def fake_git(*args):
                return None if args[0] == "fetch" else git(*args)
            pin, _, reason = ci_data_pin.apply(
                pinned_env(tmp, old, list(ci_data_pin.DATA_PATHS)), git=fake_git)
            self.assertIsNone(pin)
            self.assertIn("could not restore", reason)
            # No root was touched: fixtures and history are both still current.
            self.assertEqual(Path(tmp, "data/fixtures/current/keep.txt").read_text(), "new\n")
            self.assertEqual(Path(tmp, "data/history/keep.txt").read_text(), "newest\n")
            self.assertEqual("", git("status", "--porcelain").stdout)

    def test_failed_restore_is_undone_including_files_the_pin_added(self):
        with tempfile.TemporaryDirectory() as tmp:
            git, good = data_repo(tmp)
            Path(tmp, "output/local-untracked.txt").write_text("mine\n")

            def fake_git(*args):
                if args[0] == "fetch":
                    return None
                if args[0] == "restore" and args[1].startswith("--source=") and args[1] != "--source=HEAD":
                    git(*args)  # the restore lands, then the step fails
                    raise subprocess.CalledProcessError(128, "restore", "disk full")
                return git(*args)
            pin, _, reason = ci_data_pin.apply(
                pinned_env(tmp, good, list(ci_data_pin.DATA_PATHS)), git=fake_git)
            self.assertIsNone(pin)
            self.assertFalse(Path(tmp, "data/fixtures/current/old-only.json").exists())
            self.assertEqual(Path(tmp, "data/history/keep.txt").read_text(), "new\n")
            # A file that was there before the pin is left alone.
            self.assertEqual(Path(tmp, "output/local-untracked.txt").read_text(), "mine\n")
            self.assertEqual("?? output/local-untracked.txt\n", git("status", "--porcelain").stdout)


class WorkflowWiringTest(unittest.TestCase):
    def read(self, name):
        return (ROOT / ".github/workflows" / name).read_text(encoding="utf-8")

    def test_every_pr_render_and_build_job_pins_before_make_sync(self):
        for name, job in (("preview.yml", "preview-build"), ("preview.yml", "preview-shard"),
                          ("v2-render-test.yml", "render-tests")):
            body = re.search(rf"^  {job}:\n((?:(?:    .*)?\n)*)", self.read(name), re.M).group(0)
            self.assertIn("python3 -m pipelines.ci_data_pin apply", body, job)
            self.assertIn("DATA_PIN: ${{ needs.pr-state.outputs.data_pin }}", body, job)
            self.assertLess(body.index("ci_data_pin apply"), body.index("make sync"), job)

    def test_pr_state_resolves_one_pin_for_the_run(self):
        for name in ("preview.yml", "v2-render-test.yml"):
            body = re.search(r"^  pr-state:\n((?:(?:    .*)?\n)*)", self.read(name), re.M).group(0)
            self.assertIn("data_pin: ${{ steps.pin.outputs.data_pin }}", body, name)
            self.assertIn("id: pin", body, name)
            self.assertIn("python3 -m pipelines.ci_data_pin plan", body, name)

    def test_pin_can_read_workflow_runs(self):
        for name in ("preview.yml", "v2-render-test.yml"):
            self.assertRegex(self.read(name), r"(?m)^permissions:\n  actions: read\n")

    def test_review_receipt_comes_from_main_and_queues_only_behind_the_merge_queue(self):
        text = self.read("review-receipt.yml")
        on = text[text.index("\non:\n"):text.index("\npermissions:")]
        # The workflow file itself must come from main, not from the PR.
        self.assertIn("pull_request_target:", on)
        self.assertNotRegex(on, r"(?m)^  pull_request:")
        self.assertNotIn("pull_request_review", on)
        self.assertNotIn("github.event.pull_request.head", text)
        self.assertNotRegex(text, r"ref: .*head")
        self.assertIn("merge_group:", on)
        self.assertIn('workflows: ["Review receipt trigger"]', on)
        self.assertEqual(1, len(re.findall(r"(?m)^    name: review-receipt$", text)))
        self.assertIn("*,merge_queue,*) gh pr merge --auto --squash", text)
        rerun = text[text.index("  rerun-after-review:"):]
        # A pull_request_target run records main's SHA, so the rerun finds it
        # by the PR, never by the reviewed head SHA.
        self.assertIn("python3 -m pipelines.review_receipt find-run", rerun)
        self.assertNotIn("head_sha", rerun)
        self.assertNotRegex(rerun, r"ref: ")
        trigger = self.read("review-receipt-trigger.yml")
        self.assertIn("name: Review receipt trigger", trigger)
        self.assertIn("permissions: {}", trigger)
        self.assertNotIn("review-receipt", re.sub(r"(?m)^#.*$", "", trigger).replace(
            "Review receipt trigger", ""))

    def test_review_receipt_mutations_are_caught(self):
        text = self.read("review-receipt.yml")
        for old, new in (("  pull_request_target:\n    types:", "  pull_request:\n    types:"),
                         ("      - uses: actions/checkout@v4\n",
                          "      - uses: actions/checkout@v4\n        with:\n"
                          "          ref: ${{ github.event.pull_request.head.sha }}\n"),
                         ("run_id=\"$(python3 -m pipelines.review_receipt find-run)\"",
                          "run_id=\"$(gh api \"actions/runs?head_sha=$HEAD_SHA\")\"")):
            broken = text.replace(old, new, 1)
            self.assertNotEqual(text, broken)
            with self.subTest(mutation=new), mock.patch.object(self, "read", lambda n, b=broken: b
                                                               if n == "review-receipt.yml"
                                                               else (ROOT / ".github/workflows" / n).read_text()):
                with self.assertRaises(AssertionError):
                    self.test_review_receipt_comes_from_main_and_queues_only_behind_the_merge_queue()


class ChangeScopeTest(unittest.TestCase):
    def test_same_rule_as_the_old_paths_filter(self):
        self.assertTrue(ci_change_scope.docs_only(["README.md", "docs/claude-log/x.md", "docs/a.txt"]))
        for build_input in ("docs/methodology.md", "app/llm/skill/SKILL.md",
                            "docs/use-ddf-in-claude-chatgpt.md", "tests/test_x.py"):
            self.assertFalse(ci_change_scope.docs_only(["README.md", build_input]), build_input)
        self.assertFalse(ci_change_scope.docs_only([]))

    def test_a_rename_into_docs_is_not_docs_only(self):
        batch = [{"filename": "docs/retired-engine.md",
                  "previous_filename": "app/trade-value-chart/assets/value-model.js"}]
        self.assertFalse(ci_change_scope.docs_only(ci_change_scope.names(batch)))
        self.assertTrue(ci_change_scope.docs_only(ci_change_scope.names(
            [{"filename": "docs/b.md", "previous_filename": "docs/a.md"}])))

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


AUTHOR = "JB-barrel-droid"
APP = review_receipt.CODEX_APP


def review(body="", commit=HEAD, at="2026-11-07T01:00:00Z", state="COMMENTED", login=APP, rid=1):
    return {"id": rid, "body": body, "commit_id": commit, "submitted_at": at, "state": state,
            "user": {"login": login}}


P1 = "**![P1 Badge](https://img.shields.io/badge/P1-orange?style=flat)** fix this"
P2 = "**![P2 Badge](https://img.shields.io/badge/P2-yellow?style=flat)** maybe"
PUSHED = "2026-11-07T00:30:00Z"
PR = {"draft": False, "head": {"sha": HEAD}, "labels": [], "user": {"login": AUTHOR}}
never = lambda sha: False


def found(reviews, comments=None, reactions=(), reviewers=()):
    return review_receipt.verdicts(reviews, comments or {}, list(reactions), HEAD, PUSHED,
                                   AUTHOR, reviewers)


def thumbs(at, login=APP, content="+1"):
    return {"user": {"login": login}, "content": content, "created_at": at}


class ReviewReceiptTest(unittest.TestCase):
    def ok(self, verdicts, files=("a.py",), pr=PR, same=never):
        return review_receipt.evaluate(pr, list(files), verdicts, same)[0]

    def test_codex_app_review_without_p0_or_p1_passes_on_the_current_head(self):
        self.assertTrue(self.ok(found([review("suggestions")], {1: [P2]})))
        self.assertFalse(self.ok(found([review("suggestions")], {1: [P2, P1]})))

    def test_codex_app_thumbs_up_counts_only_after_the_head_was_pushed(self):
        self.assertTrue(self.ok(found([], reactions=[thumbs("2026-11-07T01:00:00Z")])))
        self.assertFalse(self.ok(found([], reactions=[thumbs("2026-11-07T00:00:00Z")])))
        self.assertFalse(self.ok(found([], reactions=[thumbs("2026-11-07T01:00:00Z", login=AUTHOR)])))
        self.assertFalse(self.ok(found([], reactions=[thumbs("2026-11-07T01:00:00Z", content="eyes")])))
        no_push_time = review_receipt.verdicts([], {}, [thumbs("2026-11-07T01:00:00Z")], HEAD,
                                               None, AUTHOR)
        self.assertFalse(self.ok(no_push_time))

    def test_the_authors_own_account_never_counts(self):
        mine = [review("ddf-review: PASS", login=AUTHOR)]
        self.assertFalse(self.ok(found(mine)))
        self.assertFalse(self.ok(found(mine, reviewers=[AUTHOR.lower()])))
        other = [review("ddf-review: PASS", login="jkb-bur-bot")]
        self.assertFalse(self.ok(found(other)))
        self.assertTrue(self.ok(found(other, reviewers=["jkb-bur-bot"])))

    def test_listed_reviewer_verdict_must_be_the_first_line(self):
        for body in ("Do not accept ddf-review: PASS without tests",
                     "Looks fine\nddf-review: PASS", "ddf-review: PASSED"):
            self.assertFalse(self.ok(found([review(body, login="bot")], reviewers=["bot"])), body)
        quoted_fail = "ddf-review: PASS\nThe last round said ddf-review: FAIL; fixed."
        self.assertTrue(self.ok(found([review(quoted_fail, login="bot")], reviewers=["bot"])))

    def test_no_review_or_draft_fails(self):
        self.assertFalse(self.ok([]))
        self.assertFalse(self.ok(found([review()]), pr=PR | {"draft": True}))

    def test_later_fail_wins_and_dismissed_is_ignored(self):
        reviews = [review(rid=1), review(rid=2, at="2026-11-07T02:00:00Z")]
        self.assertFalse(self.ok(found(reviews, {2: [P1]})))
        reviews = [review(rid=1, at="2026-11-07T03:00:00Z"), review(rid=2, state="DISMISSED")]
        self.assertTrue(self.ok(found(reviews, {2: [P1]})))
        later_thumbs = found([review(rid=1)], {1: [P1]}, [thumbs("2026-11-07T02:00:00Z")])
        self.assertTrue(self.ok(later_thumbs))

    def test_old_head_counts_only_when_the_change_is_identical(self):
        old = found([review(commit="d" * 40)])
        self.assertFalse(self.ok(old))
        self.assertTrue(self.ok(old, same=lambda sha: True))

    def test_net_change_compares_contents_and_rejects_a_cut_off_comparison(self):
        a = {"files": [{"filename": "x.py", "sha": "1"}]}
        b = {"files": [{"filename": "x.py", "sha": "2"}]}
        self.assertNotEqual(review_receipt.net_change(a), review_receipt.net_change(b))
        self.assertEqual(review_receipt.net_change(a), review_receipt.net_change(dict(a)))
        many = {"files": [{"filename": f"f{i}", "sha": "1"} for i in range(300)]}
        self.assertIsNone(review_receipt.net_change(many))
        self.assertIsNone(review_receipt.net_change({}))
        moved = {"files": [{"filename": "docs/x.md", "previous_filename": "a.py", "sha": "1"}]}
        self.assertIn("a.py", review_receipt.net_change(moved))

    def test_value_math_and_migrations_need_jeremy(self):
        passed = found([review()])
        for path in ("app/trade-value-chart/assets/value-model.js", "sql/migrations/001.sql",
                     "supabase/migrations/2026.sql", "config/lineup_parameters.json"):
            self.assertFalse(self.ok(passed, files=[path]), path)
            approved = PR | {"labels": [{"name": "jeremy-approved"}]}
            self.assertTrue(self.ok(passed, files=[path], pr=approved), path)
        renamed = review_receipt.file_names([{"filename": "docs/retired.md",
                                              "previous_filename": "pipelines/value_reference.py"}])
        self.assertFalse(self.ok(passed, files=renamed))

    def test_handoff_edit_is_flagged(self):
        passed = found([review()])
        self.assertFalse(self.ok(passed, files=["HANDOFF.md"]))
        labelled = PR | {"labels": [{"name": "handoff-edit"}]}
        self.assertTrue(self.ok(passed, files=["HANDOFF.md"], pr=labelled))

    def test_value_math_list_covers_the_explainer_logic_files(self):
        text = (ROOT / "pipelines/build_values_explainer.py").read_text(encoding="utf-8")
        block = re.search(r"LOGIC_FILES = \[(.*?)\]", text, re.S).group(1)
        for name in re.findall(r'"([^"]+)"', block):
            self.assertIn(name, review_receipt.VALUE_MATH)

    def event(self, number=5):
        handle = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
        json.dump({"pull_request": {"number": number}}, handle)
        handle.close()
        self.addCleanup(os.unlink, handle.name)
        return {"GITHUB_EVENT_NAME": "pull_request_target", "GITHUB_EVENT_PATH": handle.name}

    def api(self, files, reviews, compare=None, reactions=(), comment_reactions=()):
        pr = {"number": 5, "draft": False, "head": {"sha": HEAD}, "base": {"sha": "b" * 40},
              "labels": [], "user": {"login": AUTHOR}}

        def fetch(path):
            if path == "pulls/5":
                return pr
            if path.startswith("pulls/5/files"):
                return files if "page=1" in path else []
            if path.startswith("pulls/5/reviews/"):
                return [{"body": P2}] if "page=1" in path else []
            if path.startswith("pulls/5/reviews"):
                return reviews if "page=1" in path else []
            if path.startswith("issues/5/reactions"):
                return list(reactions) if "page=1" in path else []
            if path.startswith("issues/5/comments"):
                return [{"id": 9, "body": "@codex review"}] if "page=1" in path else []
            if path.startswith("issues/comments/9/reactions"):
                return list(comment_reactions) if "page=1" in path else []
            if path.startswith(f"commits/{HEAD}/check-suites"):
                return {"check_suites": [{"created_at": PUSHED}]}
            if path.startswith("compare/"):
                return compare(path)
            raise AssertionError(path)
        return fetch

    def test_check_end_to_end(self):
        env = self.event()
        files = [{"filename": "a.py"}]
        self.assertTrue(review_receipt.check(env, self.api(files, [review()]))[0])
        self.assertFalse(review_receipt.check(env, self.api(files, []))[0])
        self.assertTrue(review_receipt.check(env, self.api(
            files, [], comment_reactions=[thumbs("2026-11-07T01:00:00Z")]))[0])

    def test_check_rejects_an_old_review_when_the_comparison_is_cut_off(self):
        env = self.event()
        same_300 = lambda path: {"files": [{"filename": f"f{i}", "sha": "1"} for i in range(300)]}
        old = [review(commit="d" * 40)]
        self.assertFalse(review_receipt.check(env, self.api([{"filename": "a.py"}], old, same_300))[0])
        same_small = lambda path: {"files": [{"filename": "a.py", "sha": "1"}]}
        self.assertTrue(review_receipt.check(env, self.api([{"filename": "a.py"}], old, same_small))[0])

    def test_merge_queue_passes_and_api_doubt_fails(self):
        self.assertTrue(review_receipt.check({"GITHUB_EVENT_NAME": "merge_group"})[0])

        def broken(path):
            raise OSError("down")
        self.assertFalse(review_receipt.check(self.event(), broken)[0])


PR_HEAD = "c" * 40
MAIN_SHA = "a" * 40


def receipt_api(runs_list, pulls_for_sha=(), checks=(), pr_ref="claude/x"):
    calls = []

    def fetch(path):
        calls.append(path)
        if path.startswith("actions/workflows/review-receipt.yml/runs"):
            return {"workflow_runs": list(runs_list)}
        if path == f"commits/{PR_HEAD}/pulls":
            return [{"number": n} for n in pulls_for_sha]
        if path.startswith("pulls/"):
            return {"head": {"sha": PR_HEAD, "ref": pr_ref}}
        if path.startswith(f"commits/{PR_HEAD}/check-runs"):
            return {"check_runs": list(checks)}
        raise AssertionError(path)
    fetch.calls = calls
    return fetch


def trigger_event(pull_requests=(5,)):
    return {"workflow_run": {"head_sha": PR_HEAD,
                             "pull_requests": [{"number": n} for n in pull_requests]}}


def target_run(rid, prs=(), branch="main", at="2026-11-07T12:00:00Z"):
    # A pull_request_target run records main's commit as its head SHA.
    return {"id": rid, "head_sha": MAIN_SHA, "head_branch": branch, "created_at": at,
            "pull_requests": [{"number": n} for n in prs]}


class FindReceiptRunTest(unittest.TestCase):
    def test_finds_the_run_by_pr_although_its_sha_is_mains(self):
        api = receipt_api([target_run(11, prs=(4,)), target_run(12, prs=(5,))])
        self.assertEqual(12, review_receipt.find_receipt_run(trigger_event(), api))
        self.assertFalse(any(f"head_sha={PR_HEAD}" in c for c in api.calls))

    def test_newest_run_for_the_pr_wins(self):
        api = receipt_api([target_run(12, prs=(5,), at="2026-11-07T10:00:00Z"),
                           target_run(13, prs=(5,), at="2026-11-07T12:00:00Z")])
        self.assertEqual(13, review_receipt.find_receipt_run(trigger_event(), api))

    def test_pr_number_from_the_commit_when_the_event_has_none(self):
        api = receipt_api([target_run(12, prs=(5,))], pulls_for_sha=(5,))
        self.assertEqual(12, review_receipt.find_receipt_run(trigger_event(()), api))

    def test_check_run_on_the_pr_head_when_runs_list_no_pr(self):
        checks = [{"started_at": "2026-11-07T12:00:00Z",
                   "details_url": "https://github.com/o/r/actions/runs/21/job/99"}]
        api = receipt_api([target_run(21), target_run(22)], checks=checks)
        self.assertEqual(21, review_receipt.find_receipt_run(trigger_event(), api))

    def test_check_run_from_another_workflow_is_not_rerun(self):
        checks = [{"details_url": "https://github.com/o/r/actions/runs/77/job/1"}]
        api = receipt_api([target_run(21, branch="other")], checks=checks)
        self.assertIsNone(review_receipt.find_receipt_run(trigger_event(), api))

    def test_head_branch_as_last_resort(self):
        api = receipt_api([target_run(31, branch="claude/x")])
        self.assertEqual(31, review_receipt.find_receipt_run(trigger_event(), api))

    def test_nothing_found(self):
        self.assertIsNone(review_receipt.find_receipt_run(trigger_event(), receipt_api([])))
        self.assertIsNone(review_receipt.find_receipt_run({}, receipt_api([target_run(1, prs=(5,))])))


if __name__ == "__main__":
    unittest.main()
