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


class ReviewRegressions(unittest.TestCase):
    setUp = Observations.setUp
    observe = Observations.observe
    def test_wrong_source_and_missing_espn_datasets_fail_closed(self):
        self.observe('2026-11-05T00:00:00Z', source_updated_at='2026-11-05T00:00:00Z', trusted_numeric_time=True)
        skill = Scope('espn', 'k', 2026, 'ros', 'native', 'native')
        self.ledger.observe(skill, [{'canon': '1', 'pos': 'K', 'weeks': {'1': {'yds': 1}}}],
            attempted_at='2026-11-05T00:00:00Z', expected=1,
            source_updated_at='2026-11-05T00:00:00Z', trusted_numeric_time=True)
        for keys in ([asdict(self.scope)], [asdict(skill)]):
            status = build_dataset_status({'as_of': '2026-11-05'}, [{'name': str(i)} for i in range(400)],
                observation_ledger=self.ledger, observation_scopes={'espn': keys},
                evaluated_at='2026-11-05T00:00:00Z')
            for entry in status['datasets']:
                if entry['key'] in ('espn', 'our_value'):
                    self.assertTrue(entry['stale'])

    def test_team_only_correction_preserves_numeric_clock(self):
        self.observe('2026-11-01T00:00:00Z')
        changed = self.observe('2026-11-02T00:00:00Z', [{'player_id': 1, 'value': 101, 'team': 'SEA'}])
        corrected = self.observe('2026-11-04T00:00:00Z', [{'player_id': 1, 'value': 101, 'team': 'NYJ'}])
        self.assertEqual(changed['normalized_content_hash'], corrected['normalized_content_hash'])
        self.assertEqual(changed['last_observed_change_at'], corrected['last_observed_change_at'])
        self.assertIn('content_stale', verdict(corrected, '2026-11-04T00:00:00Z')['reasons'])

    def test_real_fc_entry_writes_scopes_and_fails_closed_on_ledger_error(self):
        import os
        from unittest.mock import patch
        from pipelines import pull_fantasycalc_12team as pull
        from pipelines.lib.content_observations import recorded_scopes
        rows = [{'player': {'id': i, 'name': str(i), 'position': 'WR'}, 'value': i} for i in range(200)]
        output = Path(self.tmp.name) / 'cache'
        with patch.dict(os.environ, CONTENT_OBSERVATION_LEDGER=str(self.ledger.path)):
            self.assertEqual(0, pull.main(['--cache-dir', str(output)], fetch_fn=lambda _: rows))
            scopes = recorded_scopes(self.ledger)['fantasycalc']
            self.assertEqual(6, len(scopes))
            self.assertTrue(all(self.ledger.latest(Scope(**k))['result'] == 'success' for k in scopes))
            # A failed acquisition invalidates previous success for every consumed scope.
            with self.assertRaises(RuntimeError):
                pull.main(['--cache-dir', str(output)], fetch_fn=lambda _: (_ for _ in ()).throw(RuntimeError('offline')))
            self.assertTrue(all(self.ledger.latest(Scope(**k))['result'] == 'failed' for k in scopes))
        blocked = Path(self.tmp.name) / 'not-a-directory'
        blocked.write_text('blocked')
        with patch.dict(os.environ, CONTENT_OBSERVATION_LEDGER=str(blocked / 'ledger')):
            with self.assertRaises(OSError):
                pull.main(['--cache-dir', str(output / 'new')], fetch_fn=lambda _: rows)
            self.assertFalse((output / 'new').exists())

    def test_razzball_and_cbs_entrypoints_record_before_promotion(self):
        import os
        from unittest.mock import patch
        from pipelines import pull_razzball_ros as rz, pull_cbs_ros_projections as cbs
        from pipelines.lib.content_observations import acquisition_scope
        rz_row = {'player_name': 'One', 'pos': 'QB', 'rz_std_ppg': 1,
                  'rz_half_ppr_ppg': 2, 'rz_ppr_ppg': 3}
        snap = {'rows': [rz_row], 'vintage_date': '2026-11-05', 'page_stamps': {},
                'row_count': 1, 'summary': {'by_pos': {'QB': 1}},
                'review_count': 0, 'ppg_gate_diverging': []}
        with patch.dict(os.environ, CONTENT_OBSERVATION_LEDGER=str(self.ledger.path)):
            with patch.object(rz, 'pull', return_value=snap), patch.object(rz, 'write_csv'):
                self.assertEqual(0, rz.main(['--out-dir', str(Path(self.tmp.name) / 'rz')]))
            self.assertEqual('success', self.ledger.latest(acquisition_scope('razzball'))['result'])
            cbs_rows = lambda pos, html: ([{'player_name': pos, 'pos': pos, 'gp': 8, 'raw_stats': {'rec': 2}}], [])
            with patch('sys.argv', ['pull', '--out-dir', str(Path(self.tmp.name) / 'cbs')]), \
                 patch.object(cbs, 'fetch', return_value='html'), \
                 patch.object(cbs, 'parse_position', side_effect=cbs_rows), \
                 patch.object(cbs, 'pull_weekly', return_value={'weeks': {}, 'not_offered_weeks': [], 'errors': []}):
                self.assertEqual(0, cbs.main())
            self.assertEqual('success', self.ledger.latest(acquisition_scope('cbsros'))['result'])
            with patch.object(rz, 'pull', side_effect=rz.PullError('offline', 'SOURCE_BLOCKED')):
                self.assertEqual(1, rz.main(['--out-dir', str(Path(self.tmp.name) / 'rz-failed')]))
            self.assertEqual('failed', self.ledger.latest(acquisition_scope('razzball'))['result'])

    def test_espn_failed_fetch_records_failed_observation(self):
        import os
        from unittest.mock import patch
        from pipelines import pull_espn_projections as espn
        from pipelines.lib.content_observations import acquisition_scope
        with patch.dict(os.environ, CONTENT_OBSERVATION_LEDGER=str(self.ledger.path)), \
             patch.object(espn, 'fetch_position', side_effect=RuntimeError('offline')), \
             patch.object(espn, 'log_line'):
            self.assertEqual(1, espn.main())
        self.assertEqual('failed', self.ledger.latest(acquisition_scope('espn'))['result'])

    def test_normal_bake_supplies_acquisition_scopes(self):
        import os
        from unittest.mock import patch
        from tests.test_bake_today_unboundlocal import BakeTodayUnboundLocalTest
        from pipelines.lib.content_observations import acquired, recorded_scopes
        fixture = BakeTodayUnboundLocalTest()
        fixture.setUp()
        self.addCleanup(fixture.tearDown)
        with patch.dict(os.environ, CONTENT_OBSERVATION_LEDGER=str(self.ledger.path)):
            acquired('espn', [{'canon': 'one', 'pos': 'QB', 'weeks': {'1': {'yds': 1}}}])
            result = fixture._run_bake()
            self.assertEqual(recorded_scopes(self.ledger), result['meta']['content_observation_scopes'])
            self.assertEqual('skill', result['meta']['content_observation_scopes']['espn'][0]['dataset'])

    def test_incomplete_coverage_cannot_certify_freshness(self):
        import json
        healthy = self.observe('2026-11-05T00:00:00Z', source_updated_at='2026-11-05T00:00:00Z', trusted_numeric_time=True)
        self.assertFalse(verdict(healthy, '2026-11-05T00:00:00Z')['stale'])
        for coverage in ({'complete': False, 'observed': 1, 'expected': 1},
                         {'complete': True, 'observed': 1, 'expected': 2}):
            self.assertIn('incomplete_coverage', verdict(dict(healthy, coverage=json.dumps(coverage)),
                '2026-11-05T00:00:00Z')['reasons'])

    def test_espn_success_records_native_acquisition(self):
        import os
        from unittest.mock import patch
        from tests.test_espn_pull_team_played_jeg574 import PullMainPerTeamWindowTest, PLAYED_THURSDAY
        from pipelines.lib.content_observations import acquisition_scope
        with patch.dict(os.environ, CONTENT_OBSERVATION_LEDGER=str(self.ledger.path)):
            PullMainPerTeamWindowTest().run_pull(PLAYED_THURSDAY)
        observation = self.ledger.latest(acquisition_scope('espn'))
        self.assertEqual('success', observation['result'])
        self.assertEqual('initial_baseline', observation['observation_kind'])


    def test_descriptive_fields_do_not_change_numeric_hash_for_any_adapter(self):
        examples = {
            'espn': {'player_id': 1, 'pos': 'QB', 'weeks': {'1': {'yds': 1}}},
            'fantasycalc': {'player_id': 1, 'pos': 'QB', 'value': 100},
            'razzball': {'player_id': 1, 'pos': 'QB', 'rz_std_ppg': 1, 'rz_half_ppr_ppg': 2, 'rz_ppr_ppg': 3},
            'cbsros': {'player_id': 1, 'pos': 'QB', 'gp': 8},
        }
        for source, row in examples.items():
            with self.subTest(source=source):
                self.assertEqual(content_hash(source, [row]),
                                 content_hash(source, [dict(row, pos='RB', team='NYJ')]))
