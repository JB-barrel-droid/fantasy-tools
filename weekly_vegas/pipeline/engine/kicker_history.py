#!/usr/bin/env python3
"""Historical kicker analog library (2024-2025 nflverse).

Builds a per-team-game table with pregame context (implied total from the
closing spread/total, spread, dome/outdoor, recorded temp/wind) and the
kicker's actual fantasy output. find_analogs() implements Upright principle 3:
match the current game context against comparable historical team-games and
return the empirical distribution of kicker points as a cross-check on the
Monte Carlo projection.

All data is our own nflverse pull -- no Upright data anywhere in this file.
"""
import sys
from pathlib import Path

sys.path.insert(0, "/home/hatch/workspace/football-signal")
sys.path.insert(0, "/home/hatch/workspace/football-signal/.venv/lib/python3.12/site-packages")

from kicker_model import BANDS, band_of, SCORING  # noqa: E402

DATA_DIR = Path("/home/hatch/workspace/goals/football-signal-database-and-app/lottery/data")
CACHE = Path(__file__).parent / "data" / "kicker_team_games_2024_2025.parquet"
SEASONS = [2024, 2025]


def _red_zone_rates(pbp):
    """Per team-game red-zone trips and TDs from play-by-play.

    A trip = an offensive drive (fixed_drive) that reached yardline_100<=20.
    A converted trip = that drive ended in an offensive TD for the same team.
    """
    import polars as pl
    drives = (
        pbp.filter(pl.col("posteam").is_not_null() & pl.col("fixed_drive").is_not_null())
        .group_by(["season", "week", "game_id", "fixed_drive", "posteam"])
        .agg([
            pl.col("yardline_100").min().alias("min_yl"),
            ((pl.col("touchdown") == 1) & (pl.col("td_team") == pl.col("posteam")))
            .any().alias("off_td"),
        ])
        .filter(pl.col("min_yl") <= 20)
    )
    return (
        drives.group_by(["season", "week", "posteam"])
        .agg([pl.len().alias("rz_trips"),
              pl.col("off_td").sum().alias("rz_tds")])
    )


def _kicker_game_stats(pbp):
    """Per team-game kicker output: FG att/makes by band, PAT att/makes,
    actual fantasy points (conventional 3/4/5), primary kicker name."""
    import polars as pl
    fg = pbp.filter(pl.col("field_goal_attempt") == 1).with_columns(
        pl.col("kick_distance").map_elements(band_of, return_dtype=pl.String).alias("band"))
    fg_pts = fg.with_columns(
        pl.when(pl.col("field_goal_result") == "made")
        .then(pl.col("band").replace_strict(
            {"20_29": 3.0, "30_39": 3.0, "40_49": 4.0, "50_plus": 5.0}))
        .otherwise(0.0).alias("fg_pts"))
    fg_tg = fg_pts.group_by(["season", "week", "posteam"]).agg([
        pl.len().alias("fg_att"),
        (pl.col("field_goal_result") == "made").sum().alias("fg_made"),
        pl.col("fg_pts").sum().alias("fg_pts_345"),
        pl.col("kicker_player_name").mode().first().alias("kicker"),
    ])
    pat = pbp.filter(pl.col("extra_point_attempt") == 1)
    pat_tg = pat.group_by(["season", "week", "posteam"]).agg([
        pl.len().alias("pat_att"),
        (pl.col("extra_point_result") == "good").sum().alias("pat_made"),
    ])
    # NOTE: full outer join -- an earlier version joined PATs off the FG
    # table (left join), silently dropping PAT points in the ~11% of
    # team-games with zero FG attempts. Same bug class as the old
    # FG_PER_IMPLIED_PT numerator/denominator mix; do not reintroduce.
    return fg_tg.join(pat_tg, on=["season", "week", "posteam"], how="full",
                      coalesce=True)


