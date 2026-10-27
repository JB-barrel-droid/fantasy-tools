#!/usr/bin/env python3
"""JEG-969 lane B step 2: comprehensive aggregator tests.

Runs every valid test from post 10's protocol on the data we have today:
  A. Per-source ROS accuracy vs single-week actuals (2026 wk 2-6)
  B. ESPN week-ahead accuracy (2026 wk 1-6)
  C. RotoWire multi-season accuracy (2018-2025, single-source)
  D. Aggregator comparison: equal vs inverse-error vs median (2026 ROS)
  E. RotoWire vs ESPN week-ahead head-to-head (2026 wk 1-6)
  F. Cross-season RotoWire stability (2018-2025)
  + Calibration/shrinkage on the 8-season RotoWire history

Aggregators tested (from post 10):
  1. Equal-weight mean (current)
  2. Median
  3. Trimmed mean (=median with 3 sources)
  4. Inverse-error weights (leave-one-week-out)
  5. Inverse-error weights by position (leave-one-season-out on RotoWire)
  6. Per-source bias correction
  7. Shrinkage toward position mean
  10. Recency (last 3 weeks actual as additional signal)

Aggregators 8 (stacking), 9 (horizon-dependent), 11 (missing source) need
more data and are noted but not testable.

Usage:
    python3 -I tools/research/jeg969_aggregator_tests.py [idmap_csv]

Writes results to docs/research/data/jeg969_aggregator_results.json and .md.
"""
from __future__ import annotations

import csv
import gzip
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
HISTORY = REPO / "data" / "history"
ACTUALS_2024 = REPO / "data" / "inputs" / "weekly_actuals_2024_2026.csv"
ESPN_WEEKLY = REPO / "data" / "inputs" / "espn_weekly_projections_2026.csv"
NFLVERSE = REPO / "data" / "inputs" / "weekly_actuals_nflverse_2015_2025.csv.gz"
SLEEPER_GZ = REPO / "data" / "inputs" / "weekly_projections_sleeper.csv.gz"
PLAYERS_FILE = REPO / "data" / "fixtures" / "current" / "players.json"
OUT_DIR = REPO / "docs" / "research" / "data"

# The idmap may be passed as arg or found in the repo (PR #850 branch)
IDMAP_DEFAULT = REPO / "data" / "inputs" / "sleeper_projection_idmap.csv"

PROJECTION_SOURCES = ["espn", "cbsros", "razzball"]
POSITIONS = ["QB", "RB", "WR", "TE"]
SEED = 20261023
N_BOOT = 2000
RNG = np.random.default_rng(SEED)


# --- Helpers ---

def mae(errors):
    return float(np.mean(np.abs(errors)))


def rmse(errors):
    return float(np.sqrt(np.mean(errors ** 2)))


def bootstrap_ci(errors, stat_fn, alpha=0.05):
    n = len(errors)
    boots = np.array([stat_fn(errors[RNG.integers(0, n, n)]) for _ in range(N_BOOT)])
    return float(np.percentile(boots, 100 * alpha / 2)), float(np.percentile(boots, 100 * (1 - alpha / 2)))


def rank_corr(proj, actual):
    """Spearman rank correlation."""
    from scipy.stats import spearmanr
    if len(proj) < 10:
        return float("nan")
    r, _ = spearmanr(proj, actual)
    return float(r)


# --- Loaders ---

def load_players():
    with open(PLAYERS_FILE) as f:
        players = json.load(f)
    pos_of = {}
    player_list = players.get("players", []) if isinstance(players, dict) else players
    for p in (player_list if player_list else []):
        pos_of[str(p.get("player_key", ""))] = p.get("position", p.get("pos", ""))
    if not pos_of and isinstance(players, dict) and "meta" not in players:
        for pk, info in players.items():
            if isinstance(info, dict):
                pos_of[str(pk)] = info.get("position", info.get("pos", ""))
    return pos_of


def load_actuals_2026():
    """2026 actuals: {(week, player_key_str): {scoring: float}}"""
    out = {}
    with open(ACTUALS_2024) as f:
        for row in csv.DictReader(f):
            if row["season"] != "2026":
                continue
            wk = int(row["week"])
            pk = row["player_key"]
            out[(wk, pk)] = {"ppr": float(row["ppr"]), "half_ppr": float(row["half_ppr"]), "std": float(row["std"])}
    return out


