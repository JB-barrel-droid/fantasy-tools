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


def roster_waiver_line(ranked: list[tuple[str, float]], n_starters: int, n_bench: int) -> tuple[float, str]:
    """Get waiver line value from roster settings.
    
    The waiver line is the value of the first non-ROSTERED player
    (not starter, not bench). Determined by roster construction.
    
    Args:
        ranked: [(player_id, value), ...] sorted descending by value
        n_starters: number of starting slots (teams * slots_per_team)
        n_bench: number of bench slots for this position
    
    Returns: (waiver_value, method)
    """
    n_rostered = n_starters + n_bench
    if len(ranked) <= n_rostered:
        # They don't rank enough players to reach waiver
        return ranked[-1][1] if ranked else 0.0, "insufficient_coverage"
    
    # Waiver line = first non-rostered player's value
    return ranked[n_rostered][1], "roster_determined"


def compute_vorp_via_roster(source: str, teams: int = 12, 
                            scoring: str = "half_ppr") -> dict:
    """Compute VORP using roster settings to dictate waiver line.
    
    Steps:
    1. Load their ranked values per position
    2. Apply roster settings: n_starters = teams * slots
    3. Waiver line = value at (n_starters + 1)th rank
    4. VORP = value - waiver_line
    5. Implied positional weights = sum(VORP) per position / total
    """
    combo_key = f"half_{teams}" if scoring == "half_ppr" else f"{scoring}_{teams}"
    ranked = load_ranked_values(source, combo_key)
    bench_mix = bench_mix_for_teams(teams)
    
    result = {
        "source": source,
        "teams": teams,
        "scoring": scoring,
        "positions": {},
    }
    
    total_vorp = 0.0
    for pos in POSITIONS:
        players = ranked.get(pos, [])
        if not players:
            continue
        
        n_start = teams * REF_SLOTS.get(pos, 0)
        n_bench = bench_mix.get(pos, 0)
        waiver_val, method = roster_waiver_line(players, n_start, n_bench)
        
        # VORP for each player
        vorp_list = []
        for pid, val in players:
            vorp = max(0.0, val - waiver_val)
            vorp_list.append((pid, val, vorp))
        
        pos_vorp_sum = sum(v for _, _, v in vorp_list)
        total_vorp += pos_vorp_sum
        
        result["positions"][pos] = {
            "n_players": len(players),
            "n_starters": n_start,
            "n_bench": n_bench,
            "n_rostered": n_start + n_bench,
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
        print(f"    Ranked: {p['n_players']}, Starters: {p['n_starters']}, "
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
