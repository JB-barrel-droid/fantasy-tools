"""Explicit candidate/reviewed linear blend reference; never legacy calibration."""
import hashlib
import json
import math
from datetime import date
from pathlib import Path

if __package__:
    from .build_imputed_vorps import RosterConfig, GROUPS, _canonical_number, _finite_sum, _nonnegative_finite, _unique_object
else:
    from build_imputed_vorps import RosterConfig, GROUPS, _canonical_number, _finite_sum, _nonnegative_finite, _unique_object

SOURCES = {'espn', 'cbsros', 'razzball'}
UNIT = 'raw_surplus_ppg'
METHOD = 'ppg-above-waiver-v1'


def _configuration(raw):
    fields = {'schema','teams','scoring','slots','flex_count','flex_eligible','bench_mix'}
    if (not isinstance(raw,dict) or set(raw)!=fields or raw['schema']!='granular-roster-config-v1'
        or not isinstance(raw['bench_mix'],dict) or set(raw['bench_mix'])!={'QB','RB','WR','TE'}
        or any(type(v) is not int or v<0 for v in raw['bench_mix'].values())):
        raise ValueError('explicit granular reference configuration required')
    RosterConfig(raw['teams'],raw['slots'],raw['flex_count'],sum(raw['bench_mix'].values()),raw['scoring'],raw['flex_eligible'])
    return raw


def load_linear_blend_reference(path, expected_configuration=None):
    """Return recomputed raw budgets and provenance; policy claims are not authentication."""
    path=Path(path);raw_bytes=path.read_bytes()
    doc=json.loads(raw_bytes,object_pairs_hook=_unique_object)
    fields={'schema','method','units','configuration','policy','sources','excluded_sources'}
    if not isinstance(doc,dict) or set(doc)!=fields or doc['schema']!='linear-blend-reference-v1' or doc['method']!=METHOD or doc['units']!=UNIT:
        raise ValueError('versioned raw linear blend reference required')
    cfg=_configuration(doc['configuration'])
    if expected_configuration is not None:
        for k in ('teams','scoring','slots','flex_count','flex_eligible'):
            if cfg[k]!=expected_configuration.get(k):raise ValueError('reference/batch configuration mismatch')
    policy=doc['policy']
    if (not isinstance(policy,dict) or set(policy)!={'status','decision_url','horizon'}
        or policy['status'] not in ('candidate','reviewed') or not isinstance(policy['horizon'],str) or not policy['horizon'].strip()
        or (policy['status']=='reviewed' and (not isinstance(policy['decision_url'],str) or not policy['decision_url'].startswith('https://')))
        or (policy['status']=='candidate' and policy['decision_url'] is not None)):
        raise ValueError('explicit weighting/horizon policy and review evidence required')
    sources,excluded=doc['sources'],doc['excluded_sources']
    if (not isinstance(sources,dict) or len(sources)<2 or not isinstance(excluded,dict)
        or set(sources)&set(excluded) or set(sources)|set(excluded)!=SOURCES
        or any(not isinstance(v,str) or not v.strip() for v in excluded.values())):
        raise ValueError('blend requires at least two sources and explicit exclusions')
    weights={};source_totals={};pins={}
    for source,entry in sources.items():
        if not isinstance(entry,dict) or set(entry)!={'leg','sha256','weight','content_date','horizon'} or not isinstance(entry['leg'],str):
            raise ValueError('complete pinned reference source required')
        weights[source]=_nonnegative_finite(entry['weight'],'reference weight')
        if weights[source]==0:raise ValueError('included reference weight must be positive; exclude explicitly')
        if not isinstance(entry['content_date'],str) or date.fromisoformat(entry['content_date']).isoformat()!=entry['content_date']:
            raise ValueError('ISO content date required')
        if entry['horizon']!=policy['horizon']:raise ValueError('reference source horizon mismatch')
        leg_bytes=(path.parent/entry['leg']).read_bytes();digest=hashlib.sha256(leg_bytes).hexdigest()
        if digest!=entry['sha256']:raise ValueError('reference source hash mismatch')
        leg=json.loads(leg_bytes,object_pairs_hook=_unique_object)
        if not isinstance(leg,dict) or leg.get('schema')!='trade-value-ddf-leg-v1':raise ValueError('raw DDF leg required')
        inputs=leg.get('inputs');shape=leg.get('reference_shape')
        if (not isinstance(inputs,dict) or not isinstance(shape,dict)
            or any(inputs.get(k)!=cfg[k] for k in ('teams','scoring'))
            or any(shape.get(k)!=cfg[k] for k in ('slots','flex_count','flex_eligible','bench_mix'))):
            raise ValueError('reference leg configuration mismatch')
        if inputs.get(source+'_snapshot_date')!=entry['content_date']:
            raise ValueError('reference leg content date mismatch')
        if inputs.get('source_tag', 'espn')!=source:raise ValueError('reference source identity mismatch')
        values=leg.get('values');cal=leg.get('calibration')
        if not isinstance(values,list) or not values or not isinstance(cal,dict):raise ValueError('raw rows/waiver thresholds required')
        waiver={p:_nonnegative_finite(cal.get(p,{}).get('rw'),f'waiver {p}') for p in ('QB','RB','WR','TE')}
        pools={g:[] for g in GROUPS};seen=set()
        for row in values:
            if not isinstance(row,dict):raise ValueError('malformed raw row')
            number=_canonical_number(row.get('player_key'))
            if number in seen:raise ValueError('duplicate reference identity')
            seen.add(number);pos=row.get('pos');tier=row.get('tier')
            if pos not in waiver or tier not in ('starter','bench','waiver'):raise ValueError('unknown reference role/position')
            ppg=_nonnegative_finite(row.get('ppg'),'reference PPG')
            if tier!='waiver':pools[pos,tier].append(max(0,ppg-waiver[pos]))
        if any(not pool for pool in pools.values()):raise ValueError('missing raw reference group')
        source_totals[source]={g:_finite_sum(pool,'reference raw group') for g,pool in pools.items()}
        pins[source]={**entry,'sha256':digest,'raw_group_totals':{f'{p}/{r}':v for (p,r),v in source_totals[source].items()}}
    total_weight=_finite_sum(weights.values(),'reference weights')
    fractions={s:w/total_weight for s,w in weights.items()}
    if any(v==0 for v in fractions.values()):raise ValueError('reference weight underflow')
    budgets={g:_finite_sum((fractions[s]*source_totals[s][g] for s in sources),'blend raw group') for g in GROUPS}
    if _finite_sum(budgets.values(),'blend raw total')==0:raise ValueError('positive raw blend budget required')
    return budgets,{'schema':doc['schema'],'method':METHOD,'units':UNIT,'configuration':cfg,'policy':policy,
                    'reference_sha256':hashlib.sha256(raw_bytes).hexdigest(),'sources':pins,'normalized_weights':fractions,
                    'excluded_sources':excluded,'raw_group_budgets':{f'{p}/{r}':v for (p,r),v in budgets.items()}}