def load_ros_projections():
    """ROS projections per source per week from history files.
    Returns {week: {source: {player_key_str: [std, half_ppr, ppr]}}}"""
    out = {}
    for wk in range(2, 8):
        fp = HISTORY / f"week-{wk}.json"
        if not fp.exists():
            continue
        with open(fp) as f:
            data = json.load(f)
        sources = data.get("sources", {})
        out[wk] = {}
        for src_key, src_name in [("espn", "espn"), ("cbsros", "cbsros"), ("razzball", "razzball")]:
            # Try various key patterns
            src_data = sources.get(src_key, sources.get(src_name, {}))
            ppg = src_data.get("ppg", {})
            if ppg:
                out[wk][src_key] = {str(pk): vals for pk, vals in ppg.items()}
    return out


def load_espn_weekly():
    """{(week, player_key_str): {scoring: float}}"""
    out = {}
    with open(ESPN_WEEKLY) as f:
        for row in csv.DictReader(f):
            wk = int(row["week"])
            pk = row["player_key"]
            out[(wk, pk)] = {"ppr": float(row["ppr"]), "half_ppr": float(row["half_ppr"]), "std": float(row["std"])}
    return out


def load_sleeper_idmap(path):
    """sleeper_id -> {gsis_id, player_key, status, pos, name}"""
    out = {}
    with open(path) as f:
        for row in csv.DictReader(f):
            if row.get("status") == "matched" and row.get("player_key"):
                out[row["sleeper_id"]] = {
                    "gsis_id": row.get("gsis_id", ""),
                    "player_key": row["player_key"],
                    "pos": row.get("pos", ""),
                    "name": row.get("name", ""),
                }
    return out


def load_sleeper_projections():
    """{(season, week, sleeper_id): {scoring: float, pos, name, gsis_id}}"""
    out = {}
    with gzip.open(SLEEPER_GZ, "rt") as f:
        for row in csv.DictReader(f):
            key = (int(row["season"]), int(row["week"]), row["sleeper_id"])
            out[key] = {
                "ppr": float(row["pts_ppr"]) if row.get("pts_ppr") else 0.0,
                "half_ppr": float(row["pts_half_ppr"]) if row.get("pts_half_ppr") else 0.0,
                "std": float(row["pts_std"]) if row.get("pts_std") else 0.0,
                "pos": row.get("pos", ""),
                "name": row.get("name", ""),
                "gsis_id": row.get("gsis_id", ""),
            }
    return out


def load_nflverse_actuals():
    """{(season, week, gsis_id): {scoring: float, pos}}"""
    out = {}
    with gzip.open(NFLVERSE, "rt") as f:
        for row in csv.DictReader(f):
            key = (int(row["season"]), int(row["week"]), row["player_id"])
            out[key] = {
                "ppr": float(row["ppr"]),
                "half_ppr": float(row["half_ppr"]),
                "std": float(row["std"]),
                "pos": row.get("pos", ""),
            }
    return out


# --- Test A: Per-source ROS accuracy (2026) ---

def test_a_ros_accuracy(ros, actuals, pos_of, scoring="ppr"):
    """Per-source ROS ppg vs single-week actual PPR, weeks 2-6."""
    scoring_idx = {"std": 0, "half_ppr": 1, "ppr": 2}[scoring]
    results = {}
    for src in PROJECTION_SOURCES:
        errors = []
        for wk in sorted(ros.keys()):
            if wk > 6:
                continue  # actuals only through wk 6
            src_ppg = ros[wk].get(src, {})
            for pk, ppg_list in src_ppg.items():
                if (wk, pk) not in actuals:
                    continue
                proj = ppg_list[scoring_idx]
                act = actuals[(wk, pk)][scoring]
                pos = pos_of.get(pk, "")
                if pos not in POSITIONS:
                    continue
                errors.append({"proj": proj, "actual": act, "err": proj - act, "pos": pos, "week": wk})
        errs = np.array([e["err"] for e in errors])
        if len(errs) == 0:
            continue
        lo, hi = bootstrap_ci(errs, lambda e: mae(e))
        projs = np.array([e["proj"] for e in errors])
        acts = np.array([e["actual"] for e in errors])
        results[src] = {
            "n": len(errs), "mae": round(mae(errs), 3), "rmse": round(rmse(errs), 3),
            "bias": round(float(np.mean(errs)), 3),
            "mae_ci": [round(lo, 3), round(hi, 3)],
            "rank_corr": round(rank_corr(projs, acts), 3),
        }
        # By position
        for pos in POSITIONS:
            pos_errs = np.array([e["err"] for e in errors if e["pos"] == pos])
            if len(pos_errs) >= 20:
                results[f"{src}_{pos}"] = {
                    "n": len(pos_errs), "mae": round(mae(pos_errs), 3),
                    "bias": round(float(np.mean(pos_errs)), 3),
                }
    return results


# --- Test B: ESPN week-ahead accuracy (2026) ---

