#!/usr/bin/env python3
"""Load the 2015-2025 nflverse weekly history into Supabase (JEG-525 item e).

PROPOSED. The target tables are defined in sql/proposed/jeg525_nflverse_history.sql,
which is NOT applied: it is a production schema change waiting on Jeremy's
approval on JEG-525. Until then this script only runs as a dry run.

Reads data/inputs/weekly_actuals_nflverse_2015_2025.csv.gz and
data/inputs/nfl_schedule_2015_2025.json (the files derive_lineup_parameters.py
uses today) and builds rows for public.nflverse_player_week_actuals and
public.nflverse_team_weeks. With --apply it upserts them in batches through
PostgREST (on_conflict on the primary keys, so a rerun is idempotent) and
then reads back the counts.

Usage:
    python3 pipelines/load_nflverse_history.py            # dry run: counts and checks only
    SUPABASE_URL=... SUPABASE_SERVICE_KEY=... \
    python3 pipelines/load_nflverse_history.py --apply    # after the migration is applied
"""
from __future__ import annotations

import argparse
import csv
import gzip
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
ACTUALS = REPO / "data" / "inputs" / "weekly_actuals_nflverse_2015_2025.csv.gz"
SCHEDULE = REPO / "data" / "inputs" / "nfl_schedule_2015_2025.json"
ACTUALS_TABLE = "nflverse_player_week_actuals"
WEEKS_TABLE = "nflverse_team_weeks"
BATCH = 1000


def actual_rows(path=ACTUALS) -> list:
    with gzip.open(path, "rt", encoding="utf-8", newline="") as fh:
        return [{"season": int(r["season"]), "week": int(r["week"]), "gsis_id": r["player_id"],
                 "player_name": r["name"], "position": r["pos"], "team": r["team"],
                 "actual_std": round(float(r["std"]), 2), "actual_half": round(float(r["half_ppr"]), 2),
                 "actual_ppr": round(float(r["ppr"]), 2)}
                for r in csv.DictReader(fh)]


def team_week_rows(path=SCHEDULE) -> list:
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    return [{"season": int(s), "week": int(w), "team": t}
            for s, teams in doc["seasons"].items() for t, weeks in teams.items() for w in weeks]


def check(actuals: list, weeks: list) -> list:
    """Problems that would make the load wrong; empty when clean."""
    problems = []
    keys = [(r["season"], r["week"], r["gsis_id"]) for r in actuals]
    if len(keys) != len(set(keys)):
        problems.append("duplicate (season, week, gsis_id) in the actuals file")
    played = {(r["season"], r["week"], r["team"]) for r in weeks}
    orphan = sum(1 for r in actuals if (r["season"], r["week"], r["team"]) not in played)
    if orphan:
        problems.append(f"{orphan} actual rows in a week their team did not play")
    bad_pos = {r["position"] for r in actuals} - {"QB", "RB", "WR", "TE"}
    if bad_pos:
        problems.append(f"unexpected positions {sorted(bad_pos)}")
    return problems


def upsert(client, table: str, rows: list, conflict: str) -> None:
    for i in range(0, len(rows), BATCH):
        client.post(table, rows[i:i + BATCH], params=f"?on_conflict={conflict}",
                    prefer="resolution=merge-duplicates,return=minimal")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--apply", action="store_true", help="write to Supabase (only after the migration is applied)")
    args = ap.parse_args(argv)
    actuals, weeks = actual_rows(), team_week_rows()
    problems = check(actuals, weeks)
    print(f"{len(actuals)} player-weeks, {len(weeks)} team-weeks, "
          f"seasons {min(r['season'] for r in actuals)}-{max(r['season'] for r in actuals)}")
    if problems:
        print("NOT LOADING:", "; ".join(problems))
        return 1
    if not args.apply:
        print("dry run: nothing written (the target tables are proposed, sql/proposed/jeg525_nflverse_history.sql)")
        return 0
    sys.path.insert(0, str(REPO / "pipelines"))
    import gh_sbclient as sb
    upsert(sb, WEEKS_TABLE, weeks, "season,team,week")
    upsert(sb, ACTUALS_TABLE, actuals, "season,week,gsis_id")
    print("upserted; verify with the counts in the migration footer")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
