"""Source-neutral value pipeline, clean-room (JEG-508).

Written only from docs/methodology.md "Value Pipeline (source-neutral,
2026-10-09)", steps VP-0..VP-12 and the decided OC table, plus the data
formats of the inputs. It shares no code with, and was written without
reading, the engine (curve-widget.js, value-model.js) or the Python reference
(pipelines/value_reference.py). Where the text leaves a detail open the most
literal reading is taken and recorded in SPEC_AMBIGUITIES.md (ids SA-n are
cited inline).

Entry points:
- run_week(...)      one week at one league setting (VP-2 .. VP-7).
- run(...)           both weeks plus the change (VP-8).
- included_set(...)  VP-1.

The result of run_week is shaped like `expected` in
tests/fixtures/value_pipeline_worked_example.json (schema /2), so the fixture
test can walk every pinned leaf. Player keys are ints throughout; the caller
converts at the edges.
"""
from __future__ import annotations

import math
import sys
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

# Roster convention module (JEG-560)
_REPO = Path(__file__).resolve().parents[2]
if str(_REPO / "pipelines") not in sys.path:
    sys.path.insert(0, str(_REPO / "pipelines"))
if str(_REPO / "pipelines" / "lib") not in sys.path:
    sys.path.insert(0, str(_REPO / "pipelines" / "lib"))

from lib.roster_convention import (
    bench_seats as _convention_bench_seats,
    starter_line as _convention_starter_line,
    waiver_band_line as _convention_waiver_band_line,
    vorp_bench_allocate as _vorp_bench,
    POSITIONS as _CONV_POSITIONS,
)

POSITIONS = ("QB", "RB", "WR", "TE")
POS_ORDER = {p: i for i, p in enumerate(POSITIONS)}
GROUP_KEYS = tuple(f"{p}|{r}" for p in POSITIONS for r in ("starter", "bench"))

BENCH_MIX_12 = {"QB": 10, "RB": 27, "WR": 33, "TE": 10}  # legacy, kept for two-tier (JEG-561)
IMPUTE_MIN_FIT = 3
ESTIMATE_FIT_N = 10
DEFAULT_BENCH_SHARE = 0.15
PIE_PER_STARTING_SLOT = 28.0

PROJECTION = "projection"
CHART = "chart"
# JEG-1058: the fixed-pie scale a reader override lives on (spec 3.6).
OVERRIDE_MIN = 0.0
OVERRIDE_MAX = 100.0


@dataclass
class Setting:
    """League setting L (VP-0)."""
    teams: int
    slots: dict                       # dedicated slots per team, {pos: D_p}
    flex: int = 1                     # F
    superflex: int = 0                # SF
    bench_per_team: float = 6         # B
    bench_share: float = DEFAULT_BENCH_SHARE
    flex_eligible: tuple = ("RB", "WR", "TE")
    position_shares: dict | None = None   # reader position shares (VP-4.4)
    bench_share_override: float | None = None   # ES-14 override (off = None)

    @classmethod
    def from_fixture(cls, s: dict) -> "Setting":
        return cls(teams=int(s["teams"]), slots=dict(s["slots"]), flex=int(s.get("flex", 0)),
                   superflex=int(s.get("superflex", 0)),
                   bench_per_team=s.get("bench_per_team", 7),
                   bench_share=float(s.get("bench_share", DEFAULT_BENCH_SHARE)),
                   flex_eligible=tuple(s.get("flex_eligible") or ("RB", "WR", "TE")),
                   position_shares=s.get("position_shares"),
                   bench_share_override=s.get("bench_share_override"))

    def starting_slots_per_team(self) -> int:
        return sum(int(self.slots.get(p, 0)) for p in POSITIONS) + self.flex + self.superflex

    def pie(self) -> float:
        """VP-5.1 (OC-1): 28 per starting slot."""
        return PIE_PER_STARTING_SLOT * self.teams * self.starting_slots_per_team()


# ---------------------------------------------------------------- helpers

