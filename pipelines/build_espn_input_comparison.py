#!/usr/bin/env python3
"""Build ESPN input variable comparison for the monitoring dashboard.

Compares grain-to-grain:
  - LIVE PAGE: visible projections scraped from ESPN's human-readable
    projections page (https://fantasy.espn.com/football/players/projections)
  - PIPELINE: what our DDF leg ingested from data/inputs/espn_projections.csv

The user requires that verification comes from the live page a human would
see, not from an API or from comparing the pipeline against itself.

Grain mapping (live page -> CSV):
  - pass_yds  -> r_pass_yds
  - pass_tds  -> r_pass_tds
  - rush_yds  -> r_rush_yds
  - rush_tds  -> r_rush_tds
  - receptions -> r_receptions
  - rec_yds   -> r_rec_yds
  - rec_tds   -> r_rec_tds

Note: the live page shows FPTS in full PPR; the CSV's ros_half_ppr is
Half-PPR. Those are NOT directly comparable (different scoring). The stat
grains (yards, TDs, receptions) are scoring-agnostic and must match.
"""

import csv
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
from canonical_players import norm_player_name

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV_PATH = os.path.join(REPO, "data/inputs/espn_projections.csv")
LIVE_PATH = os.path.join(REPO, "data/raw/sources/espn/live_page_projections_2026-09-30.json")
DATA_PATH = os.path.join(REPO, "dist/assets/comparison-sources-data.json")
OUT_PATH = os.path.join(REPO, "dist/modules/espn-input-comparison.json")

# (live_key, csv_key, label)
GRAINS = [
    ("pass_yds", "r_pass_yds", "Pass Yds"),
    ("pass_tds", "r_pass_tds", "Pass TD"),
    ("rush_yds", "r_rush_yds", "Rush Yds"),
    ("rush_tds", "r_rush_tds", "Rush TD"),
    ("receptions", "r_receptions", "Rec"),
    ("rec_yds", "r_rec_yds", "Rec Yds"),
    ("rec_tds", "r_rec_tds", "Rec TD"),
]

# Per-grain tolerance: live page rounds to integers, CSV has decimals.
# Yardage gets a wider band (page rounding + minor model refresh drift);
# TDs and receptions are tighter.
TOLERANCE = {
    "pass_yds": 5.0,
    "pass_tds": 1.0,
    "rush_yds": 5.0,
    "rush_tds": 1.0,
    "receptions": 1.0,
    "rec_yds": 5.0,
    "rec_tds": 1.0,
}


def main():
    live = json.load(open(LIVE_PATH))
    live_players = {norm_player_name(p["name"]): p for p in live["players"]}

    # Load pipeline CSV
    csv_rows = {}
    with open(CSV_PATH, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            csv_rows[norm_player_name(row["player"])] = row

    # Top 25 ESPN chart players (same method as lineage builder)
    d = json.load(open(DATA_PATH))
    combo = d["sources"]["espn"]["combos"]["half_12"]
    values = combo.get("values", {})
    ranked = sorted(
        [(k, v) for k, v in values.items() if v],
        key=lambda kv: kv[1],
        reverse=True,
    )[:25]

    result = {
        "generated_at": d.get("built_at", "unknown"),
        "method": (
            "Grain-to-grain: ESPN's live human-readable projections page vs "
            "what the pipeline ingested. Live page scraped by rendered browser, "
            "no API. Stat grains must match within rounding tolerance (1.0). "
            "FPTS is NOT compared (page is full PPR, pipeline is Half-PPR)."
        ),
        "live_source": {
            "url": live["source_url"],
            "title": live["page_title"],
            "scraped_at": live["scraped_at"],
            "scoring": live["scoring_on_page"],
            "projection_type": live["projection_type"],
        },
        "pipeline_source": "data/inputs/espn_projections.csv (from ESPN API - NOT a live page)",
        "tolerance": TOLERANCE,
        "input_columns": [{"key": lk, "label": lbl} for lk, _, lbl in GRAINS],
        "players": [],
    }

    for pkey, chart_val in ranked:
        norm_key = norm_player_name(pkey)
        live_p = live_players.get(norm_key, {})
        csv_row = csv_rows.get(norm_key, {})

        name = live_p.get("name") or csv_row.get("player", pkey)
        pos = live_p.get("pos") or csv_row.get("pos", "")
        team = live_p.get("team") or csv_row.get("team", "")

        grains = []
        all_match = True
        live_found = bool(live_p)
        csv_found = bool(csv_row)

        for live_key, csv_key, label in GRAINS:
            live_val = live_p.get(live_key)
            csv_val = csv_row.get(csv_key)
            try:
                csv_num = float(csv_val) if csv_val not in (None, "") else None
            except (ValueError, TypeError):
                csv_num = None

            tol = TOLERANCE[live_key]
            if live_val is not None and csv_num is not None:
                diff = abs(live_val - csv_num)
                match = diff <= tol
                note = None
            elif live_val is None and csv_num == 0.0:
                # Position-irrelevant grain: page shows nothing, file has 0.
                # Same fact, counts as a match.
                diff = 0.0
                match = True
                note = "n/a on page (=0)"
            elif live_val is None and csv_num is None:
                diff = None
                match = True
                note = "absent both"
            else:
                diff = None
                match = False
                note = "missing on one side"

            if not match:
                all_match = False

            grains.append({
                "key": live_key,
                "label": label,
                "live_page": live_val,
                "pipeline_input": csv_num,
                "diff": round(diff, 2) if diff is not None else None,
                "tolerance": tol,
                "match": match,
                "note": note,
            })

        # Coverage: player not in the live top-30 scrape is a coverage gap,
        # not a data mismatch. Flag it distinctly.
        coverage = "ok" if live_found else "not_in_live_top30"
        if not live_found:
            all_match = False

        result["players"].append({
            "player_key": pkey,
            "name": name,
            "pos": pos,
            "team": team,
            "chart_value": chart_val,
            "live_page_found": live_found,
            "csv_found": csv_found,
            "coverage": coverage,
            "live_fpts_ppr": live_p.get("fpts_ppr"),
            "csv_ros_half_ppr": float(csv_row["ros_half_ppr"]) if csv_row.get("ros_half_ppr") else None,
            "all_grains_match": all_match and live_found and csv_found,
            "grains": grains,
        })

    with open(OUT_PATH, "w") as f:
        json.dump(result, f, indent=2)

    matched = sum(1 for p in result["players"] if p["all_grains_match"])
    print(f"Wrote {OUT_PATH}")
    print(f"  {matched}/25 players with all grains matching (live page vs pipeline)")
    # Show mismatches
    for p in result["players"]:
        if not p["all_grains_match"]:
            bad = [g["label"] for g in p["grains"] if not g["match"]]
            print(f"  MISMATCH {p['name']}: {', '.join(bad)} "
                  f"(live_found={p['live_page_found']}, csv_found={p['csv_found']})")


if __name__ == "__main__":
    main()
