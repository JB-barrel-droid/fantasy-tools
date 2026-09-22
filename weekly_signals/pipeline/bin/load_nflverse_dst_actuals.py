#!/usr/bin/env python3
"""Load nflverse DST YTD actuals into Supabase season_actuals_ytd.

Derives team-defense stats from play-by-play (nflverse ships no team
defense table), credited to defteam unless noted:
  - sacks: sack == 1
  - interceptions: interception == 1
  - fumbles recovered: fumble_recovery_1_team == defteam
  - touchdowns: defensive return TDs only -- return_touchdown == 1 and
    td_team == defteam on scrimmage (run/pass) plays. ST return TDs are
    split out below (previously these were lumped together).
  - special_teams_touchdowns: return TDs on punt/kickoff/field_goal/
    extra_point plays (td_team == defteam), plus onside-kick recovery
    TDs (own_kickoff_recovery_td == 1, credited to the kicking team =
    posteam).
  - blocked_kicks: blocked punts (punt_blocked), blocked field goals
    (field_goal_result == 'blocked'), blocked PATs
    (extra_point_result == 'blocked'). All three flags exist in nflverse
    pbp; FG 'blocked' confirmed present in 2025 data.
  - safeties: safety == 1
  - yards_allowed: sum of yards_gained on run/pass/qb_kneel plays,
    excluding two-point conversions. Matches official NFL total net
    yards (kneels ARE included in the official number -- verified
    against 2026 Week 1 box scores: PIT 238, CIN 282, ARI 268, KC 176,
    all exact).
  - points_allowed: from load_schedules final scores (opponent's score)

Pulls fresh pbp AND fresh schedules (the lottery's cached pbp_2026.parquet
was stale as of 2026-09-16 -- missing the DEN@KC Monday game -- which
would silently zero out KC/DEN). Falls back to cache on failure, but
fail-closed: every game with a final score must have pbp rows or the
run aborts instead of writing zeros.

Grain matches the kicker loader: (season, player_norm, stat_key, actual)
with YTD aggregates. player_norm for defenses is the entity key
("dst:HOU") so it joins cleanly to fp_season_kdst_projections.

Idempotent: ON CONFLICT upserts. Re-running recomputes the same YTD.

Usage: load_nflverse_dst_actuals.py [--season 2026] [--dry-run]
"""
import argparse
import sys
from pathlib import Path

BIN = Path(__file__).resolve().parent
sys.path.insert(0, str(BIN.parent))
sys.path.insert(0, "/home/hatch/workspace/skills/supabase-mgmt/bin")

import polars as pl
from mgmt import query as sql  # noqa: E402
from engine.canonical_players import load_registry  # noqa: E402

LOT_DATA = Path("/home/hatch/workspace/goals/football-signal-database-and-app"
                "/lottery/data")

STAT_KEYS = ("sacks", "interceptions", "fumbles_recovered", "touchdowns",
             "special_teams_touchdowns", "blocked_kicks", "safeties",
             "yards_allowed", "points_allowed")
ST_PLAYS = ("punt", "kickoff", "field_goal", "extra_point")
SCRIMMAGE_PLAYS = ("run", "pass", "qb_kneel")


def _fresh_or_cached(loader, cache_name, season):
    """Fresh nflverse pull; fall back to the lottery cache on failure."""
    try:
        return loader([season]), "fresh"
    except Exception as e:
        print(f"fresh pull failed ({e}); using cache", flush=True)
        return pl.read_parquet(LOT_DATA / cache_name), "cache"