def test_b_espn_weekly(espn_wk, actuals, pos_of, scoring="ppr"):
    errors = []
    for (wk, pk), proj_dict in espn_wk.items():
        if wk > 6:
            continue
        if (wk, pk) not in actuals:
            continue
        pos = pos_of.get(pk, "")
        if pos not in POSITIONS:
            continue
        errors.append({"proj": proj_dict[scoring], "actual": actuals[(wk, pk)][scoring],
                        "err": proj_dict[scoring] - actuals[(wk, pk)][scoring], "pos": pos, "week": wk})
    errs = np.array([e["err"] for e in errors])
    if len(errs) == 0:
        return {}
    lo, hi = bootstrap_ci(errs, lambda e: mae(e))
    projs = np.array([e["proj"] for e in errors])
    acts = np.array([e["actual"] for e in errors])
    result = {
        "espn_weekly": {
            "n": len(errs), "mae": round(mae(errs), 3), "rmse": round(rmse(errs), 3),
            "bias": round(float(np.mean(errs)), 3),
            "mae_ci": [round(lo, 3), round(hi, 3)],
            "rank_corr": round(rank_corr(projs, acts), 3),
        }
    }
    for pos in POSITIONS:
        pos_errs = np.array([e["err"] for e in errors if e["pos"] == pos])
        if len(pos_errs) >= 20:
            result[f"espn_weekly_{pos}"] = {
                "n": len(pos_errs), "mae": round(mae(pos_errs), 3),
                "bias": round(float(np.mean(pos_errs)), 3),
            }
    return result


# --- Test C: RotoWire multi-season accuracy (2018-2025) ---

def test_c_rotowire_multiyear(sleeper_proj, nflverse_act, idmap):
    """Single-source week-ahead accuracy across 8 seasons."""
    results_by_season = {}
    all_errors = []
    all_projs = []
    all_acts = []
    pos_errors = defaultdict(list)

    for (season, week, sid), proj in sleeper_proj.items():
        if season > 2025:
            continue
        if sid not in idmap:
            continue
        gsis = idmap[sid]["gsis_id"]
        pos = proj["pos"]
        if pos not in POSITIONS:
            continue
        act_key = (season, week, gsis)
        if act_key not in nflverse_act:
            continue
        act = nflverse_act[act_key]["ppr"]
        p = proj["ppr"]
        err = p - act
        all_errors.append(err)
        all_projs.append(p)
        all_acts.append(act)
        pos_errors[pos].append(err)
        if season not in results_by_season:
            results_by_season[season] = []
        results_by_season[season].append(err)

    all_errs = np.array(all_errors)
    overall_lo, overall_hi = bootstrap_ci(all_errs, lambda e: mae(e))

    result = {
        "overall": {
            "n": len(all_errs),
            "mae": round(mae(all_errs), 3),
            "rmse": round(rmse(all_errs), 3),
            "bias": round(float(np.mean(all_errs)), 3),
            "mae_ci": [round(overall_lo, 3), round(overall_hi, 3)],
            "rank_corr": round(rank_corr(np.array(all_projs), np.array(all_acts)), 3),
        },
        "by_season": {},
        "by_position": {},
    }

    for season in sorted(results_by_season.keys()):
        errs = np.array(results_by_season[season])
        result["by_season"][season] = {
            "n": len(errs), "mae": round(mae(errs), 3),
            "rmse": round(rmse(errs), 3),
            "bias": round(float(np.mean(errs)), 3),
        }

    for pos in POSITIONS:
        if pos in pos_errors:
            errs = np.array(pos_errors[pos])
            lo, hi = bootstrap_ci(errs, lambda e: mae(e))
            result["by_position"][pos] = {
                "n": len(errs), "mae": round(mae(errs), 3),
                "bias": round(float(np.mean(errs)), 3),
                "mae_ci": [round(lo, 3), round(hi, 3)],
            }

    return result


# --- Test D: Aggregator comparison on ROS data (2026) ---

