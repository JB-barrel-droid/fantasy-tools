#!/usr/bin/env python3
"""Feasible bench bounds -- Python reference (JEG-432 R2).

The browser runs ValueModel.feasibleBenchBounds
(app/trade-value-chart/assets/value-model.js); this is the reference it must
match EXACTLY (tests/test_feasible_bench_bounds_parity.py). Decision
league-settings-001: the bounds are a rule over saved inputs, computed for
whatever league the reader picks, never one stored row per setup.

Rule "feasible-bench/1" (math review pending -- Jeremy 2026-10-07: "working
tool now, math review later"; see docs/claude-log.md):

Bench slots per team
    A size b is feasible when, at every position with a projection pool, the
    translation's rostered count (vorp_via_roster.rostered_for_teams: dedicated
    + flex + bench, the allocation that prices the derived curves) is strictly
    below the pool size, so the waiver line is a real projected player
    ("roster_determined"), not the bottom of the list ("insufficient_coverage").
    Pool = ESPN per-game projections for the scoring (players.json espn_ppg,
    what the browser reads). Range = the contiguous feasible run that starts at
    the smallest feasible b in [0, 14] (the stepper's UI range).

Bench share
    Per position the two-tier solve is linear in the share s, so "bench rate
    positive and starter rate above it" is an exact open interval:
        (bB / (bB + bS), (aB + bB) / T),  T = aB + bB + aS + bS   (det > 0)
    min = max(0.01, max_pos lo)  -- below any lo that position is withheld
                                    (the feasible-share fallback only searches
                                    downward, so it cannot rescue it);
    max = min(0.30, max_pos hi)  -- above a position's hi the fallback prices it
                                    at its highest feasible share; above every
                                    hi the slider would change nothing.
    Position edges rounded inward to 0.001 (product limits inclusive); default 0.15 clamped into [min, max]; empty ->
    None (fail closed). Tier exposures come from
    build_ddf_two_tier_leg.build_position_tiers at the reference shape for the
    team count -- the same pool the live slider calibrates.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path
from typing import Any, Optional

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "pipelines"))
sys.path.insert(0, str(REPO / "pipelines" / "lib"))

import build_ddf_two_tier_leg as two_tier  # noqa: E402
from vorp_translation.vorp_via_roster import rostered_for_teams  # noqa: E402

VERSION = "feasible-bench/1"
POSITION_ORDER = ["QB", "RB", "WR", "TE"]
DEFAULT_FLEX_ELIGIBLE = ["RB", "WR", "TE"]
SAVED_SETUP_SHAPE = {"QB": 1, "RB": 2, "WR": 3, "TE": 1, "FLEX": 1, "BENCH": 6}
BENCH_SLOTS_UI_MIN = 0
BENCH_SLOTS_UI_MAX = 14
BENCH_SHARE_PRODUCT_MIN = 0.01
BENCH_SHARE_PRODUCT_MAX = 0.30
BENCH_SHARE_DEFAULT = 0.15
BENCH_SHARE_STEP_INV = 1000


def _num_str(x: float) -> str:
    """JS String(number) for the values that appear in reasons."""
    if isinstance(x, int) or (isinstance(x, float) and x.is_integer()):
        return str(int(x))
    return repr(float(x))


def tier_share_interval(tier: Optional[dict]) -> Optional[dict]:
    if not tier:
        return None
    a_b, b_b = float(tier["aBench"]), float(tier["bBench"])
    a_s, b_s = float(tier["aStart"]), float(tier["bStart"])
    if not all(math.isfinite(v) for v in (a_b, b_b, a_s, b_s)):
        return None
    det = a_b * b_s - a_s * b_b
    total = a_b + b_b + a_s + b_s
    if det == 0 or (b_b + b_s) == 0 or total == 0:
        return None
    t_b = b_b / (b_b + b_s)
    t_e = (a_b + b_b) / total
    lo, hi = 0.0, 1.0
    gt_b = (det > 0) == (b_b + b_s > 0)
    lt_e = (det > 0) == (total > 0)
    if gt_b:
        lo = max(lo, t_b)
    else:
        hi = min(hi, t_b)
    if lt_e:
        hi = min(hi, t_e)
    else:
        lo = max(lo, t_e)
    if not (hi > lo):
        return None
    return {"lo": lo, "hi": hi}


def _share_ceil(x: float) -> float:
    return math.ceil(x * BENCH_SHARE_STEP_INV + 1e-7) / BENCH_SHARE_STEP_INV


def _share_floor(x: float) -> float:
    return math.floor(x * BENCH_SHARE_STEP_INV - 1e-7) / BENCH_SHARE_STEP_INV


def _flex_eligible(shape: dict) -> list[str]:
    return ["QB"] + DEFAULT_FLEX_ELIGIBLE if shape.get("SUPERFLEX") else list(DEFAULT_FLEX_ELIGIBLE)


def feasible_bench_bounds(teams: int, shape: Optional[dict], pool: dict,
                          tiers: Optional[dict] = None, scoring: Optional[str] = None) -> dict:
    """pool: {pos: [(key, value), ...]} projections; tiers: {pos: {aBench,..} | None}."""
    shape = shape or SAVED_SETUP_SHAPE
    slots = {pos: int(shape[pos]) for pos in POSITION_ORDER}
    flex_count = int(shape["FLEX"])
    flex_elig = _flex_eligible(shape)
    ranked = {pos: sorted(((k, float(v)) for k, v in pool.get(pos, [])), key=lambda r: -r[1])
              for pos in POSITION_ORDER}
    reasons: list[str] = []

    bench_slots = None
    min_b = max_b = None
    binding = None
    for b in range(BENCH_SLOTS_UI_MIN, BENCH_SLOTS_UI_MAX + 1):
        roster = rostered_for_teams(teams, b, flex_count, ranked=ranked, slots=slots,
                                    flex_eligible=flex_elig)
        short = None
        for pos in POSITION_ORDER:
            n = len(ranked[pos])
            if n and roster[pos]["rostered"] >= n:
                short = {"pos": pos, "rostered": roster[pos]["rostered"], "pool": n, "bench": b}
                break
        if not short:
            if min_b is None:
                min_b, binding = b, None
            max_b = b
        elif min_b is not None:
            binding = short
            break
        elif binding is None:
            binding = short
    if min_b is None:
        reasons.append(
            f"bench slots: no bench size in {BENCH_SLOTS_UI_MIN}-{BENCH_SLOTS_UI_MAX} leaves a waiver "
            f"player at {binding['pos']} ({binding['rostered']} rostered of {binding['pool']} "
            f"projected at bench {binding['bench']})")
    else:
        if binding:
            why = (f"max {max_b}: at bench {binding['bench']} {binding['pos']} would roster "
                   f"{binding['rostered']} of {binding['pool']} projected players (no waiver player left)")
        else:
            why = (f"every bench size in {BENCH_SLOTS_UI_MIN}-{BENCH_SLOTS_UI_MAX} leaves a waiver "
                   f"player at every position")
        bench_slots = {"min": min_b, "max": max_b, "uiMin": BENCH_SLOTS_UI_MIN,
                       "uiMax": BENCH_SLOTS_UI_MAX, "binding": binding, "reason": why}
        reasons.append("bench slots: " + why)

    bench_share = None
    share_intervals = None
    if not tiers:
        bench_share = {"min": BENCH_SHARE_PRODUCT_MIN, "max": BENCH_SHARE_PRODUCT_MAX,
                       "default": BENCH_SHARE_DEFAULT, "perPosition": None, "fallbackAbove": {},
                       "reason": "no tier exposures supplied: product range only"}
        reasons.append("bench share: " + bench_share["reason"])
    else:
        per_position: dict[str, Any] = {}
        lo_max = hi_max = -math.inf
        lo_pos = hi_pos = None
        empty: list[str] = []
        for pos in POSITION_ORDER:
            iv = tier_share_interval(tiers.get(pos))
            per_position[pos] = iv
            if not iv:
                if tiers.get(pos):
                    empty.append(pos)
                continue
            if iv["lo"] > lo_max:
                lo_max, lo_pos = iv["lo"], pos
            if iv["hi"] > hi_max:
                hi_max, hi_pos = iv["hi"], pos
        share_intervals = per_position
        if empty or lo_pos is None:
            where = "/".join(empty) if empty else "any position"
            reasons.append(f"bench share: no feasible share at {where} "
                           f"(starter rate never exceeds a positive bench rate)")
        else:
            # Position edges are OPEN (rounded strictly inside); the product
            # limits are inclusive.
            lo = max(BENCH_SHARE_PRODUCT_MIN, _share_ceil(lo_max))
            hi = min(BENCH_SHARE_PRODUCT_MAX, _share_floor(hi_max))
            if not (hi > lo):
                reasons.append(f"bench share: interval empty after rounding ({_num_str(lo)} to {_num_str(hi)})")
            else:
                fallback_above = {pos: _share_floor(per_position[pos]["hi"]) for pos in POSITION_ORDER
                                  if per_position[pos] and per_position[pos]["hi"] < hi}
                dflt = min(hi, max(lo, BENCH_SHARE_DEFAULT))
                why = (f"min {_num_str(lo)}"
                       + (f" (below it {lo_pos}'s bench rate is not positive)"
                          if lo_max > BENCH_SHARE_PRODUCT_MIN else " (product floor)")
                       + f"; max {_num_str(hi)}"
                       + (" (above it no position's starter rate exceeds its bench rate)"
                          if hi_max < BENCH_SHARE_PRODUCT_MAX else " (product ceiling)"))
                bench_share = {"min": lo, "max": hi, "default": dflt, "perPosition": per_position,
                               "fallbackAbove": fallback_above, "minPosition": lo_pos,
                               "maxPosition": hi_pos, "reason": why}
                reasons.append("bench share: " + why)
    return {"version": VERSION, "teams": teams, "scoring": scoring,
            "benchSlots": bench_slots, "benchShare": bench_share,
            "shareIntervals": share_intervals, "reasons": reasons}


def reference_tiers(pool: dict, teams: int) -> dict:
    """Two-tier exposures at the reference shape for `teams` (the live slider's pool)."""
    lists = {pos: [{"id": str(k), "x": float(v)} for k, v in pool.get(pos, [])] for pos in POSITION_ORDER}
    built = two_tier.build_position_tiers(lists, teams, two_tier.REF_SLOTS, two_tier.REF_FLEX_COUNT,
                                          two_tier.REF_FLEX_ELIGIBLE, two_tier.bench_mix_for_teams(teams))
    out = {}
    for pos in POSITION_ORDER:
        t = built["tiers"].get(pos)
        out[pos] = None if t is None else {"aBench": t["a_bench"], "bBench": t["b_bench"],
                                           "aStart": t["a_start"], "bStart": t["b_start"]}
    return out


def projection_pool(scoring: str, players_path: Optional[Path] = None) -> dict:
    from vorp_translation.unified import load_projection_ranked
    return {pos: [(k, v) for k, _n, v in rows]
            for pos, rows in load_projection_ranked(scoring, players_path).items()}


def main() -> int:
    import json
    for scoring in ("standard", "half_ppr", "ppr"):
        pool = projection_pool(scoring)
        for teams in (8, 10, 12, 14):
            out = feasible_bench_bounds(teams, None, pool, reference_tiers(pool, teams), scoring)
            print(json.dumps({"scoring": scoring, "teams": teams,
                              "benchSlots": [out["benchSlots"]["min"], out["benchSlots"]["max"]]
                              if out["benchSlots"] else None,
                              "benchShare": [out["benchShare"]["min"], out["benchShare"]["max"],
                                             out["benchShare"]["default"]]
                              if out["benchShare"] else None}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
