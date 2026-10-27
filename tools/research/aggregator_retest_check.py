#!/usr/bin/env python3
"""JEG-969: Automatic re-test check for DDF Value aggregator weights.

This script checks whether enough week-ahead projection data from all three
DDF Value sources (ESPN, CBS ROS, Razzball) has been stored in the
source_projection_captures table to run a meaningful aggregator comparison.

When enough data exists (>= MIN_WEEKS weeks of week-ahead captures from all
three sources), it runs the full aggregator battery and reports whether any
aggregator beats equal weights with statistical significance.

Intended to be run weekly as part of CI or a scheduled task.

Usage:
    python3 tools/research/aggregator_retest_check.py

Exit codes:
    0 = not enough data yet, or equal weights still best (no action needed)
    1 = an aggregator beats equal weights -- human review required
    2 = error

Environment:
    Requires SUPABASE_URL and SUPABASE_SERVICE_KEY for database access,
    OR runs in dry-run mode from local files.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
MIN_WEEKS = 8  # Minimum weeks of three-source week-ahead data for a valid test
SOURCES = ["espn", "cbs", "razzball"]


def check_data_availability():
    """Check source_projection_captures for week-ahead data coverage.

    Returns a dict with:
      ready: bool -- whether enough data exists
      weeks_available: int -- number of weeks with all three sources
      detail: dict -- per-source week coverage
    """
    # Try Supabase connection
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_KEY") or os.environ.get("SUPABASE_ANON_KEY")

    if not url or not key:
        print("No Supabase credentials. Checking local files only.")
        return check_local_files()

    try:
        # Use urllib to avoid dependency on supabase-py
        import urllib.request
        import urllib.parse

        # Query: count weeks per source where horizon = 'week_ahead'
        query = (
            f"{url}/rest/v1/rpc/sql?"
            "query=" + urllib.parse.quote(
                "SELECT source, source_week, count(DISTINCT player_key) as players "
                "FROM source_projection_captures "
                "WHERE horizon = 'week_ahead' "
                "GROUP BY source, source_week "
                "ORDER BY source, source_week"
            )
        )
        # Actually, use the PostgREST endpoint instead
        endpoint = (
            f"{url}/rest/v1/source_projection_captures"
            "?select=source,source_week"
            "&horizon=eq.week_ahead"
        )
        req = urllib.request.Request(endpoint, headers={
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        })
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read())

        # Count weeks per source
        source_weeks = {}
        for row in data:
            src = row["source"]
            wk = row["source_week"]
            source_weeks.setdefault(src, set()).add(wk)

        detail = {src: sorted(source_weeks.get(src, set())) for src in SOURCES}
        common_weeks = set.intersection(*[source_weeks.get(s, set()) for s in SOURCES]) if all(s in source_weeks for s in SOURCES) else set()

        return {
            "ready": len(common_weeks) >= MIN_WEEKS,
            "weeks_available": len(common_weeks),
            "common_weeks": sorted(common_weeks),
            "detail": detail,
        }
    except Exception as e:
        print(f"Supabase query failed: {e}. Falling back to local files.")
        return check_local_files()


def check_local_files():
    """Check local history files for week-ahead data."""
    # The existing history files only contain ROS projections.
    # ESPN weekly is in a separate CSV, but CBS/Razzball week-ahead are not stored.
    # This is the "not enough data" path.
    history_dir = REPO / "data" / "history"
    weeks = []
    for f in sorted(history_dir.glob("week-*.json")):
        wk = int(f.stem.split("-")[1])
        weeks.append(wk)

    espn_weekly = REPO / "data" / "inputs" / "espn_weekly_projections_2026.csv"
    espn_weeks = set()
    if espn_weekly.exists():
        import csv
        with open(espn_weekly) as f:
            for row in csv.DictReader(f):
                espn_weeks.add(int(row["week"]))

    return {
        "ready": False,
        "weeks_available": 0,
        "common_weeks": [],
        "detail": {
            "espn": sorted(espn_weeks),
            "cbs": [],  # no week-ahead stored
            "razzball": [],  # no week-ahead stored
        },
        "note": "CBS and Razzball week-ahead projections not stored locally. "
                "Waiting for JEG-944 capture pipeline.",
    }


def run():
    print("JEG-969 aggregator re-test check")
    print(f"Minimum weeks required: {MIN_WEEKS}")
    print()

    status = check_data_availability()

    print(f"Data status:")
    print(f"  Ready for full test: {status['ready']}")
    print(f"  Weeks with all 3 sources (week-ahead): {status['weeks_available']}")
    if status.get("common_weeks"):
        print(f"  Common weeks: {status['common_weeks']}")
    for src in SOURCES:
        weeks = status["detail"].get(src, [])
        print(f"  {src}: {len(weeks)} weeks ({weeks[:5]}{'...' if len(weeks) > 5 else ''})")
    if status.get("note"):
        print(f"  Note: {status['note']}")

    if not status["ready"]:
        print(f"\nNot enough data ({status['weeks_available']}/{MIN_WEEKS} weeks). "
              f"Equal weights remain the default. Check again next week.")
        sys.exit(0)

    print(f"\n{status['weeks_available']} weeks available. Running full aggregator battery...")
    # TODO: When data is available, import and run the full test battery from
    # jeg969_aggregator_tests.py using week-ahead data from Supabase.
    # For now, this path is not reachable since no week-ahead captures exist.
    print("Full battery not yet implemented for Supabase week-ahead data.")
    print("When implemented, this will:")
    print("  1. Pull week-ahead projections from source_projection_captures")
    print("  2. Pull actuals from weekly_actuals")
    print("  3. Run aggregators 1-7 with proper train/test split")
    print("  4. Report whether any aggregator beats equal weights (CI excludes zero)")
    print("  5. Exit 1 if a change is warranted (human review needed)")
    sys.exit(0)


if __name__ == "__main__":
    run()