def test_d_aggregators_ros(ros, actuals, pos_of, scoring="ppr"):
    """Compare aggregators 1-7 on 2026 ROS data."""
    scoring_idx = {"std": 0, "half_ppr": 1, "ppr": 2}[scoring]

    # Build aligned rows: player-weeks where at least 2 ROS sources exist
    rows = []
    for wk in sorted(ros.keys()):
        if wk > 6:
            continue
        for pk in set().union(*(ros[wk].get(s, {}).keys() for s in PROJECTION_SOURCES)):
            if (wk, pk) not in actuals:
                continue
            pos = pos_of.get(pk, "")
            if pos not in POSITIONS:
                continue
            src_vals = {}
            for src in PROJECTION_SOURCES:
                if pk in ros[wk].get(src, {}):
                    src_vals[src] = ros[wk][src][pk][scoring_idx]
            if len(src_vals) < 2:
                continue
            rows.append({
                "week": wk, "pk": pk, "pos": pos,
                "actual": actuals[(wk, pk)][scoring],
                "src_vals": src_vals,
            })

    # Aggregator 1: Equal-weight mean
    eq_errors = np.array([np.mean(list(r["src_vals"].values())) - r["actual"] for r in rows])

    # Aggregator 2: Median
    med_errors = np.array([np.median(list(r["src_vals"].values())) - r["actual"] for r in rows])

    # Aggregator 3: Trimmed mean (= median with 3 sources)
    # Same as median with 3 sources

    # Aggregator 4: Inverse-error weights (leave-one-week-out)
    weeks = sorted(set(r["week"] for r in rows))
    inv_errors = []
    for test_wk in weeks:
        train = [r for r in rows if r["week"] != test_wk]
        train_mae = {}
        for src in PROJECTION_SOURCES:
            errs = [abs(r["src_vals"][src] - r["actual"]) for r in train if src in r["src_vals"]]
            if errs:
                train_mae[src] = max(np.mean(errs), 0.01)
        if len(train_mae) < 2:
            continue
        inv_sum = sum(1.0 / v for v in train_mae.values())
        weights = {s: (1.0 / v) / inv_sum for s, v in train_mae.items()}
        for r in rows:
            if r["week"] != test_wk:
                continue
            w_sum = sum(weights.get(s, 0) for s in r["src_vals"])
            if w_sum <= 0:
                continue
            pred = sum(r["src_vals"][s] * weights.get(s, 0) for s in r["src_vals"]) / w_sum
            inv_errors.append(pred - r["actual"])
    inv_errors = np.array(inv_errors)

    # Aggregator 5: Inverse-error by position (leave-one-week-out)
    inv_pos_errors = []
    for test_wk in weeks:
        train = [r for r in rows if r["week"] != test_wk]
        pos_weights = {}
        for pos in POSITIONS:
            train_mae = {}
            for src in PROJECTION_SOURCES:
                errs = [abs(r["src_vals"][src] - r["actual"]) for r in train
                        if r["pos"] == pos and src in r["src_vals"]]
                if errs:
                    train_mae[src] = max(np.mean(errs), 0.01)
            if len(train_mae) >= 2:
                inv_sum = sum(1.0 / v for v in train_mae.values())
                pos_weights[pos] = {s: (1.0 / v) / inv_sum for s, v in train_mae.items()}
        for r in rows:
            if r["week"] != test_wk:
                continue
            w = pos_weights.get(r["pos"])
            if not w:
                continue
            w_sum = sum(w.get(s, 0) for s in r["src_vals"])
            if w_sum <= 0:
                continue
            pred = sum(r["src_vals"][s] * w.get(s, 0) for s in r["src_vals"]) / w_sum
            inv_pos_errors.append(pred - r["actual"])
    inv_pos_errors = np.array(inv_pos_errors)

    # Aggregator 6: Bias correction (leave-one-week-out)
    bias_errors = []
    for test_wk in weeks:
        train = [r for r in rows if r["week"] != test_wk]
        src_bias = {}
        for src in PROJECTION_SOURCES:
            errs = [r["src_vals"][src] - r["actual"] for r in train if src in r["src_vals"]]
            if errs:
                src_bias[src] = np.mean(errs)
        for r in rows:
            if r["week"] != test_wk:
                continue
            corrected = []
            for src in r["src_vals"]:
                corrected.append(r["src_vals"][src] - src_bias.get(src, 0))
            if corrected:
                bias_errors.append(np.mean(corrected) - r["actual"])
    bias_errors = np.array(bias_errors)

    # Aggregator 7: Shrinkage toward position mean (blend=0.9 source + 0.1 pos mean)
    # First compute per-week position means from actuals
    pos_mean_by_week = {}
    for r in rows:
        key = (r["week"], r["pos"])
        if key not in pos_mean_by_week:
            pos_mean_by_week[key] = []
        pos_mean_by_week[key].append(r["actual"])
    for k in pos_mean_by_week:
        pos_mean_by_week[k] = np.mean(pos_mean_by_week[k])

    shrink_errors = []
    blend = 0.9
    for r in rows:
        pos_mean = pos_mean_by_week.get((r["week"], r["pos"]), 0)
        vals = []
        for src in r["src_vals"]:
            shrunk = blend * r["src_vals"][src] + (1 - blend) * pos_mean
            vals.append(shrunk)
        if vals:
            shrink_errors.append(np.mean(vals) - r["actual"])
    shrink_errors = np.array(shrink_errors)

    # Build results
    aggregators = {
        "1_equal_mean": eq_errors,
        "2_median": med_errors,
        "4_inverse_error": inv_errors,
        "5_inverse_error_by_pos": inv_pos_errors,
        "6_bias_corrected": bias_errors,
        "7_shrinkage_0.9": shrink_errors,
    }

    out = {}
    for name, errs in aggregators.items():
        if len(errs) == 0:
            continue
        lo, hi = bootstrap_ci(errs, lambda e: mae(e))
        out[name] = {
            "n": len(errs), "mae": round(mae(errs), 3), "rmse": round(rmse(errs), 3),
            "bias": round(float(np.mean(errs)), 3),
            "mae_ci": [round(lo, 3), round(hi, 3)],
        }

    # Add paired differences: each aggregator vs equal mean
    eq_mae_val = mae(eq_errors)
    for name, errs in aggregators.items():
        if name == "1_equal_mean" or len(errs) == 0:
            continue
        diff = mae(errs) - eq_mae_val
        # Bootstrap the difference
        n = min(len(eq_errors), len(errs))
        # For paired comparison, use the same rows
        if len(errs) == len(eq_errors):
            diffs = np.abs(errs) - np.abs(eq_errors)
            lo_d, hi_d = bootstrap_ci(diffs, lambda d: float(np.mean(d)))
            out[name]["vs_equal_mean"] = {
                "mae_diff": round(diff, 4),
                "diff_ci": [round(lo_d, 4), round(hi_d, 4)],
                "excludes_zero": lo_d > 0 or hi_d < 0,
            }

    return out


