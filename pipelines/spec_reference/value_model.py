"""Value model: value above waivers and the three views, from the written spec.

Spec sources:
- docs/methodology.md "The Three Views": every source is translated to
  implied value above waivers under the standard default roster (bench shape
  included) unless the publisher states otherwise; implied weights by
  position and starter/bench (flex counted); "Position counts always account
  for flex".
- "Publisher Flex Allocation": dedicated starters excluded from flex
  candidates; the next teams x flex_count ranked players at each eligible
  position are the flex range, missing candidates count zero surplus; weight =
  dedicated slots per team x average native surplus above a preliminary
  waiver line from slot-proportional flex plus the bench mix; flex and bench
  capacities by D'Hondt; a zero-surplus chart falls back to dedicated-slot
  proportions; final waiver lines recomputed from the resulting roster.
- "Short charts" (V2-WAIVER-COVERAGE): peers, tail ratio, capped imputation,
  extension only where the chart lists no more players than the league
  rosters, otherwise the last listed value.
- "Trade-Value Contract" / JEG-482: Indexed = native x one factor (anchor
  total / native total over the players both price); the saved 12-team
  values are shown unchanged at the saved setup.
- "Other chart views": VORP vs waivers = value above the setting's waiver
  line x one factor per chart so its total equals the anchor's total over the
  players the chart ranks; Adjusted values = position x starter/bench groups
  (starter = dedicated + flex count at the position), each group shares the
  anchor's total for that group in proportion to value above waivers, then one
  factor across all published charts at the setting puts the top at 70. The
  saved `vorp_views` are shown only at full PPR / 12 teams / standard roster
  for FantasyCalc, FantasyPros and USA Today.
- VA-1 / "What holds": the raw projection value-above-waivers series total
  exactly the anchor's total over shared players.
"""
from __future__ import annotations

import statistics

from .twotier import BENCH_MIX_12, FLEX_ELIGIBLE, POSITIONS, round_half_up

DEFAULT_ROSTER = {"QB": 1, "RB": 2, "WR": 3, "TE": 1, "FLEX": 1, "BENCH": 6}
SAVED_TEAMS = 12
MIN_SHARED_FOR_FACTOR = 40
MIN_TAIL_OVERLAP = 3
# GAP SG-11: which anchor players count as "priced" for a total-match factor.
# The contract keeps genuine zeros as values, so "listed" (anchor 0.0 counts)
# is the spec reading. "positive" (anchor value > 0) is available only so a
# diagnostic run can separate this gap from the others; never the default.
PRICED_BASIS = "listed"


def dhondt(seats: int, weights: dict[str, float], order=POSITIONS) -> dict[str, int]:
    """Highest averages. GAP: ties are not specified; position order wins."""
    alloc = {p: 0 for p in weights}
    for _ in range(max(0, seats)):
        best, best_q = None, -1.0
        for p in order:
            if p not in weights:
                continue
            q = weights[p] / (alloc[p] + 1)
            if q > best_q + 1e-15:
                best, best_q = p, q
        if best is None:
            break
        alloc[best] += 1
    return alloc


def bench_alloc(teams: int, roster=DEFAULT_ROSTER) -> dict[str, int]:
    """teams x BENCH seats apportioned by the 12-team bench mix."""
    return dhondt(teams * roster["BENCH"], dict(BENCH_MIX_12))


def _ranked(values: dict) -> list:
    return sorted(values.items(), key=lambda kv: (-kv[1], str(kv[0])))


# --------------------------------------------------------------- short charts

def extend_position(chart: dict, peers: list[dict]) -> list:
    """chart / peers: {key: native} at ONE position. Returns the imputed
    extension [(key, value)] (ordered by value), possibly empty."""
    listed = list(chart.values())
    if not listed:
        return []
    median = statistics.median(listed)
    tail = {k for k, v in chart.items() if v <= median}
    last = min(listed)
    ratios = []
    for peer in peers:
        both = [k for k in tail if k in peer]
        if len(both) < MIN_TAIL_OVERLAP:
            continue
        den = sum(peer[k] for k in both)
        if den <= 0:
            continue
        ratios.append((sum(chart[k] for k in both) / den, peer))
    if not ratios:
        return []
    candidates = {k for _, peer in ratios for k in peer if k not in chart}
    out = {}
    for k in candidates:
        vals = [r * peer[k] for r, peer in ratios if k in peer]
        out[k] = min(sum(vals) / len(vals), last)
    return _ranked(out)


# ------------------------------------------------------------ translation

