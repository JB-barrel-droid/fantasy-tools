#!/usr/bin/env python3
"""Starts per week by depth round, from NFL game-log history.

Reproduces: finding 5 (first backup equally useful at every position;
deeper RB/WR benches justified, deeper QB/TE benches are not).

Measures how often each depth round of held players actually enters the
starting lineup, using 2015-2025 nflverse weekly actuals. "Depth round"
is defined by season-to-date PPG rank within the position among rostered
players (top S are starters; depth round 1 = first backup, etc.).

Source: 2026-10-10 bench research session (JEG-556 comments).

Usage:
    python3 tools/bench_research/depth_round_starts.py [--teams 12] [--starters QB:1,RB:2,WR:3,TE:1,FLEX:1]
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


def load_game_logs():
    """Load weekly actuals: {player_id: {season: {week: points}}}."""
    logs = defaultdict(lambda: defaultdict(dict))
    pos_map = {}
    with gzip.open(ACTUALS, "rt") as f:
        reader = csv.DictReader(f)
        for row in reader:
            pid = row["player_id"]
            pos = row.get("pos") or row.get("position", "")
            if pos not in POSITIONS:
                continue
            pos_map[pid] = pos
            season = int(row["season"])
            week = int(row["week"])
            pts = float(row.get("ppr") or row.get("fantasy_points_ppr", 0) or 0)
            logs[pid][season][week] = pts
    return logs, pos_map


def measure_starts(teams=12, starters_per_pos=None, max_depth=4, min_games=3):
    """Measure starts per week per held player by depth round."""
    if starters_per_pos is None:
        starters_per_pos = {"QB": 1, "RB": 3, "WR": 4, "TE": 1}  # with FLEX split

    logs, pos_map = load_game_logs()
    sched_raw = json.loads(SCHEDULE.read_text())
    # Handle both old format (flat {season: {team: weeks}}) and new ({seasons: {season: ...}})
    sched = sched_raw.get("seasons", sched_raw) if isinstance(sched_raw, dict) else sched_raw

    # depth_starts[pos][depth_round] = list of (started_bool,) per player-week
    depth_weeks = defaultdict(lambda: defaultdict(lambda: {"started": 0, "total": 0}))

    for season_str, team_weeks in sched.items():
        season = int(season_str)
        max_week = max(max(ws) for ws in team_weeks.values())

        for w in range(1, max_week + 1):
            # Identify players active this week with enough history
            for pos in POSITIONS:
                S = starters_per_pos.get(pos, 1) * teams
                # Players at this position who played enough games through w-1
                candidates = []
                for pid, seasons in logs.items():
                    if pos_map.get(pid) != pos:
                        continue
                    if season not in seasons:
                        continue
                    prior_games = sum(1 for wk in range(1, w) if wk in seasons[season])
                    if prior_games < min_games:
                        continue
                    prior_ppg = (
                        sum(seasons[season][wk] for wk in range(1, w) if wk in seasons[season])
                        / prior_games
                    )
                    played_this_week = w in seasons[season]
                    candidates.append((pid, prior_ppg, played_this_week))

                # Rank by prior PPG
                candidates.sort(key=lambda c: -c[1])

                # Starters are top S; depth rounds are subsequent groups of `teams` players
                for i, (pid, ppg, played) in enumerate(candidates):
                    if i < S:
                        continue  # starter
                    depth = (i - S) // teams  # depth round 0 = first backup
                    if depth >= max_depth:
                        continue
                    depth_weeks[pos][depth]["total"] += 1
                    # "Started" = a current starter at this position didn't play and
                    # this player did play. Simplified: this player played.
                    if played:
                        # Check if any starter-slot player missed
                        starters_missing = sum(
                            1 for j in range(min(S, len(candidates)))
                            if not candidates[j][2]
                        )
                        if starters_missing > 0:
                            depth_weeks[pos][depth]["started"] += 1

    print(f"Starts per week by depth round ({teams}-team, min {min_games} games)")
    print(f"{'Pos':>4s}  {'Depth':>5s}  {'Starts/wk':>10s}  {'Player-wks':>10s}")
    for pos in POSITIONS:
        for d in range(max_depth):
            total = depth_weeks[pos][d]["total"]
            started = depth_weeks[pos][d]["started"]
            rate = started / total if total > 0 else 0
            print(f"{pos:>4s}  {d + 1:>5d}  {rate:>10.3f}  {total:>10d}")
        print()


def main():
    parser = argparse.ArgumentParser(description="Depth-round starts analysis")
    parser.add_argument("--teams", type=int, default=12)
    args = parser.parse_args()
    measure_starts(teams=args.teams)


if __name__ == "__main__":
    main()
