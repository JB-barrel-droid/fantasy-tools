#!/usr/bin/env python3
"""Python reference for every value the page shows: the source-neutral value
pipeline (JEG-508).

Written from docs/methodology.md "Value Pipeline (source-neutral,
2026-10-09)", steps VP-0..VP-12 and the decided OC table, and from nothing
else: not from the browser engine (curve-widget.js / value-model.js) and not
from the clean-room spec reference (pipelines/spec_reference/). The three are
written independently on purpose; pipelines/value_check.py diffs this module
against the engine on every chain run (JEG-479).

Two layers:

  run_pipeline(league, sources, pos_of, included, ...)
      The math, VP-0 to VP-7, on plain inputs: each source's natives
      (points per game for a projection, trade value for a chart), the league
      setting and the included set. tests/test_value_reference_worked_example
      runs it on tests/fixtures/value_pipeline_worked_example.json and checks
      every intermediate to 1e-6.

  Setting / compute(inp, setting)
      The build's inputs (data/fixtures/current/comparison-sources-data.json,
      players.json, the week history in dist/assets/history): which sources
      are eligible and included (VP-1), their natives at the setting, the
      prior week (VP-8), and the page's rows per tab (VP-11) in the shape
      value_check compares.

Every "Lead's reading" in the spec is followed as written. Where this module
had to choose a reading the spec leaves open it says "Reference reading" at
the spot; the list is also on JEG-508 and in docs/claude-log.md.
"""
from __future__ import annotations

import json
import math
import re
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "pipelines"))
sys.path.insert(0, str(REPO / "pipelines" / "lib"))
sys.path.insert(0, str(REPO))

VERSION = "value-reference-002/1"
PIPELINE_VERSION = "value-pipeline/2"
FIXTURE = REPO / "data" / "fixtures" / "current" / "comparison-sources-data.json"
PLAYERS = REPO / "data" / "fixtures" / "current" / "players.json"
HISTORY = REPO / "dist" / "assets" / "history"

# ---------------------------------------------------------------------------
# VP-0 definitions and constants
# ---------------------------------------------------------------------------

POSITIONS = ("QB", "RB", "WR", "TE")
POS_ORDER = {p: i for i, p in enumerate(POSITIONS)}
FLEX_ELIGIBLE = ("RB", "WR", "TE")
BENCH_MIX_12 = {"QB": 10, "RB": 27, "WR": 33, "TE": 10}
IMPUTE_MIN_FIT = 3
ESTIMATE_FIT_N = 10
DEFAULT_BENCH_SHARE = 0.15
PIE_PER_STARTING_SLOT = 28.0
GROUPS = tuple(f"{p}|{r}" for p in POSITIONS for r in ("starter", "bench"))

# The page's sources (VP-0) and series (VP-11).
PUBLISHED = ("usatoday", "fantasycalc", "fantasypros", "cbs")
PROJECTIONS = ("espn", "cbsros", "razzball")
SOURCES = (*PUBLISHED, *PROJECTIONS)          # source-key order
FAMILY = {**{k: "chart" for k in PUBLISHED}, **{k: "projection" for k in PROJECTIONS}}
VORP_KEYS = {"espn_vorp": "espn", "cbsros_vorp": "cbsros", "razzball_vorp": "razzball"}
SERIES_KEYS = (*SOURCES, *VORP_KEYS)
PPG_FIELD = {"espn": "espn_ppg", "cbsros": "cbsros_ppg", "razzball": "rz_ppg"}
VIEWS = ("indexed", "vorp", "adj")
# VP-11: the series drawn in each tab. Projections in the Indexed tab carry
# their Adjusted values (available, off by default, OC-7); in the VORP vs
# waivers tab they are drawn only as *_vorp.
VIEW_SERIES = {
    "indexed": (*PUBLISHED, *PROJECTIONS),
    "vorp": (*PUBLISHED, *VORP_KEYS),
    "adj": (*PUBLISHED, *PROJECTIONS),
}
COMPOSITE_KEY = "ddf_value"
DDF_VERSIONS = {"ddf_value": "blended", "ddf_value_charts": "charts", "ddf_value_projections": "projections"}
DDF_FAMILY = {"blended": None, "charts": "chart", "projections": "projection"}
DDF_COUNT_FIELD = {"ddf_value": "ddf_count", "ddf_value_charts": "ddf_charts_count",
                   "ddf_value_projections": "ddf_projections_count"}

SCORINGS = ("standard", "half_ppr", "ppr")
TEAM_COUNTS = (8, 10, 12, 14)
COMBO_PREFIX = {"ppr": "full", "half_ppr": "half", "standard": "standard"}
HISTORY_SCORING_INDEX = {"standard": 0, "half_ppr": 1, "ppr": 2}
QB_AWARE = frozenset({"fantasycalc"})
DEFAULT_ROSTER = {"QB": 1, "RB": 2, "WR": 3, "TE": 1, "FLEX": 1, "SUPERFLEX": 0, "BENCH": 6}
SAVED_TEAMS = 12
HOLD_FIELDS = ("validationHold", "promotionHold")


def roster(superflex: int = 0) -> dict:
    return {**DEFAULT_ROSTER, "SUPERFLEX": int(superflex)}


def settings(superflex_too: bool = True) -> list[dict]:
    """The settings every chain run compares: 3 scorings x 4 team counts on
    the default roster, plus the same with one superflex slot."""
    out = []
    for sf in ((0, 1) if superflex_too else (0,)):
        for scoring in SCORINGS:
            for teams in TEAM_COUNTS:
                out.append({"scoring": scoring, "teams": teams, "superflex": sf})
    return out


def setting_id(s: dict) -> str:
    return f"{s['scoring']}/{s['teams']}/sf{s['superflex']}"


