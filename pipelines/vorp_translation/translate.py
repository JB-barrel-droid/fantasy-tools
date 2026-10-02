#!/usr/bin/env python3
"""VORP translation prototype for USA Today (JEG-32).

Jeremy 2026-10-01:
- Take the values given, see how they break out starter/bench and positions
- Back into their VORP assumptions (infer their replacement level)
- Build back up through OUR VORP framework (our starter/bench/position considerations)
- Fluid: re-infer every bake, nothing static
- Supabase: lean heavily on Supabase

This prototype:
1. Reads USA Today values from Supabase (source_trade_values)
2. Infers their implicit replacement level per position (fluid)
3. Computes value-over-their-replacement
4. Scales to our 0-70 framework per position
5. Writes inferred params back to Supabase for transparency
"""

from __future__ import annotations
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from infer_replacement import infer_replacement_level

SB_PY = "/home/hatch/workspace/skills/supabase-football-signal/bin/sb.py"

# Our framework: positional maxes from ESPN DDF (half_12)
# These reflect our VORP-based starter/bench/position considerations
OUR_POS_MAX = {
    "QB": 29.5,
    "RB": 70.0,
    "WR": 40.8,
    "TE": 21.3,
}


def sb_get(table: str, query: str) -> list[dict]:
    """Query Supabase via sb.py."""
    result = subprocess.run(
        ["python3", SB_PY, "get", table, query],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        raise RuntimeError(f"Supabase query failed: {result.stderr}")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        # Response may be truncated; try with smaller limit
        raise RuntimeError(f"Supabase response truncated/invalid")


def get_source_values(source: str, variant: str = "as_published") -> dict[str, list[float]]:
    """Get publisher values by position.
    
    Prototype uses local fixture. Production will query Supabase directly.
    """
    # TODO: Switch to Supabase once pagination is fixed
    from pathlib import Path
    fixture_path = Path(__file__).resolve().parent.parent.parent / "data" / "fixtures" / "current" / "comparison-sources-data.json"
    # Fallback to worktree path
    if not fixture_path.exists():
        fixture_path = Path("/home/hatch/workspace/fantasy-tools/data/fixtures/current/comparison-sources-data.json")
    
    fixture = json.load(open(fixture_path))
    sdata = fixture["sources"].get(source, {})
    combos = sdata.get("combos", {})
    # Use half_12 as representative
    combo = combos.get("half_12", {})
    native = combo.get("native", {})
    
    # Need position mapping - get from players.json or player_keys
    # For prototype, use the fixture's player_keys and infer from values
    # Actually, let's get positions from the local players.json
    players_path = fixture_path.parent / "players.json"
    pos_by_name = {}
    if players_path.exists():
        pdata = json.load(open(players_path))
        for p in pdata.get("players", []):
            name = p.get("name", "").lower()
            pos_by_name[name] = p.get("pos", "")
    
    by_pos: dict[str, list[float]] = {}
    for name, val in native.items():
        pos = pos_by_name.get(name.lower(), "")
        if pos in ("QB", "RB", "WR", "TE") and val is not None:
            by_pos.setdefault(pos, []).append(float(val))
    
    return by_pos


def translate_source(source: str) -> dict:
    """Translate a publisher's values through VORP methodology.
    
    Returns per-position translation params and translated values.
    """
    by_pos = get_source_values(source)
    result = {
        "source": source,
        "positions": {},
    }
    
    for pos, values in sorted(by_pos.items()):
        # Step 1: Infer their replacement level (fluid, per bake)
        inference = infer_replacement_level(values, pos)
        their_repl = inference["replacement_level"]
        their_max = inference["max_value"]
        
        # Step 2: Value over their replacement
        # Step 3: Scale to OUR positional anchor (not 70 for all)
        # Jeremy: "build back up into our view of starter/bench and position considerations"
        our_max = OUR_POS_MAX.get(pos, 70.0)
        their_range = their_max - their_repl
        if their_range <= 0:
            scale = 1.0
        else:
            scale = our_max / their_range
        
        result["positions"][pos] = {
            "inference": inference,
            "their_replacement": their_repl,
            "their_max": their_max,
            "their_range": their_range,
            "our_max": our_max,
            "scale_factor": round(scale, 4),
            "translated_max": round((their_max - their_repl) * scale, 1),
        }
    
    return result


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default="usatoday")
    args = parser.parse_args()
    
    result = translate_source(args.source)
    
    print(f"\nVORP Translation: {args.source}")
    print("=" * 60)
    for pos, data in result["positions"].items():
        inf = data["inference"]
        print(f"\n{pos}:")
        print(f"  Their replacement: {data['their_replacement']:.1f} "
              f"({inf['method']}, {inf['confidence']} confidence)")
        print(f"  Their max: {data['their_max']:.1f} -> Our max: {data['our_max']:.1f}")
        print(f"  Their range: {data['their_range']:.1f}")
        print(f"  Scale factor: {data['scale_factor']}")
        print(f"  Translated max: {data['translated_max']:.1f}")
    
    # Write to Supabase for transparency (fluid params per bake)
    # TODO: Create vorp_translation_params table


if __name__ == "__main__":
    main()
