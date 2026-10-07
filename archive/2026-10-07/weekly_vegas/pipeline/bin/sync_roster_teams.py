#!/usr/bin/env python3
"""Sync players.team_id from the weekly ECR feed's current team listings.

Cause (2026-09-12): players.team_id was seeded from a pre-2025-offseason
roster snapshot, so every player who changed teams in the offseason
(e.g. Rico Dowdle DAL->PIT, Kayshon Boutte NE->HOU, Aaron Rodgers NYJ->PIT,
Sam Darnold MIN->SEA, DK Metcalf SEA->PIT, George Pickens PIT->DAL) joined
to the WRONG game in the signal pipeline — the player->team->game mapping
in engine/snapshot_v4.py and v4/compute_v4.py attaches each player's rows
to their team's game, so a stale team_id silently puts the expert leg on
the wrong game_id.

The ECR feed (weekly rankings + projections CSVs, refreshed twice weekly)
is the freshest roster source in the pipeline; this script takes its Team
column as authoritative for the current week and updates players.team_id
to match. Abbreviation variants are normalized (LAR->LA, JAC->JAX) to the
teams table's canonical abbreviations.

Usage:
  bin/sync_roster_teams.py --week 1 [--season 2026] [--apply]

Without --apply this is a dry run: it reports every change it WOULD make
and exits 0. With --apply it performs the updates and exits 0 (or 2 if a
CSV team value can't be mapped to a known team — those players are
reported and skipped, never guessed).
"""
import argparse
import csv
import os
import re
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)
sys.path.insert(0, os.path.join(BASE, "..", "skills", "supabase-mgmt", "bin"))

ABBR_FIX = {"LAR": "LA", "JAC": "JAX", "ARZ": "ARI", "BLT": "BAL",
            "CLV": "CLE", "HST": "HOU"}

POSITIONS = ["qb", "rb", "wr", "te"]


def norm_name(n):
    return re.sub(r"\s+", " ", (n or "").strip().lower())


def read_team_map(week):
    """{(norm_name): (display_name, team_abbr)} from ECR CSVs."""
    out = {}
    fp = os.path.join(BASE, "data", "fantasypros")

    def add(path, name_col, team_col):
        if not os.path.exists(path):
            return 0
        n = 0
        with open(path, newline="", encoding="utf-8-sig") as f:
            r = csv.DictReader(f)
            for row in r:
                nm = (row.get(name_col) or "").strip().strip('"')
                tm = (row.get(team_col) or "").strip().strip('"').upper()
                if not nm or not tm:
                    continue
                tm = ABBR_FIX.get(tm, tm)
                out[norm_name(nm)] = (nm, tm)
                n += 1
        return n

    total = 0
    for pos in POSITIONS:
        total += add(os.path.join(fp, f"ecr_{pos}_wk{week}.csv"),
                     "PLAYER NAME", "TEAM")
        total += add(os.path.join(fp, f"proj_{pos}_wk{week}.csv"),
                     "Player", "Team")
    print(f"team map: {len(out)} players from {total} CSV rows", flush=True)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--week", type=int, required=True)
    ap.add_argument("--season", type=int, default=2026)
    ap.add_argument("--apply", action="store_true",
                    help="perform the updates (default: dry run)")
    a = ap.parse_args()

    import mgmt
    team_map = read_team_map(a.week)
    teams = {r["abbreviation"]: r["id"]
             for r in mgmt.query("select id, abbreviation from teams;")}
    players = mgmt.query(
        "select p.id, p.full_name, t.abbreviation as team "
        "from players p left join teams t on t.id = p.team_id;")

    changes, unmapped, unmatched = [], [], []
    for p in players:
        key = norm_name(p["full_name"])
        hit = team_map.get(key)
        if not hit:
            continue
        disp, csv_team = hit
        if csv_team not in teams:
            unmapped.append((p["full_name"], csv_team))
            continue
        if (p["team"] or "") != csv_team:
            changes.append({"id": p["id"], "name": p["full_name"],
                            "old": p["team"], "new": csv_team})

    print(f"players checked: {len(players)}, team changes needed: "
          f"{len(changes)}", flush=True)
    for c in sorted(changes, key=lambda c: c["name"]):
        print(f"  {c['name']}: {c['old']} -> {c['new']}", flush=True)
    if unmapped:
        print(f"WARNING: {len(unmapped)} CSV team values not in teams table "
              f"(skipped): {unmapped[:10]}", flush=True)

    if not a.apply:
        print("DRY RUN: no changes written. Re-run with --apply.",
              flush=True)
        return
    for c in changes:
        mgmt.query(
            f"update players set team_id = '{teams[c['new']]}' "
            f"where id = '{c['id']}';")
    print(f"APPLIED: {len(changes)} players.team_id updated.", flush=True)


if __name__ == "__main__":
    main()
