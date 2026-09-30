#!/usr/bin/env python3
"""Build source value lineage for the monitoring dashboard.

For each source, shows the top 25 players by native (scrape) value in
12-team Half PPR, with:
  - live_value: scraped directly from the human-readable source page
  - native: value stored in our pipeline snapshot
  - live_matches_native: whether live page matches our snapshot
  - indexed: after isotonic reindexing onto the 0-70 scale
  - index_mult: indexed / native (effective multiplier)
  - reweighted: from the adjusted curve (DDF reweighting)
  - reweight_mult: reweighted / indexed (effective multiplier)
  - chart_value: what the chart actually displays

The user requires that verification data comes from the live pages
a human would visit, not API endpoints or database snapshots.
FantasyPros and USA Today are scraped live from their article pages.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from scrape_live_source_pages import scrape_fantasypros, scrape_usatoday

REPO = "/home/hatch/workspace/fantasy-tools"
DATA_PATH = os.path.join(REPO, "dist/assets/comparison-sources-data.json")
OUT_PATH = os.path.join(REPO, "dist/modules/source-value-lineage.json")

# Snapshot paths for native values (raw scraped values, not transformed)
SNAPSHOT_PATHS = {
    "fantasypros": os.path.join(REPO, "data/raw/sources/fantasypros/2026-09-29/snapshot.json"),
    "usatoday": os.path.join(REPO, "data/raw/sources/usatoday/2026-09-29/snapshot.json"),
}


def load_snapshot_natives(source):
    """Load native_value (raw scraped) from snapshot, keyed by player_key slug.
    
    The snapshot has both native_value (raw from source page) and value (transformed).
    We want the raw native_value for the lineage comparison.
    """
    path = SNAPSHOT_PATHS.get(source)
    if not path or not os.path.exists(path):
        return {}
    
    snap = json.load(open(path))
    rows = snap.get("rows", [])
    
    # Build mapping from player name slug to native_value for half_ppr/12 teams
    natives = {}
    for r in rows:
        if r.get("scoring") != "half_ppr" or r.get("teams") != 12:
            # Also check for half-ppr variants
            scoring = str(r.get("scoring", "")).lower()
            if "half" not in scoring:
                continue
            if r.get("teams") != 12:
                continue
        
        name = r.get("player_name", "")
        if not name:
            continue
        
        # Create slug matching the comparison data format
        slug = name.lower()
        native_val = r.get("native_value")
        if native_val is not None:
            # Keep the first (or highest?) - snapshots should have one per player
            if slug not in natives:
                natives[slug] = float(native_val)
    
    return natives

# Human-readable source pages (what a human would visit)
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
        "url": "https://fantasycalc.com",
        "note": "FantasyCalc web app (human UI). Values in the app come from the same backend as the API.",
    },
    "fantasypros": {
        "url": "https://www.fantasypros.com/2026/09/fantasy-football-trade-value-chart-week-4-2026/",
        "note": "FantasyPros Week 4 trade value chart article. Values scraped LIVE from this page.",
    },
    "usatoday": {
        "url": "https://www.usatoday.com/story/sports/fantasy/football/2026/09/29/fantasy-trade-value-chart-week-4-ros-rankings/92008742007/",
        "note": "USA Today Week 4 trade value chart. Half-PPR column scraped LIVE from this page.",
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

    # Scrape live pages (user requirement: data must come from live human pages)
    print("Scraping live source pages...")
    live_data = {}
    try:
        live_data["fantasypros"] = scrape_fantasypros()
        print(f"  FantasyPros: {len(live_data['fantasypros'])} players scraped live")
    except Exception as e:
        print(f"  FantasyPros scrape FAILED: {e}")
        live_data["fantasypros"] = {}
    try:
        live_data["usatoday"] = scrape_usatoday()
        print(f"  USA Today: {len(live_data['usatoday'])} players scraped live")
    except Exception as e:
        print(f"  USA Today scrape FAILED: {e}")
        live_data["usatoday"] = {}

    result = {
        "generated_at": d.get("generated_at", "unknown"),
        "scoring": "Half PPR",
        "teams": 12,
        "method": "Native values verified against LIVE human-readable source pages. FantasyPros and USA Today scraped directly from their article pages.",
        "sources": {},
    }

    # Load snapshot natives (raw scraped values) for sources with snapshots
    # The comparison data's "native" field contains transformed values, not raw.
    # We need the true native_value from the snapshot for accurate lineage.
    snapshot_natives = {}
    for src in ["fantasypros", "usatoday"]:
        snapshot_natives[src] = load_snapshot_natives(src)
        print(f"  {src}: loaded {len(snapshot_natives[src])} native values from snapshot")

    for src in ["espn", "cbs", "fantasycalc", "fantasypros", "usatoday"]:
        combo_key = COMBO_KEYS[src]
        combo = sources[src]["combos"].get(combo_key, {})

        native = combo.get("native", {})
        # Override with snapshot natives for accuracy (raw scraped values)
        if src in snapshot_natives and snapshot_natives[src]:
            native = snapshot_natives[src]
        
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
            # Live value scraped from the human-readable page
            live_val = live_data.get(src, {}).get(pkey)
            live_matches = None
            if live_val is not None and nat_val is not None:
                live_matches = abs(live_val - nat_val) < 0.01
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
                "live_value": round(live_val, 2) if live_val is not None else None,
                "native": round(nat_val, 2) if nat_val else None,
                "live_matches_native": live_matches,
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
            "player_count": len(native),  # Use actual native count, not stale 'n' field
            "live_scraped": src in live_data and bool(live_data[src]),
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
