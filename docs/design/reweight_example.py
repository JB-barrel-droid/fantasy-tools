"""JEG-209 design arithmetic only. Never imported by the production pipeline."""
import hashlib
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INPUT = ROOT / 'data/ddf-two-tier/ddf-20260929-espn-half_ppr-12t-0p15/ddf_leg.json'
PIN = 'd29beb2e3481e4fa1ecd71b194e11428a9a64d0900fe9c0636f933517865b98d'
GROUPS = [(p, r) for p in ('QB', 'RB', 'WR', 'TE') for r in ('starter', 'bench')]


def allocate(reference, sources):
    """Each complete source is a group -> [(canonical key, nonnegative U)] map."""
    def validate(pool):
        if set(pool) != set(GROUPS):
            raise ValueError('missing/extra group')
        seen = set()
        for rows in pool.values():
            for key, u in rows:
                if not isinstance(key, int) or key in seen:
                    raise ValueError('invalid/duplicate canonical key')
                seen.add(key)
                if u is None or not math.isfinite(u) or u < 0:
                    raise ValueError('missing/negative/nonfinite VORP')
    validate(reference)
    if not sources:
        raise ValueError('empty batch')
    energy = {g: math.fsum(u*u for _, u in reference[g]) for g in GROUPS}
    total_energy = math.fsum(energy.values())
    if not math.isfinite(total_energy) or total_energy <= 0:
        raise ValueError('empty positive reference')
    weights = {g: energy[g]/total_energy for g in GROUPS}
    provisional = {}
    for name, pool in sources.items():
        validate(pool)
        provisional[name] = {}
        for g in GROUPS:
            total = math.fsum(u for _, u in pool[g])
            if not math.isfinite(total) or (weights[g] > 0 and total <= 0):
                raise ValueError('positive budget has no positive source VORP')
            if weights[g] == 0 and total > 0:
                raise ValueError('source/reference coverage mismatch')
            provisional[name][g] = [(k, weights[g]*u/total if total else 0.0)
                                       for k, u in pool[g]]
    peak = max(q for pool in provisional.values() for rows in pool.values() for _, q in rows)
    scale = 70/peak
    values = {s: {g: [(k, scale*q) for k, q in rows] for g, rows in pool.items()}
              for s, pool in provisional.items()}
    budgets = {g: scale*w for g, w in weights.items()}
    return weights, budgets, scale, values


def verify():
    d = json.loads(INPUT.read_text())
    assert hashlib.sha256(INPUT.read_bytes()).hexdigest() == PIN, 'pinned input changed'
    reference = {g: [] for g in GROUPS}
    names = {}
    for row in d['values']:
        key = row['player_key']; names[key] = row['player']
        if row['tier'] in ('starter', 'bench'):
            u = max(0, row['ppg'] - d['calibration'][row['pos']]['rw'])
            reference[row['pos'], row['tier']].append((key, u))
    weights, budgets, total_budget, values = allocate(reference, {'ESPN': reference})
    peak_u = max(u for rows in reference.values() for _, u in rows)
    result = {'model': 'reference-squared-surplus-batch70-proposal-v1',
              'source_path': str(INPUT.relative_to(ROOT)), 'source_sha256': PIN,
              'content_vintage': d['inputs']['espn_snapshot_date'],
              'scoring': d['inputs']['scoring'], 'teams': d['inputs']['teams'],
              'reference_shape': d['reference_shape'], 'comparison_batch': ['ESPN'],
              'total_budget': total_budget, 'groups': [], 'players': []}
    for g in GROUPS:
        rows = reference[g]; out = dict(values['ESPN'][g]); sum_u = math.fsum(u for _, u in rows)
        assert math.isclose(math.fsum(out.values()), budgets[g], rel_tol=1e-12)
        ordered = sorted(rows, key=lambda row: row[1])
        assert all(out[a[0]] <= out[b[0]] for a,b in zip(ordered, ordered[1:]))
        result['groups'].append({'position': g[0], 'role': g[1], 'n': len(rows),
            'vorp_sum': sum_u, 'squared_surplus_sum': math.fsum(u*u for _,u in rows),
            'share': weights[g], 'budget': budgets[g],
            'linear_budget': 70*sum_u/peak_u})
        for key,u in sorted(rows, key=lambda row: -row[1])[:2]:
            result['players'].append({'player_key':key, 'player':names[key],
                'group':'/'.join(g), 'vorp':u, 'proposed':out[key], 'linear':70*u/peak_u})
    assert math.isclose(math.fsum(budgets.values()), total_budget, rel_tol=1e-12)
    assert max(v for rows in values['ESPN'].values() for _,v in rows) == 70
    # Units: uniform reference and independent source unit changes cancel.
    scaled_ref = {g: [(k, 16*u) for k,u in rows] for g,rows in reference.items()}
    scaled_source = {g: [(k, 3*u) for k,u in rows] for g,rows in reference.items()}
    _,_,_,rescaled = allocate(scaled_ref, {'ESPN':scaled_source})
    for g in GROUPS:
        assert all(math.isclose(a[1],b[1],rel_tol=1e-12)
                   for a,b in zip(values['ESPN'][g],rescaled['ESPN'][g]))
    # A second complete source changes concentration and thus the shared anchor.
    synthetic = {g: list(rows) for g,rows in reference.items()}
    g = ('RB','starter'); synthetic[g] = [(k,u if j == 0 else 0.0) for j,(k,u) in enumerate(synthetic[g])]
    _, b2, total2, v2 = allocate(reference, {'ESPN':reference, 'synthetic':synthetic})
    for pool in v2.values():
        assert math.isclose(math.fsum(v for rows in pool.values() for _,v in rows),total2,rel_tol=1e-12)
        for group in GROUPS:
            assert math.isclose(math.fsum(v for _,v in pool[group]),b2[group],rel_tol=1e-12)
    assert total2 < total_budget
    # Rejections discriminate bad inputs; these do not establish pipeline readiness.
    bads = [({}, {'ESPN':reference}),
            ({g:[] for g in GROUPS}, {'ESPN':reference})]
    for bad in (None, -1.0, float('nan'), float('inf')):
        pool = {g:list(rows) for g,rows in reference.items()}
        key,_ = pool[GROUPS[0]][0]; pool[GROUPS[0]][0] = (key,bad)
        bads.append((reference, {'bad':pool}))
    pool = {g:list(rows) for g,rows in reference.items()}; pool[GROUPS[0]] = []
    bads.append((reference, {'bad':pool}))
    pool = {g:list(rows) for g,rows in reference.items()}; pool[GROUPS[1]].append(pool[GROUPS[0]][0])
    bads.append((reference, {'bad':pool}))
    for ref,sources in bads:
        try:
            allocate(ref,sources)
        except ValueError:
            pass
        else:
            raise AssertionError('bad input accepted')
    result['checks'] = ['group/total conservation','within-group ordering','global maximum70',
                        'uniform units invariance','shared two-source budget','8 invalid inputs rejected']
    print(json.dumps(result,indent=2,allow_nan=False))


if __name__ == '__main__':
    verify()
