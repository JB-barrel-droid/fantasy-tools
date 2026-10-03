"""Pinned approved Sheet imputation arithmetic; no canonical/production certification."""
import hashlib
import json
import math
import unittest
from pathlib import Path
from pipelines.build_imputed_vorps import compute_imputed_vorps,RosterConfig

class SheetOracleTests(unittest.TestCase):
    def test_all_195_roles_groups_and_full_precision_imputation_match(self):
        root=Path(__file__).resolve().parents[1]
        path=root/'docs/audits/jeg-242-sheet-values.json'
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),'ee21497ce441ccde935a464fa03980b7657ab0b68818c2b9f3f625a9788357e0')
        capt=json.loads(path.read_text());sheets={s['sheet']:s['data']['values'] for s in capt['sheets']}
        raw=sheets['IN_FC'][1:];calc={r[2]:r for r in sheets['CALC_Main'][1:]};v={str(i+1):(r[0],r[3]) for i,r in enumerate(raw)}
        g={('QB','starter'):148.84,('QB','bench'):26.27,('RB','starter'):995.91,('RB','bench'):175.75,('WR','starter'):975.04,('WR','bench'):172.07,('TE','starter'):145.73,('TE','bench'):23.38}
        out=compute_imputed_vorps(v,g,RosterConfig(12,{'QB':1,'RB':2,'WR':3,'TE':1},1,72,'half_ppr'),require_complete=True)
        mismatches=[]
        for i,r in enumerate(raw):
         got=out[str(i+1)];ref=calc[r[2]]
         if got['group']!=ref[5] or not math.isclose(got['imputed_vorp'],ref[8],rel_tol=1e-12,abs_tol=1e-12):mismatches.append({'name':r[2],'actual_group':got['group'],'sheet_group':ref[5],'actual_u':got['imputed_vorp'],'sheet_u':ref[8]})
        self.assertEqual(len(raw),195)
        self.assertEqual(mismatches,[])

if __name__=="__main__":unittest.main()
