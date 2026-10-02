#!/usr/bin/env python3
"""Unified VORP translation for as-published trade value sources (JEG-62).

Single module handling all as-published sources (USA Today, FantasyPros,
FantasyCalc, CBS). No per-source branching — the logic is identical.

Pipeline:
1. Load publisher native values
2. Compute rostered per position (flexible math, scales with teams)
3. Waiver line = first non-rostered player's value
4. VORP = native - waiver_line
5. Translate: vorp × (our_max / their_max_vorp)
6. Write all intermediates to Supabase

Usage:
    from vorp_translation.unified import translate_source
    result = translate_source('usatoday', scoring='half_ppr', teams=12, week=4)
"""

from __future__ import annotations
import json
import sys
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "pipelines"))

from build_ddf_two_tier_leg import (
    REF_SLOTS,
    REF_FLEX_COUNT,
    REF_FLEX_ELIGIBLE,
    POSITIONS,
    BENCH_MIX_12,
)

# Our positional maxes (embody our starter/bench/positional economics)
# These are the anchors for translation — our 0-70 scale per position
OUR_MAX = {
    'QB': 25.0,
    'RB': 70.0,
    'WR': 55.0,
    'TE': 30.0,
}


def bench_for_teams(teams: int, bench_per_team: float = 6.0) -> dict[str, int]:
    """Scale bench by teams and bench size."""
    base_per_team = sum(BENCH_MIX_12.values()) / 12
    return {
        pos: int(BENCH_MIX_12[pos] * (teams / 12) * (bench_per_team / base_per_team) + 0.5)
        for pos in POSITIONS
    }


def flex_for_teams(teams: int, flex_count: Optional[int] = None) -> dict[str, int]:
    """Allocate flex proportionally to slots (JEG-61 will make scoring-aware)."""
    if flex_count is None:
        flex_count = REF_FLEX_COUNT
    total_flex = teams * flex_count
    flex_slots = sum(REF_SLOTS.get(pos, 0) for pos in REF_FLEX_ELIGIBLE)
    result = {}
    for pos in POSITIONS:
        if pos not in REF_FLEX_ELIGIBLE:
            result[pos] = 0
        else:
            result[pos] = int(total_flex * REF_SLOTS.get(pos, 0) / flex_slots + 0.5)
    # Fix rounding
    diff = total_flex - sum(result.values())
    if diff:
        largest = max(REF_FLEX_ELIGIBLE, key=lambda p: REF_SLOTS.get(p, 0))
        result[largest] += diff
    return result


def rostered_for_teams(teams: int, bench_per_team: float = 6.0,
                       flex_count: Optional[int] = None) -> dict[str, dict]:
    """Compute rostered counts per position."""
    flex_alloc = flex_for_teams(teams, flex_count)
    bench_alloc = bench_for_teams(teams, bench_per_team)
    return {
        pos: {
            'dedicated': teams * REF_SLOTS.get(pos, 0),
            'flex': flex_alloc[pos],
            'bench': bench_alloc[pos],
            'rostered': teams * REF_SLOTS.get(pos, 0) + flex_alloc[pos] + bench_alloc[pos],
        }
        for pos in POSITIONS
    }


def load_native_values(source: str, scoring: str, teams: int,
                       fixture_path: Optional[Path] = None) -> dict[str, list[tuple[str, float]]]:
    """Load publisher native values as ranked lists per position.
    
    In production, this reads from Supabase source_trade_values.
    For now, reads from the local fixture.
    """
    if fixture_path is None:
        fixture_path = REPO / "data" / "fixtures" / "current" / "comparison-sources-data.json"
    players_path = REPO / "data" / "fixtures" / "current" / "players.json"
    
    fixture = json.loads(fixture_path.read_text())
    players = json.loads(players_path.read_text())
    pos_by_name = {p["name"].lower(): p["pos"] for p in players["players"]}
    
    combo_key = f"half_{teams}" if scoring == "half_ppr" else f"{scoring}_{teams}"
    sdata = fixture["sources"].get(source, {})
    native = sdata.get("combos", {}).get(combo_key, {}).get("native", {})
    
    by_pos: dict[str, list[tuple[str, float]]] = {p: [] for p in POSITIONS}
    for name, val in native.items():
        pos = pos_by_name.get(name.lower())
        if pos in POSITIONS and val is not None:
            by_pos[pos].append((name, float(val)))
    for pos in by_pos:
        by_pos[pos].sort(key=lambda x: -x[1])
    return by_pos


