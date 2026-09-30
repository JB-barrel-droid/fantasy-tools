#!/usr/bin/env python3
"""Rebuild FantasyPros fixture section from snapshot with correct natives.

The fixture's FP natives were corrupted (used `value` instead of `native_value`).
This script rebuilds the section directly from the snapshot using:
- native_value (raw published) for the natives
- quantile mapping (not isotonic PAVA) for the reindexing
"""
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "pipelines"))
from reindex_comparison_section import quantile_map

def load_json(path):
    with open(path) as f:
        return json.load(f)

def main():
    fixture_path = REPO / "data/fixtures/current/comparison-sources-data.json"
    fixture = load_json(fixture_path)
    
    # Load FP snapshot
    snapshot_path = REPO / "data/raw/sources/fantasypros/2026-09-29/snapshot.json"
    snapshot = load_json(snapshot_path)
    
    # Load players for positions and keys
    players_path = REPO / "data/fixtures/current/players.json"
    players = load_json(players_path)
    pos_by_key = {p["player_key"]: p["pos"] for p in players["players"]}
    
    # Build slug -> key mapping from fixture
    fixture_key_by_slug = fixture.get("player_keys", {})
    
    # Get ESPN anchor
    espn = fixture["sources"]["espn"]["combos"]["half_12"]["values"]
    anchor_by_key = {}
    for slug, val in espn.items():
        key = fixture_key_by_slug.get(slug)
        if key is not None:
            anchor_by_key[key] = float(val)
    
    # Build FP natives from snapshot (using native_value, not value)
    fp_natives = {}
    fp_keys = {}
    # Pre-build normalized slug map for robust matching
    def normalize(s):
        return s.lower().replace("'", "").replace(".", "").replace("-", "").replace(" ", "")
    norm_slug_map = {normalize(slug): (slug, key) for slug, key in fixture_key_by_slug.items()}
    
    for row in snapshot["rows"]:
        if row.get("scoring") != "half_ppr" or row.get("teams") != 12:
            continue
        name = row["player_name"]
        norm = normalize(name)
        match = norm_slug_map.get(norm)
        if match is None:
            continue
        slug, key = match
        native_val = row.get("native_value")
        if native_val is None:
            continue
        fp_natives[slug] = float(native_val)
        fp_keys[slug] = key
    
    print(f"Built {len(fp_natives)} FP natives from snapshot")
    print(f"Gibbs native: {fp_natives.get('jahmyr gibbs')} (should be 75.1)")
    
    # Group by position and apply quantile mapping
    from collections import defaultdict
    by_pos = defaultdict(list)
    for slug, native in fp_natives.items():
        key = fp_keys[slug]
        pos = pos_by_key.get(key)
        if pos in ("QB", "RB", "WR", "TE"):
            anchor_v = anchor_by_key.get(key)
            if anchor_v is not None:
                by_pos[pos].append((slug, native, anchor_v))
    
    reindexed = {}
    for pos, pairs in by_pos.items():
        xs = [x for _, x, _ in pairs]
        ys = [y for _, _, y in pairs]
        print(f"{pos}: {len(pairs)} pairs, mapping with quantile_map")
        for slug, native, _ in pairs:
            reindexed[slug] = round(quantile_map(xs, ys, native), 1)
    
    # Apply fixed-pie scaling per position
    index_total = {}
    for pos, pairs in by_pos.items():
        pos_slugs = [s for s, _, _ in pairs]
        pre_total = sum(reindexed[s] for s in pos_slugs)
        target_total = sum(anchor_by_key[fp_keys[s]] for s in pos_slugs)
        factor = target_total / pre_total if pre_total > 0 else 1.0
        print(f"{pos}: factor={factor:.6f} (target={target_total:.1f}, pre={pre_total:.1f})")
        for s in pos_slugs:
            reindexed[s] = round(reindexed[s] * factor, 1)
        # Record the fixed-pie metadata
        index_total[pos] = {
            "target_total": round(target_total, 1),
            "pre_total": round(pre_total, 1),
            "factor": round(factor, 6),
            "n_priced": len(pos_slugs),
        }
    
    # Update fixture
    fp_section = fixture["sources"]["fantasypros"]
    combo = fp_section["combos"]["half_12"]
    combo["native"] = dict(sorted(fp_natives.items()))
    combo["reindexed"] = dict(sorted(reindexed.items()))
    combo["player_keys"] = {s: fp_keys[s] for s in fp_natives}
    combo["index_total"] = index_total
    combo["fit"] = {
        pos: {
            "method": "quantile_mapping",
            "anchor": "espn_leg",
            "n_pairs": len(pairs),
            "native_min": round(min(x for _, x, _ in pairs), 1),
            "native_max": round(max(x for _, x, _ in pairs), 1),
        }
        for pos, pairs in by_pos.items()
    }
    
    # Verify our three WRs
    print("\nVerification (JSN/Chase/Amon-Ra):")
    for slug in ["jaxon smithnjigba", "jamarr chase", "amonra st brown"]:
        n = fp_natives.get(slug, "MISSING")
        r = reindexed.get(slug, "MISSING")
        print(f"  {slug}: native={n}, reindexed={r}")
    
    # Check distinctness
    vals = [reindexed.get(s) for s in ["jaxon smithnjigba", "jamarr chase", "amonra st brown"]]
    if len(set(vals)) == 3:
        print("✓ All three WRs have distinct reindexed values!")
    else:
        print(f"✗ FAILED: Values not distinct: {vals}")
        sys.exit(1)
    
    # Write fixture
    with open(fixture_path, "w") as f:
        json.dump(fixture, f, indent=2, sort_keys=True)
    print(f"\n✓ Fixture updated: {fixture_path}")

if __name__ == "__main__":
    main()
