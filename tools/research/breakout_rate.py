#!/usr/bin/env python3
"""Historical breakout rate: share of bench players who became starter-tier mid-season.

From 2015-2025 nflverse weekly actuals, for each position and depth round:
what fraction of players ranked as bench at the season's midpoint (week 9)
moved into the starter tier by season end (week 17/18)?

A "breakout" is defined as: a player ranked outside the top S (starters) at
mid-season who finishes the season ranked inside the top S, where ranking is
by cumulative half-PPR points per game.

Output: docs/research/data/breakout_rate.md and .json.

JEG-544. Research only.

Usage:
    python3 tools/research/breakout_rate.py [--teams 12]
"""
from __future__ import annotations

import argparse
import csv
import gzip
import json
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ACTUALS = REPO / "data" / "inputs" / "weekly_actuals_nflverse_2015_2025.csv.gz"
OUT_DIR = REPO / "docs" / "research" / "data"
POSITIONS = ["QB", "RB", "WR", "TE"]
# Starter counts at 12 teams (conventional)
DEFAULT_STARTERS = {"QB": 12, "RB": 24, "WR": 36, "TE": 12}


def compute_breakout_rates(teams: int = 12) -> dict:
    S = {p: (DEFAULT_STARTERS[p] * teams // 12) for p in POSITIONS}

    # Load all player-week data
    player_week_pts = defaultdict(lambda: defaultdict(float))  # (pos, season, pid) -> {week: pts}
    player_names = {}

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
            player_names[pid] = row.get("name", pid)

    seasons = sorted(set(s for (_, s, _) in player_week_pts.keys()))

    # For each season and position:
    # 1. Rank at midpoint (week 9) by cumulative PPG through week 9
    # 2. Rank at end (week 17 or 18) by cumulative PPG through end
    # 3. Count bench players at midpoint who are starters at end
    results = {p: {"breakouts": 0, "bench_at_mid": 0, "by_depth": defaultdict(lambda: {"breakouts": 0, "total": 0}),
                   "by_season": {}} for p in POSITIONS}

    for season in seasons:
        total_weeks = 17 if season < 2021 else 18
        mid_week = 9

        for pos in POSITIONS:
            # Get all players this pos/season
            players = [(pid, player_week_pts[(pos, season, pid)])
                       for (p, s, pid) in player_week_pts if p == pos and s == season]

            if not players:
                continue

            # Cumulative PPG at midpoint
            def ppg_through(week_data, max_week):
                weeks_played = [w for w in week_data if w <= max_week]
                if not weeks_played:
                    return 0.0
                return sum(week_data[w] for w in weeks_played) / len(weeks_played)

            mid_ranks = [(pid, ppg_through(wdata, mid_week)) for pid, wdata in players]
            mid_ranks.sort(key=lambda x: -x[1])

            end_ranks = [(pid, ppg_through(wdata, total_weeks)) for pid, wdata in players]
            end_ranks.sort(key=lambda x: -x[1])

            s = S[pos]
            # Players who are starters at end
            end_starters = set(pid for pid, _ in end_ranks[:s])

            # Players who are bench at midpoint
            bench_at_mid = mid_ranks[s:]
            n_bench = len(bench_at_mid)
            n_breakout = 0

            for rank_idx, (pid, _) in enumerate(bench_at_mid):
                depth = rank_idx // teams  # depth round (0 = first backup)
                results[pos]["by_depth"][depth]["total"] += 1
                if pid in end_starters:
                    n_breakout += 1
                    results[pos]["by_depth"][depth]["breakouts"] += 1

            results[pos]["breakouts"] += n_breakout
            results[pos]["bench_at_mid"] += n_bench
            results[pos]["by_season"][season] = {
                "bench_at_mid": n_bench,
                "breakouts": n_breakout,
                "rate": round(n_breakout / n_bench, 4) if n_bench else 0,
            }

    # Summarize
    output = {"teams": teams, "seasons": len(seasons), "season_range": f"{seasons[0]}-{seasons[-1]}",
              "positions": {}}
    for pos in POSITIONS:
        r = results[pos]
        overall_rate = r["breakouts"] / r["bench_at_mid"] if r["bench_at_mid"] else 0
        depth_summary = {}
        for d in sorted(r["by_depth"].keys()):
            dd = r["by_depth"][d]
            depth_summary[f"depth_{d+1}"] = {
                "total": dd["total"],
                "breakouts": dd["breakouts"],
                "rate": round(dd["breakouts"] / dd["total"], 4) if dd["total"] else 0,
            }
        season_rates = [r["by_season"][s]["rate"] for s in sorted(r["by_season"])]
        output["positions"][pos] = {
            "bench_at_mid": r["bench_at_mid"],
            "breakouts": r["breakouts"],
            "overall_rate": round(overall_rate, 4),
            "by_depth": depth_summary,
            "season_rates": {str(s): r["by_season"][s] for s in sorted(r["by_season"])},
            "rate_range": [round(min(season_rates), 4), round(max(season_rates), 4)] if season_rates else [0, 0],
        }

    return output


def write_outputs(data: dict):
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    (OUT_DIR / "breakout_rate.json").write_text(
        json.dumps(data, indent=2) + "\n", encoding="utf-8")

    lines = [
        "# Historical breakout rates: bench to starter mid-season",
        "",
        f"{data['teams']}-team league, {data['seasons']} seasons ({data['season_range']}), nflverse game logs.",
        "",
        "A breakout: a player ranked outside the starter tier at mid-season (week 9) who finishes",
        "the season ranked inside the starter tier by cumulative points per game.",
        "",
        "## By position",
        "",
        "| Position | Bench at mid | Breakouts | Rate | Range across seasons |",
        "|---|---|---|---|---|",
    ]
    for pos in POSITIONS:
        r = data["positions"][pos]
        lines.append(
            f"| {pos} | {r['bench_at_mid']} | {r['breakouts']} | "
            f"{r['overall_rate']:.1%} | {r['rate_range'][0]:.1%} - {r['rate_range'][1]:.1%} |"
        )
    lines.extend(["", "## By depth round (first backup, second backup, ...)", "",
                   "| Position | Depth 1 | Depth 2 | Depth 3 |",
                   "|---|---|---|---|"])
    for pos in POSITIONS:
        r = data["positions"][pos]
        cells = [pos]
        for d in range(3):
            key = f"depth_{d+1}"
            if key in r["by_depth"]:
                dd = r["by_depth"][key]
                cells.append(f"{dd['rate']:.1%} ({dd['breakouts']}/{dd['total']})")
            else:
                cells.append("--")
        lines.append("| " + " | ".join(cells) + " |")

    lines.extend(["", f"Generated by `tools/research/breakout_rate.py`."])
    lines.append("")

    (OUT_DIR / "breakout_rate.md").write_text("\n".join(lines), encoding="utf-8")
    print("Wrote breakout_rate.json and .md to docs/research/data/")


def main():
    parser = argparse.ArgumentParser(description="Historical breakout rates")
    parser.add_argument("--teams", type=int, default=12)
    args = parser.parse_args()

    data = compute_breakout_rates(args.teams)
    write_outputs(data)

    # Print summary
    print()
    for pos in POSITIONS:
        r = data["positions"][pos]
        print(f"{pos:>4}: {r['overall_rate']:.1%} breakout ({r['breakouts']}/{r['bench_at_mid']}), "
              f"range {r['rate_range'][0]:.1%}-{r['rate_range'][1]:.1%}")
        for d in sorted(r["by_depth"]):
            dd = r["by_depth"][d]
            print(f"      {d}: {dd['rate']:.1%} ({dd['breakouts']}/{dd['total']})")


if __name__ == "__main__":
    main()