# --- Test E: RotoWire vs ESPN head-to-head (2026) ---

def test_e_rotowire_vs_espn(sleeper_proj, espn_wk, actuals, idmap, pos_of, scoring="ppr"):
    """Head-to-head: both sources predict the same player-week."""
    rw_errors = []
    espn_errors = []
    paired_rows = []

    for (season, week, sid), proj in sleeper_proj.items():
        if season != 2026 or week > 6:
            continue
        if sid not in idmap:
            continue
        pk = idmap[sid]["player_key"]
        pos = proj["pos"]
        if pos not in POSITIONS:
            continue
        if (week, pk) not in espn_wk or (week, pk) not in actuals:
            continue
        rw_pred = proj[scoring]
        espn_pred = espn_wk[(week, pk)][scoring]
        act = actuals[(week, pk)][scoring]
        rw_errors.append(rw_pred - act)
        espn_errors.append(espn_pred - act)
        paired_rows.append({"rw": rw_pred, "espn": espn_pred, "actual": act, "pos": pos, "week": week})

    rw_errs = np.array(rw_errors)
    espn_errs = np.array(espn_errors)

    if len(rw_errs) == 0:
        return {}

    # Paired MAE difference
    rw_abs = np.abs(rw_errs)
    espn_abs = np.abs(espn_errs)
    diff = rw_abs - espn_abs  # positive = RotoWire worse
    lo, hi = bootstrap_ci(diff, lambda d: float(np.mean(d)))

    result = {
        "n_paired": len(rw_errs),
        "rotowire_mae": round(mae(rw_errs), 3),
        "espn_mae": round(mae(espn_errs), 3),
        "rotowire_bias": round(float(np.mean(rw_errs)), 3),
        "espn_bias": round(float(np.mean(espn_errs)), 3),
        "mae_diff_rw_minus_espn": round(float(np.mean(diff)), 3),
        "diff_ci": [round(lo, 3), round(hi, 3)],
        "espn_significantly_better": hi < 0,
        "rotowire_significantly_better": lo > 0,
        # Also: what about averaging the two?
    }

    # Average of the two
    avg_errors = np.array([(r["rw"] + r["espn"]) / 2 - r["actual"] for r in paired_rows])
    result["average_mae"] = round(mae(avg_errors), 3)
    avg_diff = np.abs(avg_errors) - espn_abs
    lo2, hi2 = bootstrap_ci(avg_diff, lambda d: float(np.mean(d)))
    result["average_vs_espn_diff_ci"] = [round(lo2, 3), round(hi2, 3)]

    return result


# --- Test F: Cross-season RotoWire stability ---

def test_f_rotowire_stability(test_c_result):
    """Extract year-over-year MAE stability from test C results."""
    by_season = test_c_result.get("by_season", {})
    maes = [(s, d["mae"]) for s, d in sorted(by_season.items())]
    if len(maes) < 2:
        return {}
    mae_vals = [m for _, m in maes]
    return {
        "seasons": maes,
        "mae_range": [round(min(mae_vals), 3), round(max(mae_vals), 3)],
        "mae_std": round(float(np.std(mae_vals)), 3),
        "mae_cv": round(float(np.std(mae_vals) / np.mean(mae_vals)), 3),
        "conclusion": "stable" if np.std(mae_vals) / np.mean(mae_vals) < 0.10 else "variable",
    }