def load_dst_ytd(season):
    from nflreadpy import load_pbp, load_schedules
    pbp, pbp_src = _fresh_or_cached(load_pbp, f"pbp_{season}.parquet", season)
    sched, _ = _fresh_or_cached(load_schedules, "schedules.parquet", season)
    s = sched.filter(pl.col("season") == season)

    # Fail-closed coverage: every scored game must have pbp rows.
    scored = s.filter(pl.col("home_score").is_not_null())
    pbp_games = set(pbp.filter(pl.col("game_id").is_not_null())
                    ["game_id"].unique().to_list())
    missing = [r["game_id"] for r in scored.to_dicts()
               if r["game_id"] not in pbp_games]
    if missing:
        raise SystemExit(
            f"ABORT: pbp ({pbp_src}) missing {len(missing)} scored games: "
            f"{missing}. Refusing to write zero-rows.")

    sacks = (pbp.filter(pl.col("sack") == 1)
             .group_by("defteam").agg(pl.len().alias("sacks")))
    ints = (pbp.filter(pl.col("interception") == 1)
            .group_by("defteam").agg(pl.len().alias("interceptions")))
    fr = (pbp.filter(pl.col("fumble_recovery_1_team") == pl.col("defteam"))
          .group_by("defteam").agg(pl.len().alias("fumbles_recovered")))
    dtd = (pbp.filter((pl.col("return_touchdown") == 1) &
                      (pl.col("td_team") == pl.col("defteam")) &
                      (~pl.col("play_type").is_in(ST_PLAYS)))
           .group_by("defteam").agg(pl.len().alias("touchdowns")))
    sttd_rt = (pbp.filter((pl.col("return_touchdown") == 1) &
                          (pl.col("td_team") == pl.col("defteam")) &
                          (pl.col("play_type").is_in(ST_PLAYS)))
               .group_by("defteam").agg(pl.len().alias("sttd_rt")))
    sttd_ok = (pbp.filter(pl.col("own_kickoff_recovery_td") == 1)
               .group_by("posteam").agg(pl.len().alias("sttd_ok")))
    blk = (pbp.filter((pl.col("punt_blocked") == 1) |
                      ((pl.col("field_goal_attempt") == 1) &
                       (pl.col("field_goal_result") == "blocked")) |
                      ((pl.col("extra_point_attempt") == 1) &
                       (pl.col("extra_point_result") == "blocked")))
           .group_by("defteam").agg(pl.len().alias("blocked_kicks")))
    saf = (pbp.filter(pl.col("safety") == 1)
           .group_by("defteam").agg(pl.len().alias("safeties")))
    ya = (pbp.filter(pl.col("play_type").is_in(SCRIMMAGE_PLAYS) &
                     (pl.col("two_point_attempt") != 1))
          .group_by("defteam")
          .agg(pl.col("yards_gained").sum().alias("yards_allowed")))

    pa_rows = []
    for r in scored.to_dicts():
        pa_rows.append({"team": r["home_team"],
                        "points_allowed": r["away_score"]})
        pa_rows.append({"team": r["away_team"],
                        "points_allowed": r["home_score"]})
    pa = (pl.DataFrame(pa_rows).group_by("team")
          .agg(pl.col("points_allowed").sum()) if pa_rows else None)

    teams = s.select(pl.col("home_team").alias("team")).unique()
    out = teams.join(sacks, left_on="team", right_on="defteam", how="left")
    for df_, key in ((ints, "defteam"), (fr, "defteam"),
                     (dtd, "defteam"), (sttd_rt, "defteam"),
                     (blk, "defteam"), (saf, "defteam")):
        out = out.join(df_, left_on="team", right_on=key, how="left")
    out = out.join(sttd_ok, left_on="team", right_on="posteam", how="left")
    out = out.join(ya, left_on="team", right_on="defteam", how="left")
    if pa is not None:
        out = out.join(pa, on="team", how="left")
    out = out.with_columns(
        (pl.col("sttd_rt").fill_null(0) +
         pl.col("sttd_ok").fill_null(0)).alias("special_teams_touchdowns"))
    out = out.drop("sttd_rt", "sttd_ok")
    for c in STAT_KEYS:
        if c in out.columns:
            out = out.with_columns(pl.col(c).fill_null(0).cast(pl.Int64))
        else:
            out = out.with_columns(pl.lit(0).alias(c))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", type=int, default=2026)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    df = load_dst_ytd(a.season)
    print(f"{len(df)} defenses", flush=True)
    for r in df.sort("team").to_dicts():
        print(f"  {r['team']}: {r['sacks']} sacks, {r['interceptions']} INT, "
              f"{r['fumbles_recovered']} FR, {r['touchdowns']} defTD, "
              f"{r['special_teams_touchdowns']} stTD, {r['blocked_kicks']} blk, "
              f"{r['safeties']} saf, {r['yards_allowed']} yds, "
              f"{r['points_allowed']} PA", flush=True)

    if a.dry_run:
        return
    reg = load_registry()
    vals = []
    for r in df.to_dicts():
        pn = f"dst:{r['team']}"
        key = reg.lookup_dst(r["team"])
        key_sql = str(key) if key else "NULL"
        for k in STAT_KEYS:
            vals.append(f"({a.season},'{pn}',{key_sql},'{k}',{r[k]})")
    sql(f"""INSERT INTO season_actuals_ytd (season, player_norm, player_key,
            stat_key, actual)
            VALUES {','.join(vals)}
            ON CONFLICT (season, player_norm, stat_key)
            DO UPDATE SET actual = EXCLUDED.actual,
                          player_key = EXCLUDED.player_key;""")
    print(f"upserted {len(vals)} DST actual rows", flush=True)


if __name__ == "__main__":
    main()
