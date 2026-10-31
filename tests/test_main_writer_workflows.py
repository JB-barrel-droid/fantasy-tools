"""JEG-1441: executable configuration contracts for privileged Git publication.

No YAML dependency in CI. Actionlint checks syntax; these guards discriminate
missing environment/ref/credential boundaries and duplicate deployment paths.
"""
from pathlib import Path
import re
import subprocess
import tempfile
import unittest
from tests.test_rebuild_chain_workflow import script_of, step_blocks

ROOT = Path(__file__).resolve().parents[1]
NAMES = ('espn-supabase-sync', 'espn-history-probe', 'espn-weekly-store',
         'player-status-history', 'player-trace-rebuild', 'rebuild-chain',
         'source-vintage-check', 'sleeper-identity-refresh', 'health-artifacts',
         'fidelity-pulse')
APP_BINDING = 'MAIN_WRITER_TOKEN: ${{ steps.main-writer.outputs.token }}'
APP_KEY = 'private-key: ${{ secrets.MAIN_WRITER_APP_PRIVATE_KEY }}'


def problems(text):
    errors = []
    prefix, separator, jobs = text.partition('jobs:\n')
    if not separator:
        return ['missing jobs']
    if not re.search(r'^  contents: read(?:\s|$)', prefix, re.M):
        errors.append('default token must have contents read')
    split = re.split(r'\n  [A-Za-z0-9_-]+-branch:\n', jobs, maxsplit=1)
    if len(split) != 2:
        return errors + ['missing separate branch job']
    main, branch = split
    header = main.split('    steps:', 1)[0]
    if '    environment: main-writer\n' not in header:
        errors.append('main job lacks the credential environment')
    if not re.search(r"^    if: .*github.ref == 'refs/heads/main'", header, re.M):
        errors.append('main job must require the main workflow ref')
    if not re.search(r'^    runs-on: ubuntu-latest(?:\s|$)', header, re.M):
        errors.append('main credentials require the hosted runner')
    if 'environment:' in branch:
        errors.append('branch job must have no environment')
    if "github.ref != 'refs/heads/main'" not in branch or "startsWith(github.ref, 'refs/heads/')" not in branch:
        errors.append('branch job must exclude main and non-branch refs')
    if not re.search(r'uses: actions/create-github-app-token@[0-9a-f]{40}\b', main):
        errors.append('App action must use an immutable source commit')
    if 'permission-contents: write' not in main or 'repositories: ${{ github.event.repository.name }}' not in main:
        errors.append('App token must be scoped to this repository contents')
    if 'app-id: ${{ secrets.MAIN_WRITER_APP_ID }}' not in main or main.count(APP_KEY) != 1:
        errors.append('App inputs must come only from the environment secrets')
    if 'skip-token-revoke: true' in main:
        errors.append('App token revocation must remain enabled')
    if 'persist-credentials: false' not in main:
        errors.append('checkout must not persist authentication')
    for block in re.split(r'^      - ', main, flags=re.M)[1:]:
        if 'git push "$@"' not in block:
            continue
        if APP_BINDING not in block or 'credential.helper' not in block or 'main-writer-credential.py' not in block:
            errors.append('every push step must use the ephemeral credential helper')
        if 'set -- origin "HEAD:${GITHUB_REF:?}"' not in block:
            errors.append('bare publication must have an explicit workflow-ref destination')
    return errors


