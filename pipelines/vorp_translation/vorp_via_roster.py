#!/usr/bin/env python3
"""VORP via roster settings (JEG-32).

Jeremy 2026-10-01:
- Chart values + roster settings → implied positional weights
- Roster settings dictate the waiver line (not inferred from curve shape)
- That logic gets us to VORP

This is the same as DDF, but starting from published values instead of PPG:
  DDF: PPG + Roster → Tiers → Waiver line → VORP → Weights → Value
  Trade charts: Published Value + Roster → Tiers → Waiver line → VORP → Weights

The roster settings are KNOWN (not inferred). For 12-team:
  QB: 12 starters → waiver line = QB13's value
  RB: 24 starters (+ flex) → waiver line = RB25's value (or first non-rostered)
  WR: 36 starters (+ flex) → waiver line = WR37's value
  TE: 12 starters → waiver line = TE13's value
"""

from __future__ import annotations
import json
import sys
import math
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "pipelines"))
sys.path.insert(0, str(REPO / "pipelines" / "lib"))

from build_ddf_two_tier_leg import (
    REF_SLOTS,
    REF_FLEX_COUNT,
    REF_FLEX_ELIGIBLE,
    POSITIONS,
)
# Canonical identity: all name resolution goes through the naming table via
# player_key (standing rule 2026-10-02; JEG-75). Never match on raw strings.
from canonical_players import Registry, resolve as _resolve_key


def load_ranked_values(source: str, combo_key: str) -> dict[str, list[tuple[str, float]]]:
    """Load publisher values as ranked lists per position."""
    fixture = json.loads((REPO / "data" / "fixtures" / "current" / "comparison-sources-data.json").read_text())
    players = json.loads((REPO / "data" / "fixtures" / "current" / "players.json").read_text())
    # Canonical registry built from the naming table (players.json). Identity
    # resolves through player_key -- never raw strings, so 'jaxon smithnjigba'
    # (fixture slug) matches 'Jaxon Smith-Njigba'. (JEG-75 standing rule;
    # the old exact-lowercase match silently dropped such players, breaking
    # parity with unified.load_native_values.)
    reg = Registry([
        {"player_key": p["player_key"], "full_name": p["name"],
         "position": p.get("pos"), "active": True}
        for p in players["players"] if p.get("player_key") is not None
    ])

    sdata = fixture["sources"].get(source, {})
    combo = sdata.get("combos", {}).get(combo_key, {})
    native = combo.get("native", {})

    by_pos: dict[str, list[tuple[str, float]]] = {p: [] for p in POSITIONS}
    for name, val in native.items():
        if val is None:
            continue
        key = _resolve_key(name, registry=reg)
        if key is None:
            # Unresolvable identity -> excluded (fail-closed upstream).
            continue
        pos = reg.by_key[key]["position"]
        if pos in POSITIONS:
            by_pos[pos].append((name, float(val)))

    for pos in by_pos:
        by_pos[pos].sort(key=lambda x: -x[1])

    return by_pos


def apportion(weights: dict[str, float], total: int) -> dict[str, int]:
    """Highest-averages allocation: exact totals and monotone seat counts.

    Stable position order breaks ties. Unlike independent rounding, adding
    a league slot never removes an already allocated slot.
    """
    if total < 0 or int(total) != total:
        raise ValueError("slot total must be a nonnegative integer")
    if any(not math.isfinite(w) or w < 0 for w in weights.values()):
        raise ValueError("allocation weights must be finite and nonnegative")
    result = {pos: 0 for pos in POSITIONS}
    eligible = [pos for pos in POSITIONS if weights.get(pos, 0) > 0]
    if total and not eligible:
        raise ValueError("positive slot total requires positive weights")
    for _ in range(total):
        pos = max(eligible, key=lambda p: weights[p] / (result[p] + 1))
        result[pos] += 1
    return result


