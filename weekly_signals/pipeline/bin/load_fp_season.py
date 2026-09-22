"""Load FantasyPros FULL-SEASON projections into Supabase, snapshotted by date.

Reads data/fantasypros/season_proj_{qb,rb,wr,te}.csv (downloaded via the
browser task from fantasypros.com/nfl/projections/{pos}.php season view;
the account owner authorized the pull).

Writes public.fp_season_projections with the GRANULAR stat components
(pass/rush/receiving/fumbles) plus all three scoring formats computed via
engine.scoring.fantasy_points, so any format can be (re)calculated later.

Snapshotting: every run inserts under a snapshot_date (default: today CT).
Re-running for the same date is idempotent (that date's rows are replaced),
so historical snapshots accumulate over the season and projection movement
can be tracked: e.g. compare v_fp_season_latest vs any prior snapshot_date.

Usage:
  python3 bin/load_fp_season.py [--as-of 2026-09-11] [--season 2026]
"""
import argparse
import os
import sys
from datetime import datetime, timezone, timedelta

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # weekly_signals/pipeline root
DATA_DIR = os.path.join(BASE, "data", "fantasypros")
SB = os.path.expanduser("~/workspace/skills/supabase-football-signal/bin")
for _p in (BASE, SB, os.path.join(BASE, "loaders")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import sbclient
from engine.scoring import fantasy_points
from engine.canonical_players import load_registry, resolve_skill
from fantasypros import (  # noqa: E402
    PROJ_SCHEMA, validate_proj_headers, parse_num,
    read_csv, find_col,
)

TABLE = "fp_season_projections"

# Season snapshot is a 4-position dataset (qb/rb/wr/te) by design — the job
# downloads exactly these four CSVs and the table has never held K/DST rows.
# Do NOT use the shared loaders.fantasypros.POSITIONS here: other consumers
# extended it to k/dst and the loader fail-closed on the missing files.
SEASON_POSITIONS = ("qb", "rb", "wr", "te")


def load_position(pos, snapshot_date, season, source_url, data_dir, registry):
    path = os.path.join(data_dir, f"season_proj_{pos}.csv")
    if not os.path.exists(path):
        return None
    headers, rows = read_csv(path)
    col_idx = validate_proj_headers(pos, headers)
    schema = PROJ_SCHEMA[pos]
    i_team = find_col(headers, "team")
    out, gaps, seen = [], [], set()
    for r in rows:
        if len(r) < 2:
            continue
        name = (r[0] or "").strip()
        if not name:
            continue
        # Canonical identity: skill-position name match against the players
        # table, fail-closed on ambiguity. The CSV's fantasy slot is not a
        # disambiguator (FBs/TEs appear in the RB file), so this is the
        # position-blind skill sweep, not the strict position filter.
        pkey = resolve_skill(name, registry=registry)
        if pkey is None:
            gaps.append(name)
            continue
        if pkey in seen:
            gaps.append(f"{name} (dup of same player, kept first)")
            continue
        seen.add(pkey)
        pl = registry.by_key[pkey]
        stats = {}
        for j, (_kw, key) in enumerate(schema):
            if key:
                stats[key] = parse_num(r[col_idx[j]] if col_idx[j] < len(r) else "")
        # FantasyPros' own FPTS column is the last schema col (key None)
        fp_fpts = parse_num(r[col_idx[-1]] if col_idx[-1] < len(r) else "")
        out.append({
            "snapshot_date": snapshot_date,
            "season": season,
            "player_id": pl["uuid"],
            "player_key": pkey,
            "position": pos.upper(),
            "canon_pos": (pl.get("position") or "").upper(),  # popped before insert
            "team": (r[i_team] or "").strip() if i_team is not None and i_team < len(r) else None,
            "pass_att": stats.get("pass_att"),
            "cmp": stats.get("cmp"),
            "passing_yards": stats.get("passing_yards"),
            "passing_tds": stats.get("passing_tds"),
            "interceptions": stats.get("interceptions"),
            "rush_att": stats.get("rush_att"),
            "rushing_yards": stats.get("rushing_yards"),
            "rushing_tds": stats.get("rushing_tds"),
            "receptions": stats.get("receptions"),
            "receiving_yards": stats.get("receiving_yards"),
            "receiving_tds": stats.get("receiving_tds"),
            "fumbles_lost": stats.get("fumbles_lost"),
            "fp_fpts": fp_fpts,
            "proj_standard": fantasy_points(stats, "standard"),
            "proj_half_ppr": fantasy_points(stats, "half_ppr"),
            "proj_full_ppr": fantasy_points(stats, "ppr"),
            "source_url": source_url,
        })
    return out, gaps


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--as-of", default=None,
                    help="snapshot date YYYY-MM-DD; defaults to today CT")
    ap.add_argument("--season", type=int, default=2026)
    ap.add_argument("--csv-dir", default=None,
                    help="directory holding season_proj_{pos}.csv; defaults to "
                         "data/fantasypros/")
    a = ap.parse_args()
    data_dir = a.csv_dir or DATA_DIR
    if a.as_of:
        snapshot_date = a.as_of
    else:
        ct = timezone(timedelta(hours=-5))
        snapshot_date = datetime.now(ct).strftime("%Y-%m-%d")
    total, all_gaps = 0, {}
    # One canonical registry for the whole run (loaded before any parsing,
    # so a players-table outage fails closed before the date is touched).
    registry = load_registry()
    # Fail-closed: parse + validate ALL files first, then replace the date.
    parsed = {}
    for pos in SEASON_POSITIONS:
        url = f"https://www.fantasypros.com/nfl/projections/{pos}.php"
        res = load_position(pos, snapshot_date, a.season, url, data_dir,
                            registry)
        if res is None:
            print(f"BLOCKED: missing {os.path.join(data_dir, f'season_proj_{pos}.csv')}; "
                  f"not touching existing rows for {snapshot_date}")
            sys.exit(2)
        parsed[pos] = res
    # idempotent per date: replace this date's rows, keep history
    sbclient.delete(TABLE, f"?snapshot_date=eq.{snapshot_date}")
    # cross-position dedupe: one row per (snapshot_date, player_key);
    # prefer the row from the player's canonical position
    best, dup_notes = {}, []
    for pos in SEASON_POSITIONS:
        rows, gaps = parsed[pos]
        for r in rows:
            pid = r["player_key"]
            cur = best.get(pid)
            if cur is None:
                best[pid] = r
                continue
            want = r.get("canon_pos") == r["position"]
            have = cur.get("canon_pos") == cur["position"]
            if want and not have:
                dup_notes.append(f"{pid}: kept {r['position']}, dropped {cur['position']}")
                best[pid] = r
            else:
                dup_notes.append(f"{pid}: kept {cur['position']}, dropped {r['position']}")
        print(f"{pos}: {len(rows)} players, {len(gaps)} unmatched: {gaps[:8]}")
    final = []
    for r in best.values():
        r.pop("canon_pos", None)
        final.append(r)
    for i in range(0, len(final), 200):
        sbclient.post(TABLE, final[i:i + 200])
    total = len(final)
    if dup_notes:
        print(f"cross-position dups resolved: {dup_notes[:10]}")
    print(f"snapshot {snapshot_date}: {total} rows -> {TABLE}")


if __name__ == "__main__":
    main()
