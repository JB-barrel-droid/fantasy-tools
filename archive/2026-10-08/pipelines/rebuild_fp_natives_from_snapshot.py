#!/usr/bin/env python3
"""Rebuild FantasyPros fixture natives from snapshot using native_value.

Root cause: the fixture's FP natives were built from the snapshot's `value`
field (which was flattened to 50.7 for JSN/Chase/Amon-Ra) instead of the
`native_value` field (which has the correct distinct values 55.4/57.1/54.0).

This script:
1. Loads the FP snapshot (2026-09-29)
2. Resolves player_name -> numeric player_key via players.json canonical names
3. Uses native_value (raw published) for each player
4. Applies quantile mapping per position (from reindex_comparison_section.py)
5. Updates the fixture's fantasypros section

Identity: numeric player_key is the join. Names are resolved through the
canonical players.json, not guessed.
"""
import json
import sys
from pathlib import Path
from collections import defaultdict

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "pipelines"))
from reindex_comparison_section import quantile_map

def normalize(name):
    """Normalize for matching: lowercase, remove apostrophes/periods/hyphens."""
    return name.lower().replace("'", "").replace(".", "").replace("-", "")

def load_json(path):
    with open(path) as f:
        return json.load(f)

def main():
    fixture_path = REPO / "data/fixtures/current/comparison-sources-data.json"
    fixture = load_json(fixture_path)
    
    # Load snapshot
    snapshot_path = REPO / "data/raw/sources/fantasypros/2026-09-29/snapshot.json"
    snapshot = load_json(snapshot_path)
    
    # Load players for canonical name -> key mapping
    players_path = REPO / "data/fixtures/current/players.json"
    players = load_json(players_path)
    name_to_key = {}
    key_to_pos = {}
    for p in players["players"]:
        name = p.get("name", "")
        key = p.get("player_key")
        if name and key:
            name_to_key[normalize(name)] = key
            key_to_pos[key] = p.get("pos")
    
    print(f"Loaded {len(name_to_key)} canonical players")
    
    # Build slug -> key from fixture (for output)
    fixture_key_by_slug = fixture.get("player_keys", {})
    key_to_slug = {v: k for k, v in fixture_key_by_slug.items()}
    
    # Build FP natives from snapshot using native_value
    fp_natives = {}  # key -> native_value
    combos_to_build = ["half_12", "full_12", "standard_12"]
    scoring_map = {"half_12": "half_ppr", "full_12": "ppr", "standard_12": "standard"}
    
    # Get ESPN anchors per combo for quantile mapping
    espn_anchors = {}
    for combo_name in combos_to_build:
        espn_combo = fixture["sources"]["espn"]["combos"].get(combo_name, {})
        espn_vals = espn_combo.get("values", {})
        anchor_by_key = {}
        for slug, val in espn_vals.items():
            key = fixture_key_by_slug.get(slug)
            if key is not None:
                anchor_by_key[key] = float(val)
        espn_anchors[combo_name] = anchor_by_key
    
    for combo_name in combos_to_build:
        scoring = scoring_map[combo_name]
        natives = {}
        for row in snapshot["rows"]:
            if row.get("scoring") != scoring or row.get("teams") != 12:
                continue
            name = row.get("player_name", "")
            norm = normalize(name)
            key = name_to_key.get(norm)
            if key is None:
                continue
            native_val = row.get("native_value")
            if native_val is None:
                continue
            natives[key] = float(native_val)
        
        print(f"{combo_name}: {len(natives)} natives from snapshot")
        
        # Get anchor for this combo
        anchor_by_key = espn_anchors[combo_name]
        
        # Verify the three WRs
        for test_name, expected in [("Ja'Marr Chase", 57.1), ("Jaxon Smith-Njigba", 55.4), ("Amon-Ra St. Brown", 54.0)]:
            key = name_to_key.get(normalize(test_name))
            if key and scoring == "half_ppr":
                actual = natives.get(key)
                print(f"  {test_name}: native={actual} (expected {expected})")
        
        # Group by position for quantile mapping
        by_pos = defaultdict(list)
        for key, native in natives.items():
            pos = key_to_pos.get(key)
            anchor_v = anchor_by_key.get(key)
            if pos in ("QB", "RB", "WR", "TE") and anchor_v is not None:
                by_pos[pos].append((key, native, anchor_v))
        
        # Apply quantile mapping per position with fixed-pie scaling
        reindexed = {}
        # Get existing index_total targets (preserve the fixed-pie invariant)
        existing_combo = fixture["sources"]["fantasypros"]["combos"].get(combo_name, {})
        index_total = existing_combo.get("index_total", {})
        
        for pos, items in by_pos.items():
            if len(items) < 10:
                print(f"  WARNING: {pos} has only {len(items)} pairs, skipping")
                continue
            xs = [native for _, native, _ in items]
            ys = [anchor for _, _, anchor in items]
            # Quantile map
            mapped = {}
            for key, native, _ in items:
                slug = key_to_slug.get(key)
                if slug:
                    mapped[slug] = quantile_map(xs, ys, native)
            # Fixed-pie scaling: scale to the existing target_total
            pre_total = sum(mapped.values())
            target = index_total.get(pos, {}).get("target_total")
            if target and pre_total > 0:
                factor = target / pre_total
                for slug, val in mapped.items():
                    reindexed[slug] = round(val * factor, 1)
            else:
                # Fallback: no scaling
                for slug, val in mapped.items():
                    reindexed[slug] = round(val, 1)
        
        # Update fixture
        if "fantasypros" in fixture["sources"]:
            combo = fixture["sources"]["fantasypros"]["combos"].get(combo_name)
            if combo:
                # Update natives (keyed by slug)
                new_natives = {}
                for key, native in natives.items():
                    slug = key_to_slug.get(key)
                    if slug:
                        new_natives[slug] = native
                combo["native"] = new_natives
                combo["reindexed"] = reindexed
                combo["fit"]["method"] = "quantile_mapping"
                combo["n"] = len(reindexed)
                print(f"  Updated {combo_name}: {len(new_natives)} natives, {len(reindexed)} reindexed")
    
    # Write back
    with open(fixture_path, "w") as f:
        json.dump(fixture, f, indent=2)
    print(f"\nWrote {fixture_path}")

if __name__ == "__main__":
    main()
