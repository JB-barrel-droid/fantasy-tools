#!/usr/bin/env python3
"""VORP translation via DDF Phase B only (JEG-32).

Jeremy 2026-10-01: DDF has PPG → Roster → VORP → Weights → Value.
For trade charts, we infer their VORP from their Value + their Roster.
Then we run Phase B only: their VORP + our Calibration → our Value.

We do NOT run Phase A (build_position_tiers) with VORP inputs — that expects
PPG and breaks the tier economics. Instead:
1. Their ranking determines order
2. Our roster construction determines tiers (who starts/benches)
3. Their VORP provides the magnitudes
4. Our calibration prices them
"""

from __future__ import annotations
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "pipelines"))
sys.path.insert(0, str(REPO / "pipelines" / "vorp_translation"))

from build_ddf_two_tier_leg import (
    calibrate_position,
    price_for_projection,
    slice_exposures,
    REF_SLOTS,
    REF_FLEX_COUNT,
    REF_FLEX_ELIGIBLE,
    bench_mix_for_teams,
    POSITIONS,
    GLIDE_WIDTH_FRAC,
)
from infer_replacement import infer_replacement_level


def load_publisher_rankings(source: str, combo_key: str) -> dict[str, list[tuple[str, float]]]:
    """Load publisher values as ranked lists per position.
    
    Returns: {pos: [(player_id, native_value), ...]} sorted descending by value.
    The ranking is their judgment; the values give us magnitudes.
    """
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
    
    # Sort by value descending (their ranking)
    for pos in by_pos:
        by_pos[pos].sort(key=lambda x: -x[1])
    
    return by_pos


def apply_our_tiers(rankings: dict[str, list[tuple[str, float]]], 
                   their_vorp: dict[str, dict[str, float]],
                   teams: int) -> dict[str, dict]:
    """Apply OUR roster construction to THEIR rankings.
    
    Args:
        rankings: {pos: [(player_id, native_value), ...]} sorted by their value
        their_vorp: {pos: {player_id: vorp_value}} (their value - their replacement)
        teams: league size
    
    Returns:
        {pos: {"starters": [...], "bench": [...], "waiver": [...],
               "tier": {...}}} 
        where tier has the structure calibrate_position expects
    """
    # Determine starters/bench using OUR slots, THEIR ordering
    starters: set[str] = set()
    dedicated: set[str] = set()
    
    for pos in POSITIONS:
        n_start = teams * REF_SLOTS.get(pos, 0)
        for pid, _ in rankings.get(pos, [])[:n_start]:
            dedicated.add(pid)
            starters.add(pid)
    
    # Flex
    flex_pool = []
    for pos in POSITIONS:
        if pos not in REF_FLEX_ELIGIBLE:
            continue
        for pid, val in rankings.get(pos, []):
            if pid not in dedicated:
                # Use their VORP for flex ranking
                vorp = their_vorp.get(pos, {}).get(pid, 0)
                flex_pool.append((pid, vorp, pos))
    flex_pool.sort(key=lambda x: -x[1])
    for pid, _, _ in flex_pool[:teams * REF_FLEX_COUNT]:
        starters.add(pid)
    
    # Bench
    bench: set[str] = set()
    rostered = set(starters)
    bench_mix = bench_mix_for_teams(teams)
    for pos in POSITIONS:
        available = [(pid, their_vorp.get(pos, {}).get(pid, 0)) 
                    for pid, _ in rankings.get(pos, [])
                    if pid not in rostered]
        available.sort(key=lambda x: -x[1])
        for pid, _ in available[:bench_mix.get(pos, 0)]:
            bench.add(pid)
            rostered.add(pid)
    
    # Build tier structures for calibration
    # We need: a_bench, b_bench, a_start, b_start, surplus, rw, rs, tau
    # These are computed from the VORP values using DDF logic
    tiers = {}
    for pos in POSITIONS:
        vorp_dict = their_vorp.get(pos, {})
        if not vorp_dict:
            tiers[pos] = None
            continue
        
        # Sort by VORP descending
        sorted_ids = sorted(vorp_dict.keys(), key=lambda pid: -vorp_dict[pid])
        
        # Waiver line: first non-rostered player's VORP
        non_rostered = [pid for pid in sorted_ids if pid not in rostered]
        rw = vorp_dict[non_rostered[0]] if non_rostered else 0.0
        
        # Starter line: midpoint between worst starter and best bench
        s_vorps = [vorp_dict[pid] for pid in sorted_ids if pid in starters]
        b_vorps = [vorp_dict[pid] for pid in sorted_ids if pid in bench]
        if s_vorps and b_vorps:
            rs = (min(s_vorps) + max(b_vorps)) / 2
        elif s_vorps:
            rs = min(s_vorps)
        else:
            rs = rw + 1.0
        
        # Compute exposures using DDF slice_exposures (not naive)
        # This is the exact same logic as build_position_tiers
        tau = GLIDE_WIDTH_FRAC * (rs - rw) if rs > rw else 0.1
        
        a_bench = b_bench = a_start = b_start = surplus = 0.0
        for pid in sorted_ids:
            v = vorp_dict[pid]
            if not (v > rw):
                continue
            s = v - rw
            surplus += s
            # Use real DDF exposure slicing
            a, b = slice_exposures(v, rw, rs, tau)
            if pid in starters:
                a_start += a
                b_start += b
            elif pid in bench:
                a_bench += a
                b_bench += b
        
        tiers[pos] = {
            "a_bench": a_bench, "b_bench": b_bench,
            "a_start": a_start, "b_start": b_start,
            "surplus": surplus, "rw": rw, "rs": rs, "tau": tau,
            "starters": [pid for pid in sorted_ids if pid in starters],
            "bench": [pid for pid in sorted_ids if pid in bench],
        }
    
    return tiers


