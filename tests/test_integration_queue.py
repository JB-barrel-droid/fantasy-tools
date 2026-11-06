import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from scripts.integration_queue import git, prepare


class QueueTests(unittest.TestCase):
    def setUp(self):
        # All fixture repositories and validation exports stay in this worktree.
        self.tmp = tempfile.TemporaryDirectory(prefix='.queue-test-', dir=Path.cwd())
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name)
        git(self.repo, 'init', '-b', 'main')
        git(self.repo, 'config', 'user.name', 'Fixture Author')
        git(self.repo, 'config', 'user.email', 'fixture@example.invalid')
        self.write_commit('shared', 'base')
        self.base = git(self.repo, 'rev-parse', 'HEAD')
        self.prs = []
        for n in (1, 2):
            git(self.repo, 'checkout', '-b', f'lane-{n}', self.base)
            self.write_commit(f'file-{n}', str(n))
            head = git(self.repo, 'rev-parse', 'HEAD')
            self.prs.append(dict(number=n, head=head, title=f'Feature {n}',
                                owner=f'owner-{n}', author_session='writer',
                                url=f'https://example.invalid/pull/{n}',
                                review=dict(head=head, result='pass', session='reviewer',
                                            url='https://example.invalid/review/1'),
                                checks={'preview': dict(head=head, result='success')}))
        git(self.repo, 'checkout', 'main')
        self.snapshot = dict(base_ref='refs/heads/main', required_checks=['preview'], prs=self.prs)

    def write_commit(self, path, value):
        (self.repo / path).write_text(value)
        git(self.repo, 'add', path)
        git(self.repo, 'commit', '-m', value)

    def run_queue(self, **kwargs):
        return prepare(self.repo, self.snapshot, validator=lambda path: True, **kwargs)['events']

    def test_admission_fixtures(self):
        cases = json.loads((Path(__file__).parent / 'queue_cases/admission.json').read_text())
        original = json.dumps(self.prs)
        for case in cases:
            with self.subTest(case=case['name']):
                self.snapshot['prs'] = json.loads(original)
                for pr, change in zip(self.snapshot['prs'], case['changes']):
                    for flag, value in change.items():
                        if flag == 'review_result': pr['review']['result'] = value
                        elif flag == 'ci_result': pr['checks']['preview']['result'] = value
                        elif flag == 'stale_review': pr['review']['head'] = self.base
                        elif flag == 'stale_ci': pr['checks']['preview']['head'] = self.base
                        elif flag == 'self_review': pr['review']['session'] = 'writer'
                        else: pr[flag] = value
                self.assertEqual([[e['pr'], e['state']] for e in self.run_queue()], case['expected'])

    def test_squash_exact_tree_attribution_and_lane_unchanged(self):
        receipt = self.run_queue()[0]
        self.assertEqual(git(self.repo, 'show', '-s', '--format=%P', receipt['candidate']), self.base)
        self.assertEqual(git(self.repo, 'rev-parse', 'lane-1'), self.prs[0]['head'])
        self.assertEqual(git(self.repo, 'rev-parse', 'main'), self.base)
        message = git(self.repo, 'show', '-s', '--format=%B', receipt['candidate'])
        self.assertIn(self.prs[0]['head'], message)
        self.assertIn(self.prs[0]['review']['url'], message)
        self.assertEqual(git(self.repo, 'show', '-s', '--format=%ae', receipt['candidate']), 'fixture@example.invalid')

    def test_base_change_rebuilds_and_validates_combined_tree(self):
        first = self.run_queue()[0]
        self.write_commit('trunk-new', 'new')
        seen = []
        def validate(path):
            seen.append(((path / 'trunk-new').read_text(), (path / 'file-1').read_text()))
            return True
        second = prepare(self.repo, self.snapshot, validator=validate)['events'][0]
        self.assertNotEqual(first['base'], second['base'])
        self.assertEqual(seen, [('new', '1')])
        self.assertEqual(second['state'], 'validated')

    def test_base_change_during_validation_invalidates(self):
        def validate(path):
            self.write_commit('racing-publisher', 'new base')
            return True
        receipt = prepare(self.repo, self.snapshot, validator=validate)['events'][0]
        self.assertEqual(receipt['state'], 'invalidated')

    def test_conflict_returns_to_owner_then_next_candidate(self):
        git(self.repo, 'checkout', 'lane-1')
        self.write_commit('shared', 'lane change')
        pr = self.prs[0]
        pr['head'] = git(self.repo, 'rev-parse', 'HEAD')
        pr['review']['head'] = pr['head']
        pr['checks']['preview']['head'] = pr['head']
        git(self.repo, 'checkout', 'main')
        self.write_commit('shared', 'trunk change')
        events = self.run_queue()
        self.assertEqual(events[0]['state'], 'returned_to_owner')
        self.assertEqual(events[0]['owner'], 'owner-1')
        self.assertEqual(events[1]['pr'], 2)
        self.assertEqual(events[1]['state'], 'validated')

    def test_failed_validation_stops(self):
        events = prepare(self.repo, self.snapshot, validator=lambda path: False)['events']
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]['state'], 'validation_failed')

    def test_symbolic_queue_ref_is_rejected_without_moving_main(self):
        ref = 'refs/heads/queue/pr-1'
        git(self.repo, 'symbolic-ref', ref, 'refs/heads/main')
        validated = []
        try:
            with self.assertRaisesRegex(ValueError, 'symbolic queue ref'):
                prepare(self.repo, self.snapshot,
                        validator=lambda path: validated.append(path) or True)
        finally:
            self.assertEqual(git(self.repo, 'rev-parse', 'main'), self.base)
            self.assertEqual(git(self.repo, 'symbolic-ref', ref), 'refs/heads/main')
            self.assertEqual(validated, [])

    def test_dry_run_does_not_write_objects_or_refs(self):
        refs = git(self.repo, 'show-ref')
        objects = git(self.repo, 'count-objects', '-v')
        events = self.run_queue(dry_run=True)
        self.assertEqual(events[0]['state'], 'would_prepare')
        self.assertEqual(git(self.repo, 'show-ref'), refs)
        self.assertEqual(git(self.repo, 'count-objects', '-v'), objects)

    def test_cli_runs_real_validator_and_emits_json(self):
        self.write_commit('Makefile', 'validate:\n\t@test -f file-1\n\t@git rev-parse HEAD\n')
        snapshot = self.repo / 'snapshot.json'
        snapshot.write_text(json.dumps(self.snapshot))
        run = subprocess.run([sys.executable, str(Path('scripts/integration_queue.py').resolve()),
                              str(snapshot), '--repo', str(self.repo)],
                             text=True, capture_output=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        receipt = json.loads(run.stdout)['events'][0]
        self.assertEqual(receipt['state'], 'validated')
        self.assertIn(receipt['candidate'], run.stderr)

    def test_missing_required_checks_fails_closed(self):
        self.snapshot['required_checks'] = []
        self.assertTrue(all(e['state'] == 'held' for e in self.run_queue()))


if __name__ == '__main__':
    unittest.main()
