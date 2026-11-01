"""Offline evidence and resolution guard for the Week 8 FantasyCalc alert."""
import json
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'pipelines'))
import check_source_divergence as sd
from pull_fantasycalc_12team import fantasycalc_url, to_rows

class FantasyCalcWeek8(unittest.TestCase):
    def test_alert_and_samples(self):
        e = json.loads((ROOT / 'tests/fixtures/JEG-1368/alert.json').read_text())
        self.assertEqual(e['section']['source_provenance']['week_designated'], 8)
        self.assertTrue(e['section']['fetched_at'].startswith('2026-10-29'))
        for scoring, rate in [('standard', .483), ('half', .465), ('full', .442)]:
            row = sd.divergence(e['values'][scoring], {})['fantasycalc']
            self.assertEqual(row['outlier_rate'], rate)
            leg = e['samples'][scoring]
            for r in leg['players'].values():
                self.assertAlmostEqual(r['native'] * leg['factor'], r['indexed'])
                self.assertEqual(round(r['indexed'], 1), r['display'])

    def test_scoring_and_column(self):
        for scoring, ppr in [('standard', '0'), ('half', '0.5'), ('full', '1')]:
            self.assertEqual(fantasycalc_url(scoring),
                'https://api.fantasycalc.com/values/current?isDynasty=false&numQbs=1&numTeams=12&ppr=' + ppr)
        self.assertEqual(to_rows([{'player': {'name': 'Example', 'position': 'TE'},
            'value': 123, 'redraftValue': 999, 'combinedValue': 888}])[0]['value'], 123)

    def test_display_engine_three_scorings(self):
        trace = json.loads(subprocess.check_output(['node', '--experimental-strip-types',
            str(ROOT / 'docs/research/JEG-1368/trace.cjs')], text=True))
        self.assertEqual(set(trace), {'standard', 'half_ppr', 'ppr'})
        for leg in trace.values():
            self.assertGreater(leg['factor'], 0)
            self.assertEqual(len(leg['players']), 5)
            for r in leg['players'].values():
                self.assertAlmostEqual(r['indexed'], r['native'] * leg['factor'])

    def test_resolution_applies_without_hiding_metric(self):
        report = sd.run()
        row = report['sources']['fantasycalc']
        self.assertEqual(row['week'], 8)
        self.assertEqual(row['status'], 'reviewed')
        self.assertEqual(row['computed_status'], 'investigate')
        self.assertEqual(row['resolution']['issue'], 'JEG-1368')

if __name__ == '__main__':
    unittest.main()