def allocate_superflex(ranked: dict[str, list[tuple[str, float]]] | None,
                       teams: int, superflex_count: int = 0,
                       slots: dict[str, int] = None) -> dict[str, int]:
    """Who fills the superflex slots (JEG332-SUPERFLEX-FLEX, option A).

    Jeremy 2026-10-08: a superflex league has a DEDICATED superflex slot,
    filled by the best value with QBs eligible -- no per-position slot
    weighting (the slots[pos] weight in allocate_flex_vorp_weighted is what
    kept QBs out of a QB-eligible flex). Order of filling: dedicated slots,
    then superflex, then flex, then bench.

    With ranked values: the teams x superflex_count best players left after
    the dedicated starters, across QB/RB/WR/TE, by value (ties: position
    order QB, RB, WR, TE, then rank). Without ranked values (the
    slot-proportional baseline that only seeds waiver estimates):
    apportioned by dedicated slots, like the flex baseline.

    superflex_count 0 returns all zeros, so every default roster is
    unchanged. Mirrored exactly by value-model.js translationSuperflex.
    """
    if slots is None:
        slots = REF_SLOTS
    if superflex_count < 0 or int(superflex_count) != superflex_count:
        raise ValueError("superflex count must be a nonnegative integer")
    total = teams * int(superflex_count)
    if not total:
        return {pos: 0 for pos in POSITIONS}
    if ranked is None:
        return apportion({pos: slots.get(pos, 0) for pos in POSITIONS}, total)
    candidates = []
    for pos_idx, pos in enumerate(POSITIONS):
        players = ranked.get(pos, [])
        if any(not math.isfinite(val) for _, val in players):
            raise ValueError(f"{pos}: publisher values must be finite")
        n_ded = teams * slots.get(pos, 0)
        for i, (_pid, val) in enumerate(players[n_ded:]):
            candidates.append((-val, pos_idx, i, pos))
    candidates.sort()
    out = {pos: 0 for pos in POSITIONS}
    for _neg, _pi, _i, pos in candidates[:total]:
        out[pos] += 1
    return out


def allocate_flex_vorp_weighted(ranked: dict[str, list[tuple[str, float]]],
                               teams: int, flex_count: int = None,
                               waiver_estimates: dict[str, float] = None,
                               slots: dict[str, int] = None,
                               flex_eligible: list[str] = None,
                               superflex_alloc: dict[str, int] = None) -> dict[str, int]:
    """Allocate flex slots weighted by VORP at the margin.
    
    VORP-extended logic: positions with higher VORP at the flex margin
    get more flex slots. This reflects economic reality: if WRs have
    more value available at the flex tier in PPR, they should occupy
    more flex spots.
    
    Math:
      1. Estimate VORP for marginal players (around flex cutoff)
      2. flex[pos] ∝ slots[pos] × avg_vorp_at_margin[pos]
      3. Normalize to sum to teams × flex_count
    
    Args:
        ranked: {pos: [(pid, value), ...]} sorted descending
        teams: league size
        flex_count: flex slots per team
        waiver_estimates: {pos: estimated_waiver_value} for VORP calc
                         (if None, uses 0 — pure value weighting)
        slots: dedicated starters per team by position (default REF_SLOTS).
               JEG-332: the browser port (value-model.js
               translatePublishedVorp) passes the chart's roster steppers;
               the default keeps server output unchanged.
        flex_eligible: flex-eligible positions (default REF_FLEX_ELIGIBLE)
        superflex_alloc: {pos: superflex starters} already taken
               (allocate_superflex); flex candidates start after them.
               Default none, so the window is unchanged.

    Returns:
        {pos: flex_slots}
    """
    if flex_count is None:
        flex_count = REF_FLEX_COUNT
    if slots is None:
        slots = REF_SLOTS
    if flex_eligible is None:
        flex_eligible = REF_FLEX_ELIGIBLE
    if teams <= 0 or int(teams) != teams or flex_count < 0 or int(flex_count) != flex_count:
        raise ValueError("teams must be positive and flex count nonnegative integers")
    if waiver_estimates is None:
        waiver_estimates = {pos: 0.0 for pos in POSITIONS}
    
    total_flex = teams * flex_count
    
    # For each flex-eligible position, compute avg VORP of marginal players
    # Marginal = players ranked around the expected flex range
    # (dedicated starters + 1) to (dedicated + expected flex + bench buffer)
    weights = {}
    for pos in flex_eligible:
        n_ded = teams * slots.get(pos, 0)
        n_taken = n_ded + (superflex_alloc or {}).get(pos, 0)
        players = ranked.get(pos, [])
        waiver = waiver_estimates.get(pos, 0.0)
        if not math.isfinite(waiver) or any(not math.isfinite(val) for _, val in players):
            raise ValueError(f"{pos}: publisher values and waiver must be finite")
        
        # Only non-dedicated players can fill flex; the league's total flex
        # capacity bounds the candidate window at every eligible position.
        start_idx = n_taken
        end_idx = min(len(players), n_taken + total_flex)
        candidates = players[start_idx:end_idx]
        
        if not candidates:
            weights[pos] = 0.0
            continue
        
        # Average VORP of candidates
        vorps = [max(0.0, val - waiver) for _, val in candidates]
        # Missing candidates contribute no observed surplus, not extra weight.
        avg_vorp = sum(vorps) / total_flex if total_flex else 0.0
        
        # Weight = slots × avg_vorp (economic weight)
        weights[pos] = slots.get(pos, 0) * avg_vorp

    if sum(weights.values()) <= 0:
        weights = {pos: slots.get(pos, 0) for pos in flex_eligible}
    return apportion(weights, total_flex)


