#!/usr/bin/env python3
"""Research post 7 (JEG-882): does the market gap predict anything?

One command, no network, standard library plus numpy:

    python3 tools/research/gap_backtest.py

Writes every figure the post quotes to docs/research/data/jeg1411-mean/:
    gap_backtest.json   every number, keyed by test
    gap_backtest.csv    one row per player-week-setting with the signal and outcomes
    gap_backtest.md     the tables as the post shows them

What it does
------------
1. Prices every saved content week (data/history/week-N.json, N = 2..7) with the
   Python value reference (pipelines/value_reference.py, the engine's reference
   implementation) at the reader's league settings. Each week runs on its own
   saved sources (every source with that week saved is included; no holds),
   with the current players.json as the player universe. The latest saved week
   is compared with the checkout fixture as a diagnostic, not a live check.
2. Studies the Trade targets signal with Jeremy's approved research mean
   (marketConsensus, rankEquivalents, buildTargets): Trade chart average = mean of the
   indexed charts that price the player (a finite 0 counts, null does not),
   gap = consensus - ours, eligible with 2+ charts, consensus > 0 and a strict
   majority of charts on the consensus side; Sell needs ours >= SELL_FLOOR (5);
   Buy needs the position rank-equivalent gap <= -BUY_RANK_MARGIN (2); a player
   ESPN zeroes or whose chart value is estimated is never listed.
3. Tests, pooled over week pairs and per week:
   (a) next-week and two-week change in the consensus price and in our value
       against the gap (Spearman rank correlation, quintile buckets, Buy and
       Sell hit rates with a cluster bootstrap by player);
   (b) persistence of the gap and of the lists;
   (c) realised PPR points (data/inputs/weekly_actuals_2024_2026.csv) against
       the ESPN per-game projection saved in the week's snapshot.
   Controls: a placebo signal (the consensus price's own change from the week
   before, i.e. plain regression to the mean), a rank regression of the
   outcome on gap and placebo together, and within-position correlations.

Our value is reported as DDF Value and DDF Value (projections). Saved 2026
inputs are modeled with the checked-out reference engine; this is not a live
site reproduction. Only this research signal changes from median to mean.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
import subprocess
import sys
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "pipelines"))
sys.path.insert(0, str(REPO))
import value_reference as ref  # noqa: E402

HISTORY = REPO / "data" / "history"
ACTUALS = REPO / "data" / "inputs" / "weekly_actuals_2024_2026.csv"
OUT_DIR = REPO / "docs" / "research" / "data" / "jeg1411-mean"
SEASON = 2026
WEEKS = [2, 3, 4, 5, 6, 7]

# app/v2/targets.js constants (cite: targets.js lines 36, 53, 62).
CHART_KEYS = ["usatoday", "fantasycalc", "fantasypros", "cbs"]
SELL_FLOOR = 5.0
BUY_RANK_MARGIN = 2.0
MIN_CHARTS = 2

OURS = {"blend": "blended", "proj": "projections"}   # ddf_value, ddf_value_projections
DEFAULT = {"scoring": "ppr", "teams": 12}
ALL_SETTINGS = [{"scoring": s, "teams": t} for s in ref.SCORINGS for t in ref.TEAM_COUNTS]
N_BOOT = 1000          # cluster bootstrap draws for the default setting
N_BOOT_SWEEP = 200     # the 11 other settings get a coarser interval
N_PERM = 1000
SEED = 20261022
AGGREGATION = "mean"  # Jeremy, 2026-10-31 (JEG-1411); research post 07 only.


# ---------------------------------------------------------------------------
# 1. Price each saved week with the reference
# ---------------------------------------------------------------------------

def load_week(week: int) -> dict:
    return json.loads((HISTORY / f"week-{week}.json").read_text(encoding="utf-8"))


def price_week(inp, setting: ref.Setting, doc: dict, hidden: set | None = None) -> dict:
    natives = {}
    for key in ref.SOURCES:
        entry = (doc.get("sources") or {}).get(key)
        if entry and entry.get("week") == doc["week"]:
            nat = ref.snapshot_natives(inp, key, entry, setting.scoring)
            if nat:
                natives[key] = nat
    included = list(natives)
    res = ref.run_pipeline(setting.league, setting._sources(natives), setting.pos_of, included,
                           None, lineup=setting.lineup, hidden=hidden or set())
    return {"result": res, "sources": included}


def espn_zero_in_week(doc: dict, scoring: str) -> set:
    """Players the week's ESPN snapshot lists at 0 (the engine's espnProjectsZero flag,
    GAP-025: listed but projected at 0 is 'out')."""
    entry = (doc.get("sources") or {}).get("espn") or {}
    idx = ref.HISTORY_SCORING_INDEX[scoring]
    out = set()
    for key, triple in (entry.get("ppg") or {}).items():
        if isinstance(triple, list) and len(triple) > idx and triple[idx] == 0:
            out.add(int(key))
    return out


# ---------------------------------------------------------------------------
# 2. The research signal (site rules plus the approved mean aggregation)
# ---------------------------------------------------------------------------

def finite(v) -> bool:
    return isinstance(v, (int, float)) and math.isfinite(v)


def market_consensus(ours: float, cells: dict) -> dict:
    """Research-only Trade chart average; median mode reproduces the old signal."""
    priced = [k for k in cells if finite(cells[k])]
    if not priced:
        return {"value": None, "of": 0, "gap": None, "side": None, "eligible": False, "agree": 0}
    values = [cells[k] for k in priced]
    value = statistics.fmean(values) if AGGREGATION == "mean" else ref.median(values)
    gap = value - ours
    side = "sell" if gap > 0 else "buy" if gap < 0 else None
    agree = sum(1 for v in values if (v > ours if side == "sell" else v < ours)) if side else 0
    eligible = bool(side) and len(priced) >= MIN_CHARTS and value > 0 and agree * 2 > len(priced)
    return {"value": value, "of": len(priced), "gap": gap, "side": side, "eligible": eligible,
            "agree": agree}


def build_signal(priced: dict, ours_key: str, charts: list, espn_zero: set) -> dict:
    """{player_key: row} with the gap, side, rankGap and the list membership a
    research signal at that week and setting."""
    res = priced["result"]
    charts = [c for c in charts if c in priced["sources"]]
    players = {}
    for key, r in res["rows"].items():
        ours = r["ddf"][ours_key]["value"]
        if not finite(ours):
            continue   # targets.js: omittedNoOurs
        cells = {c: (r["indexed"].get(c) if finite(r["indexed"].get(c)) else None) for c in charts}
        m = market_consensus(ours, cells)
        est = r.get("estimated") or {}
        flagged = (key in espn_zero) or any(finite(cells[c]) and est.get(c) for c in charts)
        players[key] = {"pos": r["pos"], "ours": ours, "cells": cells, **m, "flagged": flagged,
                        "ours_proj": r["ddf"]["projections"]["value"],
                        "ours_blend": r["ddf"]["blended"]["value"],
                        "rank_gap": None, "market_rank": None, "our_rank": None}
    # rankEquivalents (lines 64-84): per position over players with 2+ charts and a consensus.
    by_pos = defaultdict(list)
    for key, p in players.items():
        if p["of"] >= MIN_CHARTS and finite(p["value"]):
            by_pos[p["pos"]].append(key)
    for pos, keys in by_pos.items():
        ours_desc = sorted((players[k]["ours"] for k in keys), reverse=True)
        by_ours = sorted(keys, key=lambda k: (-players[k]["ours"], k))
        our_rank = {k: i + 1 for i, k in enumerate(by_ours)}
        by_market = sorted(keys, key=lambda k: (-players[k]["value"], k))
        for i, k in enumerate(by_market):
            p = players[k]
            p["market_rank"] = i + 1
            p["our_rank"] = our_rank[k]
            p["rank_gap"] = ours_desc[i] - p["ours"]
    # buildTargets (lines 171-188).
    for p in players.values():
        sell = p["eligible"] and p["side"] == "sell" and p["ours"] >= SELL_FLOOR
        buy = (p["eligible"] and p["side"] == "buy" and finite(p["rank_gap"])
               and p["rank_gap"] <= -BUY_RANK_MARGIN)
        p["list"] = "sell" if sell and not p["flagged"] else "buy" if buy and not p["flagged"] else None
        p["scale_only"] = bool(p["eligible"] and p["side"] == "buy" and not buy)
    return players


# ---------------------------------------------------------------------------
# 3. Statistics (numpy only)
# ---------------------------------------------------------------------------

def rank(a: np.ndarray) -> np.ndarray:
    """Average ranks (ties share the mean rank), 1-based."""
    order = np.argsort(a, kind="mergesort")
    ranks = np.empty(len(a), dtype=float)
    sorted_a = a[order]
    i = 0
    while i < len(a):
        j = i
        while j + 1 < len(a) and sorted_a[j + 1] == sorted_a[i]:
            j += 1
        ranks[order[i:j + 1]] = (i + j) / 2 + 1
        i = j + 1
    return ranks


def spearman(x, y) -> float | None:
    x, y = np.asarray(x, float), np.asarray(y, float)
    if len(x) < 4 or np.std(x) == 0 or np.std(y) == 0:
        return None
    return float(np.corrcoef(rank(x), rank(y))[0, 1])


def spearman_ci(x, y, groups, rng, n_boot=N_BOOT) -> dict:
    """Spearman with a cluster bootstrap by player (groups): resample players
    with replacement, keep every week-row of each drawn player."""
    x, y, groups = np.asarray(x, float), np.asarray(y, float), np.asarray(groups)
    rho = spearman(x, y)
    if rho is None:
        return {"rho": None, "n": int(len(x)), "players": int(len(set(groups.tolist())))}
    uniq = np.unique(groups)
    idx_by = {g: np.flatnonzero(groups == g) for g in uniq}
    boots = []
    for _ in range(n_boot):
        draw = rng.choice(uniq, size=len(uniq), replace=True)
        idx = np.concatenate([idx_by[g] for g in draw])
        r = spearman(x[idx], y[idx])
        if r is not None:
            boots.append(r)
    lo, hi = (float(np.percentile(boots, 2.5)), float(np.percentile(boots, 97.5))) if boots else (None, None)
    out = {"rho": rho, "ci95": [lo, hi], "n": int(len(x)), "players": int(len(uniq))}
    if n_boot >= N_BOOT:
        out["p_two_sided"] = p_perm(x, y, rng)
    return out


def p_perm(x, y, rng, n=N_PERM) -> float:
    """Permutation p-value for Spearman (shuffles y; ignores clustering, so it
    is the optimistic one; the bootstrap CI is the honest interval)."""
    rho = abs(spearman(x, y) or 0)
    rx, ry = rank(np.asarray(x, float)), rank(np.asarray(y, float))
    count = 0
    for _ in range(n):
        if abs(np.corrcoef(rx, rng.permutation(ry))[0, 1]) >= rho:
            count += 1
    return (count + 1) / (n + 1)


def rate_ci(hits, groups, rng, n_boot=N_BOOT) -> dict:
    hits, groups = np.asarray(hits, bool), np.asarray(groups)
    if not len(hits):
        return {"rate": None, "n": 0}
    uniq = np.unique(groups)
    idx_by = {g: np.flatnonzero(groups == g) for g in uniq}
    boots = []
    for _ in range(n_boot):
        draw = rng.choice(uniq, size=len(uniq), replace=True)
        idx = np.concatenate([idx_by[g] for g in draw])
        boots.append(hits[idx].mean())
    return {"rate": float(hits.mean()), "ci95": [float(np.percentile(boots, 2.5)), float(np.percentile(boots, 97.5))],
            "n": int(len(hits)), "players": int(len(uniq))}


def quintiles(x, y, k=5) -> list:
    """Mean and median outcome by signal quintile (1 = most negative signal)."""
    x, y = np.asarray(x, float), np.asarray(y, float)
    if len(x) < k * 2:
        return []
    edges = np.quantile(x, np.linspace(0, 1, k + 1))
    out = []
    for i in range(k):
        lo, hi = edges[i], edges[i + 1]
        mask = (x >= lo) & ((x <= hi) if i == k - 1 else (x < hi))
        if mask.sum() == 0:
            continue
        out.append({"bucket": i + 1, "signal_lo": float(lo), "signal_hi": float(hi), "n": int(mask.sum()),
                    "mean_outcome": float(y[mask].mean()), "median_outcome": float(np.median(y[mask])),
                    "share_positive": float((y[mask] > 0).mean())})
    return out


def rank_regression(y, xs: dict) -> dict:
    """OLS on ranks (all variables rank-transformed to [0,1]): the partial
    association of each predictor with the outcome, holding the others fixed."""
    y = rank(np.asarray(y, float)) / len(y)
    cols = [rank(np.asarray(v, float)) / len(y) for v in xs.values()]
    X = np.column_stack([np.ones(len(y))] + cols)
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    # np.dot, not @: numpy 2.0.2 on this Mac's Accelerate raises spurious divide-by-zero warnings in matmul.
    resid = y - np.dot(X, beta)
    dof = max(len(y) - X.shape[1], 1)
    sigma2 = float(np.dot(resid, resid)) / dof
    cov = sigma2 * np.linalg.pinv(np.dot(X.T, X))
    se = np.sqrt(np.diag(cov))
    out = {}
    for i, name in enumerate(xs):
        b, s = float(beta[i + 1]), float(se[i + 1])
        out[name] = {"beta": b, "se": s, "t": (b / s) if s > 0 else None}
    out["n"] = int(len(y))
    return out


# ---------------------------------------------------------------------------
# 4. Assemble the panel and run the tests
# ---------------------------------------------------------------------------

def load_actuals() -> dict:
    """{(player_key, week): ppr points} for the 2026 season. A player with no
    row that week did not record a line (did not play, or bye): missing, not 0."""
    out = {}
    with ACTUALS.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if int(row["season"]) != SEASON:
                continue
            out[(int(row["player_key"]), int(row["week"]))] = {
                "ppr": float(row["ppr"]), "half_ppr": float(row["half_ppr"]), "standard": float(row["std"])}
    return out


def espn_ppg_in_week(doc: dict, scoring: str) -> dict:
    entry = (doc.get("sources") or {}).get("espn") or {}
    idx = ref.HISTORY_SCORING_INDEX[scoring]
    out = {}
    for key, triple in (entry.get("ppg") or {}).items():
        if isinstance(triple, list) and len(triple) > idx and finite(triple[idx]):
            out[int(key)] = float(triple[idx])
    return out


def build_panel(inp, setting_spec: dict, docs: dict) -> dict:
    """Signals per week for one setting, both definitions of our value."""
    s = ref.Setting(inp, setting_spec["scoring"], setting_spec["teams"], 0)
    weeks = {}
    for w, doc in docs.items():
        priced = price_week(inp, s, doc)
        zero = espn_zero_in_week(doc, s.scoring)
        weeks[w] = {"sources": priced["sources"],
                    "signal": {k: build_signal(priced, v, CHART_KEYS, zero) for k, v in OURS.items()},
                    "espn_ppg": espn_ppg_in_week(doc, s.scoring)}
    return {"setting": setting_spec, "weeks": weeks, "pie": s.league.pie}


def pairs(panel: dict, ours: str, horizon: int) -> list:
    """Player-week rows with the signal at t and the outcomes at t+horizon."""
    rows = []
    weeks = sorted(panel["weeks"])
    for t in weeks:
        if t + horizon not in panel["weeks"]:
            continue
        now = panel["weeks"][t]["signal"][ours]
        later = panel["weeks"][t + horizon]["signal"][ours]
        prev = panel["weeks"].get(t - 1, {}).get("signal", {}).get(ours)
        for key, p in now.items():
            q = later.get(key)
            # Universe: the charts price him above waivers this week (consensus > 0, the
            # eligibility floor in targets.js) with 2+ charts, and he is still compared next week.
            # Players both sides put at 0 (gap 0, change 0) would otherwise pad the ranks with ties.
            if p["of"] < MIN_CHARTS or not finite(p["value"]) or p["value"] <= 0:
                continue
            if q is None or q["of"] < MIN_CHARTS or not finite(q["value"]):
                continue
            placebo = None
            if prev and key in prev and prev[key]["of"] >= MIN_CHARTS and finite(prev[key]["value"]):
                placebo = p["value"] - prev[key]["value"]
            rows.append({"week": t, "horizon": horizon, "player_key": key, "pos": p["pos"],
                         "ours": p["ours"], "consensus": p["value"], "gap": p["gap"], "rank_gap": p["rank_gap"],
                         "side": p["side"], "eligible": p["eligible"], "list": p["list"], "flagged": p["flagged"],
                         "d_consensus": q["value"] - p["value"], "d_ours": q["ours"] - p["ours"],
                         "gap_later": q["gap"], "list_later": q["list"], "placebo": placebo})
    return rows


def actual_rows(panel: dict, ours: str, actuals: dict, scoring: str, horizon_weeks: int = 2) -> list:
    """Signal at content week t against realised points in weeks t..t+horizon-1
    (the games played after the charts were saved), relative to the ESPN
    per-game projection saved that week."""
    rows = []
    for t, wk in sorted(panel["weeks"].items()):
        proj = wk["espn_ppg"]
        for key, p in wk["signal"][ours].items():
            if p["of"] < MIN_CHARTS or not finite(p["value"]) or p["value"] <= 0 or key not in proj:
                continue
            pts = [actuals[(key, w)][scoring] for w in range(t, t + horizon_weeks) if (key, w) in actuals]
            if not pts:
                continue
            rows.append({"week": t, "player_key": key, "pos": p["pos"], "gap": p["gap"], "side": p["side"],
                         "list": p["list"], "projected_ppg": proj[key], "actual_ppg": float(np.mean(pts)),
                         "games": len(pts), "residual": float(np.mean(pts)) - proj[key]})
    return rows


def test_horizon(rows: list, rng, n_boot: int = N_BOOT) -> dict:
    out = {"n": len(rows), "players": len({r["player_key"] for r in rows}),
           "weeks": sorted({r["week"] for r in rows})}
    if len(rows) < 10:
        return out
    g = np.array([r["gap"] for r in rows]); dc = np.array([r["d_consensus"] for r in rows])
    do = np.array([r["d_ours"] for r in rows]); pk = np.array([r["player_key"] for r in rows])
    out["spearman_gap_vs_d_consensus"] = spearman_ci(g, dc, pk, rng, n_boot)
    if n_boot < N_BOOT:
        # The settings sweep: headline correlations and the listed hit rates only.
        out["spearman_gap_vs_d_ours"] = spearman_ci(g, do, pk, rng, n_boot)
        for side, direction in (("sell", "down"), ("buy", "up")):
            grp = [r for r in rows if r["list"] == side]
            d = np.array([r["d_consensus"] for r in grp]); k = np.array([r["player_key"] for r in grp])
            out[f"{side}_listed"] = {"n": len(grp), "consensus_moves_toward_ours":
                                     rate_ci((d < 0) if direction == "down" else (d > 0), k, rng, n_boot) if grp else None}
        return out
    out["spearman_gap_vs_d_ours"] = spearman_ci(g, do, pk, rng)
    out["spearman_gap_vs_d_gap"] = spearman_ci(g, dc - do, pk, rng)
    out["quintiles_d_consensus"] = quintiles(g, dc)
    out["quintiles_d_ours"] = quintiles(g, do)
    out["per_week"] = {}
    for w in out["weeks"]:
        sub = [r for r in rows if r["week"] == w]
        out["per_week"][w] = {"n": len(sub),
                              "rho_d_consensus": spearman([r["gap"] for r in sub], [r["d_consensus"] for r in sub]),
                              "rho_d_ours": spearman([r["gap"] for r in sub], [r["d_ours"] for r in sub])}
    out["per_position"] = {}
    for pos in ref.POSITIONS:
        sub = [r for r in rows if r["pos"] == pos]
        if len(sub) >= 10:
            out["per_position"][pos] = {"n": len(sub),
                                        "rho_d_consensus": spearman([r["gap"] for r in sub], [r["d_consensus"] for r in sub]),
                                        "rho_d_ours": spearman([r["gap"] for r in sub], [r["d_ours"] for r in sub])}
    # Position-demeaned gap (a position whose charts run rich would otherwise drive the pooled number).
    means = defaultdict(list)
    for r in rows:
        means[r["pos"]].append(r["gap"])
    mu = {p: float(np.mean(v)) for p, v in means.items()}
    out["spearman_position_demeaned"] = spearman_ci(g - np.array([mu[r["pos"]] for r in rows]), dc, pk, rng)
    # Placebo: the consensus price's own move from the week before.
    sub = [r for r in rows if r["placebo"] is not None]
    if len(sub) >= 10:
        pg = np.array([r["gap"] for r in sub]); pp = np.array([r["placebo"] for r in sub])
        pdc = np.array([r["d_consensus"] for r in sub]); ppk = np.array([r["player_key"] for r in sub])
        out["placebo"] = {"n": len(sub), "spearman_placebo_vs_d_consensus": spearman_ci(pp, pdc, ppk, rng),
                          "spearman_gap_vs_d_consensus_same_rows": spearman_ci(pg, pdc, ppk, rng),
                          "spearman_gap_vs_placebo": spearman(pg, pp),
                          "rank_regression_d_consensus_on_gap_and_placebo": rank_regression(pdc, {"gap": pg, "placebo": pp})}
    # Hit rates: Sell = consensus falls next (price reverts toward ours); Buy = consensus rises.
    base_up = rate_ci(dc > 0, pk, rng)
    base_down = rate_ci(dc < 0, pk, rng)
    out["base_rate"] = {"consensus_up": base_up, "consensus_down": base_down,
                        "mean_d_consensus": float(dc.mean()), "mean_d_ours": float(do.mean())}
    for side, direction in (("sell", "down"), ("buy", "up")):
        listed = [r for r in rows if r["list"] == side]
        eligible = [r for r in rows if r["eligible"] and r["side"] == side]
        for label, group in (("listed", listed), ("eligible", eligible)):
            if not group:
                out[f"{side}_{label}"] = {"n": 0}
                continue
            d = np.array([r["d_consensus"] for r in group]); o = np.array([r["d_ours"] for r in group])
            k = np.array([r["player_key"] for r in group])
            hit = (d < 0) if direction == "down" else (d > 0)
            gap_closes = np.abs(np.array([r["gap_later"] if r["gap_later"] is not None else np.nan for r in group])) < np.abs(np.array([r["gap"] for r in group]))
            out[f"{side}_{label}"] = {
                "n": len(group), "players": int(len(np.unique(k))),
                "consensus_moves_toward_ours": rate_ci(hit, k, rng),
                "ours_moves_toward_consensus": rate_ci((o > 0) if side == "sell" else (o < 0), k, rng),
                "gap_closes": rate_ci(gap_closes, k, rng),
                "mean_d_consensus": float(d.mean()), "mean_d_ours": float(o.mean()),
                "mean_gap": float(np.mean([r["gap"] for r in group])),
                "still_listed_later": rate_ci(np.array([r["list_later"] == side for r in group]), k, rng),
                "flipped_side_later": rate_ci(np.array([(r["gap_later"] or 0) * (r["gap"] or 0) < 0 for r in group]), k, rng),
            }
    out["persistence"] = {
        "spearman_gap_vs_gap_later": spearman_ci(g, np.array([r["gap_later"] for r in rows]), pk, rng),
        "share_gap_shrinks": rate_ci(np.abs(np.array([r["gap_later"] for r in rows])) < np.abs(g), pk, rng),
        "share_sign_flips": rate_ci(np.array([r["gap_later"] * r["gap"] < 0 for r in rows]), pk, rng),
        "d_gap_from_consensus_share": float(np.sum(np.abs(dc)) / max(np.sum(np.abs(dc)) + np.sum(np.abs(do)), 1e-9)),
    }
    return out


def test_actuals(rows: list, rng) -> dict:
    out = {"n": len(rows), "players": len({r["player_key"] for r in rows}), "weeks": sorted({r["week"] for r in rows})}
    if len(rows) < 10:
        return out
    g = np.array([r["gap"] for r in rows]); res = np.array([r["residual"] for r in rows])
    pk = np.array([r["player_key"] for r in rows])
    out["spearman_gap_vs_residual"] = spearman_ci(g, res, pk, rng)
    out["quintiles_residual"] = quintiles(g, res)
    out["mean_residual_all"] = float(res.mean())
    out["spearman_projection_vs_actual"] = spearman([r["projected_ppg"] for r in rows], [r["actual_ppg"] for r in rows])
    for side in ("sell", "buy"):
        grp = [r for r in rows if r["list"] == side]
        if grp:
            rr = np.array([r["residual"] for r in grp]); kk = np.array([r["player_key"] for r in grp])
            out[f"{side}_listed"] = {"n": len(grp), "mean_residual": float(rr.mean()),
                                     "beats_projection": rate_ci(rr > 0, kk, rng)}
    out["per_position"] = {}
    for pos in ref.POSITIONS:
        sub = [r for r in rows if r["pos"] == pos]
        if len(sub) >= 10:
            out["per_position"][pos] = {"n": len(sub), "rho": spearman([r["gap"] for r in sub], [r["residual"] for r in sub])}
    return out


def list_summary(panel: dict, ours: str) -> dict:
    out = {}
    for w, wk in sorted(panel["weeks"].items()):
        sig = wk["signal"][ours]
        gaps = [p["gap"] for p in sig.values() if p["of"] >= MIN_CHARTS and finite(p["gap"])]
        priced = [p for p in sig.values() if p["of"] >= MIN_CHARTS and finite(p["value"]) and p["value"] > 0]
        out[w] = {"sources": wk["sources"], "compared": len(sig),
                  "with_consensus": len(gaps), "priced_by_charts": len(priced),
                  "ours_above_zero": sum(1 for p in sig.values() if p["ours"] > 0),
                  "buy_listed": sum(1 for p in sig.values() if p["list"] == "buy"),
                  "sell_listed": sum(1 for p in sig.values() if p["list"] == "sell"),
                  "buy_eligible": sum(1 for p in sig.values() if p["eligible"] and p["side"] == "buy"),
                  "sell_eligible": sum(1 for p in sig.values() if p["eligible"] and p["side"] == "sell"),
                  "flagged": sum(1 for p in sig.values() if p["flagged"]),
                  "median_gap": float(np.median(gaps)) if gaps else None,
                  "mean_abs_gap": float(np.mean(np.abs(gaps))) if gaps else None}
    return out


def self_test(inp, docs: dict) -> dict:
    """The served week re-priced from its snapshot against the reference's live
    fixture run at the default setting, with the fixture holds applied.
    A mismatch is reported, never treated as a live-site reproduction."""
    s = ref.Setting(inp, DEFAULT["scoring"], DEFAULT["teams"], 0)
    st = s.state()
    live = s.result()
    served = max(docs)
    hidden = set(st.get("hidden") or set())
    # A held source's live section can be an older version than the week's snapshot (FantasyCalc on
    # 2026-10-22: the chain held its latest pull and kept serving the last published one). The live
    # run uses the served version, so the self-test does too; the raw snapshot diff is reported as well.
    doc = json.loads(json.dumps(docs[served]))
    swapped = []
    for key in hidden:
        entry = (doc.get("sources") or {}).get(key)
        if entry and st["current"].get(key):
            snap = ref.snapshot_natives(inp, key, entry, s.scoring)
            if snap != st["current"][key]:
                swapped.append(key)
                entry["natives"] = {s.scoring: {str(k): v for k, v in st["current"][key].items()}}
    raw = price_week(inp, s, docs[served], hidden=hidden)["result"]
    re_run = price_week(inp, s, doc, hidden=hidden)["result"]
    raw_diffs = [abs(r["ddf"]["blended"]["value"] - raw["rows"][k]["ddf"]["blended"]["value"])
                 for k, r in live["rows"].items()
                 if k in raw["rows"] and finite(r["ddf"]["blended"]["value"]) and finite(raw["rows"][k]["ddf"]["blended"]["value"])]
    diffs = []
    for key, r in live["rows"].items():
        a = r["ddf"]["blended"]["value"]; b = (re_run["rows"].get(key) or {}).get("ddf", {}).get("blended", {}).get("value")
        if finite(a) and finite(b):
            diffs.append(abs(a - b))
        for c in CHART_KEYS:
            a, b = r["indexed"].get(c), (re_run["rows"].get(key) or {}).get("indexed", {}).get(c)
            if finite(a) and finite(b):
                diffs.append(abs(a - b))
    return {"served_week": served, "hidden_in_live_run": sorted(hidden), "live_included": st["included"],
            "held_sources_swapped_to_served_version": swapped,
            "raw_snapshot_max_abs_diff_ddf_value": max(raw_diffs) if raw_diffs else None,
            "values_compared": len(diffs), "max_abs_diff": max(diffs) if diffs else None,
            "within_value_check_tolerance": bool(diffs) and max(diffs) <= 0.05}


def git_head() -> str:
    try:
        return subprocess.run(["git", "-C", str(REPO), "rev-parse", "--short", "HEAD"], capture_output=True,
                              text=True, timeout=10).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return "unknown"


# ---------------------------------------------------------------------------
# 5. Markdown
# ---------------------------------------------------------------------------

def fmt(v, nd=2):
    if v is None:
        return "n/a"
    if isinstance(v, dict) and "rho" in v:
        if v["rho"] is None:
            return "n/a"
        ci = v.get("ci95")
        return f"{v['rho']:+.{nd}f} [{ci[0]:+.{nd}f}, {ci[1]:+.{nd}f}] (n={v['n']})" if ci else f"{v['rho']:+.{nd}f} (n={v['n']})"
    if isinstance(v, dict) and "rate" in v:
        if v["rate"] is None:
            return "n/a"
        ci = v.get("ci95")
        return f"{100*v['rate']:.0f}% [{100*ci[0]:.0f}, {100*ci[1]:.0f}] (n={v['n']})" if ci else f"{100*v['rate']:.0f}%"
    if isinstance(v, float):
        return f"{v:+.{nd}f}"
    return str(v)


def markdown(report: dict) -> str:
    L = []
    meta = report["meta"]
    L.append(f"# Gap backtest figures (JEG-882 / JEG-1411)\n\nAggregation: {meta['aggregation']}; modeled saved 2026 inputs.\n")
    L.append(f"Generated {meta['generated_at']} by `tools/research/gap_backtest.py` at {meta['git_head']}; "
             f"reference {meta['reference_version']}; weeks {meta['weeks']}; live build {meta['live_build_tag']}.\n")
    st = report["self_test"]
    L.append(f"Fixture consistency check (not a live check): week {st['served_week']} snapshot vs the reference's fixture run: {st['values_compared']} values, "
             f"max abs diff {st['max_abs_diff']:.4f}, within 0.05: {st['within_value_check_tolerance']} "
             f"(hidden in fixture run: {st['hidden_in_live_run']}; held sources read from the served version: "
             f"{st['held_sources_swapped_to_served_version']}; with the raw snapshot instead the DDF Value max diff is "
             f"{st['raw_snapshot_max_abs_diff_ddf_value']:.2f}).\n")
    for ours in OURS:
        d = report["default"][ours]
        L.append(f"\n## Our value = {meta['ours_labels'][ours]} (Full PPR, 12 teams)\n")
        L.append("### Lists by week\n")
        L.append("| Week | Sources saved | Compared | Priced by charts | Ours above 0 | Buy listed | Sell listed | Buy eligible | Sell eligible | Mean abs gap |")
        L.append("|---|---|---|---|---|---|---|---|---|---|")
        for w, s in d["lists"].items():
            L.append(f"| {w} | {len(s['sources'])} | {s['compared']} | {s['priced_by_charts']} | {s['ours_above_zero']} | {s['buy_listed']} | {s['sell_listed']} | "
                     f"{s['buy_eligible']} | {s['sell_eligible']} | {fmt(s['mean_abs_gap'])} |")
        for h in (1, 2):
            t = d[f"horizon_{h}"]
            L.append(f"\n### Horizon {h} week{'s' if h > 1 else ''} (n={t['n']} player-weeks, {t['players']} players, weeks {t['weeks']})\n")
            if "spearman_gap_vs_d_consensus" not in t:
                L.append("Too few rows.\n")
                continue
            L.append("| Test | Spearman rho [95% cluster bootstrap] |")
            L.append("|---|---|")
            L.append(f"| gap vs change in consensus price | {fmt(t['spearman_gap_vs_d_consensus'])} |")
            L.append(f"| gap vs change in our value | {fmt(t['spearman_gap_vs_d_ours'])} |")
            L.append(f"| gap vs change in gap | {fmt(t['spearman_gap_vs_d_gap'])} |")
            L.append(f"| position-demeaned gap vs change in consensus | {fmt(t['spearman_position_demeaned'])} |")
            if "placebo" in t:
                p = t["placebo"]
                L.append(f"| placebo (consensus own move t-1 to t) vs change in consensus | {fmt(p['spearman_placebo_vs_d_consensus'])} |")
                L.append(f"| gap vs change in consensus, same rows as placebo | {fmt(p['spearman_gap_vs_d_consensus_same_rows'])} |")
                rr = p["rank_regression_d_consensus_on_gap_and_placebo"]
                L.append(f"| rank regression, change in consensus on gap and placebo | gap t={rr['gap']['t']:+.1f}, placebo t={rr['placebo']['t']:+.1f} (n={rr['n']}) |")
            L.append("\nPer week (rho, gap vs change in consensus / vs change in ours):\n")
            L.append("| Week | n | consensus | ours |")
            L.append("|---|---|---|---|")
            for w, pw in t["per_week"].items():
                L.append(f"| {w} | {pw['n']} | {fmt(pw['rho_d_consensus'])} | {fmt(pw['rho_d_ours'])} |")
            L.append("\nPer position:\n")
            L.append("| Position | n | consensus | ours |")
            L.append("|---|---|---|---|")
            for pos, pp in t["per_position"].items():
                L.append(f"| {pos} | {pp['n']} | {fmt(pp['rho_d_consensus'])} | {fmt(pp['rho_d_ours'])} |")
            L.append("\nQuintiles of the gap (1 = charts pay least relative to us, 5 = most); outcome = change in consensus price:\n")
            L.append("| Bucket | Gap range | n | Mean change | Median change | Share up |")
            L.append("|---|---|---|---|---|---|")
            for q in t["quintiles_d_consensus"]:
                L.append(f"| {q['bucket']} | {q['signal_lo']:+.1f} to {q['signal_hi']:+.1f} | {q['n']} | {q['mean_outcome']:+.2f} | {q['median_outcome']:+.2f} | {100*q['share_positive']:.0f}% |")
            L.append("\nSame buckets; outcome = change in our value:\n")
            L.append("| Bucket | n | Mean change | Median change | Share up |")
            L.append("|---|---|---|---|---|")
            for q in t["quintiles_d_ours"]:
                L.append(f"| {q['bucket']} | {q['n']} | {q['mean_outcome']:+.2f} | {q['median_outcome']:+.2f} | {100*q['share_positive']:.0f}% |")
            b = t["base_rate"]
            L.append(f"\nBase rates over all compared players: consensus up {fmt(b['consensus_up'])}, down {fmt(b['consensus_down'])}; "
                     f"mean change in consensus {b['mean_d_consensus']:+.2f}, in ours {b['mean_d_ours']:+.2f}.\n")
            L.append("| List | n | Players | Mean gap | Consensus moves toward ours | Ours moves toward consensus | Gap closes | Still listed | Sign flips |")
            L.append("|---|---|---|---|---|---|---|---|---|")
            for side in ("sell", "buy"):
                for label in ("listed", "eligible"):
                    s = t[f"{side}_{label}"]
                    if s["n"] == 0:
                        L.append(f"| {side} {label} | 0 | | | | | | | |")
                        continue
                    L.append(f"| {side} {label} | {s['n']} | {s['players']} | {s['mean_gap']:+.1f} | {fmt(s['consensus_moves_toward_ours'])} | "
                             f"{fmt(s['ours_moves_toward_consensus'])} | {fmt(s['gap_closes'])} | {fmt(s['still_listed_later'])} | {fmt(s['flipped_side_later'])} |")
            pz = t["persistence"]
            L.append(f"\nPersistence: gap vs gap {h} week later {fmt(pz['spearman_gap_vs_gap_later'])}; gap shrinks {fmt(pz['share_gap_shrinks'])}; "
                     f"sign flips {fmt(pz['share_sign_flips'])}; share of gap movement that came from the consensus side {100*pz['d_gap_from_consensus_share']:.0f}%.\n")
        a = d["actuals"]
        L.append(f"\n### Realised points (n={a['n']} player-weeks, {a['players']} players, signal weeks {a['weeks']})\n")
        if "spearman_gap_vs_residual" in a:
            L.append(f"Spearman gap vs (actual minus ESPN projected points per game over the next two games): {fmt(a['spearman_gap_vs_residual'])}; "
                     f"projection vs actual {fmt(a['spearman_projection_vs_actual'])}; mean residual {a['mean_residual_all']:+.2f}.\n")
            L.append("| Bucket | Gap range | n | Mean residual | Share beats projection |")
            L.append("|---|---|---|---|---|")
            for q in a["quintiles_residual"]:
                L.append(f"| {q['bucket']} | {q['signal_lo']:+.1f} to {q['signal_hi']:+.1f} | {q['n']} | {q['mean_outcome']:+.2f} | {100*q['share_positive']:.0f}% |")
            for side in ("sell", "buy"):
                s = a.get(f"{side}_listed")
                if s:
                    L.append(f"\n{side} listed: n={s['n']}, mean residual {s['mean_residual']:+.2f}, beats projection {fmt(s['beats_projection'])}.")
            L.append("\nPer position: " + ", ".join(f"{p} {fmt(v['rho'])} (n={v['n']})" for p, v in a["per_position"].items()) + "\n")
    L.append("\n## All 12 settings, our value = DDF Value: Spearman gap vs next-week change in consensus\n")
    L.append("| Scoring | Teams | n | rho | 95% CI | rho (ours changes) | sell listed hit | buy listed hit |")
    L.append("|---|---|---|---|---|---|---|---|")
    for s in report["settings_sweep"]:
        r = s["h1"]
        if "spearman_gap_vs_d_consensus" not in r:
            L.append(f"| {s['scoring']} | {s['teams']} | {r['n']} | too few | | | | |")
            continue
        sc = r["spearman_gap_vs_d_consensus"]; so = r["spearman_gap_vs_d_ours"]
        L.append(f"| {s['scoring']} | {s['teams']} | {sc['n']} | {sc['rho']:+.2f} | [{sc['ci95'][0]:+.2f}, {sc['ci95'][1]:+.2f}] | {so['rho']:+.2f} | "
                 f"{fmt(r['sell_listed']['consensus_moves_toward_ours'])} | {fmt(r['buy_listed']['consensus_moves_toward_ours'])} |")
    return ("\n".join(L) + "\n").replace("consensus", "Trade chart average")


# ---------------------------------------------------------------------------

def post_markdown(report: dict) -> str:
    """Render the studied projection view directly from the mean rerun evidence."""
    if report['meta']['aggregation'] != 'mean':
        raise ValueError('Post 07 requires mean-based figures')
    m = report['meta']; d = report['default']['proj']; h = d['horizon_1']
    h2 = d['horizon_2']; a = d['actuals']; b = h['buy_listed']; p = h['placebo']
    rr = p['rank_regression_d_consensus_on_gap_and_placebo']
    return f'''# Does the Trade chart average gap predict anything?

This is early evidence from saved 2026 content weeks {min(m['weeks'])} to {max(m['weeks'])}.
These figures are **mean-based**, rerun on {m['generated_at']} with the
reference engine at commit `{m['git_head']}`. Jeremy approved the research
aggregation change on 31 October 2026 (JEG-1411). The earlier October 22
figures used a different aggregation and are superseded here.

Terms used below:

- **DDF Value (projections)** is the projection-side view: the average of the
  projection sources' weight-adjusted indexed values. Every result below uses
  this view as our value.
- **Indexed** is a chart's value on the common scale, before position and
  bench weighting.
- **Trade chart average (mean)** is the arithmetic mean of the available
  Indexed trade-chart values for a player. A real zero counts; a missing chart
  does not.
- **The gap** is the Trade chart average minus DDF Value (projections).
  A positive gap is the Sell side; a negative gap is the Buy side.

## Data and method

The chart inputs are saved as-published 2026 weekly snapshots, then modeled
through the checked-out reference engine. These are historical inputs, not
fresh current-week prices. The player universe has {m['players_universe']} players
from this checkout. The actuals file contains 2026 weeks
{min(m['actual_weeks'])} to {max(m['actual_weeks'])}; each outcome uses only the next
two calendar weeks from the signal week, skipping a missing game row rather
than counting it as zero. Older reports used earlier player and actuals files,
so their sample sizes need not match this rerun.

The headline setting is Full PPR, 12 teams, one quarterback and the standard
roster. Each saved week uses the sources recorded for that content week, with
no holds. Indexed chart prices and DDF Value (projections) use the same league
scale. A gap can therefore reflect a price disagreement at those settings.

The research signal requires at least two charts, a positive Trade chart
average, and a strict majority of charts on the same side of our value.
A Sell requires our value of at least 5. A Buy requires the position
rank-equivalent gap to be at most -2. Players zeroed by the saved ESPN
projection or given estimated chart prices are excluded from the lists.
This is the research mean variant of the signal; it does not change the site
or engine's calculations.

We compare each gap with the next change in the Trade chart average and in our
value, then check gap persistence. A placebo control uses the chart average's
own previous move. Correlations are Spearman rank correlations. Intervals are
95 percent cluster bootstraps by player, with 1,000 draws at the headline
setting. Results are associations, not evidence that an actual offer was accepted.

## Results

The next-week panel has {h['n']} player-weeks and {h['players']} players,
covering signal weeks {h['weeks']}. Figures below show correlations and their
95 percent intervals unless specified otherwise.

| Test | Mean-based result |
|---|---|
| Gap vs next change in Trade chart average | {fmt(h['spearman_gap_vs_d_consensus'])} |
| Gap vs next change in our value | {fmt(h['spearman_gap_vs_d_ours'])} |
| Gap vs next change in gap | {fmt(h['spearman_gap_vs_d_gap'])} |
| Placebo vs next change in Trade chart average | {fmt(p['spearman_placebo_vs_d_consensus'])} |
| Gap on the same rows as the placebo | {fmt(p['spearman_gap_vs_d_consensus_same_rows'])} |
| Rank regression, gap and placebo together | gap t={rr['gap']['t']:+.1f}, placebo t={rr['placebo']['t']:+.1f} (n={rr['n']}) |

The Buy list has {b['n']} player-weeks and {b['players']} players. Its share
with a rising Trade chart average next week is {fmt(b['consensus_moves_toward_ours'])},
against the all-player base rate of {fmt(h['base_rate']['consensus_up'])}.
The intervals matter: a Buy label is not a promise that the price will rise.

| Persistence test | Mean-based result |
|---|---|
| Gap vs gap one week later | {fmt(h['persistence']['spearman_gap_vs_gap_later'])} |
| Gap vs gap two weeks later | {fmt(h2['persistence']['spearman_gap_vs_gap_later'])} |
| Gaps changing sign next week | {fmt(h['persistence']['share_sign_flips'])} |
| Buy targets still listed next week | {fmt(b['still_listed_later'])} |

The realised-points panel has {a['n']} player-weeks and {a['players']} players,
using signal weeks {a['weeks']}. The gap's correlation with actual points per
game minus the saved ESPN projection is {fmt(a['spearman_gap_vs_residual'])}.
The projection's correlation with actual points is
{fmt(a['spearman_projection_vs_actual'])}.
A price gap and a forecast of fantasy production answer different questions.

## Limits and interpretation

- The history covers one season and only a few weekly transitions. It cannot
  establish a stable effect across seasons.
- This is a modeled rerun with the current checkout's player list and
  reference engine. Players absent from that list are absent from every week.
- Chart values come from published snapshots; Indexed values, gaps, list
  memberships and statistics are modeled. Actuals are observed game results.
- A chart dropping a player can produce a large move. The mean of two to four
  charts remains sensitive to outliers and changes in which charts price him.
- No actual proposed or accepted trades are recorded. A price move is a proxy,
  not a measured trade outcome.
- The historical snapshot consistency diagnostic has maximum difference
  {report['self_test']['max_abs_diff']:.4f} against the checkout's current fixture;
  it {'passes' if report['self_test']['within_value_check_tolerance'] else 'does not pass'} the 0.05 tolerance. It is not proof of historical live-site
  parity, and no live site was checked for this rerun.

For a manager, use the gap as a description of disagreement between the chart
average and the projection view. Read it alongside the uncertainty and roster
context, rather than as an instruction to buy or sell.

## Evidence

- Reproduction: `python3 tools/research/gap_backtest.py --output-dir docs/research/data/jeg1411-mean --post docs/research/posts/07-does-the-gap-predict.md`.
- [Mean rerun tables](../data/jeg1411-mean/gap_backtest.md),
  [full statistics](../data/jeg1411-mean/gap_backtest.json) and
  [player-week rows](../data/jeg1411-mean/gap_backtest.csv).
- [Before/after comparison](../data/jeg1411-mean/before-after.md) separates
  the old published figures from a median baseline on the same current inputs.
- The underlying script also runs Standard, Half PPR and PPR at each supported
  team count. Its settings appendix is explicitly the DDF Value chart view;
  the headline study above is DDF Value (projections).
'''


def comparison_markdown(previous: dict, baseline: dict, report: dict) -> str:
    """Separate input/engine drift from the research aggregation change."""
    if baseline['meta']['aggregation'] != 'median' or report['meta']['aggregation'] != 'mean':
        raise ValueError('Comparison requires a median baseline and mean rerun')
    for key in ['git_head', 'weeks', 'actual_weeks', 'players_universe', 'fixture_built_at', 'constants']:
        if baseline['meta'][key] != report['meta'][key]:
            raise ValueError(f'Comparison inputs differ: {key}')
    metrics = [
        ('Next-week player-weeks', 'horizon_1.n'),
        ('Next-week players', 'horizon_1.players'),
        ('Gap vs next Trade chart average change', 'horizon_1.spearman_gap_vs_d_consensus'),
        ('Gap vs next own-value change', 'horizon_1.spearman_gap_vs_d_ours'),
        ('Gap vs next gap change', 'horizon_1.spearman_gap_vs_d_gap'),
        ('Placebo vs next chart change', 'horizon_1.placebo.spearman_placebo_vs_d_consensus'),
        ('Gap vs next chart change, placebo rows', 'horizon_1.placebo.spearman_gap_vs_d_consensus_same_rows'),
        ('Partial gap t', 'horizon_1.placebo.rank_regression_d_consensus_on_gap_and_placebo.gap.t'),
        ('Partial placebo t', 'horizon_1.placebo.rank_regression_d_consensus_on_gap_and_placebo.placebo.t'),
        ('Buy player-weeks', 'horizon_1.buy_listed.n'),
        ('Buy players', 'horizon_1.buy_listed.players'),
        ('Buy chart price rises', 'horizon_1.buy_listed.consensus_moves_toward_ours'),
        ('Base chart price rises', 'horizon_1.base_rate.consensus_up'),
        ('One-week persistence', 'horizon_1.persistence.spearman_gap_vs_gap_later'),
        ('Two-week persistence', 'horizon_2.persistence.spearman_gap_vs_gap_later'),
        ('Gap sign flips', 'horizon_1.persistence.share_sign_flips'),
        ('Buy still listed', 'horizon_1.buy_listed.still_listed_later'),
        ('Actuals player-weeks', 'actuals.n'), ('Actuals players', 'actuals.players'),
        ('Gap vs actual residual', 'actuals.spearman_gap_vs_residual'),
        ('Projection vs actual', 'actuals.spearman_projection_vs_actual'),
    ]
    def get(r, path):
        v = r['default']['proj']
        for k in path.split('.'):
            v = v[k]
        return fmt(v)
    lines = ['# Post 07 before / after (JEG-1411)', '',
             'The October 22 report is historical evidence, not the same input set.',
             'The median baseline and mean rerun use the same checked-out engine,',
             'saved 2026 inputs, players, actuals and random seed. Only their research',
             'chart aggregation differs. The mean can admit more players when a',
             'positive chart value raises the mean above zero while the middle value is zero.', '',
             '| Metric | October 22 median report | Current-input median | Current-input mean |',
             '|---|---|---|---|']
    lines += [f'| {label} | {get(previous, path)} | {get(baseline, path)} | {get(report, path)} |'
              for label, path in metrics]
    return '\n'.join(lines) + '\n'


def main() -> int:
    global AGGREGATION, OUT_DIR
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--aggregation', choices=['mean', 'median'], default='mean',
                        help='median is retained only for same-input before/after comparisons')
    parser.add_argument('--output-dir', type=Path, default=OUT_DIR)
    parser.add_argument('--post', type=Path, help='render post 07 from a mean report')
    parser.add_argument('--median-baseline', type=Path, help='same-input median JSON for comparison')
    parser.add_argument('--previous-report', type=Path, default=REPO / 'docs/research/data/gap_backtest.json')
    args = parser.parse_args()
    AGGREGATION, OUT_DIR = args.aggregation, args.output_dir
    rng = np.random.default_rng(SEED)
    inp = ref.Inputs.load(ref.FIXTURE, ref.PLAYERS)
    docs = {w: load_week(w) for w in WEEKS if (HISTORY / f"week-{w}.json").exists()}
    actuals = load_actuals()
    actual_weeks = sorted({w for (_, w) in actuals})
    meta = {"generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ"), "git_head": git_head(),
            "reference_version": ref.VERSION, "pipeline_version": ref.PIPELINE_VERSION,
            "weeks": sorted(docs), "actual_weeks": actual_weeks,
            "aggregation": AGGREGATION,
            "live_build_tag": "unavailable: offline modeled rerun, no live check",
            "players_universe": len(inp.players), "fixture_built_at": inp.fixture.get("built_at"),
            "ours_labels": {"blend": "DDF Value",
                            "proj": "DDF Value (projections)"},
            "constants": {"SELL_FLOOR": SELL_FLOOR, "BUY_RANK_MARGIN": BUY_RANK_MARGIN, "MIN_CHARTS": MIN_CHARTS,
                          "N_BOOT": N_BOOT, "SEED": SEED},
            "sources_by_week": {w: sorted(k for k in ref.SOURCES if (d.get("sources") or {}).get(k)) for w, d in docs.items()}}
    report = {"schema": "gap-backtest/1", "meta": meta, "self_test": self_test(inp, docs), "default": {}, "settings_sweep": []}

    csv_rows = []
    panel = build_panel(inp, DEFAULT, docs)
    for ours in OURS:
        d = {"lists": list_summary(panel, ours)}
        for h in (1, 2):
            rows = pairs(panel, ours, h)
            d[f"horizon_{h}"] = test_horizon(rows, rng)
            for r in rows:
                csv_rows.append({"setting": "ppr/12", "view": ours, **{k: v for k, v in r.items()}})
        arows = actual_rows(panel, ours, actuals, DEFAULT["scoring"])
        d["actuals"] = test_actuals(arows, rng)
        report["default"][ours] = d

    for spec in ALL_SETTINGS:
        if spec == DEFAULT:
            p = panel
        else:
            p = build_panel(inp, spec, docs)
        rows = pairs(p, "blend", 1)
        report["settings_sweep"].append({**spec, "h1": test_horizon(rows, rng, N_BOOT_SWEEP)})

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "gap_backtest.json").write_text(json.dumps(report, indent=1, default=float), encoding="utf-8")
    if csv_rows:
        with (OUT_DIR / "gap_backtest.csv").open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(csv_rows[0].keys()), lineterminator="\n")
            w.writeheader()
            w.writerows(csv_rows)
    (OUT_DIR / "gap_backtest.md").write_text(markdown(report), encoding="utf-8")
    if args.median_baseline:
        before = json.loads(args.previous_report.read_text())
        baseline = json.loads(args.median_baseline.read_text())
        (OUT_DIR / 'before-after.md').write_text(comparison_markdown(before, baseline, report), encoding='utf-8')
    if args.post:
        if AGGREGATION != 'mean':
            raise ValueError('Post 07 must be mean-based')
        args.post.write_text(post_markdown(report), encoding='utf-8')
    print(f"wrote {OUT_DIR}/gap_backtest.{{json,csv,md}}; weeks {sorted(docs)}; self-test max diff "
          f"{report['self_test']['max_abs_diff']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