def round_half_up(x) -> int:
    f = Fraction(x)
    return int((f + Fraction(1, 2)) // 1)


def median(values: list) -> float:
    v = sorted(values)
    n = len(v)
    if n % 2:
        return v[n // 2]
    return (v[n // 2 - 1] + v[n // 2]) / 2.0


def fsum_in_order(values) -> float:
    """Plain left-to-right double sum (VP-0: sums run in sort order)."""
    total = 0.0
    for x in values:
        total += x
    return total


def included_set(eligible: list, has_prior: dict) -> tuple[list, bool]:
    """VP-1.2. Returns (I, has_prior_week)."""
    with_prior = [s for s in eligible if has_prior.get(s)]
    if with_prior:
        return with_prior, True
    return list(eligible), False


# ---------------------------------------------------------------- VP-0 m

def mean_ppg(sources: dict, included: list, pos_of: dict) -> dict:
    """m_i: mean of the natives of the projections in I that list i."""
    acc: dict = {}
    for s in included:
        src = sources.get(s)
        if not src or src["family"] != PROJECTION:
            continue
        for k, x in src["values"].items():
            if pos_of.get(k) in POS_ORDER and x is not None:
                acc.setdefault(k, []).append(float(x))
    return {k: fsum_in_order(v) / len(v) for k, v in acc.items()}


def score_order(scores: dict, pos_of: dict) -> dict:
    """{pos: [keys]} by score descending, then player_key ascending."""
    out = {p: [] for p in POSITIONS}
    for k in scores:
        p = pos_of.get(k)
        if p in out:
            out[p].append(k)
    for p in out:
        out[p].sort(key=lambda k: (-scores[k], k))
    return out


# ---------------------------------------------------------------- VP-2.2 allocation

def dhondt_bench(setting, *, flex_filled: dict | None = None) -> dict:
    """VP-2.2d: D'Hondt bench seats via roster convention (market bench
    ratios, JEG-560). Replaces the fixed BENCH_MIX_12 weights.

    flex_filled: optional {pos: count} of superflex+flex starters (MR-28)."""
    slots = {p: int(setting.slots.get(p, 0)) for p in _CONV_POSITIONS}
    seats = _convention_bench_seats(
        slots, setting.teams, setting.bench_per_team,
        superflex=(setting.superflex > 0),
        flex_filled=flex_filled,
    )
    return {p: seats.get(p, 0) for p in POSITIONS}


def allocate(setting: Setting, order: dict, scores: dict, *,
             flex_bench_seats: bool = True) -> dict:
    """League allocation (VP-2.2 a-e) on a per-position order with scores.

    flex_bench_seats (MR-28): on by default (2026-10-23, Jeremy approved).
    Bench weights count sf+flex starters.
    Skipped in 2-QB / superflex (Jeremy, 2026-10-23, option A):
    market_bench 2-QB data already reflects supply-capped QB benches."""
    T = setting.teams
    ded = {p: T * int(setting.slots.get(p, 0)) for p in POSITIONS}

    def take(cands: list, n: int) -> dict:
        cands.sort(key=lambda kp: (-scores[kp[0]], POS_ORDER[kp[1]], kp[0]))
        got = {p: 0 for p in POSITIONS}
        for _, p in cands[:max(0, n)]:
            got[p] += 1
        return got

    sf_cands = [(k, p) for p in POSITIONS for k in order[p][ded[p]:]]
    sf = take(sf_cands, T * setting.superflex)
    fx_cands = [(k, p) for p in POSITIONS if p in setting.flex_eligible
                for k in order[p][ded[p] + sf[p]:]]
    fx = take(fx_cands, T * setting.flex)
    if flex_bench_seats:
        # JEG-1121 VORP: bench fills by VORP × usage discount.
        _starters = {p: ded[p] + sf[p] + fx[p] for p in POSITIONS}
        _remaining = {p: order.get(p, [])[_starters[p]:] for p in POSITIONS}
        _is_2qb = setting.superflex > 0 or int(setting.slots.get("QB", 1)) >= 2
        _ff = (None if _is_2qb
               else {p: (sf[p] + fx[p]) / T for p in POSITIONS})
        bench = _vorp_bench(
            _starters, _remaining, scores,
            T, T * setting.bench_per_team,
            {p: int(setting.slots.get(p, 0)) for p in POSITIONS},
            _is_2qb, _ff,
        )
    else:
        # D'Hondt bench (backward compat).
        is_two_qb = setting.superflex > 0 or int(setting.slots.get("QB", 1)) >= 2
        use_flex = not is_two_qb
        ff = {p: (sf[p] + fx[p]) / T for p in POSITIONS} if use_flex else None
        bench = dhondt_bench(setting, flex_filled=ff)
    out = {}
    for p in POSITIONS:
        starters = ded[p] + sf[p] + fx[p]
        out[p] = {"dedicated": ded[p], "superflex": sf[p], "flex": fx[p], "bench": bench[p],
                  "starters": starters, "rostered": starters + bench[p]}
    return out


# ---------------------------------------------------------------- VP-2.4 fill-in

def _sorted_listed(values: dict, keys) -> list:
    return sorted(keys, key=lambda k: (-values[k], k))


def estimate_player(c: str, i: int, p: str, listed_c: list, natives: dict, peers: list,
                    peer_listed: dict, m: dict) -> dict:
    """One estimate for chart c, player i at position p (VP-2.4 d-f).

    listed_c: c's listed players at p in c's sort order.
    natives:  {source: {key: native}} listed natives only (overlay applied).
    peer_listed: {peer: set of keys the peer lists at p}.
    """
    nat_c = natives[c]
    rec: dict = {"peers": {}, "cap": nat_c[listed_c[-1]]}
    ests = []
    for k in peers:
        nat_k = natives[k]
        if i not in nat_k:
            continue
        shared = [j for j in listed_c if j in peer_listed[k]]
        fit = shared[-min(ESTIMATE_FIT_N, len(shared)):] if shared else []
        num = fsum_in_order(nat_c[j] for j in fit)
        den = fsum_in_order(nat_k[j] for j in fit)
        entry = {"fit_players": list(fit), "num": num, "den": den, "peer_native": nat_k[i]}
        if len(fit) < IMPUTE_MIN_FIT or den <= 0:
            entry.update(usable=False, ratio=None, estimate=None,
                         reason="fit set under 3" if len(fit) < IMPUTE_MIN_FIT else "peer sum <= 0")
        else:
            ratio = num / den
            est = ratio * nat_k[i]
            entry.update(usable=True, ratio=ratio, estimate=est)
            ests.append(est)
        rec["peers"][k] = entry
    if ests:
        rec["path"] = "peers"
        raw = median(ests)
    else:
        rec["path"] = "curve"
        pts = [j for j in listed_c if j in m]
        pts = pts[-min(ESTIMATE_FIT_N, len(pts)):] if pts else []
        mi = m[i]
        if len(pts) >= IMPUTE_MIN_FIT and len({m[j] for j in pts}) > 1:
            mx = fsum_in_order(m[j] for j in pts) / len(pts)
            xx = fsum_in_order(nat_c[j] for j in pts) / len(pts)
            sxy = fsum_in_order((m[j] - mx) * (nat_c[j] - xx) for j in pts)
            sxx = fsum_in_order((m[j] - mx) ** 2 for j in pts)
            b = sxy / sxx
            a = xx - b * mx
            raw = a + b * mi
            rec["curve"] = {"kind": "ols", "points": pts, "slope": b, "intercept": a, "mean_ppg": mi}
        else:
            pos_m = [j for j in listed_c if j in m and m[j] > 0]
            if pos_m:
                low = pos_m[-1]
                raw = nat_c[low] * mi / m[low]
                rec["curve"] = {"kind": "proportional", "points": pts, "low": low, "mean_ppg": mi}
            else:
                raw = 0.0
                rec["curve"] = {"kind": "zero", "points": pts, "mean_ppg": mi}
    cap = rec["cap"]
    rec["raw"] = raw
    rec["value"] = min(max(raw, 0.0), cap)
    rec["capped"] = raw > cap
    return rec


# ---------------------------------------------------------------- ES (expected starts)
# docs/methodology.md ES-3 .. ES-5, ES-10, ES-14 and the engine rulings ES-15.
# `lineup` = resolved parameters {bye, projection_confidence, positions: {pos:
# {m, sigma_rel, sigma_floor}}} (derive_lineup_parameters.resolve).

def _cdf(z: float) -> float:
    return 0.5 * math.erfc(-z / math.sqrt(2.0))


def _prob(mu: float, sd: float, lo: float, hi: float | None) -> float:
    """P(lo < X <= hi) for X ~ N(mu, sd); hi None = +inf; sd 0 = point mass."""
    if hi is not None and hi <= lo:
        return 0.0
    if sd <= 0:
        return 1.0 if (mu > lo and (hi is None or mu <= hi)) else 0.0
    top = 1.0 if hi is None else _cdf((hi - mu) / sd)
    return top - _cdf((lo - mu) / sd)


def _fill(n: int, q: float, k: int) -> float:
    """fill_k = P(Binomial(n, q) >= k), as 1 - P(< k) summed from the pmf."""
    if k <= 0:
        return 1.0
    if k > n or n <= 0:
        return 0.0
    tail = 0.0
    for j in range(k, n + 1):
        tail += math.comb(n, j) * (q ** j) * ((1.0 - q) ** (n - j))
    return tail


def resolve_lineup(cfg: dict, objective: str | None = None, injury_history: str | None = None,
                   league_weeks: dict | None = None, projection_confidence: float | None = None) -> dict:
    """ES-12 / ES-14 from the text: the window, b over the window's
    team-weeks, the drift horizon (gap before the window plus half its
    length) and sigma = sqrt(now^2 + weekly^2 x horizon) x confidence."""
    d = cfg["defaults"]
    obj = objective or d["objective"]
    hist = injury_history or d["injury_history"]
    lw = dict(d["league_weeks"])
    lw.update(league_weeks or {})
    conf = d["projection_confidence"] if projection_confidence is None else projection_confidence
    W = cfg["content_week"]
    first_po, last_po = lw["playoff_weeks"]
    lo, hi = {"season": (W + 1, last_po), "regular": (W + 1, lw["regular_season_end"]),
              "playoffs": (max(first_po, W + 1), last_po)}[obj]
    if hi >= lo:
        byes = cfg["byes"]
        b = sum(1 for wk in byes.values() if lo <= wk <= hi) / (len(byes) * (hi - lo + 1)) if byes else 0.0
        horizon = max(0, lo - W - 1) + (hi - lo + 1) / 2.0
    else:
        b, horizon = 0.0, 0.0
    pos = {}
    for p in POSITIONS:
        blk = cfg["positions"][p]
        m = (blk["m_late"] if obj == "playoffs" else blk["m"])[hist]
        sig = math.sqrt(blk["sigma_now"] ** 2 + blk["sigma_weekly"] ** 2 * horizon) * conf
        pos[p] = {"m": m, "sigma_rel": sig, "sigma_floor": blk["sigma_floor"] * conf}
    return {"bye": b, "projection_confidence": conf, "window": [lo, hi], "positions": pos}


def es_chart_sigma(setting: Setting, natives: dict, charts: list, pos_of: dict,
                   *, flex_bench_seats: bool = True) -> dict:
    """ES-15.3 (SA-ES-3): sigma for the chart family, per position."""
    shared = None
    for c in charts:
        keys = set(natives[c])
        shared = keys if shared is None else (shared & keys)
    shared = shared or set()
    scale = {}
    for c in charts:
        t = fsum_in_order(natives[c][k] for k in sorted(shared))
        scale[c] = 1000.0 / t if t > 0 else 1.0
    # MR-28: approximate flex_filled for bench weights
    # Skipped in 2-QB / superflex (Jeremy, 2026-10-23).
    is_two_qb = setting.superflex > 0 or int(setting.slots.get("QB", 1)) >= 2
    ff = None
    if flex_bench_seats and not is_two_qb:
        ff = {}
        sf_total = setting.teams * setting.superflex
        fx_total = setting.teams * setting.flex
        for p in POSITIONS:
            n_listed = sum(1 for k in shared if pos_of.get(k) == p)
            ded = setting.teams * int(setting.slots.get(p, 0))
            avail = max(0, n_listed - ded)
            # JEG-1121: sf_total/fx_total/avail are league-wide; normalize to per-team.
            ff[p] = min(sf_total + (fx_total if p in setting.flex_eligible else 0), avail) / setting.teams
    bench = dhondt_bench(setting, flex_filled=ff)
    res = {}
    for p in POSITIONS:
        vals: dict = {}
        for c in charts:
            for k, x in natives[c].items():
                if pos_of.get(k) == p:
                    vals.setdefault(k, []).append(x * scale[c])
        pts = []
        for k, xs in vals.items():
            if len(xs) < 2:
                continue
            mu = fsum_in_order(xs) / len(xs)
            var = fsum_in_order((x - mu) ** 2 for x in xs) / (len(xs) - 1)
            pts.append((mu, math.sqrt(var), k))
        pts.sort(key=lambda t: (-t[0], t[2]))
        ded = setting.teams * int(setting.slots.get(p, 0))
        more = setting.teams * setting.superflex + (setting.teams * setting.flex if p in setting.flex_eligible else 0)
        n_start = ded + min(more, max(0, len(pts) - ded))
        n_rost = n_start + bench[p]
        band = [t for t in pts[n_start // 2:n_rost] if t[0] > 0]
        res[p] = {"sigma_rel": median([sd / mu for mu, sd, _ in band]) if band else 0.2,
                  "players": len(pts), "band": len(band)}
    return res


def es_parts(values: list, S: int, T: int, w: float, line: float, m: float, bye: float,
             sig: float, floor: float) -> dict:
    """ES-3.2 depth edges, ES-4 lineup share, ES-5 parts for one work list."""
    avail = (1.0 - bye) * (1.0 - m)
    q_out = bye + (1.0 - bye) * m
    n = max(1, round(S / T)) if T else 1        # SA-ES-2: Python round, half to even
    e = [line]
    while T:
        idx = S + len(e) * T
        if idx >= len(values) or not values[idx] > w:
            break
        e.append(values[idx])
    bands = []
    for depth in range(1, len(e) + 1):
        lo = e[depth] if depth < len(e) else w
        bands.append({"depth": depth, "lo": lo, "hi": e[depth - 1], "fill": _fill(n, q_out, depth)})
    out = []
    for x in values:
        sd = max(sig * x, floor) if x > 0 else floor
        surplus = max(0.0, x - w)
        start = _prob(x, sd, line, None)
        fill = fsum_in_order(b["fill"] * _prob(x, sd, b["lo"], b["hi"]) for b in bands)
        out.append({"sw": avail * (surplus * start), "fi": avail * (surplus * fill),
                    "share": avail * (start + fill), "start_worthy": start})
    return {"avail": avail, "n_per_team": n, "bands": bands, "rows": out}


# ---------------------------------------------------------------- JEG-969 promotion/demotion

import json as _json

# JEG-1142 (Jeremy, 2026-10-27): no role-change math (bench promotion boost
# or starter demotion cut) until the JEG-1144 research supports it. Master
# switch overriding every promotion_model flag; mirrors value_reference.py
# and value-model.js. The model code is kept for later.
PROMOTION_MODEL_ENABLED = False

_PROMOTION_CONFIG = _REPO / "config" / "promotion_rates.json"


def _load_promotion_config() -> dict:
    return _json.loads(_PROMOTION_CONFIG.read_text(encoding="utf-8"))


def _promotion_rate(cfg: dict, pos: str, depth: int) -> float:
    rates = cfg.get("promotion_rate_per_remaining_week", {}).get(pos, {})
    if depth <= 0:
        return 0.0
    key = str(min(depth, 4)) if depth <= 3 else "4+"
    return float(rates.get(key, rates.get("4+", 0.0)))


def _demotion_rate_cfg(cfg: dict, pos: str) -> float:
    return float(cfg.get("demotion_rate_per_remaining_week", {}).get(pos, 0.0))


def apply_promotion_model(parts: dict, values: list, S: int, T: int, pos: str,
                          cfg: dict, weeks_remaining: float) -> dict:
    """JEG-969: adjust es_parts rows for promotion/demotion dynamics."""
    avail = parts["avail"]
    if avail <= 0 or weeks_remaining <= 0:
        return parts
    n = parts["n_per_team"]
    rows = []
    for rank_0, (pt, x) in enumerate(zip(parts["rows"], values)):
        rank = rank_0 + 1
        sw = pt["sw"]
        fi = pt["fi"]
        ls = pt["share"]
        if rank > S:
            depth = rank - S
            rate_pw = _promotion_rate(cfg, pos, depth)
            bonus = rate_pw * weeks_remaining * 0.5
            new_ls = min(avail, ls + bonus * (avail - ls))
            if ls > 0:
                scale = new_ls / ls
                sw *= scale
                fi *= scale
            ls = new_ls
        elif rank > S - n * T and rank <= S:
            rate_pw = _demotion_rate_cfg(cfg, pos)
            penalty = rate_pw * weeks_remaining * 0.5
            new_ls = max(0.0, ls - penalty * ls)
            if ls > 0:
                scale = new_ls / ls
                sw *= scale
                fi *= scale
            ls = new_ls
        rows.append({"sw": sw, "fi": fi, "share": ls, "start_worthy": pt["start_worthy"]})
    return {**parts, "rows": rows}


# ---------------------------------------------------------------- one source, VP-2/3

def price_source(s: str, family: str, natives: dict, pos_of: dict, alloc: dict,
                 fill_sets: dict | None, peers: list, m: dict, bs: float | None,
                 es: dict | None = None, promotion: dict | None = None) -> dict:
    """VP-2 (work lists, waiver/starter lines, slices) and VP-3 for one source."""
    nat = natives[s]
    listed_by_pos = {p: [] for p in POSITIONS}
    for k in nat:
        p = pos_of.get(k)
        if p in listed_by_pos:
            listed_by_pos[p].append(k)
    positions, players = {}, {}
    groups = {g: 0.0 for g in GROUP_KEYS}
    surplus = []
    for p in POSITIONS:
        a = alloc[p]
        listed = _sorted_listed(nat, listed_by_pos[p])
        estimates = {}
        if family == CHART and fill_sets is not None and listed:
            listed_set = set(listed)
            peer_listed = {k: {j for j in natives[k] if pos_of.get(j) == p} for k in peers}
            for i in fill_sets[p]:
                if i not in listed_set:
                    estimates[i] = estimate_player(s, i, p, listed, natives, peers, peer_listed, m)
        work_val = {k: nat[k] for k in listed}
        work_val.update({i: e["value"] for i, e in estimates.items()})
        work = sorted(work_val, key=lambda k: (-work_val[k], k in estimates, k))
        N, S = a["rostered"], a["starters"]
        info = dict(a)
        info.update(listed=len(listed), extended=bool(estimates),
                    imputation_ratios=estimates or None)
        if len(work) > N:
            # JEG-1047 (Jeremy, 2026-10-29): a projection's line is the
            # 7-player band around the first non-rostered seat.
            w = (_convention_waiver_band_line([work_val[k] for k in work], N)
                 if family == PROJECTION else work_val[work[N]])
            method = "estimated" if work[N] in estimates else "roster_determined"
        elif work:
            w = work_val[work[-1]]
            method = "insufficient_coverage"
        else:
            info.update(waiver_value=None, starter_line=None, method="no_players")
            positions[p] = info
            continue
        # Convention rule 3 (JEG-560): midpoint of last starter and first
        # non-starter, replacing the old first-non-starter rule.
        work_values = [work_val[k] for k in work]
        line = _convention_starter_line(work_values, S)
        if line is None:
            line = w
        line = max(line, w)
        info.update(waiver_value=w, starter_line=line, method=method)
        parts = None
        if es is not None:
            prm = es["lineup"]["positions"][p]
            if family == CHART:
                sig = es["chart_sigma"][p]["sigma_rel"] * float(es["lineup"].get("projection_confidence", 1.0))
                floor = 0.0
            else:
                sig, floor = prm["sigma_rel"], prm["sigma_floor"]
            got = es_parts([work_val[k] for k in work], S, es["teams"], w, line, prm["m"],
                           es["lineup"]["bye"], sig, floor)
            # JEG-969: apply promotion/demotion model if enabled
            if promotion is not None:
                got = apply_promotion_model(got, [work_val[k] for k in work], S, es["teams"],
                                            p, promotion["config"], promotion["weeks_remaining"])
            parts = got["rows"]
            info.update(avail=got["avail"], bands=got["bands"],
                        lineup={"m": prm["m"], "n_per_team": got["n_per_team"], "sigma_rel": sig,
                                "sigma_floor": floor})
        positions[p] = info
        g_s, g_b = [], []
        for rank, k in enumerate(work, start=1):
            x = work_val[k]
            v = max(0.0, x - w)
            if parts is None:
                bsl = max(0.0, min(x, line) - w)
                ssl = max(0.0, x - line)
            else:
                bsl, ssl = parts[rank - 1]["fi"], parts[rank - 1]["sw"]
            role = "starter" if rank <= S else ("bench" if rank <= N else "waiver")
            players[k] = {"pos": p, "native": x, "imputed": k in estimates, "rank": rank,
                          "role": role, "vorp": v, "bench_slice": bsl, "starter_slice": ssl,
                          "lineup_share": parts[rank - 1]["share"] if parts else None,
                          "start_worthy": parts[rank - 1]["start_worthy"] if parts else None}
            g_s.append(ssl)
            g_b.append(bsl)
            surplus.append(v)
        groups[f"{p}|starter"] = fsum_in_order(g_s)
        groups[f"{p}|bench"] = fsum_in_order(g_b)
    total = fsum_in_order(groups[g] for g in GROUP_KEYS)
    st_tot = fsum_in_order(groups[f"{p}|starter"] for p in POSITIONS)
    be_tot = fsum_in_order(groups[f"{p}|bench"] for p in POSITIONS)
    has_weights = total != 0
    sig = {p: groups[f"{p}|starter"] / st_tot for p in POSITIONS} if has_weights and st_tot > 0 else None
    beta = {p: groups[f"{p}|bench"] / be_tot for p in POSITIONS} if has_weights and be_tot > 0 else None
    weights = None
    if has_weights:
        weights = {}
        for p in POSITIONS:
            if bs is None:                 # ES-15.1: own implied weights
                weights[f"{p}|starter"] = groups[f"{p}|starter"] / total
                weights[f"{p}|bench"] = groups[f"{p}|bench"] / total
            elif sig is not None and beta is not None:
                weights[f"{p}|starter"] = (1 - bs) * sig[p]
                weights[f"{p}|bench"] = bs * beta[p]
            elif sig is not None:          # bench mix undefined
                weights[f"{p}|starter"] = sig[p]
                weights[f"{p}|bench"] = 0.0
            else:                          # starter mix undefined
                weights[f"{p}|starter"] = 0.0
                weights[f"{p}|bench"] = beta[p]
    return {"family": family, "positions": positions, "groups": groups, "total_vorp": total,
            "surplus_total": fsum_in_order(surplus),
            "players": players, "weights": weights, "starter_mix": sig, "bench_mix": beta,
            "has_weights": has_weights}


# ---------------------------------------------------------------- VP-4

def ddf_weights(priced: dict, included: list, bs: float | None, position_shares: dict | None) -> tuple:
    """VP-4; bs None = ES-15.1 (mean of the 8-group source weights, renormalized)."""
    S_raw, B_raw = {}, {}
    for p in POSITIONS:
        s_vals, b_vals = [], []
        for s in included:
            r = priced.get(s)
            if not r or not r["has_weights"] or r["positions"][p]["method"] == "no_players":
                continue
            if r["starter_mix"] is not None:
                s_vals.append(r["starter_mix"][p])
            if r["bench_mix"] is not None:
                b_vals.append(r["bench_mix"][p])
        S_raw[p] = fsum_in_order(s_vals) / len(s_vals) if s_vals else 0.0
        B_raw[p] = fsum_in_order(b_vals) / len(b_vals) if b_vals else 0.0
    s_sum = fsum_in_order(S_raw[p] for p in POSITIONS)
    b_sum = fsum_in_order(B_raw[p] for p in POSITIONS)
    W = {}
    if bs is None:
        raw = {}
        for g in GROUP_KEYS:
            p = g.split("|")[0]
            vals = [priced[s]["weights"][g] for s in included
                    if priced.get(s) and priced[s]["has_weights"]
                    and priced[s]["positions"][p]["method"] != "no_players"]
            raw[g] = fsum_in_order(vals) / len(vals) if vals else 0.0
        tot = fsum_in_order(raw[g] for g in GROUP_KEYS)
        for g in GROUP_KEYS:
            W[g] = raw[g] / tot if tot > 0 else 0.0
        bs_star = fsum_in_order(W[f"{p}|bench"] for p in POSITIONS)
    else:
        if b_sum == 0:
            bs_star = 0.0
        elif s_sum == 0:
            bs_star = 1.0
        else:
            bs_star = bs
        for p in POSITIONS:
            W[f"{p}|starter"] = (1 - bs_star) * S_raw[p] / s_sum if s_sum else 0.0
            W[f"{p}|bench"] = bs_star * B_raw[p] / b_sum if b_sum else 0.0
    if position_shares:
        for p in POSITIONS:
            tot = W[f"{p}|starter"] + W[f"{p}|bench"]
            if tot == 0 or p not in position_shares:
                continue
            share = float(position_shares[p])
            for r in ("starter", "bench"):
                W[f"{p}|{r}"] = W[f"{p}|{r}"] * share / tot
    return S_raw, B_raw, bs_star, W


# ---------------------------------------------------------------- VP-5

def adjust_source(r: dict, pie: float, W: dict) -> None:
    budgets = {g: pie * W[g] for g in GROUP_KEYS}
    G = r["groups"]
    moved, unpaid = [], []
    bprime = dict(budgets)
    for p in POSITIONS:
        for a_role, b_role in (("starter", "bench"), ("bench", "starter")):
            g, other = f"{p}|{a_role}", f"{p}|{b_role}"
            if G[g] == 0 and budgets[g] > 0:
                if G[other] > 0:
                    bprime[other] += budgets[g]
                    bprime[g] = 0.0
                    moved.append({"from": g, "to": other, "budget": budgets[g]})
                else:
                    unpaid.append({"group": g, "budget": budgets[g]})
    if not r["has_weights"]:
        rates = {g: 0.0 for g in GROUP_KEYS}
    else:
        rates = {g: (bprime[g] / G[g] if G[g] != 0 else 0.0) for g in GROUP_KEYS}
    sur = r.get("surplus_total", r["total_vorp"])
    factor = pie / sur if r["has_weights"] and sur > 0 else 0.0   # ES-15.4
    for k, pl in r["players"].items():
        p = pl["pos"]
        pl["adjusted"] = rates[f"{p}|bench"] * pl["bench_slice"] + rates[f"{p}|starter"] * pl["starter_slice"]
        pl["vorp_display"] = pl["vorp"] * factor
    r["rates"] = rates
    r["unfunded_moved"] = moved
    r["unfunded_groups"] = unpaid
    r["vorp_display_factor"] = factor
    r["budgets_paid"] = bprime


# ---------------------------------------------------------------- VP-6 rows

def row_value(r: dict, family: str, k: int, p: str, view: str):
    """VP-6.2: (value, estimated_path_or_None)."""
    if r["positions"][p]["method"] == "no_players":
        return None, None
    pl = r["players"].get(k)
    if pl is not None:
        return pl[view], (r["positions"][p]["imputation_ratios"] or {}).get(k, {}).get("path") if pl["imputed"] else None
    if family == CHART:
        return 0.0, None          # below rosterable depth
    return None, None             # projection that does not list him


def normalize_basis(cfg: dict | None, source_order: list) -> dict | None:
    """JEG-1044: the reader's value basis. None = the default (equal-weight
    projections). Else {"mode", "asked", "keys" (in source order), "weights"}.
    "single": one source, weight 1. "blend": every named source with a positive
    weight (a missing weight reads as 1)."""
    if not cfg or not cfg.get("mode") or cfg["mode"] == "default":
        return None
    asked, weights = [], {}
    if cfg["mode"] == "single":
        one = cfg.get("source")
        if one is None and cfg.get("sources"):
            one = cfg["sources"][0]
        if one is None:
            return None
        asked, weights = [str(one)], {str(one): 1.0}
    elif cfg["mode"] == "blend":
        named = cfg.get("sources")
        if named is None:
            named = list((cfg.get("weights") or {}).keys())
        for k in named:
            k = str(k)
            w = float((cfg.get("weights") or {}).get(k, 1))
            if not (w > 0) or w == float("inf") or k in weights:
                continue
            asked.append(k)
            weights[k] = w
    else:
        return None
    if not asked:
        return None
    return {"mode": cfg["mode"], "asked": asked, "keys": [s for s in source_order if s in asked],
            "weights": weights}


def ddf_version(values: dict, members: list, weights: dict | None = None) -> dict:
    used = [(s, values[s]) for s in members if values.get(s) is not None]
    if not used:
        return {"value": None, "count": 0, "low_confidence": False, "sources": [],
                "reason": "No source prices this player"}
    if weights is not None:
        # Weighted mean on the Adjusted scale, re-normalised over the sources
        # that price the player (JEG-1044).
        val = fsum_in_order(weights[s] * v for s, v in used) / fsum_in_order(weights[s] for s, _ in used)
    else:
        val = fsum_in_order(v for _, v in used) / len(used)
    thin = len(used) == 1 and (weights is None or len(members) > 1)   # a one-source basis is not "only one source"
    out = {"value": val, "count": len(used), "low_confidence": thin,
           "sources": [s for s, _ in used]}
    if thin:
        out["reason"] = "Only one source prices this player"
    return out


def _override_number(value):
    """JEG-1058: a number or a numeric string, the same set the JS engine's
    normalizeOverride accepts. None when the value cannot be a number."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value) if math.isfinite(value) else None
    if isinstance(value, str):
        if value == "":
            return None
        try:
            text = float(value)
        except ValueError:
            return None
        return text if math.isfinite(text) else None
    return None


def _override_spec(override) -> dict | None:
    """JEG-1058: what the reader set, as one record: {"type": "absolute",
    "value"} or {"type": "adjustment", "delta"}. None when it cannot be used.
    A value past the top of the scale is capped and an adjustment is capped to
    the scale's span, so an override from outside the editor lands on the same
    numbers the editor shows."""
    if override is None or isinstance(override, bool):
        return None
    if isinstance(override, (int, float, str)):
        value = _override_number(override)
        if value is None or value < OVERRIDE_MIN:
            return None
        return {"type": "absolute", "value": min(OVERRIDE_MAX, value)}
    if isinstance(override, dict):
        if override.get("type") == "adjustment":
            delta = _override_number(override.get("delta"))
            if delta is None:
                return None
            return {"type": "adjustment", "delta": min(OVERRIDE_MAX, max(-OVERRIDE_MAX, delta))}
        value = _override_number(override.get("value"))
        if value is None or value < OVERRIDE_MIN:
            return None
        return {"type": "absolute", "value": min(OVERRIDE_MAX, value)}
    return None


def apply_value_overrides(rows: dict, overrides: dict) -> None:
    """JEG-1035 / JEG-1044 / JEG-1058: the reader's per-player DDF Value
    overrides, a row-level overlay applied after the pipeline. It replaces the
    blended DDF value only (JEG-1073: the projections version is a separate
    alternate); Adjusted values, Indexed values, the pie and the charts-only and
    projections versions are never touched. An override is an absolute value or
    an adjustment to the pipeline's own value, clamped to the fixed-pie scale."""
    for k, row in rows.items():
        ov = overrides.get(k)
        for field_ in ("ddf_blended",):
            entry = row[field_]
            entry["pipeline_value"] = entry["value"]
            spec = _override_spec(ov)
            entry["overridden"] = spec is not None
            if spec is None:
                continue
            if spec["type"] == "adjustment":
                base = entry["pipeline_value"]
                base = float(base) if isinstance(base, (int, float)) else 0.0
                entry["value"] = min(OVERRIDE_MAX, max(OVERRIDE_MIN, base + spec["delta"]))
            else:
                entry["value"] = float(spec["value"])
            entry["low_confidence"] = False
            entry.pop("reason", None)


# ---------------------------------------------------------------- one week

def run_week(setting: Setting, pos_of: dict, sources: dict, included: list,
             selection: list | None = None, names: dict | None = None,
             lineup: dict | None = None, hidden: list | None = None,
             promotion_model: bool = True, flex_bench_seats: bool = True,
             basis: dict | None = None) -> dict:
    """VP-2 .. VP-7 for one week.

    basis: JEG-1044, the reader's value basis ({"mode": "single"|"blend", ...});
           None or mode "default" = equal-weight projections. It changes only
           the blended DDF Value (and so the Indexed basis, tiers, ranking);
           allocation, weights, pie and Adjusted values never see it.

    sources: {key: {"family": "projection"|"chart", "values": {player_key: native}}}
             in source-key display order; natives already carry the superflex
             overlay. Every source here is shown (VP-1.4); only `included`
             counts.
    selection: the reader's input selection (VP-1.5); filters DDF averaging only.
    hidden: JEG-569 part 2 / JEG-787.  Sources that are in `included` (so they
            count in allocation, weights and pie) but hidden from the DDF Value
            blend (VP-6.3) and the Indexed basis (VP-6.4).
    """
    hidden_set = set(hidden or ())
    bs = setting.bench_share
    natives = {s: {int(k): float(v) for k, v in src["values"].items()
                   if v is not None and pos_of.get(int(k)) in POS_ORDER}
               for s, src in sources.items()}
    family = {s: src["family"] for s, src in sources.items()}
    inc = [s for s in included if s in sources]
    proj_in = [s for s in inc if family[s] == PROJECTION]
    m = mean_ppg({s: {"family": family[s], "values": natives[s]} for s in sources}, inc, pos_of)
    pie = setting.pie()
    degenerate = not proj_in
    if not degenerate:
        p_order = score_order(m, pos_of)
        alloc = allocate(setting, p_order, m, flex_bench_seats=flex_bench_seats)
        fill_sets = {p: p_order[p][:alloc[p]["rostered"] + 1] for p in POSITIONS}
    else:   # VP-2.2 f (SA-3)
        alloc, fill_sets, p_order = None, None, None
    peers_all = sorted(s for s in inc if family[s] == CHART)
    es = None
    if lineup is not None:
        charts_in = [s for s in inc if family[s] == CHART]
        es = {"teams": setting.teams, "lineup": lineup,
              "chart_sigma": es_chart_sigma(setting, natives, charts_in, pos_of,
                                            flex_bench_seats=flex_bench_seats)}
        bs = setting.bench_share_override

    # JEG-969: promotion/demotion model, off for everyone since JEG-1142
    # (PROMOTION_MODEL_ENABLED master switch).
    promo = None
    if PROMOTION_MODEL_ENABLED and promotion_model and es is not None and lineup is not None:
        promo_cfg = _load_promotion_config()
        season_wks = float(promo_cfg.get("season_weeks", 17))
        window = lineup.get("window")
        if window is not None:
            w0, w1 = window
            weeks_rem = max(0.0, float(w1 - w0 + 1))
        else:
            weeks_rem = season_wks
        promo = {"config": promo_cfg, "weeks_remaining": weeks_rem}

    priced = {}
    for s in sources:
        if degenerate:
            own = score_order(natives[s], pos_of)
            a = allocate(setting, own, natives[s], flex_bench_seats=flex_bench_seats)
        else:
            a = alloc
        peers = [k for k in peers_all if k != s]
        priced[s] = price_source(s, family[s], natives, pos_of, a, fill_sets, peers, m, bs, es, promo)
        priced[s]["status"] = "included" if s in inc else sources[s].get("status", "excluded")
        priced[s]["allocation"] = a
    S_raw, B_raw, bs_star, W = ddf_weights(priced, inc, bs, setting.position_shares)
    for s in sources:
        adjust_source(priced[s], pie, W)

    # rows: every player any source lists (VP-6.1)
    row_keys = sorted({k for s in sources for k in natives[s]})
    sel = set(selection) if selection is not None else None
    # JEG-569 part 2 / JEG-787: hidden sources are in `inc` (so they count in
    # allocation, weights and pie) but excluded from the DDF Value blend and
    # the Indexed basis, matching value-model.js isHidden.
    # JEG-1073 (Jeremy, 2026-10-25): DDF Value = the Adjusted trade charts,
    # equal weight; the projections version is the alternate. Reverses JEG-804.
    proj_members = [s for s in inc if s not in hidden_set and family[s] == PROJECTION and (sel is None or s in sel)]
    # No fallback to the other family: with no chart in I, DDF Value is null.
    blended_members = [s for s in inc if s not in hidden_set and family[s] == CHART and (sel is None or s in sel)]
    blend_weights = None
    asked = normalize_basis(basis, list(sources))
    basis_out = None
    if asked is not None:
        usable = [s for s in asked["keys"] if s in inc and s not in hidden_set]
        basis_out = {"mode": asked["mode"], "requested": list(asked["asked"]), "applied": bool(usable),
                     "members": list(usable), "weights": {s: asked["weights"][s] for s in usable},
                     "fell_back_to_default": not usable}
        if usable:
            blended_members = usable
            blend_weights = asked["weights"]
    members = {
        "blended": blended_members,
        "charts": [s for s in inc if s not in hidden_set and family[s] == CHART],   # JEG-930: charts-only ignores the blend selection
        "projections": proj_members,
    }
    rows = {}
    for k in row_keys:
        p = pos_of[k]
        adj, vorp, est = {}, {}, {}
        for s in sources:
            a_v, path = row_value(priced[s], family[s], k, p, "adjusted")
            v_v, _ = row_value(priced[s], family[s], k, p, "vorp_display")
            adj[s], vorp[s] = a_v, v_v
            if path:
                est[s] = path
        rows[k] = {"name": (names or {}).get(k), "pos": p, "adjusted": adj, "vorp_vs_waivers": vorp,
                   "estimated": est,
                   "ddf_blended": ddf_version(adj, members["blended"], blend_weights),
                   "ddf_charts": ddf_version(adj, members["charts"]),
                   "ddf_projections": ddf_version(adj, members["projections"]),
                   "mean_ppg": m.get(k)}
        shares = [(priced[s]["players"][k]["lineup_share"], priced[s]["players"][k]["start_worthy"])
                  for s in inc if k in priced[s]["players"] and priced[s]["players"][k]["lineup_share"] is not None]
        rows[k]["lineup_share"] = fsum_in_order(a for a, _ in shares) / len(shares) if shares else None
        rows[k]["start_worthy"] = fsum_in_order(b for _, b in shares) / len(shares) if shares else None

    # VP-6.4 Indexed, every chart (held ones too)
    indexed = {}
    for s in sources:
        if family[s] != CHART:
            continue
        r = priced[s]
        shared = [k for k in sorted(natives[s], key=lambda k: (POS_ORDER[pos_of[k]], -natives[s][k], k))
                  if rows[k]["ddf_blended"]["value"] is not None]
        ddf_tot = fsum_in_order(rows[k]["ddf_blended"]["value"] for k in shared)
        nat_tot = fsum_in_order(natives[s][k] for k in shared)
        f = ddf_tot / nat_tot if shared and nat_tot > 0 else None
        vals = {}
        for k in row_keys:
            p = pos_of[k]
            if f is None or r["positions"][p]["method"] == "no_players":
                vals[k] = None    # a null factor nulls the whole chart (VP-6.4, ruling)
            elif k in r["players"]:
                vals[k] = r["players"][k]["native"] * f
            else:
                vals[k] = 0.0     # below rosterable depth (VP-6.2)
        indexed[s] = {"factor": f, "shared_players": len(shared), "ddf_total": ddf_tot,
                      "native_total": nat_tot, "values": vals}
        r["indexed_factor"] = f
        for k in row_keys:
            rows[k].setdefault("indexed", {})[s] = vals[k]

    # VP-7 slot fill and tiers
    if degenerate:
        ddf_scores = {k: rows[k]["ddf_blended"]["value"] for k in row_keys
                      if rows[k]["ddf_blended"]["value"] is not None}
        slot_fill = allocate(setting, score_order(ddf_scores, pos_of), ddf_scores,
                             flex_bench_seats=flex_bench_seats)
    else:
        slot_fill = alloc
    for p in POSITIONS:
        ranked = [k for k in row_keys if pos_of[k] == p and rows[k]["ddf_blended"]["value"] is not None]
        ranked.sort(key=lambda k: (-rows[k]["ddf_blended"]["value"],
                                   0 if k in m else 1, -m.get(k, 0.0), k))
        for rank, k in enumerate(ranked, start=1):
            v = rows[k]["ddf_blended"]["value"]
            if v == 0:
                t = "waiver"
            elif rank <= slot_fill[p]["starters"]:
                t = "starter"
            elif rank <= slot_fill[p]["rostered"]:
                t = "bench"
            else:
                t = "waiver"
            rows[k]["ddf_tier"] = t
    for k in row_keys:
        rows[k].setdefault("ddf_tier", None)
        rows[k].setdefault("indexed", {})
    ranking = sorted(row_keys, key=lambda k: (rows[k]["ddf_blended"]["value"] is None,
                                              -(rows[k]["ddf_blended"]["value"] or 0.0), k))
    budgets = {g: pie * W[g] for g in GROUP_KEYS}
    # ES-14 readout (SA-ES-5): bench tier = ranks S_p+1..N_p of the
    # projected-points order; value = blended DDF Value over I, no selection.
    # JEG-1073: uses the blended DDF Value (now the chart average), matching
    # the engine's indexBasis.
    readout = None
    if not degenerate:
        readout = {"override": (bs is not None) if es is not None else True, "override_value": bs,
                   "fill_in_share": bs_star, "method": "expected-starts" if es is not None else "fixed-share"}
        tb, tt = [], []
        for p in POSITIONS:
            pb, pt = [], []
            for idx, k in enumerate(p_order[p]):
                v = rows[k]["ddf_blended"]["value"]
                if v is None:
                    continue
                pt.append(v)
                if alloc[p]["starters"] <= idx < alloc[p]["rostered"]:
                    pb.append(v)
            b_, t_ = fsum_in_order(pb), fsum_in_order(pt)
            readout[p] = b_ / t_ if t_ > 0 else None
            tb.append(b_)
            tt.append(t_)
        b_, t_ = fsum_in_order(tb), fsum_in_order(tt)
        readout["overall"] = b_ / t_ if t_ > 0 else None
    src_out = {}
    for s in sources:
        r = priced[s]
        src_out[s] = {k: r[k] for k in ("family", "status", "positions", "groups", "total_vorp", "surplus_total",
                                        "players", "weights", "starter_mix", "bench_mix", "rates",
                                        "unfunded_moved", "unfunded_groups", "vorp_display_factor",
                                        "indexed_factor") if k in r}
        if degenerate:
            src_out[s]["allocation"] = r["allocation"]
    return {
        "included": inc,
        "basis": basis_out,
        "hidden": [s for s in inc if s in hidden_set],
        "pie": pie,
        "starting_slots_per_team": setting.starting_slots_per_team(),
        "bench_share_applied": bs_star,
        "bench_share_readout": readout,
        "chart_sigma": es["chart_sigma"] if es is not None else None,
        "mean_ppg": m,
        "allocation": alloc,
        "fill_sets": fill_sets,
        "sources": src_out,
        "starter_mix_mean": S_raw,
        "bench_mix_mean": B_raw,
        "ddf_weights": W,
        "group_budgets": budgets,
        "indexed": indexed,
        "slot_fill_mean_ppg": slot_fill,
        "default_ranking": ranking,
        "rows": rows,
    }


# ---------------------------------------------------------------- VP-8

VERSIONS = (("blended", "ddf_blended"), ("charts", "ddf_charts"), ("projections", "ddf_projections"))


def run(setting: Setting, pos_of: dict, current: dict, prior: dict | None, included: list,
        selection: list | None = None, names: dict | None = None,
        prior_pos_of: dict | None = None, lineup: dict | None = None,
        hidden: list | None = None, promotion_model: bool = True,
        flex_bench_seats: bool = True, basis: dict | None = None) -> dict:
    """Both weeks and the change. `prior` holds only sources with a prior
    snapshot; the prior week uses the same I and setting (VP-8.1)."""
    cur = run_week(setting, pos_of, current, included, selection, names, lineup, hidden=hidden,
                   promotion_model=promotion_model, flex_bench_seats=flex_bench_seats, basis=basis)
    out = {"current": cur, "prior": None}
    if prior:
        prior_src = {s: prior[s] for s in included if s in prior}
        pw = run_week(setting, prior_pos_of or pos_of, prior_src, included, selection, names, lineup, hidden=hidden,
                      promotion_model=promotion_model, flex_bench_seats=flex_bench_seats, basis=basis)
        out["prior"] = pw
        for k, row in cur["rows"].items():
            prow = pw["rows"].get(k)
            for _, field_ in VERSIONS:
                c = row[field_]
                pv = prow[field_] if prow else None
                c["prior"] = pv["value"] if pv else None
                c["prior_count"] = pv["count"] if pv else 0
                c["prior_low_confidence"] = pv["low_confidence"] if pv else False
                c["change"] = (c["value"] - c["prior"]) if (c["value"] is not None and c["prior"] is not None) else None
    return out