def bench_for_teams(teams: int, bench_per_team: float = 6.0) -> dict[str, int]:
    """Scale bench by teams and bench size.
    
    Math: bench[pos] = BENCH_MIX_12[pos] × (teams/12) × (bench_per_team/6.67)
    
    BENCH_MIX_12 assumes 6.67 bench/team. We rescale to the actual
    bench size (ESPN default 6.0).
    
    Args:
        teams: league size
        bench_per_team: bench spots per team (ESPN default 6.0)
    
    Returns:
        {pos: bench_slots}
    """
    from build_ddf_two_tier_leg import BENCH_MIX_12
    
    total = teams * bench_per_team
    if not math.isfinite(total) or total < 0:
        raise ValueError("bench capacity must be finite and nonnegative")
    return apportion(BENCH_MIX_12, int(total + 0.5))


def rostered_for_teams(teams: int, bench_per_team: float = 6.0,
                       flex_count: int = None,
                       ranked: dict[str, list[tuple[str, float]]] = None,
                       use_vorp_weighting: bool = True,
                       slots: dict[str, int] = None,
                       flex_eligible: list[str] = None,
                       superflex_count: int = 0) -> dict[str, dict[str, int]]:
    """Compute rostered players per position with flexible math.
    
    VORP-extended logic: if ranked values are provided, flex is allocated
    weighted by VORP at the margin (not just slots). This makes the
    allocation scoring-aware: PPR shifts flex toward WR, standard toward RB.
    
    All values scale with teams, bench_per_team, and flex_count.
    This is a one-pass bootstrap using preliminary slot-proportional waiver
    estimates. Final waiver lines are recomputed, not iterated to convergence.
    
    Args:
        teams: league size
        bench_per_team: bench spots per team
        flex_count: flex slots per team
        ranked: {pos: [(pid, value), ...]} for VORP-weighted flex
        use_vorp_weighting: if False, use pure slot-proportional
        slots: dedicated starters per team by position (default REF_SLOTS)
        flex_eligible: flex-eligible positions (default REF_FLEX_ELIGIBLE)
        superflex_count: dedicated superflex slots per team (default 0;
               JEG332-SUPERFLEX-FLEX option A, see allocate_superflex)

    Returns:
        {pos: {'dedicated': int, 'superflex': int, 'flex': int, 'bench': int,
               'rostered': int}}
    """
    if flex_count is None:
        flex_count = REF_FLEX_COUNT
    if slots is None:
        slots = REF_SLOTS
    if flex_eligible is None:
        flex_eligible = REF_FLEX_ELIGIBLE
    if teams <= 0 or int(teams) != teams or flex_count < 0 or int(flex_count) != flex_count:
        raise ValueError("teams must be positive and flex count nonnegative integers")
    
    # Flex allocation: VORP-weighted if we have values, else slot-proportional
    if ranked is not None and use_vorp_weighting:
        # First, estimate waiver lines via slot-proportional baseline
        baseline = rostered_for_teams(teams, bench_per_team, flex_count,
                                      ranked=None, use_vorp_weighting=False,
                                      slots=slots, flex_eligible=flex_eligible,
                                      superflex_count=superflex_count)
        waiver_est = {}
        for pos in POSITIONS:
            players = ranked.get(pos, [])
            n_rost = baseline[pos]['rostered']
            if len(players) > n_rost:
                waiver_est[pos] = players[n_rost][1]
            elif players:
                waiver_est[pos] = players[-1][1]
            else:
                waiver_est[pos] = 0.0
        
        sf_alloc = allocate_superflex(ranked, teams, superflex_count, slots)
        flex_alloc = allocate_flex_vorp_weighted(ranked, teams, flex_count, waiver_est,
                                                 slots=slots, flex_eligible=flex_eligible,
                                                 superflex_alloc=sf_alloc)
    else:
        sf_alloc = allocate_superflex(None, teams, superflex_count, slots)
        # Slot-proportional fallback
        flex_alloc = apportion({pos: slots.get(pos, 0) for pos in flex_eligible},
                              teams * flex_count)
    
    bench_alloc = bench_for_teams(teams, bench_per_team)
    
    result = {}
    for pos in POSITIONS:
        dedicated = teams * slots.get(pos, 0)
        superflex = sf_alloc.get(pos, 0)
        flex = flex_alloc.get(pos, 0)
        bench = bench_alloc.get(pos, 0)
        result[pos] = {
            'dedicated': dedicated,
            'superflex': superflex,
            'flex': flex,
            'bench': bench,
            'rostered': dedicated + superflex + flex + bench,
        }
    
    return result


