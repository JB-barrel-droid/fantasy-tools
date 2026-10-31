"""Protect drafts from premature closure and duplicate warnings."""
from copy import deepcopy
from datetime import datetime, timezone, timedelta
import unittest
from scripts.stale_draft_expiry import select, WARNING

NOW = datetime(2026, 10, 31, tzinfo=timezone.utc)
def ago(days):
    return (NOW - timedelta(days=days)).isoformat()

class SelectionTests(unittest.TestCase):
    def setUp(self):
        self.pr = dict(state='OPEN', isDraft=True, labels=[], title='JEG-1452 task',
                       body='', headRefName='codex/JEG-1452', createdAt=ago(30), updatedAt=ago(8))
        self.labels = {'JEG-1452': []}

    def choose(self, comments=None, reviews=None, review_comments=None, commits=None):
        return select(self.pr, comments or [], reviews or [], review_comments or [],
                      commits or [], self.labels, NOW, 7)

    def warning(self, days):
        return dict(body=WARNING, created_at=ago(days), updated_at=ago(days),
                    user={'type': 'Bot', 'login': 'github-actions[bot]'})

    def test_warn_boundary(self):
        self.pr['updatedAt'] = ago(7)
        self.assertEqual(self.choose()['action'], 'warn')
        self.pr['updatedAt'] = ago(6.99)
        self.assertIsNone(self.choose())

    def test_old_unwarned_draft_gets_warning_first(self):
        self.pr['updatedAt'] = ago(29)
        self.assertEqual(self.choose()['action'], 'warn')

    def test_second_window_and_no_duplicate(self):
        self.pr['updatedAt'] = ago(8)
        self.assertIsNone(self.choose([self.warning(6)]))
        self.pr['updatedAt'] = ago(7)
        self.assertEqual(self.choose([self.warning(7)])['action'], 'close')

    def test_activity_after_warning_requires_fresh_warning(self):
        self.pr['updatedAt'] = ago(8)
        self.assertEqual(self.choose([self.warning(20)])['action'], 'warn')
        self.pr['updatedAt'] = ago(14)
        self.assertEqual(self.choose([self.warning(22)])['action'], 'warn')

    def test_exemptions(self):
        for field, value in [('isDraft', False), ('state', 'CLOSED'), ('labels', [{'name':'keep-open'}])]:
            with self.subTest(field=field):
                p = deepcopy(self.pr)
                self.pr[field] = value
                self.assertIsNone(self.choose())
                self.pr = p
        for label in ('needs-jeremy', 'blocked-dependency'):
            self.labels['JEG-1452'] = [label]
            self.assertIsNone(self.choose())
        self.labels = {}
        self.assertIsNone(self.choose())

    def test_referenced_protected_ticket(self):
        self.pr['body'] = 'Depends on JEG-1'
        self.labels['JEG-1'] = ['needs-jeremy']
        self.assertIsNone(self.choose())

    def test_each_activity_resets_clock(self):
        for kwargs in [dict(comments=[dict(body='update',created_at=ago(1),user={'type':'User','login':'a'})]),
                       dict(reviews=[dict(submitted_at=ago(1))]),
                       dict(review_comments=[dict(created_at=ago(1))]),
                       dict(commits=[dict(commit={'committer':{'date':ago(1)}})])]:
            with self.subTest(kwargs=kwargs):
                self.assertIsNone(self.choose(**kwargs))

    def test_user_marker_does_not_authorize_close(self):
        comment = self.warning(15)
        comment['user'] = {'login':'untrusted', 'type':'User'}
        self.assertIsNone(self.choose([comment]))



