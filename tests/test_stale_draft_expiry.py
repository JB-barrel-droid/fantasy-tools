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
        self.pr['updatedAt'] = ago(6)
        self.assertIsNone(self.choose([self.warning(6)]))
        self.pr['updatedAt'] = ago(7)
        self.assertEqual(self.choose([self.warning(7)])['action'], 'close')

    def test_activity_after_warning_requires_full_grace(self):
        self.pr['updatedAt'] = ago(8)
        self.assertIsNone(self.choose([self.warning(20)]))
        self.pr['updatedAt'] = ago(14)
        self.assertEqual(self.choose([self.warning(22)])['action'], 'close')

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
        self.assertEqual(self.choose([comment])['action'], 'warn')

if __name__ == '__main__':
    unittest.main()
