"""JEG239: explicit roster/config, deterministic role ties and Cut0 contract."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from pipelines.build_imputed_vorps import (DEFAULT_ROSTER, DEDICATED, GROUPS,
    RosterConfig, compute_imputed_vorps, infer_roster, main)
from pipelines.build_reweighted_values import build_three_views


def pool():
    rows = {}
    for j,(pos,n) in enumerate([('QB',40),('RB',100),('WR',130),('TE',70)]):
        for i in range(n):
            rows[str(1000+j*1000+i)] = (pos,1000-i)
    return rows


class RosterConfigTests(unittest.TestCase):
    def test_team_matrix_and_custom_shape_have_exact_roles(self):
        for teams in (8,10,12,14):
            cfg=RosterConfig(teams,DEDICATED,1,teams*6,'half_ppr')
            roles=infer_roster(pool(),cfg,require_complete=True)
            self.assertEqual(list(roles.values()).count('starter'),teams*8)
            self.assertEqual(list(roles.values()).count('bench'),teams*6)
        cfg=RosterConfig(8,{'QB':2,'RB':1,'WR':2,'TE':0},2,5,'ppr',('RB','WR'))
        roles=infer_roster(pool(),cfg,require_complete=True)
        self.assertEqual(list(roles.values()).count('starter'),56)
        self.assertEqual(list(roles.values()).count('bench'),5)
        rows=pool()
        self.assertTrue(all(rows[k][0] in ('RB','WR') for k,r in roles.items()
                            if r=='starter' and rows[k][0]!='QB'))

    def test_ties_use_numeric_keys_and_are_input_order_independent(self):
        cfg=RosterConfig(1,{'QB':1,'RB':0,'WR':0,'TE':0},0,1,'standard')
        values={'100':('QB',1),'10':('QB',1),'2':('QB',1)}
        roles=infer_roster(values,cfg,require_complete=True)
        self.assertEqual(roles,{'2':'starter','10':'bench','100':'cut'})
        self.assertEqual(roles,infer_roster(dict(reversed(list(values.items()))),cfg,require_complete=True))

    def test_invalid_config_and_missing_complete_pool_reject(self):
        for fields in [(0,DEDICATED,1,72,'half_ppr'),(12,DEDICATED,True,72,'half_ppr'),
                       (12,{'QB':1},1,72,'half_ppr'),(12,DEDICATED,1,-1,'half_ppr')]:
            with self.assertRaises(ValueError): RosterConfig(*fields)
        for rows in ({},{'869':('QB',1)}):
            with self.assertRaisesRegex(ValueError,'incomplete'):
                infer_roster(rows,DEFAULT_ROSTER,require_complete=True)
        cfg=RosterConfig(1,{'QB':0,'RB':0,'WR':0,'TE':0},1,0,'ppr')
        with self.assertRaisesRegex(ValueError,'flex'):
            infer_roster({'869':('QB',1)},cfg,require_complete=True)
        cfg=RosterConfig(1,{'QB':0,'RB':0,'WR':0,'TE':0},0,2,'ppr')
        with self.assertRaisesRegex(ValueError,'bench'):
            infer_roster({'869':('QB',1)},cfg,require_complete=True)

    def test_key_alias_and_unresolved_key_format_reject(self):
        for rows in ({'869':('QB',1),869:('QB',1)}, {'p1':('QB',1)}, {'0869':('QB',1)}, {True:('QB',1)}):
            with self.assertRaises(ValueError): infer_roster(rows)

    def test_cut_is_explicit_zero_and_reweight_keeps_native(self):
        cfg=RosterConfig(1,{'QB':1,'RB':0,'WR':0,'TE':0},0,0,'standard')
        values={'869':('QB',2),'100':('QB',1)}
        g={x:0 for x in GROUPS};g['QB','starter']=20
        out=compute_imputed_vorps(values,g,cfg,require_complete=True)
        self.assertEqual(out['100'],{'group':'QB|Cut','alloc_factor':0,'imputed_vorp':0,'native':1})
        views=build_three_views(out,{k:r[1] for k,r in values.items()},g)
        self.assertEqual(views['vorp']['100'],0)
        self.assertEqual(views['adj_values']['100'],0)
        self.assertEqual(views['indexed']['100'],1)
        bad={**out,'100':{**out['100'],'imputed_vorp':1}}
        with self.assertRaises(ValueError): build_three_views(bad,{'100':1,'869':2},g)

    def test_cli_matching_manifest_and_separate_bench_counts(self):
        cfg=RosterConfig(12,DEDICATED,1,72,'half_ppr')
        shape=cfg.manifest()
        target_roster={'slots':dict(DEDICATED),'flex_count':1,'flex_eligible':['RB','WR','TE'],
                       'bench_mix':{'QB':10,'RB':27,'WR':33,'TE':10}}
        g={x:0 for x in GROUPS}  # arithmetic/count oracle, not canonical coverage approval
        with tempfile.TemporaryDirectory() as tmp:
            vals,groups,config,out=(Path(tmp)/x for x in ['v.json','g.json','c.json','out.json'])
            vals.write_text(json.dumps(pool())); config.write_text(json.dumps(shape))
            group_doc={'teams':12,'scoring':'half_ppr','roster':target_roster,
                       'groups':[{'position':p,'role':r,'total_vorp':g[p,r]} for p,r in GROUPS]}
            groups.write_text(json.dumps(group_doc))
            args=['--values',str(vals),'--group-vorps',str(groups),'--roster-config',str(config),'--out',str(out)]
            self.assertEqual(main(args),0)
            manifest=json.loads(out.with_suffix('.json.manifest.json').read_text())
            self.assertEqual(manifest['publisher_roster']['bench_total'],72)
            self.assertEqual(manifest['target_bench_total'],80)
            self.assertEqual(manifest['role_counts'],{'starter':96,'bench':72,'cut':172})
            self.assertEqual(manifest['output_sha256'],hashlib.sha256(out.read_bytes()).hexdigest())
            for changed in ('teams','scoring','slots','flex_count'):
                doc=json.loads(json.dumps(group_doc))
                if changed=='teams': doc['teams']=8
                elif changed=='scoring': doc['scoring']='standard'
                elif changed=='slots': doc['roster']['slots']['QB']=2
                else: doc['roster']['flex_count']=0
                groups.write_text(json.dumps(doc)); before=out.read_bytes()
                with self.assertRaises(ValueError):main(args)
                self.assertEqual(out.read_bytes(),before)


if __name__=='__main__':unittest.main()
