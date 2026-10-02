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
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "pipelines"))

from build_ddf_two_tier_leg import (
    REF_SLOTS,
    REF_FLEX_COUNT,
    REF_FLEX_ELIGIBLE,
    bench_mix_for_teams,
    POSITIONS,
)


def load_ranked_values(source: str, combo_key: str) -> dict[str, list[tuple[str, float]]]:
    """Load publisher values as ranked lists per position."""
    fixture = json.load(open(REPO / "data" / "fixtures" / "current" / "comparison-sources-data.json"))
    players = json.load(open(REPO / "data" / "fixtures" / "current" / "players.json"))
    pos_by_name = {p["name"].lower(): p["pos"] for p in players["players"]}
    
    sdata = fixture["sources"].get(source, {})
    combo = sdata.get("combos", {}).get(combo_key, {})
    native = combo.get("native", {})
    
    by_pos: dict[str, list[tuple[str, float]]] = {p: [] for p in POSITIONS}
    for name, val in native.items():
        pos = pos_by_name.get(name.lower())
        if pos in POSITIONS and val is not None:
            by_pos[pos].append((name, float(val)))
    
    for pos in by_pos:
        by_pos[pos].sort(key=lambda x: -x[1])
    
    return by_pos


def allocate_flex_vorp_weighted(ranked: dict[str, list[tuple[str, float]]],
                               teams: int, flex_count: int = None,
                               waiver_estimates: dict[str, float] = None) -> dict[str, int]:
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
    
    Returns:
        {pos: flex_slots}
    """
    if flex_count is None:
        flex_count = REF_FLEX_COUNT
    if waiver_estimates is None:
        waiver_estimates = {pos: 0.0 for pos in POSITIONS}
    
    total_flex = teams * flex_count
    
    # For each flex-eligible position, compute avg VORP of marginal players
    # Marginal = players ranked around the expected flex range
    # (dedicated starters + 1) to (dedicated + expected flex + bench buffer)
    weights = {}
    for pos in REF_FLEX_ELIGIBLE:
        n_ded = teams * REF_SLOTS.get(pos, 0)
        players = ranked.get(pos, [])
        waiver = waiver_estimates.get(pos, 0.0)
        
        # Look at players 5 before to 10 after the dedicated cutoff
        # These are the flex candidates
        start_idx = max(0, n_ded - 5)
        end_idx = min(len(players), n_ded + 15)
        candidates = players[start_idx:end_idx]
        
        if not candidates:
            weights[pos] = 0.0
            continue
        
        # Average VORP of candidates
        vorps = [max(0.0, val - waiver) for _, val in candidates]
        avg_vorp = sum(vorps) / len(vorps) if vorps else 0.0
        
        # Weight = slots × avg_vorp (economic weight)
        weights[pos] = REF_SLOTS.get(pos, 0) * avg_vorp
    
    total_weight = sum(weights.values())
    if total_weight <= 0:
        # Fall back to slot-proportional
        total_flex = teams * flex_count
        flex_slots = sum(REF_SLOTS.get(pos, 0) for pos in REF_FLEX_ELIGIBLE)
        result = {}
        for pos in POSITIONS:
            if pos not in REF_FLEX_ELIGIBLE:
                result[pos] = 0
            else:
                raw = total_flex * REF_SLOTS.get(pos, 0) / flex_slots
                result[pos] = int(raw + 0.5)
        diff = total_flex - sum(result.values())
        if diff != 0:
            largest = max(REF_FLEX_ELIGIBLE, key=lambda p: REF_SLOTS.get(p, 0))
            result[largest] += diff
        return result
    
    # Allocate proportionally to weights
    result = {}
    for pos in POSITIONS:
        if pos not in REF_FLEX_ELIGIBLE:
            result[pos] = 0
        else:
            raw = total_flex * weights[pos] / total_weight
            result[pos] = int(raw + 0.5)
    
    # Adjust for rounding
    diff = total_flex - sum(result.values())
    if diff != 0:
        # Adjust the position with highest weight
        largest = max(REF_FLEX_ELIGIBLE, key=lambda p: weights.get(p, 0))
        result[largest] += diff
    
    return result


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
    
    # BENCH_MIX_12 totals 80 = 6.67 per team
    base_per_team = sum(BENCH_MIX_12.values()) / 12
    
    result = {}
    for pos in POSITIONS:
        raw = BENCH_MIX_12[pos] * (teams / 12) * (bench_per_team / base_per_team)
        result[pos] = int(raw + 0.5)
    
    return result


def rostered_for_teams(teams: int, bench_per_team: float = 6.0,
                       flex_count: int = None,
                       ranked: dict[str, list[tuple[str, float]]] = None,
                       use_vorp_weighting: bool = True) -> dict[str, dict[str, int]]:
    """Compute rostered players per position with flexible math.
    
    VORP-extended logic: if ranked values are provided, flex is allocated
    weighted by VORP at the margin (not just slots). This makes the
    allocation scoring-aware: PPR shifts flex toward WR, standard toward RB.
    
    All values scale with teams, bench_per_team, and flex_count.
    
    Args:
        teams: league size
        bench_per_team: bench spots per team
        flex_count: flex slots per team
        ranked: {pos: [(pid, value), ...]} for VORP-weighted flex
        use_vorp_weighting: if False, use pure slot-proportional
    
    Returns:
        {pos: {'dedicated': int, 'flex': int, 'bench': int, 'rostered': int}}
    """
    if flex_count is None:
        flex_count = REF_FLEX_COUNT
    
    # Flex allocation: VORP-weighted if we have values, else slot-proportional
    if ranked is not None and use_vorp_weighting:
        # First, estimate waiver lines via slot-proportional baseline
        baseline = rostered_for_teams(teams, bench_per_team, flex_count,
                                      ranked=None, use_vorp_weighting=False)
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
        
        flex_alloc = allocate_flex_vorp_weighted(ranked, teams, flex_count, waiver_est)
    else:
        # Slot-proportional fallback
        total_flex = teams * flex_count
        flex_slots = sum(REF_SLOTS.get(pos, 0) for pos in REF_FLEX_ELIGIBLE)
        flex_alloc = {}
        for pos in POSITIONS:
            if pos not in REF_FLEX_ELIGIBLE:
                flex_alloc[pos] = 0
            else:
                raw = total_flex * REF_SLOTS.get(pos, 0) / flex_slots
                flex_alloc[pos] = int(raw + 0.5)
        # Adjust rounding
        diff = total_flex - sum(flex_alloc.values())
        if diff != 0:
            largest = max(REF_FLEX_ELIGIBLE, key=lambda p: REF_SLOTS.get(p, 0))
            flex_alloc[largest] += diff
    
    bench_alloc = bench_for_teams(teams, bench_per_team)
    
    result = {}
    for pos in POSITIONS:
        dedicated = teams * REF_SLOTS.get(pos, 0)
        flex = flex_alloc.get(pos, 0)
        bench = bench_alloc.get(pos, 0)
        result[pos] = {
            'dedicated': dedicated,
            'flex': flex,
            'bench': bench,
            'rostered': dedicated + flex + bench,
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
       - Flex: proportional to slot counts (scales with teams)
       - Bench: scaled by teams and bench_per_team
    3. Waiver line = first non-rostered
    4. VORP = value - waiver_line
    5. Implied positional weights = sum(VORP) per position / total
    """
    combo_key = f"half_{teams}" if scoring == "half_ppr" else f"{scoring}_{teams}"
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
    args = parser.parse_args()
    
    result = compute_vorp_via_roster(args.source, args.teams)
    
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