def translate(natives: dict, pos_of: dict, teams: int, peers: list[dict] | None = None,
              roster=DEFAULT_ROSTER) -> dict:
    """A published chart's value above waivers at a league setting.

    natives: {key: native} for the chart (1-QB); pos_of: {key: pos};
    peers: other charts' natives at the same scoring (for short positions).
    """
    by_pos = {p: {k: v for k, v in natives.items() if pos_of.get(k) == p and v is not None}
              for p in POSITIONS}
    peer_pos = [{p: {k: v for k, v in pr.items() if pos_of.get(k) == p and v is not None}
                 for p in POSITIONS} for pr in (peers or [])]
    lists = {p: _ranked(by_pos[p]) for p in POSITIONS}
    ext = {p: extend_position(by_pos[p], [pp[p] for pp in peer_pos]) for p in POSITIONS}

    def line_at(pos: int | str, count: int):
        own = lists[pos]
        if len(own) > count:
            return own[count][1], "rostered_count", 0
        full = own + ext[pos]
        if len(full) > count:
            return full[count][1], "imputed_from_other_charts", count - len(own) + 1
        return (own[-1][1] if own else 0.0), "insufficient_coverage", 0

    dedicated = {p: teams * roster[p] for p in POSITIONS}
    bench = bench_alloc(teams, roster)
    flex_seats = teams * roster["FLEX"]
    elig_slots = sum(roster[p] for p in FLEX_ELIGIBLE)
    # preliminary line: slot-proportional flex plus the bench mix
    # GAP: rounding of the fractional slot-proportional flex count is not
    # written; round half up.
    prelim = {}
    for p in POSITIONS:
        flex_share = flex_seats * roster[p] / elig_slots if p in FLEX_ELIGIBLE else 0.0
        prelim[p] = line_at(p, dedicated[p] + round_half_up(flex_share) + bench[p])[0]
    weights = {}
    for p in FLEX_ELIGIBLE:
        full = lists[p] + ext[p]
        cands = full[dedicated[p]: dedicated[p] + flex_seats]
        # GAP: whether imputed (hidden) players count as flex candidates is not
        # written; they do here (they exist "only for this computation").
        surplus = sum(max(0.0, v - prelim[p]) for _, v in cands)
        weights[p] = roster[p] * surplus / flex_seats if flex_seats else 0.0
    if sum(weights.values()) <= 0:
        weights = {p: float(roster[p]) for p in FLEX_ELIGIBLE}
    flex = dhondt(flex_seats, weights, FLEX_ELIGIBLE)
    flex = {p: flex.get(p, 0) for p in POSITIONS}
    rostered = {p: dedicated[p] + flex[p] + bench[p] for p in POSITIONS}
    waiver, method, n_imputed = {}, {}, {}
    for p in POSITIONS:
        waiver[p], method[p], n_imputed[p] = line_at(p, rostered[p])
    vaw, role = {}, {}
    for p in POSITIONS:
        n_start = dedicated[p] + flex[p]
        for i, (k, v) in enumerate(lists[p]):
            vaw[k] = max(0.0, v - waiver[p])
            role[k] = "starter" if i < n_start else ("bench" if vaw[k] > 0 else "waiver")
    total = sum(vaw.values())
    weights_out = {}
    for p in POSITIONS:
        for g in ("starter", "bench"):
            s = sum(vaw[k] for k in by_pos[p] if role.get(k) == g)
            weights_out[f"{p}|{g}"] = s / total if total > 0 else None
    return {
        "vaw": vaw, "role": role, "waiver": waiver, "waiver_method": method,
        "n_imputed": n_imputed, "flex": flex, "bench": bench, "rostered": rostered,
        "dedicated": dedicated, "implied_weights": weights_out,
    }


# ------------------------------------------------------------- the views

def one_factor(values: dict, anchor: dict, basis: str = "shared") -> float | None:
    """basis 'shared': anchor / own over keys both price.
    basis 'chart': anchor over the chart's keys / own over ALL own keys."""
    shared = [k for k in values if k in anchor and anchor[k] is not None and values[k] is not None
              and (PRICED_BASIS == "listed" or anchor[k] > 0)]
    if basis == "shared":
        own = sum(values[k] for k in shared)
    else:
        own = sum(v for v in values.values() if v is not None)
    target = sum(anchor[k] for k in shared)
    if own <= 0:
        return None
    return target / own


