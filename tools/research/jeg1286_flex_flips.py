"""JEG-1286 research: how often a flex or bench slot flip reprices a position.

Research only. Runs the Python reference (pipelines/value_reference.py) of a
checkout given by --repo and swaps `value_reference.allocate` in-process to
hold, replay or replace the league allocation (VP-2.2). Nothing in the
pipeline, config or published output changes.

Experiments (docs/research/jeg1286-flex-flips.md explains each):

  margins   how far each setting's flex and bench cutoffs are from flipping
  sweep     1 PPG and 0.5 PPG changes to one source's projection for every
            player near a flex or rostered cutoff; how often the allocation
            flips, and how far DDF Value moves with the allocation free vs
            held
  options   the same sweep under candidate rules (fractional flex blend,
            fixed flex split, bench discount decoupled from the flex split)
  history   the real data updates on main (every players.json bake), replayed
            with today's code: how often the allocation flips between two
            consecutive bakes and how much of the move the flip causes

Usage:
  python3 tools/research/jeg1286_flex_flips.py --repo . --out docs/research/data
  python3 tools/research/jeg1286_flex_flips.py --repo /path/to/pr1077 --tag band --only sweep
"""
from __future__ import annotations

import argparse
import copy
import json
import math
import statistics
import subprocess
import sys
import tempfile
from datetime import timezone, timedelta
from multiprocessing import Pool
from pathlib import Path

HERE = Path(__file__).resolve()

# The two real leagues Jeremy plays in, as their settings pages show them
# (USO and Charlotte Patriots, both 12-team half PPR, pulled 2026-10-29 for
# JEG-1188). No league rosters are loaded: these are the no-league values at
# each league's own roster shape.
LEAGUES = {
    "uso": {"scoring": "half_ppr", "teams": 12, "slots": {"QB": 1, "RB": 2, "WR": 3, "TE": 1},
            "flex": 1, "bench": 5},
    "charlotte": {"scoring": "half_ppr", "teams": 12, "slots": {"QB": 1, "RB": 2, "WR": 2, "TE": 1},
                  "flex": 1, "bench": 6},
}
# Where real managers put the W/R/T slot in those two leagues on 2026-10-29
# (USO RB 5, WR 6, TE 1; Charlotte RB 5, WR 5, TE 2). Used only by the
# fixed-split options C and D as a stand-in for a market convention.
REAL_FLEX_SHARE = {"RB": 10 / 24, "WR": 11 / 24, "TE": 3 / 24}
DELTAS = (-1.0, -0.5, 0.5, 1.0)
BAND = 3            # players either side of a cutoff that the sweep perturbs
PRUNE = 1e-3       # option B vertices lighter than this are dropped
OPTION_DELTAS = (-1.0, 1.0)   # options are swept at +-1 PPG only, for time

VR = RC = ALLOCATE = None


def setup(repo: Path):
    global VR, RC, ALLOCATE
    repo = Path(repo).resolve()
    for p in (repo, repo / "pipelines" / "lib", repo / "pipelines"):
        sys.path.insert(0, str(p))
    import value_reference as vr  # noqa: E402
    from lib import roster_convention as rc  # noqa: E402
    VR, RC, ALLOCATE = vr, rc, vr.allocate
    return vr, rc


# ---------------------------------------------------------------------------
# Cells and runs
# ---------------------------------------------------------------------------

def cells():
    out = [{"name": f"{sc}/{t}", "scoring": sc, "teams": t} for sc in VR.SCORINGS for t in VR.TEAM_COUNTS]
    for name, L in LEAGUES.items():
        out.append({"name": name, **copy.deepcopy(L)})
    return out


def make_setting(inp, cell):
    s = VR.Setting(inp, cell["scoring"], cell["teams"])
    if "slots" in cell:
        s.shape = {**s.shape, **cell["slots"], "FLEX": cell["flex"], "BENCH": cell["bench"]}
        s.league = VR.League(
            teams=s.teams, slots={p: s.shape[p] for p in VR.POSITIONS}, flex=s.shape["FLEX"],
            superflex=s.shape["SUPERFLEX"], bench=s.shape["BENCH"],
            bench_share=s.league.bench_share)
    return s


def extract(res):
    """{key: {"ddf": DDF Value, "proj": DDF Value (projections), "adj": {src: Adjusted}}}."""
    out = {}
    for i, r in res["rows"].items():
        out[i] = {"pos": r["pos"], "ddf": r["ddf"]["blended"]["value"],
                  "proj": r["ddf"]["projections"]["value"],
                  "adj": {k: v for k, v in r["adjusted"].items() if v is not None}}
    return out


