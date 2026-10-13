#!/usr/bin/env python3
"""Insurance vs upside value of bench players, gross (vs hindsight best left out).

Reproduces: finding 6 (upside is about half of bench value; breakdown by
position and depth).

For each non-starter set into a lineup in a given week, measures the points
added split into:
  - insurance: filling in for an absent starter (the player played because
    a starter didn't)
  - upside: the player's production above what the best available deeper
    player would have scored

The "gross" version compares against the best player left out of that week's
hindsight-optimal lineup (not against the waiver wire). The net-of-waivers
version is in waiver_rule.py.

Source: 2026-10-10 bench research session (JEG-556 comments).

Usage:
    python3 tools/bench_research/insurance_upside.py [--teams 12] [--scoring ppr]
"""
from __future__ import annotations

import argparse
import csv
import gzip
import json
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
POSITIONS = ("QB", "RB", "WR", "TE")
ACTUALS = REPO / "data" / "inputs" / "weekly_actuals_nflverse_2015_2025.csv.gz"
SCHEDULE = REPO / "data" / "inputs" / "nfl_schedule_2015_2025.json"


def load_actuals(scoring="ppr"):
    """Load weekly actuals keyed by player_id -> season -> week -> points."""
    pts_col = {
        "ppr": "fantasy_points_ppr",
        "half_ppr": "fantasy_points_half_ppr",
        "standard": "fantasy_points",
    }.get(scoring, "fantasy_points_ppr")

    logs = defaultdict(lambda: defaultdict(dict))
    pos_map = {}
    with gzip.open(ACTUALS, "rt") as f:
        reader = csv.DictReader(f)
        for row in reader:
            pid = row["player_id"]
            pos = row.get("position", "")
            if pos not in POSITIONS:
                continue
            pos_map[pid] = pos
            season = int(row["season"])
            week = int(row["week"])
            pts = float(row.get(pts_col, 0) or 0)
            logs[pid][season][week] = pts
    return logs, pos_map


def measure_insurance_upside(teams=12, scoring="ppr", starters_per_pos=None, min_games=3):
    """Measure insurance and upside points per held backup per week."""
    if starters_per_pos is None:
        starters_per_pos = {"QB": 1, "RB": 3, "WR": 4, "TE": 1}

    logs, pos_map = load_actuals(scoring)
    sched = json.loads(SCHEDULE.read_text())

    # Accumulate per position and depth offset
    ins = defaultdict(lambda: defaultdict(float))
    ups = defaultdict(lambda: defaultdict(float))
    counts = defaultdict(lambda: defaultdict(int))

    for season_str, team_weeks in sched.items():
        season = int(season_str)
        max_week = max(max(ws) for ws in team_weeks.values())

        for w in range(1, max_week + 1):
            for pos in POSITIONS:
                S = starters_per_pos.get(pos, 1) * teams
                # Build ranked candidate list from prior PPG
                candidates = []
                for pid, seasons in logs.items():
                    if pos_map.get(pid) != pos or season not in seasons:
                        continue
                    prior = [seasons[season][wk] for wk in range(1, w) if wk in seasons[season]]
                    if len(prior) < min_games:
                        continue
                    ppg = sum(prior) / len(prior)
                    actual = seasons[season].get(w)
                    candidates.append((pid, ppg, actual))

                candidates.sort(key=lambda c: -c[1])
                if len(candidates) <= S:
                    continue

                # Find starters missing this week
                starters_missing = sum(
                    1 for i in range(min(S, len(candidates)))
                    if candidates[i][2] is None
                )

                # For each backup who played
                bench_pool = [(pid, ppg, actual) for pid, ppg, actual in candidates[S:] if actual is not None]
                bench_pool.sort(key=lambda c: -c[1])  # by prior rank

                for d, (pid, ppg, actual) in enumerate(bench_pool):
                    # Best deeper player (lower prior rank) who played
                    deeper = [a for _, _, a in bench_pool[d + 1:] if a is not None]
                    alt_pts = max(deeper) if deeper else 0.0

                    val = actual - alt_pts
                    if val <= 0:
                        counts[pos][d] += 1
                        continue

                    # Split: insurance fraction based on whether starters were missing
                    if starters_missing > 0:
                        f_ins = min(1.0, starters_missing / max(1, S // teams))
                    else:
                        f_ins = 0.0

                    ins[pos][d] += val * f_ins
                    ups[pos][d] += val * (1 - f_ins)
                    counts[pos][d] += 1

    print(f"Insurance vs upside, gross ({scoring}/{teams}-team)")
    print(f"{'Pos':>4s}  {'Depth':>5s}  {'Ins/wk':>8s}  {'Ups/wk':>8s}  {'Total':>8s}  {'Weeks':>6s}")
    for pos in POSITIONS:
        for d in range(4):
            n = counts[pos][d]
            if n == 0:
                continue
            i_rate = ins[pos][d] / n
            u_rate = ups[pos][d] / n
            print(f"{pos:>4s}  {d + 1:>5d}  {i_rate:>8.3f}  {u_rate:>8.3f}  {i_rate + u_rate:>8.3f}  {n:>6d}")
        print()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--teams", type=int, default=12)
    parser.add_argument("--scoring", default="ppr")
    args = parser.parse_args()
    measure_insurance_upside(teams=args.teams, scoring=args.scoring)


if __name__ == "__main__":
    main()
