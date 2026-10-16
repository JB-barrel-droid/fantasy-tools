"""Fundamental bench module: net-of-waiver value per bench spot by position
and depth.

Ticket: JEG-564 (part of JEG-556).
Decision: Jeremy, 2026-10-10: "research + advice later. The fundamental bench
stays in Later. It never feeds values, tiers or waiver lines."

This module is SEPARATE from the market bench convention (roster_convention.py).
The market bench sets tiers and the waiver line. The fundamental bench NEVER
does -- the parity test asserts this.

Uses:
  - Roster advice (market vs fundamental gap: "drop your backup QB, hold a
    3rd WR")
  - Research content (JEG-557)
  - Expected-starts bench component (JEG-562, when it lands)

Data: 2015-2025 history, pooled across 3 scorings x 4 league sizes for
stability. No hindsight: lineups set on season-to-date PPG; held backup
compared with the best deeper player available that week on actual points.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent.parent
FUNDAMENTAL_BENCH_PATH = REPO / "config" / "fundamental_bench.json"


def _load_config() -> dict:
    with open(FUNDAMENTAL_BENCH_PATH) as f:
        return json.load(f)


def ladder() -> list[dict[str, Any]]:
    """Return the pooled net-of-waiver ladder, sorted best-first.

    Each entry: {position, depth, insurance, upside, total, label}.
    Total = insurance + upside = net points per week per held player,
    pooled across all 12 settings.
    """
    cfg = _load_config()
    return list(cfg["ladder"])


def bench_value(position: str, depth: int) -> dict[str, float]:
    """Return net-of-waiver value for one bench slot.

    Args:
        position: "QB", "RB", "WR", or "TE".
        depth: 1 = first backup, 2 = second backup, etc.

    Returns:
        {insurance, upside, total} in net points per week.
        Returns {insurance: 0, upside: 0, total: 0} for unknown slots.
    """
    cfg = _load_config()
    for entry in cfg["ladder"]:
        if entry["position"] == position and entry["depth"] == depth:
            return {
                "insurance": entry["insurance"],
                "upside": entry["upside"],
                "total": entry["total"],
            }
    return {"insurance": 0.0, "upside": 0.0, "total": 0.0}


def optimal_bench(bench_spots: int) -> list[dict[str, Any]]:
    """Allocate bench spots by fundamental value (greedy, best-first).

    Returns a list of bench_spots entries from the ladder, in priority
    order. If bench_spots exceeds the ladder length, only ladder entries
    are returned (remaining spots have ~zero value).

    This is the prescriptive answer to "what should a manager hold?" --
    as opposed to the market bench (what leagues actually hold).
    """
    cfg = _load_config()
    entries = cfg["ladder"]
    # Already sorted best-first in the config
    return [dict(e) for e in entries[:bench_spots]]


def bench_summary(bench_spots: int) -> dict[str, int]:
    """How many backups per position to hold, given bench_spots.

    Returns {QB: n, RB: n, WR: n, TE: n} -- the fundamental
    recommendation (not the market convention).
    """
    picks = optimal_bench(bench_spots)
    counts: dict[str, int] = {"QB": 0, "RB": 0, "WR": 0, "TE": 0}
    for p in picks:
        pos = p["position"]
        if pos in counts:
            counts[pos] += 1
    return counts


def findings() -> dict[str, str]:
    """Return research findings as {key: human-readable sentence}."""
    cfg = _load_config()
    return dict(cfg["findings"])
