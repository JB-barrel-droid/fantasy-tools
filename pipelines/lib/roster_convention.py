"""Shared roster convention: one definition of bench seats, starter line,
waiver line, flex allocation and tier basis.

Ticket: JEG-559 (part of JEG-556).
Decisions: Jeremy 2026-10-10/12 (see JEG-556 comments).

Every value path must call these functions. No other module may define its
own bench counts, starter line, waiver line or tier boundaries. The
fundamental bench module (its own ticket) must never be used for tiers or
lines -- the parity test asserts this.

Rules implemented:
  1. Bench seats: weight_p = starters_p * backups_per_starter_p (from
     config/market_bench.json), D'Hondt over teams * bench.
  2. Flex: greedy by points (projections) or by value (charts). Superflex
     includes QB.
  3. Starter line: midpoint of last starter and first non-starter.
  4. Waiver line: first player not rostered.
  5. Short lists: fill with real players from other sources, valued at the
     source's last listed value (imputation).
  6. Tier basis: rank within position on the list being valued.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent.parent
MARKET_BENCH_PATH = REPO / "config" / "market_bench.json"

POSITIONS = ("QB", "RB", "WR", "TE", "K", "DEF")
SKILL_POSITIONS = ("QB", "RB", "WR", "TE")
POS_ORDER = {p: i for i, p in enumerate(POSITIONS)}
FLEX_ELIGIBLE = ("RB", "WR", "TE")
SUPERFLEX_ELIGIBLE = ("QB", "RB", "WR", "TE")

# JEG-1121: VORP bench allocation constants.
# miss_rate per game (from lineup_parameters.json; rounded for JS parity).
_BENCH_MISS_RATE = {"QB": 0.12, "RB": 0.14, "WR": 0.11, "TE": 0.15}
_BYE_RATE = 1.0 / 17.0  # one bye per 17-game season

# Default roster: 1 QB / 2 RB / 2 WR / 1 TE / 1 FLEX / 1 K / 1 DEF, 7 bench.
# The switch to this default ships in JEG-563; this module defines it.
DEFAULT_SLOTS = {"QB": 1, "RB": 2, "WR": 2, "TE": 1, "K": 1, "DEF": 1}
DEFAULT_FLEX = 1
DEFAULT_SUPERFLEX = 0
DEFAULT_BENCH = 7
DEFAULT_TEAMS = 12


def _load_market_bench() -> dict:
    with open(MARKET_BENCH_PATH) as f:
        return json.load(f)


def market_bench_ratios(*, superflex: bool = False, qb_slots: int = 1) -> dict[str, float]:
    """Return backups-per-starter ratios from config/market_bench.json.

    Uses two_qb when the roster has 2+ QB slots or a superflex slot (JEG-559
    comment, Jeremy 2026-10-10); otherwise one_qb.
    """
    cfg = _load_market_bench()
    key = "two_qb" if (superflex or qb_slots >= 2) else "one_qb"
    return dict(cfg[key]["backups_per_starter"])


def bench_weights(slots: dict[str, int], *, superflex: bool = False,
                  flex_filled: dict[str, float] | None = None) -> dict[str, float]:
    """Convention rule 1: bench weight per position.

    weight_p = starters_p * backups_per_starter_p.

    `slots` maps position -> dedicated starter slots (not including flex).
    `flex_filled` maps position -> flex starters assigned to that position
    (from a prior flex allocation). If not provided, flex is not counted in
    starters for bench weight purposes.
    """
    ratios = market_bench_ratios(
        superflex=superflex,
        qb_slots=int(slots.get("QB", 0)),
    )
    ff = flex_filled or {}
    weights = {}
    for pos in POSITIONS:
        starters = int(slots.get(pos, 0)) + (ff.get(pos, 0) or 0)
        ratio = ratios.get(pos, 0.0)
        weights[pos] = starters * ratio
    return weights


def dhondt_allocate(weights: dict[str, float], total: int) -> dict[str, int]:
    """D'Hondt (highest averages) seat allocation.

    Ties go to position order (earliest in POSITIONS wins).
    """
    if total < 0 or total != int(total):
        raise ValueError("total must be a nonnegative integer")
    total = int(total)
    seats = {p: 0 for p in POSITIONS}
    eligible = [p for p in POSITIONS if (weights.get(p, 0) or 0) > 0]
    if total > 0 and not eligible:
        raise ValueError("positive total requires at least one positive weight")
    for _ in range(total):
        best = max(eligible, key=lambda p: (weights[p] / (seats[p] + 1), -POS_ORDER[p]))
        seats[best] += 1
    return seats


def bench_seats(slots: dict[str, int], teams: int, bench_per_team: int, *,
                superflex: bool = False,
                flex_filled: dict[str, float] | None = None) -> dict[str, int]:
    """Convention rule 1: D'Hondt bench allocation using market bench ratios.

    Returns {pos: bench_count} across the entire league.
    """
    w = bench_weights(slots, superflex=superflex, flex_filled=flex_filled)
    total = teams * bench_per_team
    return dhondt_allocate(w, total)


def flex_allocate_greedy(remaining: dict[str, list], scores: dict,
                         count: int, eligible: tuple | list) -> dict[str, int]:
    """Convention rule 2: greedy flex allocation by score.

    `remaining[pos]` = list of player keys still available (after dedicated
    slots), already sorted best-first. `scores[key]` = the score to rank by
    (points for projections, value for charts). `count` = total flex slots
    across the league. `eligible` = positions eligible for flex.

    Returns {pos: flex_starters_at_pos}.
    """
    candidates = []
    for pos in eligible:
        for key in remaining.get(pos, []):
            if key in scores:
                candidates.append((pos, key, scores[key]))
    # Sort: highest score first, ties to position order then key
    candidates.sort(key=lambda c: (-c[2], POS_ORDER.get(c[0], 99), c[1]))
    filled = {p: 0 for p in POSITIONS}
    for pos, _key, _score in candidates[:max(0, count)]:
        filled[pos] += 1
    return filled


def starter_line(values: list[float], starters: int) -> float | None:
    """Convention rule 3: midpoint of last starter and first non-starter.

    `values` must be sorted descending (best first). `starters` is the count
    of starters at this position across the league.

    Returns None if there aren't enough values.
    """
    if starters <= 0 or len(values) < starters:
        return None
    last_starter = values[starters - 1]
    if len(values) > starters:
        first_bench = values[starters]
        return (last_starter + first_bench) / 2.0
    # Exactly starters players: starter line = last starter value
    return last_starter


def waiver_line(values: list[float], rostered: int) -> float | None:
    """Convention rule 4: the first player not rostered.

    `values` must be sorted descending (best first). `rostered` is starters +
    bench at this position across the league.

    Returns None if there aren't enough values. If the list is exactly
    rostered-length, the waiver line is the last value (the short-list
    imputation rule ensures rosters are always full).
    """
    if rostered <= 0 or len(values) == 0:
        return None
    if len(values) > rostered:
        return values[rostered]
    # Short list or exact fit: waiver is at or below the last listed value
    return values[-1]


# JEG-1047 (Jeremy, 2026-10-29: "A"): a projection source's waiver line is the
# average of the 7 players around the first non-rostered seat, not that one
# player, so one fringe player's projection cannot reprice a whole position.
WAIVER_BAND_HALF_WIDTH = 3


def waiver_band_line(values: list[float], rostered: int,
                     half_width: int = WAIVER_BAND_HALF_WIDTH) -> float | None:
    """JEG-1047: mean of values[rostered - h .. rostered + h], clipped to the
    list. `values` sorted descending. Same short-list fallback as
    waiver_line: with no player past the rostered count, the last value.

    A zero seat (rostered == 0, a position no team starts or benches) is the
    band clipped at the top of the list, values[0 .. h], as VP-2.3 reads
    ("indexes N_p - 3 through N_p + 3, clipped to the work list") and as the
    engine's vpWaiverBand computes (JEG-1244). Only an empty list or a
    negative count has no line."""
    if rostered < 0 or len(values) == 0:
        return None
    if len(values) <= rostered:
        return values[-1]
    lo, hi = max(0, rostered - half_width), min(len(values), rostered + half_width + 1)
    window = values[lo:hi]
    return sum(window) / len(window)


def vorp_bench_allocate(
    starters: dict[str, int],
    remaining: dict[str, list],
    player_scores: dict,
    teams: int,
    total_bench: int,
    slots: dict[str, int],
    is_two_qb: bool,
    flex_filled_per_team: dict[str, float] | None = None,
) -> dict[str, int]:
    """Greedy bench fill by PPG × usage discount (JEG-1121 stable spec).

    All bench seats are filled in a single cross-position pass: the candidate
    at each position scores max(0, PPG) × c_p^(1 + floor(k / t1_p)), where
    c_p = starters_per_team × (bye_rate + miss_rate) and t1_p =
    round(2 × c_p × teams).  Replacement level is 0 (any positive-PPG player
    competes).  Seats left unfilled only if no positive-PPG candidates remain.
    No D'Hondt fallback.

    Seat counts never depend on DDF Value, so the result is deterministic
    without iteration.

    starters[pos]: league-wide starter count (dedicated + sf + flex).
    remaining[pos]: non-starter candidates sorted best-first (by PPG).
    """
    spt = {pos: starters.get(pos, 0) / teams for pos in POSITIONS}

    # t1[pos] = round(2 × coverage_rate × teams): tier-1 boundary.
    t1: dict[str, int] = {}
    for pos in POSITIONS:
        c = spt[pos] * (_BYE_RATE + _BENCH_MISS_RATE.get(pos, 0.12))
        t1[pos] = max(1, round(2.0 * c * float(teams)))

    def _discount(pos: str, k: int) -> float:
        c = spt[pos] * (_BYE_RATE + _BENCH_MISS_RATE.get(pos, 0.12))
        return c ** (1 + k // t1[pos])

    counts: dict[str, int] = {pos: 0 for pos in POSITIONS}
    for _ in range(max(0, int(total_bench))):
        best: float = -1e18
        winner: str | None = None
        any_candidate = False
        for pos in POSITIONS:
            order = remaining.get(pos, [])
            k = counts[pos]
            if k >= len(order):
                continue
            any_candidate = True
            raw = float(player_scores.get(order[k], 0) or 0)
            effective = max(0.0, raw) * _discount(pos, k)
            pos_rank = POS_ORDER.get(pos, 99)
            win_rank = POS_ORDER.get(winner, 99) if winner is not None else 99
            if effective > best or (effective == best and pos_rank < win_rank):
                best = effective
                winner = pos
        if winner is None or not any_candidate:
            break
        if best <= 0:
            break  # no positive-PPG candidates remain; leave seats unfilled
        counts[winner] += 1

    return counts


def allocate_league(slots: dict[str, int], teams: int, bench_per_team: int,
                    flex_count: int, superflex_count: int,
                    player_order: dict[str, list],
                    player_scores: dict,
                    flex_eligible: tuple | list = FLEX_ELIGIBLE,
                    superflex_eligible: tuple | list = SUPERFLEX_ELIGIBLE,
                    ) -> dict[str, dict[str, int]]:
    """Full league allocation: dedicated + superflex + flex + bench.

    Returns {pos: {dedicated, superflex, flex, bench, starters, rostered}}.

    `player_order[pos]` = list of player keys sorted best-first.
    `player_scores[key]` = score for flex/superflex ranking.
    """
    t = int(teams)

    # Dedicated slots
    dedicated = {p: t * int(slots.get(p, 0)) for p in POSITIONS}

    # Track remaining players after dedicated
    remaining_after_ded = {}
    for pos in POSITIONS:
        order = player_order.get(pos, [])
        remaining_after_ded[pos] = order[dedicated[pos]:]

    # Superflex: greedy across all positions
    sf_filled = flex_allocate_greedy(
        remaining_after_ded, player_scores,
        t * int(superflex_count), superflex_eligible,
    )

    # Track remaining after superflex
    remaining_after_sf = {}
    for pos in POSITIONS:
        remaining_after_sf[pos] = remaining_after_ded[pos][sf_filled[pos]:]

    # Flex: greedy across flex-eligible positions
    fx_filled = flex_allocate_greedy(
        remaining_after_sf, player_scores,
        t * int(flex_count), flex_eligible,
    )

    # JEG-1121 VORP: bench fills by VORP × usage discount (not raw PPG).
    remaining_after_fx = {}
    for pos in POSITIONS:
        remaining_after_fx[pos] = remaining_after_sf[pos][fx_filled[pos]:]

    starters_count = {pos: dedicated[pos] + sf_filled[pos] + fx_filled[pos]
                      for pos in POSITIONS}
    is_two_qb = int(superflex_count) > 0 or int(slots.get("QB", 0)) >= 2
    ff_per_team = (None if is_two_qb
                   else {pos: (sf_filled[pos] + fx_filled[pos]) / t
                         for pos in POSITIONS})
    b = vorp_bench_allocate(
        starters_count, remaining_after_fx, player_scores,
        t, t * int(bench_per_team), slots, is_two_qb, ff_per_team,
    )

    out = {}
    for pos in POSITIONS:
        s = dedicated[pos] + sf_filled[pos] + fx_filled[pos]
        out[pos] = {
            "dedicated": dedicated[pos],
            "superflex": sf_filled[pos],
            "flex": fx_filled[pos],
            "bench": b[pos],
            "starters": s,
            "rostered": s + b[pos],
        }
    return out


def compute_lines(values: list[float], starters: int, rostered: int
                  ) -> dict[str, Any]:
    """Compute starter line and waiver line for one position.

    `values` = sorted descending list of player values at this position.
    Returns {starter_line, waiver_line, method}.
    """
    sl = starter_line(values, starters)
    wl = waiver_line(values, rostered)
    if sl is not None and wl is not None:
        # Starter line must be >= waiver line
        sl = max(sl, wl)
    method = "roster_determined"
    if len(values) < rostered:
        method = "insufficient_coverage"
    if len(values) == 0:
        method = "no_players"
        sl = None
        wl = None
    return {"starter_line": sl, "waiver_line": wl, "method": method}
