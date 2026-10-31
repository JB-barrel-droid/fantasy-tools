import tempfile
import unittest
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
                children.append({'id': 'drift', 'title': TITLE})
                return {'issueCreate': {'success': True}}
            return {'issueUpdate': {'success': True}}
        ticket({'missing': ['x']}, api)
        ticket({'missing': ['y']}, api)
        self.assertIn('issueCreate', calls[1][0])
        self.assertIn('issueUpdate', calls[3][0])
        self.assertEqual(calls[3][1]['id'], 'drift')
