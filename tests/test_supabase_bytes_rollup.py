"""Recorded-format summaries; no network or measurement jobs."""
from datetime import datetime, timezone
import io
import json
from pathlib import Path
import tempfile
import unittest
import yaml
from urllib.parse import parse_qs, urlsplit
from unittest import mock
from contextlib import redirect_stdout, redirect_stderr
from pipelines import gh_sbclient as sb
from pipelines import rollup_supabase_bytes as rollup

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / 'tests/fixtures/supabase-bytes/recorded-summary.md'

class RollupTest(unittest.TestCase):
    def test_window_dedup_writes_and_attribution(self):
        rows, legacy = rollup.parse_summaries([FIXTURE], datetime(2026,10,30,tzinfo=timezone.utc), datetime(2026,11,1,tzinfo=timezone.utc))
        self.assertEqual((len(rows), legacy), (2, 1))
        self.assertEqual(rows[0]['run_id'], '41202210713')
        self.assertEqual(sum(v[1] for v in rollup.aggregate(rows).values()), 1300)
        self.assertEqual(sum(v[2] for v in rollup.aggregate(rows, True).values()), 300)
        rows, _ = rollup.parse_summaries([FIXTURE], datetime(2026,10,31,tzinfo=timezone.utc), datetime(2026,11,1,tzinfo=timezone.utc))
        self.assertEqual(len(rows), 1)

    def test_cli_coverage_and_totals(self):
        out = io.StringIO()
        with mock.patch('sys.argv', ['rollup', str(FIXTURE.parent), '--days', '2', '--until', '2026-11-01T00:00:00+00:00']), redirect_stdout(out):
            self.assertEqual(rollup.main(), 0)
        self.assertIn('NOT COVERED', out.getvalue())
        self.assertIn('must not be read as zero', out.getvalue())
        self.assertIn('1200\t300', out.getvalue())

    def test_labels_and_retained_summary(self):
        sb._BYTES.clear(); sb._WIRE.clear()
        self.addCleanup(sb._BYTES.clear); self.addCleanup(sb._WIRE.clear)
        sb._count('GET', '/rest/v1/players', 200, 50)
        with tempfile.TemporaryDirectory() as tmp:
            step = Path(tmp)/'step-uuid'
            env = {'GITHUB_ACTIONS':'true','GITHUB_WORKFLOW':'Health artifacts', 'GITHUB_RUN_ID':'123', 'GITHUB_RUN_ATTEMPT':'2', 'GITHUB_JOB':'build', 'GITHUB_STEP_SUMMARY':str(step), 'RUNNER_TEMP':tmp, 'SUPABASE_BYTES_CALLER':'espn'}
            with mock.patch.dict('os.environ', env, clear=True), mock.patch('sys.argv', ['/some/path/import.py']), redirect_stderr(io.StringIO()):
                sb._emit_bytes_summary()
            text = step.read_text()
            ctx = json.loads(next(l for l in text.splitlines() if l.startswith('[supabase-bytes]')).split(' context=')[1])
            self.assertEqual([ctx[k] for k in ('script','caller','run_id','run_attempt','job','step')], ['import.py','espn','123','2','build','step-uuid'])
            self.assertEqual(len(list((Path(tmp)/'supabase-bytes').glob('*.md'))), 1)

    def test_download_failure_stops_without_retry(self):
        import subprocess
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(rollup.subprocess, 'run', side_effect=subprocess.CalledProcessError(1, 'gh')) as run:
            with self.assertRaises(subprocess.CalledProcessError):
                rollup.download(Path(tmp), 'owner/repo', datetime(2026,10,30,tzinfo=timezone.utc))
            self.assertEqual(run.call_count, 1)

    def test_malformed_structured_record_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'bad.md'
            path.write_text('[supabase-bytes] invalid context={}\n')
            with self.assertRaises(ValueError):
                rollup.parse_summaries([path], datetime(2026,10,30,tzinfo=timezone.utc), datetime(2026,11,1,tzinfo=timezone.utc))

    def test_download_query_is_encoded_utc_seconds(self):
        from datetime import timedelta
        import subprocess
        since = datetime(2026, 10, 31, 14, 30, 12, 123456,
                         tzinfo=timezone(timedelta(hours=2)))
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(
                rollup.subprocess, 'run', side_effect=subprocess.CalledProcessError(1, 'gh')) as run:
            with self.assertRaises(subprocess.CalledProcessError):
                rollup.download(Path(tmp), 'owner/repo', since)
            endpoint = run.call_args.args[0][-1]
            query = parse_qs(urlsplit(endpoint).query)
            self.assertEqual(query, {'created': ['>=2026-10-31T12:30:12Z'], 'per_page': ['100']})
            self.assertNotIn('+', endpoint)
            self.assertIn('%3E%3D', endpoint)
            self.assertIn('%3A', endpoint)

    def test_missing_or_wrong_context_fields_fail_clearly(self):
        line = next(line for line in FIXTURE.read_text().splitlines()
                    if line.startswith('[supabase-bytes]') and ' context=' in line)
        prefix, context = line.split(' context=')
        for field in ('script', 'caller', 'workflow', 'event', 'at'):
            for value in (None, 42, []):
                with self.subTest(field=field, value=value), tempfile.TemporaryDirectory() as tmp:
                    ctx = json.loads(context)
                    if value is None:
                        del ctx[field]
                    else:
                        ctx[field] = value
                    path = Path(tmp)/'invalid.md'
                    path.write_text(prefix + ' context=' + json.dumps(ctx))
                    with self.assertRaisesRegex(ValueError, 'counter needs string'):
                        rollup.parse_summaries([path], datetime(2026,10,30,tzinfo=timezone.utc), datetime(2026,11,1,tzinfo=timezone.utc))
                    with mock.patch('sys.argv', ['rollup', tmp]), redirect_stderr(io.StringIO()) as err:
                        self.assertEqual(rollup.main(), 1)
                    self.assertIn('Rollup stopped: ValueError', err.getvalue())

    def test_shim_jobs_retain_artifacts(self):
        paths = list((ROOT / '.github/workflows').glob('*.yml'))
        self.assertTrue(paths, 'workflow glob must find the repo regardless of cwd')
        shim_jobs = 0
        matrix_jobs = 0
        for path in paths:
            text = path.read_text()
            if 'pipelines/gh_sbclient.py' not in text:
                continue
            for job in yaml.safe_load(text)['jobs'].values():
                steps = job.get('steps', [])
                if not any('pipelines/gh_sbclient.py' in step.get('run', '') for step in steps):
                    continue
                shim_jobs += 1
                uploads = [step for step in steps if step.get('name') == 'Retain Supabase byte counters (JEG-1458)']
                self.assertEqual(len(uploads), 1, path)
                upload = uploads[0]
                self.assertIs(upload.get('continue-on-error'), True, path)
                self.assertEqual(upload.get('if'), 'always()', path)
                name = upload['with']['name']
                self.assertIn('${{ github.job }}', name, path)
                self.assertIn('${{ github.run_attempt }}', name, path)
                matrix = job.get('strategy', {}).get('matrix', {})
                if matrix:
                    matrix_jobs += 1
                    for key in matrix:
                        if key not in ('include', 'exclude'):
                            self.assertIn('${{ matrix.' + key + ' }}', name, path)
                for step in steps:
                    if 'python' in step.get('run', ''):
                        label = step.get('env', {}).get('SUPABASE_BYTES_CALLER', '')
                        self.assertTrue(label.startswith(path.stem + ':'), (path, step.get('name')))
                        self.assertRegex(label, r'^[a-z0-9:-]+$')
        self.assertEqual(shim_jobs, 24)
        self.assertGreater(matrix_jobs, 0)
        health = (ROOT / '.github/workflows/health-artifacts.yml').read_text()
        self.assertIn("grep '^\\[supabase-bytes\\]' /tmp/build.log", health)

if __name__ == '__main__':
    unittest.main()
