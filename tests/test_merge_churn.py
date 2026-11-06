"""Fixture-driven local merge telemetry contract; no GitHub credentials."""
import copy
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest

from pipelines import merge_churn as m

FIXTURE = Path(__file__).parent / 'data/merge_churn/week.json'
START = '2026-11-02T00:00:00Z'


class Source:
    def __init__(self, events):
        self.items = events

    def events(self):
        return iter(self.items)


class MergeChurnTests(unittest.TestCase):
    def setUp(self):
        self.db = m.connect(':memory:')
        self.addCleanup(self.db.close)
        m.collect(self.db, m.FixtureSource(FIXTURE))

    def report(self):
        return m.weekly_report(self.db, 'example/tools', START)

    def test_observed_baseline_and_per_pr(self):
        r = self.report()
        self.assertEqual(r['pr_count'], 2)
        self.assertEqual(r['refreshes_per_pr'], .5)
        self.assertEqual((r['stale_prs'], r['sampled_prs'], r['stale_rate']), (1, 1, 1))
        self.assertEqual((r['latency_samples'], r['median_ready_to_merge_minutes']), (1, 180))
        self.assertEqual((r['ci_attempts'], r['completed_ci_attempts'], r['ci_minutes']), (3, 2, 30))
        self.assertEqual(r['superseded_ci_share'], 1 / 3)
        self.assertEqual(r['superseded_ci_minutes_share'], 2 / 3)
        p = next(p for p in r['prs'] if p['pr'] == 10)
        self.assertEqual((p['head_transitions'], p['refreshes'], p['ci_attempts'], p['ci_minutes'], p['superseded_ci_attempts']), (1, 1, 2, 30, 1))
        self.assertEqual(p['enqueue_at'], '2026-11-02T00:30:00+00:00')

    def test_replay_and_shuffled_ingest(self):
        self.assertEqual(m.collect(self.db, m.FixtureSource(FIXTURE)), 0)
        other = m.connect(':memory:')
        self.addCleanup(other.close)
        events = list(m.FixtureSource(FIXTURE).events())
        m.collect(other, Source(list(reversed(events))))
        self.assertEqual(self.report(), m.weekly_report(other, 'example/tools', START))

    def test_conflict_rolls_back_entire_batch(self):
        existing = list(m.FixtureSource(FIXTURE).events())[0]
        fresh = dict(existing, source_id='new')
        conflict = dict(existing, pr=999)
        count = self.db.execute('SELECT count(*) FROM events').fetchone()[0]
        with self.assertRaisesRegex(ValueError, 'reused'):
            m.collect(self.db, Source([fresh, conflict]))
        self.assertEqual(self.db.execute('SELECT count(*) FROM events').fetchone()[0], count)

    def test_bad_data_is_atomic(self):
        bad = dict(repository='example/tools', source_id='bad', pr=10, kind='base',
                   occurred_at=START, payload={'head_sha': 'a', 'base_sha': 'b', 'behind': -1})
        with self.assertRaises(ValueError):
            m.collect(self.db, Source([bad]))
        bad.update(kind='ready', occurred_at='2026-11-02T00:00:00')
        with self.assertRaisesRegex(ValueError, 'timezone'):
            m.collect(self.db, Source([bad]))

    def test_empty_and_missing_are_not_zero(self):
        r = m.weekly_report(self.db, 'other/repo', START)
        for field in ('stale_rate', 'refreshes_per_pr', 'median_ready_to_merge_minutes', 'superseded_ci_share'):
            self.assertIsNone(r[field])
        p = next(p for p in self.report()['prs'] if p['pr'] == 11)
        self.assertIsNone(p['stale'])
        self.assertIsNone(p['ready_to_merge_minutes'])
        self.assertIn('N/A', m.render(r))

    def test_ci_lifecycle_rerun_and_shared_run(self):
        events = list(m.FixtureSource(FIXTURE).events())
        run = next(e for e in events if e['source_id'] == 'run2')
        shared = copy.deepcopy(run)
        shared.update(source_id='shared', pr=11)
        m.collect(self.db, Source([shared]))
        self.assertEqual(self.report()['ci_attempts'], 3)
        rerun = copy.deepcopy(run)
        rerun['source_id'] = 'rerun'
        rerun['payload']['attempt'] = 2
        m.collect(self.db, Source([rerun]))
        self.assertEqual(self.report()['ci_attempts'], 4)
        pending = next(e for e in events if e['source_id'] == 'pending')
        done = copy.deepcopy(pending)
        done.update(source_id='done', occurred_at='2026-11-02T02:10:00Z')
        done['payload']['completed_at'] = '2026-11-02T02:10:00Z'
        m.collect(self.db, Source([done]))
        self.assertEqual(self.report()['completed_ci_attempts'], 4)

    def test_window_boundary_and_future_do_not_leak(self):
        event = dict(repository='example/tools', source_id='future', pr=20, kind='merge',
                     occurred_at='2026-11-09T00:00:00Z')
        m.collect(self.db, Source([event]))
        self.assertEqual(self.report()['pr_count'], 2)
        # Pre-window ready is retained for a merge in this window.
        self.assertEqual(self.report()['latency_samples'], 1)

    def test_later_shared_observation_preserves_completion(self):
        events = list(m.FixtureSource(FIXTURE).events())
        completed = next(e for e in events if e['source_id'] == 'run1')
        for missing in ('absent', 'null'):
            with self.subTest(completed_at=missing):
                shared = copy.deepcopy(completed)
                shared.update(source_id='later-shared-' + missing, pr=11,
                              occurred_at='2026-11-02T03:00:00Z')
                shared['payload'].pop('completed_at')
                if missing == 'null':
                    shared['payload']['completed_at'] = None
                m.collect(self.db, Source([shared]))
                r = self.report()
                self.assertEqual((r['completed_ci_attempts'], r['ci_minutes']), (2, 30))
                self.assertEqual(r['superseded_ci_minutes_share'], 2 / 3)
                for number, minutes in ((10, 30), (11, 20)):
                    p = next(p for p in r['prs'] if p['pr'] == number)
                    self.assertEqual(p['ci_minutes'], minutes)
                # The result must also survive reverse ingestion / PR ordering.
                other = m.connect(':memory:')
                try:
                    m.collect(other, Source([shared] + list(reversed(events))))
                    self.assertEqual(m.weekly_report(other, 'example/tools', START), r)
                finally:
                    other.close()

    def test_persistence_and_cli(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as tmp:
            db = str(Path(tmp) / 'events.sqlite')
            cmd = [sys.executable, 'pipelines/merge_churn.py', '--db', db]
            result = subprocess.run(cmd + ['collect', '--fixture', str(FIXTURE)], capture_output=True, text=True, check=True)
            self.assertGreater(json.loads(result.stdout)['inserted'], 0)
            result = subprocess.run(cmd + ['report', '--repository', 'example/tools', '--start', START, '--json'], capture_output=True, text=True, check=True)
            self.assertEqual(json.loads(result.stdout), self.report())
            result = subprocess.run(cmd + ['report', '--repository', 'example/tools', '--start', START], capture_output=True, text=True, check=True)
            self.assertIn('read-only GitHub adapter', result.stdout)

    def test_completed_before_head_change_is_not_superseded(self):
        pending = dict(repository='example/tools', source_id='early-pending', pr=10,
                       kind='ci', occurred_at='2026-11-02T01:00:00Z',
                       payload=dict(head_sha='aaa', run_id=200, attempt=1,
                                    started_at='2026-11-02T01:00:00Z'))
        done = copy.deepcopy(pending)
        done.update(source_id='early-done', occurred_at='2026-11-02T01:06:00Z')
        done['payload']['completed_at'] = '2026-11-02T01:05:00Z'
        m.collect(self.db, Source([pending, done]))
        self.assertEqual(self.report()['superseded_ci_attempts'], 1)
        self.assertEqual(self.report()['ci_minutes'], 35)
        shared_pending = dict(pending, source_id='shared-early-pending', pr=11)
        m.collect(self.db, Source([shared_pending]))
        self.assertEqual(self.report()['superseded_ci_attempts'], 1)
        self.assertEqual(self.report()['completed_ci_attempts'], 3)

    def test_ci_rejects_negative_duration(self):
        event = dict(repository='example/tools', source_id='bad-ci', pr=10,
                     kind='ci', occurred_at='2026-11-02T02:00:00Z',
                     payload=dict(head_sha='aaa', run_id=200, attempt=1,
                                  started_at='2026-11-02T01:00:00Z',
                                  completed_at='2026-11-02T00:59:00Z'))
        with self.assertRaisesRegex(ValueError, 'interval'):
            m.collect(self.db, Source([event]))

    def test_database_version_rejected(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as tmp:
            path = str(Path(tmp) / 'future.sqlite')
            db = sqlite3.connect(path)
            db.execute('PRAGMA user_version=2')
            db.close()
            with self.assertRaisesRegex(ValueError, 'schema'):
                m.connect(path)


if __name__ == '__main__':
    unittest.main()
