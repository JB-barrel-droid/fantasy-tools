"""JEG243: pinned raw blend economics, with no legacy calibration fallback."""
import hashlib
import json
import math
import tempfile
import unittest
from pathlib import Path
from pipelines.reweight_reference import load_linear_blend_reference
from pipelines.build_reweighted_values import load_group_budgets, main
from pipelines.build_reweighted_values import SOURCE_KINDS

ROOT=Path(__file__).resolve().parents[1]
PINS={'espn':('ddf-20260930-espn-half_ppr-12t-0p15/ddf_leg.json','af508f01700ebf5ee791aa932360b8da2b83b26b39d537144e7c04aa22162021'),
      'cbsros':('ddf-20260930-cbsros-half_ppr-12t-0p15/ddf_leg_cbsros.json','afdf7a80a05655a1ba6f9845ba562dfd77b6e0846df79360b75c75b503ba6591'),
      'razzball':('ddf-20261001-razzball-half_ppr-12t-0p15/ddf_leg_razzball.json','a28babbf2a1d57fc26086ab69e1809b22f642f3c26c0ffb7142a50eb092856d0')}


def fixture(root):
    source={};cfg=None
    for s,(relative,digest) in PINS.items():
        legpath=ROOT/'data/ddf-two-tier'/relative;raw=legpath.read_bytes();leg=json.loads(raw)
        cfg={'schema':'granular-roster-config-v1','teams':leg['inputs']['teams'],'scoring':leg['inputs']['scoring'],**leg['reference_shape']}
        target=root/(s+'.json');target.write_bytes(raw)
        source[s]={'leg':target.name,'sha256':digest,'weight':{'espn':2,'cbsros':1,'razzball':1}[s],
                   'content_date':leg['inputs'][s+'_snapshot_date'],'horizon':'illustrative historical per-game comparison; review required'}
    doc={'schema':'linear-blend-reference-v1','method':'ppg-above-waiver-v1','units':'raw_surplus_ppg','configuration':cfg,
         'policy':{'status':'candidate','decision_url':None,'horizon':source['espn']['horizon']},'sources':source,'excluded_sources':{}}
    p=root/'reference.json';p.write_text(json.dumps(doc));return p,doc


class ReferenceContractTests(unittest.TestCase):
    def test_real_pins_independent_raw_weighted_arithmetic_and_legacy_discrimination(self):
        with tempfile.TemporaryDirectory() as t:
            p,doc=fixture(Path(t));budgets,meta=load_linear_blend_reference(p)
            self.assertEqual(meta['normalized_weights'],{'espn':.5,'cbsros':.25,'razzball':.25})
            expected={g:0 for g in budgets};legacy={g:0 for g in budgets}
            for source,e in doc['sources'].items():
                leg=json.loads((p.parent/e['leg']).read_text(encoding="utf-8"));weight=e['weight']/4
                for row in leg['values']:
                    g=row['pos'],row['tier']
                    if g in expected:expected[g]+=weight*max(0,row['ppg']-leg['calibration'][row['pos']]['rw'])
                for g in legacy:legacy[g]+=weight*leg['calibration'][g[0]][g[1]+'_raw']
            for g in budgets:self.assertTrue(math.isclose(budgets[g],expected[g],rel_tol=1e-12))
            self.assertFalse(math.isclose(budgets['QB','starter'],legacy['QB','starter'],rel_tol=1e-8))
            self.assertEqual(load_group_budgets(p),budgets)
            self.assertEqual(meta['policy']['status'],'candidate')

    def test_single_leg_single_source_units_config_horizon_and_hash_reject(self):
        for kind in ('single_leg','single_source','units','scoring','shape','date','horizon','hash','weight','review','missing'):
            with self.subTest(kind=kind),tempfile.TemporaryDirectory() as t:
                p,d=fixture(Path(t))
                if kind=='single_leg':p=Path(t)/'espn.json'
                else:
                    if kind=='single_source':d['sources']={'espn':d['sources']['espn']};d['excluded_sources']={'cbsros':'unavailable','razzball':'unavailable'}
                    elif kind=='units':d['units']='calibrated_0_70_value'
                    elif kind=='scoring':d['configuration']['scoring']='ppr'
                    elif kind=='shape':d['configuration']['bench_mix']['QB']=11
                    elif kind=='date':d['sources']['espn']['content_date']='2026-09-29'
                    elif kind=='horizon':d['sources']['espn']['horizon']='another horizon'
                    elif kind=='hash':d['sources']['espn']['sha256']='0'*64
                    elif kind=='weight':d['sources']['espn']['weight']=True
                    elif kind=='review':d['policy']['status']='reviewed'
                    elif kind=='missing':d.pop('policy')
                    p.write_text(json.dumps(d))
                with self.assertRaises(ValueError):load_group_budgets(p)

    def test_expected_batch_configuration_and_explicit_review_claim(self):
        with tempfile.TemporaryDirectory() as t:
            p,d=fixture(Path(t));expected={**d['configuration'],'scoring':'ppr'}
            with self.assertRaises(ValueError):load_linear_blend_reference(p,expected)
            d['policy'].update(status='reviewed',decision_url='https://linear.app/example/review-record')
            p.write_text(json.dumps(d));_,meta=load_linear_blend_reference(p)
            self.assertEqual(meta['policy'],d['policy'])  # declaration only, not authenticated approval

    def test_cli_reference_pins_defaults_and_failed_validation_preserves_output(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);p,d=fixture(root)
            cfg=d['configuration'];sources={}
            for source,e in d['sources'].items():
                leg=json.loads((root/e['leg']).read_text(encoding="utf-8"))
                pool={str(r['player_key']):{'group':r['pos']+'|'+r['tier'].title(),
                      'imputed_vorp':max(0,r['ppg']-leg['calibration'][r['pos']]['rw'])}
                      for r in leg['values'] if r['tier'] in ('starter','bench')}
                vp=root/(source+'.vorp.json');vp.write_text(json.dumps(pool))
                mp=root/(source+'.manifest.json');mp.write_text(json.dumps({'schema':'granular-vorp-manifest-v1',
                    'method':'ppg-above-waiver-v1','source_config':cfg,'output_sha256':hashlib.sha256(vp.read_bytes()).hexdigest()}))
                sources[source]={'values':vp.name,'manifest':mp.name}
            batch=root/'batch.json';batchcfg={**cfg,'schema':'option-c-publisher-roster-v1','bench_total':72};batchcfg.pop('bench_mix')
            batch.write_text(json.dumps({'schema':'vorp-source-batch-v1','configuration':batchcfg,'sources':sources,
                'excluded_sources':{s:'historical arithmetic fixture excludes publisher inputs' for s in SOURCE_KINDS if s not in sources}}))
            out=root/'out.json'
            self.assertEqual(main(['--batch',str(batch),'--reference',str(p),'--out',str(out)]),0)
            result=json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(result['manifest']['control_origin'],'linear_blend_reference')
            self.assertEqual(result['manifest']['reference']['reference_sha256'],hashlib.sha256(p.read_bytes()).hexdigest())
            self.assertEqual(result['manifest']['reference']['normalized_weights'],{'espn':.5,'cbsros':.25,'razzball':.25})
            self.assertEqual(result['artifact_status'],'candidate')
            out.write_text('sentinel');d['configuration']['scoring']='ppr';p.write_text(json.dumps(d))
            with self.assertRaises(ValueError):main(['--batch',str(batch),'--reference',str(p),'--out',str(out)])
            self.assertEqual(out.read_text(encoding="utf-8"),'sentinel')


if __name__=='__main__':unittest.main()
