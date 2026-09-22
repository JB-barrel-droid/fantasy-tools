"""Load FantasyPros FULL-SEASON K and DST projections into Supabase.

Reads data/fantasypros/season_snapshots/{date}/season_proj_{k,dst}.csv
(downloaded via the browser task from fantasypros.com/nfl/projections/{k,dst}.php
season view).

Writes public.fp_season_kdst_projections, one dated snapshot per run.
K rows key off the players table (entity_key 'k:<player_id>'); DST rows key
off the teams table (entity_key 'dst:<abbr>', FP names the full team e.g.
"Seattle Seahawks").

Header validation is fail-closed via loaders.fantasypros.validate_proj_headers
(raises on misalignment — never force it). Points are computed with OUR
engine (engine.scoring.kicker_points / dst_points), not FP's FPTS column,
so the number is checkable against our scoring; fp_fpts is stored for
cross-check.

DST per-game caution: the CSV holds FULL-SEASON components. dst_points()
is per-game shaped (PA/YA brackets are per-game) — build_values.py converts
to per-game rates before scoring. Never score season totals directly.

Usage:
  python3 bin/load_fp_season_kdst.py --csv-dir data/fantasypros/season_snapshots/2026-09-16 --as-of 2026-09-16
"""
import argparse
import os
import re
import sys
from datetime import datetime, timezone, timedelta

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # weekly_vegas/pipeline root
DATA_DIR = os.path.join(BASE, "data", "fantasypros")
SB = os.path.expanduser("~/workspace/skills/supabase-football-signal/bin")
for _p in (BASE, SB, os.path.join(BASE, "loaders")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import sbclient
from engine.scoring import (kicker_points, dst_points, dst_component_points,
                            dst_bracket_points)
from engine.canonical_players import (load_registry, resolve,
                                      norm_plain)
from fantasypros import (  # noqa: E402
    PROJ_SCHEMA, validate_proj_headers, parse_num,
    read_csv,
)

TABLE = "fp_season_kdst_projections"

# Full team name ("Seattle Seahawks", "San Francisco 49ers") -> abbreviation
# via teams.name mascot. Mascot may contain digits ("49ers").
# The teams table has stale duplicate rows (STL/SD/OAK); prefer current
# abbreviations so downstream games_remaining maps resolve.
_STALE_ABBR = {"STL": "LA", "SD": "LAC", "OAK": "LV"}


def team_abbr(full_name, by_mascot):
    m = re.search(r"([A-Za-z0-9]+)$", (full_name or "").strip())
    if not m:
        return None
    abbr = by_mascot.get(m.group(1).lower())
    return _STALE_ABBR.get(abbr, abbr)


def load_k(snapshot_date, season, data_dir, registry):
    path = os.path.join(data_dir, "season_proj_k.csv")
    if not os.path.exists(path):
        return None
    headers, rows = read_csv(path)
    col_idx = validate_proj_headers("k", headers)
    schema = PROJ_SCHEMA["k"]
    out, gaps, seen = [], [], set()
    for r in rows:
        if len(r) < 2:
            continue
        name = (r[0] or "").strip()
        if not name:
            continue
        # Canonical identity: kickers resolve position-aware (K) against the
        # players table. Unmatched stays a gap (fail-closed), never a guess.
        pkey = resolve(name, position="K", registry=registry)
        if pkey is None:
            gaps.append(name)
            continue
        if pkey in seen:
            gaps.append(f"{name} (dup, kept first)")
            continue
        seen.add(pkey)
        pl = registry.by_key[pkey]
        # Display name: the players table's full_name ONLY (user rule
        # 2026-09-18). The source spelling is never substituted -- a
        # resolved key always has a canonical name, so its absence is a
        # data bug, not a gap.
        if not pl.get("full_name"):
            raise SystemExit(
                f"FAIL-CLOSED: player_key {pkey} has no canonical "
                "players-table name; refusing to use the source spelling "
                f"{name!r}.")
        stats = {}
        for j, (_kw, key) in enumerate(schema):
            if key:
                stats[key] = parse_num(r[col_idx[j]] if col_idx[j] < len(r) else "")
        # schema keys: fg_made, fg_att, pat_made -> our columns
        fg = stats.get("fg_made", 0.0)
        xp = stats.get("pat_made", 0.0)
        pts = kicker_points({"fg_made": fg, "xp_made": xp})
        fp_fpts = parse_num(r[col_idx[-1]] if col_idx[-1] < len(r) else "")
        team = (r[1] or "").strip() if len(r) > 1 else None
        out.append({
            "snapshot_date": snapshot_date, "season": season,
            "entity_key": f"k:{pl['uuid']}", "position": "K",
            "player_key": pkey,
            "player_norm": norm_plain(name),
            "team": team or pl.get("team"),
            "display_name": pl["full_name"],
            "fg_made": fg, "fg_att": stats.get("fg_att", 0.0),
            "xp_made": xp, "xp_att": 0.0,
            "proj_points": pts,
            "fp_fpts": fp_fpts,
            "bracket_pts": 0.0,
            "drift_note": "K scoring matches FP exactly (3/FG + 1/XP)",
            "source_url": "https://www.fantasypros.com/nfl/projections/k.php",
            "_comp_season": pts,
            "_fp_fpts": fp_fpts,
        })
    return out, gaps


def load_dst(snapshot_date, season, data_dir, registry):
    path = os.path.join(data_dir, "season_proj_dst.csv")
    if not os.path.exists(path):
        return None
    headers, rows = read_csv(path)
    col_idx = validate_proj_headers("dst", headers)
    schema = PROJ_SCHEMA["dst"]
    teams = sbclient.get("teams", "?select=abbreviation,name&limit=100")
    by_mascot = {t["name"].lower(): t["abbreviation"] for t in teams if t.get("name")}
    out, gaps = [], []
    for r in rows:
        if len(r) < 1:
            continue
        full = (r[0] or "").strip()
        if not full:
            continue
        abbr = team_abbr(full, by_mascot)
        if abbr is None:
            gaps.append(full)
            continue
        # Canonical identity for team defenses via the registry's DST token
        # map ("Seattle Seahawks"/"Seahawks"/"Seattle" -> player_key). A miss
        # keeps the row (today's abbr-keyed universe is unchanged) with a
        # NULL key and a loud gap — never a guessed key.
        pkey = registry.lookup_dst(full)
        if pkey is None:
            gaps.append(f"{full} (no DST player_key)")
        stats = {}
        for j, (_kw, key) in enumerate(schema):
            if key:
                stats[key] = parse_num(r[col_idx[j]] if col_idx[j] < len(r) else "")
        # per-game rates for scoring (season totals / 17), then scale later
        pg = {k: v / 17.0 for k, v in stats.items()}
        dst_stats = {
            "sacks": pg.get("sacks", 0.0),
            "interceptions": pg.get("interceptions", 0.0),
            "fumbles_recovered": pg.get("fumble_recoveries", 0.0),
            "touchdowns": pg.get("def_tds", 0.0),
            "safeties": pg.get("safeties", 0.0),
            "points_allowed": pg.get("points_allowed", 0.0),
            "yards_allowed": pg.get("yards_allowed", 0.0),
        }
        comp_pg = dst_component_points(dst_stats)
        bracket_pg = dst_bracket_points(dst_stats)
        fp_fpts = parse_num(r[col_idx[-1]] if col_idx[-1] < len(r) else "")
        # Display name: the players table's full_name by key ONLY (user rule
        # 2026-09-18) -- never the raw source row text. NULL-key rows keep
        # no canonical name (they never reach the chart: build_values only
        # reads player_key IS NOT NULL).
        _dst_canon = (registry.by_key.get(pkey) or {}).get("full_name")
        if pkey is not None and not _dst_canon:
            raise SystemExit(
                f"FAIL-CLOSED: player_key {pkey} has no canonical "
                "players-table name; refusing to use the source spelling "
                f"{full!r}.")
        out.append({
            "snapshot_date": snapshot_date, "season": season,
            "entity_key": f"dst:{abbr}", "position": "DST",
            "player_key": pkey,
            "player_norm": norm_plain(full),
            "team": abbr, "display_name": _dst_canon,
            "dst_sacks": stats.get("sacks", 0.0),
            "dst_int": stats.get("interceptions", 0.0),
            "dst_fum_rec": stats.get("fumble_recoveries", 0.0),
            "dst_td": stats.get("def_tds", 0.0),
            "dst_safety": stats.get("safeties", 0.0),
            "dst_points_allowed": stats.get("points_allowed", 0.0),
            "dst_yards_allowed": stats.get("yards_allowed", 0.0),
            "proj_points": round((comp_pg + bracket_pg) * 17.0, 2),
            "fp_fpts": fp_fpts,
            "bracket_pts": round(bracket_pg * 17.0, 2),
            "drift_note": "FP FPTS = components only (no PA/YA brackets); "
                          "ours adds PA/YA brackets per FP-default scoring",
            "source_url": "https://www.fantasypros.com/nfl/projections/dst.php",
            "_comp_season": round(comp_pg * 17.0, 2),
            "_fp_fpts": fp_fpts,
        })
    return out, gaps


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--as-of", default=None)
    ap.add_argument("--season", type=int, default=2026)
    ap.add_argument("--csv-dir", default=None)
    a = ap.parse_args()
    data_dir = a.csv_dir or DATA_DIR
    if a.as_of:
        snapshot_date = a.as_of
    else:
        ct = timezone(timedelta(hours=-5))
        snapshot_date = datetime.now(ct).strftime("%Y-%m-%d")

    # One canonical registry for the whole run (loaded before the date is
    # touched, so a players-table outage fails closed instead of wiping).
    registry = load_registry()

    # idempotent per date: replace this date's rows
    sbclient.delete(TABLE, f"?snapshot_date=eq.{snapshot_date}")

    total, all_gaps = 0, {}
    for pos, loader in (("k", load_k), ("dst", load_dst)):
        res = loader(snapshot_date, a.season, data_dir, registry)
        if res is None:
            print(f"{pos}: CSV missing, skipped loudly (not silent)")
            all_gaps[pos] = ["CSV missing"]
            continue
        rows, gaps = res
        for r in rows:
            comp_season = r.pop("_comp_season", None)
            fp_fpts = r.pop("_fp_fpts", None)
            sbclient.post(TABLE, r)
            # cross-check: our component points vs FP's own FPTS.
            # K: must match (same formula). DST: components must match;
            # the PA/YA bracket delta is expected and stored as bracket_pts.
            if fp_fpts and comp_season is not None:
                if abs(fp_fpts - comp_season) > 1.0:
                    print(f"  COMPONENT DRIFT {r['display_name']}: "
                          f"ours {comp_season} vs FP {fp_fpts}")
            elif fp_fpts and abs(fp_fpts - r["proj_points"]) > 1.0:
                print(f"  FPTS drift {r['display_name']}: "
                      f"ours {r['proj_points']} vs FP {fp_fpts}")
        total += len(rows)
        all_gaps[pos] = gaps
        print(f"{pos}: {len(rows)} rows, {len(gaps)} gaps")
        for g in gaps[:10]:
            print(f"  gap: {g}")
    print(f"total {total} rows for {snapshot_date}")


if __name__ == "__main__":
    main()
