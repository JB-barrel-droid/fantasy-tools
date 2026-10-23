#!/usr/bin/env python3
"""JEG-943: first honest backtest of projection source accuracy.

    python3 tools/research/source_accuracy_backtest.py

Uses the data we actually have:
- ROS projections per source per week from data/history/week-N.json (weeks 2-7)
- ESPN weekly projections from data/inputs/espn_weekly_projections_2026.csv
- Actuals from data/inputs/weekly_actuals_2024_2026.csv (2026 weeks 1-6)

The question: which projection source (ESPN, CBS ROS, Razzball) best predicts
next-week fantasy points, and does weighting them improve on the equal-weight
mean?

Limitations stated upfront:
- ROS projections are not week-ahead projections; they predict rest-of-season
  per-game, not next-week points. We use them as a proxy.
- Only 2026 weeks 2-6 have both saved ROS projections and actuals (5 weeks).
- CBS ROS is missing weeks 2-3; Razzball missing week 2.
- ESPN weekly (week-ahead) projections exist but only for one source.
- This is a preliminary pass; the full backtest needs aligned week-ahead
  projections from all sources (JEG-944).

Writes:
  docs/research/data/source_accuracy_backtest.json
  docs/research/data/source_accuracy_backtest.md
"""
from __future__ import annotations

import csv
import json
import math
import statistics
from collections import defaultdict
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
HISTORY = REPO / "data" / "history"
ACTUALS_FILE = REPO / "data" / "inputs" / "weekly_actuals_2024_2026.csv"
ESPN_WEEKLY = REPO / "data" / "inputs" / "espn_weekly_projections_2026.csv"
PLAYERS_FILE = REPO / "data" / "fixtures" / "current" / "players.json"
OUT_DIR = REPO / "docs" / "research" / "data"

PROJECTION_SOURCES = ["espn", "cbsros", "razzball"]
SCORINGS = {"ppr": 2, "half_ppr": 1, "standard": 0}  # index into ppg list
SCORING_MAP_ACTUALS = {"ppr": "ppr", "half_ppr": "half_ppr", "standard": "std"}
WEEKS = [2, 3, 4, 5, 6]  # weeks where we have ROS projections AND next-week actuals
POSITIONS = ["QB", "RB", "WR", "TE"]
SEED = 20261023
N_BOOT = 1000


def load_players():
    """Load player_key -> position mapping."""
    with open(PLAYERS_FILE) as f:
        players = json.load(f)
    pos_of = {}
    if isinstance(players, dict):
        # players.json has {meta: ..., players: [...]}
        player_list = players.get("players", [])
        if not player_list and "meta" not in players:
            # keyed by player_key
            for pk, info in players.items():
                if isinstance(info, dict):
                    pos_of[str(pk)] = info.get("position", info.get("pos", ""))
            return pos_of
        for p in player_list:
            pos_of[str(p.get("player_key", ""))] = p.get("position", p.get("pos", ""))
    elif isinstance(players, list):
        for p in players:
            pos_of[str(p.get("player_key", ""))] = p.get("position", p.get("pos", ""))
    return pos_of


def load_actuals():
    """Load 2026 actuals: {(week, player_key): {scoring: points}}."""
    actuals = {}
    with open(ACTUALS_FILE) as f:
        for row in csv.DictReader(f):
            if row["season"] != "2026":
                continue
            week = int(row["week"])
            pk = row["player_key"]
            actuals[(week, pk)] = {
                "ppr": float(row["ppr"]),
                "half_ppr": float(row["half_ppr"]),
                "standard": float(row["std"]),
            }
    return actuals


def load_espn_weekly():
    """Load ESPN week-ahead projections: {(week, player_key): {scoring: ppg}}."""
    projs = {}
    with open(ESPN_WEEKLY) as f:
        for row in csv.DictReader(f):
            week = int(row["week"])
            pk = row["player_key"]
            projs[(week, pk)] = {
                "ppr": float(row["ppr"]),
                "half_ppr": float(row["half_ppr"]),
                "standard": float(row["std"]),
            }
    return projs


