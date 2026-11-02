"""Org prep: URL selection and queue gate execute without external services."""
import json
import os
import ast
import re
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from urllib.parse import urljoin
from pipelines.ci_pr_gate import run

ROOT = Path(__file__).resolve().parents[1]

class OrgCutoverTests(unittest.TestCase):
    def run_with_repository(self, code, slug):
        result = subprocess.run([sys.executable, "-c", code], cwd=ROOT,
            env={**os.environ, "DDF_GITHUB_REPOSITORY": slug},
            capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_published_outputs_follow_repository_override(self):
        code = '''
import json, sys, tempfile, zipfile
from pathlib import Path
sys.path.insert(0, 'pipelines')
import build_llm_surfaces as llm
import sync_dashboard_artifacts as sync
import build_v2_page as v2
with tempfile.TemporaryDirectory() as td:
    dist = Path(td)
    llm.build(dist)
    outputs = {p: (dist / p).read_text() for p in (
        'llms.txt', 'ddf-skill/SKILL.md', 'mcp-server-card.json', '.well-known/mcp/server-card.json')}
    with zipfile.ZipFile(dist / 'ddf-skill.zip') as z:
        outputs['zip'] = z.read('data-driven-football/SKILL.md').decode()
    llm.build(dist, sync.SITE_URL)
    outputs['sync-llms'] = (dist / 'llms.txt').read_text()
    outputs['classic'] = sync.classic_redirect_html()
    outputs['engine'] = sync.classic_page_html('<html><head><title>DDF</title></head><body></body></html>')
    outputs['v2'] = v2.head_for_v2('<html><head><title>DDF</title></head><body></body></html>', at_root=True)
    print(json.dumps(outputs))
'''
        for slug, owner in (("", "jb-barrel-droid"), ("JB-barrel-droid/fantasy-tools", "jb-barrel-droid"),
                            ("datadrivenfootball/fantasy-tools", "datadrivenfootball")):
            with self.subTest(slug=slug):
                site = f"https://{owner}.github.io/fantasy-tools/"
                outputs = self.run_with_repository(code, slug)
                for name, content in outputs.items():
                    # The skill delegates site links to make_state tool results;
                    # it has no literal site URL, including in the upload zip.
                    if name not in ('ddf-skill/SKILL.md', 'zip'):
                        self.assertIn(site, content, name)
                    self.assertNotIn("{{DDF_", content, name)
                    if owner == 'datadrivenfootball':
                        self.assertNotIn('jb-barrel-droid.github.io', content, name)
                self.assertEqual(outputs['zip'], outputs['ddf-skill/SKILL.md'])

    def test_published_monitor_links_follow_repository_override(self):
        code = '''
import json, sys
sys.path.insert(0, 'pipelines')
import sync_dashboard_artifacts as sync
print(json.dumps(sync.module_dashboard_html((sync.MODULES / 'dashboard.html').read_text())))
'''
        for slug in ('', 'datadrivenfootball/fantasy-tools'):
            with self.subTest(slug=slug):
                html = self.run_with_repository(code, slug)
                repository = slug or 'JB-barrel-droid/fantasy-tools'
                site = f'https://{repository.split("/")[0].lower()}.github.io/fantasy-tools/'
                self.assertIn(site, html)
                self.assertIn(f'https://api.github.com/repos/{repository}/', html)
                self.assertNotIn('{{DDF_', html)

    def test_live_probes_and_status_follow_repository_override(self):
        code = '''
import json, sys
sys.path.insert(0, 'pipelines')
import fidelity_pulse as f, check_source_fidelity as c, health_artifacts_watch as h
import monitor_alerts as m, build_ops_status as o, build_github_actions_status as g
import production_verify as p, build_pipeline_checkpoints as b
import verify_live as v
print(json.dumps({'urls': [f.SITE, f.SITE_FIXTURE, f.VALUE_CHECK_URL, f.UA,
    f.SITE_HISTORY, f.RANK_GUARD_URL, c.PAGES_URL, h.BASE_URL, m.STATUS_PAGE, o.SITE, v.BASE],
    'repos': [o.REPO, g.REPO, p.REPO, b.REPOSITORY]}))
'''
        for slug, owner in (("", "jb-barrel-droid"), ("datadrivenfootball/fantasy-tools", "datadrivenfootball")):
            with self.subTest(slug=slug):
                result = self.run_with_repository(code, slug)
                for url in result['urls']:
                    self.assertIn(f'https://{owner}.github.io/fantasy-tools/', url)
                self.assertEqual(result['repos'], [slug or 'JB-barrel-droid/fantasy-tools'] * 4)

    def test_build_and_status_workflows_export_shared_repository_variable(self):
        # Workflow-level env reaches every build, matrix shard, and status job.
        names = ('pages', 'preview', 'v2-render-test', 'full-suite', 'render-sweep',
                 'jeg1140-settings-render', 'waivers-mutation-offline', 'bake-players',
                 'rebuild-chain', 'fidelity-pulse', 'health-artifacts', 'player-identity-reconcile',
                 'live-page-synthetic', 'main-writer-checks')
        for name in names:
            with self.subTest(workflow=name):
                text = (ROOT / f'.github/workflows/{name}.yml').read_text()
                top_env = re.search(r'^env:\n((?:[ \t]+[^\n]*\n|\n)+)', text, re.M)
                self.assertIsNotNone(top_env, name)
                self.assertIn('  DDF_GITHUB_REPOSITORY: ${{ vars.DDF_GITHUB_REPOSITORY }}', top_env.group(1))
                # Nested overrides would defeat inheritance from this source.
                self.assertEqual(text.count('DDF_GITHUB_REPOSITORY:'), 1)

    def test_deploy_status_uses_shared_repository(self):
        with tempfile.TemporaryDirectory() as td:
            gh = Path(td) / 'gh'
            gh.write_text('#!/bin/sh\nprintf "%s\\n" "$@"\n')
            gh.chmod(0o755)
            for slug in ('', 'datadrivenfootball/fantasy-tools'):
                with self.subTest(slug=slug):
                    result = subprocess.run(['make', '-s', 'deploy-status'], cwd=ROOT,
                        env={**os.environ, 'DDF_GITHUB_REPOSITORY': slug,
                             'PATH': f'{td}:{Path(sys.executable).parent}:{os.environ["PATH"]}'},
                        capture_output=True, text=True, check=True)
                    self.assertEqual(result.stdout.splitlines(), ['run', 'list', '--repo',
                        slug or 'JB-barrel-droid/fantasy-tools', '--workflow', 'Deploy dashboard', '--limit', '5'])

    def test_repository_cleanup_has_no_duplicate_path_or_unused_site_import(self):
        tree = ast.parse((ROOT / 'pipelines/build_ops_status.py').read_text())
        inserts = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
                   and isinstance(n.func, ast.Attribute) and n.func.attr == 'insert'
                   and ast.unparse(n.func.value) in ('sys.path', '_sys.path')]
        self.assertEqual(len(inserts), 1)
        for name in ('build_github_actions_status', 'production_verify'):
            tree = ast.parse((ROOT / f'pipelines/{name}.py').read_text())
            imports = [a.name for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)
                       and n.module == 'lib.repository' for a in n.names]
            self.assertNotIn('SITE_URL', imports)

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
