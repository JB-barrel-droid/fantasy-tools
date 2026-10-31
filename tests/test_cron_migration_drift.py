import tempfile
import unittest
import contextlib
import io
import re
from unittest.mock import patch
import tools.cron_migration_drift as checker
from pathlib import Path
from tools.cron_migration_drift import compare, migration_names, ticket, TITLE


class DriftTest(unittest.TestCase):
    def setUp(self):
        self.job = dict(name='daily', schedule='0 12 * * *', target='workflow:daily.yml', active=True)

    def test_match_and_whitespace(self):
        live = dict(self.job, schedule='0  12 * * *')
        self.assertFalse(any(compare([self.job], {'init'}, {'cron': [live], 'migrations': [{'version': '123', 'name': 'init'}]}).values()))

    def test_all_directions_and_changes(self):
        live = {'cron': [dict(self.job, schedule='1 12 * * *', target='workflow:other.yml', active=False), dict(self.job, name='extra')], 'migrations': [{'name': 'cloud_only'}]}
        diff = compare([self.job, dict(self.job, name='missing')], {'pending'}, live)
        self.assertEqual(diff['cron_in_supabase_not_repo'], ['extra'])
        self.assertEqual(diff['cron_in_repo_not_supabase'], ['missing'])
        self.assertEqual(len(diff['changed_schedules_targets_or_active']), 3)
        self.assertEqual(diff['migrations_in_repo_not_applied'], ['pending'])
        self.assertEqual(diff['migrations_in_supabase_not_repo'], ['cloud_only'])

    def test_invalid_inventory_is_not_empty(self):
        for jobs in ([self.job, self.job], [dict(self.job, target=None)]):
            with self.assertRaises(ValueError):
                compare([self.job], set(), {'cron': jobs, 'migrations': []})

    def test_migration_filenames(self):
        with tempfile.TemporaryDirectory() as d:
            for name in ['20261031120000_init.sql', 'jeg1195_weekly.sql', 'README.md']:
                Path(d, name).touch()
            self.assertEqual(migration_names(Path(d)), {'init', 'jeg1195_weekly'})

    def test_notify_creates_then_updates_same_ticket(self):
        calls = []
        children = []
        def api(query, variables):
            calls.append((query, variables))
            if query.startswith('query'):
                return {'issue': {'id': 'parent', 'team': {'id': 'team'}, 'children': {'nodes': children, 'pageInfo': {'hasNextPage': False}}}}
            if 'issueCreate' in query:
                children.append({'id': 'drift', 'title': TITLE, 'description': variables['i']['description'], 'state': {'type': 'started'}, 'url': 'https://linear.app/drift', 'archivedAt': None})
                return {'issueCreate': {'success': True}}
            return {'issueUpdate': {'success': True}}
        ticket({'missing': ['x']}, api)
        ticket({'missing': ['y']}, api)
        self.assertIn('issueCreate', calls[1][0])
        self.assertIn('issueUpdate', calls[3][0])
        self.assertEqual(calls[3][1]['id'], 'drift')


    def test_target_extraction_real_migration_commands(self):
        root = Path(__file__).resolve().parents[1]
        for filename, workflow in [
            ('gha_schedules_pg_cron.sql', 'pages.yml'),
            ('source_probe_schedules_20261008.sql', 'source-probe.yml'),
            ('ros_rankings_sync_schedule_20261029.sql', 'ros-rankings-sync.yml')]:
            sql = (root/'supabase/migrations'/filename).read_text()
            commands = re.findall(r"\$\$(SELECT public.dispatch_gha_workflow\(.*?)\$\$", sql, re.S)
            self.assertTrue(commands)
            self.assertEqual(checker.extract_target(commands[0]), 'workflow:' + workflow)
        # Both Python and the SELECT projection use these exact patterns.
        self.assertIn(checker.sql_literal(checker.WORKFLOW_PATTERN), checker.QUERY)
        self.assertIn(checker.sql_literal(checker.FUNCTION_PATTERN), checker.QUERY)
        spec = (root/'docs/audits/jeg285-phase2/02-pgcron-job-specs.md').read_text()
        raw = re.search(r"\$\$(delete from cron.job_run_details.*?)\$\$", spec, re.S)[1]
        expected = __import__('json').loads((root/'config/expected-cron.json').read_text())
        retention = next(row for row in expected if row['name'] == 'cron-retention-30d')
        self.assertEqual(checker.extract_target(raw), retention['target'])
        self.assertNotIn(raw, checker.QUERY)
        self.assertEqual(checker.extract_target('select public.weekly_fp_record_daily_check()'),
                         'function:public.weekly_fp_record_daily_check')

    def test_normalizes_legacy_names_and_explicit_exceptions(self):
        rules = {'aliases': {'old_name': {'canonical': 'new_name', 'reason': 'recorded rename'}},
                 'ignore': {'manual_only': {'reason': 'external inventory'}}}
        live = {'cron': [self.job], 'migrations': [
            {'name': 'monitoring_6h_and_posture_20261008'}, {'name': 'init'},
            {'name': 'old_name'}, {'name': 'manual_only'}]}
        diff = compare([self.job], {'20261008_monitoring_6h_and_posture',
                                  '20261031120000_init', 'new_name'}, live, rules)
        self.assertFalse(any(diff.values()))
        self.assertEqual(checker.normalize_migration('security_lockdown_20261008'),
                         checker.normalize_migration('20261008_security_lockdown'))

    def test_main_query_error_empty_and_low_inventory_never_notify(self):
        scenarios = [RuntimeError('sensitive connection detail'),
                     {'cron': [], 'migrations': []},
                     {'cron': [self.job], 'migrations': []},
                     {'cron': [], 'migrations': [{'name': 'init'}]},
                     {'cron': [self.job], 'migrations': [{'name': 'init'}]}]
        for scenario in scenarios:
            kwargs = {'side_effect': scenario} if isinstance(scenario, Exception) else {'return_value': scenario}
            with patch.object(checker, 'read_live', **kwargs), patch.object(checker, 'ticket') as notify:
                with contextlib.redirect_stderr(io.StringIO()) as err:
                    self.assertEqual(checker.main(['--notify']), 2)
                notify.assert_not_called()
                self.assertNotIn('sensitive connection detail', err.getvalue())

    def test_floor_boundary(self):
        expected = [dict(self.job, name=str(i)) for i in range(4)]
        live = {'cron': expected[:2], 'migrations': [{'name': 'init'}]}
        self.assertEqual(len(compare(expected, {'init'}, live)['cron_in_repo_not_supabase']), 2)
        live['cron'] = expected[:1]
        with self.assertRaises(ValueError):
            compare(expected, {'init'}, live)

    def test_notify_unchanged_and_closed_ticket(self):
        for state, archived in [('completed', None), ('canceled', None), ('started', '2026-10-31')]:
            calls = []
            children = [{'id': 'old', 'title': TITLE, 'state': {'type': state},
                         'archivedAt': archived, 'url': 'https://linear.app/old'}]
            def api(query, variables):
                calls.append((query, variables))
                if query.startswith('query'):
                    return {'issue': {'id': 'parent', 'team': {'id': 'team'}, 'children': {
                        'nodes': children, 'pageInfo': {'hasNextPage': False}}}}
                if 'issueCreate' in query:
                    children.append({'id': 'new', 'title': TITLE, 'state': {'type': 'started'},
                                     'archivedAt': None, 'url': 'https://linear.app/new',
                                     'description': variables['i']['description'].replace('Latest read-only diff', 'Older timestamped diff')})
                    return {'issueCreate': {'success': True}}
                self.fail('Unchanged diff must not update ticket')
            ticket({'missing': ['x']}, api)
            self.assertIn('issueCreate', calls[1][0])
            self.assertIn('https://linear.app/old', calls[1][1]['i']['description'])
            ticket({'missing': ['x']}, api)
            self.assertEqual(len(calls), 3)  # second run queries but makes no mutation