def get_our_pie(scoring: str, teams: int) -> dict[str, float]:
    """Get OUR positional pie from DDF legs (fluid per combination)."""
    import glob
    # Map scoring to leg naming
    scoring_map = {"half_ppr": "half_ppr", "ppr": "ppr", "standard": "standard"}
    s = scoring_map.get(scoring, scoring)
    pattern = str(REPO / "data" / "ddf-two-tier" / f"ddf-*-espn-{s}-{teams}t-*")
    legs = sorted(glob.glob(pattern))
    if not legs:
        return {"QB": 55.9, "RB": 373.4, "WR": 264.6, "TE": 46.1}
    
    leg = json.load(open(f"{legs[-1]}/ddf_leg.json"))
    pie = {}
    for pos in POSITIONS:
        cal = leg.get("calibration", {}).get(pos, {})
        pie[pos] = cal.get("starter_raw", 0) + cal.get("bench_raw", 0)
    return pie


def translate_phase_b(source: str, scoring: str = "half_ppr", teams: int = 12,
                      bench_share: float = 0.15) -> dict:
    """Translate via DDF Phase B only.
    
    1. Load their rankings
    2. Infer their replacement per position → their VORP
    3. Apply OUR tiers to THEIR ranking
    4. Calibrate with OUR pie (Phase B)
    5. Price via DDF price_for_projection
    """
    combo_key = f"half_{teams}" if scoring == "half_ppr" else f"{scoring}_{teams}"
    
    # Step 1: Their rankings
    rankings = load_publisher_rankings(source, combo_key)
    
    # Step 2: Infer their replacement, compute their VORP
    their_vorp: dict[str, dict[str, float]] = {}
    inferences = {}
    for pos in POSITIONS:
        vals = [v for _, v in rankings.get(pos, [])]
        if not vals:
            continue
        inf = infer_replacement_level(vals, pos)
        inferences[pos] = inf
        repl = inf["replacement_level"]
        their_vorp[pos] = {
            pid: max(0.0, val - repl) 
            for pid, val in rankings[pos]
        }
    
    # Step 3: Apply OUR tiers to THEIR ranking
    tiers = apply_our_tiers(rankings, their_vorp, teams)
    
    # Step 4: Calibrate with OUR pie (Phase B)
    our_pie = get_our_pie(scoring, teams)
    calibration = {}
    for pos in POSITIONS:
        tier = tiers.get(pos)
        if not tier or tier["surplus"] <= 0:
            continue
        try:
            cal = calibrate_position(tier, our_pie[pos], bench_share)
            calibration[pos] = cal
        except ValueError as e:
            print(f"  Warning {pos}: {e}", file=sys.stderr)
    
    # Step 5: Price via DDF
    translated = {}
    for pos in POSITIONS:
        cal = calibration.get(pos)
        if not cal:
            continue
        for pid, vorp in their_vorp.get(pos, {}).items():
            if vorp <= 0:
                continue
            val = price_for_projection(vorp, cal)
            translated[pid] = {
                "pos": pos,
                "their_vorp": round(vorp, 2),
                "translated_value": round(val, 2),
            }
    
    return {
        "source": source,
        "inferences": inferences,
        "our_pie": our_pie,
        "translated": translated,
        "n_translated": len(translated),
    }


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default="usatoday")
    args = parser.parse_args()
    
    result = translate_phase_b(args.source)
    
    print(f"\nVORP Translation (Phase B): {args.source}")
    print("=" * 70)
    print("\nTheir inferred replacements:")
    for pos, inf in result["inferences"].items():
        print(f"  {pos}: {inf['replacement_level']:.1f} ({inf['method']})")
    
    print(f"\nTranslated top 5 per position:")
    by_pos = {}
    for pid, data in result["translated"].items():
        by_pos.setdefault(data["pos"], []).append((pid, data))
    for pos in ["RB", "WR", "QB", "TE"]:
        top = sorted(by_pos.get(pos, []), 
                    key=lambda x: -x[1]["translated_value"])[:5]
        print(f"\n  {pos}:")
        for pid, data in top:
            print(f"    {pid}: vorp={data['their_vorp']:.1f} "
                  f"-> value={data['translated_value']:.1f}")
    
    print(f"\nTotal translated: {result['n_translated']}")


if __name__ == "__main__":
    main()
