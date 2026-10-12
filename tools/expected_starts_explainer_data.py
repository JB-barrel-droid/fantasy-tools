#!/usr/bin/env python3
"""Data for the "Points That Reach a Lineup" explainer (JEG-521 / JEG-525).

Writes the JSON that docs/claude-log/2026-10-09-jeg521-points-that-reach-a-lineup.html
embeds as `const D = {...}` (ESPN lists per position at 12-team full PPR,
parameters from output/lineup-parameters.json, bench share by content week,
weekly noise, hazard). Run pipelines/derive_lineup_parameters.py first, then
this, then splice the JSON into the page and republish it to
https://claude.ai/artifact/WL2hJUxWWStAvj2Co2FdeW (read it first in a new
session, then publish with url=...). Usage: python3 tools/expected_starts_explainer_data.py OUT.json
"""
import sys, json, math; sys.path.insert(0,'pipelines'); sys.path.insert(0,'.')
import expected_starts_model as es, value_reference as ref, derive_lineup_parameters as dl
inp=ref.Inputs.load(ref.FIXTURE, ref.PLAYERS); params=es.load_params()
sources,pos_of=es.load_sources(inp,'ppr',12); cs=es.chart_sigma_from(sources,12)
names={k:p['name'] for k,p in inp.players.items()}
espn=[s for s in sources if s.key=='espn'][0]
run=es.run_setting(sources,12,params,cs,'A')
out={'params':params,'positions':{}}
for pos in es.POSITIONS:
    c=run['per_source']['espn'][pos]['counts']; e=run['per_source']['espn'][pos]['es']
    keys=espn.keys(pos)
    out['positions'][pos]={'counts':c,'players':[{'name':names[k],'x':round(p['x'],3)} for k,p in zip(keys,e['players'])][:c['rostered']+8]}
byes=json.load(open('data/inputs/nfl_byes_2026.json'))['byes']
lp=json.load(open('output/lineup-parameters.json'))
prog=[]
for cw in range(5,18):
    b=dl.bye_share(byes, cw+1, 18)['share']; horizon=(18-(cw+1)+1)/2
    prm={'bye':b}
    for p in es.POSITIONS:
        now=lp['recommended'][p]['sigma_rel_now']; wk=lp['week_to_week_summary'][p]['weekly_rel_sd']
        prm[p]={'m':params[p]['m'],'sigma_rel':math.sqrt(now**2+(wk*math.sqrt(horizon))**2),'sigma_floor':params[p]['sigma_floor']}
    r=es.run_setting(sources,12,prm,cs,'A')
    tiers=es.tiers_on_mean(sources,12); ddf=es.ddf_mean(r['adjusted'],sorted(tiers)); met=es.shares_and_ratio(ddf,tiers,12)
    fill=sum(v for g,v in r['weights'].items() if g.endswith('|bench'))
    prog.append({'content_week':cw,'weeks_left':18-cw,'bye_share':round(b,4),'sigma_rb':round(prm['RB']['sigma_rel'],3),'fill_state_share':round(fill,4),'bench_tier_share':round(met['bench_tier_share_overall'],4),'rb_price':round(met['starter_to_bench_price']['RB'],2)})
out['progression']=prog
out['weekly_noise']={p:lp['weekly_noise'][p] for p in es.POSITIONS}
out['cross_source']={p:{'sigma_rel':lp['recommended'][p]['sigma_rel_now'],'drift_weekly':lp['week_to_week_summary'][p]['weekly_rel_sd']} for p in es.POSITIONS}
src=lp['missed_games_history'] or lp['missed_games']
out['missed']={p:src['pooled'][p] for p in es.POSITIONS}
out['m_source']=lp['recommended']['QB']['m_source']
json.dump(out, open(sys.argv[1], "w"), indent=0)
print({p:(round(params[p]['m'],3)) for p in es.POSITIONS}, prog[0], prog[-1])
