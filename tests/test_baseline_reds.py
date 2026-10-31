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
            registry.write_text(json.dumps([dict(test_id='forced.Forced.test_known', where=['CI'], ticket='JEG-1234')]))
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
        entries = [dict(test_id='a.b', where=['local'], ticket='JEG-1')]
        history = {}
        for night in ('2026-10-29', '2026-10-30'):
            self.assertNotIn('can remove', report(entries, {'a.b': 'green'}, 'nightly', history, night))
        self.assertIn('can remove', report(entries, {'a.b': 'green'}, 'nightly', history, '2026-10-31'))
        self.assertNotIn('can remove', report(entries, {}, 'nightly', history, '2026-11-01'))

    def test_unittest_formats(self):
        self.assertEqual(results('FAIL: test_x (tests.a.A)\nERROR: test_y (tests.b.B.test_y)\n'), {'tests.a.A.test_x': 'red', 'tests.b.B.test_y': 'red'})
