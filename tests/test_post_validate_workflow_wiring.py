"""Exercise the real rebuild validation shell with injected recovery outcomes."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from tests.test_rebuild_chain_workflow import CHAIN, find_step, script_of

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / '.github/workflows/rebuild-chain.yml'


def validation_shell():
    script = script_of(find_step(WORKFLOW.read_text(), CHAIN))
    start = script.index('set +e\nenv -u SUPABASE_URL -u SUPABASE_SERVICE_KEY make validate > output/post-rebuild-validate.log')
    end = script.index('# The published build', start)
    return script[start:end].replace('${{ steps.week.outputs.nfl_week }}', '8')


def exercise(initial, isolate=0, retry=0, confirm=0):
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp)
        (repo / 'output').mkdir()
        bin_dir = repo / 'bin'
        bin_dir.mkdir()
        (bin_dir / 'make').write_text('''#!/bin/sh
n=$(cat count 2>/dev/null || echo 0)
n=$((n + 1)); echo "$n" > count
echo "validation attempt $n"
if [ "$n" -eq 1 ]; then exit "$INITIAL"; fi
exit "$RETRY"
''')
        (bin_dir / 'python3').write_text('''#!/bin/sh
case "$1 $2" in
  'pipelines/isolate_post_validate.py isolate')
    echo isolate >> calls
    if [ "$ISOLATE" -ne 0 ]; then exit "$ISOLATE"; fi
    echo retry_pending > status; exit 0 ;;
  'pipelines/isolate_post_validate.py confirm')
    echo confirm >> calls
    if [ "$CONFIRM" -ne 0 ]; then exit "$CONFIRM"; fi
    echo published_with_holds > status; exit 0 ;;
  'pipelines/record_post_rebuild_validation.py --log')
    echo record >> calls; echo failed > status; exit 0 ;;
esac
exit 97
''')
        for executable in (bin_dir / 'make', bin_dir / 'python3'):
            executable.chmod(0o755)
        env = {**os.environ, 'PATH': f'{bin_dir}:{os.environ["PATH"]}',
               'INITIAL': str(initial), 'ISOLATE': str(isolate),
               'RETRY': str(retry), 'CONFIRM': str(confirm)}
        result = subprocess.run(['bash', '-e', '-c', validation_shell()], cwd=repo, env=env,
                                capture_output=True, text=True)
        calls = (repo / 'calls').read_text().splitlines() if (repo / 'calls').exists() else []
        status = (repo / 'status').read_text().strip() if (repo / 'status').exists() else None
        count = int((repo / 'count').read_text())
        return result, calls, status, count


class ValidationWiring(unittest.TestCase):
    def test_healthy_validation_does_not_isolate_or_retry(self):
        result, calls, status, count = exercise(0)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((calls, status, count), ([], None, 1))

    def test_decline_or_isolator_error_stays_red(self):
        for code in (3, 1):
            with self.subTest(code=code):
                result, calls, status, count = exercise(7, isolate=code)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual((calls, status, count), (['isolate', 'record'], 'failed', 1))
                self.assertIn('validation attempt 1', result.stdout)

    def test_retry_failure_stays_red_after_exactly_one_retry(self):
        result, calls, status, count = exercise(7, retry=9)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual((calls, status, count), (['isolate', 'record'], 'failed', 2))
        self.assertIn('validation attempt 2', result.stdout)

    def test_confirm_error_stays_red(self):
        result, calls, status, count = exercise(7, confirm=3)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual((calls, status, count), (['isolate', 'confirm', 'record'], 'failed', 2))

    def test_healthy_sources_advance_only_after_retry_and_confirm(self):
        result, calls, status, count = exercise(7)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((calls, status, count), (['isolate', 'confirm'], 'published_with_holds', 2))


if __name__ == '__main__':
    unittest.main()
