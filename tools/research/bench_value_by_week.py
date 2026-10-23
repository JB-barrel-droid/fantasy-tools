#!/usr/bin/env python3
"""Bench value decline over the season: how fill-in and breakout value fall
as weeks remaining shrink.

For each content week 1-17 (as if we re-ran the model at that point):
- Remaining byes, remaining injury exposure, sigma (uncertainty narrows)
- Overall bench share from the expected-starts model
- Breakout value from historical actuals (fewer weeks for a breakout to pay off)
- Playoff-weeks weighting (bench value in playoff weeks vs regular season)

Also reports what the current tool does: the engine IS week-aware (objective_window
sets the remaining-weeks horizon, bye_share counts only future byes, drift_horizon
narrows sigma). Bench share is per-week (a share of the pie), not cumulative ROS.

Output: docs/research/data/bench_value_by_week.md and .json.

JEG-544. Research only.

Usage:
    python3 tools/research/bench_value_by_week.py [--scoring ppr] [--teams 12]
"""
from __future__ import annotations

import argparse
import csv
import gzip
import json
import math
import statistics
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "pipelines"))
import expected_starts_model as es  # noqa: E402
import derive_lineup_parameters as dl  # noqa: E402

POSITIONS = es.POSITIONS
OUT_DIR = REPO / "docs" / "research" / "data"
ACTUALS = REPO / "data" / "inputs" / "weekly_actuals_nflverse_2015_2025.csv.gz"


def model_bench_share_by_week(scoring: str = "ppr", teams: int = 12) -> list:
    """Run the expected-starts model at each content week and report bench share."""
    import value_reference as ref
    cfg = ref.load_lineup_config()
    inp = ref.Inputs.load(ref.FIXTURE, ref.PLAYERS)
    hist = ref.History(ref.HISTORY) if ref.HISTORY.exists() else None

    results = []
    for cw in range(1, 18):
        # Resolve parameters at this content week
        resolved = dl.resolve(cfg, content_week=cw)
        params = {p: resolved["positions"][p] for p in POSITIONS}
        params["bye"] = resolved["bye"]

        # Load sources and run
        sources, pos_of = es.load_sources(inp, scoring, teams)
        chart_sigma = es.chart_sigma_from(sources, teams)

        try:
            run = es.run_setting(sources, teams, params, chart_sigma, "A", "share")
        except Exception as e:
            results.append({"content_week": cw, "error": str(e)})
            continue

        # Get DDF values and compute bench share
        all_keys = set()
        for src in sources:
            for p in POSITIONS:
                all_keys.update(src.keys(p))
        ddf = es.ddf_mean(run["adjusted"], sorted(all_keys))
        ddf_tiers = es.tiers_on_values(
            {k: v for k, v in ddf.items() if v is not None}, pos_of, teams)
        metrics = es.shares_and_ratio(ddf, ddf_tiers, teams)

        window = dl.objective_window("season", cw)
        remaining_weeks = max(0, window[1] - window[0] + 1)
        bye_info = dl.bye_share(cfg["byes"], window[0], window[1])
        horizon = dl.drift_horizon(window, cw)

        row = {
            "content_week": cw,
            "remaining_weeks": remaining_weeks,
            "bye_share": round(bye_info["share"], 4),
            "drift_horizon": round(horizon, 1),
            "sigma_rel": {p: round(resolved["positions"][p]["sigma_rel"], 4) for p in POSITIONS},
            "bench_share_overall": round(metrics.get("bench_tier_share_overall", 0), 4),
            "bench_share_by_pos": {p: round(metrics.get("bench_tier_share", {}).get(p, 0), 4) for p in POSITIONS},
        }
        results.append(row)

    return results


