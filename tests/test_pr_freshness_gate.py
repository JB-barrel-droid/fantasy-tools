"""Fake REST evidence pins fail-closed promotion decisions (JEG-1466)."""

import base64
import copy
import io
import json
from pathlib import Path
import tempfile
from contextlib import redirect_stdout
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from pipelines import pr_freshness_gate as gate, pr_promotion

MAIN, HEAD = "a" * 40, "b" * 40


def check(conclusion="success", **changes):
    return {"name": "test", "status": "completed", "conclusion": conclusion,
            "head_sha": HEAD, "app": {"slug": "github-actions"}, **changes}


def full_ci(head=HEAD):
    # Literal policy names: don't generate evidence from the implementation's
    # required set, which could hide an accidentally removed requirement.
    return [check(name="preview", head_sha=head), check(name="v2-render", head_sha=head)]


class FakeRest:
    repo = gate.REPO

    def __init__(self, checks=None, states=None, behind=0):
        self.checks = full_ci() if checks is None else checks
        self.states = [] if states is None else states
        self.behind = behind
        self.calls = []
        self.entries = None
        self.main_reads = self.pull_reads = 0
        self.move_main = self.move_head = False

    def get(self, path):
        self.calls.append(path)
        if path == "commits/main":
            self.main_reads += 1
            return {"sha": "c" * 40 if self.move_main and self.main_reads > 1 else MAIN}
        if path == "pulls/7":
            self.pull_reads += 1
            return {"state": "open", "head": {"sha": "c" * 40 if self.move_head
                                             and self.pull_reads > 1 else HEAD},
                    "base": {"ref": "main", "repo": {"full_name": self.repo}}}
        if path == f"compare/main...{HEAD}":
            return {"behind_by": self.behind}
        if path == f"contents/{gate.REGISTRY}?ref={MAIN}":
            if self.entries is None:
                raise gate.NotFound("absent")
            return {"encoding": "base64", "content": base64.b64encode(
                json.dumps(self.entries).encode()).decode()}
        if path.startswith(f"commits/{HEAD}/check-runs?"):
            page = int(path.rsplit("=", 1)[1])
            return {"total_count": len(self.checks),
                    "check_runs": copy.deepcopy(self.checks[(page - 1) * 100:page * 100])}
        if path.startswith(f"commits/{HEAD}/status?"):
            page = int(path.rsplit("=", 1)[1])
            return {"sha": HEAD, "total_count": len(self.states),
                    "statuses": copy.deepcopy(self.states[(page - 1) * 100:page * 100])}
        raise AssertionError(f"unexpected REST path: {path}")


