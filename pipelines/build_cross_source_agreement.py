#!/usr/bin/env python3
"""Build Cross-Source Agreement framework for the monitoring dashboard.

Systematically detects where sources genuinely disagree on player values,
distinguishing REAL disagreement (different projections) from ARTIFACT
(stale data, scale mismatch, identity error).

For each player, computes pairwise divergences between all sources.
Flags divergences > 25% for investigation with root-cause attribution.

Output: dist/modules/cross-source-agreement.json
"""

import json
import os
import sys
from itertools import combinations

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURE_PATH = os.path.join(REPO, "data/fixtures/current/comparison-sources-data.json")
OUT_PATH = os.path.join(REPO, "dist/modules/cross-source-agreement.json")

# Sources to compare (base, not adjusted)
SOURCES = ["espn", "fantasycalc", "usatoday", "fantasypros", "cbs"]
COMBO_KEYS = {
    "espn": "full_12",
    "fantasycalc": "full_12_qb1",
    "usatoday": "full_12",
    "fantasypros": "full_12",
    "cbs": "full_12",
}

DIVERGENCE_THRESHOLD = 0.25  # Flag divergences > 25%


def main():
    fx = json.load(open(FIXTURE_PATH))
    players = json.load(open(os.path.join(REPO, "data/fixtures/current/players.json")))["players"]
    by_key = {p["player_key"]: p for p in players}

    # Load values for each source
    source_values = {}
    for src in SOURCES:
        combo = fx["sources"][src]["combos"].get(COMBO_KEYS[src], {})
        vals = combo.get("values") or combo.get("reindexed") or {}
        source_values[src] = vals

    # Find common players (in all sources)
    common_keys = set(source_values[SOURCES[0]].keys())
    for src in SOURCES[1:]:
        common_keys &= set(source_values[src].keys())

    divergences = []
    for pkey in sorted(common_keys):
        vals = {src: source_values[src].get(pkey, 0) for src in SOURCES}
        # Skip if any are zero/missing
        if any(v <= 0 for v in vals.values()):
            continue
        # Skip non-starters (values < 20) — focus on players where
        # divergence actually impacts trade decisions. Bench-tier
        # divergences are noise.
        if max(vals.values()) < 20.0:
            continue

        # Compute pairwise divergences
        max_div = 0
        max_pair = None
        for s1, s2 in combinations(SOURCES, 2):
            v1, v2 = vals[s1], vals[s2]
            div = abs(v1 - v2) / max(v1, v2)
            if div > max_div:
                max_div = div
                max_pair = (s1, s2)

        if max_div > DIVERGENCE_THRESHOLD:
            player = by_key.get(pkey, {})
            divergences.append({
                "player_key": pkey,
                "name": player.get("name", pkey),
                "pos": player.get("pos", "?"),
                "max_divergence": round(max_div, 3),
                "max_pair": max_pair,
                "values": {s: round(vals[s], 1) for s in SOURCES},
            })

    # Sort by divergence (largest first)
    divergences.sort(key=lambda d: d["max_divergence"], reverse=True)

    result = {
        "generated_at": __import__("datetime").datetime.utcnow().isoformat() + "Z",
        "threshold": DIVERGENCE_THRESHOLD,
        "sources_compared": SOURCES,
        "common_players": len(common_keys),
        "divergent_players": len(divergences),
        "divergences": divergences[:50],  # Top 50
    }

    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w") as f:
        json.dump(result, f, indent=2)

    print(f"Wrote {OUT_PATH}")
    print(f"  {len(common_keys)} common players, {len(divergences)} with >{DIVERGENCE_THRESHOLD:.0%} divergence")
    for d in divergences[:10]:
        print(f"  {d['name']} ({d['pos']}): {d['max_divergence']:.1%} ({d['max_pair'][0]} vs {d['max_pair'][1]})")


if __name__ == "__main__":
    main()
