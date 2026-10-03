"""JEG-209 arithmetic illustration; never imported by the production pipeline."""
import hashlib
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
POSITIONS = ('QB', 'RB', 'WR', 'TE')
GROUPS = [(p, r) for p in POSITIONS for r in ('starter', 'bench')]
PINS = {
    'ESPN': ('ddf-20260930-espn-half_ppr-12t-0p15/ddf_leg.json',
             'af508f01700ebf5ee791aa932360b8da2b83b26b39d537144e7c04aa22162021'),
    'CBS ROS': ('ddf-20260930-cbsros-half_ppr-12t-0p15/ddf_leg_cbsros.json',
                'afdf7a80a05655a1ba6f9845ba562dfd77b6e0846df79360b75c75b503ba6591'),
    'Razzball': ('ddf-20261001-razzball-half_ppr-12t-0p15/ddf_leg_razzball.json',
                'a28babbf2a1d57fc26086ab69e1809b22f642f3c26c0ffb7142a50eb092856d0'),
}


def number(x):
    if isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x) or x < 0:
        raise ValueError('missing/negative/nonfinite/nonnumeric value')
    return x


def validate(pool):
    if set(pool) != set(GROUPS):
        raise ValueError('missing/extra group')
    seen = set()
    for rows in pool.values():
        for key, u in rows:
            if type(key) is not int or key in seen:
                raise ValueError('invalid/duplicate canonical key')
            seen.add(key)
            number(u)


def blend_defaults(references, alpha):
    """Linear mean of same-unit, complete raw-VORP group totals."""
    if not references or set(references) != set(alpha):
        raise ValueError('reference manifest mismatch')
    for pool in references.values():
        validate(pool)
    for a in alpha.values():
        if number(a) <= 0:
            raise ValueError('reference weight must be positive')
    denominator = number(math.fsum(alpha.values()))
    totals = {g: number(math.fsum(alpha[s] * math.fsum(u for _, u in pool[g])
                                 for s, pool in references.items()) / denominator)
              for g in GROUPS}
    total = number(math.fsum(totals.values()))
    if total <= 0:
        raise ValueError('empty positive reference')
    return {g: t/total for g, t in totals.items()}


def allocate(requested, sources):
    """Visible closed-form bench caps, then one all-source 70 normalization."""
    if set(requested) != set(GROUPS) or not sources:
        raise ValueError('missing group or empty batch')
    for w in requested.values():
        number(w)
    if not math.isclose(math.fsum(requested.values()), 1, rel_tol=0, abs_tol=1e-12):
        raise ValueError('budget shares must sum to one')
    totals = {}
    for s, pool in sources.items():
        validate(pool)
        totals[s] = {g: number(math.fsum(u for _, u in rows)) for g, rows in pool.items()}
        for g in GROUPS:
            if requested[g] > 0 and totals[s][g] <= 0:
                raise ValueError('funded group without positive source VORP')
    effective = dict(requested)
    caps = {}
    for p in POSITIONS:
        gs, gb = (p, 'starter'), (p, 'bench')
        limits = {}
        for s, pool in sources.items():
            # Empty roles impose no cross-role comparison; no synthetic epsilon.
            if not pool[gs] or not pool[gb]:
                limits[s] = 1.0
                continue
            a = min(u for _, u in pool[gs]) / totals[s][gs] if totals[s][gs] else 0.0
            b = max(u for _, u in pool[gb]) / totals[s][gb] if totals[s][gb] else 0.0
            limits[s] = a/(a+b) if a+b else 1.0
        cap = min(limits.values())
        position = requested[gs] + requested[gb]
        requested_t = requested[gb]/position if position else 0.0
        t = min(requested_t, cap)
        effective[gb] = position*t
        effective[gs] = position-effective[gb]
        # A cap cannot create a funded starter group with no data.
        if any(effective[gs] > 0 and totals[s][gs] <= 0 for s in sources):
            raise ValueError('ironing requires unavailable starter VORP')
        caps[p] = {'requested_bench_share': requested_t, 'effective_bench_share': t,
                   'maximum_bench_share': cap, 'per_source_caps': limits,
                   'constrained': t < requested_t}
    q = {s: {g: [(k, effective[g]*u/totals[s][g] if totals[s][g] else 0.0)
                 for k, u in rows] for g, rows in pool.items()}
         for s, pool in sources.items()}
    peak = max((v for pool in q.values() for rows in pool.values() for _, v in rows), default=0)
    if peak <= 0:
        raise ValueError('empty positive peak')
    scale = number(70/peak)
    values = {s: {g: [(k, scale*v) for k, v in rows] for g, rows in pool.items()}
              for s, pool in q.items()}
    budgets = {g: scale*w for g, w in effective.items()}
    return effective, budgets, scale, values, caps


def check(sources, result):
    effective, budgets, total, values, caps = result
    assert math.isclose(math.fsum(effective.values()), 1, abs_tol=1e-12)
    assert math.isclose(math.fsum(budgets.values()), total, rel_tol=1e-12)
    assert math.isclose(max(v for pool in values.values() for rows in pool.values()
                            for _, v in rows), 70, rel_tol=1e-12)
    for s, pool in sources.items():
        assert math.isclose(math.fsum(v for rows in values[s].values() for _, v in rows), total, rel_tol=1e-12)
        for g, rows in pool.items():
            out = dict(values[s][g])
            assert math.isclose(math.fsum(out.values()), budgets[g], abs_tol=1e-10)
            ordered = sorted(rows, key=lambda x: x[1])
            assert all(out[a[0]] <= out[b[0]] for a, b in zip(ordered, ordered[1:]))
            assert all(out[k] == 0 for k, u in rows if u == 0)
        for p in POSITIONS:
            starter, bench = values[s][p, 'starter'], values[s][p, 'bench']
            if starter and bench:
                assert min(v for _, v in starter) + 1e-10 >= max(v for _, v in bench)
    return caps


