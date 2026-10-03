"""JEG241: closed-form visible cross-role constraints preserve budget and ratios."""
import hashlib
import json
import math
import unittest
from pathlib import Path
from pipelines.build_imputed_vorps import GROUPS
from pipelines.build_reweighted_values import (build_batch_three_views,
    constrain_group_budgets,iron_within_position_inversions,linear_reweight)


def rows(starters=(1,10),bench=(1,2),pos='QB'):
    return {str(i+1):{'group':pos+'|'+('Starter' if i<len(starters) else 'Bench'),
                     'imputed_vorp':u,'native':u} for i,u in enumerate(starters+bench)}


def budget(pos='QB'):
    g={x:0 for x in GROUPS};g[pos,'starter']=20;g[pos,'bench']=10;return g


def native(pools):return {s:{k:r['native'] for k,r in p.items()} for s,p in pools.items()}


class ConservingInversionTests(unittest.TestCase):
    def test_hand_calculated_cap_preserves_position_and_source_totals(self):
        p={'A':rows()};effective,caps=constrain_group_budgets(p,budget())
        self.assertTrue(math.isclose(caps['QB']['maximum_bench_fraction'],3/25,rel_tol=1e-12))
        self.assertTrue(math.isclose(effective['QB','starter'],26.4,rel_tol=1e-12))
        self.assertTrue(math.isclose(effective['QB','bench'],3.6,rel_tol=1e-12))
        self.assertTrue(math.isclose(sum(effective.values()),30,rel_tol=1e-12))
        result=build_batch_three_views(p,native(p),budget());v=result['sources']['A']['adj_values']
        for k,expected in [('1',7),('2',70),('3',3.5),('4',7)]:self.assertTrue(math.isclose(v[k],expected,rel_tol=1e-12))
        self.assertTrue(math.isclose(sum(v.values()),87.5,rel_tol=1e-12))
        self.assertTrue(math.isclose(v['3']/v['4'],.5,rel_tol=1e-12))
        self.assertNotEqual(result['requested_allocation_fractions'],result['allocation_fractions'])

    def test_tightest_source_cap_shared_by_every_source(self):
        p={'A':rows(),'B':rows((2,9),(4,5))};result=build_batch_three_views(p,native(p),budget())
        self.assertEqual(result['control_constraints']['QB']['limiting_sources'],['A'])
        for s,out in result['sources'].items():
            v=out['adj_values']
            self.assertGreaterEqual(min(v[k] for k in ('1','2'))+1e-12,max(v[k] for k in ('3','4')))
            self.assertTrue(math.isclose(v['1']+v['2'],result['group_budgets']['QB/starter'],rel_tol=1e-12))
            self.assertTrue(math.isclose(v['3']+v['4'],result['group_budgets']['QB/bench'],rel_tol=1e-12))
            self.assertTrue(math.isclose(sum(v.values()),result['total_budget_per_source'],rel_tol=1e-12))

    def test_feasible_budget_and_cross_position_inversion_unchanged(self):
        p={'A':rows()};g=budget();g['QB','starter']=29;g['QB','bench']=1
        effective,caps=constrain_group_budgets(p,g)
        for group in GROUPS:self.assertTrue(math.isclose(effective[group],g[group],abs_tol=1e-12))
        self.assertFalse(caps['QB']['constrained'])
        p={'A':{'1':{'group':'RB|Bench','imputed_vorp':1,'native':8},
                '2':{'group':'TE|Starter','imputed_vorp':1,'native':2}}}
        g={x:0 for x in GROUPS};g['RB','bench']=8;g['TE','starter']=2
        out=build_batch_three_views(p,native(p),g)['sources']['A']['adj_values']
        self.assertEqual(out,{'1':70,'2':17.5})

    def test_zero_boundary_and_infeasible_all_zero_starters(self):
        p={'A':rows((0,2),(1,))};r=build_batch_three_views(p,native(p),budget())
        self.assertEqual(r['control_constraints']['QB']['effective_bench_fraction'],0)
        self.assertEqual(r['sources']['A']['adj_values'],{'1':0,'2':70,'3':0})
        p={'A':rows((0,),(1,))};g=budget();g['QB','starter']=0
        with self.assertRaisesRegex(ValueError,'starter budget'):
            build_batch_three_views(p,native(p),g)

    def test_diagnostic_never_clips_and_stale_budget_adapter_rejects(self):
        p=rows();v=linear_reweight(p,budget())
        with self.assertRaises(ValueError):iron_within_position_inversions(v,p)
        effective,_=constrain_group_budgets({'A':p},budget());v=linear_reweight(p,effective)
        self.assertEqual(iron_within_position_inversions(v,p),v)

    def test_real_pinned_three_source_example_conserves_and_orders(self):
        base=Path(__file__).resolve().parents[1]/'data/ddf-two-tier'
        pins={'ESPN':('ddf-20260930-espn-half_ppr-12t-0p15/ddf_leg.json','af508f01700ebf5ee791aa932360b8da2b83b26b39d537144e7c04aa22162021'),
              'CBS ROS':('ddf-20260930-cbsros-half_ppr-12t-0p15/ddf_leg_cbsros.json','afdf7a80a05655a1ba6f9845ba562dfd77b6e0846df79360b75c75b503ba6591'),
              'Razzball':('ddf-20261001-razzball-half_ppr-12t-0p15/ddf_leg_razzball.json','a28babbf2a1d57fc26086ab69e1809b22f642f3c26c0ffb7142a50eb092856d0')}
        pools={};totals={g:0 for g in GROUPS}
        for source,(path,pin) in pins.items():
            raw=(base/path).read_bytes();self.assertEqual(hashlib.sha256(raw).hexdigest(),pin);d=json.loads(raw);pools[source]={}
            for row in d['values']:
                if row['tier'] not in ('starter','bench'):continue
                u=max(0,row['ppg']-d['calibration'][row['pos']]['rw'])
                pools[source][str(row['player_key'])]={'group':row['pos']+'|'+row['tier'].title(),'imputed_vorp':u}
                totals[row['pos'],row['tier']]+=u/3  # illustrative equal-weight arithmetic fixture
        result=build_batch_three_views(pools,{s:{} for s in pools},totals)
        self.assertTrue(math.isclose(result['total_budget_per_source'],2387.4243126568526,rel_tol=1e-12))
        for source,output in result['sources'].items():
            out=output['adj_values']
            for g in GROUPS:
                values=[out[k] for k,r in pools[source].items() if r['group']==g[0]+'|'+g[1].title()]
                self.assertTrue(math.isclose(math.fsum(values),result['group_budgets']['/'.join(g)],rel_tol=1e-12))
            for pos in ('QB','RB','WR','TE'):
                starter=[out[k] for k,r in pools[source].items() if r['group']==pos+'|Starter']
                bench=[out[k] for k,r in pools[source].items() if r['group']==pos+'|Bench']
                self.assertGreaterEqual(min(starter)+1e-10,max(bench))


if __name__=='__main__':unittest.main()