class FreshnessTest(unittest.TestCase):
    def verdict(self, api, args=None, **kwargs):
        with redirect_stdout(io.StringIO()) as output:
            rc = gate.main(args or ["7"], api=api, **kwargs)
        self.assertEqual(1, len(output.getvalue().splitlines()))
        return rc, output.getvalue()

    def test_green_subset_never_authorizes_missing_required_checks(self):
        # Reviewer's reproduction: a quick green check registers before the
        # full preview/render workflows. Informational success isn't CI proof.
        for name in ("security-contracts", "PR freshness (informational)",
                     "preview", "v2-render"):
            with self.subTest(name=name):
                rc, reason = gate.evaluate(FakeRest(checks=[check(name=name)]), number=7)
                self.assertEqual(1, rc)
                self.assertIn("missing required checks", reason)

    def test_required_checks_must_each_register_and_succeed(self):
        api = FakeRest(checks=[check(name="preview")])
        self.assertEqual(1, self.verdict(api)[0])
        api.checks.append(check(name="v2-render", status="queued", conclusion=None))
        self.assertEqual(1, self.verdict(api)[0])
        api.checks[-1] = check(name="v2-render")
        self.assertEqual(0, self.verdict(api)[0])

    def test_required_checks_cannot_be_neutral_skipped_or_from_another_app(self):
        for name in ("preview", "v2-render"):
            for conclusion in ("neutral", "skipped", "failure"):
                with self.subTest(name=name, conclusion=conclusion):
                    rows = [row for row in full_ci() if row["name"] != name]
                    rows.append(check(name=name, conclusion=conclusion, output={
                        "summary": "skipped-by-path: documentation-only"}))
                    self.assertEqual(1, self.verdict(FakeRest(checks=rows))[0])
            rows = [row for row in full_ci() if row["name"] != name]
            rows.append(check(name=name, app={"slug": "another-app"}))
            self.assertEqual(1, self.verdict(FakeRest(checks=rows))[0])

    def test_commit_statuses_and_manual_checks_cannot_substitute_for_required_jobs(self):
        api = FakeRest(checks=[check(name="preview-manual"), check(name="v2-render-manual")],
                       states=[{"context": "preview", "state": "success"},
                               {"context": "v2-render", "state": "success"}])
        self.assertEqual(1, self.verdict(api)[0])

    def test_behind_refused(self):
        rc, text = self.verdict(FakeRest(behind=1))
        self.assertEqual(1, rc)
        self.assertIn("behind main", text)

    def test_main_merged_in_accepted_without_rebase_test(self):
        # Diverged history is fine once main is an ancestor: compare behind=0.
        api = FakeRest(behind=0)
        self.assertEqual(0, self.verdict(api)[0])
        self.assertIn(f"compare/main...{HEAD}", api.calls)
        self.assertFalse(any("graphql" in path for path in api.calls))

    def test_green_checks_and_statuses_accepted(self):
        self.assertEqual(0, self.verdict(FakeRest(
            checks=full_ci() + [check(), check("neutral"), check("skipped", output={
                "summary": "skipped-by-path: documentation-only"})],
            states=[{"state": "success"}]))[0])

    def test_red_and_generic_skip_refused(self):
        for conclusion in ("failure", "cancelled", "timed_out", "action_required", "skipped", None):
            with self.subTest(conclusion=conclusion):
                self.assertEqual(1, self.verdict(FakeRest(checks=[check(conclusion)]))[0])
        for state in ("failure", "error", "pending", None):
            with self.subTest(state=state):
                self.assertEqual(1, self.verdict(FakeRest(states=[{"state": state}]))[0])

    def test_pending_check_refused_even_with_old_success_conclusion(self):
        for status in ("queued", "in_progress", "waiting", "pending"):
            with self.subTest(status=status):
                self.assertEqual(1, self.verdict(FakeRest(checks=[check(status=status)]))[0])

    def test_empty_evidence_and_invalid_compare_refused(self):
        self.assertEqual(1, self.verdict(FakeRest(checks=[]))[0])
        for behind in (None, "0", False, -1):
            with self.subTest(behind=behind):
                self.assertEqual(2, self.verdict(FakeRest(behind=behind))[0])

    def test_api_errors_at_every_read_fail_closed_without_retry(self):
        reference = FakeRest()
        self.verdict(reference)
        for index in range(len(reference.calls)):
            api = FakeRest()
            original = api.get
            calls = []

            def fetch(path):
                calls.append(path)
                if len(calls) == index + 1:
                    raise gate.EvidenceError("API down")
                return original(path)

            api.get = fetch
            with self.subTest(index=index):
                self.assertEqual(2, self.verdict(api)[0])
                self.assertEqual(index + 1, len(calls))

    def test_head_or_main_moving_refused(self):
        for attribute in ("move_main", "move_head"):
            api = FakeRest()
            setattr(api, attribute, True)
            self.assertEqual(1, self.verdict(api)[0])

    def test_check_for_different_head_refused(self):
        self.assertEqual(2, self.verdict(FakeRest(checks=[check(head_sha=MAIN)]))[0])

    def test_red_on_second_page_cannot_hide(self):
        self.assertEqual(1, self.verdict(FakeRest(checks=[check()] * 100 + [check("failure")]))[0])
        self.assertEqual(1, self.verdict(FakeRest(states=[{"state": "success"}] * 100
                                               + [{"state": "pending"}]))[0])

    def test_registry_read_from_main_only_and_does_not_waive_red(self):
        api = FakeRest(checks=[check("failure")])
        api.entries = [{"test_id": "tests.test_example.Test.test_bad", "where": ["CI"]}]
        rc, text = self.verdict(api)
        self.assertEqual(1, rc)
        self.assertIn("attribution only", text)
        self.assertIn(f"contents/{gate.REGISTRY}?ref={MAIN}", api.calls)
        api.entries = {"waive_all": True}
        self.assertEqual(2, self.verdict(api)[0])

    def test_merge_group_head_uses_same_gate(self):
        api = FakeRest()
        self.assertEqual(0, self.verdict(api, ["--merge-group", HEAD])[0])
        self.assertNotIn("pulls/7", api.calls)
        self.assertEqual(1, self.verdict(FakeRest(checks=[check(name="preview")]),
                                        ["--merge-group", HEAD])[0])

    def test_information_only_excludes_exact_self_run_and_never_authorizes_promotion(self):
        own = check(status="in_progress", name="PR freshness (informational)",
                    app={"slug": "github-actions"},
                    details_url=f"https://github.com/{gate.REPO}/actions/runs/42/job/10")
        env = {"GITHUB_ACTIONS": "true", "GITHUB_RUN_ID": "42",
               "GITHUB_WORKFLOW": "PR freshness", "GITHUB_REPOSITORY": gate.REPO}
        args = ["7", "--informational"]
        self.assertIn("PASS:", self.verdict(FakeRest(checks=full_ci() + [own]), args, environ=env)[1])
        self.assertEqual(1, self.verdict(FakeRest(checks=[check(), own]))[0])
        other = {**own, "details_url": own["details_url"].replace("runs/42", "runs/43")}
        self.assertIn("REFUSED:", self.verdict(FakeRest(checks=[check(), other]), args, environ=env)[1])
        self.assertIn("REFUSED:", self.verdict(FakeRest(checks=[own]), args, environ=env)[1])
        self.assertIn("REFUSED:", self.verdict(FakeRest(), args, environ={})[1])

    def test_rest_calls_only_get_and_does_not_echo_api_error(self):
        with patch.object(gate.subprocess, "run", return_value=SimpleNamespace(
                returncode=1, stdout="private API body", stderr="request rejected")) as execute:
            rc, text = self.verdict(gate.Rest(gate.REPO))
        self.assertEqual(2, rc)
        self.assertNotIn("private API body", text)
        self.assertNotIn("request rejected", text)
        self.assertEqual(["gh", "api", "--method", "GET"], execute.call_args.args[0][:4])
        execute.assert_called_once()


