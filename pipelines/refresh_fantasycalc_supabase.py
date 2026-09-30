#!/usr/bin/env python3
"""Refresh Supabase FantasyCalc Week 4 as_published rows from the live API snapshot.

Replaces the 580 stale Week 4 rows with the 584 fresh matched rows from
the 2026-09-30 API-direct snapshot. This clears the TABLE_DRIFT gate.

Fail-closed: verifies the delete count and insert count before committing.
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "pipelines"))
sys.path.insert(0, "/home/hatch/workspace/skills/supabase-football-signal/bin")

from sbclient import delete, get_all, post

TABLE = "source_trade_values"
SOURCE = "fantasycalc"
VARIANT = "as_published"
WEEK = 4
SEASON = 2026

SCORING_MAP = {
    "standard": "std",
    "half_ppr": "half",
    "ppr": "full",
}


def normalize_name(name: str) -> str:
    return name.lower().strip()


def main() -> int:
    # Load the matched data (has player_key)
    match_path = REPO / "output/source-matches/fantasycalc/2026-09-30/fantasycalc-mixed-12-matched.json"
    if not match_path.exists():
        print(f"match file not found: {match_path}", file=sys.stderr)
        return 1
    matched = json.load(open(match_path))["matched_rows"]
    print(f"Loaded {len(matched)} matched rows")

    # Load the snapshot for native values
    snap = json.load(open(REPO / "data/raw/sources/fantasycalc/week-4/snapshot.json"))
    snap_by_key = {}
    for row in snap["rows"]:
        key = (row.get("player_name"), row.get("scoring"))
        snap_by_key[key] = row

    # Check existing Week 4 rows
    existing = get_all(
        TABLE,
        f"?source=eq.{SOURCE}&variant=eq.{VARIANT}&week=eq.{WEEK}&select=id&order=id",
    )
    print(f"Existing Week 4 as_published rows: {len(existing)}")

    # Delete the stale rows
    if existing:
        print(f"Deleting {len(existing)} stale rows...")
        result = delete(
            TABLE,
            f"?source=eq.{SOURCE}&variant=eq.{VARIANT}&week=eq.{WEEK}",
        )
        print(f"Delete result: {result}")

    # Verify deletion
    remaining = get_all(
        TABLE,
        f"?source=eq.{SOURCE}&variant=eq.{VARIANT}&week=eq.{WEEK}&select=id&order=id",
    )
    if remaining:
        print(f"ERROR: {len(remaining)} rows remain after delete", file=sys.stderr)
        return 1
    print("Delete verified: 0 rows remain")

    # Build player_key -> team map from the players table
    print("Loading player teams...")
    all_players = get_all("players", "?select=player_key,metadata&order=player_key")
    team_by_key = {}
    for p in all_players:
        pk = p.get("player_key")
        meta = p.get("metadata") or {}
        if pk is not None and isinstance(meta, dict):
            team = meta.get("team")
            if team:
                team_by_key[pk] = team
    print(f"Loaded {len(team_by_key)} player teams")

    # Build the new rows
    pulled_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")
    new_rows = []
    skipped = 0
    missing_team = 0
    for m in matched:
        snap_key = (m.get("source_player_name"), m.get("scoring"))
        snap_row = snap_by_key.get(snap_key)
        if not snap_row:
            skipped += 1
            continue
        scoring = SCORING_MAP.get(m.get("scoring"), m.get("scoring"))
        native_val = snap_row.get("native_value", snap_row.get("value"))
        team = team_by_key.get(m.get("player_key"))
        if not team:
            missing_team += 1
            continue  # check constraint requires team
        new_rows.append({
            "source": SOURCE,
            "player_norm": normalize_name(m.get("source_player_name", "")),
            # FantasyCalc API ids are numeric, not UUIDs; player_id is nullable
            "player_id": None,
            "position": m.get("pos"),
            "team": team,
            "scoring": scoring,
            "league_teams": 12,
            "qb_slots": 1,
            "season": SEASON,
            "week": WEEK,
            "variant": VARIANT,
            "value": float(native_val) if native_val is not None else None,
            "native_value": float(native_val) if native_val is not None else None,
            "pulled_at": pulled_at,
            "player_key": m.get("player_key"),
        })
    print(f"Built {len(new_rows)} new rows (skipped {skipped}, missing team {missing_team})")

    # Insert in batches
    BATCH = 100
    for i in range(0, len(new_rows), BATCH):
        batch = new_rows[i:i + BATCH]
        result = post(TABLE, batch)
        if not isinstance(result, list) or len(result) != len(batch):
            print(f"ERROR: batch {i//BATCH} insert failed", file=sys.stderr)
            return 1
        print(f"Inserted batch {i//BATCH + 1}: {len(batch)} rows")

    # Verify
    final = get_all(
        TABLE,
        f"?source=eq.{SOURCE}&variant=eq.{VARIANT}&week=eq.{WEEK}&select=id&order=id",
    )
    print(f"Final count: {len(final)} Week 4 as_published rows")
    if len(final) != len(new_rows):
        print(f"ERROR: expected {len(new_rows)}, got {len(final)}", file=sys.stderr)
        return 1

    print("SUCCESS: Supabase refreshed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
