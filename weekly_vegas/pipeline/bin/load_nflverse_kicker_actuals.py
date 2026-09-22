"""Load nflverse kicker YTD actuals into season_actuals_ytd.

Reads the cached nflverse player_stats_<season>.parquet (lottery/data/),
aggregates fg_made / pat_made per kicker over played weeks, resolves each
kicker to the canonical numeric player_key via engine.canonical_players,
and upserts into public.season_actuals_ytd with stat_keys 'fg_made' and
'pat_made' (season = <season>). player_norm is the transitional label
(norm_plain — byte-identical to the old norm_loose labels for kickers).

Kicker identity: canonical registry, position=K. Unmatched kickers are
reported, never force-matched.

Usage:
  python3 bin/load_nflverse_kicker_actuals.py --season 2026
"""
import argparse
import json
import subprocess
import sys

BASE = "/home/hatch/workspace/football-signal"
LOT = "/home/hatch/workspace/goals/football-signal-database-and-app/lottery"
sys.path.insert(0, f"/home/hatch/workspace/skills/supabase-football-signal/bin")
sys.path.insert(0, BASE)
from engine.canonical_players import (  # noqa: E402
    load_registry, norm_plain, resolve)

MGMT = [sys.executable, "/home/hatch/workspace/skills/supabase-mgmt/bin/mgmt.py"]


def sql(s):
    r = subprocess.run(MGMT + [s], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"SQL failed: {r.stderr[:400]}\nSQL: {s[:200]}")
    return json.loads(r.stdout)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", type=int, required=True)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    import pandas as pd
    df = pd.read_parquet(f"{LOT}/data/player_stats_{a.season}.parquet")
    k = df[df["position"] == "K"]
    print(f"nflverse K rows: {len(k)}, weeks: {sorted(k['week'].unique())}", flush=True)
    # player_stats abbreviates first names ("N.Folk"); join rosters on GSIS id
    # for full names so norm_loose matches the players-table convention.
    ros = pd.read_parquet(f"{LOT}/data/rosters_weekly_{a.season}.parquet")
    ros = ros[ros["position"] == "K"][["gsis_id", "full_name"]].drop_duplicates()
    k = k.merge(ros, left_on="player_id", right_on="gsis_id", how="left")
    k["full_name"] = k["full_name"].fillna(k["player_name"])
    agg = (k.groupby("full_name", dropna=False)[["fg_made", "pat_made"]]
             .sum().reset_index())

    # Canonical identity: every nflverse kicker resolves to a numeric
    # player_key via the registry (position=K). Unmatched kickers are
    # reported, never force-matched. player_norm is the transitional label
    # (norm_plain — byte-identical to the old norm_loose labels for kickers;
    # none of the deleted alias entries were kickers).
    reg = load_registry()
    rows, unmatched = [], []
    for _, r in agg.iterrows():
        name = r["full_name"]
        key = resolve(name, position="K", registry=reg)
        if key is None:
            unmatched.append(f"{name} (norm={norm_plain(name)})")
            continue
        rows.append((key, norm_plain(name), float(r["fg_made"] or 0),
                     float(r["pat_made"] or 0)))
    print(f"matched: {len(rows)}, unmatched: {len(unmatched)}", flush=True)
    for u in unmatched:
        print("  UNMATCHED:", u)

    if a.dry_run or not rows:
        return
    vals = []
    for key, nn, fg, xp in rows:
        nnq = nn.replace("'", "''")
        vals.append(f"({a.season},'{nnq}',{key},'fg_made',{fg})")
        vals.append(f"({a.season},'{nnq}',{key},'pat_made',{xp})")
    sql(f"""INSERT INTO season_actuals_ytd (season, player_norm, player_key,
            stat_key, actual)
            VALUES {','.join(vals)}
            ON CONFLICT (season, player_norm, stat_key)
            DO UPDATE SET actual = EXCLUDED.actual,
                          player_key = EXCLUDED.player_key;""")
    print(f"upserted {len(vals)} actuals rows", flush=True)


if __name__ == "__main__":
    main()