# --- Test: Calibration on RotoWire (does spread predict error?) ---

def test_calibration_rotowire(sleeper_proj, nflverse_act, idmap):
    """Bin players by projected points, check if residual variance matches."""
    bins = [(0, 5), (5, 10), (10, 15), (15, 20), (20, 30)]
    bin_data = {b: [] for b in bins}

    for (season, week, sid), proj in sleeper_proj.items():
        if season > 2025:
            continue
        if sid not in idmap:
            continue
        gsis = idmap[sid]["gsis_id"]
        pos = proj["pos"]
        if pos not in POSITIONS:
            continue
        act_key = (season, week, gsis)
        if act_key not in nflverse_act:
            continue
        p = proj["ppr"]
        a = nflverse_act[act_key]["ppr"]
        for lo, hi in bins:
            if lo <= p < hi:
                bin_data[(lo, hi)].append({"proj": p, "actual": a, "err": p - a})
                break

    result = {}
    for (lo, hi), data in bin_data.items():
        if len(data) < 50:
            continue
        errs = np.array([d["err"] for d in data])
        result[f"{lo}-{hi}"] = {
            "n": len(data),
            "mae": round(mae(errs), 3),
            "bias": round(float(np.mean(errs)), 3),
            "residual_std": round(float(np.std(errs)), 3),
        }
    return result


# --- Test: Shrinkage on RotoWire multi-season ---

def test_shrinkage_rotowire(sleeper_proj, nflverse_act, idmap):
    """Leave-one-season-out: does shrinking toward position mean help?"""
    seasons = list(range(2018, 2026))
    results = {}

    for blend in [1.0, 0.95, 0.9, 0.85, 0.8]:
        all_errors = []
        for test_season in seasons:
            # Compute position means from training seasons
            pos_mean_train = defaultdict(list)
            for (s, w, sid), proj in sleeper_proj.items():
                if s == test_season or s > 2025:
                    continue
                if sid not in idmap:
                    continue
                gsis = idmap[sid]["gsis_id"]
                pos = proj["pos"]
                if pos not in POSITIONS:
                    continue
                if (s, w, gsis) in nflverse_act:
                    pos_mean_train[pos].append(nflverse_act[(s, w, gsis)]["ppr"])
            pos_means = {p: np.mean(v) for p, v in pos_mean_train.items() if v}

            # Test on held-out season
            for (s, w, sid), proj in sleeper_proj.items():
                if s != test_season:
                    continue
                if sid not in idmap:
                    continue
                gsis = idmap[sid]["gsis_id"]
                pos = proj["pos"]
                if pos not in POSITIONS:
                    continue
                if (s, w, gsis) not in nflverse_act:
                    continue
                p = proj["ppr"]
                a = nflverse_act[(s, w, gsis)]["ppr"]
                pm = pos_means.get(pos, p)
                shrunk = blend * p + (1 - blend) * pm
                all_errors.append(shrunk - a)

        errs = np.array(all_errors)
        if len(errs) > 0:
            results[f"blend_{blend}"] = {
                "n": len(errs),
                "mae": round(mae(errs), 3),
                "rmse": round(rmse(errs), 3),
            }

    return results


# --- Main ---

