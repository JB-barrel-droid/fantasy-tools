#!/usr/bin/env python3
"""Expected-starts value: the analysis model behind docs/methodology.md ES-* (JEG-521 G1).

This is NOT the engine. It is a standalone implementation of the expected-starts
spec on the build's own inputs, used to produce the before/after table Jeremy
decides on (JEG-450 rule) and the sensitivity of the result to m_pos and sigma.
The engine change lands through JEG-508's pipeline (curve-widget.js,
value-model.js, value_reference.py, spec_reference), never from here.

What it computes, per league setting (scoring x teams, default roster):

  before   today's Adjusted values and DDF Value from pipelines/value_reference.py
           (the live two-tier at the 15% bench share, ESPN anchored), scaled to
           the fixed pie so the two columns share a total;
  after A  the expected-starts spec, option A ("replace the slices"): each
           source's value above waivers is split into a start-worthy part and a
           fill-in part by the lineup share of the player's level (ES-4 to
           ES-6); the parts are the 8 groups of VP-3; weights average across
           sources (VP-4); the pie splits by the weights (VP-5);
  after B  option B ("only set the bench share"): VP-2.6 slices unchanged; the
           per-position bench budget is set so that bench-tier players hold the
           share option A gives them.

For each: bench-tier share per position (the pie held by players ranked past
the starters), the fill-state share (the pie paid on fill-in parts), the price
of a starter-level point against a bench-level point, the top movers, and the
order check (zero inversions within every source and position).

Inputs: data/fixtures/current/players.json (espn_ppg, cbsros_ppg, rz_ppg),
data/fixtures/current/comparison-sources-data.json (the charts' 12-team
natives), output/lineup-parameters.json (pipelines/derive_lineup_parameters.py).

Usage:
    python3 pipelines/expected_starts_model.py [--params output/lineup-parameters.json]
        [--out output/expected-starts-before-after.json]
        [--report output/expected-starts-before-after.md] [--no-sensitivity]
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "pipelines"))
sys.path.insert(0, str(REPO))

PARAMS = REPO / "output" / "lineup-parameters.json"
OUT = REPO / "output" / "expected-starts-before-after.json"
REPORT = REPO / "output" / "expected-starts-before-after.md"
SCHEMA = "expected-starts-before-after/1"

POSITIONS = ("QB", "RB", "WR", "TE")
SCORINGS = ("standard", "half_ppr", "ppr")
TEAM_COUNTS = (8, 10, 12, 14)
PROJECTIONS = {"espn": "espn_ppg", "cbsros": "cbsros_ppg", "razzball": "rz_ppg"}
CHARTS = ("fantasycalc", "usatoday", "fantasypros", "cbs")
ROSTER = {"QB": 1, "RB": 2, "WR": 3, "TE": 1, "FLEX": 1, "BENCH": 6}
FLEX_ELIGIBLE = ("RB", "WR", "TE")
BENCH_MIX_12 = {"QB": 10, "RB": 27, "WR": 33, "TE": 10}
PIE_PER_STARTING_SLOT = 28.0
STARTERS_PER_TEAM = ROSTER["QB"] + ROSTER["RB"] + ROSTER["WR"] + ROSTER["TE"] + ROSTER["FLEX"]
TOP_MOVERS = 30
# First-pass assumptions (JEG-521 description), kept only for the sensitivity table.
FIRST_PASS = {"m": {"QB": 0.11, "RB": 0.17, "WR": 0.14, "TE": 0.13}, "sigma_rel": 0.25}


# ------------------------------------------------------------------ normal helpers

SQRT2 = math.sqrt(2.0)
INV_SQRT_2PI = 1.0 / math.sqrt(2.0 * math.pi)


def Phi(z: float) -> float:
    return 0.5 * (1.0 + math.erf(z / SQRT2))


def phi(z: float) -> float:
    return INV_SQRT_2PI * math.exp(-0.5 * z * z)


def band_surplus(mu: float, s: float, w: float, lo: float, hi: float) -> float:
    """E[(X - w) 1[lo < X <= hi]] for X ~ N(mu, s), with lo >= w. hi may be inf.

    Bands are open below and closed above, so the first non-starter (whose value
    is the starter line l) is in the depth-1 band, not start-worthy (VP-2.5).
    With s = 0 it is the point mass: (mu - w) if lo < mu <= hi else 0."""
    if hi <= lo:
        return 0.0
    if s <= 0:
        return (mu - w) if (lo < mu <= hi and mu > w) else 0.0
    za = (lo - mu) / s
    if math.isinf(hi):
        return (mu - w) * (1.0 - Phi(za)) + s * phi(za)
    zc = (hi - mu) / s
    return (mu - w) * (Phi(zc) - Phi(za)) + s * (phi(za) - phi(zc))


def prob_band(mu: float, s: float, lo: float, hi: float) -> float:
    """P(lo < X <= hi) for X ~ N(mu, s); a point mass when s = 0."""
    if hi <= lo:
        return 0.0
    if s <= 0:
        return 1.0 if lo < mu <= hi else 0.0
    za = (lo - mu) / s
    if math.isinf(hi):
        return 1.0 - Phi(za)
    return Phi((hi - mu) / s) - Phi(za)


def binomial_at_least(n: int, q: float, k: int) -> float:
    """P(Binomial(n, q) >= k)."""
    if k <= 0:
        return 1.0
    if n <= 0 or k > n:
        return 0.0
    return sum(math.comb(n, j) * q ** j * (1 - q) ** (n - j) for j in range(k, n + 1))


# ------------------------------------------------------------------ roster allocation (VP-2.2)

def dhondt(seats: int, weights: dict, order=POSITIONS) -> dict:
    alloc = {p: 0 for p in weights}
    for _ in range(max(0, seats)):
        best, best_q = None, -1.0
        for p in order:
            q = weights[p] / (alloc[p] + 1)
            if q > best_q + 1e-15:
                best, best_q = p, q
        alloc[best] += 1
    return alloc


def alloc(lists: dict, teams: int, roster=ROSTER) -> dict:
    """lists: {pos: [values sorted descending]}. Returns per position
    {dedicated, flex, starters, bench, rostered}. Greedy flex (OC-4 A)."""
    d = {p: teams * roster[p] for p in POSITIONS}
    cands = []
    for p in FLEX_ELIGIBLE:
        for i, v in enumerate(lists[p][d[p]:], start=d[p]):
            cands.append((-v, POSITIONS.index(p), i, p))
    cands.sort()
    fx = {p: 0 for p in POSITIONS}
    for c in cands[:teams * roster["FLEX"]]:
        fx[c[3]] += 1
    bench = dhondt(round(teams * roster["BENCH"] + 1e-9), dict(BENCH_MIX_12))
    out = {}
    for p in POSITIONS:
        s = d[p] + fx[p]
        out[p] = {"dedicated": d[p], "flex": fx[p], "starters": s, "bench": bench[p], "rostered": s + bench[p]}
    return out


def lines(values: list, starters: int, rostered: int) -> tuple:
    """Waiver line w (value at index N, else the last listed) and starter line
    l (value at index S, else w), with l >= w. VP-2.3 / VP-2.5 without imputation."""
    if not values:
        return None, None
    w = values[rostered] if len(values) > rostered else values[-1]
    l = values[starters] if len(values) > starters else w
    return w, max(l, w)


# ------------------------------------------------------------------ expected-starts components (ES-4..6)

def position_components(values: list, starters: int, rostered: int, teams: int, m: float, bye: float,
                        sigma_rel: float, sigma_floor: float, fill_cap_depth: int | None = None,
                        form: str = "share") -> dict:
    """For one source and position. values: the work list sorted descending.

    form = "share" (ES-5, the spec): the player's value above waivers times the
    probability-weighted lineup share of his level,
        share(x) = avail x [ P(X > l) + sum_k fill_k P(e_k < X <= e_{k-1}) ],
    which is at most avail. form = "option": the convex form
        avail x E[(X - w)^+ lineup(X)],
    which also pays for the upside of a level change (manifesto section 5) and
    is reported for comparison only (it exceeds the surplus near the line).

    Returns {w, l, bands, avail, players: [{x, s, starter_part, bench_part, v, share}]}.
    starter_part / bench_part are in source units x availability; v is the plain
    value above waivers; share = (starter_part + bench_part) / v, None where v = 0."""
    w, l = lines(values, starters, rostered)
    if w is None:
        return {"w": None, "l": None, "bands": [], "players": []}
    avail = (1.0 - bye) * (1.0 - m)
    q = bye + (1.0 - bye) * m  # a starter at this position is unavailable this week
    n_per_team = max(1, round(starters / teams)) if teams else 1
    # Depth bands: band k (k >= 1) is (e_k, e_{k-1}] where e_0 = l and e_k is the
    # value of the first player at depth k + 1 (0-based index starters + k x teams).
    edges = [l]
    k = 1
    while True:
        idx = starters + k * teams
        if idx >= len(values) or values[idx] <= w:
            break
        edges.append(values[idx])
        k += 1
        if fill_cap_depth and k > fill_cap_depth:
            break
    bands = []
    for k in range(1, len(edges)):
        bands.append({"depth": k, "lo": edges[k], "hi": edges[k - 1], "fill": binomial_at_least(n_per_team, q, k)})
    # The last band runs down to the waiver line.
    bands.append({"depth": len(edges), "lo": w, "hi": edges[-1], "fill": binomial_at_least(n_per_team, q, len(edges))})
    players = []
    for x in values:
        s = max(sigma_rel * x, sigma_floor) if x > 0 else sigma_floor
        v = max(0.0, x - w)
        if form == "option":
            start = band_surplus(x, s, w, l, math.inf)
            fill = 0.0
            for b in bands:
                fill += b["fill"] * band_surplus(x, s, w, b["lo"], b["hi"])
        else:
            start = v * prob_band(x, s, l, math.inf)
            fill = 0.0
            for b in bands:
                fill += b["fill"] * v * prob_band(x, s, b["lo"], b["hi"])
        sp, bp = avail * start, avail * fill
        players.append({"x": x, "s": s, "starter_part": sp, "bench_part": bp, "v": v,
                        "share": ((sp + bp) / v) if v > 0 else None})
    return {"w": w, "l": l, "bands": bands, "avail": avail, "n_per_team": n_per_team, "players": players}


def slice_components(values: list, starters: int, rostered: int) -> dict:
    """VP-2.6 slices (option B keeps these): bench slice up to the starter line,
    starter slice above it."""
    w, l = lines(values, starters, rostered)
    players = []
    if w is None:
        return {"w": None, "l": None, "players": []}
    for x in values:
        bsl = max(0.0, min(x, l) - w)
        ssl = max(0.0, x - l)
        players.append({"x": x, "bench_part": bsl, "starter_part": ssl, "v": bsl + ssl})
    return {"w": w, "l": l, "players": players}


# ------------------------------------------------------------------ one setting

class SourceLists:
    """Per source: {pos: [(key, value), ...] sorted}, and the position of every key."""

    def __init__(self, natives: dict, pos_of: dict, family: str, key: str):
        self.key, self.family = key, family
        self.lists = {p: [] for p in POSITIONS}
        for k, v in natives.items():
            p = pos_of.get(k)
            if p in self.lists and isinstance(v, (int, float)) and math.isfinite(v):
                self.lists[p].append((k, float(v)))
        for p in POSITIONS:
            self.lists[p].sort(key=lambda kv: (-kv[1], kv[0]))

    def values(self, p):
        return [v for _, v in self.lists[p]]

    def keys(self, p):
        return [k for k, _ in self.lists[p]]


def run_setting(sources: list, teams: int, params: dict, chart_sigma: dict, variant: str = "A",
                form: str = "share") -> dict:
    """sources: list of SourceLists (included set I). params: {pos: {m, sigma_rel,
    sigma_floor}, bye}. Returns adjusted values per source, DDF, weights, shares."""
    pie = PIE_PER_STARTING_SLOT * teams * STARTERS_PER_TEAM
    bye = params["bye"]
    per_source = {}
    for src in sources:
        counts = alloc({p: src.values(p) for p in POSITIONS}, teams)
        comps = {}
        for p in POSITIONS:
            pp = params[p]
            if src.family == "chart":
                w_chart, _ = lines(src.values(p), counts[p]["starters"], counts[p]["rostered"])
                # Charts: the family's own relative spread, no absolute floor. The
                # deep tail of the charts is too noisy for one (floor_frac is
                # reported, not used; ES-5.3).
                sig_rel = chart_sigma[p]["sigma_rel"]
                sig_floor = 0.0
            else:
                sig_rel, sig_floor = pp["sigma_rel"], pp["sigma_floor"]
            es = position_components(src.values(p), counts[p]["starters"], counts[p]["rostered"], teams,
                                     pp["m"], bye, sig_rel, sig_floor, form=form)
            sl = slice_components(src.values(p), counts[p]["starters"], counts[p]["rostered"])
            comps[p] = {"counts": counts[p], "es": es, "slices": sl}
        per_source[src.key] = comps
    # Groups and weights (VP-3 / VP-4) on the chosen components.
    comp_key = "es" if variant == "A" else "slices"
    weights = {}
    for key, comps in per_source.items():
        G = {}
        for p in POSITIONS:
            pl = comps[p][comp_key]["players"]
            G[(p, "starter")] = sum(x["starter_part"] for x in pl)
            G[(p, "bench")] = sum(x["bench_part"] for x in pl)
        total = sum(G.values())
        weights[key] = {g: (v / total) for g, v in G.items()} if total > 0 else None
        per_source[key]["_G"] = G
    W = {}
    for p in POSITIONS:
        for r in ("starter", "bench"):
            vals = [w[(p, r)] for w in weights.values() if w is not None]
            W[(p, r)] = statistics.mean(vals) if vals else 0.0
    tot = sum(W.values())
    W = {g: v / tot for g, v in W.items()} if tot > 0 else W
    if variant == "B":
        W = reweight_option_b(W, per_source, sources, teams)
    budgets = {g: pie * W[g] for g in W}
    # Adjusted values (VP-5).
    adjusted = {}
    for src in sources:
        comps = per_source[src.key]
        G = comps["_G"]
        vals = {}
        for p in POSITIONS:
            bs, bb = budgets[(p, "starter")], budgets[(p, "bench")]
            gs, gb = G[(p, "starter")], G[(p, "bench")]
            # OC-5 A: an unfunded group's budget moves to the other group.
            if gs <= 0 and gb > 0:
                bb, bs = bb + bs, 0.0
            if gb <= 0 and gs > 0:
                bs, bb = bs + bb, 0.0
            rs = bs / gs if gs > 0 else 0.0
            rb = bb / gb if gb > 0 else 0.0
            for key, comp in zip(src.keys(p), comps[p][comp_key]["players"]):
                vals[key] = rs * comp["starter_part"] + rb * comp["bench_part"]
        adjusted[src.key] = vals
    return {"pie": pie, "weights": {f"{p}|{r}": W[(p, r)] for (p, r) in W}, "adjusted": adjusted,
            "per_source": per_source, "sources": [s.key for s in sources]}


def reweight_option_b(W: dict, per_source: dict, sources: list, teams: int) -> dict:
    """Option B: keep the slices, but set each position's bench-group weight so
    that bench-tier players hold the share option A gives them. Uses the
    average over sources of (bench-tier bench slices / all bench slices)."""
    # Option A's bench-tier share per position comes from the same components.
    target = {}
    for p in POSITIONS:
        tier_shares, ratios = [], []
        for src in sources:
            comps = per_source[src.key][p]
            S = comps["counts"]["starters"]
            es = comps["es"]["players"]
            tot_es = sum(x["starter_part"] + x["bench_part"] for x in es)
            if tot_es > 0:
                tier_shares.append(sum(x["starter_part"] + x["bench_part"] for x in es[S:]) / tot_es)
            sl = comps["slices"]["players"]
            all_b = sum(x["bench_part"] for x in sl)
            if all_b > 0:
                ratios.append(sum(x["bench_part"] for x in sl[S:]) / all_b)
        target[p] = (statistics.mean(tier_shares) if tier_shares else 0.0,
                     statistics.mean(ratios) if ratios else 1.0)
    out = dict(W)
    for p in POSITIONS:
        pos_w = W[(p, "starter")] + W[(p, "bench")]
        share, ratio = target[p]
        # bench-tier share = W_bench x ratio / pos_w  ->  W_bench = share x pos_w / ratio
        wb = min(pos_w, share * pos_w / ratio) if ratio > 0 else W[(p, "bench")]
        out[(p, "bench")] = wb
        out[(p, "starter")] = pos_w - wb
    return out


# ------------------------------------------------------------------ metrics

def tiers_on_mean(sources: list, teams: int) -> dict:
    """{key: (pos, tier, mean_ppg)} from the projections' mean points per game
    (VP-7); the bench tier is what 'bench share' is measured on."""
    acc = defaultdict(list)
    pos_of = {}
    for src in sources:
        if src.family != "projection":
            continue
        for p in POSITIONS:
            for k, v in src.lists[p]:
                acc[k].append(v)
                pos_of[k] = p
    mean = {k: statistics.mean(v) for k, v in acc.items()}
    lists = {p: sorted((v for k, v in mean.items() if pos_of[k] == p), reverse=True) for p in POSITIONS}
    counts = alloc(lists, teams)
    ranked = {p: sorted((k for k in mean if pos_of[k] == p), key=lambda k: (-mean[k], k)) for p in POSITIONS}
    out = {}
    for p in POSITIONS:
        w, l = lines(lists[p], counts[p]["starters"], counts[p]["rostered"])
        for i, k in enumerate(ranked[p]):
            tier = "starter" if i < counts[p]["starters"] else ("bench" if i < counts[p]["rostered"] else "waiver")
            out[k] = {"pos": p, "tier": tier, "mean": mean[k], "v": max(0.0, mean[k] - w) if w is not None else 0.0}
    return out


def ddf_mean(adjusted: dict, keys) -> dict:
    out = {}
    for k in keys:
        vals = [a[k] for a in adjusted.values() if k in a]
        out[k] = statistics.mean(vals) if vals else None
    return out


def shares_and_ratio(values: dict, tiers: dict, teams: int | None = None) -> dict:
    """Bench-tier share per position and overall, position shares, and the price
    of a starter-level point against a bench-level point: median over
    starters of value per point above waivers, over the same for bench-tier
    players (on the mean projection's lines)."""
    by_pos = defaultdict(float)
    bench_pos = defaultdict(float)
    starter_rates, bench_rates = defaultdict(list), defaultdict(list)
    total = 0.0
    for k, v in values.items():
        if v is None or k not in tiers:
            continue
        t = tiers[k]
        total += v
        by_pos[t["pos"]] += v
        if t["tier"] == "bench":
            bench_pos[t["pos"]] += v
        if t["v"] > 0.25:
            (starter_rates if t["tier"] == "starter" else bench_rates if t["tier"] == "bench" else defaultdict(list))[t["pos"]].append(v / t["v"])
    top_share = {}
    if teams:
        for p in POSITIONS:
            ranked = sorted((values[k] for k in values if values[k] is not None and k in tiers and tiers[k]["pos"] == p),
                            reverse=True)
            top_share[p] = (sum(ranked[:teams]) / by_pos[p]) if by_pos[p] else None
    out = {"total": total, "position_share": {p: (by_pos[p] / total if total else None) for p in POSITIONS},
           "top_tier_share": top_share,
           "bench_tier_share": {p: (bench_pos[p] / by_pos[p] if by_pos[p] else None) for p in POSITIONS},
           "bench_tier_share_overall": (sum(bench_pos.values()) / total) if total else None,
           "starter_to_bench_price": {}}
    for p in POSITIONS:
        if starter_rates[p] and bench_rates[p]:
            out["starter_to_bench_price"][p] = statistics.median(starter_rates[p]) / statistics.median(bench_rates[p])
        else:
            out["starter_to_bench_price"][p] = None
    return out


def inversions(adjusted: dict, sources: list) -> int:
    """Pairs within one source and position where a higher native got a lower
    Adjusted value (strict), or equal natives are not required to tie."""
    n = 0
    for src in sources:
        vals = adjusted[src.key]
        for p in POSITIONS:
            prev_x = prev_a = None
            for k, x in src.lists[p]:
                a = vals[k]
                if prev_x is not None and x < prev_x and a > prev_a + 1e-9:
                    n += 1
                prev_x, prev_a = x, a
    return n


# ------------------------------------------------------------------ inputs

def load_params(path=PARAMS) -> dict:
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    rec = doc["recommended"]
    params = {p: {"m": rec[p]["m"], "sigma_rel": rec[p]["sigma_rel"], "sigma_floor": rec[p]["sigma_floor"]}
              for p in POSITIONS}
    params["bye"] = rec["bye_share"]
    return params


def chart_sigma_from(sources: list, teams: int) -> dict:
    """Relative spread across the charts in chart units, per position: median
    sample sd / mean over players at least two charts list, in the band from
    half the starters to the rostered count; floor = median absolute sd below
    the starters. Mirrors derive_lineup_parameters.cross_source_sigma."""
    charts = [s for s in sources if s.family == "chart"]
    # Charts are in different units (FantasyCalc in the thousands, CBS in
    # tens). Put each on a common scale first: one factor per chart so that its
    # total over the players every chart lists is the same (the Indexed idea).
    listed = [{k: v for p in POSITIONS for k, v in c.lists[p]} for c in charts]
    shared = set.intersection(*(set(d) for d in listed)) if listed else set()
    factors = []
    for d in listed:
        tot = sum(d[k] for k in shared)
        factors.append((1000.0 / tot) if tot > 0 else 1.0)
    acc = defaultdict(list)
    pos_of = {}
    for c, d, f in zip(charts, listed, factors):
        for p in POSITIONS:
            for k, v in c.lists[p]:
                acc[k].append(v * f)
                pos_of[k] = p
    out = {}
    for p in POSITIONS:
        rows = [(statistics.mean(v), statistics.stdev(v)) for k, v in acc.items() if pos_of[k] == p and len(v) >= 2]
        rows.sort(key=lambda r: -r[0])
        sizes = alloc({q: [r[0] for r in rows] if q == p else [] for q in POSITIONS}, teams)[p]
        band = rows[sizes["starters"] // 2:sizes["rostered"]]
        deep = rows[sizes["starters"]:]
        # The floor is kept relative to the position's waiver-line value, so it
        # can be applied in any chart's own units (floor_frac x the chart's w).
        w_common = rows[sizes["rostered"]][0] if len(rows) > sizes["rostered"] else (rows[-1][0] if rows else 1.0)
        out[p] = {"sigma_rel": statistics.median(sd / m for m, sd in band) if band else 0.2,
                  "floor_frac": (statistics.median(sd for _, sd in deep) / w_common) if deep and w_common > 0 else 0.0,
                  "sigma_floor": 0.0, "players": len(rows), "shared_players": len(shared)}
    return out


def load_sources(inp, scoring: str, teams: int) -> tuple:
    """Included sources at a setting from the reference's inputs: the three
    projections (players.json per-game) and the four charts (12-team natives)."""
    import value_reference as ref
    pos_of = {k: p["pos"] for k, p in inp.players.items()}
    sources = []
    for key, field in PROJECTIONS.items():
        natives = {}
        for k, p in inp.players.items():
            v = (p.get(field) or {}).get(scoring)
            if isinstance(v, (int, float)) and math.isfinite(v):
                natives[k] = float(v)
        if natives:
            sources.append(SourceLists(natives, pos_of, "projection", key))
    setting = ref.Setting(inp, scoring, teams)
    for key in CHARTS:
        nat = setting.native(key)
        if nat:
            sources.append(SourceLists({int(k): float(v) for k, v in nat.items()}, pos_of, "chart", key))
    return sources, pos_of


def before_values(inp, hist, scoring: str, teams: int) -> dict:
    """Today's Adjusted values per source and the blended DDF Value, from the
    Python reference (the live engine's twin), at this setting."""
    import value_reference as ref
    r = ref.compute(inp, {"scoring": scoring, "teams": teams, "superflex": 0}, hist=hist)
    rows = r["views"]["adj"]
    out = {"ddf": {}, "sources": defaultdict(dict)}
    for k, row in rows.items():
        key = int(k)
        if row.get("ddf_value") is not None:
            out["ddf"][key] = row["ddf_value"]
        for src in list(PROJECTIONS) + list(CHARTS):
            v = row.get(src)
            if v is not None:
                out["sources"][src][key] = v
    return out


# ------------------------------------------------------------------ the comparison

def compare_setting(inp, hist, scoring: str, teams: int, params: dict, names: dict) -> dict:
    sources, pos_of = load_sources(inp, scoring, teams)
    chart_sigma = chart_sigma_from(sources, teams)
    tiers = tiers_on_mean(sources, teams)
    keys = sorted(tiers)
    before = before_values(inp, hist, scoring, teams)
    pie = PIE_PER_STARTING_SLOT * teams * STARTERS_PER_TEAM
    b_total = sum(v for k, v in before["ddf"].items() if k in tiers)
    before_scaled = {k: v * pie / b_total for k, v in before["ddf"].items() if k in tiers} if b_total else {}
    out = {"setting": {"scoring": scoring, "teams": teams}, "pie": pie, "before_total_unscaled": b_total,
           "chart_sigma": chart_sigma, "variants": {}}
    out["before"] = shares_and_ratio(before_scaled, tiers, teams)
    for variant, form in (("A", "share"), ("A-option", "option"), ("B", "share")):
        run = run_setting(sources, teams, params, chart_sigma, variant[0], form)
        ddf = ddf_mean(run["adjusted"], keys)
        metrics = shares_and_ratio(ddf, tiers, teams)
        fill_share = sum(v for g, v in run["weights"].items() if g.endswith("|bench"))
        movers = []
        for k in keys:
            a, b = ddf.get(k), before_scaled.get(k)
            if a is None or b is None:
                continue
            movers.append({"key": k, "name": names.get(k, str(k)), "pos": tiers[k]["pos"], "tier": tiers[k]["tier"],
                           "mean_ppg": round(tiers[k]["mean"], 2), "before": round(b, 2), "after": round(a, 2),
                           "change": round(a - b, 2)})
        movers.sort(key=lambda m: -abs(m["change"]))
        proj_sources = [s for s in sources if s.family == "projection"]
        out["variants"][variant] = {
            "weights": run["weights"], "fill_state_share": fill_share, "metrics": metrics,
            "inversions": inversions(run["adjusted"], sources),
            "top_movers": movers[:TOP_MOVERS],
            "top_values": sorted(({"key": k, "name": names.get(k, str(k)), "pos": tiers[k]["pos"], "value": round(v, 2)}
                                  for k, v in ddf.items() if v is not None), key=lambda r: -r["value"])[:10],
            "source_bench_tier_share": {s.key: _source_bench_tier(run, s) for s in sources},
            "lineup_share_examples": _share_examples(run, proj_sources, names, tiers),
        }
    return out


def _source_bench_tier(run, src) -> dict:
    out = {}
    for p in POSITIONS:
        comps = run["per_source"][src.key][p]
        S = comps["counts"]["starters"]
        vals = [run["adjusted"][src.key][k] for k in src.keys(p)]
        tot = sum(vals)
        out[p] = (sum(vals[S:]) / tot) if tot > 0 else None
    return out


def _share_examples(run, proj_sources, names, tiers) -> list:
    """A few players' expected lineup share of their surplus on the first
    projection source, around each position's starter line."""
    if not proj_sources:
        return []
    src = proj_sources[0]
    rows = []
    for p in POSITIONS:
        comps = run["per_source"][src.key][p]
        S = comps["counts"]["starters"]
        pl = comps["es"]["players"]
        for i in (0, max(0, S // 2), max(0, S - 1), S, S + 5, S + 12):
            if i < len(pl) and pl[i]["share"] is not None:
                k = src.keys(p)[i]
                rows.append({"source": src.key, "pos": p, "rank": i + 1, "name": names.get(k, str(k)),
                             "ppg": round(pl[i]["x"], 2), "sigma": round(pl[i]["s"], 2),
                             "share": round(pl[i]["share"], 3),
                             "start_worthy_part": round(pl[i]["starter_part"] / pl[i]["v"], 3) if pl[i]["v"] else None})
    return rows


def sensitivity(inp, scoring: str, teams: int, params: dict) -> list:
    """Bench-tier share and starter/bench price at one setting across m and
    sigma multipliers, the first-pass assumptions, and the two bounds."""
    sources, _ = load_sources(inp, scoring, teams)
    chart_sigma = chart_sigma_from(sources, teams)
    tiers = tiers_on_mean(sources, teams)
    keys = sorted(tiers)
    rows = []

    def run(label, prm, csig=None, form="share"):
        r = run_setting(sources, teams, prm, csig or chart_sigma, "A", form)
        ddf = ddf_mean(r["adjusted"], keys)
        met = shares_and_ratio(ddf, tiers, teams)
        rows.append({"label": label, "top_tier_share": met["top_tier_share"], "m": {p: round(prm[p]["m"], 3) for p in POSITIONS},
                     "sigma_rel": {p: round(prm[p]["sigma_rel"], 3) for p in POSITIONS},
                     "bench_tier_share": met["bench_tier_share"], "overall": met["bench_tier_share_overall"],
                     "starter_to_bench_price": met["starter_to_bench_price"],
                     "fill_state_share": sum(v for g, v in r["weights"].items() if g.endswith("|bench"))})

    def scaled(m_mult=1.0, s_mult=1.0, s_abs=None, m_abs=None, floor_mult=1.0):
        prm = {"bye": params["bye"]}
        for p in POSITIONS:
            prm[p] = {"m": (m_abs[p] if m_abs else params[p]["m"] * m_mult),
                      "sigma_rel": (s_abs if s_abs is not None else params[p]["sigma_rel"] * s_mult),
                      "sigma_floor": params[p]["sigma_floor"] * floor_mult}
        return prm

    run("recommended (share form)", scaled())
    run("recommended, convex option form", scaled(), form="option")
    run("convex option form, sigma x 0.5", scaled(s_mult=0.5, floor_mult=0.5), form="option")
    for mm in (0.5, 0.75, 1.25, 1.5):
        run(f"m x {mm}", scaled(m_mult=mm))
    for sm in (0.0, 0.25, 0.5, 0.75, 1.25, 1.5):
        run(f"sigma x {sm}", scaled(s_mult=sm, floor_mult=sm))
    run("first-pass assumptions (m QB 11 RB 17 WR 14 TE 13, sigma 25%)",
        scaled(m_abs=FIRST_PASS["m"], s_abs=FIRST_PASS["sigma_rel"]),
        {p: {**chart_sigma[p], "sigma_rel": FIRST_PASS["sigma_rel"]} for p in POSITIONS})
    run("lower bound: fill-in only (sigma 0)", scaled(s_mult=0.0, floor_mult=0.0))
    # Upper bound: every surplus point counts (m = 0, bye = 0, no fill discount) = plain value above waivers.
    prm = scaled(s_mult=0.0, floor_mult=0.0)
    prm["bye"] = 0.0
    for p in POSITIONS:
        prm[p]["m"] = 0.0
    r = run_setting(sources, teams, prm, chart_sigma, "A")
    # With sigma 0 and m = bye = 0, fill_k = 0: bench players get nothing; add the
    # plain VORP bound directly instead.
    plain = {}
    for src in sources:
        counts = alloc({p: src.values(p) for p in POSITIONS}, teams)
        vals = {}
        for p in POSITIONS:
            w, _ = lines(src.values(p), counts[p]["starters"], counts[p]["rostered"])
            for k, x in src.lists[p]:
                vals[k] = max(0.0, x - w) if w is not None else 0.0
        tot = sum(vals.values())
        plain[src.key] = {k: v * r["pie"] / tot for k, v in vals.items()} if tot else vals
    met = shares_and_ratio(ddf_mean(plain, keys), tiers, teams)
    rows.append({"label": "upper bound: plain value above waivers (bench starts every week)",
                 "top_tier_share": met["top_tier_share"],
                 "m": {p: 0.0 for p in POSITIONS}, "sigma_rel": {p: 0.0 for p in POSITIONS},
                 "bench_tier_share": met["bench_tier_share"], "overall": met["bench_tier_share_overall"],
                 "starter_to_bench_price": met["starter_to_bench_price"], "fill_state_share": None})
    return rows


# ------------------------------------------------------------------ report

def _pct(x, d=1):
    return "n/a" if x is None else f"{100 * x:.{d}f}%"


def _x(x):
    return "n/a" if x is None else f"{x:.1f}x"


def render_report(doc: dict) -> str:
    L = ["# Expected-starts value: before and after, all 12 settings", ""]
    L.append(f"Produced by `pipelines/expected_starts_model.py` on the Week {doc['content_week']} build. "
             "Before = today's live values (two-tier at the 15% bench share, ESPN anchored), scaled to the fixed "
             "pie. After A = expected-starts replaces the slices (ES-4 to ES-6). After B = slices kept, bench "
             "budget set from A. Bench-tier share = the pie held by players ranked past the starters on the mean "
             "projection. Price ratio = median value per point above waivers, starters over bench tier.")
    L.append("")
    prm = doc["params"]
    L.append("Parameters: " + "; ".join(f"{p} m {_pct(prm[p]['m'])}, sigma {_pct(prm[p]['sigma_rel'])}, floor "
                                        f"{prm[p]['sigma_floor']:.2f}" for p in POSITIONS)
             + f"; bye share {_pct(prm['bye'])}.")
    L.append("")
    L.append("## Bench-tier share and starter/bench price, per setting")
    L.append("")
    L.append("| Setting | Variant | QB bench | RB bench | WR bench | TE bench | Overall | Fill-state share | "
             "QB price | RB price | WR price | TE price | Inversions |")
    L.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for s in doc["settings"]:
        sid = f"{s['setting']['scoring']}/{s['setting']['teams']}"
        b = s["before"]
        L.append(f"| {sid} | before | " + " | ".join(_pct(b["bench_tier_share"][p]) for p in POSITIONS)
                 + f" | {_pct(b['bench_tier_share_overall'])} | n/a | "
                 + " | ".join(_x(b["starter_to_bench_price"][p]) for p in POSITIONS) + " | n/a |")
        for v in ("A", "A-option", "B"):
            m = s["variants"][v]["metrics"]
            L.append(f"| {sid} | after {v} | " + " | ".join(_pct(m["bench_tier_share"][p]) for p in POSITIONS)
                     + f" | {_pct(m['bench_tier_share_overall'])} | "
                     + (_pct(s['variants'][v]['fill_state_share']) if v != "B" else "n/a") + " | "
                     + " | ".join(_x(m["starter_to_bench_price"][p]) for p in POSITIONS)
                     + f" | {s['variants'][v]['inversions']} |")
    L.append("")
    L.append("## Position shares of the pie (blended DDF Value)")
    L.append("")
    L.append("| Setting | QB before | QB after A | RB before | RB after A | WR before | WR after A | TE before | TE after A |")
    L.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for s in doc["settings"]:
        sid = f"{s['setting']['scoring']}/{s['setting']['teams']}"
        b, a = s["before"]["position_share"], s["variants"]["A"]["metrics"]["position_share"]
        L.append(f"| {sid} | " + " | ".join(f"{_pct(b[p])} | {_pct(a[p])}" for p in POSITIONS) + " |")
    L.append("")
    L.append("## Sensitivity at 12-team full PPR (option A)")
    L.append("")
    L.append("| Case | QB bench | RB bench | WR bench | TE bench | Overall | Fill-state share | QB price | RB price | WR price | TE price | RB top-12 share | WR top-12 share |")
    L.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for r in doc["sensitivity"]:
        L.append(f"| {r['label']} | " + " | ".join(_pct(r["bench_tier_share"][p]) for p in POSITIONS)
                 + f" | {_pct(r['overall'])} | {_pct(r['fill_state_share'])} | "
                 + " | ".join(_x(r["starter_to_bench_price"][p]) for p in POSITIONS)
                 + f" | {_pct(r['top_tier_share'].get('RB'))} | {_pct(r['top_tier_share'].get('WR'))} |")
    b = ex_before = next((s for s in doc["settings"] if s["setting"] == {"scoring": "ppr", "teams": 12}), None)
    if b:
        L.append(f"| before (today) | " + " | ".join(_pct(b["before"]["bench_tier_share"][p]) for p in POSITIONS)
                 + f" | {_pct(b['before']['bench_tier_share_overall'])} | n/a | "
                 + " | ".join(_x(b["before"]["starter_to_bench_price"][p]) for p in POSITIONS)
                 + f" | {_pct(b['before']['top_tier_share'].get('RB'))} | {_pct(b['before']['top_tier_share'].get('WR'))} |")
    L.append("")
    L.append("## Expected lineup share of a player's surplus (ESPN, 12-team full PPR, option A)")
    L.append("")
    L.append("| Position | Rank | Player | Points per game | sigma (ppg) | Lineup share of surplus | Start-worthy part |")
    L.append("| --- | --- | --- | --- | --- | --- | --- |")
    ex = next((s for s in doc["settings"] if s["setting"] == {"scoring": "ppr", "teams": 12}), doc["settings"][0])
    for r in ex["variants"]["A"]["lineup_share_examples"]:
        L.append(f"| {r['pos']} | {r['rank']} | {r['name']} | {r['ppg']} | {r['sigma']} | {_pct(r['share'])} | "
                 f"{_pct(r['start_worthy_part'])} |")
    L.append("")
    L.append("## Top movers, blended DDF Value, before (scaled to the pie) and after A")
    for s in doc["settings"]:
        sid = f"{s['setting']['scoring']}/{s['setting']['teams']}"
        L.append("")
        L.append(f"### {sid}")
        L.append("")
        L.append("| Player | Pos | Tier | Points per game | Before | After A | Change |")
        L.append("| --- | --- | --- | --- | --- | --- | --- |")
        for m in s["variants"]["A"]["top_movers"]:
            L.append(f"| {m['name']} | {m['pos']} | {m['tier']} | {m['mean_ppg']} | {m['before']} | {m['after']} | "
                     f"{m['change']:+.2f} |")
    return "\n".join(L) + "\n"


# ------------------------------------------------------------------ main

def bench_share_readout(inp, scoring: str, teams: int, cfg: dict, **settings) -> dict:
    """The dashboard's bench-share readout (ES-14), Python reference: the
    reader's settings (objective, injury_history, league_weeks,
    projection_confidence; see derive_lineup_parameters.resolve) resolve to
    parameters, the expected-starts rule runs, and the bench tier's share of
    each position's value and of the whole pie is reported. The readout is an
    output; the bench-share override replaces it only when the reader sets it."""
    import derive_lineup_parameters as dl
    res = dl.resolve(cfg, **settings)
    params = {"bye": res["bye"], **{p: dict(res["positions"][p]) for p in POSITIONS}}
    sources, _ = load_sources(inp, scoring, teams)
    cs = chart_sigma_from(sources, teams)
    if res["projection_confidence"] != 1.0:
        cs = {p: {**cs[p], "sigma_rel": cs[p]["sigma_rel"] * res["projection_confidence"]} for p in POSITIONS}
    tiers = tiers_on_mean(sources, teams)
    run = run_setting(sources, teams, params, cs, "A")
    met = shares_and_ratio(ddf_mean(run["adjusted"], sorted(tiers)), tiers, teams)
    return {"settings": {k: res[k] for k in ("objective", "injury_history", "league_weeks", "content_week",
                                              "projection_confidence", "window")},
            "scoring": scoring, "teams": teams,
            "bench_share": {p: met["bench_tier_share"][p] for p in POSITIONS},
            "bench_share_overall": met["bench_tier_share_overall"],
            "fill_in_share": sum(v for g, v in run["weights"].items() if g.endswith("|bench")),
            "starter_to_bench_price": met["starter_to_bench_price"]}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--params", type=Path, default=PARAMS)
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--report", type=Path, default=REPORT)
    ap.add_argument("--no-sensitivity", action="store_true")
    ap.add_argument("--settings", default=None, help="comma list like ppr/12,half_ppr/10 (default: all 12)")
    args = ap.parse_args(argv)
    import value_reference as ref
    inp = ref.Inputs.load(ref.FIXTURE, ref.PLAYERS)
    hist = ref.History(ref.HISTORY)
    params = load_params(args.params)
    names = {k: p.get("name", str(k)) for k, p in inp.players.items()}
    if args.settings:
        setting_list = [(s.split("/")[0], int(s.split("/")[1])) for s in args.settings.split(",")]
    else:
        setting_list = [(sc, t) for sc in SCORINGS for t in TEAM_COUNTS]
    settings = [compare_setting(inp, hist, sc, t, params, names) for sc, t in setting_list]
    content_week = json.loads((REPO / "data/history/index.json").read_text(encoding="utf-8")).get("content_week")
    doc = {"schema": SCHEMA, "content_week": content_week, "params": params, "settings": settings,
           "sensitivity": [] if args.no_sensitivity else sensitivity(inp, "ppr", 12, params)}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(doc, indent=1, sort_keys=True, default=str), encoding="utf-8")
    args.report.write_text(render_report(doc), encoding="utf-8")
    for s in settings:
        a = s["variants"]["A"]
        print(f"{s['setting']['scoring']}/{s['setting']['teams']}: before bench "
              f"{_pct(s['before']['bench_tier_share_overall'])} -> A {_pct(a['metrics']['bench_tier_share_overall'])} "
              f"(fill-state {_pct(a['fill_state_share'])}), inversions {a['inversions']}")
    print(f"wrote {args.out} and {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
