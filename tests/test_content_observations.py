"""Local, deterministic observation-clock and native-content contracts."""
import sqlite3
from dataclasses import asdict
from pathlib import Path
import tempfile
import unittest

from pipelines.lib.content_observations import Ledger, Scope, content_hash, verdict
from pipelines.lib.dataset_status import build_dataset_status


class Observations(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1])
        self.addCleanup(self.tmp.cleanup)
        self.ledger = Ledger(Path(self.tmp.name) / 'ledger.sqlite3')
        self.scope = Scope('fantasycalc', 'values', 2026, 'ros', 'ppr', '12_qb1')
        self.rows = [{'player': {'id': 1}, 'value': 100}]

    def observe(self, at, rows=None, **kwargs):
        return self.ledger.observe(self.scope, self.rows if rows is None else rows,
                                   attempted_at=at, expected=1, **kwargs)

    def test_baseline_and_identical_repull(self):
        first = self.observe('2026-11-01T00:00:00Z')
        self.assertIn('content_vintage_unknown', verdict(first)['reasons'])
        changed = self.observe('2026-11-02T00:00:00Z', [{'player': {'id': 1}, 'value': 101}])
        again = self.observe('2026-11-03T01:00:00Z', [{'player': {'id': 1}, 'value': '101.0'}])
        self.assertEqual(again['last_observed_change_at'], changed['last_observed_change_at'])
        self.assertEqual(again['successful_fetch_at'], '2026-11-03T01:00:00Z')
        self.assertIn('content_stale', verdict(again, '2026-11-03T01:00:00Z')['reasons'])
        self.assertNotIn('pull_overdue', verdict(again, '2026-11-03T01:00:00Z')['reasons'])

    def test_boundary_failure_and_immutability(self):
        self.observe('2026-11-01T00:00:00Z')
        changed = self.observe('2026-11-02T00:00:00Z', [{'player_id': 1, 'value': 102}])
        self.assertFalse(verdict(changed, '2026-11-03T00:00:00Z')['stale'])
        self.assertTrue(verdict(changed, '2026-11-03T00:00:01Z')['stale'])
        failed = self.observe('2026-11-04T00:00:00Z', result='failed')
        self.assertEqual(failed['successful_fetch_at'], changed['successful_fetch_at'])
        self.assertIn('content_stale', verdict(failed, '2026-11-04T00:00:00Z')['reasons'])
        with sqlite3.connect(self.ledger.path) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM observations').fetchone()[0], 3)
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute('DELETE FROM observations')
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute("UPDATE observations SET result='success'")

    def test_partial_and_version_baseline(self):
        self.observe('2026-11-01T00:00:00Z')
        partial = self.observe('2026-11-02T00:00:00Z', complete=False)
        self.assertEqual(partial['successful_fetch_at'], '2026-11-01T00:00:00Z')
        self.assertIn('incomplete_scope', verdict(partial)['reasons'])
        new = self.observe('2026-11-03T00:00:00Z', normalizer_version='native-v2')
        self.assertIsNone(new['last_observed_change_at'])
        self.assertEqual(new['observation_kind'], 'normalizer_baseline')

    def test_scopes_are_independent(self):
        self.observe('2026-11-01T00:00:00Z')
        self.assertIsNone(self.ledger.latest(Scope('espn', 'k', 2026, 'ros', 'ppr', 'native')))

    def test_vendor_timestamp_does_not_renew_identical_numbers(self):
        self.observe('2026-11-01T00:00:00Z', source_updated_at='2026-10-31T00:00:00Z', trusted_numeric_time=True)
        again = self.observe('2026-11-02T00:00:00Z', source_updated_at='2026-11-02T00:00:00Z', trusted_numeric_time=True)
        self.assertEqual(again['source_updated_at'], '2026-10-31T00:00:00Z')
        future = dict(again, source_updated_at='2026-11-05T00:00:00Z')
        self.assertIn('future_timestamp', verdict(future, '2026-11-02T00:00:00Z')['reasons'])

    def test_untrusted_page_date_is_supporting_evidence_only(self):
        observed = self.observe('2026-11-01T00:00:00Z', source_updated_at='2026-11-01')
        self.assertEqual(observed['source_updated_at'], '2026-11-01')
        self.assertIn('content_vintage_unknown', verdict(observed)['reasons'])
        with self.assertRaises(ValueError):
            self.observe('2026-11-02T00:00:00Z', source_updated_at='2026-11-02', trusted_numeric_time=True)

    def test_propagation_mismatch(self):
        observed = self.observe('2026-11-01T00:00:00Z', served_hash='wrong')
        self.assertIn('served_hash_mismatch', verdict(observed)['reasons'])

    def test_all_adapters_reorder_cosmetics_and_numeric_changes(self):
        examples = {
            'espn': {'canon': '1', 'pos': 'QB', 'weeks': {'1': {'pass_yds': 1.123456}}},
            'fantasycalc': {'player': {'id': 1}, 'value': 100},
            'razzball': {'player_name': 'One', 'pos': 'QB', 'rz_std_ppg': 1, 'rz_half_ppr_ppg': 2, 'rz_ppr_ppg': 3},
            'cbsros': {'player_name': 'One', 'gp': 8, 'rec': None},
        }
        for source, row in examples.items():
            with self.subTest(source=source):
                second = dict(row, player_id='2')
                original = content_hash(source, [row, second])
                cosmetic = dict(row, fetched_at='today', vintage_date='today', html='advert')
                self.assertEqual(original, content_hash(source, [second, cosmetic]))
                changed = dict(row)
                if source == 'espn':
                    changed['weeks'] = {'1': {'pass_yds': 1.123457}}
                else:
                    changed[{'fantasycalc': 'value', 'razzball': 'rz_std_ppg', 'cbsros': 'rec'}[source]] = 0
                self.assertNotEqual(original, content_hash(source, [changed, second]))
                self.assertNotEqual(original, content_hash(source, [row]))

    def test_cbs_nested_native_stats_and_source_ids(self):
        row = {'player_name': 'One', 'gp': 8, 'raw_stats': {'rec': 12}}
        changed = dict(row, raw_stats={'rec': 13})
        self.assertNotEqual(content_hash('cbsros', [row]), content_hash('cbsros', [changed]))
        fc = {'name': 'One', 'fantasycalc_id': 1, 'value': 10}
        self.assertEqual(content_hash('fantasycalc', [fc]),
                         content_hash('fantasycalc', [dict(fc, name='Cosmetic Name')]))

    def test_invalid_scope_coverage_and_duplicates(self):
        with self.assertRaises(ValueError):
            content_hash('fantasycalc', self.rows * 2)
        with self.assertRaises(ValueError):
            self.observe('2026-11-01')
        with self.assertRaises(ValueError):
            self.ledger.observe(Scope('espn', 'skill', 2026, 'ros', 'native', 'native'),
                [{'player_id': 1, 'pos': 'K', 'stats': {'fg': 1}}],
                attempted_at='2026-11-01T00:00:00Z', expected=1)
        self.observe('2026-11-01T00:00:00Z')
        changed = self.observe('2026-11-02T00:00:00Z', [{'player_id': 1, 'value': 2}])
        failed = self.observe('2026-11-03T00:00:00Z', result='failed', normalizer_version='v2')
        self.assertEqual(changed['last_observed_change_at'], failed['last_observed_change_at'])
        self.assertEqual(changed['normalizer_version'], failed['normalizer_version'])

    def test_dataset_status_fails_closed_and_adds_cbs(self):
        status = build_dataset_status({'as_of': '2026-11-05', 'n_cbsros_complete': 300}, [{'name': str(i)} for i in range(400)],
                                      observation_ledger=self.ledger, evaluated_at='2026-11-05T00:00:00Z')
        entries = {e['key']: e for e in status['datasets']}
        self.assertIn('cbsros', entries)
        self.assertEqual(entries['cbsros']['status'], 'stale')
        self.assertEqual(entries['cbsros']['completeness']['priced'], 300)
        self.assertTrue(entries['espn']['stale'])
        self.assertEqual(entries['espn']['stale_reason'], entries['our_value']['stale_reason'])
        self.assertIn('content_vintage_unknown', entries['cbsros']['stale_reason'])

    def test_dataset_status_reads_exact_scoped_ledger(self):
        self.observe('2026-11-05T00:00:00Z', source_updated_at='2026-11-04T23:00:00Z', trusted_numeric_time=True)
        status = build_dataset_status({'as_of': '2026-11-05'}, [{'name': str(i)} for i in range(400)],
            observation_ledger=self.ledger, observation_scopes={'fantasycalc': [asdict(self.scope)]},
            evaluated_at='2026-11-05T00:00:00Z')
        fc = next(e for e in status['datasets'] if e['key'] == 'fantasycalc')
        self.assertFalse(fc['stale'])
        self.assertEqual(fc['freshness']['observations'][0]['content_age_seconds'], 3600)


if __name__ == '__main__':
    unittest.main()
