"""Queue drift must remain visible; this report never writes to Linear."""
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('review_queue', Path(__file__).resolve().parents[1] / 'scripts/review_queue.py')
queue = importlib.util.module_from_spec(spec)
spec.loader.exec_module(queue)


class ReviewQueueTests(unittest.TestCase):
    def issue(self, **kw):
        return dict(id='JEG-1425', status='In Review', createdAt='2026-10-01T00:00:00Z',
                    labels=['review-light'], description='Review family: docs and rules\nReview tier: review-standard', **kw)

    def test_routing_mismatch_is_flagged(self):
        rows = queue.rows([self.issue()], [], queue.timestamp('2026-11-01T00:00:00Z'))
        self.assertIn('tier mismatch', rows[0]['flags'])
        self.assertEqual(rows[0]['owner'], 'Claude (Duet coordinator)')
        self.assertEqual(rows[0]['age'], '31d (created)')

    def test_non_draft_pr_without_ticket_is_not_lost(self):
        prs = [dict(number=1, title='Unlinked work', body='', headRefName='feature', isDraft=False),
               dict(number=2, title='JEG-1425', body='', headRefName='draft', isDraft=True)]
        rows = queue.rows([], prs, queue.timestamp('2026-11-01T00:00:00Z'))
        self.assertEqual(len(rows), 1)
        self.assertIn('missing Linear ticket', rows[0]['flags'])

    def test_missing_or_conflicting_notes_are_unknown(self):
        i = self.issue()
        i['description'] = 'Review tier: review-light\nReview tier: review-high-risk'
        row = queue.rows([i], [], queue.timestamp('2026-11-01T00:00:00Z'))[0]
        self.assertIn('missing/ambiguous routing tier', row['flags'])
        self.assertIn('missing/unknown family', row['flags'])

    def test_multiple_prs_and_references_preserved(self):
        prs = [dict(number=n, title='JEG-1425', body='depends on JEG-999', headRefName='branch', isDraft=False) for n in (3, 4)]
        rows = queue.rows([self.issue()], prs, queue.timestamp('2026-11-01T00:00:00Z'))
        self.assertEqual(len(rows), 2)
        self.assertEqual([r['pr'] for r in rows], ['#3', '#4'])

    def test_partial_export_rejected(self):
        with self.assertRaises(ValueError):
            queue.issues_from_export({'issues': [], 'hasNextPage': True})
