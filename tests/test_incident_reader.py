"""Offline contract tests; no secrets or live GitHub quota required."""
import json
import unittest
from unittest.mock import patch
from pipelines.incident_reader import IncidentClient, Observer, Unknown, RoutineClient, observer_for, _registry

HEAD = 'a'*40
OTHER = 'b'*40
ENV = {'INCIDENT_GITHUB_APP_ID': '1', 'INCIDENT_GITHUB_INSTALLATION_ID': '2',
       'INCIDENT_GITHUB_PRIVATE_KEY': 'secret-key'}


class Fake:
    def __init__(self):
        self.calls = []
        self.head = HEAD
        self.fail = None
        self.paginate = False
        self.change = False
        self.pr_reads = 0
        self.rate = False
        self.expired = False
        self.missing = False

    def __call__(self, method, path, token, payload):
        self.calls.append((method, path, token, payload))
        headers = {'X-RateLimit-Resource': 'core', 'X-RateLimit-Limit': '5000',
                   'X-RateLimit-Remaining': '4999', 'X-RateLimit-Used': '1', 'X-RateLimit-Reset': '2000'}
        if self.rate:
            return 429, {**headers, 'Retry-After': '120', 'X-RateLimit-Remaining': '0'}, {}
        if self.fail and self.fail in path:
            return 503, headers, {}
        if method == 'POST':
            return 201, headers, {'token': 'secret-token', 'expires_at':
                                 '1970-01-01T00:00:00Z' if self.expired else '2099-01-01T00:00:00Z'}
        if '/pulls/' in path:
            self.pr_reads += 1
            return 200, headers, {'head': {'sha': OTHER if self.change and self.pr_reads > 1 else self.head}}
        if '/check-runs' in path:
            if self.paginate:
                headers['Link'] = '<https://api.github.com/next>; rel="next"'
            return 200, headers, {'check_runs': [] if self.missing else [
                {'name': 'test', 'status': 'completed', 'conclusion': 'success'}]}
        if '/statuses' in path:
            return 200, headers, []
        if '/jobs' in path:
            return 200, headers, {'jobs': [{'status': 'completed', 'conclusion': 'success'}]}
        return 200, headers, {'workflow_runs': [{'id': 9, 'workflow_id': 3, 'head_sha': self.head,
                                              'status': 'completed', 'conclusion': 'success'}]}


