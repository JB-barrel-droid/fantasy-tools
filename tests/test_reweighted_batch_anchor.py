"""JEG240: one all-source scale, explicit candidate manifests and no rounding."""
import hashlib
import json
import math
import tempfile
import unittest
from pathlib import Path
from pipelines.build_imputed_vorps import GROUPS,RosterConfig
from pipelines.build_reweighted_values import (SOURCE_KINDS,apply_70_anchor,
    build_batch_three_views,build_three_views,load_source_batch,main)


def budgets():
    d={g:0 for g in GROUPS};d['RB','starter']=20;return d


def records(a,b):
    return {'2227':{'group':'RB|Starter','imputed_vorp':a,'native':a},
            '2821':{'group':'RB|Starter','imputed_vorp':b,'native':b}}


def pair():
    pools={'fantasycalc':records(10,10),'usat':records(18,2)}
    natives={s:{k:r['native'] for k,r in p.items()} for s,p in pools.items()}
    return pools,natives


class SharedAnchorTests(unittest.TestCase):
    def test_one_batch_anchor_preserves_equal_totals_and_group_budget(self):
        result=build_batch_three_views(*pair(),budgets())
        a=result['sources']['fantasycalc']['adj_values'];b=result['sources']['usat']['adj_values']
        self.assertTrue(math.isclose(a['2227'],70*10/18,rel_tol=1e-12))
        self.assertTrue(math.isclose(b['2227'],70,rel_tol=1e-12))
        self.assertTrue(math.isclose(b['2821'],70*2/18,rel_tol=1e-12))
        self.assertEqual(a['2227'],a['2821'])
        self.assertNotEqual(b['2821'],7.8)
        for values in (a,b):
            self.assertTrue(math.isclose(math.fsum(values.values()),result['total_budget_per_source'],rel_tol=1e-12))
            self.assertTrue(math.isclose(math.fsum(values.values()),result['group_budgets']['RB/starter'],rel_tol=1e-12))
        self.assertLess(max(a.values()),70)

    def test_budget_units_and_source_vorp_unit_changes_cancel(self):
        pools,native=pair();before=build_batch_three_views(pools,native,budgets())
        changed={s:{k:{**r,'imputed_vorp':r['imputed_vorp']*16} for k,r in p.items()} for s,p in pools.items()}
        after=build_batch_three_views(changed,native,{g:b*3 for g,b in budgets().items()})
        self.assertEqual(before['sources'],{s:{**out,'vorp':before['sources'][s]['vorp']} for s,out in after['sources'].items()})

    def test_explicit_common_peak_required_and_stale_peak_rejected(self):
        with self.assertRaises(TypeError):apply_70_anchor({'1':10})
        with self.assertRaises(ValueError):apply_70_anchor({'1':10},batch_maximum=9)
        with self.assertRaises(ValueError):apply_70_anchor({'1':0},batch_maximum=0)
        self.assertEqual(apply_70_anchor({'1':0},batch_maximum=10),{'1':0})
        with self.assertRaises(TypeError):build_three_views(records(10,10),{'2227':10,'2821':10},budgets())

    def test_missing_invalid_or_unfunded_batches_reject(self):
        pools,native=pair()
        with self.assertRaises(ValueError):build_batch_three_views({}, {}, budgets())
        with self.assertRaises(ValueError):build_batch_three_views(pools,{},budgets())
        with self.assertRaises(ValueError):build_batch_three_views(pools,native,{})
        with self.assertRaises(ValueError):build_batch_three_views(pools,native,{g:0 for g in GROUPS})
        for bad in (None,True,'1',-1,float('nan'),float('inf')):
            changed={**pools,'usat':records(bad,0)}
            with self.subTest(bad=bad),self.assertRaises(ValueError):build_batch_three_views(changed,native,budgets())
        with self.assertRaises(ValueError):build_batch_three_views({**pools,'usat':records(0,0)},native,budgets())

    def test_existing_player_clamp_is_rejected_before_batch_output(self):
        p={str(i):{'group':'QB|'+('Starter' if i<3 else 'Bench'),'imputed_vorp':u,'native':u}
           for i,u in ((1,1),(2,10),(3,1),(4,2))}
        g={x:0 for x in GROUPS};g['QB','starter']=20;g['QB','bench']=10
        with self.assertRaisesRegex(ValueError,'conserving budget'):
            build_batch_three_views({'test':p},{'test':{k:r['native'] for k,r in p.items()}},g)

    def fixture(self,tmp,with_granular=False):
        root=Path(tmp);cfg=RosterConfig(1,{'QB':0,'RB':2,'WR':0,'TE':0},0,0,'half_ppr').manifest()
        sources={};pools,_=pair()
        if with_granular:pools['espn']=records(8,12)
        for source,pool in pools.items():
            values=root/(source+'.json');values.write_text(json.dumps(pool,sort_keys=True,indent=2))
            gran=SOURCE_KINDS[source]=='granular'
            meta={'schema':'granular-vorp-manifest-v1' if gran else 'option-c-imputation-manifest-v1',
                  'method':'ppg-above-waiver-v1' if gran else 'eight-group-proportional-v1',
                  'source_config' if gran else 'publisher_roster':({**{k:v for k,v in cfg.items() if k!='bench_total'},'schema':'granular-roster-config-v1','bench_mix':{p:0 for p in ('QB','RB','WR','TE')}} if gran else cfg),
                  'output_sha256':hashlib.sha256(values.read_bytes()).hexdigest()}
            mp=root/(source+'.manifest.json');mp.write_text(json.dumps(meta))
            sources[source]={'values':values.name,'manifest':mp.name}
        batch=root/'batch.json';doc={'schema':'vorp-source-batch-v1','configuration':cfg,'sources':sources,
                                   'excluded_sources':{s:'unavailable arithmetic fixture' for s in SOURCE_KINDS if s not in sources}}
        batch.write_text(json.dumps(doc));controls=root/'controls.json'
        controls.write_text(json.dumps({f'{p}/{r}':v for (p,r),v in budgets().items()}))
        return batch,controls,root/'out.json'

    def test_cli_mixed_batch_pins_sources_exclusions_and_shared_scale(self):
        with tempfile.TemporaryDirectory() as tmp:
            batch,controls,out=self.fixture(tmp,with_granular=True)
            self.assertEqual(main(['--batch',str(batch),'--controls',str(controls),'--out',str(out)]),0)
            result=json.loads(out.read_text())
            self.assertEqual(set(result['sources']),{'fantasycalc','usat','espn'})
            self.assertEqual(result['sources']['espn']['indexed'],{})
            self.assertEqual(len(result['manifest']['excluded_sources']),4)
            self.assertEqual(result['manifest']['batch_sha256'],hashlib.sha256(batch.read_bytes()).hexdigest())
            self.assertLess(max(result['sources']['fantasycalc']['adj_values'].values()),70)
            self.assertEqual(max(result['sources']['usat']['adj_values'].values()),70)

    def test_hash_config_and_undeclared_source_rejections_keep_output(self):
        for kind in ('hash','config','typed_config','exclusion'):
            with self.subTest(kind=kind),tempfile.TemporaryDirectory() as tmp:
                batch,controls,out=self.fixture(tmp,with_granular=True);out.write_text('sentinel')
                doc=json.loads(batch.read_text())
                if kind=='hash':(Path(tmp)/'usat.json').write_text('{}')
                elif kind in ('config','typed_config'):
                    p=Path(tmp)/'espn.manifest.json';m=json.loads(p.read_text())
                    if kind=='config':m['source_config']['scoring']='ppr'
                    else:m['source_config']['teams']=1.0
                    p.write_text(json.dumps(m))
                else:doc['excluded_sources'].pop('cbs');batch.write_text(json.dumps(doc))
                with self.assertRaises(ValueError):main(['--batch',str(batch),'--controls',str(controls),'--out',str(out)])
                self.assertEqual(out.read_text(),'sentinel')


if __name__=='__main__':unittest.main()