def verify():
    sources, manifest, names = {}, {}, {}
    for source, (relative, pin) in PINS.items():
        path = ROOT / 'data/ddf-two-tier' / relative
        assert hashlib.sha256(path.read_bytes()).hexdigest() == pin, 'pinned bytes changed'
        d = json.loads(path.read_text())
        assert d['inputs']['scoring'] == 'half_ppr' and d['inputs']['teams'] == 12
        sources[source] = {g: [] for g in GROUPS}
        for row in d['values']:
            names[row['player_key']] = row['player']
            if row['tier'] in ('starter', 'bench'):
                sources[source][row['pos'], row['tier']].append(
                    (row['player_key'], max(0, row['ppg']-d['calibration'][row['pos']]['rw'])))
        manifest[source] = {'path': str(path.relative_to(ROOT)), 'sha256': pin,
                            'inputs': d['inputs'], 'reference_shape': d['reference_shape']}
    # Equal weights illustrate a blend, not an approved production weighting policy.
    alpha = {s: 1 for s in sources}
    requested = blend_defaults(sources, alpha)
    result = allocate(requested, sources)
    check(sources, result)
    effective, budgets, total, values, caps = result
    # One-source linear defaults reduce exactly to ordinary VORP rescale.
    solo = {'ESPN': sources['ESPN']}
    solo_result = allocate(blend_defaults(solo, {'ESPN': 1}), solo)
    check(solo, solo_result)
    peak_u = max(u for rows in solo['ESPN'].values() for _, u in rows)
    for g, rows in solo['ESPN'].items():
        for (k, u), (k2, v) in zip(rows, solo_result[3]['ESPN'][g]):
            assert k == k2 and math.isclose(v, 70*u/peak_u, abs_tol=1e-10)
    # Unit conversion must be COMMON across reference sources before blending.
    converted = {s: {g: [(k, 16*u) for k, u in rows] for g, rows in pool.items()}
                 for s, pool in sources.items()}
    converted_result = allocate(blend_defaults(converted, alpha), converted)
    check(converted, converted_result)
    for s, pool in values.items():
        for g, rows in pool.items():
            assert all(math.isclose(a[1], b[1], abs_tol=1e-10)
                       for a, b in zip(rows, converted_result[3][s][g]))
    # Deliberately infeasible controls: preserve position total, expose the cap.
    forced = dict(requested)
    p = ('QB', 'starter'), ('QB', 'bench')
    position = forced[p[0]] + forced[p[1]]
    forced[p[0]], forced[p[1]] = position*.01, position*.99
    forced_result = allocate(forced, sources)
    check(sources, forced_result)
    assert forced_result[4]['QB']['constrained']
    assert math.isclose(sum(forced_result[0][g] for g in p), position, abs_tol=1e-12)
    # Null, bool and bad numeric values cannot quietly become zeros.
    negatives = 0
    for bad in (None, True, '1', -1, float('nan'), float('inf')):
        pool = {g: list(rows) for g, rows in sources['ESPN'].items()}
        key, _ = pool[GROUPS[0]][0]; pool[GROUPS[0]][0] = key, bad
        try:
            allocate(requested, {'bad': pool})
        except ValueError:
            negatives += 1
        else:
            raise AssertionError('bad input accepted')
    for bad in ({}, {g: [] for g in GROUPS}):
        try:
            allocate(requested, {'bad': bad})
        except ValueError:
            negatives += 1
        else:
            raise AssertionError('bad coverage accepted')
    duplicate = {g: list(rows) for g, rows in sources['ESPN'].items()}
    duplicate[GROUPS[1]].append(duplicate[GROUPS[0]][0])
    try:
        allocate(requested, {'duplicate': duplicate})
    except ValueError:
        negatives += 1
    else:
        raise AssertionError('duplicate accepted')
    output = {'model': 'linear-blend-controlled-batch70-design-v2',
              'production_ready': False, 'illustrative_reference_weights': alpha,
              'manifest': manifest, 'total_budget': total, 'caps': caps,
              'groups': [{'position': g[0], 'role': g[1],
                          'raw_vorp_totals': {s: math.fsum(u for _, u in pool[g]) for s, pool in sources.items()},
                          'requested_share': requested[g], 'effective_share': effective[g],
                          'displayed_budget': budgets[g]} for g in GROUPS],
              'players': [{'source': s, 'player': names[k], 'player_key': k,
                           'group': '/'.join(g), 'value': v}
                          for s, pool in values.items() for g, rows in pool.items()
                          for k, v in rows if k in (869, 2227, 1370, 3133)],
              'checks': ['per-group/total conservation', 'within-group order and genuine zero',
                         'within-position starter >= bench', 'batch maximum70',
                         'single-reference linear baseline identity', 'common unit invariance',
                         'visible infeasible control cap preserves position total',
                         f'{negatives} invalid inputs rejected']}
    print(json.dumps(output, indent=2, allow_nan=False))


if __name__ == '__main__':
    verify()