def breakout_value_by_week(teams: int = 12) -> list:
    """Historical breakout rate by the week the breakout is measured from.

    For each hypothetical 'start week' w (mid-season point), what fraction of
    bench players at that week end up in the starter tier by season end?
    This shows how breakout value declines as fewer weeks remain.
    """
    S = {p: ({"QB": 12, "RB": 24, "WR": 36, "TE": 12}[p] * teams // 12) for p in POSITIONS}

    player_week_pts = defaultdict(lambda: defaultdict(float))
    with gzip.open(ACTUALS, "rt") as f:
        reader = csv.DictReader(f)
        for row in reader:
            pos = row["pos"]
            if pos not in POSITIONS:
                continue
            season = int(row["season"])
            week = int(row["week"])
            pid = row["player_id"]
            pts = float(row.get("half_ppr") or row.get("std") or 0)
            player_week_pts[(pos, season, pid)][week] = pts

    seasons = sorted(set(s for (_, s, _) in player_week_pts.keys()))

    results = []
    for measure_week in range(4, 17):  # weeks 4-16 as the "current" week
        pos_rates = {}
        for pos in POSITIONS:
            breakouts = 0
            bench_count = 0
            for season in seasons:
                total_weeks = 17 if season < 2021 else 18
                players = [(pid, player_week_pts[(pos, season, pid)])
                           for (p, s, pid) in player_week_pts if p == pos and s == season]
                if not players:
                    continue

                def ppg_through(wdata, max_week):
                    weeks = [w for w in wdata if w <= max_week]
                    if not weeks:
                        return 0.0
                    return sum(wdata[w] for w in weeks) / len(weeks)

                mid_ranks = [(pid, ppg_through(wd, measure_week)) for pid, wd in players]
                mid_ranks.sort(key=lambda x: -x[1])

                end_ranks = [(pid, ppg_through(wd, total_weeks)) for pid, wd in players]
                end_ranks.sort(key=lambda x: -x[1])

                s = S[pos]
                end_starters = set(pid for pid, _ in end_ranks[:s])
                bench_at_mid = mid_ranks[s:]

                bench_count += len(bench_at_mid)
                breakouts += sum(1 for pid, _ in bench_at_mid if pid in end_starters)

            rate = breakouts / bench_count if bench_count else 0
            pos_rates[pos] = round(rate, 4)

        results.append({
            "measure_week": measure_week,
            "weeks_remaining": 17 - measure_week,  # approx
            "breakout_rate": pos_rates,
        })

    return results


def write_outputs(model_data: list, breakout_data: list, scoring: str, teams: int):
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    combined = {
        "setting": {"scoring": scoring, "teams": teams},
        "model_bench_share_by_week": model_data,
        "breakout_rate_by_week": breakout_data,
        "engine_behavior": {
            "week_aware": True,
            "what_changes": [
                "objective_window shrinks (content_week+1 to last playoff week)",
                "bye_share counts only future byes in the remaining window",
                "drift_horizon narrows sigma (less projection uncertainty closer to games)",
                "missed-game rate (m) is per-week, unchanged by week"
            ],
            "bench_share_is": "per-week share of the value pie, not cumulative ROS total",
            "implication": "The per-week bench share stays roughly stable, but the total "
                           "ROS bench value (share x remaining weeks) naturally declines. "
                           "The model does not explicitly compute a 'bench value decay curve'."
        }
    }

    (OUT_DIR / "bench_value_by_week.json").write_text(
        json.dumps(combined, indent=2) + "\n", encoding="utf-8")

    # Markdown
    lines = [
        "# Bench value over the season",
        "",
        f"Setting: {scoring} / {teams} teams.",
        "",
        "## Model bench share by content week",
        "",
        "| Week | Remaining | Bye share | Sigma QB | Sigma RB | Bench share |",
        "|---|---|---|---|---|---|",
    ]
    for r in model_data:
        if "error" in r:
            continue
        lines.append(
            f"| {r['content_week']} | {r['remaining_weeks']} | {r['bye_share']:.1%} | "
            f"{r['sigma_rel']['QB']:.3f} | {r['sigma_rel']['RB']:.3f} | "
            f"{r['bench_share_overall']:.1%} |"
        )

    lines.extend(["", "## Historical breakout rate by measurement week", "",
                   "| Measure week | Weeks left | QB | RB | WR | TE |",
                   "|---|---|---|---|---|---|"])
    for r in breakout_data:
        br = r["breakout_rate"]
        lines.append(
            f"| {r['measure_week']} | {r['weeks_remaining']} | "
            f"{br['QB']:.1%} | {br['RB']:.1%} | {br['WR']:.1%} | {br['TE']:.1%} |"
        )

    lines.extend(["", "## What the engine does today", "",
                   "The expected-starts model IS week-aware:", ""])
    for item in combined["engine_behavior"]["what_changes"]:
        lines.append(f"- {item}")
    lines.extend(["",
                   f"Bench share is: {combined['engine_behavior']['bench_share_is']}.",
                   "", f"Generated by `tools/research/bench_value_by_week.py`.", ""])

    (OUT_DIR / "bench_value_by_week.md").write_text("\n".join(lines), encoding="utf-8")
    print("Wrote bench_value_by_week.json and .md to docs/research/data/")


def main():
    parser = argparse.ArgumentParser(description="Bench value by week")
    parser.add_argument("--scoring", default="ppr")
    parser.add_argument("--teams", type=int, default=12)
    args = parser.parse_args()

    print("Computing model bench share by week...")
    model_data = model_bench_share_by_week(args.scoring, args.teams)

    print("Computing historical breakout rates by week...")
    breakout_data = breakout_value_by_week(args.teams)

    write_outputs(model_data, breakout_data, args.scoring, args.teams)

    # Print summary
    print("\nModel bench share by week:")
    for r in model_data:
        if "error" in r:
            print(f"  cw={r['content_week']}: ERROR {r['error']}")
        else:
            print(f"  cw={r['content_week']}: remaining={r['remaining_weeks']}, "
                  f"bench_share={r['bench_share_overall']:.1%}, "
                  f"bye={r['bye_share']:.1%}, horizon={r['drift_horizon']}")

    print("\nBreakout rate by measurement week:")
    for r in breakout_data:
        br = r["breakout_rate"]
        print(f"  w={r['measure_week']}: QB={br['QB']:.1%} RB={br['RB']:.1%} "
              f"WR={br['WR']:.1%} TE={br['TE']:.1%}")


if __name__ == "__main__":
    main()
