#!/usr/bin/env python3
"""Fail-closed check on the ESPN CSV the daily anchor bake is about to commit.

rebuild-chain.yml (bake_players=true) downloads the CSV the latest ESPN scrape
uploaded and copies it over data/inputs/espn_projections.csv, the input of
bake_players.py and the chain's ESPN DDF legs. This refuses a CSV that is not
the snapshot Supabase holds as latest (an older artifact, a scrape whose save
failed), is not in the shape the bake reads, or is too small to be a real pull.

Exit 0 when clean; non-zero with every problem printed otherwise.
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

REQUIRED_COLUMNS = ("player", "player_norm", "pos", "team", "has_espn_projection",
                    "eligible", "r_pass_yds", "r_pass_tds", "r_rush_yds",
                    "r_rush_tds", "r_receptions", "r_rec_yds", "r_rec_tds",
                    "ros_half_ppr", "espn_snapshot_date")
MIN_ROWS = 100  # the scrape's own floor (espn-supabase-sync.yml)


def csv_problems(header, rows, db_vintage):
    """Problems with an ESPN CSV (header + row dicts) against Supabase's latest date."""
    missing = [c for c in REQUIRED_COLUMNS if c not in (header or ())]
    if missing:
        return [f"missing columns: {missing}"]
    problems = []
    if len(rows) < MIN_ROWS:
        problems.append(f"only {len(rows)} rows (floor {MIN_ROWS})")
    dates = {(r.get("espn_snapshot_date") or "").strip() for r in rows}
    if len(dates) != 1 or "" in dates:
        problems.append(f"espn_snapshot_date is not one unanimous date: {sorted(dates)[:5]}")
    elif db_vintage is None:
        problems.append("Supabase espn_season_projections has no snapshot date")
    elif next(iter(dates)) != str(db_vintage):
        problems.append(f"CSV vintage {next(iter(dates))} != Supabase latest "
                        f"espn_snapshot_date {db_vintage}")
    if not any(str(r.get("eligible")).strip().lower() == "true" for r in rows):
        problems.append("no eligible rows")
    return problems


def supabase_latest_vintage():
    import sbclient  # noqa: PLC0415 - env-shimmed client (gh_sbclient.py)
    rows = sbclient.get_all(
        "espn_season_projections",
        "?select=espn_snapshot_date&order=espn_snapshot_date.desc&limit=1")
    return str(rows[0]["espn_snapshot_date"]) if rows else None


def main(argv):
    if len(argv) != 2:
        print("usage: check_espn_bake_csv.py <espn_projections.csv>", file=sys.stderr)
        return 2
    with Path(argv[1]).open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        header = reader.fieldnames
    problems = csv_problems(header, rows, supabase_latest_vintage())
    for p in problems:
        print(f"FAIL-CLOSED: {p}", file=sys.stderr)
    if not problems:
        print(f"ESPN CSV ok: {len(rows)} rows, vintage {rows[0]['espn_snapshot_date']} "
              "(matches Supabase latest)")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