def load_ros_projections():
    """Load ROS projections from history: {week: {source: {player_key: {scoring: ppg}}}}."""
    ros = {}
    for w in range(2, 8):
        fn = HISTORY / f"week-{w}.json"
        if not fn.exists():
            continue
        with open(fn) as f:
            data = json.load(f)
        ros[w] = {}
        for src in PROJECTION_SOURCES:
            if src not in data["sources"]:
                continue
            s = data["sources"][src]
            ppg = s.get("ppg", {})
            ros[w][src] = {}
            for pk, vals in ppg.items():
                if isinstance(vals, list) and len(vals) >= 3:
                    ros[w][src][pk] = {
                        "standard": vals[0],
                        "half_ppr": vals[1],
                        "ppr": vals[2],
                    }
    return ros


def mae(errors):
    return np.mean(np.abs(errors)) if len(errors) > 0 else float("nan")


def rmse(errors):
    return np.sqrt(np.mean(errors ** 2)) if len(errors) > 0 else float("nan")


def spearman(x, y):
    if len(x) < 3:
        return float("nan")
    from scipy.stats import spearmanr
    r, _ = spearmanr(x, y)
    return r


def bootstrap_ci(values, stat_fn, n_boot=N_BOOT, alpha=0.05):
    rng = np.random.default_rng(SEED)
    n = len(values)
    if n == 0:
        return float("nan"), float("nan")
    stats = []
    for _ in range(n_boot):
        idx = rng.integers(0, n, size=n)
        stats.append(stat_fn(values[idx]))
    lo = np.percentile(stats, 100 * alpha / 2)
    hi = np.percentile(stats, 100 * (1 - alpha / 2))
    return float(lo), float(hi)


