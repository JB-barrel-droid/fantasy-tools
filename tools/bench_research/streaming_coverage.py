#!/usr/bin/env python3
"""Streaming coverage: best held first-round backup vs best deeper stream.

Reproduces: finding 7 (measuring waiver quality from history is circular).

This is the CIRCULAR measurement, kept as a cautionary example. Waiver
quality depends on how deep everyone else holds; assuming one backup per
team, streams match or beat held backups at RB/WR/TE (100-121%) and fall
short only at QB (84-93%), which would send every bench spot to QB. The
circularity makes it unsuitable as a bench-allocation rule.

Source: 2026-10-10 bench research session (JEG-556 comments).

Usage:
    python3 tools/bench_research/streaming_coverage.py [--teams 12]
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


def load_actuals():
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
            pts = float(row.get("fantasy_points_ppr", 0) or 0)
            logs[pid][season][week] = pts
    return logs, pos_map


def measure_streaming(teams=12, min_games=3):
    """Compare held first backup vs best waiver stream on hole weeks."""
    logs, pos_map = load_actuals()
    sched = json.loads(SCHEDULE.read_text())

    held_total = defaultdict(float)
    stream_total = defaultdict(float)
    hole_weeks = defaultdict(int)

    starters_per_pos = {"QB": 1, "RB": 3, "WR": 4, "TE": 1}

    for season_str, team_weeks in sched.items():
        season = int(season_str)
        max_week = max(max(ws) for ws in team_weeks.values())

        for w in range(1, max_week + 1):
            for pos in POSITIONS:
                S = starters_per_pos.get(pos, 1) * teams

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
                if len(candidates) <= S + teams:
                    continue

                # Check if any starter is missing (hole week)
                starters_missing = sum(
                    1 for i in range(min(S, len(candidates)))
                    if candidates[i][2] is None
                )
                if starters_missing == 0:
                    continue

                hole_weeks[pos] += 1

                # Best held first backup (ranks S to S+teams) who played
                held = candidates[S:S + teams]
                held_best = max(
                    (a for _, _, a in held if a is not None), default=0.0
                )
                held_total[pos] += held_best

                # Best stream (deeper than rostered) who played
                waiver = candidates[S + teams:]
                stream_best = max(
                    (a for _, _, a in waiver if a is not None), default=0.0
                )
                stream_total[pos] += stream_best

    print(f"Streaming coverage ({teams}-team, PPR, hole weeks only)")
    print(f"{'Pos':>4s}  {'Held avg':>10s}  {'Stream avg':>10s}  {'Coverage':>10s}  {'Holes':>6s}")
    for pos in POSITIONS:
        n = hole_weeks[pos]
        if n == 0:
            continue
        h = held_total[pos] / n
        s = stream_total[pos] / n
        cov = s / h * 100 if h > 0 else 0
        print(f"{pos:>4s}  {h:>10.2f}  {s:>10.2f}  {cov:>9.1f}%  {n:>6d}")
    print("\nNOTE: This measurement is circular. Waiver quality depends on")
    print("how deep everyone holds. See JEG-557 finding 7.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--teams", type=int, default=12)
    args = parser.parse_args()
    measure_streaming(teams=args.teams)


if __name__ == "__main__":
    main()
