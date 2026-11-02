"""JEG-1451: routing must not silently omit risky changes or known regressions."""
import json
import os
import re
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

from pipelines import fast_gate
from pipelines.fast_gate_history import capture, regression_audit, report
from tests.test_workflow_script_paths import _run_bodies_text
from tests.test_validate_shards import shard_targets

ROOT = fast_gate.ROOT
SNAPSHOT = ROOT / "tests/fast_gate_history.json"


class MappingTest(unittest.TestCase):
    def test_full_selection_keeps_validate_and_the_complete_nightly_list(self):
        config = fast_gate.load_mapping()
        commands = [cmd for name in config["full_shards"] for cmd in config["shards"][name]["commands"]]
        self.assertIn("smoke", config["full_shards"])
        for target in ["validate-base", "test-unit", *shard_targets((ROOT / "Makefile").read_text())]:
            self.assertIn(["make", target], commands)

    def test_three_sample_prs(self):
        docs = fast_gate.plan(["docs/claude-log/new-inert-record.md"])
        self.assertTrue(docs["docs_only"])
        self.assertEqual(["smoke"], docs["shards"])
        frontend = fast_gate.plan(["app/v2/waivers.js", "docs/claude-log/change.md"])
        self.assertFalse(frontend["full"])
        self.assertEqual(["smoke", "fe-waivers"], frontend["shards"])
        engine = fast_gate.plan(["app/trade-value-chart/assets/value-model.js"])
        self.assertTrue(engine["full"])
        self.assertEqual(fast_gate.load_mapping()["full_shards"], engine["shards"])

    def test_full_coverage_preserves_touched_page_renders_outside_nightly(self):
        selected = fast_gate.plan([".github/workflows/preview.yml", "app/v2/league.js"])
        self.assertTrue(selected["full"])
        self.assertIn("fe-league", selected["shards"])
        self.assertTrue(set(fast_gate.load_mapping()["full_shards"]) <= set(selected["shards"]))

    def test_every_page_is_narrow_and_mixed_paths_union(self):
        pages = {"targets.js": "fe-targets", "finder.js": "fe-finder", "trade.js": "fe-compare",
                 "league.js": "fe-league", "values-fieldnotes.css": "fe-values",
                 "settings-fieldnotes.js": "fe-settings", "waivers.css": "fe-waivers"}
        for path, shard in pages.items():
            with self.subTest(path=path):
                selected = fast_gate.plan(["app/v2/" + path])
                self.assertFalse(selected["full"])
                expected = {"smoke", shard} | ({"connector"} if path in ("finder.js", "trade.js") else set())
                self.assertEqual(expected, set(selected["shards"]))
        self.assertEqual({"smoke", "connector", "fe-compare", "fe-finder"}, set(fast_gate.plan(
            ["app/v2/trade.js", "app/v2/finder.js"])["shards"]))

    def test_shared_ui_runs_full_and_connector_stays_separate(self):
        self.assertTrue(fast_gate.plan(["app/v2/v2.js"])["full"])
        self.assertEqual({"smoke", "connector"}, set(fast_gate.plan(["supabase/functions/mcp/tools.ts"])["shards"]))

    def test_page_modules_loaded_by_the_connector_select_both_consumers(self):
        files = [ROOT / "supabase/functions/mcp/analyses.ts", ROOT / "supabase/functions/mcp/index.ts",
                 ROOT / "supabase/functions/get-values/index.ts"]
        paths = set()
        for file in files:
            paths.update("app/" + p for p in re.findall(r'(v2/[a-z-]+\.js)', file.read_text()))
        self.assertGreaterEqual(len(paths), 7)
        for path in paths:
            with self.subTest(path=path):
                selected = fast_gate.plan([path])
                self.assertTrue(selected["full"] or "connector" in selected["shards"], path)

    def test_pipelines_run_integration_identity_guards_and_paired_test(self):
        self.assertTrue(fast_gate.plan(["pipelines/sync_players_active.py"])["full"])
        # Exercise the isolated CLI-producer path separately from imported modules.
        data = dict(fast_gate.inventory(), shared_pipelines=set())
        with mock.patch.object(fast_gate, "inventory", return_value=data):
            selected = fast_gate.plan(["pipelines/sync_players_active.py"])
        self.assertEqual(["smoke", "pipelines"], selected["shards"])
        self.assertIn("tests.test_sync_players_active", selected["paired_tests"])
        commands = fast_gate.load_mapping()["shards"]["pipelines"]["commands"]
        self.assertIn(["make", "test-integration"], commands)
        self.assertTrue(any("tests.test_cbsros_bake_identity" in cmd for cmd in commands))
        self.assertTrue(fast_gate.plan(["pipelines/new_uncovered_producer.py"])["full"])

    def test_risky_paths_and_empty_or_unknown_diff_fail_closed_to_full(self):
        paths = ["app/trade-value-chart/assets/fractional-seats.js", "pipelines/value_reference.py",
                 "pipelines/spec_reference/value_pipeline.py", "pipelines/lib/roster_convention.py",
                 "pipelines/bake_players.py", "supabase/functions/get-values/pipeline.ts",
                 "config/roster.json", "config/fast_gate.json", "pipelines/fast_gate.py",
                 "pipelines/fast_gate_history.py", "tests/test_fast_gate.py", "tests/fast_gate_history.json",
                 ".github/workflows/preview.yml", ".github/actions/new/action.yml", "Makefile",
                 "docs/methodology.md", "docs/feature-contract.md", "docs/use-ddf-in-claude-chatgpt.md",
                 "tests/_dist_server.py", "tests/fixtures/example.json", "some/new/path.js"]
        for path in paths:
            with self.subTest(path=path):
                self.assertTrue(fast_gate.plan([path])["full"])
        self.assertTrue(fast_gate.plan([])["full"])
        self.assertTrue(fast_gate.plan(["README.md"], force_full=True)["full"])

    def test_build_markdown_is_not_docs_only(self):
        selected = fast_gate.plan(["app/llm/skill/SKILL.md"])
        self.assertFalse(selected["docs_only"])
        self.assertTrue(selected["full"])

    def test_mapped_tests_select_their_owners_and_unknown_tests_run_full(self):
        self.assertIn("fe-finder", fast_gate.plan(["tests/test_v2_finder.py"])["shards"])
        self.assertIn("fe-waivers", fast_gate.plan(["tests/test_waivers_mutation_specificity.py"])["shards"])
        self.assertTrue(fast_gate.plan(["tests/test_new_behavior.py"])["full"])
        helper = fast_gate.plan(["tests/node/mcp_unmatched_check.mjs"])
        self.assertEqual({"smoke", "connector"}, set(helper["shards"]))
        self.assertTrue(fast_gate.plan(["tests/node/new_unowned_helper.mjs"])["full"])

    def test_invalid_paths_and_broken_mapping_do_not_pass(self):
        for path in ("../escape", "/absolute", "app/../escape", "a\\b"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                fast_gate.plan([path])
        config = fast_gate.load_mapping()
        config["rules"][0]["shards"] = ["missing"]
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "mapping.json"
            path.write_text(json.dumps(config))
            with self.assertRaises(ValueError):
                fast_gate.load_mapping(path)
            config = fast_gate.load_mapping()
            config["shards"]["fe-waivers"]["commands"] = []
            path.write_text(json.dumps(config))
            with self.assertRaises(ValueError):
                fast_gate.load_mapping(path)

    def test_selected_commands_exist_and_unittest_does_not_silently_find_nothing(self):
        config = fast_gate.load_mapping()
        loader = unittest.TestLoader()
        for shard in config["shards"].values():
            for command in shard["commands"]:
                if command[:3] == ["python3", "-m", "unittest"]:
                    for module in command[3:]:
                        if module == "tests.test_fast_gate":
                            continue
                        suite = loader.loadTestsFromName(module)
                        self.assertGreater(suite.countTestCases(), 0, module)
        self.assertEqual([], loader.errors)

    def test_runner_preserves_failures_and_continues_with_baseline_attribution(self):
        config = {"shards": {"example": {"commands": [["make", "first"], ["make", "second"]]}}}
        with mock.patch.object(fast_gate.subprocess, "run", side_effect=[
                subprocess.CompletedProcess([], 2), subprocess.CompletedProcess([], 0)]) as run:
            self.assertEqual(1, fast_gate.run_shard("example", config))
        self.assertEqual(2, run.call_count)
        self.assertIn("pipelines.baseline_reds", run.call_args_list[0].args[0])
        self.assertEqual(["make", "first"], run.call_args_list[0].args[0][-2:])

    def test_paired_puller_tests_use_pytest_and_propagate_no_collection_failure(self):
        config = {"shards": {"pipelines": {"commands": []}}}
        with mock.patch.object(fast_gate.subprocess, "run", return_value=
                               subprocess.CompletedProcess([], 5)) as run:
            self.assertEqual(1, fast_gate.run_shard("pipelines", config, ["tests.test_pull_rotoballer"]))
        self.assertIn("pytest", run.call_args.args[0])
        self.assertEqual("tests/test_pull_rotoballer.py", run.call_args.args[0][-1])
        with self.assertRaises(ValueError):
            fast_gate.run_shard("pipelines", config, ["../bad"])


class HistoryTest(unittest.TestCase):
    def test_last_30_merged_pr_file_lists_through_mapper_and_regression_audit(self):
        snapshot = json.loads(SNAPSHOT.read_text())
        self.assertEqual(30, len(snapshot["prs"]))
        self.assertEqual(30, len({pr["number"] for pr in snapshot["prs"]}))
        for pr in snapshot["prs"]:
            selected = fast_gate.plan(pr["files"])
            self.assertIn("smoke", selected["shards"], pr["number"])
            self.assertEqual(pr["expected_shards"], selected["shards"], pr["number"])
            self.assertEqual(pr["expected_full"], selected["full"], pr["number"])
        rows = regression_audit(snapshot, snapshot["regressions"])
        self.assertTrue(rows)
        self.assertTrue(all(not r["skipped_broken_area"] for r in rows), rows)
        self.assertIn("#1179", report(snapshot, snapshot["regressions"]))

    def test_a_mapper_that_skips_the_documented_broken_area_is_flagged(self):
        snapshot = json.loads(SNAPSHOT.read_text())
        broken = lambda paths: {"full": False, "shards": ["smoke", "fe-values"]}
        rows = regression_audit(snapshot, snapshot["regressions"], planner=broken)
        self.assertEqual([["pipelines"], ["connector"]], [r["skipped_broken_area"] for r in rows])

    def test_snapshot_file_lists_match_git_when_pinned_main_is_available(self):
        snapshot = json.loads(SNAPSHOT.read_text())
        # A depth-2 full-suite checkout cannot recapture the history. The plan
        # job fetches all history; standalone fixture replay is always tested.
        available = subprocess.run(["git", "cat-file", "-e", snapshot["prs"][-1]["sha"] + "^1"],
                                   cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0
        if not available:
            self.skipTest("history recapture needs full git history; stored 30-PR replay still runs")
        actual = capture(snapshot["main_sha"])
        for saved, found in zip(snapshot["prs"], actual["prs"]):
            self.assertEqual({k: saved[k] for k in found}, found)

    def test_git_merge_base_and_both_sides_of_a_rename(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            def git(*args):
                return subprocess.check_output(["git", *args], cwd=root, text=True).strip()
            git("init", "-q")
            git("config", "user.name", "Fast gate test")
            git("config", "user.email", "test@example.invalid")
            git("commit", "--allow-empty", "-qm", "Initial commit")
            (root / "value-model.js").write_text("engine")
            git("add", ".")
            git("commit", "-qm", "Base (#1)")
            branch = git("branch", "--show-current")
            git("checkout", "-qb", "topic")
            git("mv", "value-model.js", "guide.md")
            git("commit", "-qm", "Move (#2)")
            head = git("rev-parse", "HEAD")
            git("checkout", "-q", branch)
            (root / "unrelated.txt").write_text("main advanced")
            git("add", ".")
            git("commit", "-qm", "Bot refresh")
            self.assertEqual({"value-model.js", "guide.md"}, set(fast_gate.changed_paths("HEAD", head, root)))
            history = capture(head, 2, root)
            self.assertEqual([2, 1], [pr["number"] for pr in history["prs"]])
            self.assertEqual({"value-model.js", "guide.md"}, set(history["prs"][0]["files"]))


class WorkflowTest(unittest.TestCase):
    def test_aggregate_does_not_turn_failures_skips_or_drafts_into_success(self):
        workflow = (ROOT / ".github/workflows/fast-gate.yml").read_text()
        final = _run_bodies_text(workflow)[-1]
        with tempfile.TemporaryDirectory() as temp:
            fake = Path(temp) / "python3"
            fake.write_text("#!/bin/sh\nexit 0\n")
            fake.chmod(0o755)
            env = {**os.environ, "PATH": temp + ":" + os.environ["PATH"],
                   "GITHUB_STEP_SUMMARY": str(Path(temp) / "summary")}
            cases = [("success", "success", "true", "true", 0),
                     ("success", "skipped", "false", "true", 0),
                     ("failure", "success", "true", "true", 1),
                     ("cancelled", "skipped", "false", "true", 1),
                     ("success", "skipped", "true", "true", 1),
                     ("success", "failure", "true", "true", 1),
                     ("success", "cancelled", "true", "true", 1),
                     ("success", "skipped", "", "true", 1),
                     ("success", "success", "true", "false", 1)]
            for plan_result, shard_result, has_shards, expensive, code in cases:
                with self.subTest(case=(plan_result, shard_result, has_shards, expensive)):
                    result = subprocess.run(["bash", "-e", "-c", final], env={**env,
                        "PLAN_RESULT": plan_result, "SHARD_RESULT": shard_result,
                        "HAS_SHARDS": has_shards, "RUN_EXPENSIVE": expensive})
                    self.assertEqual(code, result.returncode)


if __name__ == "__main__":
    unittest.main()