class PromotionTest(unittest.TestCase):
    def test_green_subset_blocks_both_promotion_entry_points(self):
        for action in ("ready-for-review", "merge-gate"):
            with self.subTest(action=action):
                execute = Mock()
                self.assertEqual(1, pr_promotion.main(
                    [action, "7"], gate=lambda _: gate.evaluate(FakeRest(
                        checks=[check(name="security-contracts")]), number=7)[0], execute=execute))
                execute.assert_not_called()

    def test_refused_gate_never_promotes(self):
        for action in ("ready-for-review", "merge-gate"):
            execute = Mock()
            self.assertEqual(1, pr_promotion.main([action, "7"], gate=lambda _: 1, execute=execute))
            execute.assert_not_called()

    def test_ready_is_gated_and_merge_gate_never_merges(self):
        events = []

        def green(args):
            events.append("gate")
            return 0

        def execute(args, **kwargs):
            self.assertEqual("gate", events[-1])
            self.assertEqual(["gh", "pr", "ready", "7", "--repo", gate.REPO], args)
            events.append("ready")
            return SimpleNamespace(returncode=0)

        self.assertEqual(0, pr_promotion.main(["ready-for-review", "7"], green, execute))
        never = Mock()
        self.assertEqual(0, pr_promotion.main(["merge-gate", "7"], green, never))
        never.assert_not_called()