def translate_source(source: str, scoring: str = "half_ppr", teams: int = 12,
                     week: int = 4, bench_per_team: float = 6.0,
                     write_supabase: bool = False) -> dict:
    """Unified VORP translation for any as-published source.
    
    Args:
        source: usatoday, fantasypros, fantasycalc, cbs
        scoring: standard, half_ppr, ppr
        teams: 10, 12, 14
        week: NFL week
        bench_per_team: bench spots per team (ESPN default 6.0)
        write_supabase: if True, write intermediates to Supabase
    
    Returns:
        {
            'source': str,
            'positions': {pos: {...roster, waiver, vorp stats...}},
            'translated': {player_name: {'pos':, 'native':, 'vorp':, 'translated':}},
        }
    """
    ranked = load_native_values(source, scoring, teams)
    roster = rostered_for_teams(teams, bench_per_team)
    
    result = {
        'source': source,
        'scoring': scoring,
        'teams': teams,
        'week': week,
        'positions': {},
        'translated': {},
    }
    
    for pos in POSITIONS:
        players = ranked.get(pos, [])
        if not players:
            continue
        
        r = roster[pos]
        n_rostered = r['rostered']
        
        # Waiver line = first non-rostered
        if len(players) > n_rostered:
            waiver_val = players[n_rostered][1]
            method = 'roster_determined'
        elif players:
            waiver_val = players[-1][1]
            method = 'insufficient_coverage'
        else:
            waiver_val = 0.0
            method = 'no_players'
        
        # VORP per player
        vorp_list = [(pid, val, max(0.0, val - waiver_val)) for pid, val in players]
        max_vorp = max((v for _, _, v in vorp_list), default=0.0)
        total_vorp = sum(v for _, _, v in vorp_list)
        
        # Translate via our positional max
        scale = OUR_MAX[pos] / max_vorp if max_vorp > 0 else 0.0
        for pid, val, vorp in vorp_list:
            if vorp > 0:
                result['translated'][pid] = {
                    'pos': pos,
                    'native': round(val, 1),
                    'vorp': round(vorp, 1),
                    'translated': round(vorp * scale, 1),
                }
        
        result['positions'][pos] = {
            'n_dedicated': r['dedicated'],
            'n_flex': r['flex'],
            'n_bench': r['bench'],
            'n_rostered': n_rostered,
            'waiver_line_value': round(waiver_val, 2),
            'waiver_method': method,
            'max_vorp': round(max_vorp, 1),
            'total_vorp': round(total_vorp, 1),
            'scale_factor': round(scale, 3),
        }
    
    # Implied weights
    total = sum(p['total_vorp'] for p in result['positions'].values())
    for pos in result['positions']:
        w = result['positions'][pos]['total_vorp'] / total if total > 0 else 0
        result['positions'][pos]['implied_weight'] = round(w, 4)
    
    if write_supabase:
        _write_to_supabase(result)
    
    return result


def _write_to_supabase(result: dict):
    """Write intermediates to Supabase tables (JEG-62 schema)."""
    # TODO: Implement via sb.py
    # - publisher_roster_assumptions
    # - publisher_vorp
    # - publisher_translated_values
    pass


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Unified VORP translation")
    parser.add_argument("--source", required=True,
                        choices=["usatoday", "fantasypros", "fantasycalc", "cbs"])
    parser.add_argument("--scoring", default="half_ppr",
                        choices=["standard", "half_ppr", "ppr"])
    parser.add_argument("--teams", type=int, default=12)
    parser.add_argument("--week", type=int, default=4)
    args = parser.parse_args()
    
    result = translate_source(args.source, args.scoring, args.teams, args.week)
    
    print(f"\nVORP Translation: {args.source} ({args.scoring}, {args.teams}t, W{args.week})")
    print("=" * 70)
    for pos in ['QB', 'RB', 'WR', 'TE']:
        p = result['positions'].get(pos)
        if not p:
            continue
        print(f"\n{pos}: rostered={p['n_rostered']} waiver={p['waiver_line_value']} "
              f"max_vorp={p['max_vorp']} weight={p['implied_weight']:.1%}")
    
    print(f"\nTranslated {len(result['translated'])} players")


if __name__ == "__main__":
    main()
