"""Behavior, real Git range, and publication-boundary mutation regressions."""
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from pipelines import pages_change_gate as gate

ROOT = Path(__file__).resolve().parents[1]


def workflow_problems(text):
    problems = []
    for name in ('build', 'validate-shard'):
        match = re.search(rf'^  {name}:\n(.*?)(?=^  [\w-]+:|\Z)', text, re.M | re.S)
        body = match[1] if match else ''
        if (re.findall(r'^    needs: (.*)$', body, re.M) != ['classify']
                or re.findall(r'^    if: (.*)$', body, re.M) != ["needs.classify.outputs.mode == 'full'"]):
            problems.append('full jobs require the exact classifier dependency and allow condition')
    classifier = re.search(r'^  classify:\n(.*?)(?=^  [\w-]+:|\Z)', text, re.M | re.S)
    body = classifier[1] if classifier else ''
    for expected in ('fetch-depth: 0', 'ref: ${{ github.sha }}', 'run: python3 pipelines/pages_change_gate.py',
                     'mode: ${{ steps.classify.outputs.mode }}', 'path: pages-change-receipt.json', 'if-no-files-found: error'):
        if expected not in body:
            problems.append('classifier must retain full history, exact head and visible receipt')
    if re.search(r'^    (if|needs|continue-on-error):', body, re.M) or 'continue-on-error: true' in body:
        problems.append('classifier must run and block on failure')
    if "    if: always() && needs.classify.outputs.mode == 'full'" not in text:
        problems.append('status-only must not enter publication')
    if 'CLASSIFY_RESULT: ${{ needs.classify.result }}' not in text or '[ "$CLASSIFY_RESULT" = "success" ] &&' not in text:
        problems.append('publication must require successful classification')
    return problems


class PagesChangeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.git('init', '-q')
        self.git('config', 'user.name', 'Test')
        self.git('config', 'user.email', 'test@example.invalid')
        self.commit('app/main.js', 'app')
        self.anchor = self.git('rev-parse', 'HEAD').decode().strip()

    def git(self, *args):
        return subprocess.check_output(['git', '-C', str(self.root), *args], stderr=subprocess.PIPE)

    def commit(self, name, content):
        p = self.root / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
        self.git('add', name)
        self.git('commit', '-qm', name)
        return self.git('rev-parse', 'HEAD').decode().strip()

    def classify(self, **kwargs):
        head = self.git('rev-parse', 'HEAD').decode().strip()
        event = {'before': self.anchor, 'after': head, 'ref': 'refs/heads/main', 'forced': False}
        event.update(kwargs.pop('event', {}))
        return gate.classify(kwargs.pop('event_name', 'push'), event, head,
                             kwargs.pop('anchor', self.anchor), self.git)[0]

    def test_exact_status_only_records_no_publication(self):
        for name in sorted(gate.STATUS_FILES):
            self.commit(name, '{"generated_at":"2026-11-03"}')
        self.assertEqual(self.classify(), 'status-only')

    def test_application_data_workflow_unknown_and_status_lookalikes_are_full(self):
        for name in ('app/main.js', 'data/fixtures/current/players.json', '.github/workflows/pages.yml',
                     'dist/modules/new-signal.json', 'output/player-status-history.json',
                     'dist/modules/status.js', 'dist/modules/../new.json',
                     'dist/modules/source-import-health.json', 'dist/modules/pipeline-checkpoints.json'):
            with self.subTest(name=name):
                self.git('reset', '--hard', self.anchor)
                self.commit(name, '{}')
                self.assertEqual(self.classify(), 'full')

    def test_accumulated_range_catches_app_commit_before_latest_status_push(self):
        app = self.commit('app/main.js', 'changed app')
        self.commit('dist/modules/ops-status.json', '{}')
        self.assertEqual(self.classify(event={'before': app}), 'full')
        # Mutant: anchoring on the latest push would silently miss the app.
        self.assertEqual(self.classify(event={'before': app}, anchor=app), 'status-only')

    def test_manual_missing_forced_nonmain_and_malformed_ranges_are_full(self):
        self.commit('dist/modules/ops-status.json', '{}')
        for kwargs in ({'event_name': 'workflow_dispatch'}, {'anchor': None},
                       {'event': {'before': '0' * 40}}, {'event': {'after': 'f' * 40}},
                       {'event': {'forced': True}}, {'event': {'forced': None}},
                       {'event': {'ref': 'refs/heads/other'}}):
            with self.subTest(kwargs=kwargs):
                self.assertEqual(self.classify(**kwargs), 'full')

    def test_empty_invalid_deleted_and_unavailable_records_never_qualify(self):
        self.assertEqual(self.classify(), 'full')
        self.commit('dist/modules/ops-status.json', '[]')
        self.assertEqual(self.classify(), 'full')
        self.commit('dist/modules/ops-status.json', 'not JSON')
        with self.assertRaises(ValueError):
            self.classify()
        self.git('rm', 'dist/modules/ops-status.json')
        self.git('commit', '-qm', 'delete')
        # Added then deleted yields no net diff, so full work.
        self.assertEqual(self.classify(), 'full')
        with self.assertRaises(subprocess.CalledProcessError):
            self.classify(anchor='f' * 40)

    def test_main_falls_back_to_full_on_api_git_or_json_failure(self):
        for error in (ValueError('range'), OSError('fetch'), KeyError('response')):
            with self.subTest(error=error), tempfile.TemporaryDirectory() as directory:
                paths = {name: str(Path(directory) / name) for name in ('event', 'out', 'summary')}
                Path(paths['event']).write_text('{}')
                with patch.dict(os.environ, {'GITHUB_EVENT_PATH': paths['event'], 'GITHUB_OUTPUT': paths['out'],
                     'GITHUB_STEP_SUMMARY': paths['summary'], 'GITHUB_EVENT_NAME': 'push', 'GITHUB_SHA': self.anchor}), \
                     patch.object(gate, 'published_head', side_effect=error), patch('pathlib.Path.write_text'):
                    gate.main()
                self.assertEqual(Path(paths['out']).read_text(), 'mode=full\n')
                self.assertIn('last published build', Path(paths['summary']).read_text())

    def test_successful_noop_cannot_be_publication_anchor(self):
        def api(path):
            if path.startswith('actions/workflows'):
                return {'workflow_runs': [{'id': 2, 'head_sha': 'b' * 40}, {'id': 1, 'head_sha': self.anchor}]}
            return {'jobs': [{'name': 'deploy', 'conclusion': 'skipped' if '/2/' in path else 'success'}]}
        self.assertEqual(gate.published_head(api), self.anchor)
        with self.assertRaises(ValueError):
            gate.published_head(lambda _: {'workflow_runs': []})

    def test_workflow_mutations_cannot_publish_or_skip_full_gates(self):
        text = (ROOT / '.github/workflows/pages.yml').read_text()
        self.assertEqual(workflow_problems(text), [])
        for old, new in (("needs: classify", 'needs: nothing'),
                         ("needs.classify.outputs.mode == 'full'", "needs.classify.outputs.mode != 'status-only'"),
                         ('fetch-depth: 0', 'fetch-depth: 2'),
                         ('ref: ${{ github.sha }}', 'ref: main'),
                         ('[ "$CLASSIFY_RESULT" = "success" ] &&', 'true &&'),
                         ('if-no-files-found: error', 'if-no-files-found: warn'),
                         ("if: always() && needs.classify.outputs.mode == 'full'", 'if: always()')):
            with self.subTest(old=old):
                mutant = text.replace(old, new)
                self.assertNotEqual(text, mutant)
                self.assertTrue(workflow_problems(mutant))

    def test_recorder_does_not_mark_status_noop_as_deploy(self):
        text = (ROOT / '.github/workflows/record-pages-deploy.yml').read_text()
        script = text.split("          python3 - <<'PYCODE'\n", 1)[1].split('          PYCODE', 1)[0]
        script = '\n'.join(line[10:] for line in script.splitlines())
        for classify, deploy, record in (('success', 'skipped', False), ('failure', 'skipped', True),
                                         ('success', 'failure', True), ('success', 'success', True)):
            with self.subTest(classify=classify, deploy=deploy), tempfile.TemporaryDirectory() as directory:
                jobs = {'total_count': 2, 'jobs': [{'name': 'classify', 'conclusion': classify}, {'name': 'deploy', 'conclusion': deploy}]}
                out = Path(directory) / 'out'
                env = {'GITHUB_OUTPUT': str(out), 'GITHUB_STEP_SUMMARY': str(Path(directory) / 'summary')}
                # Execute the actual YAML script with its input file replaced.
                data = Path(directory) / 'jobs.json'; data.write_text(json.dumps(jobs))
                result = subprocess.run(['python3', '-c', script.replace('/tmp/pages-jobs.json', str(data))], env={**os.environ, **env}, capture_output=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(out.read_text(), f"record={str(record).lower()}\n")
        self.assertIn("if: steps.publication.outputs.record == 'true'", text)


if __name__ == '__main__':
    unittest.main()