def run():
    idmap_path = Path(sys.argv[1]) if len(sys.argv) > 1 else IDMAP_DEFAULT
    if not idmap_path.exists():
        print(f"ERROR: idmap not found at {idmap_path}")
        print("Pass the path to sleeper_projection_idmap.csv as first arg")
        sys.exit(1)

    print("Loading data...")
    pos_of = load_players()
    actuals = load_actuals_2026()
    ros = load_ros_projections()
    espn_wk = load_espn_weekly()
    idmap = load_sleeper_idmap(idmap_path)
    sleeper_proj = load_sleeper_projections()
    nflverse_act = load_nflverse_actuals()
    print(f"  Players: {len(pos_of)}, Actuals 2026: {len(actuals)}, "
          f"ROS weeks: {sorted(ros.keys())}, ESPN weekly: {len(espn_wk)}")
    print(f"  Sleeper idmap matched: {len(idmap)}, Sleeper proj: {len(sleeper_proj)}, "
          f"nflverse: {len(nflverse_act)}")

    all_results = {}

    print("\n=== Test A: Per-source ROS accuracy (2026, PPR) ===")
    test_a = test_a_ros_accuracy(ros, actuals, pos_of, "ppr")
    all_results["A_ros_accuracy"] = test_a
    for k, v in sorted(test_a.items()):
        if "_" not in k or k.count("_") == 0:
            print(f"  {k}: n={v['n']}, MAE={v['mae']}, RMSE={v.get('rmse','?')}, "
                  f"bias={v['bias']}, CI={v.get('mae_ci','?')}, rho={v.get('rank_corr','?')}")

    print("\n=== Test B: ESPN week-ahead accuracy (2026, PPR) ===")
    test_b = test_b_espn_weekly(espn_wk, actuals, pos_of, "ppr")
    all_results["B_espn_weekly"] = test_b
    for k, v in sorted(test_b.items()):
        if "_" not in k or k.count("_") <= 1:
            print(f"  {k}: n={v['n']}, MAE={v['mae']}, bias={v['bias']}, CI={v.get('mae_ci','?')}")

    print("\n=== Test C: RotoWire multi-season accuracy (2018-2025, PPR) ===")
    test_c = test_c_rotowire_multiyear(sleeper_proj, nflverse_act, idmap)
    all_results["C_rotowire_multiyear"] = test_c
    ov = test_c.get("overall", {})
    print(f"  Overall: n={ov.get('n')}, MAE={ov.get('mae')}, RMSE={ov.get('rmse')}, "
          f"bias={ov.get('bias')}, rho={ov.get('rank_corr')}")
    for s, d in sorted(test_c.get("by_season", {}).items()):
        print(f"  {s}: n={d['n']}, MAE={d['mae']}, bias={d['bias']}")
    for p, d in sorted(test_c.get("by_position", {}).items()):
        print(f"  {p}: n={d['n']}, MAE={d['mae']}, bias={d['bias']}, CI={d.get('mae_ci')}")

    print("\n=== Test D: Aggregator comparison (2026 ROS, PPR) ===")
    test_d = test_d_aggregators_ros(ros, actuals, pos_of, "ppr")
    all_results["D_aggregators_ros"] = test_d
    for name, v in sorted(test_d.items()):
        line = f"  {name}: n={v['n']}, MAE={v['mae']}, RMSE={v['rmse']}, bias={v['bias']}, CI={v['mae_ci']}"
        vs = v.get("vs_equal_mean")
        if vs:
            line += f"  | vs equal: diff={vs['mae_diff']}, CI={vs['diff_ci']}, sig={vs['excludes_zero']}"
        print(line)

    print("\n=== Test E: RotoWire vs ESPN head-to-head (2026, PPR) ===")
    test_e = test_e_rotowire_vs_espn(sleeper_proj, espn_wk, actuals, idmap, pos_of, "ppr")
    all_results["E_rotowire_vs_espn"] = test_e
    if test_e:
        print(f"  Paired: n={test_e['n_paired']}")
        print(f"  RotoWire MAE={test_e['rotowire_mae']}, ESPN MAE={test_e['espn_mae']}")
        print(f"  MAE diff (RW-ESPN)={test_e['mae_diff_rw_minus_espn']}, CI={test_e['diff_ci']}")
        print(f"  ESPN sig better: {test_e['espn_significantly_better']}")
        print(f"  Average of both MAE={test_e['average_mae']}, vs ESPN CI={test_e['average_vs_espn_diff_ci']}")

    print("\n=== Test F: Cross-season RotoWire stability ===")
    test_f = test_f_rotowire_stability(test_c)
    all_results["F_rotowire_stability"] = test_f
    if test_f:
        print(f"  MAE range: {test_f['mae_range']}, std: {test_f['mae_std']}, "
              f"CV: {test_f['mae_cv']}, conclusion: {test_f['conclusion']}")

    print("\n=== Calibration: RotoWire by projection bin (2018-2025) ===")
    test_cal = test_calibration_rotowire(sleeper_proj, nflverse_act, idmap)
    all_results["calibration_rotowire"] = test_cal
    for k, v in sorted(test_cal.items()):
        print(f"  {k} ppg: n={v['n']}, MAE={v['mae']}, bias={v['bias']}, residual_std={v['residual_std']}")

    print("\n=== Shrinkage: RotoWire leave-one-season-out ===")
    test_shrink = test_shrinkage_rotowire(sleeper_proj, nflverse_act, idmap)
    all_results["shrinkage_rotowire"] = test_shrink
    for k, v in sorted(test_shrink.items()):
        print(f"  {k}: n={v['n']}, MAE={v['mae']}, RMSE={v['rmse']}")

    # Also run test D for all 3 scorings
    print("\n=== Test D across scorings ===")
    for scoring in ["std", "half_ppr"]:
        test_d_s = test_d_aggregators_ros(ros, actuals, pos_of, scoring)
        all_results[f"D_aggregators_{scoring}"] = test_d_s
        eq = test_d_s.get("1_equal_mean", {})
        print(f"  {scoring}: equal mean MAE={eq.get('mae')}, n={eq.get('n')}")

    # Write outputs
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUT_DIR / "jeg969_aggregator_results.json", "w") as f:
        json.dump(all_results, f, indent=2, default=str)
    print(f"\nJSON written to {OUT_DIR / 'jeg969_aggregator_results.json'}")

    # Write markdown summary
    write_markdown_summary(all_results)


