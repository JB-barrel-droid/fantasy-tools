"""Recorded-format summaries; no network or measurement jobs."""
from datetime import datetime, timezone
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock
from contextlib import redirect_stdout, redirect_stderr
from pipelines import gh_sbclient as sb
from pipelines import rollup_supabase_bytes as rollup

FIXTURE = Path(__file__).parent / 'fixtures/supabase-bytes/recorded-summary.md'

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

    def test_shim_jobs_retain_artifacts(self):
        for path in Path('.github/workflows').glob('*.yml'):
            text = path.read_text()
            if 'pipelines/gh_sbclient.py' in text:
                self.assertIn('name: supabase-bytes-${{ github.job }}-${{ github.run_attempt }}', text, path)
        health = Path('.github/workflows/health-artifacts.yml').read_text()
        self.assertIn("grep '^\\[supabase-bytes\\]' /tmp/build.log", health)

if __name__ == '__main__':
    unittest.main()