def run(inp, cell, alloc_fn=None):
    """One Setting run. alloc_fn(league, order, score, call_index) replaces
    VR.allocate when given. Returns (values, allocations, result)."""
    orig = ALLOCATE
    made = []

    def patched(league, order, score, **kw):
        out = orig(league, order, score, **kw) if alloc_fn is None else alloc_fn(league, order, score, len(made))
        made.append(copy.deepcopy(out))
        return out

    VR.allocate = patched
    try:
        res = make_setting(inp, cell).result()
    finally:
        VR.allocate = orig
    return extract(res), made, res


def replay(allocs):
    def fn(league, order, score, idx):
        return copy.deepcopy(allocs[idx]) if idx < len(allocs) else ALLOCATE(league, order, score)
    return fn


def split(alloc):
    return ({p: alloc[p]["flex"] for p in VR.POSITIONS}, {p: alloc[p]["bench"] for p in VR.POSITIONS})


def moves(a, b, skip=None):
    """Largest |b - a| over players other than `skip`, for DDF Value, DDF
    Value (projections) and any source's Adjusted value."""
    best = {"ddf": (0.0, None), "proj": (0.0, None), "adj": (0.0, None, None)}
    for i, ra in a.items():
        if i == skip or i not in b:
            continue
        rb = b[i]
        for f in ("ddf", "proj"):
            if ra[f] is not None and rb[f] is not None:
                d = abs(rb[f] - ra[f])
                if d > best[f][0]:
                    best[f] = (d, i)
        for k, va in ra["adj"].items():
            vb = rb["adj"].get(k)
            if vb is not None:
                d = abs(vb - va)
                if d > best["adj"][0]:
                    best["adj"] = (d, i, k)
    return best


# ---------------------------------------------------------------------------
# VP-2.2 allocation, re-implemented with hooks (checked equal to VR.allocate)
# ---------------------------------------------------------------------------

