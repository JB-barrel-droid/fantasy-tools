"""Fractional flex and bench seats (JEG-1334, part of JEG-1333).

Decision: Jeremy, 2026-10-29, "Go with B" (JEG-1286, `docs/decisions.md`
"JEG-1286: fractional flex and bench seats (option B)"). Research:
`docs/research/jeg1286-flex-flips.md`.

Today VP-2.2 hands each flex seat and each bench seat to whoever ranks above
a hard cutoff. When two fringe players near the cutoff swap order, a whole
seat moves from one position to another and every value at both positions
reprices. Under option B each candidate holds a share of a seat,
Phi((score - tau) / sigma), with tau set so the shares add up to the seats.
The fractional counts are written as a weighted mix of whole allocations;
the value pipeline runs once per allocation and the values are averaged by
weight. As sigma goes to 0 the mix is one allocation, today's.

This module only builds the mix. Nothing calls it yet; JEG-1335 wires it
into `value_reference.allocate`, the spec reference and `vpAllocate` in
`value-model.js`. The JS twin is `app/trade-value-chart/assets/
fractional-seats.js`; `tests/test_fractional_seats.py` holds the two equal.

The bench discount is not defined here. The caller passes
`bench_discount(starters, teams)`, which returns a function (pos, k) to the
usage discount of the k-th bench candidate at pos, so the one definition
stays in `roster_convention.vorp_bench_allocate` (JEG-556).
"""
from __future__ import annotations

import math

POSITIONS = ("QB", "RB", "WR", "TE")
PRUNE = 1e-3        # mix entries lighter than this are dropped, then renormalized
_BISECT = 200


def phi(z: float) -> float:
    """Standard normal CDF."""
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def soft_select(items, n):
    """Expected seats by position when n seats go to `items`.

    items: [(pos, score, sigma)], in tie-break order (best first among equal
    scores). Each item holds Phi((score - tau) / sigma) of a seat, with tau
    found by bisection so the shares add up to n. When every sigma is 0 this
    is the hard top n by score, ties going to the earlier item: today's rule.
    Returns {pos: expected seats}, summing to min(n, len(items)).
    """
    out: dict[str, float] = {}
    n = int(n)
    if n <= 0 or not items:
        return out
    if n >= len(items):
        for p, _s, _g in items:
            out[p] = out.get(p, 0.0) + 1.0
        return out
    sigmas = [float(g) for _, _, g in items]
    if all(g <= 0 for g in sigmas):
        ranked = sorted(range(len(items)), key=lambda j: (-float(items[j][1]), j))
        for j in ranked[:n]:
            p = items[j][0]
            out[p] = out.get(p, 0.0) + 1.0
        return out
    if any(g <= 0 for g in sigmas):
        raise ValueError("soft_select: sigma must be all zero or all positive")
    gmax = max(sigmas)
    lo = min(float(s) for _, s, _ in items) - 50.0 * gmax - 1.0
    hi = max(float(s) for _, s, _ in items) + 50.0 * gmax + 1.0
    for _ in range(_BISECT):
        tau = 0.5 * (lo + hi)
        if tau <= lo or tau >= hi:
            break   # the interval can't shrink further: later steps change nothing
        tot = 0.0
        for _p, s, g in items:
            tot += phi((float(s) - tau) / float(g))
        if tot > n:
            lo = tau
        else:
            hi = tau
    tau = 0.5 * (lo + hi)
    for p, s, g in items:
        out[p] = out.get(p, 0.0) + phi((float(s) - tau) / float(g))
    tot = sum(out.values())
    if tot <= 0:
        return out
    return {p: v * n / tot for p, v in out.items()}


def decompose(frac, positions=POSITIONS):
    """Fractional counts (summing to a whole number) to [(weight, counts)].

    Systematic rounding along `positions`: each position's fractional part is
    an interval laid end to end on [0, k), and a uniform u in [0, 1) picks the
    positions whose interval holds u, u + 1, ..., u + k - 1. The expected
    counts equal `frac`, and the weights move continuously with it.
    """
    positions = tuple(positions)
    fl = {p: int(math.floor(float(frac.get(p, 0.0)) + 1e-12)) for p in positions}
    f = {p: max(0.0, float(frac.get(p, 0.0)) - fl[p]) for p in positions}
    tot = sum(f[p] for p in positions)
    k = int(math.floor(tot + 0.5))
    if k == 0:
        return [(1.0, dict(fl))]
    scale = k / tot
    ends, c = {}, 0.0
    for p in positions:
        ends[p] = (c, c + f[p] * scale)
        c += f[p] * scale
    pts = sorted({0.0, 1.0} | {e % 1.0 for p in positions for e in ends[p]})
    got: dict[tuple, float] = {}
    order: list[tuple] = []
    for u0, u1 in zip(pts, pts[1:]):
        if u1 - u0 < 1e-12:
            continue
        u = 0.5 * (u0 + u1)
        sel = dict(fl)
        for p in positions:
            a, b = ends[p]
            if any(a <= u + j < b for j in range(k)):
                sel[p] += 1
        key = tuple(sel[p] for p in positions)
        if key not in got:
            got[key] = 0.0
            order.append(key)
        got[key] += u1 - u0
    return [(got[key], dict(zip(positions, key))) for key in order]