class MainWriterWorkflowTest(unittest.TestCase):
    def test_linear_issue_creation_requires_explicit_dispatch(self):
        text = (ROOT/'.github/workflows/divergence-issues.yml').read_text()
        events = text.split('\non:\n', 1)[1].split('\npermissions:', 1)[0]
        self.assertEqual(re.findall(r'^  ([A-Za-z0-9_]+):', events, re.M),
                         ['workflow_dispatch'])

    def test_publication_wrappers_require_a_ref_before_calling_git(self):
        checked = 0
        for name in NAMES:
            text = (ROOT/f'.github/workflows/{name}.yml').read_text()
            for block in step_blocks(text):
                script = script_of(block)
                if not script or 'release_push()' not in script:
                    continue
                function = re.search(r'^release_push\(\) \{\n.*?^\}', script,
                                     flags=re.M | re.S).group()
                with tempfile.TemporaryDirectory() as td:
                    folder = Path(td)
                    binary = folder/'git'
                    binary.write_text('#!/bin/sh\n: > "$PROBE_MARKER"\n')
                    binary.chmod(0o700)
                    marker = folder/'git-was-called'
                    for ref in (None, ''):
                        env = {'PATH': td+':/usr/bin:/bin',
                               'PROBE_MARKER': str(marker)}
                        if ref is not None:
                            env['GITHUB_REF'] = ref
                        result = subprocess.run(
                            ['bash', '-e', '-c',
                             'release_guard() { :; }\n'+function+'\nrelease_push\n'],
                            cwd=folder, env=env, capture_output=True, text=True)
                        self.assertNotEqual(result.returncode, 0,
                                            name+': missing ref reached publication')
                        self.assertFalse(marker.exists(), name+': Git was called')
                checked += 1
        self.assertGreaterEqual(checked, len(NAMES))

    def test_ten_workflows_enforce_separate_main_and_branch_boundaries(self):
        for name in NAMES:
            with self.subTest(workflow=name):
                self.assertEqual(problems((ROOT/f'.github/workflows/{name}.yml').read_text()), [])

    def test_mutations_remove_real_security_boundaries(self):
        text = (ROOT/'.github/workflows/rebuild-chain.yml').read_text()
        mutations = [('    environment: main-writer\n', '', 'credential environment'),
                     ("github.ref == 'refs/heads/main'", "github.ref != ''", 'main workflow ref'),
                     ("github.ref != 'refs/heads/main'", "github.ref != ''", 'exclude main'),
                     (APP_BINDING, '', 'ephemeral credential helper'),
                     ('persist-credentials: false', 'persist-credentials: true', 'persist authentication'),
                     ('HEAD:${GITHUB_REF:?}', 'HEAD:${GITHUB_REF:-refs/heads/main}', 'workflow-ref destination'),
                     (APP_KEY, 'private-key: ${{ secrets.UNRELATED_KEY }}', 'environment secrets')]
        for old, new, expected in mutations:
            with self.subTest(boundary=expected):
                self.assertIn(old, text)
                broken = text.replace(old, new, 1)
                self.assertNotEqual(broken, text)
                self.assertTrue(any(expected in error for error in problems(broken)))

    def test_pages_and_render_have_one_app_push_route(self):
        pages = (ROOT/'.github/workflows/pages.yml').read_text()
        self.assertRegex(pages, r'(?m)^  push:\n    branches: \[main\]')
        for name in ('rebuild-chain', 'health-artifacts', 'fidelity-pulse'):
            text = (ROOT/f'.github/workflows/{name}.yml').read_text()
            self.assertNotIn('actions/workflows/pages.yml/dispatches', text)
            self.assertNotIn('actions/workflows/v2-render-test.yml/dispatches', text)

    def test_probe_dry_run_has_no_token_mint_or_publication(self):
        text = (ROOT/'.github/workflows/espn-history-probe.yml').read_text()
        self.assertIn('      dry_run:\n', text)
        for name in ('Mint main writer token', 'Commit the result'):
            block = text.split('      - name: '+name+'\n', 1)[1].split('\n      - ', 1)[0]
            self.assertRegex(block, r'(?m)^        if: .*!inputs.dry_run')

    def test_rebuild_branch_token_cannot_write_repository_contents(self):
        text = (ROOT/'.github/workflows/rebuild-chain.yml').read_text()
        branch = text.split('  rebuild-branch:\n', 1)[1]
        self.assertRegex(branch, r'(?m)^      contents: read$')
        self.assertNotRegex(branch, r'(?m)^      contents: write$')

    def test_dry_modes_do_not_mint_the_app_writer(self):
        for name in ('espn-weekly-store', 'player-status-history'):
            text = (ROOT/f'.github/workflows/{name}.yml').read_text()
            mint = text.split('      - name: Mint main writer token\n', 1)[1].split('\n      - ', 1)[0]
            self.assertRegex(mint, r"(?m)^        if: .*inputs.mode == 'write'")
        text = (ROOT/'.github/workflows/espn-supabase-sync.yml').read_text()
        for name in ('Mint main writer token', 'Commit scraper updates if changed'):
            block = text.split('      - name: '+name+'\n', 1)[1].split('\n      - ', 1)[0]
            self.assertRegex(block, r'(?m)^        if: .*!inputs.dry_run')

    def test_fidelity_rejects_untrusted_workflow_run_provenance(self):
        text = (ROOT/'.github/workflows/fidelity-pulse.yml').read_text()
        self.assertRegex(text, r'workflow_run:\n    workflows:.*\n    types: \[completed\]\n    branches: \[main\]')
        header = text.split('jobs:\n', 1)[1].split('    steps:', 1)[0]
        for guard in ("github.event.workflow_run.conclusion == 'success'",
                      "github.event.workflow_run.head_branch == 'main'",
                      'github.event.workflow_run.head_repository.full_name == github.repository'):
            self.assertIn(guard, header)


if __name__ == '__main__':
    unittest.main()
