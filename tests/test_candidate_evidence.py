import json
import hashlib
from datetime import datetime
from pathlib import Path
import sys
import tempfile
import unittest

from pipelines.candidate_evidence import describe, refresh, replay, run


class CandidateEvidenceTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1])
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name)
        self.fixture = self.repo / 'data/fixtures/current/comparison-sources-data.json'
        self.fixture.parent.mkdir(parents=True)
        self.write(10)
        self.store = self.repo / 'output/candidate-evidence'
        self.store.mkdir(parents=True)
        self.command = [sys.executable, '-c',
                        "import json; from pathlib import Path; assert json.loads(Path('data/fixtures/current/comparison-sources-data.json').read_text())['sources']['razzball']['ppg'] == 10"]

    def write(self, ppg):
        self.fixture.write_text(json.dumps({'sources': {'razzball': {
            'vintage': '2026-11-05', 'ppg': ppg}}}))

    def index(self):
        return json.loads((self.store / 'index.json').read_text())

    def test_week9_a_pass_b_supersedes_and_a_replays(self):
        self.assertEqual(run(self.repo, self.store, 'validation', self.command), 0)
        first = self.index()['results'][0]
        self.assertEqual(first['sources']['razzball']['content_vintage'], '2026-11-05')
        self.write(11)  # same vintage, different content
        refresh(self.repo, self.store)
        old = self.index()['results'][0]
        self.assertTrue(old['superseded'])
        self.assertNotEqual(old['candidate_id'], old['superseded_by'])
        self.assertEqual(replay(self.repo, self.store, first['id']), 0)
        self.assertEqual(json.loads(self.fixture.read_text())['sources']['razzball']['ppg'], 11)
        self.assertEqual(run(self.repo, self.store, 'perturbation', self.command), 1)
        self.assertEqual(self.index()['results'][-1]['status'], 'failed')

    def test_real_source_vintage_fields_are_recorded(self):
        real = Path(__file__).resolve().parents[1] / 'data/fixtures/current/comparison-sources-data.json'
        sections = json.loads(real.read_text())['sources']
        self.fixture.write_text(json.dumps({'sources': sections}))
        self.assertEqual(run(self.repo, self.store, 'validation', [sys.executable, '-c', 'pass']), 0)
        recorded = self.index()['results'][0]['sources']
        for name, field in {'espn': 'espn_snapshot', 'cbsros': 'vintage',
                            'razzball': 'vintage', 'cbs': 'content_vintage',
                            'fantasycalc': 'content_vintage', 'fantasypros': 'content_vintage',
                            'usatoday': 'content_vintage'}.items():
            with self.subTest(source=name):
                self.assertTrue(sections[name][field])
                self.assertEqual(recorded[name]['content_vintage'], sections[name][field])
                expected = hashlib.sha256(json.dumps(sections[name], sort_keys=True,
                                                     separators=(',', ':')).encode()).hexdigest()
                self.assertEqual(recorded[name]['sha256'], expected)

    def test_replay_outcomes_have_distinct_durable_evidence(self):
        for code in (0, 3):
            with self.subTest(returncode=code):
                command = [sys.executable, '-c',
                           f"import os; print('replay output', os.environ['TODAY']); raise SystemExit({code})"]
                self.assertEqual(run(self.repo, self.store, 'validation', command), code)
                parent = self.index()['results'][-1]
                self.write(11)
                for _ in range(2):
                    self.assertEqual(replay(self.repo, self.store, parent['id']), code)
                    results = self.index()['results']
                    evidence = results[-1]
                    self.assertEqual(len({r['id'] for r in results}), len(results))
                    self.assertEqual(evidence['kind'], 'replay')
                    self.assertEqual(evidence['parent_result_id'], parent['id'])
                    for key in ('candidate_id', 'input_id', 'sources', 'command', 'today', 'exemptions'):
                        self.assertEqual(evidence[key], parent[key])
                    self.assertEqual(evidence['returncode'], code)
                    self.assertEqual(evidence['status'], 'passed' if code == 0 else 'failed')
                    self.assertLessEqual(datetime.fromisoformat(evidence['recorded_at']),
                                         datetime.fromisoformat(evidence['completed_at']))
                    log = (self.store / (evidence['id'] + '.log')).read_bytes()
                    self.assertIn(('replay output ' + parent['today']).encode(), log)
                    self.assertEqual(evidence['log_sha256'], hashlib.sha256(log).hexdigest())
                    self.assertEqual(next(r for r in results if r['id'] == parent['id'])['returncode'], code)

    def test_exemptions_and_unchanged_inputs(self):
        exemption = self.repo / 'exemption.txt'
        exemption.write_text('[{"case":"Murray", "authority":"test only"}]')
        self.assertEqual(run(self.repo, self.store, 'exemption', self.command, exemption), 0)
        refresh(self.repo, self.store)
        result = self.index()['results'][0]
        self.assertFalse(result['superseded'])
        self.assertEqual(result['exemptions'][0]['case'], 'Murray')

    def test_archive_corruption_is_rejected(self):
        run(self.repo, self.store, 'validation', self.command)
        result = self.index()['results'][0]
        import tarfile
        with tarfile.open(self.store / (result['candidate_id'] + '.tar.gz'), 'w:gz'):
            pass
        with self.assertRaisesRegex(ValueError, 'hash mismatch'):
            replay(self.repo, self.store, result['id'])
        failed = self.index()['results'][-1]
        self.assertEqual(failed['parent_result_id'], result['id'])
        self.assertEqual(failed['status'], 'failed')
        self.assertEqual(failed['returncode'], 127)
        log = (self.store / (failed['id'] + '.log')).read_bytes()
        self.assertIn(b'hash mismatch', log)
        self.assertEqual(failed['log_sha256'], hashlib.sha256(log).hexdigest())

    def test_mutation_during_command_supersedes_result(self):
        command = [sys.executable, '-c', "from pathlib import Path; Path('data/new.json').write_text('{}')"]
        self.assertEqual(run(self.repo, self.store, 'validation', command), 0)
        self.assertTrue(self.index()['results'][0]['superseded'])

    def test_config_and_test_fixture_changes_invalidate(self):
        before = describe(self.repo)
        path = self.repo / 'config/roster.json'
        path.parent.mkdir()
        path.write_text('{}')
        self.assertNotEqual(before['input_id'], describe(self.repo)['input_id'])
        before = describe(self.repo)
        fixture = self.repo / 'tests/fixtures/example.json'
        fixture.parent.mkdir(parents=True)
        fixture.write_text('{}')
        self.assertNotEqual(before['input_id'], describe(self.repo)['input_id'])
