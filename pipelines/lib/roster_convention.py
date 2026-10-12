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
                  flex_filled: dict[str, int] | None = None) -> dict[str, float]:
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
        starters = int(slots.get(pos, 0)) + int(ff.get(pos, 0))
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
                flex_filled: dict[str, int] | None = None) -> dict[str, int]:
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

    # Bench: convention rule 1
    # For bench weights, starters = dedicated + superflex + flex
    effective_slots = {}
    for pos in POSITIONS:
        effective_slots[pos] = int(slots.get(pos, 0))
    effective_flex = {}
    for pos in POSITIONS:
        effective_flex[pos] = sf_filled[pos] + fx_filled[pos]

    is_superflex = superflex_count > 0
    is_2qb = int(slots.get("QB", 0)) >= 2
    b = bench_seats(
        effective_slots, teams, bench_per_team,
        superflex=(is_superflex or is_2qb),
        flex_filled=effective_flex,
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
