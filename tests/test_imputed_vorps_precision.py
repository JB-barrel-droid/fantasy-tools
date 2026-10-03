"""JEG238: numerical conservation/ratios, without rounding producer fields."""
import json
import math
import tempfile
import unittest
from pathlib import Path
from pipelines.build_imputed_vorps import GROUPS, compute_imputed_vorps, infer_roster, main


def targets(amount=20):
    g = {x: 0 for x in GROUPS}; g['RB', 'starter'] = amount
    return g


class ImputationPrecisionTests(unittest.TestCase):
    def test_equal_thirds_conserve_and_emitted_factor_reproduces_values(self):
        rows = {'2227': ('RB', 1), '2821': ('RB', 1), '1307': ('RB', 1)}
        out = compute_imputed_vorps(rows, targets())
        self.assertTrue(math.isclose(math.fsum(r['imputed_vorp'] for r in out.values()), 20, abs_tol=1e-12))
        for rec in out.values():
            self.assertEqual(rec['alloc_factor'], 20/3)
            self.assertEqual(rec['imputed_vorp'], rec['native']*rec['alloc_factor'])

    def test_small_positive_and_ratios_ties_zero_preserved(self):
        rows = {'2227': ('RB', 1), '2821': ('RB', .0001), '1307': ('RB', 0)}
        out = compute_imputed_vorps(rows, targets(1))
        self.assertGreater(out['2821']['imputed_vorp'], 0)
        self.assertEqual(out['1307']['imputed_vorp'], 0)
        self.assertTrue(math.isclose(out['2227']['imputed_vorp']/out['2821']['imputed_vorp'], 10000, rel_tol=1e-12))
        self.assertTrue(math.isclose(math.fsum(r['imputed_vorp'] for r in out.values()), 1, abs_tol=1e-12))

    def test_all_eight_groups_conserve_unrounded_targets(self):
        # Arithmetic fixture keys are supplied identifiers; no canonical coverage verdict.
        rows = {}
        for pos, count in [('QB',20), ('RB',60), ('WR',80), ('TE',30)]:
            for i in range(count):
                rows[str(10000+len(rows))] = (pos, 100-i)
        roles = infer_roster(rows)
        self.assertEqual({(rows[k][0],r) for k,r in roles.items()}, set(GROUPS))
        g = {group: (j+1)/7 for j,group in enumerate(GROUPS)}
        out = compute_imputed_vorps(rows,g)
        for group in GROUPS:
            actual = math.fsum(out[k]['imputed_vorp'] for k,r in roles.items() if (rows[k][0],r)==group)
            self.assertTrue(math.isclose(actual,g[group],rel_tol=1e-12,abs_tol=1e-12),group)
        self.assertTrue(math.isclose(math.fsum(r['imputed_vorp'] for r in out.values()),math.fsum(g.values()),rel_tol=1e-12))

    def test_cli_json_roundtrip_keeps_full_precision(self):
        with tempfile.TemporaryDirectory() as tmp:
            vals, groups, out = (Path(tmp)/x for x in ['vals.json','groups.json','out.json'])
            vals.write_text(json.dumps({'2227':['RB',1], '2821':['RB',1], '1307':['RB',1]}))
            groups.write_text(json.dumps({'groups':[{'position':p,'role':r,'total_vorp':targets()[p,r]} for p,r in GROUPS]}))
            self.assertEqual(main(['--values',str(vals),'--group-vorps',str(groups),'--out',str(out)]),0)
            loaded=json.loads(out.read_text())
            self.assertEqual(loaded['2227']['alloc_factor'],20/3)
            self.assertTrue(math.isclose(math.fsum(r['imputed_vorp'] for r in loaded.values()),20,abs_tol=1e-12))


if __name__ == '__main__':
    unittest.main()
