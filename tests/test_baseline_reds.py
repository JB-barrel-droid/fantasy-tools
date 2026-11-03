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

    def test_checked_in_seeds_attribute_only_recorded_environments_and_signatures(self):
        from pipelines.baseline_reds import REGISTRY, load_registry
        entries = load_registry(REGISTRY)
        self.assertEqual(len(entries), len({e['test_id'] for e in entries}))
        for entry in entries:
            test = entry['test_id']
            owner, method = test.rsplit('.', 1)
            signature = entry.get('signature', 'recorded failure')
            log = f"ERROR: {method} ({owner})\n{signature}\n"
            with self.subTest(test=test):
                self.assertIn('known baseline red (' + entry['ticket'] + ')',
                              report(entries, results(log), 'local', {}, log=log))
                self.assertIn('new red', report(entries, results(log), 'CI', {}, log=log))
                if 'signature' in entry:
                    changed = f"ERROR: {method} ({owner})\nAssertionError: different failure\n"
                    self.assertIn('new red; failure signature mismatch',
                                  report(entries, results(changed), 'local', {}, log=changed))

    def test_nightly_fixture_targets_load_and_attribute_without_loader_crash(self):
        from pipelines.baseline_reds import observe_targets, load_registry, REGISTRY
        for target in observe_targets(load_registry(REGISTRY)):
            self.assertNotIn(target.rsplit('.', 1)[-1], ('setUpModule', 'setUpClass'))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'probe_mod.py').write_text('import unittest\ndef setUpModule(): raise RuntimeError("fixture sentinel")\nclass Probe(unittest.TestCase):\n def test_probe(self): pass\n')
            (root / 'probe_class.py').write_text('import unittest\nclass Probe(unittest.TestCase):\n @classmethod\n def setUpClass(cls): raise RuntimeError("fixture sentinel")\n def test_probe(self): pass\n')
            entries = [dict(test_id=test, where=['nightly'], ticket='JEG-1450', first_seen_main_sha='abc', reason='probe', signature='fixture sentinel') for test in ('probe_mod.setUpModule', 'probe_class.Probe.setUpClass')]
            registry = root / 'registry.json'
            registry.write_text(json.dumps(entries))
            env = dict(os.environ, PYTHONPATH=str(root))
            base = [sys.executable, '-m', 'pipelines.baseline_reds', '--registry', str(registry)]
            listed = subprocess.run(base + ['--list-observe-targets'], env=env, text=True, capture_output=True)
            self.assertEqual(listed.returncode, 0, listed.stderr)
            self.assertEqual(listed.stdout.splitlines(), ['probe_mod', 'probe_class.Probe'])
            history = root / 'history.json'
            proc = subprocess.run(base + ['--context', 'nightly', '--history', str(history), '--night', '2026-11-02', '--', sys.executable, '-m', 'unittest', *listed.stdout.splitlines()], env=env, text=True, capture_output=True)
            raw = subprocess.run([sys.executable, '-m', 'unittest', *listed.stdout.splitlines()], env=env, capture_output=True)
            self.assertNotEqual(raw.returncode, 0)
            self.assertEqual(proc.returncode, raw.returncode, proc.stdout + proc.stderr)
            self.assertNotIn('not a test', proc.stdout)
            for entry in entries:
                self.assertIn('`' + entry['test_id'] + '`: known baseline red (JEG-1450)', proc.stdout)
                self.assertEqual(json.loads(history.read_text())[entry['test_id']]['nightly']['2026-11-02'], 'red')