def run():
    pos_of = load_players()
    actuals = load_actuals()
    ros = load_ros_projections()
    espn_weekly = load_espn_weekly()

    results = {}
    scoring = "ppr"  # primary scoring

    # For each week, build the projection vs actual pairs
    # A pair: (week, player_key, source_projections, actual_points)
    pairs = []  # list of dicts
    for week in WEEKS:
        # Next week's actuals
        next_week = week  # ROS projection from week W, actuals from week W
        # Actually: the ROS projection saved in week W predicts the rest of
        # the season. The next game is week W (the content week). So we compare
        # the ROS ppg from the week-W snapshot against actual points in week W.
        for pk in set(k[1] for k in actuals if k[0] == next_week):
            if pk not in pos_of or pos_of[pk] not in POSITIONS:
                continue
            actual = actuals.get((next_week, pk), {}).get(scoring)
            if actual is None:
                continue
            row = {
                "week": week,
                "player_key": pk,
                "position": pos_of[pk],
                "actual": actual,
            }
            # ROS projections from each source
            for src in PROJECTION_SOURCES:
                if week in ros and src in ros[week] and pk in ros[week][src]:
                    row[f"ros_{src}"] = ros[week][src][pk][scoring]
            # ESPN weekly projection
            if (week, pk) in espn_weekly:
                row["weekly_espn"] = espn_weekly[(week, pk)][scoring]
            pairs.append(row)

    print(f"Total pairs: {len(pairs)} (weeks {WEEKS}, {scoring})")

    # Per-source accuracy
    source_errors = defaultdict(list)
    source_pairs = defaultdict(list)

    for row in pairs:
        actual = row["actual"]
        for src in PROJECTION_SOURCES:
            key = f"ros_{src}"
            if key in row:
                err = row[key] - actual
                source_errors[src].append(err)
                source_pairs[src].append((row[key], actual))
        if "weekly_espn" in row:
            err = row["weekly_espn"] - actual
            source_errors["espn_weekly"].append(err)
            source_pairs["espn_weekly"].append((row["weekly_espn"], actual))

    # Equal-weight mean of ROS sources
    mean_errors = []
    for row in pairs:
        vals = []
        for src in PROJECTION_SOURCES:
            key = f"ros_{src}"
            if key in row:
                vals.append(row[key])
        if len(vals) >= 2:
            mean_proj = sum(vals) / len(vals)
            err = mean_proj - row["actual"]
            mean_errors.append(err)
            source_errors["equal_mean"].append(err)

    # Median
    median_errors = []
    for row in pairs:
        vals = []
        for src in PROJECTION_SOURCES:
            key = f"ros_{src}"
            if key in row:
                vals.append(row[key])
        if len(vals) >= 2:
            med_proj = float(np.median(vals))
            err = med_proj - row["actual"]
            median_errors.append(err)
            source_errors["median"].append(err)

    print("\n--- Source accuracy (ROS ppg vs actual PPR points, 2026 weeks 2-6) ---")
    print(f"{'Source':<16} {'N':>5} {'MAE':>6} {'RMSE':>6} {'Bias':>7} {'MAE 95% CI':>18}")

    summary = {}
    for label in list(PROJECTION_SOURCES) + ["espn_weekly", "equal_mean", "median"]:
        errs = np.array(source_errors[label])
        n = len(errs)
        if n == 0:
            continue
        m = float(mae(errs))
        r = float(rmse(errs))
        bias = float(np.mean(errs))
        lo, hi = bootstrap_ci(errs, lambda e: float(np.mean(np.abs(e))))
        print(f"{label:<16} {n:>5} {m:>6.2f} {r:>6.2f} {bias:>+7.2f}   [{lo:.2f}, {hi:.2f}]")
        summary[label] = {
            "n": n, "mae": round(m, 3), "rmse": round(r, 3),
            "bias": round(bias, 3), "mae_ci_lo": round(lo, 3), "mae_ci_hi": round(hi, 3),
        }

    # By position
    print("\n--- By position (equal-weight mean) ---")
    for pos in POSITIONS:
        errs = []
        for row in pairs:
            if row["position"] != pos:
                continue
            vals = []
            for src in PROJECTION_SOURCES:
                key = f"ros_{src}"
                if key in row:
                    vals.append(row[key])
            if len(vals) >= 2:
                mean_proj = sum(vals) / len(vals)
                errs.append(mean_proj - row["actual"])
        errs = np.array(errs)
        if len(errs) > 0:
            print(f"  {pos}: n={len(errs)}, MAE={mae(errs):.2f}, RMSE={rmse(errs):.2f}, bias={np.mean(errs):+.2f}")
            summary[f"equal_mean_{pos}"] = {
                "n": len(errs), "mae": round(float(mae(errs)), 3),
                "rmse": round(float(rmse(errs)), 3),
                "bias": round(float(np.mean(errs)), 3),
            }

    # By week
    print("\n--- By week (equal-weight mean MAE) ---")
    for week in WEEKS:
        errs = []
        for row in pairs:
            if row["week"] != week:
                continue
            vals = []
            for src in PROJECTION_SOURCES:
                key = f"ros_{src}"
                if key in row:
                    vals.append(row[key])
            if len(vals) >= 2:
                mean_proj = sum(vals) / len(vals)
                errs.append(mean_proj - row["actual"])
        errs = np.array(errs)
        if len(errs) > 0:
            print(f"  Week {week}: n={len(errs)}, MAE={mae(errs):.2f}")

    # Inverse-error weighting (leave-one-week-out)
    # For each week, compute weights from the OTHER weeks' errors,
    # then score on this week
    print("\n--- Inverse-error weighting (leave-one-week-out) ---")
    inv_errors = []
    for test_week in WEEKS:
        # Train: all other weeks
        train_mae = {}
        for src in PROJECTION_SOURCES:
            train_errs = []
            for row in pairs:
                if row["week"] == test_week:
                    continue
                key = f"ros_{src}"
                if key in row:
                    train_errs.append(abs(row[key] - row["actual"]))
            if len(train_errs) > 0:
                train_mae[src] = max(sum(train_errs) / len(train_errs), 0.01)
        if len(train_mae) < 2:
            continue
        # Inverse-MAE weights
        inv_sum = sum(1.0 / v for v in train_mae.values())
        weights = {s: (1.0 / v) / inv_sum for s, v in train_mae.items()}

        for row in pairs:
            if row["week"] != test_week:
                continue
            vals = {}
            for src in PROJECTION_SOURCES:
                key = f"ros_{src}"
                if key in row:
                    vals[src] = row[key]
            if len(vals) < 2:
                continue
            # Weighted mean (renormalize to available sources)
            w_sum = sum(weights.get(s, 0) for s in vals)
            if w_sum <= 0:
                continue
            weighted = sum(vals[s] * weights.get(s, 0) for s in vals) / w_sum
            inv_errors.append(weighted - row["actual"])

    inv_errors = np.array(inv_errors)
    if len(inv_errors) > 0:
        print(f"  Inverse-MAE weighted: n={len(inv_errors)}, MAE={mae(inv_errors):.2f}, "
              f"RMSE={rmse(inv_errors):.2f}, bias={np.mean(inv_errors):+.2f}")
        lo, hi = bootstrap_ci(inv_errors, lambda e: float(np.mean(np.abs(e))))
        print(f"  MAE 95% CI: [{lo:.2f}, {hi:.2f}]")
        summary["inverse_mae_weighted"] = {
            "n": len(inv_errors), "mae": round(float(mae(inv_errors)), 3),
            "rmse": round(float(rmse(inv_errors)), 3),
            "bias": round(float(np.mean(inv_errors)), 3),
            "mae_ci_lo": round(lo, 3), "mae_ci_hi": round(hi, 3),
        }

    # Compare equal mean MAE vs inverse-error MAE
    eq_mae = summary.get("equal_mean", {}).get("mae", float("nan"))
    inv_mae_val = summary.get("inverse_mae_weighted", {}).get("mae", float("nan"))
    print(f"\n  Equal mean MAE: {eq_mae:.3f}")
    print(f"  Inverse-MAE MAE: {inv_mae_val:.3f}")
    if not (math.isnan(eq_mae) or math.isnan(inv_mae_val)):
        diff = inv_mae_val - eq_mae
        print(f"  Difference: {diff:+.3f} ({'inverse better' if diff < 0 else 'equal mean better or tie'})")

    # Write outputs
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    output = {
        "scoring": scoring,
        "weeks": WEEKS,
        "total_pairs": len(pairs),
        "sources_available": {
            w: [s for s in PROJECTION_SOURCES if w in ros and s in ros[w]]
            for w in WEEKS
        },
        "summary": summary,
        "note": "ROS projections vs single-game actuals. ROS ppg is a proxy for "
                "week-ahead projection; this overstates the error for sources whose "
                "ROS projection is farther from the weekly projection. 5 weeks of data. "
                "Preliminary.",
    }
    with open(OUT_DIR / "source_accuracy_backtest.json", "w") as f:
        json.dump(output, f, indent=2)

    # Markdown summary
    lines = [
        "# Source accuracy backtest (preliminary)",
        "",
        f"Script: `tools/research/source_accuracy_backtest.py`, run 2026-10-23.",
        f"Scoring: {scoring}. Weeks: {WEEKS}. Total player-weeks: {len(pairs)}.",
        "",
        "## Caveat",
        "",
        "This compares rest-of-season per-game projections against single-week actual",
        "points. ROS projections are not week-ahead projections. The error is inflated",
        "by bye weeks, injuries, and game-to-game variance that week-ahead projections",
        "partially account for. This is a directional check, not a definitive ranking.",
        "",
        "## Per-source accuracy",
        "",
        "| Source | N | MAE | RMSE | Bias | MAE 95% CI |",
        "|---|---|---|---|---|---|",
    ]
    for label in list(PROJECTION_SOURCES) + ["espn_weekly", "equal_mean", "median"]:
        s = summary.get(label)
        if s:
            lines.append(
                f"| {label} | {s['n']} | {s['mae']:.2f} | {s['rmse']:.2f} | "
                f"{s['bias']:+.2f} | [{s.get('mae_ci_lo', '?'):.2f}, {s.get('mae_ci_hi', '?'):.2f}] |"
            )
    inv = summary.get("inverse_mae_weighted")
    if inv:
        lines.append(
            f"| inverse_mae_weighted | {inv['n']} | {inv['mae']:.2f} | {inv['rmse']:.2f} | "
            f"{inv['bias']:+.2f} | [{inv.get('mae_ci_lo', '?'):.2f}, {inv.get('mae_ci_hi', '?'):.2f}] |"
        )
    lines += ["", "## By position (equal-weight mean)", "", "| Pos | N | MAE | RMSE | Bias |", "|---|---|---|---|---|"]
    for pos in POSITIONS:
        s = summary.get(f"equal_mean_{pos}")
        if s:
            lines.append(f"| {pos} | {s['n']} | {s['mae']:.2f} | {s['rmse']:.2f} | {s['bias']:+.2f} |")

    with open(OUT_DIR / "source_accuracy_backtest.md", "w") as f:
        f.write("\n".join(lines) + "\n")

    print(f"\nOutput written to {OUT_DIR / 'source_accuracy_backtest.json'}")
    print(f"Output written to {OUT_DIR / 'source_accuracy_backtest.md'}")


if __name__ == "__main__":
    run()
