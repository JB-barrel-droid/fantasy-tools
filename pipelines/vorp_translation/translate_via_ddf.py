#!/usr/bin/env python3
"""VORP translation using the actual DDF pipeline (JEG-32).

Jeremy 2026-10-01: "can we essentially get to their implied VORP and then
build them up exactly the same way we do the projection side sources?"

Yes. This prototype:
1. Gets publisher values (USA Today) from local fixture (Supabase in prod)
2. Infers their implicit replacement per position (fluid)
3. Computes their VORP = value - their_replacement
4. Feeds their VORP into build_position_tiers (as x, instead of PPG)
5. Calibrates with OUR pie from DDF legs (fluid per combination)
6. Prices via price_for_projection (exact same function as projections)

Their ordering + our methodology. Same code path.
"""

from __future__ import annotations
import json
import sys
from pathlib import Path

# Import DDF pipeline functions
REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "pipelines"))
sys.path.insert(0, str(REPO / "pipelines" / "vorp_translation"))

from build_ddf_two_tier_leg import (
    build_position_tiers,
    calibrate_position,
    price_for_projection,
    REF_SLOTS,
    REF_FLEX_COUNT,
    REF_FLEX_ELIGIBLE,
    bench_mix_for_teams,
    POSITIONS,
)
from infer_replacement import infer_replacement_level


def load_publisher_values(source: str, scoring: str = "half_ppr", teams: int = 12) -> dict[str, list[dict]]:
    """Load publisher native values by position from fixture.
    
    Returns: {pos: [{player_key, x: native_value}, ...]}
    """
    fixture = json.load(open(REPO / "data" / "fixtures" / "current" / "comparison-sources-data.json"))
    players = json.load(open(REPO / "data" / "fixtures" / "current" / "players.json"))
    pos_by_name = {p["name"].lower(): p["pos"] for p in players["players"]}
    
    combo_key = f"{scoring}_{teams}"
    # Map scoring names
    if scoring == "half_ppr":
        combo_key = f"half_{teams}"
    elif scoring == "ppr":
        combo_key = f"full_{teams}"
    elif scoring == "standard":
        combo_key = f"standard_{teams}"
    
    sdata = fixture["sources"].get(source, {})
    combo = sdata.get("combos", {}).get(combo_key, {})
    native = combo.get("native", {})
    
    by_pos: dict[str, list[dict]] = {p: [] for p in POSITIONS}
    for name, val in native.items():
        pos = pos_by_name.get(name.lower())
        if pos in POSITIONS and val is not None:
            # player_key: use name as key for prototype
            by_pos[pos].append({"id": name, "x": float(val)})
    
    return by_pos


def get_our_pie(scoring: str, teams: int, bench_share: float) -> dict[str, float]:
    """Get OUR positional pie from DDF legs for the active combination.
    
    Fluid: queries the actual DDF leg for this combination.
    """
    # Find the ESPN DDF leg for this combination
    import glob
    pattern = str(REPO / "data" / "ddf-two-tier" / f"ddf-*-espn-{scoring}-{teams}t-*")
    legs = sorted(glob.glob(pattern))
    if not legs:
        # Fallback to known values
        return {"QB": 29.5, "RB": 70.0, "WR": 40.8, "TE": 21.3}
    
    leg = json.load(open(f"{legs[-1]}/ddf_leg.json"))
    pie = {}
    for pos in POSITIONS:
        cal = leg.get("calibration", {}).get(pos, {})
        # Pie is the total value allocated to this position
        # Use starter_raw + bench_raw, or infer from calibration
        pie[pos] = cal.get("starter_raw", 0) + cal.get("bench_raw", 0)
        if pie[pos] <= 0:
            # Fallback: use max value * estimated count
            pie[pos] = {"QB": 29.5, "RB": 70.0, "WR": 40.8, "TE": 21.3}[pos]
    
    return pie


