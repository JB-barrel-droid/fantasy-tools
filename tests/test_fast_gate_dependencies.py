"""Review regressions: a narrow selection must include every known reader."""
import copy
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

from pipelines import fast_gate, fast_gate_dependencies as deps
from pipelines.ci_pr_gate import decide
from tests.test_draft_ci_workflows import event, live


class DependencyCoverageTest(unittest.TestCase):
    def test_shared_helper_keeps_its_page_shards_when_promoted_to_full(self):
        path = "tests/test_connector_analyses.py"
        config = fast_gate.load_mapping()
        owners = fast_gate.test_owners(config)[path]
        with mock.patch.object(fast_gate, "inventory", return_value={
            "shared_pipelines": set(), "test_helpers": {path}, "test_read_paths": []
        }):
            selected = fast_gate.plan([path], config)
        self.assertTrue(selected["full"])
        self.assertTrue(set(owners).issubset(selected["shards"]))

    def test_every_test_naming_a_mapped_page_is_in_its_shard(self):
        config = fast_gate.load_mapping()
        self.assertEqual({}, deps.coverage_gaps(config))
        waivers = deps.declared_tests(config["shards"]["fe-waivers"]["commands"])
        for name in ("test_waivers_render.py", "test_waivers_view_render.py", "test_waivers_paste_render.py"):
            self.assertIn("tests/" + name, waivers)
        finder = deps.declared_tests(config["shards"]["fe-finder"]["commands"])
        self.assertGreaterEqual(sum(Path(p).name.startswith("test_v2_finder_") for p in finder), 20)
        self.assertIn("tests/test_v2_extract_players.js", deps.declared_tests(config["shards"]["fe-league"]["commands"]))
        broken = copy.deepcopy(config)
        for command in broken["shards"]["fe-waivers"]["commands"]:
            if "tests/test_waivers_render.py" in command:
                command.remove("tests/test_waivers_render.py")
        self.assertIn("tests/test_waivers_render.py", deps.coverage_gaps(broken)["fe-waivers"])

    def test_test_read_document_manifest_is_current_and_every_reader_routes_full(self):
        config = fast_gate.load_mapping()
        self.assertEqual(deps.inventory()["test_read_paths"], config["test_read_paths"])
        for path in config["test_read_paths"]:
            with self.subTest(path=path):
                self.assertTrue(fast_gate.plan([path])["full"])
        for path in ("docs/README.md", "docs/import-health-schema.md", "docs/get-values.openapi.yaml",
                     "docs/baseline-reds/registry.json", "README.md"):
            self.assertTrue(fast_gate.plan([path])["full"], path)
        self.assertEqual(["smoke"], fast_gate.plan(["docs/claude-log/unreferenced-record.md"])["shards"])

    def test_all_imported_pipeline_modules_and_test_helpers_route_full(self):
        data = deps.inventory()
        for path in ("pipelines/week_state.py", "pipelines/publish_gate.py", "pipelines/dist_manifest.py",
                     "pipelines/main_write_guard.py"):
            self.assertIn(path, data["shared_pipelines"])
        for path in sorted(data["shared_pipelines"] | data["test_helpers"]):
            with self.subTest(path=path):
                self.assertTrue(fast_gate.plan([path])["full"])
        for path in ("pipelines/baseline_reds.py", "pipelines/baseline_runtime/sitecustomize.py",
                     "pipelines/ci_pr_gate.py", "app/v2/modules.js", "app/v2/shell.html"):
            self.assertTrue(fast_gate.plan([path])["full"], path)
        self.assertIn("tests/test_v2_finder_render.py", data["test_helpers"])

    def test_new_readers_importers_and_inert_doc_reads_are_discovered_without_a_hand_list(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            def write(path, text):
                file = root / path
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_text(text)
            write("Makefile", "")
            write("app/v2/probe.js", "")
            write("docs/claude-log/probe.md", "inert until a test reads it")
            write("pipelines/shared.py", "raise AssertionError('scanner must not execute this')")
            write("pipelines/consumer.py", "from . import shared")
            write("pipelines/dynamic.py", "")
            write("pipelines/dynamic_user.py", "import importlib\nimportlib.import_module('pipelines.dynamic')")
            write("tests/test_helper.py", "from pathlib import Path\nx=Path('app')/'v2'/'probe.js'\ny=Path('docs')/'claude-log'/'probe.md'")
            write("tests/test_consumer.py", "from tests import test_helper")
            initial = deps.inventory(root)
            expected = {"tests/test_helper.py", "tests/test_consumer.py"}
            self.assertEqual(expected, set(deps.page_tests(["app/v2/probe.js"], initial)))
            self.assertIn("pipelines/shared.py", initial["shared_pipelines"])
            self.assertIn("pipelines/dynamic.py", initial["shared_pipelines"])
            self.assertIn("tests/test_helper.py", initial["test_helpers"])
            self.assertIn("docs/claude-log/probe.md", initial["test_read_paths"])
            config = {"rules": [{"paths": ["app/v2/probe.js"], "shards": ["fe-probe"]}],
                      "shards": {"fe-probe": {"commands": deps.page_commands(sorted(expected), initial)}}}
            write("tests/test_new_reader.py", "source = 'app/v2/probe.js'")
            deps.inventory.cache_clear()
            changed = deps.inventory(root)
            self.assertEqual({"fe-probe": ["tests/test_new_reader.py"]}, deps.coverage_gaps(config, changed))
            write("tests/node/orphan.cjs", "const page = 'probe.js'")
            write("tests/test_native.js", "const page = 'probe.js'; require('node:test')")
            deps.inventory.cache_clear()
            changed = deps.inventory(root)
            missing = deps.coverage_gaps(config, changed)["fe-probe"]
            self.assertIn("tests/node/orphan.cjs", missing)
            self.assertIn("tests/test_native.js", missing)
            self.assertIn(["node", "--test", "tests/test_native.js"],
                          deps.page_commands(deps.page_tests(["app/v2/probe.js"], changed), changed))
            with mock.patch.object(fast_gate, "inventory", return_value=changed):
                self.assertTrue(fast_gate.plan(["docs/claude-log/probe.md"])["full"])
            (root / "docs/claude-log/probe.md").rename(root / "docs/claude-log/removed.md")
            deps.inventory.cache_clear()
            removed = deps.inventory(root)
            previous = fast_gate.load_mapping()
            previous["test_read_paths"].append("docs/claude-log/probe.md")
            self.assertNotIn("docs/claude-log/probe.md", removed["test_read_paths"])
            with mock.patch.object(fast_gate, "inventory", return_value=removed):
                self.assertTrue(fast_gate.plan(["docs/claude-log/probe.md"], previous)["full"])
        deps.inventory.cache_clear()


class RetargetTest(unittest.TestCase):
    def test_edited_replans_after_base_ref_or_sha_changes_and_old_snapshot_fails(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            def git(*args):
                return subprocess.check_output(["git", *args], cwd=root, text=True).strip()
            git("init", "-q")
            git("config", "user.name", "Fast gate test")
            git("config", "user.email", "test@example.invalid")
            file = root / "app/trade-value-chart/assets/value-model.js"
            file.parent.mkdir(parents=True)
            file.write_text("before")
            git("add", ".")
            git("commit", "-qm", "Original base")
            old_base = git("rev-parse", "HEAD")
            file.write_text("engine change")
            git("commit", "-qam", "Stacked base")
            stacked_base = git("rev-parse", "HEAD")
            log = root / "docs/claude-log/retarget-probe.md"
            log.parent.mkdir(parents=True)
            log.write_text("record")
            git("add", ".")
            git("commit", "-qm", "PR head")
            head = git("rev-parse", "HEAD")
            self.assertTrue(fast_gate.plan(fast_gate.changed_paths(stacked_base, head, root))["docs_only"])
            self.assertTrue(fast_gate.plan(fast_gate.changed_paths(old_base, head, root))["full"])
            snapshot = event(draft=False, sha=head)
            snapshot["pull_request"]["base"] = {"ref": "stacked", "sha": stacked_base}
            for ref, sha in (("main", old_base), ("stacked", old_base), ("main", stacked_base)):
                current = live(False, sha=head)
                current["base"] = {"ref": ref, "sha": sha}
                self.assertFalse(decide("pull_request", snapshot, current)[0])
                edited = copy.deepcopy(snapshot)
                edited["action"] = "edited"
                edited["changes"] = {"base": {"ref": {"from": "stacked"}, "sha": {"from": stacked_base}}}
                edited["pull_request"]["base"] = current["base"]
                self.assertTrue(decide("pull_request", edited, current)[0])
        workflow = (fast_gate.ROOT / ".github/workflows/fast-gate.yml").read_text()
        self.assertIn("converted_to_draft, edited]", workflow)
        self.assertIn("BASE_SHA: ${{ github.event.pull_request.base.sha }}", workflow)
        self.assertIn('--base "$BASE_SHA"', workflow)


if __name__ == "__main__":
    unittest.main()