def _hard_bench(remaining, score, total_bench, disc, positions, pos_rank):
    """The greedy of roster_convention.vorp_bench_allocate with a given
    discount: each seat to the best max(0, PPG) x discount, ties to the
    earlier position, stopping when no positive candidate is left."""
    counts = {p: 0 for p in positions}
    for _ in range(max(0, int(total_bench))):
        best, winner = -1e18, None
        for p in positions:
            cands = remaining.get(p, [])
            k = counts[p]
            if k >= len(cands):
                continue
            eff = max(0.0, float(score.get(cands[k], 0) or 0)) * disc(p, k)
            if eff > best or (eff == best and winner is not None and pos_rank[p] < pos_rank[winner]):
                best, winner = eff, p
        if winner is None or best <= 0:
            break
        counts[winner] += 1
    return counts


def allocation_mix(*, teams, dedicated, superflex, flex_eligible, flex_seats, bench_seats,
                   order, score, sigma, bench_discount, positions=POSITIONS,
                   soft_bench=True, prune=PRUNE):
    """VP-2.2 with fractional flex and bench seats, as [(weight, allocation)].

    teams: league size. dedicated, superflex: league-wide seats per position
    (superflex from today's hard rule). flex_seats, bench_seats: league-wide
    totals. order: {pos: [player ids, best first]}. score: {id: mean PPG}.
    sigma: projection noise in mean PPG (0 gives today's allocation).
    bench_discount(starters, teams) -> disc(pos, k). Each allocation is
    {pos: {dedicated, superflex, flex, bench, starters, rostered}}, the shape
    of value_reference.allocate. Weights sum to 1; entries under `prune` are
    dropped and the rest renormalized.
    """
    positions = tuple(positions)
    pos_rank = {p: j for j, p in enumerate(positions)}
    t = int(teams)
    d = {p: int(dedicated.get(p, 0)) for p in positions}
    sf = {p: int(superflex.get(p, 0)) for p in positions}
    sigma = float(sigma)
    # Flex candidates in today's tie-break order: score, then position, then id.
    fitems = []
    for p in positions:
        if p not in flex_eligible:
            continue
        for idx, i in enumerate(order.get(p, [])):
            if idx >= d[p] + sf[p]:
                fitems.append((pos_rank[p], i, p))
    fitems.sort(key=lambda x: (x[0], x[1]))
    items = [(p, float(score[i]), sigma) for _r, i, p in fitems]
    fxf = soft_select(items, int(flex_seats))
    out = []
    for wv, fx in decompose({p: fxf.get(p, 0.0) for p in positions}, positions):
        starters = {p: d[p] + sf[p] + fx[p] for p in positions}
        remaining = {p: list(order.get(p, []))[starters[p]:] for p in positions}
        disc = bench_discount(starters, t)
        if not soft_bench or sigma <= 0:
            verts = [(1.0, _hard_bench(remaining, score, bench_seats, disc, positions, pos_rank))]
        else:
            bitems = []
            for p in positions:
                for k, i in enumerate(remaining[p]):
                    dk = float(disc(p, k))
                    eff = max(0.0, float(score.get(i, 0) or 0)) * dk
                    if eff > 0 and dk > 0:
                        bitems.append((p, eff, sigma * dk))
            nb = min(int(bench_seats), len(bitems))
            bf = soft_select(bitems, nb)
            verts = decompose({p: bf.get(p, 0.0) for p in positions}, positions)
        for wb, b in verts:
            a = {}
            for p in positions:
                s_ = starters[p]
                a[p] = {"dedicated": d[p], "superflex": sf[p], "flex": fx[p],
                        "bench": int(b.get(p, 0)), "starters": s_, "rostered": s_ + int(b.get(p, 0))}
            out.append((wv * wb, a))
    kept = [(w, a) for w, a in out if w >= prune] or [max(out, key=lambda x: x[0])]
    tot = sum(w for w, _ in kept)
    return [(w / tot, a) for w, a in kept]


def expected_counts(mix, positions=POSITIONS):
    """{pos: {field: expected count}} of a mix."""
    fields = ("dedicated", "superflex", "flex", "bench", "starters", "rostered")
    return {p: {f: sum(w * a[p][f] for w, a in mix) for f in fields} for p in positions}
