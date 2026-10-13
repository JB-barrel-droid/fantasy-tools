#!/usr/bin/env python3
"""Net-of-waivers bench value from NFL game-log history.

Reproduces: finding 6 (net of waivers, QB/TE upside disappears; a bench
spot is worth only 0-0.5 points per week).

For each backup set into a lineup, compares against the best player
available on waivers that week (a player deeper than all rostered players
who played that week). This is the realistic alternative: not hindsight-
optimal, but the best pickup a manager could make.

Source: 2026-10-10 bench research session (JEG-556 comments, waiver_rule.py core loop).

Usage:
    python3 tools/bench_research/waiver_rule.py [--teams 12] [--scoring ppr]
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

BIG = 999


def load_actuals(scoring="ppr"):
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


def measure_net_of_waivers(teams=12, scoring="ppr", starters_per_pos=None, min_games=3):
    """Measure net value of holding a backup vs picking up the best waiver option."""
    if starters_per_pos is None:
        starters_per_pos = {"QB": 1, "RB": 3, "WR": 4, "TE": 1}

    logs, pos_map = load_actuals(scoring)
    sched = json.loads(SCHEDULE.read_text())

    ins = defaultdict(lambda: defaultdict(float))
    ups = defaultdict(lambda: defaultdict(float))
    counts = defaultdict(lambda: defaultdict(int))

    for season_str, team_weeks in sched.items():
        season = int(season_str)
        max_week = max(max(ws) for ws in team_weeks.values())

        for w in range(1, max_week + 1):
            for pos in POSITIONS:
                S = starters_per_pos.get(pos, 1) * teams
                rostered = S + teams  # assume ~1 backup per team for waiver boundary

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

                # Rostered backups and waiver pool
                bench = candidates[S:rostered]
                waiver_pool = candidates[rostered:]

                # Best waiver pickup who played this week (not hindsight: by prior rank)
                best_waiver = None
                for pid, ppg, actual in waiver_pool:
                    if actual is not None:
                        best_waiver = actual
                        break

                starters_missing = sum(
                    1 for i in range(min(S, len(candidates)))
                    if candidates[i][2] is None
                )

                for d, (pid, ppg, actual) in enumerate(bench):
                    if actual is None:
                        counts[pos][d] += 1
                        continue

                    alt = best_waiver if best_waiver is not None else 0.0
                    val = actual - alt
                    if val <= 0:
                        counts[pos][d] += 1
                        continue

                    if starters_missing > 0:
                        f_ins = min(1.0, starters_missing / max(1, S // teams))
                    else:
                        f_ins = 0.0

                    ins[pos][d] += val * f_ins
                    ups[pos][d] += val * (1 - f_ins)
                    counts[pos][d] += 1

    print(f"Net-of-waivers bench value ({scoring}/{teams}-team)")
    print(f"{'Pos':>4s}  {'Depth':>5s}  {'Ins/wk':>8s}  {'Ups/wk':>8s}  {'Net/wk':>8s}  {'Weeks':>6s}")
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
    measure_net_of_waivers(teams=args.teams, scoring=args.scoring)


if __name__ == "__main__":
    main()