def _finite(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _num(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def round_half_up(x: float) -> int:
    return int(math.floor(x + 0.5))


def median(values: list[float]) -> float:
    s = sorted(values)
    n = len(s)
    mid = n // 2
    return s[mid] if n % 2 else (s[mid - 1] + s[mid]) / 2.0


@dataclass
class League:
    """League setting L (VP-0)."""
    teams: int
    slots: dict                      # dedicated slots per team, D_p
    flex: int = 1                    # F (RB/WR/TE)
    superflex: int = 0               # SF (QB/RB/WR/TE)
    bench: int = 6                   # B
    bench_share: float = DEFAULT_BENCH_SHARE
    flex_eligible: tuple = FLEX_ELIGIBLE
    position_shares: dict | None = None   # reader position shares (VP-4.4)
    bench_share_override: float | None = None   # ES-14: the reader's override, off by default

    @property
    def starting_slots(self) -> int:
        return sum(int(self.slots.get(p, 0)) for p in POSITIONS) + int(self.flex) + int(self.superflex)

    @property
    def pie(self) -> float:
        """VP-5.1 (OC-1): 28 per starting slot."""
        return PIE_PER_STARTING_SLOT * self.teams * self.starting_slots


@dataclass
class SourceInput:
    key: str
    family: str                      # "projection" | "chart"
    values: dict                     # {player_key: native}; a finite native = listed
    label: str = ""

    def __post_init__(self):
        self.label = self.label or self.key


# ---------------------------------------------------------------------------
# VP-2.2 league allocation
# ---------------------------------------------------------------------------

def bench_seats(total: int) -> dict:
    """VP-2.2d: D'Hondt over BENCH_MIX_12; ties go to position order."""
    seats = {p: 0 for p in POSITIONS}
    for _ in range(max(0, total)):
        best = max(POSITIONS, key=lambda p: (BENCH_MIX_12[p] / (seats[p] + 1), -POS_ORDER[p]))
        seats[best] += 1
    return seats


def allocate(league: League, order: dict, score: dict) -> dict:
    """VP-2.2 a-e on per-position orders (best first) and a score per
    player (mean points per game, or a source's own natives in the
    degenerate week, or blended DDF Value for VP-7.2's degenerate slot fill)."""
    t = int(league.teams)
    d = {p: t * int(league.slots.get(p, 0)) for p in POSITIONS}

    def take(cands, n):
        cands.sort(key=lambda c: (-score[c[1]], POS_ORDER[c[0]], c[1]))
        got = {p: 0 for p in POSITIONS}
        for p, _i in cands[:max(0, n)]:
            got[p] += 1
        return got

    sf = take([(p, i) for p in POSITIONS for idx, i in enumerate(order.get(p, [])) if idx >= d[p]],
              t * int(league.superflex))
    fx = take([(p, i) for p in POSITIONS if p in league.flex_eligible
               for idx, i in enumerate(order.get(p, [])) if idx >= d[p] + sf[p]],
              t * int(league.flex))
    b = bench_seats(round_half_up(t * league.bench))
    out = {}
    for p in POSITIONS:
        s = d[p] + sf[p] + fx[p]
        out[p] = {"dedicated": d[p], "superflex": sf[p], "flex": fx[p], "bench": b[p],
                  "starters": s, "rostered": s + b[p]}
    return out


# ---------------------------------------------------------------------------
# VP-2.4 fill-in of rosterable players a chart does not list
# ---------------------------------------------------------------------------

def _estimate(c: SourceInput, i: int, c_order_p: list, peers: list, m: dict) -> dict:
    """One estimate for chart c, player i at position p (VP-2.4 c-g).
    c_order_p: c's listed players at p in c's sort order."""
    cv = c.values
    cap = cv[c_order_p[-1]]           # lowest listed native at p
    peer_info, ests = {}, []
    for k in peers:
        kv = k.values
        if i not in kv:
            continue
        shared = [j for j in c_order_p if j in kv]
        n_fit = min(ESTIMATE_FIT_N, len(shared))
        fit = shared[len(shared) - n_fit:] if n_fit else []
        num = 0.0
        den = 0.0
        for j in fit:
            num += cv[j]
            den += kv[j]
        entry = {"usable": False, "fit_players": list(fit), "num": num, "den": den}
        if len(fit) >= IMPUTE_MIN_FIT and den > 0:
            ratio = num / den
            est = ratio * kv[i]
            entry.update({"usable": True, "ratio": ratio, "peer_native": kv[i], "estimate": est})
            ests.append(est)
        peer_info[k.key] = entry
    out = {"peers": peer_info, "cap": cap}
    if ests:
        out["path"] = "peers"
        raw = median(ests)
    else:
        # Curve path: no chart lists him, or none that does is usable.
        out["path"] = "curve"
        pts_all = [j for j in c_order_p if j in m]
        n_pts = min(ESTIMATE_FIT_N, len(pts_all))
        pts = pts_all[len(pts_all) - n_pts:] if n_pts else []
        if len(pts) >= IMPUTE_MIN_FIT and len({m[j] for j in pts}) > 1:
            n = len(pts)
            mean_m = sum(m[j] for j in pts) / n
            mean_x = sum(cv[j] for j in pts) / n
            sxy = sum((m[j] - mean_m) * (cv[j] - mean_x) for j in pts)
            sxx = sum((m[j] - mean_m) ** 2 for j in pts)
            slope = sxy / sxx
            intercept = mean_x - slope * mean_m
            raw = intercept + slope * m[i]
            out["curve"] = {"points": pts, "slope": slope, "intercept": intercept, "mean_ppg": m[i]}
        else:
            positive = [j for j in c_order_p if j in m and m[j] > 0]
            if positive:
                low = positive[-1]
                raw = cv[low] * m[i] / m[low]
                out["curve"] = {"points": pts, "low": low, "mean_ppg": m[i]}
            else:
                raw = 0.0
                out["curve"] = {"points": pts, "low": None, "mean_ppg": m[i]}
    out["raw"] = raw
    out["value"] = min(max(raw, 0.0), cap)
    out["capped"] = raw > cap
    return out


# ---------------------------------------------------------------------------
# Expected starts (docs/methodology.md ES-0..ES-15; JEG-536, es-value-001)
# ---------------------------------------------------------------------------
# With `lineup` (resolved parameters, derive_lineup_parameters.resolve) the two
# parts of ES-5 replace the VP-2.6 slices and the bench share is an output;
# without it the pipeline is VP-2.6 at the bench share, unchanged.

LINEUP_CONFIG = REPO / "config" / "lineup_parameters.json"
CHART_SIGMA_DEFAULT = 0.2
CHART_COMMON_TOTAL = 1000.0


def load_lineup_config(path: Path = LINEUP_CONFIG) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def resolve_lineup(cfg: dict, **settings) -> dict:
    """ES-14: reader settings -> parameters. The Python reference is
    derive_lineup_parameters.resolve; this is a thin pass-through."""
    import derive_lineup_parameters as dl
    return dl.resolve(cfg, **settings)


def _norm_cdf(z: float) -> float:
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def _p_between(mu: float, sd: float, lo: float, hi: float) -> float:
    """P(lo < X <= hi), X ~ N(mu, sd); point mass at sd = 0; hi may be inf."""
    if hi <= lo:
        return 0.0
    if sd <= 0:
        return 1.0 if lo < mu <= hi else 0.0
    upper = 1.0 if math.isinf(hi) else _norm_cdf((hi - mu) / sd)
    return upper - _norm_cdf((lo - mu) / sd)


def _at_least(n: int, q: float, k: int) -> float:
    """P(Binomial(n, q) >= k)."""
    if k <= 0:
        return 1.0
    if n <= 0 or k > n:
        return 0.0
    return sum(math.comb(n, j) * q ** j * (1.0 - q) ** (n - j) for j in range(k, n + 1))


def chart_sigma(league: League, sources: dict, chart_keys: list, pos_of: dict) -> dict:
    """ES-15.3: the chart family's relative spread per position, on the
    included charts' listed natives put on one common scale."""
    import statistics
    lists = [sources[k].values for k in chart_keys]
    shared = set.intersection(*(set(v) for v in lists)) if lists else set()
    factors = []
    for v in lists:
        tot = sum(v[i] for i in sorted(shared))
        factors.append(CHART_COMMON_TOTAL / tot if tot > 0 else 1.0)
    seats = bench_seats(round_half_up(league.teams * league.bench))
    out = {}
    for p in POSITIONS:
        acc = {}
        for v, f in zip(lists, factors):
            for i, x in v.items():
                if pos_of.get(i) == p:
                    acc.setdefault(i, []).append(x * f)
        rows = sorted(((statistics.mean(xs), statistics.stdev(xs), i) for i, xs in acc.items() if len(xs) >= 2),
                      key=lambda r: (-r[0], r[2]))
        dedicated = league.teams * int(league.slots.get(p, 0))
        extra = league.teams * int(league.superflex) + (
            league.teams * int(league.flex) if p in league.flex_eligible else 0)
        starters = dedicated + min(extra, max(0, len(rows) - dedicated))
        rostered = starters + seats[p]
        band = [r for r in rows[starters // 2:rostered] if r[0] > 0]
        out[p] = {"sigma_rel": median([sd / mu for mu, sd, _ in band]) if band else CHART_SIGMA_DEFAULT,
                  "players": len(rows), "band": len(band), "shared_players": len(shared),
                  "starters": starters, "rostered": rostered}
    return out


def _expected_start_parts(xs: list, starters: int, teams: int, w: float, line: float, m_p: float,
                          bye: float, sig_rel: float, sig_floor: float) -> dict:
    """ES-3 / ES-4 on one work list (values best first)."""
    avail = (1.0 - bye) * (1.0 - m_p)
    q = bye + (1.0 - bye) * m_p
    n_team = max(1, round(starters / teams)) if teams else 1
    edges = [line]
    k = 1
    while teams:
        j = starters + k * teams
        if j >= len(xs) or xs[j] <= w:
            break
        edges.append(xs[j])
        k += 1
    bands = [{"depth": d, "lo": edges[d], "hi": edges[d - 1], "fill": _at_least(n_team, q, d)}
             for d in range(1, len(edges))]
    bands.append({"depth": len(edges), "lo": w, "hi": edges[-1], "fill": _at_least(n_team, q, len(edges))})
    parts = []
    for x in xs:
        sd = max(sig_rel * x, sig_floor) if x > 0 else sig_floor
        v = max(0.0, x - w)
        p_start = _p_between(x, sd, line, math.inf)
        p_fill = 0.0
        for b in bands:
            p_fill += b["fill"] * _p_between(x, sd, b["lo"], b["hi"])
        parts.append({"start_worthy": p_start, "lineup_share": avail * (p_start + p_fill),
                      "start_worthy_part": avail * (v * p_start), "fill_in_part": avail * (v * p_fill)})
    return {"avail": avail, "unavailable": q, "n_per_team": n_team, "bands": bands, "parts": parts}


# ---------------------------------------------------------------------------
# VP-2 .. VP-5 for one source
# ---------------------------------------------------------------------------

def _source_lines(src: SourceInput, pos_of: dict, alloc: dict, estimates: dict,
                  es: dict | None = None) -> dict:
    """VP-2.3, 2.5, 2.6 and VP-3.1: work lists, waiver and starter lines,
    slices (or, with `es` = {teams, lineup, chart_sigma}, the ES-5 parts)
    and the 8 group totals."""
    positions, players = {}, {}
    groups = {g: 0.0 for g in GROUPS}
    surplus = 0.0
    for p in POSITIONS:
        a = alloc[p]
        listed = [(i, x, False) for i, x in src.values.items() if pos_of.get(i) == p]
        est = [(i, e["value"], True) for i, e in (estimates.get(p) or {}).items()]
        work = sorted(listed + est, key=lambda r: (-r[1], r[2], r[0]))
        n_rost, n_start = a["rostered"], a["starters"]
        info = {**a, "listed": len(listed), "extended": bool(est),
                "imputation_ratios": dict(estimates.get(p) or {}) or None}
        if len(work) > n_rost:
            w = work[n_rost][1]
            method = "estimated" if work[n_rost][2] else "roster_determined"
        elif work:
            w = work[-1][1]
            method = "insufficient_coverage"
        else:
            info.update({"waiver_value": None, "starter_line": None, "method": "no_players"})
            positions[p] = info
            continue
        line = work[n_start][1] if len(work) > n_start else w
        line = max(line, w)
        info.update({"waiver_value": w, "starter_line": line, "method": method})
        parts = None
        if es is not None:
            lp = es["lineup"]["positions"][p]
            if src.family == "chart":
                sig_rel = es["chart_sigma"][p]["sigma_rel"] * es["lineup"].get("projection_confidence", 1.0)
                sig_floor = 0.0
            else:
                sig_rel, sig_floor = lp["sigma_rel"], lp["sigma_floor"]
            got = _expected_start_parts([r[1] for r in work], n_start, es["teams"], w, line, lp["m"],
                                        es["lineup"]["bye"], sig_rel, sig_floor)
            parts = got["parts"]
            info.update({"avail": got["avail"], "bands": got["bands"],
                         "lineup": {"m": lp["m"], "unavailable": got["unavailable"],
                                    "n_per_team": got["n_per_team"], "sigma_rel": sig_rel,
                                    "sigma_floor": sig_floor}})
        positions[p] = info
        g_s = g_b = v_sum = 0.0
        for rank, (i, x, is_est) in enumerate(work, start=1):
            v = max(0.0, x - w)
            role = "starter" if rank <= n_start else "bench" if rank <= n_rost else "waiver"
            rec = {"pos": p, "native": x, "imputed": is_est, "rank": rank, "role": role, "vorp": v,
                   "lineup_share": None, "start_worthy": None}
            if parts is not None:
                pt = parts[rank - 1]
                bsl, ssl = pt["fill_in_part"], pt["start_worthy_part"]   # ES-5: bsl := fi, ssl := sw
                rec.update({"lineup_share": pt["lineup_share"], "start_worthy": pt["start_worthy"]})
            else:
                bsl = max(0.0, min(x, line) - w)
                ssl = max(0.0, x - line)
            rec.update({"bench_slice": bsl, "starter_slice": ssl})
            players[i] = rec
            g_s += ssl
            g_b += bsl
            v_sum += v
        groups[f"{p}|starter"] = g_s
        groups[f"{p}|bench"] = g_b
        surplus += v_sum
    return {"positions": positions, "players": players, "groups": groups, "surplus_total": surplus}


def _mixes(groups: dict, bench_share: float | None) -> dict:
    """VP-3.2 - 3.4: mixes and the source's own weights. bench_share None
    (expected starts, no override; ES-15.1): each group's share of the
    source's parts."""
    total = sum(groups[g] for g in GROUPS)
    s_tot = sum(groups[f"{p}|starter"] for p in POSITIONS)
    b_tot = sum(groups[f"{p}|bench"] for p in POSITIONS)
    sig = {p: groups[f"{p}|starter"] / s_tot for p in POSITIONS} if s_tot > 0 else None
    beta = {p: groups[f"{p}|bench"] / b_tot for p in POSITIONS} if b_tot > 0 else None
    weights = None
    if total > 0:
        weights = {}
        for p in POSITIONS:
            if bench_share is None:
                ws, wb = groups[f"{p}|starter"] / total, groups[f"{p}|bench"] / total
            elif sig is not None and beta is not None:
                ws, wb = (1 - bench_share) * sig[p], bench_share * beta[p]
            elif sig is not None:
                ws, wb = sig[p], 0.0
            else:
                ws, wb = 0.0, beta[p]
            weights[f"{p}|starter"], weights[f"{p}|bench"] = ws, wb
    return {"total_vorp": total, "starter_mix": sig, "bench_mix": beta, "weights": weights}


def ddf_weights(league: League, details: dict, included: list, computed_share: bool = False) -> dict:
    """VP-4: the average of the included sources' mixes, bench fixed at bs.
    computed_share (ES-15.1): the mean of the sources' own 8-group weights,
    renormalized; the bench share applied is then an output."""
    s_raw, b_raw = {}, {}
    for p in POSITIONS:
        sv, bv = [], []
        for k in included:
            d = details[k]
            if d["weights"] is None or d["positions"][p]["method"] == "no_players":
                continue
            if d["starter_mix"] is not None:
                sv.append(d["starter_mix"][p])
            if d["bench_mix"] is not None:
                bv.append(d["bench_mix"][p])
        s_raw[p] = sum(sv) / len(sv) if sv else 0.0
        b_raw[p] = sum(bv) / len(bv) if bv else 0.0
    s_sum, b_sum = sum(s_raw.values()), sum(b_raw.values())
    w = {}
    if computed_share:
        raw = {}
        for p in POSITIONS:
            for r in ("starter", "bench"):
                g = f"{p}|{r}"
                vals = [details[k]["weights"][g] for k in included
                        if details[k]["weights"] is not None and details[k]["positions"][p]["method"] != "no_players"]
                raw[g] = sum(vals) / len(vals) if vals else 0.0
        tot = sum(raw[g] for g in GROUPS)
        w = {g: (raw[g] / tot if tot > 0 else 0.0) for g in GROUPS}
        bs_eff = sum(w[f"{p}|bench"] for p in POSITIONS)
    else:
        bs = league.bench_share
        if s_sum > 0 and b_sum > 0:
            bs_eff = bs
        elif b_sum == 0:
            bs_eff = 0.0
        else:
            bs_eff = 1.0
        for p in POSITIONS:
            w[f"{p}|starter"] = (1 - bs_eff) * s_raw[p] / s_sum if s_sum > 0 else 0.0
            w[f"{p}|bench"] = bs_eff * b_raw[p] / b_sum if b_sum > 0 else 0.0
    if league.position_shares:
        for p in POSITIONS:
            share = league.position_shares.get(p)
            tot = w[f"{p}|starter"] + w[f"{p}|bench"]
            if share is None or tot == 0:
                continue
            for r in ("starter", "bench"):
                w[f"{p}|{r}"] = w[f"{p}|{r}"] * share / tot
    return {"starter_mix_mean": s_raw, "bench_mix_mean": b_raw, "bench_share_applied": bs_eff, "weights": w}


def _price(detail: dict, budgets: dict, pie: float) -> None:
    """VP-5.3 - 5.6 for one source, in place."""
    g = detail["groups"]
    b2 = dict(budgets)
    moved, unpaid = [], []
    for p in POSITIONS:
        for r, o in (("starter", "bench"), ("bench", "starter")):
            gk, ok = f"{p}|{r}", f"{p}|{o}"
            if g[gk] == 0 and budgets[gk] > 0:
                if g[ok] > 0:
                    b2[ok] += budgets[gk]
                    b2[gk] = 0.0
                    moved.append(gk)
                else:
                    unpaid.append(gk)
    rates = {k: (b2[k] / g[k] if g[k] > 0 else 0.0) for k in GROUPS}
    total = detail["total_vorp"]
    surplus = detail.get("surplus_total", total)
    # VP-5.6 / ES-15.4: the display factor scales the surplus to the pie.
    factor = pie / surplus if total > 0 and surplus > 0 else 0.0
    for pl in detail["players"].values():
        if total > 0:
            pl["adjusted"] = (rates[f"{pl['pos']}|bench"] * pl["bench_slice"]
                              + rates[f"{pl['pos']}|starter"] * pl["starter_slice"])
            pl["vorp_display"] = pl["vorp"] * factor
        else:
            pl["adjusted"] = 0.0
            pl["vorp_display"] = 0.0
    detail.update({"rates": rates, "budgets_paid": b2, "unfunded_moved": moved, "unfunded_groups": unpaid,
                   "vorp_display_factor": factor})


# ---------------------------------------------------------------------------
# The pipeline
# ---------------------------------------------------------------------------

def mean_ppg(sources: dict, included: list) -> dict:
    """VP-0 m_i: mean native of the projections in I that list i."""
    projs = [sources[k] for k in included if sources[k].family == "projection"]
    keys = set()
    for s in projs:
        keys.update(s.values)
    m = {}
    for i in sorted(keys):
        vals = [s.values[i] for s in projs if i in s.values]
        m[i] = sum(vals) / len(vals)
    return m


def run_pipeline(league: League, sources: dict, pos_of: dict, included: list,
                 selection: list | None = None, lineup: dict | None = None) -> dict:
    """VP-1.3 .. VP-7 at one setting and week.

    sources: {key: SourceInput} in source-key order, every source shown (held
    and unpublished ones too); included: the keys in I; selection: the
    reader's DDF input selection (VP-1.5), None = all.
    """
    pos_of = {i: p for i, p in pos_of.items() if p in POSITIONS}
    for s in sources.values():
        s.values = {i: float(x) for i, x in s.values.items() if _finite(x) and i in pos_of}
    inc = [k for k in sources if k in set(included)]
    m = mean_ppg(sources, inc)
    degenerate = not any(sources[k].family == "projection" for k in inc)
    order_m = {p: sorted((i for i in m if pos_of[i] == p), key=lambda i: (-m[i], i)) for p in POSITIONS}

    alloc = None if degenerate else allocate(league, order_m, m)
    fill_sets = {} if degenerate else {p: order_m[p][:alloc[p]["rostered"] + 1] for p in POSITIONS}
    chart_peers = [sources[k] for k in inc if sources[k].family == "chart"]
    es = None
    if lineup is not None:
        es = {"teams": int(league.teams), "lineup": lineup,
              "chart_sigma": chart_sigma(league, sources, [k.key for k in chart_peers], pos_of)}
    share_in = league.bench_share
    if es is not None:
        share_in = league.bench_share_override   # None = computed (ES-14)

    details = {}
    for key, src in sources.items():
        own_order = {p: sorted((i for i in src.values if pos_of[i] == p), key=lambda i: (-src.values[i], i))
                     for p in POSITIONS}
        s_alloc = alloc if alloc is not None else allocate(league, own_order, src.values)
        estimates = {}
        if src.family == "chart" and not degenerate:
            peers = [k for k in chart_peers if k.key != key]
            for p in POSITIONS:
                if not own_order[p]:
                    continue
                est = {}
                for i in fill_sets[p]:
                    if i not in src.values:
                        est[i] = _estimate(src, i, own_order[p], peers, m)
                if est:
                    estimates[p] = est
        d = _source_lines(src, pos_of, s_alloc, estimates, es)
        d.update(_mixes(d["groups"], share_in))
        d.update({"family": src.family, "status": "included" if key in inc else "excluded",
                  "allocation": s_alloc})
        details[key] = d

    if es is not None and share_in is not None:
        league = League(**{**league.__dict__, "bench_share": share_in})
    wts = ddf_weights(league, details, inc, computed_share=es is not None and share_in is None)
    pie = league.pie
    budgets = {g: pie * wts["weights"][g] for g in GROUPS}
    for d in details.values():
        _price(d, budgets, pie)

    rows = _rows(sources, details, pos_of, inc, selection, m)
    for i, r in rows.items():
        by_src = {k: details[k]["players"][i]["lineup_share"] for k in sources
                  if i in details[k]["players"] and details[k]["players"][i]["lineup_share"] is not None}
        in_i = [k for k in inc if k in by_src]
        r["lineup_share_by_source"] = by_src
        r["lineup_share"] = sum(by_src[k] for k in in_i) / len(in_i) if in_i else None
        r["start_worthy"] = (sum(details[k]["players"][i]["start_worthy"] for k in in_i) / len(in_i)
                             if in_i else None)
    if degenerate:
        blended = {i: r["ddf"]["blended"]["value"] for i, r in rows.items()}
        scored = {i: v for i, v in blended.items() if v is not None}
        order_d = {p: sorted((i for i in scored if pos_of[i] == p), key=lambda i: (-scored[i], i))
                   for p in POSITIONS}
        slot_fill = allocate(league, order_d, scored)
    else:
        slot_fill = alloc
    _tiers(rows, slot_fill, m)
    indexed = _indexed(sources, details, rows)
    readout = None if degenerate else bench_share_readout(rows, order_m, alloc, inc, es is not None,
                                                         share_in, wts["bench_share_applied"])
    ranking = sorted(rows, key=lambda i: (rows[i]["ddf"]["blended"]["value"] is None,
                                          -(rows[i]["ddf"]["blended"]["value"] or 0.0), i))
    return {
        "included": inc, "degenerate": degenerate, "pie": pie,
        "starting_slots_per_team": league.starting_slots,
        "bench_share": league.bench_share, "bench_share_applied": wts["bench_share_applied"],
        "method": "expected-starts" if es is not None else "slices",
        "bench_share_readout": readout, "bench_share_override": share_in if es is not None else None,
        "chart_sigma": es["chart_sigma"] if es is not None else None, "lineup": lineup,
        "mean_ppg": m, "allocation": alloc, "fill_sets": fill_sets, "slot_fill": slot_fill,
        "sources": details, "starter_mix_mean": wts["starter_mix_mean"],
        "bench_mix_mean": wts["bench_mix_mean"], "ddf_weights": wts["weights"],
        "group_budgets": budgets, "indexed": indexed, "rows": rows, "default_ranking": ranking,
    }


def bench_share_readout(rows: dict, order_m: dict, alloc: dict, inc: list, expected_starts: bool,
                        override, applied: float) -> dict:
    """ES-14: the bench tier's share (ranks S_p+1..N_p on the projected-points
    order) of each position's blended DDF Value over I and of the whole."""
    out = {"override": (override is not None) if expected_starts else True,
           "override_value": override, "fill_in_share": applied,
           "method": "expected-starts" if expected_starts else "fixed-share"}
    bench_all = total_all = 0.0
    for p in POSITIONS:
        bench = total = 0.0
        for idx, i in enumerate(order_m[p]):
            vals = [rows[i]["adjusted"][k] for k in inc if rows[i]["adjusted"].get(k) is not None]
            if not vals:
                continue
            v = sum(vals) / len(vals)
            total += v
            if alloc[p]["starters"] <= idx < alloc[p]["rostered"]:
                bench += v
        out[p] = bench / total if total > 0 else None
        bench_all += bench
        total_all += total
    out["overall"] = bench_all / total_all if total_all > 0 else None
    return out


def row_value(src: SourceInput, detail: dict, i: int, pos: str, field_name: str):
    """VP-6.2: (value, reason) of source src for player i in one view field
    ("adjusted" or "vorp_display")."""
    pl = detail["players"].get(i)
    if pl is not None:
        return pl[field_name], None
    if detail["positions"][pos]["method"] == "no_players":
        return None, f"{src.label} doesn't price {pos}"
    if src.family == "chart":
        return 0.0, f"Below rosterable depth; {src.label} doesn't list him"
    return None, f"{src.label} doesn't project this player"


def _ddf(values: dict, keys: list) -> dict:
    used = [k for k in keys if values.get(k) is not None]
    if not used:
        return {"value": None, "count": 0, "low_confidence": False, "sources": [],
                "reason": "No source prices this player"}
    total = 0.0
    for k in used:
        total += values[k]
    n = len(used)
    return {"value": total / n, "count": n, "low_confidence": n == 1, "sources": used,
            "reason": "Only one source prices this player" if n == 1 else None}


def _rows(sources: dict, details: dict, pos_of: dict, inc: list, selection, m: dict) -> dict:
    """VP-6.1 - 6.3: one row per player any source lists."""
    universe = set()
    for s in sources.values():
        universe.update(s.values)
    sel = set(selection) if selection is not None else None
    rows = {}
    for i in sorted(universe):
        pos = pos_of[i]
        adj, vorp, reasons, est = {}, {}, {}, {}
        for key, src in sources.items():
            d = details[key]
            adj[key], why = row_value(src, d, i, pos, "adjusted")
            vorp[key], _ = row_value(src, d, i, pos, "vorp_display")
            if why:
                reasons[key] = why
            pl = d["players"].get(i)
            if pl is not None and pl["imputed"]:
                e = d["positions"][pos]["imputation_ratios"][i]
                est[key] = e["path"]
        ddf = {}
        for version, fam in DDF_FAMILY.items():
            keys = [k for k in inc if (fam is None or sources[k].family == fam) and (sel is None or k in sel)]
            ddf[version] = _ddf(adj, keys)
        if not inc:
            for v in ddf.values():
                v["reason"] = "No source available this week"
        rows[i] = {"pos": pos, "adjusted": adj, "vorp_vs_waivers": vorp, "estimated": est,
                   "reasons": reasons, "ddf": ddf, "mean_ppg": m.get(i), "indexed": {}}
    return rows


def _tiers(rows: dict, slot_fill: dict, m: dict) -> None:
    """VP-7.3 ddfTier."""
    for p in POSITIONS:
        ranked = [i for i, r in rows.items() if r["pos"] == p and r["ddf"]["blended"]["value"] is not None]
        ranked.sort(key=lambda i: (-rows[i]["ddf"]["blended"]["value"], m.get(i) is None,
                                   -(m.get(i) or 0.0), i))
        for rank, i in enumerate(ranked, start=1):
            v = rows[i]["ddf"]["blended"]["value"]
            if v == 0:
                tier = "waiver"
            elif rank <= slot_fill[p]["starters"]:
                tier = "starter"
            elif rank <= slot_fill[p]["rostered"]:
                tier = "bench"
            else:
                tier = "waiver"
            rows[i]["ddf_tier"] = tier
    for r in rows.values():
        r.setdefault("ddf_tier", None)


def _indexed(sources: dict, details: dict, rows: dict) -> dict:
    """VP-6.4: one factor per chart over its listed players with a numeric
    blended DDF Value (zeros included, OC-8)."""
    out = {}
    for key, src in sources.items():
        if src.family != "chart":
            continue
        d = details[key]
        listed = sorted(src.values, key=lambda i: (-src.values[i], i))
        shared = [i for i in listed if rows[i]["ddf"]["blended"]["value"] is not None]
        ddf_total = 0.0
        nat_total = 0.0
        for i in shared:
            ddf_total += rows[i]["ddf"]["blended"]["value"]
            nat_total += src.values[i]
        # Null when nothing is shared or either sum is <= 0 (spec PR #484);
        # then the chart's whole Indexed column is null, below-depth included.
        factor = ddf_total / nat_total if shared and nat_total > 0 and ddf_total > 0 else None
        values = {}
        for i, r in rows.items():
            pl = d["players"].get(i)
            if factor is None:
                v = None
            elif pl is not None:
                v = pl["native"] * factor
            elif d["positions"][r["pos"]]["method"] == "no_players":
                v = None
            else:
                v = 0.0
            values[i] = v
            r["indexed"][key] = v
            if factor is None:
                r["reasons"].setdefault(f"{key}:indexed", "Not enough shared players to index")
        out[key] = {"factor": factor, "shared_players": len(shared), "ddf_total": ddf_total,
                    "native_total": nat_total, "values": values}
    return out


# ---------------------------------------------------------------------------
# The build's inputs
# ---------------------------------------------------------------------------

def espn_projects_zero(p: dict) -> bool:
    if p.get("espn_status") == "ineligible":
        return True
    if p.get("espn_status") == "absent":
        return False
    ppg = p.get("espn_ppg")
    if not isinstance(ppg, dict) or not ppg:
        return False
    return all(_finite(v) and v == 0 for v in ppg.values())


@dataclass
class Inputs:
    fixture: dict
    players: dict          # player_key -> player dict (QB/RB/WR/TE, named)
    key_of: dict           # fixture slug -> player_key
    today: date
    held: dict = field(default_factory=dict)  # section -> reason (explicit holds)

    @classmethod
    def load(cls, fixture=FIXTURE, players=PLAYERS, today: date | None = None, **_ignored):
        fx = json.loads(Path(fixture).read_text(encoding="utf-8"))
        pl = json.loads(Path(players).read_text(encoding="utf-8"))
        canon = {}
        for p in pl.get("players") or []:
            try:
                key = int(p.get("player_key"))
            except (TypeError, ValueError):
                continue
            if isinstance(p.get("player_key"), bool) or float(p.get("player_key")) != key:
                continue
            name = str(p.get("full_name") or p.get("name") or "").strip()
            if not name or p.get("pos") not in POSITIONS:
                continue
            canon[key] = {
                "player_key": key, "name": name, "pos": p["pos"],
                "espn_ppg": p.get("espn_ppg") or None, "rz_ppg": p.get("rz_ppg") or None,
                "cbsros_ppg": p.get("cbsros_ppg") or None,
                "espn_zero": espn_projects_zero(p),
            }
        key_of = {}
        for slug, k in (fx.get("player_keys") or {}).items():
            n = _num(k)
            if n is not None and n == int(n):
                key_of[slug] = int(n)
        return cls(fx, canon, key_of, today or datetime.now(timezone.utc).date(), {})

    def section(self, source: str) -> dict | None:
        sec = (self.fixture.get("sources") or {}).get(source)
        return sec if isinstance(sec, dict) else None

    def cell(self, source: str, scoring: str, teams: int, view: str = "native") -> dict | None:
        combo_key = f"{COMBO_PREFIX[scoring]}_{teams}" + ("_qb1" if source in QB_AWARE else "")
        combo = ((self.section(source) or {}).get("combos") or {}).get(combo_key)
        if not combo:
            return None
        raw = combo.get(view) if view != "values" else (combo.get("values") or combo.get("reindexed"))
        if not raw:
            return None
        out = {}
        for slug, value in raw.items():
            key = self.key_of.get(slug)
            v = _num(value)
            if key is None or v is None or key not in self.players:
                continue
            out[key] = v
        return {"values": out}

    def ppg(self, key: int, field_name: str, scoring: str):
        v = (self.players[key].get(field_name) or {}).get(scoring)
        return float(v) if _finite(v) else None


# ---------------------------------------------------------------------------
# Content weeks (Tuesday flip, pipelines/nfl_week.py) and holds (VP-1.1)
# ---------------------------------------------------------------------------

def section_week(section: dict | None, today: date) -> tuple[int | None, bool]:
    """(content week, weekly?) of a fixture section."""
    from nfl_week import current_nfl_week
    if not isinstance(section, dict):
        return None, False
    for f in ("week_designated", "content_vintage"):
        mt = re.search(r"week\s*(\d+)|wk\s*(\d+)", str(section.get(f) or ""), re.I)
        if mt:
            return int(mt.group(1) or mt.group(2)), True
    for f in ("content_vintage", "vintage", "published", "fetched_at"):
        mt = re.match(r"(\d{4})-(\d{2})-(\d{2})", str(section.get(f) or ""))
        if mt:
            d = date(int(mt.group(1)), int(mt.group(2)), int(mt.group(3)))
            return current_nfl_week(d), f == "content_vintage"
    return None, False


def freshness(inp: Inputs) -> dict:
    """{"current_week", "reference_week", "series": {source: {week, weekly,
    older, first_load_excluded}}}. Only charts are weekly; projections are
    rest-of-season and always current."""
    from nfl_week import current_nfl_week
    current = current_nfl_week(inp.today)
    rows = {}
    for key in SOURCES:
        week, weekly = section_week(inp.section(key), inp.today)
        weekly = weekly and FAMILY[key] == "chart"
        rows[key] = {"week": week, "weekly": weekly, "older": weekly and week is not None and week < current}
    weekly_weeks = [r["week"] for r in rows.values() if r["weekly"] and r["week"] is not None]
    ref_week = min(max(weekly_weeks), current) if weekly_weeks else None
    for r in rows.values():
        r["first_load_excluded"] = bool(r["weekly"] and ref_week is not None and r["week"] is not None
                                        and r["week"] < ref_week)
    return {"current_week": current, "reference_week": ref_week, "series": rows}


def section_hold(inp: Inputs, section: str) -> str | None:
    """The hold reason on a fixture section, or None."""
    if section in inp.held:
        return inp.held[section]
    sec = inp.section(section)
    if not sec:
        return None
    for f in HOLD_FIELDS:
        hold = sec.get(f)
        if hold:
            if isinstance(hold, dict) and hold.get("reason"):
                return str(hold["reason"])
            return hold if isinstance(hold, str) else f
    return None


# ---------------------------------------------------------------------------
# Week history (docs/methodology.md "Week-Over-Week Snapshots"; written by
# pipelines/build_week_history.py into dist/assets/history during make sync)
# ---------------------------------------------------------------------------

class History:
    def __init__(self, root: Path = HISTORY):
        self.root = Path(root)
        self.index = self._load("index.json") or {}
        self.served_versions = self._load("served.json") or {}
        self._weeks = {}

    def _load(self, name):
        try:
            return json.loads((self.root / name).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def week_doc(self, week: int):
        if week not in self._weeks:
            rec = (self.index.get("weeks") or {}).get(str(week)) or {}
            name = Path(str(rec.get("file") or "")).name
            doc = self._load(name) if name else None
            self._weeks[week] = doc if doc and doc.get("week") == week else None
        return self._weeks[week]

    def served(self, base: str):
        return (self.index.get("served") or {}).get(base)


def history_entry(hist: History, base: str, week: int):
    """(entry, None) | (None, reason): a source's saved entry for a week, the
    served version when the source serves that week from a kept version."""
    doc = hist.week_doc(week)
    entry = ((doc or {}).get("sources") or {}).get(base)
    served = hist.served(base) or {}
    if served.get("week") == week and served.get("version") == "superseded":
        version = (hist.served_versions.get("sources") or {}).get(base)
        if not version or version.get("fingerprint") != served.get("entry_fingerprint"):
            return None, "the served version is not saved"
        entry = version
    if not entry:
        return None, f"no Week {week} content saved"
    if entry.get("week") != week:
        return None, f"saved entry is labelled week {entry.get('week')}"
    return entry, None


def snapshot_natives(inp: Inputs, source: str, entry: dict, scoring: str) -> dict:
    """A source's natives from a saved week entry: a chart's 12-team natives
    at the scoring, a projection's per-game points at the scoring. Reference
    reading: the snapshot has no superflex natives, so a superflex setting's
    prior week uses the 1-QB natives (nothing from the current week enters
    the prior week, VP-8.1)."""
    out = {}
    if FAMILY[source] == "chart":
        for key, v in ((entry.get("natives") or {}).get(scoring) or {}).items():
            k, f = int(key), _num(v)
            if k in inp.players and f is not None:
                out[k] = f
    else:
        idx = HISTORY_SCORING_INDEX[scoring]
        for key, triple in (entry.get("ppg") or {}).items():
            k = int(key)
            v = triple[idx] if isinstance(triple, list) and len(triple) > idx else None
            if k in inp.players and _finite(v):
                out[k] = float(v)
    return out


# ---------------------------------------------------------------------------
# One setting on the build's inputs
# ---------------------------------------------------------------------------

class Setting:
    """Everything the page computes at one (scoring, teams, roster)."""

    def __init__(self, inp: Inputs, scoring: str, teams: int, superflex: int = 0,
                 hist: History | None = None, bench_share: float | None = None,
                 position_shares: dict | None = None, selection: list | None = None,
                 lineup_settings: dict | None = None, bench_share_override: float | None = None,
                 expected_starts: bool = True):
        """lineup_settings: derive_lineup_parameters.resolve() keyword
        arguments (objective, injury_history, league_weeks,
        projection_confidence); None = the config's defaults. expected_starts
        False runs the VP-2.6 slices at bench_share (the JEG-508 pipeline)."""
        self.inp, self.scoring, self.teams = inp, scoring, int(teams)
        self.lineup = (resolve_lineup(load_lineup_config(), **(lineup_settings or {}))
                       if expected_starts else None)
        self.shape = roster(superflex)
        self.hist = hist
        self.selection = selection
        self.league = League(
            teams=self.teams, slots={p: self.shape[p] for p in POSITIONS}, flex=self.shape["FLEX"],
            superflex=self.shape["SUPERFLEX"], bench=self.shape["BENCH"],
            bench_share=DEFAULT_BENCH_SHARE if bench_share is None else float(bench_share),
            position_shares=position_shares, bench_share_override=bench_share_override)
        self.pos_of = {k: p["pos"] for k, p in inp.players.items()}
        self._current = None
        self._prior = None
        self._state = None

    # -- natives (VP-0) --------------------------------------------------
    def natives(self, src: str) -> dict:
        """Current-week natives at this setting's scoring. A chart: the saved
        12-team list, the saved native_superflex replacing it for the players
        it covers when SF >= 1. A projection: per-game points; ESPN lists a
        player it projects at zero (espn_status ineligible) at 0.0 (JEG-496;
        Reference reading of "every player on ESPN's list", VP-6.1, matching
        the ESPN week snapshot, which carries those players at 0)."""
        if self.inp.section(src) is None:
            return {}
        if FAMILY[src] == "chart":
            cell = self.inp.cell(src, self.scoring, SAVED_TEAMS, "native")
            out = dict(cell["values"]) if cell else {}
            if out and self.shape["SUPERFLEX"] >= 1:
                sf = self.inp.cell(src, self.scoring, SAVED_TEAMS, "native_superflex")
                if sf:
                    out.update(sf["values"])
            return out
        out = {}
        for k, p in self.inp.players.items():
            v = self.inp.ppg(k, PPG_FIELD[src], self.scoring)
            if v is not None:
                out[k] = v
            elif src == "espn" and p["espn_zero"]:
                out[k] = 0.0
        return out

    # -- VP-1 the included set -------------------------------------------
    def state(self) -> dict:
        """Eligible and included sources, exclusion reasons and the prior
        week's natives."""
        if self._state is not None:
            return self._state
        fresh = freshness(self.inp)
        current = {k: self.natives(k) for k in SOURCES}
        eligible, excluded = [], {}
        for k in SOURCES:
            hold = section_hold(self.inp, k)
            row = fresh["series"].get(k) or {}
            if hold:
                excluded[k] = f"held: {hold}"
            elif row.get("older") or row.get("first_load_excluded"):
                excluded[k] = f"not yet published for week {fresh['current_week']}"
            elif self.inp.section(k) is None:
                excluded[k] = "missing from this build"
            elif not current[k]:
                excluded[k] = "not available at this setting"
            else:
                eligible.append(k)
        prior, current_week = {}, None
        hist = self.hist
        built = (hist.index.get("fixture_built_at") if hist else None)
        same_build = not (built and self.inp.fixture.get("built_at") and built != self.inp.fixture["built_at"])
        if hist is not None and same_build:
            weeks = {k: (hist.served(k) or {}).get("week") for k in eligible}
            weeks = {k: w for k, w in weeks.items() if isinstance(w, int)}
            current_week = max(weeks.values()) if weeks else None
            for k in eligible:
                if weeks.get(k) != current_week or current_week is None:
                    continue
                entry, _why = history_entry(hist, k, current_week - 1)
                nat = snapshot_natives(self.inp, k, entry, self.scoring) if entry else {}
                if nat:
                    prior[k] = nat
        prior_shown = {}
        if prior:
            included = [k for k in eligible if k in prior]
            for k in eligible:
                if k not in prior:
                    excluded[k] = "no prior week"
            # VP-6.1 in the prior week: a held or unpublished source that has
            # the week saved is run and shown (its listed players get rows),
            # never counted, as in the current week.
            for k in SOURCES:
                if k in eligible or not current[k] or self.inp.section(k) is None:
                    continue
                entry, _why = history_entry(hist, k, current_week - 1)
                nat = snapshot_natives(self.inp, k, entry, self.scoring) if entry else {}
                if nat:
                    prior_shown[k] = nat
        else:
            included = list(eligible)
            current_week = None
        self._state = {"eligible": eligible, "included": included, "excluded": excluded,
                       "current": current, "prior": prior, "prior_shown": prior_shown,
                       "current_week": current_week}
        return self._state

    def _sources(self, natives: dict) -> dict:
        return {k: SourceInput(k, FAMILY[k], dict(natives[k])) for k in SOURCES if k in natives}

    def result(self) -> dict:
        if self._current is None:
            st = self.state()
            self._current = run_pipeline(self.league, self._sources(st["current"]), self.pos_of,
                                         st["included"], self.selection, lineup=self.lineup)
        return self._current

    def prior_result(self) -> dict | None:
        """VP-8: the same L, I and pie on the prior week's inputs."""
        st = self.state()
        if not st["prior"]:
            return None
        if self._prior is None:
            self._prior = run_pipeline(self.league, self._sources({**st["prior_shown"], **st["prior"]}),
                                       self.pos_of,
                                       st["included"], self.selection, lineup=self.lineup)
        return self._prior

    # -- VP-11 rows --------------------------------------------------------
    def rows(self, view: str = "indexed") -> dict:
        """{player_key: {series: value or None}} -- the page's rows in a tab,
        with the three DDF versions and their counts."""
        res = self.result()
        out = {}
        for i, r in res["rows"].items():
            values = {}
            for key in VIEW_SERIES[view]:
                base = VORP_KEYS.get(key, key)
                if key in VORP_KEYS:
                    values[key] = r["vorp_vs_waivers"].get(base)
                elif view == "indexed":
                    values[key] = r["indexed"].get(key) if FAMILY[key] == "chart" else r["adjusted"].get(key)
                elif view == "vorp":
                    values[key] = r["vorp_vs_waivers"].get(key)
                else:
                    values[key] = r["adjusted"].get(key)
            for version, name in DDF_VERSIONS.items():
                values[version] = r["ddf"][name]["value"]
                values[DDF_COUNT_FIELD[version]] = r["ddf"][name]["count"]
            out[i] = values
        return out

    def diagnostics(self) -> dict:
        """The comparable part of TradeValueCurveDiagnostics.valuePipeline."""
        res, st = self.result(), self.state()
        srcs = {}
        for k, d in res["sources"].items():
            srcs[k] = {
                "family": d["family"], "totalVorp": d["total_vorp"], "weights": d["weights"],
                "starterMix": d["starter_mix"], "benchMix": d["bench_mix"], "rates": d["rates"],
                "unfundedGroups": d["unfunded_groups"], "vorpFactor": d["vorp_display_factor"],
                "indexedFactor": (res["indexed"].get(k) or {}).get("factor"),
                "positions": {p: {"method": pi["method"], "waiver": pi["waiver_value"],
                                  "starterLine": pi["starter_line"], "starters": pi["starters"],
                                  "rostered": pi["rostered"], "listed": pi["listed"],
                                  "nEstimated": len(pi["imputation_ratios"] or {})}
                              for p, pi in d["positions"].items()},
            }
        return {"version": PIPELINE_VERSION, "pie": res["pie"], "method": res["method"],
                "benchShare": res["bench_share_readout"], "benchShareApplied": res["bench_share_applied"],
                "included": res["included"],
                "excluded": [{"key": k, "reason": v} for k, v in st["excluded"].items()],
                "ddfWeights": res["ddf_weights"], "allocation": res["slot_fill"],
                "fillSets": res["fill_sets"], "sources": srcs}


def compute(inp: Inputs, setting_spec: dict, views=VIEWS, hist: History | None = None) -> dict:
    """One setting in the shape value_check compares: rows per tab, the
    estimated flags, each DDF version's prior-week pair (the shape of the
    engine's getPriorWeek(version)), the included set and the diagnostics."""
    s = Setting(inp, setting_spec["scoring"], setting_spec["teams"], setting_spec.get("superflex", 0), hist=hist,
                lineup_settings=setting_spec.get("lineup"),
                bench_share_override=setting_spec.get("bench_share_override"),
                expected_starts=setting_spec.get("expected_starts", True))
    res, st = s.result(), s.state()
    prior = s.prior_result()
    out = {"setting": setting_spec, "views": {}, "prior": {}, "composite": {}}
    for view in views:
        out["views"][view] = s.rows(view)
    out["estimated"] = {i: dict(r["estimated"]) for i, r in res["rows"].items() if r["estimated"]}
    for version, name in DDF_VERSIONS.items():
        fam = DDF_FAMILY[name]
        inputs = [k for k in st["included"] if fam is None or FAMILY[k] == fam]
        excluded = {k: v for k, v in st["excluded"].items() if fam is None or FAMILY[k] == fam}
        out["composite"][version] = {"inputs": inputs, "excluded": excluded}
        if hist is None:
            continue
        if prior is not None and inputs:
            pv = {i: r["ddf"][name]["value"] for i, r in prior["rows"].items()}
            cv = {i: r["ddf"][name]["value"] for i, r in res["rows"].items()}
            entry = {"available": True, "sources": inputs, "currentWeek": st["current_week"],
                     "priorWeek": st["current_week"] - 1,
                     "values": {i: v for i, v in pv.items() if v is not None},
                     "currentValues": {i: v for i, v in cv.items() if v is not None}}
        else:
            entry = {"available": False, "sources": []}
        for view in views:
            out["prior"].setdefault(view, {})[version] = entry
    out["composite_inputs"] = list(st["included"])
    out["composite_excluded"] = dict(st["excluded"])
    out["pipeline"] = s.diagnostics()
    return out


# ---------------------------------------------------------------------------
# Legacy (retired by JEG-508 VP-10; not part of the pipeline above)
# ---------------------------------------------------------------------------
# derive_views is the superseded published-chart VORP vs waivers / Adjusted
# batch (D'Hondt flex, ESPN group budgets, the 70 Adjusted scale). It is kept
# only because tests/test_published_views_engine.py holds the CURRENT
# engine's ValueModel.derivePublishedViews to it; that test and this function
# retire with the engine change that removes derivePublishedViews.

def _ranked_by_pos(native: dict, pos_of) -> dict:
    ranked = {p: [] for p in POSITIONS}
    for key, value in native.items():
        ranked[pos_of(key)].append((str(key), str(key), float(value)))
    for p in POSITIONS:
        ranked[p].sort(key=lambda r: -r[2])
    return ranked


def derive_views(inputs: dict, natives: dict, pos_of, teams: int, shape: dict) -> dict:
    """LEGACY. {src: {"vorp": {key: v}, "adj": {key: v}}} for a batch of
    published charts under the superseded rules (see the note above)."""
    from pipelines.vorp_translation import unified
    slots = {p: int(shape[p]) for p in POSITIONS}
    sf = int(shape.get("SUPERFLEX") or 0)
    vorp_out, weighted, batch_max = {}, {}, 0.0
    for src, (native, keys, budgets) in inputs.items():
        total = sum(b for g in budgets.values() for b in g.values() if b > 0)
        ranked = _ranked_by_pos(native, pos_of)
        peers = {}
        for other, nat in natives.items():
            if other != src and nat:
                by_pos = {p: [] for p in POSITIONS}
                for key, value in nat.items():
                    by_pos[pos_of(key)].append((str(key), float(value)))
                peers[other] = by_pos
        at = unified.translate_ranked(ranked, teams, shape["BENCH"], shape["FLEX"], slots=slots,
                                      peers=peers, superflex_count=sf)
        info, groups, vsum = {}, {p: {"starter": 0.0, "bench": 0.0} for p in POSITIONS}, 0.0
        for p in POSITIONS:
            pinfo = at["positions"].get(p)
            if not pinfo:
                continue
            n_start = pinfo["n_dedicated"] + pinfo.get("n_superflex", 0) + pinfo["n_flex"]
            for i, (pkey, _n, _v) in enumerate(ranked[p]):
                t = at["translated"].get(pkey)
                if t is None:
                    continue
                role = "starter" if i < n_start else "bench"
                info[pkey] = (p, role, t["vorp"])
                groups[p][role] += t["vorp"]
                vsum += t["vorp"]
        scale = total / vsum if vsum > 0 else 0.0
        v_map, w_map = {}, {}
        for key in keys:
            row = info.get(str(key))
            v = w = 0.0
            if row:
                p, role, vorp = row
                v = vorp * scale
                gt, b = groups[p][role], budgets[p][role]
                w = b * vorp / gt if gt > 0 and b > 0 else 0.0
            v_map[key], w_map[key] = v, w
            batch_max = max(batch_max, w)
        vorp_out[src], weighted[src] = v_map, w_map
    adj_scale = 70.0 / batch_max if batch_max > 0 else 0.0
    return {src: {"vorp": vorp_out[src], "adj": {k: w * adj_scale for k, w in weighted[src].items()}}
            for src in vorp_out}


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=REPO / "output" / "value-reference.json")
    ap.add_argument("--fixture", type=Path, default=FIXTURE)
    ap.add_argument("--players", type=Path, default=PLAYERS)
    ap.add_argument("--history", type=Path, default=HISTORY)
    args = ap.parse_args(argv)
    inp = Inputs.load(args.fixture, args.players)
    hist = History(args.history)
    result = {"version": VERSION, "settings": [compute(inp, s, hist=hist) for s in settings()]}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, separators=(",", ":"), default=str), encoding="utf-8")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