def roster_waiver_line(ranked: list[tuple[str, float]], n_rostered: int) -> tuple[float, str]:
    """Get waiver line value from roster settings.
    
    The waiver line is the value of the first non-ROSTERED player.
    Rostered = dedicated starters + flex starters + bench.
    
    Args:
        ranked: [(player_id, value), ...] sorted descending by value
        n_rostered: total number of rostered players for this position
    
    Returns: (waiver_value, method)
    """
    if len(ranked) <= n_rostered:
        # They don't rank enough players to reach waiver
        return ranked[-1][1] if ranked else 0.0, "insufficient_coverage"
    
    # Waiver line = first non-rostered player's value
    return ranked[n_rostered][1], "roster_determined"


def compute_vorp_via_roster(source: str, teams: int = 12, 
                            scoring: str = "half_ppr",
                            bench_per_team: float = 6.0) -> dict:
    """Compute VORP using roster settings to dictate waiver line.
    
    Steps:
    1. Load their ranked values per position
    2. Compute rostered per position via flexible math:
       - Dedicated: teams × slots
       - Flex: proportional to publisher marginal VORP times dedicated slots
       - Bench: scaled by teams and bench_per_team
    3. Waiver line = first non-rostered
    4. VORP = value - waiver_line
    5. Implied positional weights = sum(VORP) per position / total
    """
    prefix = {"half_ppr": "half", "ppr": "full"}.get(scoring, scoring)
    combo_key = f"{prefix}_{teams}"
    ranked = load_ranked_values(source, combo_key)
    
    # Flexible roster math with VORP-weighted flex (scoring-aware)
    roster = rostered_for_teams(teams, bench_per_team, ranked=ranked,
                                use_vorp_weighting=True)
    
    result = {
        "source": source,
        "teams": teams,
        "scoring": scoring,
        "bench_per_team": bench_per_team,
        "positions": {},
    }
    
    total_vorp = 0.0
    for pos in POSITIONS:
        players = ranked.get(pos, [])
        if not players:
            continue
        
        r = roster[pos]
        n_rostered = r['rostered']
        
        waiver_val, method = roster_waiver_line(players, n_rostered)
        
        # VORP for each player
        vorp_list = []
        for pid, val in players:
            vorp = max(0.0, val - waiver_val)
            vorp_list.append((pid, val, vorp))
        
        pos_vorp_sum = sum(v for _, _, v in vorp_list)
        total_vorp += pos_vorp_sum
        
        result["positions"][pos] = {
            "n_players": len(players),
            "n_dedicated": r['dedicated'],
            "n_flex": r['flex'],
            "n_starters": r['dedicated'] + r['flex'],
            "n_bench": r['bench'],
            "n_rostered": n_rostered,
            "waiver_line_value": round(waiver_val, 2),
            "waiver_method": method,
            "max_value": round(players[0][1], 2) if players else 0,
            "max_vorp": round(max(v for _, _, v in vorp_list), 2) if vorp_list else 0,
            "total_vorp": round(pos_vorp_sum, 2),
            "top_5": [
                {"player": pid, "value": round(val, 1), "vorp": round(vorp, 1)}
                for pid, val, vorp in vorp_list[:5]
            ],
        }
    
    # Implied positional weights
    for pos in result["positions"]:
        pos_vorp = result["positions"][pos]["total_vorp"]
        weight = pos_vorp / total_vorp if total_vorp > 0 else 0
        result["positions"][pos]["implied_weight"] = round(weight, 4)
    
    result["total_vorp"] = round(total_vorp, 2)
    return result


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default="usatoday")
    parser.add_argument("--teams", type=int, default=12)
    parser.add_argument("--scoring", choices=("standard", "half_ppr", "ppr"), default="half_ppr")
    args = parser.parse_args()
    
    result = compute_vorp_via_roster(args.source, args.teams, args.scoring)
    
    print(f"\nVORP via Roster Settings: {args.source} ({args.teams}t)")
    print("=" * 70)
    print("\nWaiver lines dictated by roster construction:")
    for pos in ["QB", "RB", "WR", "TE"]:
        p = result["positions"].get(pos, {})
        if not p:
            continue
        print(f"\n  {pos}:")
        print(f"    Ranked: {p['n_players']}, Dedicated: {p['n_dedicated']}, "
              f"Flex: {p['n_flex']}, Starters: {p['n_starters']}, "
              f"Bench: {p['n_bench']}, Rostered: {p['n_rostered']}")
        print(f"    Waiver line value: {p['waiver_line_value']} ({p['waiver_method']})")
        print(f"    Max value: {p['max_value']} → Max VORP: {p['max_vorp']}")
        print(f"    Total VORP: {p['total_vorp']}, Implied weight: {p['implied_weight']:.1%}")
        print(f"    Top 5:")
        for t in p["top_5"]:
            print(f"      {t['player']}: value={t['value']} vorp={t['vorp']}")
    
    print(f"\nTotal VORP across positions: {result['total_vorp']}")


if __name__ == "__main__":
    main()