def translate_via_ddf(source: str, scoring: str = "half_ppr", teams: int = 12,
                      bench_share: float = 0.15) -> dict:
    """Translate publisher values through the DDF pipeline.
    
    Steps:
    1. Load their native values by position
    2. Infer their replacement per position (fluid)
    3. Their VORP = value - their_replacement
    4. Build tiers from their VORP (using DDF build_position_tiers)
    5. Calibrate with OUR pie (from DDF legs)
    6. Price via DDF price_for_projection
    """
    # Step 1: Load their values
    by_pos_raw = load_publisher_values(source, scoring, teams)
    
    # Step 2 & 3: Infer replacement, compute their VORP
    by_pos_vorp: dict[str, list[dict]] = {}
    inferences = {}
    for pos in POSITIONS:
        raw_list = by_pos_raw.get(pos, [])
        if not raw_list:
            continue
        values = [d["x"] for d in raw_list]
        inf = infer_replacement_level(values, pos)
        inferences[pos] = inf
        their_repl = inf["replacement_level"]
        
        # Their VORP = value - their_replacement
        vorp_list = [
            {"id": d["id"], "x": max(0.0, d["x"] - their_repl)}
            for d in raw_list
        ]
        # Filter to positive VORP only (they have value above their replacement)
        vorp_list = [d for d in vorp_list if d["x"] > 0]
        by_pos_vorp[pos] = vorp_list
    
    # Step 4: Build tiers from their VORP using DDF function
    pool = build_position_tiers(
        by_pos_vorp, teams, dict(REF_SLOTS), REF_FLEX_COUNT,
        list(REF_FLEX_ELIGIBLE), bench_mix_for_teams(teams)
    )
    
    # Step 5: Get OUR pie and calibrate
    our_pie = get_our_pie(scoring, teams, bench_share)
    calibration = {}
    for pos in POSITIONS:
        tier = pool["tiers"].get(pos)
        if tier is None:
            continue
        try:
            cal = calibrate_position(tier, our_pie[pos], bench_share)
            calibration[pos] = cal
        except ValueError as e:
            print(f"  Warning: {pos} calibration failed: {e}", file=sys.stderr)
    
    # Step 6: Price each player via DDF function
    translated = {}
    for pos in POSITIONS:
        cal = calibration.get(pos)
        if not cal:
            continue
        for d in by_pos_vorp.get(pos, []):
            val = price_for_projection(d["x"], cal)
            translated[d["id"]] = {
                "pos": pos,
                "their_vorp": round(d["x"], 2),
                "translated_value": round(val, 2),
            }
    
    return {
        "source": source,
        "scoring": scoring,
        "teams": teams,
        "inferences": inferences,
        "our_pie": our_pie,
        "translated": translated,
    }


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default="usatoday")
    parser.add_argument("--scoring", default="half_ppr")
    parser.add_argument("--teams", type=int, default=12)
    args = parser.parse_args()
    
    result = translate_via_ddf(args.source, args.scoring, args.teams)
    
    print(f"\nVORP Translation via DDF: {args.source} ({args.scoring}, {args.teams}t)")
    print("=" * 70)
    print("\nInferred replacements (their VORP baseline):")
    for pos, inf in result["inferences"].items():
        print(f"  {pos}: {inf['replacement_level']:.1f} "
              f"({inf['method']}, {inf['confidence']})")
    
    print(f"\nOur pie (positional totals from DDF):")
    for pos, pie in result["our_pie"].items():
        print(f"  {pos}: {pie:.1f}")
    
    # Show top 5 per position
    print(f"\nTop 5 translated values per position:")
    by_pos = {}
    for name, data in result["translated"].items():
        by_pos.setdefault(data["pos"], []).append((name, data))
    for pos in ["RB", "WR", "QB", "TE"]:
        players = sorted(by_pos.get(pos, []), 
                        key=lambda x: x[1]["translated_value"], reverse=True)[:5]
        print(f"\n  {pos}:")
        for name, data in players:
            print(f"    {name}: their_vorp={data['their_vorp']:.1f} "
                  f"-> translated={data['translated_value']:.1f}")


if __name__ == "__main__":
    main()
