#!/usr/bin/env python3
"""Refresh Supabase FantasyCalc Week 4 as_published rows from the latest matched snapshot.

Replaces the stale Week 4 rows with the fresh matched rows produced by
match_source_snapshot.py (latest dated run under output/source-matches/fantasycalc/).
This clears the TABLE_DRIFT gate.

The match file is resolved dynamically (JEG-294): match_source_snapshot.py writes
each refresh to output/source-matches/fantasycalc/<YYYY-MM-DD>/, so a hardcoded
date goes stale on the next drift day. Latest dated directory wins; --match-path
overrides for manual re-runs.

Fail-closed: no match file -> exit 1 before touching Supabase; verifies the
delete count and insert count before committing.
"""
from __future__ import annotations

import argparse
import json
import re
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

MATCH_BASE = Path("output") / "source-matches" / "fantasycalc"
DATE_DIR_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

SCORING_MAP = {
    "standard": "std",
    "half_ppr": "half",
    "ppr": "full",
}


def normalize_name(name: str) -> str:
    return name.lower().strip()


def resolve_match_path(repo_root: Path, override: str | None = None) -> Path:
    """Return the FantasyCalc match file to import.

    Latest dated match directory wins (YYYY-MM-DD sorts lexically, newest
    first); --match-path overrides for manual re-runs. Fail-closed: raises
    FileNotFoundError when nothing usable exists, so the caller exits before
    touching Supabase.
    """
    if override:
        p = Path(override)
        if not p.is_file():
            raise FileNotFoundError(f"--match-path not found: {p}")
        return p
    base = repo_root / MATCH_BASE
    dated = sorted(
        (d for d in base.iterdir() if d.is_dir() and DATE_DIR_RE.match(d.name)),
        key=lambda d: d.name,
    )
    for day in reversed(dated):  # newest first
        cands = sorted(day.glob("fantasycalc-*-matched.json"))
        if cands:
            return cands[-1]
    raise FileNotFoundError(
        f"no fantasycalc match file under {base} "
        "(expected output/source-matches/fantasycalc/<YYYY-MM-DD>/fantasycalc-*-matched.json)"
    )


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Refresh Supabase FantasyCalc as_published rows from the "
                    "latest matched snapshot (dynamic match path, JEG-294).")
    ap.add_argument("--match-path", default=None,
                    help="explicit match file; default: latest dated run under "
                         "output/source-matches/fantasycalc/")
    args = ap.parse_args(argv)

    # Load the matched data (has player_key)
    try:
        match_path = resolve_match_path(REPO, args.match_path)
    except FileNotFoundError as e:
        print(str(e), file=sys.stderr)
        return 1
    matched = json.load(open(match_path))["matched_rows"]
    print(f"Loaded {len(matched)} matched rows from {match_path}")

    # Load the snapshot for native values (keyed by name+scoring+teams: the
    # 12-combo world; a name+scoring-only key would collapse the 4 team
    # sizes onto whichever row the dict kept last).
    snap = json.load(open(REPO / "data/raw/sources/fantasycalc/week-4/snapshot.json"))
    snap_by_key = {}
    for row in snap["rows"]:
        key = (row.get("player_name"), row.get("scoring"), row.get("teams"))
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
        teams = m.get("teams")
        if teams not in (8, 10, 12, 14):
            print(f"WARNING: skipping {m.get('source_player_name')}: "
                  f"unexpected teams={teams}", file=sys.stderr)
            skipped += 1
            continue
        snap_key = (m.get("source_player_name"), m.get("scoring"), teams)
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
            "league_teams": teams,
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