class ReaderTests(unittest.TestCase):
    def setUp(self):
        self.fake, self.events = Fake(), []
        self.client = IncidentClient('incident', 'owner/repo', env=ENV, send=self.fake,
            signer=lambda *args: 'secret-jwt', clock=lambda: 1000, telemetry=self.events.append)
        self.observer = Observer(self.client, 1, ['test'])

    def test_complete_green_and_safe_telemetry(self):
        self.assertEqual(self.observer.sample()['state'], 'GREEN')
        self.assertEqual(self.client.requests, 7)
        self.assertEqual(self.fake.calls[0][3]['permissions']['actions'], 'read')
        text = json.dumps(self.events)
        for secret in ('secret-key', 'secret-token', 'secret-jwt', 'Authorization'):
            self.assertNotIn(secret, text)
        for field in ('resource', 'limit', 'remaining', 'used', 'reset'):
            self.assertIn(field, self.events[-1])

    def test_routine_cannot_select_incident(self):
        with self.assertRaises(Unknown):
            IncidentClient('routine', 'owner/repo', env=ENV, send=self.fake)
        self.assertEqual(self.fake.calls, [])

    def test_routine_exhaustion_does_not_block_incident(self):
        routine = RoutineClient('routine-token', send=lambda *a: (403,
            {'X-RateLimit-Remaining': '0', 'X-RateLimit-Reset': '999999'}, {}))
        with self.assertRaises(Unknown):
            routine.read('/repos/owner/repo/pulls/1')
        self.assertEqual(self.observer.sample()['state'], 'GREEN')
        self.assertEqual(self.client.backoff_until, 0)

    def test_missing_credentials_no_fallback(self):
        self.client.env = {'GITHUB_TOKEN': 'routine'}
        self.assertEqual(self.observer.sample()['state'], 'UNKNOWN')
        self.assertEqual(self.fake.calls, [])

    def test_expired_mint(self):
        self.fake.expired = True
        self.assertEqual(self.observer.sample()['state'], 'UNKNOWN')
        self.assertEqual(len(self.fake.calls), 1)

    def test_each_incomplete_surface_unknown(self):
        for endpoint in ('/pulls/', '/check-runs', '/statuses', '/actions/runs', '/jobs'):
            with self.subTest(endpoint=endpoint):
                self.fake.fail = endpoint
                self.assertEqual(self.observer.sample()['state'], 'UNKNOWN')

    def test_budget_never_partial_green(self):
        self.fake.paginate = True
        result = self.observer.sample()
        self.assertEqual(result['state'], 'UNKNOWN')
        self.assertEqual(result['reads'], 10)

    def test_complete_two_page_checks(self):
        original = self.client.send
        def paginated(method, path, token, payload):
            status, headers, data = original(method, path, token, payload)
            if '/check-runs' in path and path.endswith('&page=1'):
                headers['Link'] = '<https://api.github.com/ignored>; rel="next"'
            return status, headers, data
        self.client.send = paginated
        self.assertEqual(self.observer.sample()['state'], 'GREEN')
        self.assertEqual(self.client.requests, 8)

    def test_missing_required_unknown(self):
        self.fake.missing = True
        self.assertEqual(self.observer.sample()['state'], 'UNKNOWN')

    def test_failed_status_cannot_be_hidden_by_successful_check(self):
        original = self.client.send
        def conflicting(method, path, token, payload):
            status, headers, data = original(method, path, token, payload)
            if '/statuses' in path:
                data = [{'context': 'test', 'state': 'failure'}]
            return status, headers, data
        self.client.send = conflicting
        self.assertEqual(self.observer.sample()['state'], 'PENDING')

    def test_same_named_checks_require_every_result_to_pass(self):
        original = self.client.send
        for conclusions in (('failure', 'success'), ('success', 'failure'),
                            (None, 'success'), ('success', 'success')):
            with self.subTest(conclusions=conclusions):
                def conflicting(method, path, token, payload):
                    status, headers, data = original(method, path, token, payload)
                    if '/check-runs' in path:
                        data = {'check_runs': [
                            {'name': 'test', 'status': 'completed' if conclusion else 'in_progress',
                             'conclusion': conclusion} for conclusion in conclusions]}
                    return status, headers, data
                self.client.send = conflicting
                self.assertEqual(self.observer.sample()['state'],
                                 'GREEN' if conclusions == ('success', 'success') else 'PENDING')

    def test_new_head_invalidates_ids_even_on_failure(self):
        self.observer.sample()
        self.fake.head, self.fake.fail = OTHER, '/check-runs'
        self.assertEqual(self.observer.sample()['state'], 'UNKNOWN')
        self.assertEqual(self.observer.head, OTHER)
        self.assertEqual(self.observer.run_ids, {})
        self.assertEqual(self.observer.workflow_ids, set())

    def test_mid_sample_head_change_unknown(self):
        self.fake.change = True
        self.assertEqual(self.observer.sample()['state'], 'UNKNOWN')
        self.assertEqual(self.observer.run_ids, {})

    def test_rate_headers_backoff_and_no_retry(self):
        self.fake.rate = True
        self.observer.sample()
        self.assertGreaterEqual(self.client.backoff_until, 2000)
        self.observer.sample()
        self.assertEqual(len(self.fake.calls), 1)
        self.assertTrue(self.events[0]['reserve_alert'])

    def test_one_shared_observer(self):
        _registry.clear()
        self.assertIs(observer_for(self.client, 1, ['test']), observer_for(self.client, 1, ['test']))

    def test_deadline_no_read(self):
        with patch('pipelines.incident_reader.time.monotonic', return_value=self.observer.started+1800):
            self.assertEqual(self.observer.sample()['state'], 'UNKNOWN')
        self.assertEqual(self.fake.calls, [])

    def test_transport_exception_redacted(self):
        self.client.send = lambda *a: (_ for _ in ()).throw(ValueError('secret-token'))
        self.assertNotIn('secret-token', json.dumps(self.observer.sample()))

    def test_token_reused(self):
        self.observer.sample()
        self.observer.sample()
        self.assertEqual(sum(c[0] == 'POST' for c in self.fake.calls), 1)


if __name__ == '__main__':
    unittest.main()
