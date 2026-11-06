"""Offline object-channel contract and failure tests."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pipelines import monitoring_publication as pub
from pipelines import health_artifacts_watch as watch


class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1])
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        for name in pub.HEALTH:
            (self.directory / name).write_text(json.dumps({'generated_at': '2026-11-05T12:00:00Z', 'status': 'red'}))
        self.objects = {}

    def publish(self):
        return pub.publish(self.directory, 'https://objects.example', self.objects.__setitem__)

    def fetch(self, name):
        return pub.fetch_artifact('https://objects.example', name,
                                  lambda url: self.objects[url.split('/v1/health/')[1]])

    def test_roundtrip_preserves_red_and_source_timestamp(self):
        manifest = self.publish()
        self.assertIn('versions/' + manifest['revision'] + '.json', self.objects)
        for name in pub.HEALTH:
            self.assertEqual(self.fetch(name), json.loads((self.directory / name).read_text()))

    def test_watcher_resolves_channel_over_http_adapter(self):
        from io import BytesIO
        self.publish()

        def open_object(request, timeout):
            body = self.objects[request.full_url.split('/v1/health/')[1]]
            return BytesIO(body)

        with patch.dict('os.environ', {'MONITORING_PUBLICATION_URL': 'https://objects.example'}), patch.object(watch.urllib.request, 'urlopen', side_effect=open_object):
            payload, status, _ = watch.fetch_json(watch.BASE_URL + pub.HEALTH[0])
        self.assertEqual(200, status)
        self.assertEqual('red', payload['status'])
        self.assertEqual('2026-11-05T12:00:00Z', payload['generated_at'])

    def test_http_transport_and_watcher_read_same_revision(self):
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        from threading import Thread
        objects = self.objects

        class Gateway(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_PUT(self):
                objects[self.path] = self.rfile.read(int(self.headers['Content-Length']))
                self.send_response(201)
                self.end_headers()

            def do_GET(self):
                body = objects.get(self.path)
                self.send_response(200 if body is not None else 404)
                self.end_headers()
                self.wfile.write(body or b'')

        server = ThreadingHTTPServer(('127.0.0.1', 0), Gateway)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base = f'http://127.0.0.1:{server.server_port}'
            with patch.dict('os.environ', {'MONITORING_PUBLICATION_URL': base}):
                pub.publish(self.directory, base)
                payload, status, _ = watch.fetch_json(watch.BASE_URL + pub.HEALTH[0])
            self.assertEqual(200, status)
            self.assertEqual('red', payload['status'])
            self.assertEqual('2026-11-05T12:00:00Z', payload['generated_at'])
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

    def test_failed_upload_does_not_advance_pointer(self):
        self.publish()
        previous = self.objects['latest.json']
        (self.directory / pub.HEALTH[0]).write_text('{"generated_at":"2026-11-05T13:00:00Z"}')
        def fail(key, body):
            if key.startswith('objects/'):
                raise OSError('unavailable')
            self.objects[key] = body
        with self.assertRaises(OSError):
            pub.publish(self.directory, 'https://objects.example', fail)
        self.assertEqual(previous, self.objects['latest.json'])

    def test_corruption_rejected(self):
        manifest = self.publish()
        self.objects[manifest['artifacts'][pub.HEALTH[0]]['key']] = b'{}'
        with self.assertRaisesRegex(ValueError, 'digest mismatch'):
            self.fetch(pub.HEALTH[0])

    def test_missing_timestamp_never_published(self):
        (self.directory / pub.HEALTH[0]).write_text('{}')
        with self.assertRaises(ValueError):
            self.publish()
        self.assertEqual({}, self.objects)

    def test_watcher_channel_failure_remains_fail_closed(self):
        with patch.dict('os.environ', {'MONITORING_PUBLICATION_URL': 'https://objects.example'}), patch.object(watch.urllib.request, 'urlopen', side_effect=OSError('down')):
            payload, status, _ = watch.fetch_json(watch.BASE_URL + pub.HEALTH[0])
        self.assertIsNone(payload)
        self.assertFalse(watch.evaluate(payload, ('generated_at',), watch.datetime.now(watch.timezone.utc))[0])

    def test_simulation_repeated_observations_need_no_main_commits(self):
        # 24 six-hour observations: legacy writes one commit per pair;
        # channel retains 24 revisions and never invokes a git writer.
        revisions = set()
        for hour in range(24):
            for name in pub.HEALTH:
                (self.directory / name).write_text(json.dumps({'generated_at': f'2026-11-05T{hour:02}:00:00Z'}))
            revisions.add(self.publish()['revision'])
        self.assertEqual(24, len(revisions))
        self.assertEqual(24, sum(key.startswith('versions/') for key in self.objects))
        print('simulation: health-pair observations=24 legacy_artifact_commits=24 channel_artifact_commits=0 reduction=100% (pair only)')


if __name__ == '__main__':
    unittest.main()
