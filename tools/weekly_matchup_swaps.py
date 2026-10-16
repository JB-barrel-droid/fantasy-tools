#!/usr/bin/env python3
"""Matchup swaps and weekly projection spread by position (JEG-534, MR-23).

Internal measurement on the stored weekly projections
(data/inputs/weekly_projections_sleeper.csv.gz, JEG-540). Nothing user-facing.

Season rank: each season, players are ranked inside their position by the mean
of their weekly projections over regular-season weeks 1-17 (players with at
least MIN_WEEKS projected weeks). That rank is what the season curve sees.

Per position, with a 12-team league's starter count N (QB 12, RB 30, WR 30,
TE 14: the lineup slots plus the flex share) and a bench tier of the next
BENCH ranks:

  swap rate     over every projected week, the share of (bench-tier player,
                low-end starter) pairs where the bench player's projection
                that week is above the starter's. Low-end starters are the
                LOW_END ranks just inside N. Reported with the share of
                weeks in which at least one bench-tier player beats the
                lowest starter.
  weekly spread standard deviation of a player's weekly projection over its
                own mean, averaged over the starters (rank <= N). This is the
                spread of what the start decision sees, not of outcomes.

Usage: python3 tools/weekly_matchup_swaps.py [--report output/weekly-matchup-swaps.md]
"""
from __future__ import annotations

import argparse
import csv
import gzip
import statistics
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "inputs" / "weekly_projections_sleeper.csv.gz"
STARTERS = {"QB": 12, "RB": 30, "WR": 30, "TE": 14}
BENCH = 12
LOW_END = 6
MIN_WEEKS = 8
WEEKS = range(1, 18)
SCORING = "pts_ppr"


def load(path: Path = DATA) -> dict:
    """{season: {pos: {gsis_id: {week: points}}}} for regular-season weeks 1-17."""
    out: dict = defaultdict(lambda: defaultdict(lambda: defaultdict(dict)))
    with gzip.open(path, "rt") as handle:
        for row in csv.DictReader(handle):
            pos, week = row["pos"], int(row["week"])
            if pos not in STARTERS or week not in WEEKS or not row["gsis_id"] or not row[SCORING]:
                continue
            out[int(row["season"])][pos][row["gsis_id"]][week] = float(row[SCORING])
    return out


def season_ranks(players: dict) -> list:
    """Player ids ordered by mean weekly projection, best first, with enough weeks."""
    means = {p: statistics.fmean(w.values()) for p, w in players.items() if len(w) >= MIN_WEEKS}
    return sorted(means, key=lambda p: -means[p])


def measure(data: dict) -> dict:
    """{pos: {swap_pairs, pairs, weeks_any, weeks, spread: [..], seasons}}."""
    result = {pos: {"swaps": 0, "pairs": 0, "weeks_any": 0, "weeks": 0, "spread": [], "seasons": set()}
              for pos in STARTERS}
    for season, positions in data.items():
        if season >= 2026:  # the current season is incomplete: ranks would use few weeks
            continue
        for pos, players in positions.items():
            ranked = season_ranks(players)
            n = STARTERS[pos]
            if len(ranked) < n + BENCH:
                continue
            starters, bench, low_end = ranked[:n], ranked[n:n + BENCH], ranked[n - LOW_END:n]
            acc = result[pos]
            acc["seasons"].add(season)
            for p in starters:
                weekly = list(players[p].values())
                mean = statistics.fmean(weekly)
                if mean > 0 and len(weekly) > 1:
                    acc["spread"].append(statistics.pstdev(weekly) / mean)
            for week in WEEKS:
                bench_pts = [players[p][week] for p in bench if week in players[p]]
                low_pts = [players[p][week] for p in low_end if week in players[p]]
                if not bench_pts or not low_pts:
                    continue
                acc["weeks"] += 1
                acc["swaps"] += sum(b > s for b in bench_pts for s in low_pts)
                acc["pairs"] += len(bench_pts) * len(low_pts)
                acc["weeks_any"] += max(bench_pts) > min(low_pts)
    return result


def render(result: dict) -> str:
    lines = [
        "# Weekly matchup swaps and projection spread (JEG-534, MR-23)",
        "",
        f"Weekly projections ({SCORING.replace('pts_', '')}), seasons {min(min(r['seasons']) for r in result.values() if r['seasons'])}"
        f"-{max(max(r['seasons']) for r in result.values() if r['seasons'])}, weeks 1-17. 12-team starter counts "
        f"{STARTERS}; bench tier = next {BENCH} ranks; low-end starters = {LOW_END} ranks inside the cut.",
        "",
        "| Position | Pair swap rate | Weeks a bench player beats the lowest starter | Starter weekly projection spread |",
        "| -- | -- | -- | -- |",
    ]
    for pos, acc in result.items():
        if not acc["pairs"]:
            continue
        lines.append(f"| {pos} | {acc['swaps'] / acc['pairs']:.1%} | {acc['weeks_any'] / acc['weeks']:.1%} "
                     f"| {statistics.fmean(acc['spread']):.1%} |")
    lines += ["", "Swap rate: share of (bench-tier, low-end starter) pairs where the bench player's projection is higher that week.",
              "Season rank is ex post (mean of the season's weekly projections), the same view the season curve has."]
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", default=str(ROOT / "output" / "weekly-matchup-swaps.md"))
    args = parser.parse_args()
    text = render(measure(load()))
    Path(args.report).parent.mkdir(parents=True, exist_ok=True)
    Path(args.report).write_text(text)
    print(text)


if __name__ == "__main__":
    main()