class BotOnlyBehindTest(unittest.TestCase):
    """Real local histories, fake REST checks: the standing exception stays opt-in."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.git = gate.LocalGit(self.root)
        self.git.run("init", "-q", "-b", "main")
        self.git.run("config", "user.name", "Test worker")
        self.git.run("config", "user.email", "worker@example.invalid")
        self.write("feature.txt", "base\n")
        self.git.run("add", ".")
        self.git.run("commit", "-qm", "base")
        self.base = self.git.run("rev-parse", "HEAD").strip()
        self.config = gate.load_config()
        self.config["allow_bot_only_behind"] = True

    def write(self, path, content):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)

    def history(self, pr_path="feature.txt", writes=None):
        self.git.run("switch", "-qc", "pr")
        self.write(pr_path, "PR change\n")
        self.git.run("add", ".")
        self.git.run("commit", "-qm", "PR")
        self.head = self.git.run("rev-parse", "HEAD").strip()
        self.git.run("switch", "-q", "main")
        self.skipped = []
        for path, identity in writes or [("dist/modules/ops-status.json", 0)]:
            author = (self.config["bot_authors"][identity] if isinstance(identity, int)
                      else identity)
            self.git.run("config", "user.name", author["name"])
            self.git.run("config", "user.email", author["email"])
            self.write(path, f"bot change {len(self.skipped)}\n")
            self.git.run("add", ".")
            self.git.run("commit", "-qm", "main write")
            self.skipped.append(self.git.run("rev-parse", "HEAD").strip())
        self.main = self.skipped[-1]
        self.git.run("update-ref", "refs/remotes/origin/main", self.main)
        self.git.run("switch", "-q", "pr")
        self.red = False

    def api(self):
        history = self

        class BotRest:
            repo = gate.REPO

            def get(self, path):
                if path == "commits/main":
                    return {"sha": history.main}
                if path == "pulls/7":
                    return {"state": "open", "head": {"sha": history.head},
                            "base": {"ref": "main", "repo": {"full_name": self.repo}}}
                if path == f"compare/main...{history.head}":
                    return {"behind_by": len(history.skipped)}
                if path == f"contents/{gate.REGISTRY}?ref={history.main}":
                    raise gate.NotFound("absent")
                if path == f"commits/{history.head}/check-runs?filter=latest&per_page=100&page=1":
                    rows = full_ci(history.head)
                    if history.red:
                        rows[0]["conclusion"] = "failure"
                    return {"total_count": len(rows), "check_runs": rows}
                if path == f"commits/{history.head}/status?per_page=100&page=1":
                    return {"sha": history.head, "total_count": 0, "statuses": []}
                raise AssertionError(f"unexpected REST path: {path}")

        return BotRest()

    def verdict(self):
        return gate.evaluate(self.api(), number=7, config=self.config, local_git=self.git)

    def test_flag_off_behind_still_refused_and_checked_in_defaults_stay_off(self):
        self.history()
        defaults = gate.load_config()
        self.assertFalse(defaults["allow_bot_only_behind"])
        self.assertFalse(defaults["allow_bot_data_inputs"])
        self.config = defaults
        self.assertEqual(1, self.verdict()[0])

    def test_status_only_bot_history_passes_and_names_all_skipped_commits(self):
        self.history(writes=[("dist/modules/ops-status.json", 0),
                             ("dist/modules/monitoring-summary.json", 1)])
        rc, reason = self.verdict()
        self.assertEqual(0, rc)
        self.assertIn("bot-only-behind:", reason)
        for commit in self.skipped:
            self.assertIn(commit, reason)
        self.assertEqual(self.head, self.git.run("rev-parse", "HEAD").strip())
        self.assertEqual("", self.git.run("status", "--porcelain"))

    def test_data_input_with_only_first_flag_refused(self):
        self.history(writes=[("data/inputs/espn_projections.csv", 0)])
        self.assertEqual(1, self.verdict()[0])

    def test_data_input_needs_both_flags(self):
        self.history(writes=[("data/inputs/espn_projections.csv", 0)])
        self.config["allow_bot_data_inputs"] = True
        self.assertEqual(0, self.verdict()[0])
        self.config["allow_bot_only_behind"] = False
        self.assertEqual(1, self.verdict()[0])

    def test_non_bot_commit_anywhere_in_main_history_refused(self):
        self.history(writes=[("dist/modules/ops-status.json", {
            "name": "Human", "email": "human@example.invalid"}),
            ("dist/modules/monitoring-summary.json", 0)])
        rc, reason = self.verdict()
        self.assertEqual(1, rc)
        self.assertIn("non-bot author", reason)

    def test_bot_name_with_unrecognized_email_refused(self):
        self.history(writes=[("dist/modules/ops-status.json", {
            "name": "github-actions[bot]", "email": "other@example.invalid"})])
        self.assertEqual(1, self.verdict()[0])

    def test_bot_commit_touching_pr_file_refused(self):
        self.history(pr_path="dist/modules/ops-status.json")
        rc, reason = self.verdict()
        self.assertEqual(1, rc)
        self.assertIn("PR file overlap", reason)

    def test_directory_file_merge_conflict_despite_disjoint_paths_refused(self):
        self.history(pr_path="dist/modules/ops-status.json/nested")
        rc, reason = self.verdict()
        self.assertEqual(1, rc)
        self.assertIn("merge-tree not clean", reason)

    def test_exact_current_head_not_green_refused(self):
        self.history()
        self.red = True
        self.assertEqual(1, self.verdict()[0])

    def test_unlisted_path_refused_even_with_data_flag(self):
        self.history(writes=[("pipelines/other_code.py", 0)])
        self.config["allow_bot_data_inputs"] = True
        self.assertEqual(1, self.verdict()[0])

    def test_stale_local_main_cannot_substitute_for_rest_main(self):
        self.history()
        self.git.run("update-ref", "refs/remotes/origin/main", self.base)
        rc, reason = self.verdict()
        self.assertEqual(1, rc)
        self.assertIn("differs from observed main", reason)

    def test_every_commit_inspected_not_just_net_changed_paths(self):
        self.history(writes=[("unlisted.txt", 0), ("dist/modules/ops-status.json", 0)])
        self.git.run("switch", "-q", "main")
        self.git.run("rm", "-q", "unlisted.txt")
        self.git.run("commit", "-qm", "undo unlisted write")
        self.main = self.git.run("rev-parse", "HEAD").strip()
        self.skipped.append(self.main)
        self.git.run("update-ref", "refs/remotes/origin/main", self.main)
        self.git.run("switch", "-q", "pr")
        self.assertEqual(1, self.verdict()[0])

    def test_fresh_success_names_fresh_rule(self):
        rc, reason = gate.evaluate(FakeRest(), number=7)
        self.assertEqual(0, rc)
        self.assertTrue(reason.startswith("fresh:"))


if __name__ == "__main__":
    unittest.main()
