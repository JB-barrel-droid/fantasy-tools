#!/usr/bin/env python3
"""Build source value lineage for the monitoring dashboard.

For each source, shows the top 25 players by native (scrape) value in
12-team Half PPR, with:
  - native: direct value from the source snapshot
  - indexed: after isotonic reindexing onto the 0-70 scale
  - index_mult: indexed / native (effective multiplier)
  - reweighted: from the adjusted curve (DDF reweighting)
  - reweight_mult: reweighted / indexed (effective multiplier)
  - chart_value: what the chart actually displays

The user wants to verify that the numbers on the chart trace back
to the source page values through each transformation.
"""

import json
import os

REPO = "/home/hatch/workspace/fantasy-tools"
DATA_PATH = os.path.join(REPO, "dist/assets/comparison-sources-data.json")
OUT_PATH = os.path.join(REPO, "dist/modules/source-value-lineage.json")

# Best-known source URLs for the latest scrape pages
SOURCE_URLS = {
    "espn": {
        "url": "https://www.espn.com/fantasy/football/",
        "note": "Mike Clay ROS half-PPR projections via Supabase public.espn_season_projections (not a direct web scrape)",
    },
    "cbs": {
        "url": "https://www.cbssports.com/fantasy/football/",
        "note": "CBS Sports fantasy football trade values via Supabase public.cbs_trade_values",
    },
    "fantasycalc": {
        "url": "https://api.fantasycalc.com/values/current",
        "note": "FantasyCalc API, redraft 12-team 1QB Half PPR",
    },
    "fantasypros": {
        "url": "https://www.fantasypros.com/2026/09/fantasy-football-trade-value-chart-week-4-2026/",
        "note": "FantasyPros Week 4 trade value chart article",
    },
    "usatoday": {
        "url": "https://www.usatoday.com/sports/fantasy/",
        "note": "USA Today fantasy football trade values via Supabase",
    },
}

# Combo keys for 12-team Half PPR
COMBO_KEYS = {
    "espn": "half_12",
    "cbs": "half_12",
    "fantasycalc": "half_12_qb1",  # 1QB is the standard
    "fantasypros": "half_12",
    "usatoday": "half_12",
}

ADJUSTED_SOURCES = {
    "espn": None,  # ESPN uses DDF methodology, no "adjusted" variant
    "cbs": "cbs_adjusted",
    "fantasycalc": "fantasycalc_adjusted",
    "fantasypros": "fantasypros_adjusted",
    "usatoday": "usatoday_adjusted",
}


def main():
    d = json.load(open(DATA_PATH))
    sources = d["sources"]

    result = {
        "generated_at": d.get("generated_at", "unknown"),
        "scoring": "Half PPR",
        "teams": 12,
        "sources": {},
    }

    for src in ["espn", "cbs", "fantasycalc", "fantasypros", "usatoday"]:
        combo_key = COMBO_KEYS[src]
        combo = sources[src]["combos"].get(combo_key, {})

        native = combo.get("native", {})
        reindexed = combo.get("reindexed", {})
        values = combo.get("values", {})  # ESPN DDF values

        # Top 25 by CHART VALUE (most valuable), not native.
        # For ESPN, native is ROS projected points (counting stat), not trade value.
        # Sorting by native would rank high-volume QBs above elite RBs.
        if src == "espn":
            sort_vals = values
        else:
            sort_vals = reindexed

        top25_keys = sorted(
            [k for k in sort_vals if sort_vals[k]],
            key=lambda k: sort_vals[k],
            reverse=True
        )[:25]

        # Get adjusted curve data for reweighted values
        adj_src = ADJUSTED_SOURCES[src]
        adj_combo = {}
        if adj_src and adj_src in sources:
            adj_combo = sources[adj_src]["combos"].get(combo_key, {})
        adj_reindexed = adj_combo.get("reindexed", {})

        players = []
        for rank, pkey in enumerate(top25_keys, 1):
            nat_val = native.get(pkey)
            idx_val = reindexed.get(pkey)
            # For ESPN, the chart shows DDF values; for others, reindexed
            if src == "espn":
                chart_val = values.get(pkey)
            else:
                chart_val = idx_val

            # Effective multipliers
            index_mult = (idx_val / nat_val) if idx_val and nat_val else None
            reweighted_val = adj_reindexed.get(pkey)
            reweight_mult = (reweighted_val / idx_val) if reweighted_val and idx_val else None

            players.append({
                "rank": rank,
                "player_key": pkey,
                "native": round(nat_val, 2) if nat_val else None,
                "index_mult": round(index_mult, 4) if index_mult else None,
                "indexed": round(idx_val, 2) if idx_val else None,
                "reweight_mult": round(reweight_mult, 4) if reweight_mult else None,
                "reweighted": round(reweighted_val, 2) if reweighted_val else None,
                "chart_value": round(chart_val, 2) if chart_val else None,
                "chart_matches_indexed": (
                    abs(chart_val - idx_val) < 0.01
                    if chart_val and idx_val else None
                ),
            })

        result["sources"][src] = {
            "source_url": SOURCE_URLS[src]["url"],
            "source_note": SOURCE_URLS[src]["note"],
            "combo_key": combo_key,
            "player_count": combo.get("n", len(native)),
            "top25": players,
        }

    # Write output
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w") as f:
        json.dump(result, f, indent=2)

    print(f"Wrote {OUT_PATH}")
    for src in result["sources"]:
        n = len(result["sources"][src]["top25"])
        print(f"  {src}: {n} players")


if __name__ == "__main__":
    main()
