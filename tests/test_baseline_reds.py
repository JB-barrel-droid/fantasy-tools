import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from pipelines.baseline_reds import report, results


class BaselineRedsTest(unittest.TestCase):
    def test_forced_known_and_new_red_preserve_failure_and_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'forced.py').write_text('import unittest\nclass Forced(unittest.TestCase):\n def test_known(self): self.fail("forced")\n def test_new(self): self.fail("forced")\n')
            registry = root / 'registry.json'
            registry.write_text(json.dumps([dict(test_id='forced.Forced.test_known', where=['CI'], ticket='JEG-1234', first_seen_main_sha='abc123', reason='forced')]))
            summary = root / 'summary'
            env = dict(os.environ, GITHUB_STEP_SUMMARY=str(summary))
            env['PYTHONPATH'] = str(root)
            proc = subprocess.run([sys.executable, '-m', 'pipelines.baseline_reds', '--registry', str(registry), '--context', 'CI', '--', sys.executable, '-m', 'unittest', 'forced'], env=env, text=True, capture_output=True)
            self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
            for text in ('`forced.Forced.test_known`: known baseline red (JEG-1234)', '`forced.Forced.test_new`: new red'):
                self.assertIn(text, proc.stdout)
                self.assertIn(text, summary.read_text())

    def test_context_does_not_hide_ci_regression(self):
        entry = dict(test_id='a.b', where=['local'], ticket='JEG-1')
        self.assertIn('new red', report([entry], {'a.b': 'red'}, 'CI', {}))

    def test_three_consecutive_nights_require_explicit_passes(self):
        entries = [dict(test_id='a.b', where=['nightly'], ticket='JEG-1')]
        history = {}
        for night in ('2026-10-29', '2026-10-30'):
            self.assertNotIn('can remove', report(entries, {'a.b': 'green'}, 'nightly', history, night))
        self.assertIn('can remove', report(entries, {'a.b': 'green'}, 'nightly', history, '2026-10-31'))
        self.assertNotIn('can remove', report(entries, {}, 'nightly', history, '2026-11-01'))

    def test_unittest_formats(self):
        self.assertEqual(results('FAIL: test_x (tests.a.A)\nERROR: test_y (tests.b.B.test_y)\n'), {'tests.a.A.test_x': 'red', 'tests.b.B.test_y': 'red'})

    def test_registry_validation_and_gate_output(self):
        from pipelines.baseline_reds import load_registry
        valid = dict(test_id='a.b', where=['CI'], ticket='JEG-123', first_seen_main_sha='abc', reason='test')
        invalid = [{}, dict(valid, ticket='oops'), dict(valid, where='CI'), dict(valid, where=['unknown']), dict(valid, test_id=''), dict(valid, first_seen_main_sha=''), dict(valid, expires='2026-02-30')]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'registry.json'
            for entry in invalid:
                path.write_text(json.dumps([entry]))
                with self.assertRaises(ValueError):
                    load_registry(path)
            for rc in (0, 7):
                proc = subprocess.run([sys.executable, '-m', 'pipelines.baseline_reds', '--registry', str(path), '--', sys.executable, '-c', f'print("gate output survives"); raise SystemExit({rc})'], capture_output=True, text=True)
                self.assertEqual(proc.returncode, 2 if rc == 0 else rc)
                self.assertIn('gate output survives', proc.stdout)
                self.assertIn('Malformed registry:', proc.stdout)

    def test_zero_exit_preserved(self):
        proc = subprocess.run([sys.executable, '-m', 'pipelines.baseline_reds', '--', sys.executable, '-c', 'print("green gate")'], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

    def test_signature_expiry_and_unattributed_commands(self):
        from datetime import date
        entry = dict(test_id='tests.a.A.test_x', where=['CI'], ticket='JEG-1', signature='TypeError: null slider')
        log = """python3 -m unittest tests.a
ERROR: test_x (tests.a.A)
----------------------------------------------------------------------
Traceback:
TypeError: null slider
----------------------------------------------------------------------
Ran 1 test
FAILED (errors=1)
run_suite: FAILED (rc=1, 0s): python3 -m unittest tests.a
node harness.mjs
bad harness
run_suite: FAILED (rc=3, 0s): node harness.mjs
run_suite: failed: python3 -m unittest tests.a
run_suite: failed: node harness.mjs
"""
        text = report([entry], results(log), 'CI', {}, rc=1, log=log)
        self.assertIn('known baseline red (JEG-1)', text)
        self.assertIn('`node harness.mjs`: unattributed failure', text)
        self.assertNotIn('`python3 -m unittest tests.a`: unattributed failure', text)
        self.assertNotIn('All failures are known', text)
        mismatch = report([dict(entry, signature='different')], results(log), 'CI', {}, rc=1, log=log)
        self.assertIn('new red; failure signature mismatch', mismatch)
        expired = report([dict(entry, expires='2026-10-30')], results(log), 'CI', {}, rc=1, log=log, today=date(2026, 10, 31))
        self.assertIn('new red; expired registry entry', expired)
        simple = log.split('run_suite: FAILED')[0]
        self.assertIn('All failures are known', report([entry], results(simple), 'CI', {}, rc=1, log=simple, command=['python3', '-m', 'unittest', 'tests.a']))

    def test_context_aware_removal_and_registered_only_note(self):
        entry = dict(test_id='a.b', where=['local'], ticket='JEG-1')
        history = {}
        for day in ('2026-10-29', '2026-10-30', '2026-10-31'):
            self.assertNotIn('can remove', report([entry], {'a.b': 'green'}, 'nightly', history, day))
        self.assertEqual(history, {})
        self.assertIn('new red; registered for local only', report([entry], {'a.b': 'red'}, 'CI', {}))