def _vorp_bench(starters, remaining, score, teams, total_bench, spt=None):
    """roster_convention.vorp_bench_allocate with the discount's starters per
    team optionally given (option D). Also returns each position's last
    winner and next candidate effective score, for the bench margins."""
    P = RC.POSITIONS
    spt = spt or {p: starters.get(p, 0) / teams for p in P}
    c = {p: spt.get(p, 0) * (RC._BYE_RATE + RC._BENCH_MISS_RATE.get(p, 0.12)) for p in P}
    t1 = {p: max(1, round(2.0 * c[p] * float(teams))) for p in P}

    def disc(p, k):
        return c[p] ** (1 + k // t1[p])

    counts = {p: 0 for p in P}
    last = {}
    for _ in range(max(0, int(total_bench))):
        best, winner = -1e18, None
        for p in P:
            order = remaining.get(p, [])
            k = counts[p]
            if k >= len(order):
                continue
            eff = max(0.0, float(score.get(order[k], 0) or 0)) * disc(p, k)
            if eff > best or (eff == best and RC.POS_ORDER.get(p, 99) < RC.POS_ORDER.get(winner, 99)):
                best, winner = eff, p
        if winner is None or best <= 0:
            break
        last[winner] = (best, disc(winner, counts[winner]), remaining[winner][counts[winner]])
        counts[winner] += 1
    nxt = {}
    for p in P:
        order = remaining.get(p, [])
        k = counts[p]
        if k < len(order):
            nxt[p] = (max(0.0, float(score.get(order[k], 0) or 0)) * disc(p, k), disc(p, k), order[k])
    return counts, last, nxt


def alloc_custom(league, order, score, *, fx_override=None, spt_share=None, bench_shift=None):
    """VP-2.2 with hooks. fx_override: flex counts per position (option C or
    a blend alternative). spt_share: the flex share per position used only
    in the bench discount (option D). bench_shift: (from_pos, to_pos) moves
    one bench seat (a bench blend alternative). Returns (alloc, margins)."""
    P = VR.POSITIONS
    t = int(league.teams)
    d = {p: t * int(league.slots.get(p, 0)) for p in P}

    def take(cands, n):
        cands.sort(key=lambda c: (-score[c[1]], VR.POS_ORDER[c[0]], c[1]))
        got = {p: 0 for p in P}
        for p, _i in cands[:max(0, n)]:
            got[p] += 1
        return got, cands

    sf, _ = take([(p, i) for p in P for idx, i in enumerate(order.get(p, [])) if idx >= d[p]],
                 t * int(league.superflex))
    n_fx = t * int(league.flex)
    fx, fcands = take([(p, i) for p in P if p in league.flex_eligible
                       for idx, i in enumerate(order.get(p, [])) if idx >= d[p] + sf[p]], n_fx)
    # Flex margins: lowest winner at A against best loser at B != A.
    lowest, bestlose = {}, {}
    for j, (p, i) in enumerate(fcands):
        if j < n_fx:
            lowest[p] = i
        elif p not in bestlose:
            bestlose[p] = i
    flex_pairs = []
    for a, wi in lowest.items():
        for b, li in bestlose.items():
            if a != b:
                flex_pairs.append({"from": a, "to": b, "winner": wi, "loser": li,
                                   "gap": score[wi] - score[li]})
    flex_pairs.sort(key=lambda x: x["gap"])
    if fx_override is not None:
        fx = {p: int(fx_override.get(p, 0)) for p in P}
    starters = {p: d[p] + sf[p] + fx[p] for p in P}
    remaining = {p: order.get(p, [])[starters[p]:] for p in P}
    is_2qb = league.superflex > 0 or int(league.slots.get("QB", 1)) >= 2
    spt = None
    if spt_share is not None:
        spt = {p: (d[p] + sf[p]) / t + int(league.flex) * spt_share.get(p, 0.0) for p in P}
    b, last, nxt = _vorp_bench(starters, remaining, score, t, t * int(league.bench), spt)
    bench_pairs = []
    for a, (ea, da, wi) in last.items():
        for bb, (eb, db, li) in nxt.items():
            if a != bb and bb in P:
                # mean-PPG change of the more sensitive player that closes the gap
                bench_pairs.append({"from": a, "to": bb, "winner": wi, "loser": li,
                                    "gap_eff": ea - eb, "gap": (ea - eb) / max(da, db, 1e-12)})
    bench_pairs.sort(key=lambda x: x["gap"])
    if bench_shift is not None:
        a, bb = bench_shift
        b = dict(b)
        b[a] -= 1
        b[bb] = b.get(bb, 0) + 1
    out = {}
    for p in P:
        s = d[p] + sf[p] + fx[p]
        out[p] = {"dedicated": d[p], "superflex": sf[p], "flex": fx[p], "bench": b.get(p, 0),
                  "starters": s, "rostered": s + b.get(p, 0)}
    return out, {"flex": flex_pairs, "bench": bench_pairs}


def _phi(z):
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def soft_select(items, n):
    """items: [(pos, score, sigma)]. Each item is in the selection with
    probability Phi((score - tau) / sigma), tau set so the expected count is
    n. As sigma -> 0 this is today's hard top-n. Returns {pos: expected count}."""
    out = {}
    if n <= 0 or not items:
        return out
    if n >= len(items):
        for p, _s, _g in items:
            out[p] = out.get(p, 0.0) + 1.0
        return out
    lo = min(s for _, s, _ in items) - 50 * max(g for _, _, g in items) - 1
    hi = max(s for _, s, _ in items) + 50 * max(g for _, _, g in items) + 1
    for _ in range(200):
        tau = 0.5 * (lo + hi)
        tot = sum(_phi((s - tau) / g) for _, s, g in items)
        if tot > n:
            lo = tau
        else:
            hi = tau
    tau = 0.5 * (lo + hi)
    for p, s, g in items:
        out[p] = out.get(p, 0.0) + _phi((s - tau) / g)
    tot = sum(out.values())
    return {p: v * n / tot for p, v in out.items()} if tot > 0 else out


def decompose(frac, positions):
    """Write fractional counts (summing to an integer) as a weighted set of
    integer count vectors with the same expected value (systematic rounding
    along a fixed position order). The weights move continuously with the
    counts, so values blended over them do too."""
    fl = {p: int(math.floor(frac.get(p, 0.0) + 1e-12)) for p in positions}
    f = {p: max(0.0, frac.get(p, 0.0) - fl[p]) for p in positions}
    k = int(round(sum(f.values())))
    if k == 0:
        return [(1.0, fl)]
    scale = k / sum(f.values())
    ends, c = {}, 0.0
    for p in positions:
        ends[p] = (c, c + f[p] * scale)
        c += f[p] * scale
    pts = sorted({0.0, 1.0} | {e % 1.0 for a, b in ends.values() for e in (a, b)})
    got = {}
    for u0, u1 in zip(pts, pts[1:]):
        if u1 - u0 < 1e-12:
            continue
        u = 0.5 * (u0 + u1)
        sel = dict(fl)
        for p, (a, b) in ends.items():
            if any(a <= u + j < b for j in range(k)):
                sel[p] += 1
        key = tuple(sel[p] for p in positions)
        got[key] = got.get(key, 0.0) + (u1 - u0)
    return [(w, dict(zip(positions, key))) for key, w in got.items() if w > 1e-6]


def alloc_soft(league, order, score, sigma, bench_soft):
    """Option B: VP-2.2 with fractional flex (and optionally bench) seats.
    sigma is the projection noise in mean PPG; sigma -> 0 gives today's
    allocation. Returns [(weight, allocation)]."""
    P = VR.POSITIONS
    t = int(league.teams)
    d = {p: t * int(league.slots.get(p, 0)) for p in P}
    base, _ = alloc_custom(league, order, score)
    sf = {p: base[p]["superflex"] for p in P}
    items = [(p, float(score[i]), sigma) for p in P if p in league.flex_eligible
             for idx, i in enumerate(order.get(p, [])) if idx >= d[p] + sf[p]]
    fxf = soft_select(items, t * int(league.flex))
    out = []
    for wv, fx in decompose({p: fxf.get(p, 0.0) for p in P}, P):
        starters = {p: d[p] + sf[p] + fx[p] for p in P}
        remaining = {p: order.get(p, [])[starters[p]:] for p in P}
        if not bench_soft:
            b, _, _ = _vorp_bench(starters, remaining, score, t, t * int(league.bench))
            verts = [(1.0, b)]
        else:
            spt = {p: starters[p] / t for p in P}
            cc = {p: spt[p] * (RC._BYE_RATE + RC._BENCH_MISS_RATE.get(p, 0.12)) for p in P}
            t1 = {p: max(1, round(2.0 * cc[p] * float(t))) for p in P}
            bitems = []
            for p in P:
                for k, i in enumerate(remaining[p]):
                    dk = cc[p] ** (1 + k // t1[p])
                    eff = max(0.0, float(score.get(i, 0) or 0)) * dk
                    if eff > 0 and dk > 0:
                        bitems.append((p, eff, sigma * dk))
            nb = min(t * int(league.bench), len(bitems))
            bf = soft_select(bitems, nb)
            verts = decompose({p: bf.get(p, 0.0) for p in P}, P)
        for wb, b in verts:
            a = {}
            for p in P:
                s_ = d[p] + sf[p] + fx[p]
                a[p] = {"dedicated": d[p], "superflex": sf[p], "flex": fx[p], "bench": b.get(p, 0),
                        "starters": s_, "rostered": s_ + b.get(p, 0)}
            out.append((wv * wb, a))
    out = [(w, a) for w, a in out if w >= PRUNE]   # drops at most PRUNE per vertex
    tot = sum(w for w, _ in out)
    return [(w / tot, a) for w, a in out]


def blend(base, runs):
    out = {}
    for i, rb in base.items():
        r = {"pos": rb["pos"], "adj": {}}
        for f in ("ddf", "proj"):
            vals = [(w, a[i][f] if i in a else None) for w, a in runs]
            r[f] = None if any(v is None for _, v in vals) else sum(w * v for w, v in vals)
        for k in rb["adj"]:
            vals = [(w, a[i]["adj"].get(k) if i in a else None) for w, a in runs]
            r["adj"][k] = None if any(x is None for _, x in vals) else sum(w * x for w, x in vals)
        out[i] = r
    return out


def fixed_split(league, share):
    """Largest-remainder integer split of the league's flex seats by share."""
    n = int(league.teams) * int(league.flex)
    raw = {p: n * share.get(p, 0.0) for p in VR.POSITIONS}
    got = {p: int(math.floor(v)) for p, v in raw.items()}
    rest = n - sum(got.values())
    for p in sorted(raw, key=lambda p: (-(raw[p] - got[p]), VR.POS_ORDER[p]))[:rest]:
        got[p] += 1
    return got


# ---------------------------------------------------------------------------
# Options. Each returns values for one data state.
# ---------------------------------------------------------------------------

def option_values(inp, cell, option):
    """option: {"kind": "A"} today; {"kind": "S", "sigma": mean PPG, "bench": bool}
    option B, fractional flex (and bench) seats; {"kind": "C"} fixed flex split;
    {"kind": "D"} bench discount from the fixed flex share."""
    kind = option["kind"]
    if kind == "A":
        return run(inp, cell)[0]
    if kind == "C":
        def fn(league, order, score, idx):
            return alloc_custom(league, order, score, fx_override=fixed_split(league, REAL_FLEX_SHARE))[0]
        return run(inp, cell, fn)[0]
    if kind == "D":
        def fn(league, order, score, idx):
            return alloc_custom(league, order, score, spt_share=REAL_FLEX_SHARE)[0]
        return run(inp, cell, fn)[0]
    if kind == "CD":
        def fn(league, order, score, idx):
            return alloc_custom(league, order, score, fx_override=fixed_split(league, REAL_FLEX_SHARE),
                                spt_share=REAL_FLEX_SHARE)[0]
        return run(inp, cell, fn)[0]
    if kind == "S":
        seen = {}

        def base_fn(league, order, score, idx):
            seen.update(league=league, order=order, score=score)
            return ALLOCATE(league, order, score)

        base, made, _ = run(inp, cell, base_fn)
        if not seen:
            return base
        verts = alloc_soft(seen["league"], seen["order"], seen["score"], option["sigma"], option["bench"])
        if len(verts) == 1 and verts[0][1] == made[0]:
            return base
        runs = []
        for w, alloc in verts:
            if alloc == made[0]:
                runs.append((w, base))
            else:
                runs.append((w, run(inp, cell, lambda *a, alloc=alloc: copy.deepcopy(alloc))[0]))
        return blend(base, runs)
    raise ValueError(kind)


OPTIONS = {
    "A": {"kind": "A"},
    "B50": {"kind": "S", "sigma": 0.5, "bench": False},
    "B100": {"kind": "S", "sigma": 1.0, "bench": False},
    "B75": {"kind": "S", "sigma": 0.75, "bench": False},
    "B50b": {"kind": "S", "sigma": 0.5, "bench": True},
    "B75b": {"kind": "S", "sigma": 0.75, "bench": True},
    "B100b": {"kind": "S", "sigma": 1.0, "bench": True},
    "C": {"kind": "C"},
    "D": {"kind": "D"},
}


# ---------------------------------------------------------------------------
# Experiments
# ---------------------------------------------------------------------------

def name(inp, k):
    return inp.players[k]["name"] if k in inp.players else str(k)


def check_equal(inp):
    """alloc_custom with no hooks must match VR.allocate on every cell."""
    bad = []
    for cell in cells():
        def fn(league, order, score, idx):
            a = ALLOCATE(league, order, score)
            b = alloc_custom(league, order, score)[0]
            if a != b:
                bad.append(cell["name"])
            return a
        run(inp, cell, fn)
    return bad


def margins(inp, cell):
    got = {}

    def fn(league, order, score, idx):
        alloc, m = alloc_custom(league, order, score)
        got.update(alloc=alloc, m=m, league=league, order=order, score=score)
        return alloc

    _, _, res = run(inp, cell, fn)
    n_src = len([k for k in res["included"] if VR.FAMILY[k] == "projection"])
    fmt = lambda pr: {**pr, "winner": name(inp, pr["winner"]), "loser": name(inp, pr["loser"]),
                      "one_source_ppg": pr["gap"] * n_src}
    soft = {}
    for sigma in (0.5, 0.75, 1.0):
        v = alloc_soft(got["league"], got["order"], got["score"], sigma, True)
        soft[str(sigma)] = {"flex": {p: sum(w * a[p]["flex"] for w, a in v) for p in VR.POSITIONS},
                            "bench": {p: sum(w * a[p]["bench"] for w, a in v) for p in VR.POSITIONS},
                            "vertices": len(v)}
    return {"cell": cell["name"], "projections": n_src, "soft": soft,
            "flex": {p: got["alloc"][p]["flex"] for p in VR.POSITIONS},
            "bench": {p: got["alloc"][p]["bench"] for p in VR.POSITIONS},
            "flex_pairs": [fmt(p) for p in got["m"]["flex"][:3]],
            "bench_pairs": [fmt(p) for p in got["m"]["bench"][:3]]}


def noise(inp, cell):
    """How uncertain the mean projection is near the flex cutoff: for the 10
    flex-eligible players either side of it, the spread of the three
    projections (standard error of their mean)."""
    _, made, res = run(inp, cell)
    m = res["mean_ppg"]
    alloc = made[0]
    near = []
    cands = sorted(((p, i) for p in VR.FLEX_ELIGIBLE
                    for idx, i in enumerate(sorted((i for i in m if inp.players.get(i, {}).get("pos") == p),
                                                   key=lambda i: (-m[i], i)))
                    if idx >= alloc[p]["dedicated"]), key=lambda c: (-m[c[1]], c[1]))
    n = sum(alloc[p]["flex"] for p in VR.POSITIONS)
    for p, i in cands[max(0, n - 10):n + 10]:
        vals = [inp.ppg(i, VR.PPG_FIELD[src], cell["scoring"]) for src in VR.PROJECTIONS]
        vals = [v for v in vals if v is not None]
        if len(vals) >= 2:
            sd = statistics.stdev(vals)
            near.append({"name": name(inp, i), "pos": p, "mean": m[i], "sources": vals, "se_mean": sd / math.sqrt(len(vals))})
    ses = sorted(x["se_mean"] for x in near)
    return {"cell": cell["name"], "players": len(near), "median_se": statistics.median(ses) if ses else None,
            "p25_se": ses[len(ses) // 4] if ses else None, "p75_se": ses[(3 * len(ses)) // 4] if ses else None}


def sweep_candidates(inp, cell):
    """Players within BAND of a position's starter cutoff (flex positions)
    or rostered cutoff (all positions), in mean-PPG order."""
    _, made, res = run(inp, cell)
    if not made:
        return [], None
    alloc = made[0]
    m = res["mean_ppg"]
    keys = set()
    for p in VR.POSITIONS:
        order = sorted((i for i in m if inp.players.get(i, {}).get("pos") == p), key=lambda i: (-m[i], i))
        cuts = [alloc[p]["rostered"]]
        if p in VR.FLEX_ELIGIBLE:
            cuts.append(alloc[p]["starters"])
        for c in cuts:
            for j in range(max(0, c - BAND), min(len(order), c + BAND)):
                keys.add(order[j])
    return sorted(keys), alloc


def sweep_cell(args):
    repo, cell, opts = args
    setup(repo)
    inp = VR.Inputs.load()
    keys, base_alloc = sweep_candidates(inp, cell)
    base = {o: option_values(inp, cell, OPTIONS[o]) for o in opts}
    _, base_made, _ = run(inp, cell)
    cases = []
    for k in keys:
        for src in VR.PROJECTIONS:
            field = VR.PPG_FIELD[src]
            rec = inp.players[k].get(field)
            if not isinstance(rec, dict) or not VR._finite(rec.get(cell["scoring"])):
                continue
            old = rec[cell["scoring"]]
            for delta in DELTAS:
                rec[cell["scoring"]] = max(0.0, old + delta)
                try:
                    free, made, _ = run(inp, cell)
                    fb, bb = split(base_made[0])
                    fa, ba = split(made[0])
                    kind = "flex" if fa != fb else ("bench" if ba != bb else "none")
                    c = {"key": k, "name": name(inp, k), "pos": inp.players[k]["pos"], "src": src,
                         "delta": delta, "flip": kind, "flex_after": fa, "bench_after": ba}
                    mv = moves(base["A"], free, skip=k)
                    c["move"] = {"ddf": mv["ddf"][0], "ddf_who": name(inp, mv["ddf"][1]) if mv["ddf"][1] else None,
                                 "proj": mv["proj"][0], "adj": mv["adj"][0],
                                 "adj_who": name(inp, mv["adj"][1]) if mv["adj"][1] else None, "adj_src": mv["adj"][2]}
                    if kind != "none":
                        held, _, _ = run(inp, cell, replay(base_made))
                        fp = moves(held, free, skip=k)
                        hm = moves(base["A"], held, skip=k)
                        c["flip_part"] = {"ddf": fp["ddf"][0], "ddf_who": name(inp, fp["ddf"][1]) if fp["ddf"][1] else None,
                                          "proj": fp["proj"][0], "adj": fp["adj"][0],
                                          "adj_who": name(inp, fp["adj"][1]) if fp["adj"][1] else None,
                                          "adj_src": fp["adj"][2]}
                        c["held_move"] = {"ddf": hm["ddf"][0], "proj": hm["proj"][0], "adj": hm["adj"][0]}
                        if fp["ddf"][1] is not None:
                            w = fp["ddf"][1]
                            c["example"] = {"who": name(inp, w), "pos": base["A"][w]["pos"],
                                            "base": base["A"][w]["ddf"], "free": free[w]["ddf"],
                                            "held": held[w]["ddf"]}
                    c["options"] = {}
                    for o in opts:
                        if o == "A" or delta not in OPTION_DELTAS:
                            continue
                        ov = option_values(inp, cell, OPTIONS[o])
                        om = moves(base[o], ov, skip=k)
                        c["options"][o] = {"ddf": om["ddf"][0], "proj": om["proj"][0], "adj": om["adj"][0]}
                finally:
                    rec[cell["scoring"]] = old
                cases.append(c)
    # How far each option sits from today's values with no perturbation.
    depart = {}
    for o in opts:
        if o == "A":
            continue
        mv = moves(base["A"], base[o])
        top = sorted(((abs((base[o][i]["ddf"] or 0) - (base["A"][i]["ddf"] or 0)), i) for i in base["A"]
                      if i in base[o] and base["A"][i]["ddf"] is not None and base[o][i]["ddf"] is not None),
                     reverse=True)[:5]
        depart[o] = {"ddf": mv["ddf"][0], "proj": mv["proj"][0], "adj": mv["adj"][0],
                     "top": [{"who": name(inp, i), "pos": base["A"][i]["pos"], "today": base["A"][i]["ddf"],
                              "option": base[o][i]["ddf"]} for _, i in top]}
    return {"cell": cell["name"], "base_flex": split(base_alloc)[0], "base_bench": split(base_alloc)[1],
            "cases": cases, "departure": depart}


def examples(inp, opts, cases=None):
    """Named before/after DDF Values for flip cases under every option:
    the JEG-1286 repro (Coker, standard/10, CBS ROS -1 PPG) and the closest
    flex swap in USO and Charlotte."""
    cases = cases or []
    if not cases:
        cases.append(("standard/10", "Jalen Coker", "cbsros", -1.0))
        for lg in ("uso", "charlotte"):
            m = margins(inp, next(c for c in cells() if c["name"] == lg))
            pr = m["flex_pairs"][0]
            cases.append((lg, pr["winner"], "espn", -1.0))
    by_name = {}
    for k, p in inp.players.items():
        by_name.setdefault(p["name"], k)
    out = []
    for cell_name, who, src, delta in cases:
        cell = next(c for c in cells() if c["name"] == cell_name)
        k = by_name[who]
        rec = inp.players[k][VR.PPG_FIELD[src]]
        old = rec[cell["scoring"]]
        before = {o: option_values(inp, cell, OPTIONS[o]) for o in opts}
        _, b_made, _ = run(inp, cell)
        rec[cell["scoring"]] = max(0.0, old + delta)
        try:
            after = {o: option_values(inp, cell, OPTIONS[o]) for o in opts}
            _, a_made, _ = run(inp, cell)
        finally:
            rec[cell["scoring"]] = old
        a, b = before["A"], after["A"]
        top = sorted(((abs((b[i]["ddf"] or 0) - (a[i]["ddf"] or 0)), i) for i in a
                      if i != k and i in b and a[i]["ddf"] is not None and b[i]["ddf"] is not None),
                     reverse=True)[:6]
        out.append({"cell": cell_name, "who": who, "src": src, "delta": delta,
                    "flex_before": split(b_made[0])[0], "flex_after": split(a_made[0])[0],
                    "bench_before": split(b_made[0])[1], "bench_after": split(a_made[0])[1],
                    "players": [{"name": name(inp, i), "pos": a[i]["pos"],
                                 **{o: {"before": before[o][i]["ddf"], "after": after[o][i]["ddf"]}
                                    for o in opts if i in before[o] and i in after[o]}}
                                for _, i in top],
                    "worst": {o: moves(before[o], after[o], skip=k)["ddf"][0] for o in opts}})
    return out


# ---------------------------------------------------------------------------
# History: every players.json bake on main, replayed with today's code
# ---------------------------------------------------------------------------

def bakes(repo: Path, ref: str):
    out = subprocess.run(["git", "-C", str(repo), "log", "--reverse", "--format=%H %cI", ref, "--",
                          "data/fixtures/current/players.json"], capture_output=True, text=True, check=True)
    return [line.split() for line in out.stdout.splitlines() if line.strip()]


def history_cell(args):
    repo, cell, snaps = args
    setup(repo)
    rows = []
    prev = None
    from lib.timestamps import parse_iso_timestamp  # on the path after setup()
    for sha, when, players, fixture in snaps:
        try:
            day = parse_iso_timestamp(when).astimezone(timezone(timedelta(hours=-5))).date()
            inp = VR.Inputs.load(fixture=fixture, players=players, today=day)
            vals, made, res = run(inp, cell)
        except Exception as e:  # an old fixture today's code can't read
            rows.append({"sha": sha[:8], "when": when, "error": f"{type(e).__name__}: {e}"[:200]})
            continue
        if not made:
            rows.append({"sha": sha[:8], "when": when, "error": "degenerate (no projection in I)"})
            prev = None
            continue
        fx, bn = split(made[0])
        _, mg = alloc_custom(make_setting(inp, cell).league, *_order_score(res, inp))
        n_src = len([k for k in res["included"] if VR.FAMILY[k] == "projection"])
        r = {"sha": sha[:8], "when": when, "flex": fx, "bench": bn,
             "flex_gap": mg["flex"][0]["gap"] if mg["flex"] else None,
             "bench_gap": mg["bench"][0]["gap"] if mg["bench"] else None, "n_src": n_src}
        if prev is not None:
            pfx, pbn, pmade, pvals, _ = prev
            r["flip"] = "flex" if fx != pfx else ("bench" if bn != pbn else "none")
            tot = moves(pvals, vals)
            r["total_move"] = {"ddf": tot["ddf"][0], "ddf_who": name(inp, tot["ddf"][1]) if tot["ddf"][1] else None}
            if r["flip"] != "none" and len(pmade) == len(made):
                held, _, _ = run(inp, cell, replay(pmade))
                fp = moves(held, vals)
                r["flip_part"] = {"ddf": fp["ddf"][0], "ddf_who": name(inp, fp["ddf"][1]) if fp["ddf"][1] else None,
                                  "proj": fp["proj"][0], "adj": fp["adj"][0]}
                if fp["ddf"][1] is not None:
                    w = fp["ddf"][1]
                    r["example"] = {"who": name(inp, w), "free": vals[w]["ddf"], "held": held[w]["ddf"]}
        near = _near_flex(res, inp, made[0])
        if prev is not None and prev[4]:
            ch = [abs(res["mean_ppg"][i] - prev[4][i]) for i in prev[4] if i in res["mean_ppg"]]
            r["near_mean_change"] = statistics.median(ch) if ch else None
        rows.append(r)
        prev = (fx, bn, made, vals, {i: res["mean_ppg"][i] for i in near} if n_src >= 3 else None)
    return {"cell": cell["name"], "bakes": rows}


def _near_flex(res, inp, alloc, band=10):
    m = res["mean_ppg"]
    cands = sorted(((p, i) for p in VR.FLEX_ELIGIBLE
                    for idx, i in enumerate(sorted((i for i in m if inp.players.get(i, {}).get("pos") == p),
                                                   key=lambda i: (-m[i], i)))
                    if idx >= alloc[p]["dedicated"]), key=lambda c: (-m[c[1]], c[1]))
    n = sum(alloc[p]["flex"] for p in VR.POSITIONS)
    return [i for _, i in cands[max(0, n - band):n + band]]


def _order_score(res, inp):
    m = res["mean_ppg"]
    order = {p: sorted((i for i in m if inp.players.get(i, {}).get("pos") == p), key=lambda i: (-m[i], i))
             for p in VR.POSITIONS}
    return order, m


def snapshots(repo: Path, ref: str, workdir: Path):
    out = []
    for sha, when in bakes(repo, ref):
        d = workdir / sha[:10]
        d.mkdir(parents=True, exist_ok=True)
        ok = True
        for rel, fn in (("data/fixtures/current/players.json", "players.json"),
                        ("data/fixtures/current/comparison-sources-data.json", "comparison-sources-data.json")):
            p = subprocess.run(["git", "-C", str(repo), "show", f"{sha}:{rel}"], capture_output=True)
            if p.returncode != 0:
                ok = False
                break
            (d / fn).write_bytes(p.stdout)
        if ok:
            out.append((sha, when, str(d / "players.json"), str(d / "comparison-sources-data.json")))
    return out


# ---------------------------------------------------------------------------

def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=str(HERE.parents[2]))
    ap.add_argument("--git", default=None, help="repo whose git history to replay (default --repo)")
    ap.add_argument("--ref", default="origin/main")
    ap.add_argument("--out", default=None)
    ap.add_argument("--tag", default="main")
    ap.add_argument("--only", default="margins,noise,examples,sweep,history")
    ap.add_argument("--opts", default="A,B50b,B75b,B100b,C,D")
    ap.add_argument("--example-opts", default=",".join(OPTIONS))
    ap.add_argument("--procs", type=int, default=4)
    a = ap.parse_args(argv)
    repo = Path(a.repo).resolve()
    setup(repo)
    out_dir = Path(a.out or repo / "docs" / "research" / "data")
    out_dir.mkdir(parents=True, exist_ok=True)
    only = set(a.only.split(","))
    inp = VR.Inputs.load()
    report = {"repo_head": subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                                          capture_output=True, text=True).stdout.strip()}
    bad = check_equal(inp)
    if bad:
        raise SystemExit(f"alloc_custom differs from value_reference.allocate on {bad}")
    report["alloc_check"] = "alloc_custom == value_reference.allocate on every cell"
    if "margins" in only:
        report["margins"] = [margins(inp, c) for c in cells()]
    opts = [o for o in a.opts.split(",") if o]
    if "examples" in only:
        report["examples"] = examples(inp, [o for o in a.example_opts.split(",") if o])
    if "noise" in only:
        report["noise"] = [noise(inp, c) for c in cells()]
    with Pool(a.procs) as pool:
        if "sweep" in only:
            report["sweep"] = pool.map(sweep_cell, [(str(repo), c, opts) for c in cells()])
        if "history" in only:
            with tempfile.TemporaryDirectory() as td:
                snaps = snapshots(Path(a.git or repo), a.ref, Path(td))
                report["history"] = pool.map(history_cell, [(str(repo), c, snaps) for c in cells()])
    path = out_dir / f"jeg1286_flex_flips_{a.tag}.json"
    path.write_text(json.dumps(report, indent=1, sort_keys=True, default=str) + "\n", encoding="utf-8")
    print(path)


if __name__ == "__main__":
    main()
