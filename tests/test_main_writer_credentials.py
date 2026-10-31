"""JEG-1441 credential isolation, refusal and offline Git protocol proofs."""
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / '.github/scripts/main-writer-credential.py'
spec = importlib.util.spec_from_file_location('main_writer_credential', HELPER)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
REPO = 'JB-barrel-droid/fantasy-tools'
REQUEST = {'protocol': 'https', 'host': 'github.com', 'path': REPO+'.git'}


def environment(ref='refs/heads/main', **extra):
    return {'GITHUB_REF': ref, 'GITHUB_REPOSITORY': REPO,
            'MAIN_WRITER_TOKEN': 'synthetic-main-password',
            'BRANCH_WRITER_TOKEN': 'synthetic-branch-password', **extra}


class WriterCredentialTests(unittest.TestCase):
    def test_main_selects_only_app_token(self):
        self.assertEqual(module.credential(REQUEST, environment())['password'], 'synthetic-main-password')

    def test_main_refuses_missing_app_token_instead_of_falling_back(self):
        with self.assertRaises(ValueError):
            module.credential(REQUEST, environment(MAIN_WRITER_TOKEN=''))

    def test_branch_uses_only_nonexempt_default_token(self):
        self.assertEqual(module.credential(REQUEST, environment('refs/heads/safety/test'))['password'], 'synthetic-branch-password')

    def test_destination_and_ref_isolation(self):
        cases = [({**REQUEST, 'host': 'other.example'}, environment()),
                 ({**REQUEST, 'protocol': 'http'}, environment()),
                 ({**REQUEST, 'path': 'JB-barrel-droid/other.git'}, environment()),
                 (REQUEST, environment(GITHUB_REPOSITORY='JB-barrel-droid/other')),
                 (REQUEST, environment('')),
                 (REQUEST, environment('refs/tags/main')),
                 (REQUEST, environment('refs/pull/1/merge'))]
        for request, env in cases:
            with self.subTest(request=request, ref=env['GITHUB_REF']):
                with self.assertRaises(ValueError):
                    module.credential(request, env)

    def test_rejects_protocol_injection_in_token(self):
        for value in ['bad\nusername=bad', 'bad\rvalue', 'bad\0value']:
            with self.assertRaises(ValueError):
                module.credential(REQUEST, environment(MAIN_WRITER_TOKEN=value))

    def test_store_and_erase_never_persist_credentials(self):
        with tempfile.TemporaryDirectory() as td:
            for operation in ['store', 'erase']:
                result = subprocess.run([sys.executable, "-B", str(HELPER), operation], cwd=td,
                                        input='password=synthetic-password\n\n',
                                        text=True, capture_output=True, env=environment())
                self.assertEqual(result.returncode, 0)
                self.assertEqual(result.stdout, '')
                self.assertEqual(result.stderr, '')
            self.assertEqual(list(Path(td).iterdir()), [])

    def test_refusal_does_not_echo_any_token(self):
        result = subprocess.run([sys.executable, "-B", str(HELPER), 'get'],
                                input='protocol=https\nhost=other.example\npath='+REPO+'.git\n\n',
                                text=True, capture_output=True, env=environment())
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, '')
        self.assertNotIn('synthetic-main-password', result.stderr)
        self.assertNotIn('synthetic-branch-password', result.stderr)

    def test_real_git_credential_protocol_without_network_or_storage(self):
        with tempfile.TemporaryDirectory() as td:
            env = {**os.environ, **environment(), 'HOME': td, 'GIT_TERMINAL_PROMPT': '0'}
            # -B disables Apple Python's HOME/Library bytecode cache. Keep
            # the strict empty-directory assertion: no stored credential or cache.
            # In-memory request to Git's protocol; no HTTP, refs or remote push.
            result = subprocess.run(['git', '-c', 'credential.helper=', '-c',
                                     'credential.helper=!'+sys.executable+' -B "'+str(HELPER)+'"',
                                     '-c', 'credential.useHttpPath=true', 'credential', 'fill'],
                                    input='protocol=https\nhost=github.com\npath='+REPO+'.git\n\n',
                                    text=True, capture_output=True, cwd=td, env=env)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('username=x-access-token', result.stdout)
            self.assertIn('password=synthetic-main-password', result.stdout)
            self.assertNotIn('synthetic-main-password', result.stderr)
            self.assertEqual(list(Path(td).iterdir()), [])


if __name__ == '__main__':
    unittest.main()