class MainTests(unittest.TestCase):
    """Exercise orchestration with no network, clock, or mutation side effects."""
    def run_main(self, config_dry=False, cli_dry=False, ticket_labels=None,
                 comments=None, events=None, changed_labels=None):
        import contextlib
        import io
        import json
        import tempfile
        from pathlib import Path
        from unittest.mock import patch
        from scripts import stale_draft_expiry as expiry

        prs = [dict(number=n, state='OPEN', isDraft=True, labels=[],
                    title=f'JEG-{n} draft', body='', headRefName=f'codex/JEG-{n}',
                    createdAt=ago(30), updatedAt=ago(8)) for n in (1, 2)]
        lookups = {}
        def fake_linear(query, variables):
            ticket = variables.get('id')
            if 'labels' in query:
                lookups[ticket] = lookups.get(ticket, 0) + 1
                names = (ticket_labels or {}).get(ticket, [])
                if lookups[ticket] > 1 and changed_labels:
                    names = changed_labels.get(ticket, names)
                return {'issue': {'labels': {'nodes': [{'name': x} for x in names]}}}
            if query.startswith('query'):
                return {'issue': {'id': ticket}}
            return {'commentCreate': {'success': True}}

        def fake_gh(*args):
            if args[:2] == ('pr', 'list'):
                return deepcopy(prs)
            if args[:2] == ('pr', 'view'):
                return deepcopy(prs[int(args[2]) - 1])
            if args == ('api', 'user'):
                return {'login': 'operator'}
            path = args[-1]
            number = int(path.split('/')[4])
            if '/issues/' in path and path.endswith('/comments'):
                return [deepcopy((comments or {}).get(number, []))]
            if path.endswith('/events'):
                return [deepcopy((events or {}).get(number, []))]
            return [[]]

        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / 'config.json'
            config.write_text(json.dumps({'window_days': 7, 'dry_run': config_dry}))
            argv = ['expiry', '--config', str(config)] + (['--dry-run'] if cli_dry else [])
            output = io.StringIO()
            with patch.object(expiry, 'gh', side_effect=fake_gh), \
                 patch.object(expiry, 'linear', side_effect=fake_linear) as linear_mock, \
                 patch.object(expiry, 'datetime') as clock, \
                 patch.object(expiry.subprocess, 'run') as writes, \
                 patch('sys.argv', argv), patch.dict('os.environ', {'GITHUB_ACTIONS': ''}), \
                 contextlib.redirect_stdout(output):
                clock.now.return_value = NOW
                clock.fromisoformat.side_effect = datetime.fromisoformat
                expiry.main()
                return writes.call_args_list, output.getvalue(), linear_mock.call_args_list

    def test_both_dry_run_gates_prevent_all_writes(self):
        for config_dry, cli_dry in [(True, False), (False, True)]:
            with self.subTest(config_dry=config_dry, cli_dry=cli_dry):
                writes, output, linear_calls = self.run_main(config_dry, cli_dry)
                self.assertEqual(writes, [])
                self.assertIn('#1', output)
                self.assertIn('#2', output)
                self.assertFalse(any(c.args[0].startswith('mutation') for c in linear_calls))

    def test_warning_marker_suppresses_duplicate_with_eligible_quiet_age(self):
        writes, output, _ = self.run_main(comments={1: [SelectionTests().warning(6)]})
        self.assertEqual([c.args[0][3] for c in writes], ['2'])
        self.assertNotIn('#1', output)

    def test_recheck_does_not_discard_later_pr_ticket_labels(self):
        writes, _, _ = self.run_main()
        self.assertEqual([c.args[0][3] for c in writes], ['1', '2'])
        self.assertTrue(all(c.args[0][2] == 'comment' for c in writes))

    def test_mixed_case_linear_labels_protect_in_main(self):
        for label in ['Needs Jeremy', 'Needs-Jeremy', 'NEEDS_JEREMY', 'Blocked Dependency']:
            with self.subTest(label=label):
                writes, output, _ = self.run_main(ticket_labels={'JEG-1': [label]})
                self.assertEqual([c.args[0][3] for c in writes], ['2'])
                self.assertNotIn('#1', output)

    def test_protection_added_during_recheck(self):
        writes, _, _ = self.run_main(changed_labels={'JEG-1': ['Needs Jeremy']})
        self.assertEqual([c.args[0][3] for c in writes], ['2'])

    def test_later_activity_rewarns_then_new_warning_can_close(self):
        from scripts.stale_draft_expiry import CLOSED
        warning = SelectionTests().warning(25)
        closure = dict(body=CLOSED, created_at=ago(10), updated_at=ago(10),
                       user={'type': 'Bot', 'login': 'github-actions[bot]'})
        writes, _, linear_calls = self.run_main(
            comments={1: [warning, closure]},
            events={1: [{'event': 'reopened', 'created_at': ago(8)}]})
        self.assertEqual(writes[0].args[0][2], 'comment')
        self.assertIn(WARNING, writes[0].args[0][-1])
        self.assertFalse(any(c.args[0].startswith('mutation') for c in linear_calls))
        # Next cycle: this warning is now 8 days old, with no subsequent activity.
        writes, _, linear_calls = self.run_main(comments={1: [warning, closure, SelectionTests().warning(8)]})
        self.assertEqual(writes[0].args[0][2], 'close')
        self.assertEqual(sum(c.args[0].startswith('mutation') for c in linear_calls), 1)


class AdditionalSelectionTests(unittest.TestCase):
    setUp = SelectionTests.setUp
    choose = SelectionTests.choose
    warning = SelectionTests.warning
    def test_github_protected_labels_normalized(self):
        for name in ['Needs Jeremy', 'Needs-Jeremy', 'NEEDS_JEREMY',
                     'Blocked Dependency', 'BLOCKED_dependency', 'Keep Open']:
            with self.subTest(name=name):
                self.pr['labels'] = [{'name': name}]
                self.assertIsNone(self.choose())

    def test_closed_marker_and_reopen_each_restart_warning_cycle(self):
        from scripts.stale_draft_expiry import CLOSED
        warning = self.warning(25)
        self.pr['updatedAt'] = ago(25)
        closed = dict(body=CLOSED, created_at=ago(8),
                      user={'type': 'Bot', 'login': 'github-actions[bot]'})
        self.assertEqual(self.choose([warning, closed])['action'], 'warn')
        result = select(self.pr, [warning], [], [], [], self.labels, NOW, 7,
                        events=[{'event':'reopened', 'created_at':ago(8)}])
        self.assertEqual(result['action'], 'warn')


if __name__ == '__main__':
    unittest.main()