def build_team_game_table(force=False):
    """Build (or rebuild) the cached per-team-game table. Returns DataFrame."""
    import polars as pl
    if CACHE.exists() and not force:
        return pl.read_parquet(CACHE)
    pbp = pl.concat([
        pl.read_parquet(DATA_DIR / f"pbp_{s}.parquet") for s in SEASONS])
    sched = pl.read_parquet(DATA_DIR / "schedules.parquet").filter(
        pl.col("season").is_in(SEASONS) & (pl.col("game_type") == "REG"))

    home = sched.select([
        "season", "week", "game_id",
        pl.col("home_team").alias("team"),
        pl.col("away_team").alias("opp"),
        ((pl.col("total_line") + pl.col("spread_line")) / 2).alias("implied_total"),
        pl.col("spread_line").alias("spread"),
        pl.lit("home").alias("ha"),
        pl.col("roof").is_in(["dome", "closed"]).alias("dome"),
        pl.col("temp").cast(pl.Float64).alias("temp_f"),
        pl.col("wind").cast(pl.Float64).alias("wind_mph"),
    ])
    away = sched.select([
        "season", "week", "game_id",
        pl.col("away_team").alias("team"),
        pl.col("home_team").alias("opp"),
        ((pl.col("total_line") - pl.col("spread_line")) / 2).alias("implied_total"),
        (-pl.col("spread_line")).alias("spread"),
        pl.lit("away").alias("ha"),
        pl.col("roof").is_in(["dome", "closed"]).alias("dome"),
        pl.col("temp").cast(pl.Float64).alias("temp_f"),
        pl.col("wind").cast(pl.Float64).alias("wind_mph"),
    ])
    tg = pl.concat([home, away])
    rz = _red_zone_rates(pbp)
    ks = _kicker_game_stats(pbp)
    tg = (tg.join(rz, left_on=["season", "week", "team"],
                  right_on=["season", "week", "posteam"], how="left")
            .join(ks, left_on=["season", "week", "team"],
                  right_on=["season", "week", "posteam"], how="left"))
    tg = tg.with_columns([
        pl.col("fg_att").fill_null(0), pl.col("fg_made").fill_null(0),
        pl.col("fg_pts_345").fill_null(0.0),
        pl.col("pat_att").fill_null(0), pl.col("pat_made").fill_null(0),
        pl.col("rz_trips").fill_null(0), pl.col("rz_tds").fill_null(0),
    ]).with_columns(
        (pl.col("fg_pts_345") + pl.col("pat_made")).alias("kicker_pts_345"))
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    tg.write_parquet(CACHE)
    print(f"wrote {len(tg)} team-games -> {CACHE}")
    return tg


def find_analogs(implied_total, spread=None, dome=None, k=60, min_k=20):
    """Empirical kicker-point distribution from comparable team-games.

    Matches on venue class (dome vs outdoor) and normalized distance in
    (implied_total, spread). Returns mean/p10/p50/p90 of ACTUAL kicker
    points (conventional 3/4/5) across the k nearest analogs -- a reality
    check on the Monte Carlo mean, not a replacement for it.
    """
    import polars as pl
    import numpy as np
    tg = build_team_game_table()
    pool = tg
    if dome is not None:
        pool = pool.filter(pl.col("dome") == dome)
    if len(pool) < min_k:
        pool = tg  # fall back to the full library rather than nothing
    imp = pool["implied_total"].to_numpy()
    dist = np.abs(imp - implied_total) / 3.0
    if spread is not None:
        dist = dist + np.abs(pool["spread"].to_numpy() - spread) / 7.0
    idx = np.argsort(dist)[:k]
    sub = pool[idx]
    pts = sub["kicker_pts_345"].to_numpy()
    return {
        "n": len(sub),
        "mean_pts": round(float(np.mean(pts)), 2),
        "p10": round(float(np.quantile(pts, 0.10)), 1),
        "p50": round(float(np.quantile(pts, 0.50)), 1),
        "p90": round(float(np.quantile(pts, 0.90)), 1),
        "mean_att": round(float(sub["fg_att"].mean()), 2),
        "mean_implied": round(float(sub["implied_total"].mean()), 2),
    }


if __name__ == "__main__":
    tg = build_team_game_table()
    print(tg.head(3))
    for imp, dome in [(24, False), (24, True), (27, False)]:
        print(f"implied={imp} dome={dome}:", find_analogs(imp, dome=dome))
