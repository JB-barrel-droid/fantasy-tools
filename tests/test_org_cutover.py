"""Org prep: URL selection and queue gate execute without external services."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from urllib.parse import urljoin
from pipelines.ci_pr_gate import run

ROOT = Path(__file__).resolve().parents[1]

class OrgCutoverTests(unittest.TestCase):
    def test_repository_url_selection(self):
        for slug, owner in (("", "jb-barrel-droid"), ("datadrivenfootball/fantasy-tools", "datadrivenfootball")):
            result = subprocess.run([sys.executable, "-m", "pipelines.lib.repository"], cwd=ROOT,
                env={**os.environ, "DDF_GITHUB_REPOSITORY": slug}, capture_output=True, text=True, check=True)
            self.assertEqual(result.stdout.strip(), f"https://{owner}.github.io/fantasy-tools/")

    def test_merge_group_runs_gate_and_verification_without_pr_read(self):
        with tempfile.TemporaryDirectory() as td:
            paths = {k: str(Path(td) / k) for k in ("GITHUB_EVENT_PATH", "GITHUB_OUTPUT", "GITHUB_STEP_SUMMARY")}
            Path(paths["GITHUB_EVENT_PATH"]).write_text(json.dumps({"action": "checks_requested"}))
            env = {**paths, "GITHUB_EVENT_NAME": "merge_group"}
            def no_fetch(*args):
                self.fail("merge_group must verify its merge SHA without reading a PR")
            for phase in ("gate", "verify"):
                self.assertEqual(run(phase, env, no_fetch), 0)
            self.assertIn("run_expensive=true", Path(paths["GITHUB_OUTPUT"]).read_text())

    def test_queue_workflows_subscribe(self):
        for name in ("preview", "v2-render-test", "waivers-mutation-offline"):
            text = (ROOT / f".github/workflows/{name}.yml").read_text()
            self.assertIn("  merge_group:\n    types: [checks_requested]", text)

    def test_connect_links_follow_both_pages_origins_and_v2_base(self):
        from pipelines.build_v2_page import build_v2_html
        shell = (ROOT / "app/v2/shell.html").read_text()
        index = (ROOT / "app/trade-value-chart/index.html").read_text()
        for owner in ("jb-barrel-droid", "datadrivenfootball"):
            site = f"https://{owner}.github.io/fantasy-tools/"
            for at_root in (True, False):
                html = build_v2_html(index, shell, at_root=at_root, posts=[])
                self.assertIn('href="connect/"', html)
                base = site if at_root else urljoin(site + 'v2/', '../')
                self.assertEqual(urljoin(base, 'connect/'), site + 'connect/')
