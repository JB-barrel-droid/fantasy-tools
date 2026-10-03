"""JEG237: actual arithmetic/CLI fail-closed regressions, discovered by unittest."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from pipelines.build_imputed_vorps import GROUPS, compute_imputed_vorps, infer_roster, main


def targets(amount=20):
    result = {g: 0.0 for g in GROUPS}
    result['RB', 'starter'] = amount
    return result


class ImputationValidationTests(unittest.TestCase):
    def test_valid_proportion_and_native_immutable(self):
        values = {'2227': ('RB', 60.0), '2821': ('RB', 40.0)}
        before = copy.deepcopy(values)
        result = compute_imputed_vorps(values, targets())
        self.assertEqual([r['imputed_vorp'] for r in result.values()], [12, 8])
        self.assertEqual(values, before)
        self.assertEqual(result['2227']['native'], 60)

    def test_positive_target_zero_or_empty_pool_rejects(self):
        for values in ({}, {'2227': ('RB', 0.0)}):
            with self.subTest(values=values), self.assertRaisesRegex(ValueError, 'infeasible'):
                compute_imputed_vorps(values, targets())

    def test_true_zero_target_and_native_is_zero(self):
        out = compute_imputed_vorps({'2227': ('RB', 0.0)}, targets(0))
        self.assertEqual(out['2227']['imputed_vorp'], 0)
        self.assertEqual(out['2227']['alloc_factor'], 0)

    def test_invalid_native_and_target_types_reject(self):
        for bad in (None, True, '1', -1, float('nan'), float('inf'), 10**1000):
            with self.subTest(bad=str(bad)[:30]):
                with self.assertRaises(ValueError):
                    compute_imputed_vorps({'2227': ('RB', bad)}, targets())
                with self.assertRaises(ValueError):
                    compute_imputed_vorps({'2227': ('RB', 1)}, targets(bad))

    def test_invalid_row_and_position_reject(self):
        for row in (None, ['RB'], ['RB', 1, 2], ['K', 1], ['RB', None]):
            with self.subTest(row=row), self.assertRaises(ValueError):
                infer_roster({'2227': row})

    def test_exact_group_target_keys_required(self):
        for groups in ({}, {('RB', 'starter'): 20}, {**targets(), ('RB', 'flex'): 1}):
            with self.assertRaises(ValueError):
                compute_imputed_vorps({'2227': ('RB', 1)}, groups)

    def test_aggregate_and_factor_overflow_reject(self):
        for values in ({'2227': ('RB', 1e308), '2821': ('RB', 1e308)},
                       {'2227': ('RB', 5e-324)}):
            with self.assertRaises(ValueError):
                compute_imputed_vorps(values, targets())

    def test_cli_rejects_bad_types_duplicates_without_overwriting(self):
        good_groups = [{'position': p, 'role': r, 'total_vorp': targets()[p, r]}
                       for p, r in GROUPS]
        cases = [('{"2227":["RB",true]}', good_groups),
                 ('{"2227":["RB",1],"2227":["RB",2]}', good_groups),
                 ('{"2227":["RB",1]}', good_groups + [good_groups[0]])]
        with tempfile.TemporaryDirectory() as tmp:
            values, groups, out = (Path(tmp)/x for x in ('values.json', 'groups.json', 'out.json'))
            for raw, rows in cases:
                values.write_text(raw); groups.write_text(json.dumps({'groups': rows}))
                out.write_text('sentinel')
                with self.assertRaises(ValueError):
                    main(['--values', str(values), '--group-vorps', str(groups), '--out', str(out)])
                self.assertEqual(out.read_text(), 'sentinel')


if __name__ == '__main__':
    unittest.main()
