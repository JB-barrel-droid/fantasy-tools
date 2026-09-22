#!/usr/bin/env python3
"""Independent backtest of the kicker model on 2024-2025 actuals.

For every REG team-game: build the model's inputs strictly from pregame-
knowable data (closing spread/total -> implied total, dome, recorded
temp/wind as the forecast proxy, season-to-date red-zone rates through the
prior week, the team's primary kicker through the prior week with his prior
band accuracy), project with kicker_model.project_kicker(), and compare
expected_points against the kicker's ACTUAL fantasy points (conventional
3/4/5).

Baselines: (1) naive constant = league-mean kicker points every game;
(2) a fitted implied-total-only line. If the model cannot beat the naive
mean, this script says so -- principle 10.

Usage: backtest_kicker.py [--n-sims 2000] [--out results.json]
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, "/home/hatch/workspace/football-signal")
sys.path.insert(0, "/home/hatch/workspace/football-signal/engine")
sys.path.insert(0, "/home/hatch/workspace/football-signal/.venv/lib/python3.12/site-packages")

import kicker_model as km
from kicker_history import build_team_game_table, DATA_DIR  # noqa: E402

BANDS = km.BANDS


def _prior_kicker_accuracy():
    """{(season, team): {week: (name, makes, atts)}} -- accuracy known
    strictly before each week: prior full season (when available) plus
    current-season weeks < week."""
    import polars as pl
    frames = []
    for s in (2024, 2025):
        df = pl.read_parquet(DATA_DIR / f"pbp_{s}.parquet",
                             columns=["season", "week", "posteam",
                                      "field_goal_attempt", "kick_distance",
                                      "field_goal_result", "kicker_player_name"])
        frames.append(df.filter(pl.col("field_goal_attempt") == 1))
    fg = pl.concat(frames).with_columns(
        pl.col("kick_distance").map_elements(
            km.band_of, return_dtype=pl.String).alias("band"))
    out = {}
    for season in (2024, 2025):
        prior = fg.filter(pl.col("season") < season)  # 2024 for 2025; empty for 2024
        cur = fg.filter(pl.col("season") == season)
        for week in range(1, 19):
            wk = pl.concat([prior, cur.filter(pl.col("week") < week)]) \
                if len(prior) else cur.filter(pl.col("week") < week)
            if not len(wk):
                continue
            prim = (wk.group_by(["posteam", "kicker_player_name"])
                    .agg(pl.len().alias("n")).sort("n", descending=True)
                    .group_by("posteam").first())
            for r in prim.iter_rows(named=True):
                sub = wk.filter((pl.col("posteam") == r["posteam"])
                                & (pl.col("kicker_player_name") == r["kicker_player_name"]))
                makes = {b: sub.filter((pl.col("band") == b)
                                       & (pl.col("field_goal_result") == "made")).height
                         for b in BANDS}
                atts = {b: sub.filter(pl.col("band") == b).height for b in BANDS}
                out[(season, r["posteam"], week)] = (r["kicker_player_name"], makes, atts)
    return out


def _std_rz_rates():
    """{(season, team): {week: (off_rz_rate, def_rz_allowed)}} season-to-date
    through the prior week."""
    import polars as pl
    frames = [pl.read_parquet(DATA_DIR / f"pbp_{s}.parquet",
                              columns=["season", "week", "fixed_drive",
                                       "posteam", "defteam", "touchdown",
                                       "td_team", "yardline_100"])
              for s in (2024, 2025)]
    pbp = pl.concat(frames)
    drives = (
        pbp.filter(pl.col("posteam").is_not_null()
                   & pl.col("fixed_drive").is_not_null())
        .group_by(["season", "week", "fixed_drive", "posteam", "defteam"])
        .agg([
            pl.col("yardline_100").min().alias("min_yl"),
            ((pl.col("touchdown") == 1)
             & (pl.col("td_team") == pl.col("posteam"))).any().alias("off_td"),
        ])
        .filter(pl.col("min_yl") <= 20))
    out = {}
    for season in (2024, 2025):
        for week in range(1, 19):
            d = drives.filter((pl.col("season") == season) & (pl.col("week") < week))
            if not len(d):
                continue
            off = d.group_by("posteam").agg(
                (pl.col("off_td").sum() / pl.len()).alias("r"))
            deff = d.group_by("defteam").agg(
                (pl.col("off_td").sum() / pl.len()).alias("r"))
            off_d = dict(zip(off["posteam"], off["r"]))
            def_d = dict(zip(deff["defteam"], deff["r"]))
            for team in set(off_d) | set(def_d):
                out[(season, team, week)] = (off_d.get(team), def_d.get(team))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-sims", type=int, default=2000)
    ap.add_argument("--out", default="engine/data/kicker_backtest_2024_2025.json")
    args = ap.parse_args()

    tg = build_team_game_table().sort(["season", "week"])
    print("team-games:", len(tg))
    kick_acc = _prior_kicker_accuracy()
    rz = _std_rz_rates()

    preds, actuals, rows = [], [], []
    for i, r in enumerate(tg.iter_rows(named=True)):
        key = (r["season"], r["team"], r["week"])
        kname, makes, atts = kick_acc.get(key, (None, {}, {}))
        off_rz, def_rz = rz.get(key, (None, None))
        p = km.project_kicker(
            team_implied=r["implied_total"],
            rz_td_rate=off_rz, opp_rz_td_allowed=def_rz,
            kicker_makes=makes, kicker_atts=atts,
            temp_f=r["temp_f"], wind_mph=r["wind_mph"],
            precip_prob=None, dome=r["dome"],
            week=r["week"], n_sims=args.n_sims, seed=7)
        preds.append(p["expected_points"])
        actuals.append(r["kicker_pts_345"])
        rows.append({"season": r["season"], "week": r["week"], "team": r["team"],
                     "kicker": kname, "pred": p["expected_points"],
                     "actual": r["kicker_pts_345"],
                     "implied": round(r["implied_total"], 1)})
        if (i + 1) % 300 == 0:
            print(f"  {i + 1}/{len(tg)}")

    import numpy as np
    pred = np.array(preds)
    act = np.array(actuals)
    err = pred - act
    naive = np.full_like(act, act.mean())
    # fitted implied-only line (in-sample, generous to the baseline)
    imp = np.array([x["implied"] for x in rows])
    b, a = np.polyfit(imp, act, 1)
    line = a + b * imp

    def metrics(p, a):
        e = p - a
        return {"bias": round(float(e.mean()), 3),
                "mae": round(float(np.abs(e).mean()), 3),
                "rmse": round(float(np.sqrt((e ** 2).mean())), 3),
                "corr": round(float(np.corrcoef(p, a)[0, 1]), 3)}

    report = {
        "n": len(tg),
        "actual_mean": round(float(act.mean()), 3),
        "actual_std": round(float(act.std()), 3),
        "model": metrics(pred, act),
        "naive_constant": metrics(naive, act),
        "implied_line_insample": metrics(line, act),
        "implied_line": {"intercept": round(float(a), 3),
                         "slope": round(float(b), 4)},
    }
    out = Path("/home/hatch/workspace/football-signal") / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    json.dump({"report": report, "rows": rows}, open(out, "w"))
    print(json.dumps(report, indent=1))
    print("wrote", out)


if __name__ == "__main__":
    main()