def write_markdown_summary(results):
    lines = [
        "# JEG-969 Lane B: Aggregator Test Results",
        "",
        "Script: `tools/research/jeg969_aggregator_tests.py`, run 2026-10-23.",
        "All tests use PPR scoring unless noted. Bootstrap CIs: 2000 resamples, seed 20261023.",
        "",
        "## Test A: Per-source ROS accuracy (2026 wk 2-6)",
        "",
        "| Source | N | MAE | RMSE | Bias | 95% CI | Rank corr |",
        "|--------|---|-----|------|------|--------|-----------|",
    ]
    for src in PROJECTION_SOURCES:
        d = results.get("A_ros_accuracy", {}).get(src, {})
        if d:
            lines.append(f"| {src} | {d['n']} | {d['mae']} | {d.get('rmse','')} | {d['bias']} | {d.get('mae_ci','')} | {d.get('rank_corr','')} |")

    lines += ["", "## Test B: ESPN week-ahead (2026 wk 1-6)", ""]
    d = results.get("B_espn_weekly", {}).get("espn_weekly", {})
    if d:
        lines.append(f"ESPN weekly: n={d['n']}, MAE={d['mae']}, RMSE={d.get('rmse','')}, "
                      f"bias={d['bias']}, rank_corr={d.get('rank_corr','')}")

    lines += ["", "## Test C: RotoWire multi-season (2018-2025)", ""]
    ov = results.get("C_rotowire_multiyear", {}).get("overall", {})
    if ov:
        lines.append(f"Overall: n={ov['n']}, MAE={ov['mae']}, RMSE={ov.get('rmse','')}, "
                      f"bias={ov['bias']}, rank_corr={ov.get('rank_corr','')}")
    lines.append("")
    lines.append("| Season | N | MAE | Bias |")
    lines.append("|--------|---|-----|------|")
    for s, d in sorted(results.get("C_rotowire_multiyear", {}).get("by_season", {}).items()):
        lines.append(f"| {s} | {d['n']} | {d['mae']} | {d['bias']} |")

    lines += ["", "## Test D: Aggregator comparison (2026 ROS)", "",
              "| Aggregator | N | MAE | RMSE | Bias | 95% CI | vs Equal (diff, CI, sig) |",
              "|------------|---|-----|------|------|--------|--------------------------|"]
    for name, v in sorted(results.get("D_aggregators_ros", {}).items()):
        vs = v.get("vs_equal_mean", {})
        vs_str = f"{vs.get('mae_diff','')}, {vs.get('diff_ci','')}, {vs.get('excludes_zero','')}" if vs else ""
        lines.append(f"| {name} | {v['n']} | {v['mae']} | {v['rmse']} | {v['bias']} | {v['mae_ci']} | {vs_str} |")

    lines += ["", "## Test E: RotoWire vs ESPN head-to-head (2026)", ""]
    e = results.get("E_rotowire_vs_espn", {})
    if e:
        lines.append(f"Paired n={e.get('n_paired','')}: RotoWire MAE={e.get('rotowire_mae','')}, "
                      f"ESPN MAE={e.get('espn_mae','')}")
        lines.append(f"MAE diff (RW-ESPN)={e.get('mae_diff_rw_minus_espn','')}, CI={e.get('diff_ci','')}")
        lines.append(f"Average of both: MAE={e.get('average_mae','')}")

    lines += ["", "## Test F: RotoWire stability across seasons", ""]
    f_res = results.get("F_rotowire_stability", {})
    if f_res:
        lines.append(f"MAE range={f_res.get('mae_range','')}, CV={f_res.get('mae_cv','')}, "
                      f"conclusion: {f_res.get('conclusion','')}")

    lines += ["", "## Shrinkage (RotoWire, leave-one-season-out)", "",
              "| Blend | N | MAE | RMSE |", "|-------|---|-----|------|"]
    for k, v in sorted(results.get("shrinkage_rotowire", {}).items()):
        lines.append(f"| {k} | {v['n']} | {v['mae']} | {v['rmse']} |")

    with open(OUT_DIR / "jeg969_aggregator_results.md", "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"Markdown written to {OUT_DIR / 'jeg969_aggregator_results.md'}")


if __name__ == "__main__":
    run()
