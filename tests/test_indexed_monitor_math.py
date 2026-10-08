"""JEG-208: native-only target report cannot certify derived or rendered values."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'pipelines'))
import build_index_math as builder


class IndexedMonitorMathTest(unittest.TestCase):
    def test_uniform_rescale_preserves_zero_missing_and_publisher_shape(self):
        factor, values = builder.simple_native_rescale({'a': 1000, 'b': 250, 'zero': 0, 'missing': None})
        self.assertEqual(factor, .07)
        self.assertEqual(values, {'a': 70, 'b': 17.5, 'zero': 0, 'missing': None})
        _, scaled = builder.simple_native_rescale({'a': 10, 'b': 2.5, 'zero': 0, 'missing': None})
        self.assertEqual(values, scaled)

    def test_unavailable_and_invalid_values_fail_closed(self):
        for native in ({}, {'a': None}, {'a': 0}, {'a': -1}, {'a': True}, {'a': '10'},
                       {'a': float('nan')}, {'a': float('inf')}, {'a': 1e-320}):
            with self.subTest(native=native), self.assertRaises(ValueError):
                builder.simple_native_rescale(native)

    def test_report_ignores_translated_fixture_and_visits_every_native_combo(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = Path(tmp)/'fixture.json'; output = Path(tmp)/'report.json'
            combo = {'native': {'a': 100, 'b': 25}, 'reindexed': {'a': 2, 'b': 999},
                     'translation': {'method': 'vorp-supabase'}, 'fit': {'bad': 'isotonic'}}
            fixture.write_text(json.dumps({'sources': {source: {'combos': {'full_12':combo, 'half_12':combo}}
                                                  for source in ('cbs','fantasycalc','fantasypros','usatoday','espn')}}))
            with mock.patch.object(builder, 'FIXTURE', fixture), mock.patch.object(builder, 'OUTPUT',output), \
                 mock.patch.object(builder, 'verify_ddf_leg', side_effect=AssertionError('Indexed invoked DDF')):
                builder.main()
            report = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(set(report['sources']), {'cbs','fantasycalc','fantasypros','usatoday'})
            self.assertFalse(report['rendered_verified'])
            for source in report['sources'].values():
                self.assertEqual(source['status'], 'warn')
                self.assertEqual(set(source['combos']), {'full_12','half_12'})
                for combo_report in source['combos'].values():
                    self.assertEqual(combo_report['samples'][1]['reindexed'],17.5)
                    self.assertIsNone(combo_report['samples'][1]['match'])
                    self.assertFalse(combo_report['rendered_verified'])


if __name__ == '__main__':
    unittest.main()
