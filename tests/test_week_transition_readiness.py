"""Offline contracts for JEG-1526; no production/network dependencies."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pipelines import week_transition_readiness as gate


class ReadinessTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1])
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / 'snapshot.json').write_text('{"rows": [1]}')
        self.policy = {'version': 1, 'sources': {s: {'kind': 'week', 'scorings': ['ppr'],
                       'grains': {'players': 1}} for s in gate.SOURCES}}
        self.arrivals = {s: {'season': 2026, 'week': 10, 'path': 'snapshot.json',
                            'scorings': ['ppr'], 'grains': {'players': 1}} for s in gate.SOURCES}

    def capture(self):
        return gate.capture(self.root, self.policy, self.arrivals, 2026, 10)

    def test_complete_and_partial(self):
        self.assertTrue(self.capture()['complete'])
        del self.arrivals['espn']
        self.assertFalse(self.capture()['complete'])

    def test_wrong_week_and_grain_and_scoring_block(self):
        for key, value in [('week', 9), ('grains', {}), ('scorings', [])]:
            with self.subTest(key=key):
                saved = copy.deepcopy(self.arrivals)
                self.arrivals['espn'][key] = value
                self.assertFalse(self.capture()['complete'])
                self.arrivals = saved

    def test_date_feed_window(self):
        self.policy['sources']['cbsros'].update(kind='date', earliest='2026-11-04', latest='2026-11-05')
        self.arrivals['cbsros']['content_date'] = '2026-11-04'
        self.assertTrue(self.capture()['complete'])
        self.arrivals['cbsros']['content_date'] = '2026-11-03'
        self.assertFalse(self.capture()['complete'])

    def test_empty_policy_blocks(self):
        self.policy['sources'] = {}
        self.assertFalse(self.capture()['complete'])

    def test_escape_and_symlink_escape_block(self):
        self.arrivals['espn']['path'] = '../outside'
        self.assertFalse(self.capture()['complete'])
        (self.root / 'link').symlink_to(self.root.parent)
        self.arrivals['espn']['path'] = 'link/outside'
        self.assertFalse(self.capture()['complete'])

    def test_corrected_bytes_invalidate_and_events_dedupe(self):
        state = {}
        first = self.capture()
        self.assertTrue(gate.reconcile(state, first, 'code', 'landing')['queued'])
        self.assertFalse(gate.reconcile(state, first, 'code', 'hourly')['queued'])
        (self.root / 'snapshot.json').write_text('corrected')
        changed = self.capture()
        self.assertNotEqual(first['input_hash'], changed['input_hash'])
        self.assertTrue(gate.reconcile(state, changed, 'code', 'landing')['invalidated'])
        self.assertTrue(gate.reconcile(state, changed, 'new-code', 'hourly')['queued'])
        self.assertFalse(gate.receipt_valid({'ready': True, 'input_hash': first['input_hash'],
                                           'code_hash': 'code'}, changed, 'code'))

    def test_no_automatic_retry(self):
        state = {}
        first = gate.reconcile(state, self.capture(), 'code', 'landing')
        state['jobs'][first['key']]['status'] = 'FAIL'
        self.assertFalse(gate.reconcile(state, self.capture(), 'code', 'hourly')['queued'])

    def test_default_run_blocks_and_retains_captured_bytes(self):
        with patch.object(gate.subprocess, 'run', side_effect=AssertionError('must not execute')):
            out = self.root / 'run'
            result = gate.run(self.root, out, self.capture(), 'code', '2026-11-10')
        self.assertFalse(result['ready'])
        self.assertEqual(result['status'], 'BLOCKED')
        self.assertEqual(len(list((out / 'captures').iterdir())), 1)
        self.assertEqual(json.loads((out / 'readiness.json').read_text()), result)
        self.assertEqual(sum(s['name'].startswith('browser_') for s in result['stages']), 3)

    def test_container_boundary_and_independent_browser_failure(self):
        calls = []
        def execute(argv, **kwargs):
            from subprocess import CompletedProcess
            if argv[0] == 'git':
                self.assertEqual(argv[:4], ['git', 'ls-files', '-z', '--cached'])
                return CompletedProcess(argv, 0, b'', b'')
            calls.append(argv)
            return CompletedProcess(argv, 1 if 'tests/rendered_gate/gate_flexibility.mjs' in argv else 0, b'', b'')
        with patch.object(gate.subprocess, 'run', side_effect=execute):
            result = gate.run(self.root, self.root / 'run', self.capture(), 'code', '2026-11-10', 'sha256:' + 'a' * 64)
        self.assertEqual(result['status'], 'FAIL')
        for argv in calls:
            self.assertIn('--network=none', argv)
            self.assertIn('--pull=never', argv)
            self.assertIn('-i', argv)
        self.assertEqual(next(s for s in result['stages'] if s['name'] == 'browser_flex')['status'], 'FAIL')
        self.assertFalse((self.root / 'run/scratch/run').exists())

    def test_scratch_copies_only_selected_tracked_files_without_credentials(self):
        import subprocess
        subprocess.run(['git', 'init', '-q', str(self.root)], check=True)
        files = {
            'Makefile': 'safe build', 'pipelines/check.py': 'safe code',
            '.gitignore': '*.pem\n*.key\nsecrets/\ndata/private/\n',
            'secrets/production.json': 'fake secret',
            'data/private/export.json': 'fake private data',
            'service-account.pem': 'fake certificate', 'nested/client.key': 'fake key',
            '.env': 'fake environment', '.aws/config': 'fake config',
            'pipelines/.env.local': 'fake environment',
            'dist/index.html': 'old build', 'ticket-work/receipt.json': 'old run',
            'untracked.json': 'unreviewed payload',
        }
        for name, content in files.items():
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
        # Force-track private paths too: Git membership alone is insufficient.
        subprocess.run(['git', '-C', str(self.root), 'add', '-f', '--',
                        *[n for n in files if n != 'untracked.json']], check=True)
        (self.root / 'pipelines/link.py').symlink_to(self.root / 'secrets/production.json')
        (self.root / 'linked').symlink_to(self.root / 'secrets', target_is_directory=True)
        subprocess.run(['git', '-C', str(self.root), 'add', 'pipelines/link.py', 'linked'], check=True)
        (self.root / 'pipelines/check.py').write_text('dirty safe code')
        dest = self.root / 'run/scratch'
        gate.scratch_copy(self.root, dest)
        self.assertEqual({p.relative_to(dest).as_posix() for p in dest.rglob('*') if p.is_file()},
                         {'Makefile', 'pipelines/check.py', '.gitignore'})
        self.assertEqual((dest / 'pipelines/check.py').read_text(), 'dirty safe code')

    def test_week9_evidence_pins_three_cases_without_weakening_tests(self):
        evidence = json.loads((Path(__file__).resolve().parents[1] / 'docs/week9-regression-evidence.json').read_text())
        self.assertEqual(evidence['cases'], [
            ['standard', 10, 'razzball', 'QB', 370, -1.0],
            ['standard', 8, 'razzball', 'TE', 1970, -1.0],
            ['half_ppr', 8, 'razzball', 'TE', 3279, 1.0]])
        self.assertIn('tests.test_waiver_band_line.OnePlayerPerturbationTest', gate.commands('2026-11-10')['week9_regression'])


if __name__ == '__main__':
    unittest.main()
