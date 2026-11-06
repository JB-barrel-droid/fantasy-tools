"""Hermetic trip of the real perturbation assertion and its JSON transport."""
import contextlib
import io
import json
import unittest
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from tests import test_waiver_band_line as band
from validation_breach import emit, records_from_log, render
import record_post_rebuild_validation as recorder


class ValidationBreachTest(unittest.TestCase):
    def probe(self, delta=-1.0, hold=True):
        case = band.OnePlayerPerturbationTest('test_fringe_player_moves_no_one_more_than_tolerance')
        case.inp = SimpleNamespace(fixture={'week': 9}, players={
            1: {'name': 'Perturbed Player', 'pos': 'QB', 'rz_ppg': {'standard': 10.0}},
            2: {'name': 'Affected Player', 'pos': 'QB', 'rz_ppg': {'standard': 20.0}},
            3: {'name': 'Second Affected', 'pos': 'QB', 'rz_ppg': {'standard': 19.0}},
        })
        case._base_trace = {'waiver': 10.0, 'rates': [8.0]}
        def run(*args):
            case._last_trace = {'waiver': 10.0 + delta / 7, 'rates': [7.6]}
            return {1: 5.0, 2: 8.999999999, 3: 8.5}, []
        with patch.object(case, '_base', return_value=({1: 5.0, 2: 10.0, 3: 10.0}, [])), \
                patch.object(case, '_run', side_effect=run):
            result = case._worst('standard', 10, 'razzball', 'QB', 1, delta, hold)
        self.assertEqual(10.0, case.inp.players[1]['rz_ppg']['standard'])
        return case, result

    def test_real_assertion_trips_and_names_cause_and_players(self):
        case, result = self.probe()
        output = io.StringIO()
        with patch.object(case, '_cases', return_value=[('standard', 10, 'razzball', 'QB', 1)] * 20), \
                patch.object(case, '_map_worst', return_value=[result] * 40), \
                contextlib.redirect_stdout(output):
            with self.assertRaises(AssertionError):
                case.test_fringe_player_moves_no_one_more_than_tolerance()
        text = output.getvalue()
        for expected in ['Perturbed Player', 'Affected Player', 'Second Affected', 'mechanism=',
                         'bound=1.0 Adjusted points', 'observed=', 'causal_inputs=',
                         'runbooks/validation-failures.md#band-line']:
            self.assertIn(expected, text)
        records = records_from_log(text)
        self.assertEqual(40, len(records))
        self.assertEqual(2, len(records[0]['affected']))
        self.assertEqual(3, records[0]['argmax']['player_key'])
        self.assertEqual(result.record, records[0])
        self.assertTrue(Path(records[0]['runbook'].split('#')[0]).is_file())
        self.assertEqual(records, recorder.summarize(text)['breaches'])
        self.assertEqual('\n'.join(map(render, records)), recorder.summarize(text)['detail'])

    def test_rounding_boundary_and_exempt_record_are_lossless(self):
        _, result = self.probe()
        row = result.record['affected'][0]
        self.assertGreater(row['absolute'], 1.0)
        self.assertEqual('1.000', f"{row['absolute']:.3f}")
        result.record['status'] = 'exempt'
        stream = io.StringIO()
        emit(result.record, stream)
        self.assertEqual(result.record, records_from_log(stream.getvalue())[0])
        self.assertEqual((1.5, False), tuple(result))
        self.assertEqual('unclassified', result.record['mechanism']['name'])

    def test_free_allocation_mode_and_requested_delta_preserved(self):
        _, result = self.probe(delta=1.0, hold=False)
        self.assertEqual('allocations-free', result.record['setting']['mode'])
        self.assertEqual(11.0, result.record['perturbation']['after'])
        self.assertEqual({'waiver': 10.0, 'rates': [8.0]}, result.record['trace']['before'])
        self.assertAlmostEqual(10 + 1 / 7, result.record['trace']['after']['waiver'])

    def test_status_copies_and_artifact_keep_every_record(self):
        _, result = self.probe()
        out = io.StringIO()
        emit(result.record, out)
        emit(result.record, out)
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            block = recorder.record(repo, out.getvalue())
            self.assertEqual([result.record] * 2, json.loads(
                (repo / block['breach_artifact']).read_text()))
            for path in recorder.STATUS_PATHS:
                saved = json.loads((repo / path).read_text())
                self.assertEqual(block, saved['post_rebuild_validation'])
                self.assertFalse(saved['success'])

    def test_existing_exemption_still_continues_and_reports(self):
        case, result = self.probe()
        output = io.StringIO()
        signature = ('standard', 10, 'razzball', 'QB', 1, -1.0)
        with patch.object(case, '_cases', return_value=[signature[:5]] * 20), \
                patch.object(case, '_map_worst', return_value=[result] * 40), \
                patch.object(band, 'KNOWN_OVER_BAR_CASES', {signature, (*signature[:5], 1.0)}), \
                contextlib.redirect_stdout(output):
            case.test_fringe_player_moves_no_one_more_than_tolerance()
        self.assertEqual(40, len(records_from_log(output.getvalue())))
        self.assertTrue(all(r['status'] == 'exempt' for r in records_from_log(output.getvalue())))

    def test_malformed_transport_is_not_silently_discarded(self):
        with self.assertRaises(json.JSONDecodeError):
            records_from_log('VALIDATION_BREACH_JSON {broken')