def indexed_published(natives: dict, anchor: dict, saved_reindexed: dict | None,
                      saved_factor: float | None, teams: int) -> dict:
    if teams == SAVED_TEAMS and saved_reindexed is not None:
        return dict(saved_reindexed)
    shared = [k for k in natives if k in anchor]
    factor = one_factor(natives, anchor, "shared")
    if len(shared) < MIN_SHARED_FOR_FACTOR or factor is None:
        factor = saved_factor
    if factor is None:
        return {}
    return {k: v * factor for k, v in natives.items()}


def vorp_view_published(tr: dict, anchor: dict) -> dict:
    factor = one_factor(tr["vaw"], anchor, "chart")
    if factor is None:
        return {k: 0.0 for k in tr["vaw"]}
    return {k: v * factor for k, v in tr["vaw"].items()}


# SG-7 resolution: "all" (the anchor's whole group) is the spec reference's
# reading; "chart" (the anchor's group over the chart's own players, VA-5) is
# available only for a diagnostic run.
ADJ_BUDGET_BASIS = "all"


def anchor_groups(anchor: dict, anchor_tier: dict, pos_of: dict, keys=None) -> dict:
    """The anchor's total per position x starter/bench group.

    GAP: "the anchor's total for that group" does not say whose roles define
    the anchor's groups nor over which players. Resolved: the anchor's own
    two-tier tiers (its pool is the setting's starter + flex count at the
    default roster), summed over every player the anchor prices."""
    out = {f"{p}|{g}": 0.0 for p in POSITIONS for g in ("starter", "bench")}
    for k, v in anchor.items():
        if keys is not None and k not in keys:
            continue
        t = anchor_tier.get(k)
        p = pos_of.get(k)
        if t in ("starter", "bench") and p in POSITIONS and v:
            out[f"{p}|{t}"] += v
    return out


def adjusted_published(trs: dict, budgets: dict, pos_of: dict, top: float = 70.0,
                       budgets_by_chart: dict | None = None) -> dict:
    """trs: {chart: translate() result}. Returns {chart: {key: value}} with one
    factor across all charts putting the top at `top`."""
    pre = {}
    for src, tr in trs.items():
        if budgets_by_chart and src in budgets_by_chart:
            budgets = budgets_by_chart[src]
        vals = {}
        for p in POSITIONS:
            for g in ("starter", "bench"):
                keys = [k for k, r in tr["role"].items() if r == g and pos_of.get(k) == p]
                s = sum(tr["vaw"][k] for k in keys)
                for k in keys:
                    vals[k] = budgets[f"{p}|{g}"] * tr["vaw"][k] / s if s > 0 else 0.0
        for k in tr["vaw"]:
            vals.setdefault(k, 0.0)
        pre[src] = vals
    m = max((v for vals in pre.values() for v in vals.values()), default=0.0)
    lam = top / m if m > 0 else 0.0
    return {src: {k: v * lam for k, v in vals.items()} for src, vals in pre.items()}


def projection_vaw(ppg: dict, pos_of: dict, teams: int, roster=DEFAULT_ROSTER) -> dict:
    """Raw value above waivers for a projection source (espn/cbsros/razzball).

    Roles by projected points (methodology "Superflex": projection roles rank
    by projected points per game, like ordinary FLEX); bench by the shared
    allocator (teams x BENCH by the 12-team mix, D'Hondt).
    GAP: the raw series' bench count is not written for projections; the
    shared translation allocator's bench is used.
    """
    by_pos = {p: _ranked({k: v for k, v in ppg.items() if pos_of.get(k) == p and v is not None})
              for p in POSITIONS}
    dedicated = {p: teams * roster[p] for p in POSITIONS}
    flex_pool = sorted([(k, v, p) for p in FLEX_ELIGIBLE for k, v in by_pos[p][dedicated[p]:]],
                       key=lambda r: (-r[1], str(r[0])))[: teams * roster["FLEX"]]
    flex = {p: sum(1 for r in flex_pool if r[2] == p) for p in POSITIONS}
    bench = bench_alloc(teams, roster)
    out, waiver = {}, {}
    for p in POSITIONS:
        n = dedicated[p] + flex[p] + bench[p]
        lst = by_pos[p]
        waiver[p] = lst[n][1] if len(lst) > n else (lst[-1][1] if lst else 0.0)
        for k, v in lst:
            out[k] = max(0.0, v - waiver[p])
    return {"vaw": out, "waiver": waiver, "flex": flex, "bench": bench}


def match_total(values: dict, anchor: dict) -> dict:
    """One factor so the total over shared players equals the anchor's."""
    f = one_factor(values, anchor, "shared")
    if f is None:
        return {}
    return {k: v * f for k, v in values.items()}
