#!/usr/bin/env python3
"""Measure promotion and demotion rates from NFL game-log history.

Promotion: a player ranked as bench (by season-to-date PPG, rank > S_p)
in week W who is ranked as a starter (rank <= S_p) by the end of the season.

Demotion: a player ranked as a starter in week W who ends the season ranked
as bench or worse.

By week of season: how rates change as the season progresses (fewer remaining
weeks for role changes to occur).

Source: 2015-2025 nflverse weekly actuals.
JEG-969: bench share promotion/demotion model.

Usage:
    python3 tools/bench_research/promotion_demotion_rates.py [--teams 12] [--scoring ppr]
"""
from __future__ import annotations

import argparse
import csv
import gzip
import json
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
POSITIONS = ("QB", "RB", "WR", "TE")
ACTUALS = REPO / "data" / "inputs" / "weekly_actuals_nflverse_2015_2025.csv.gz"

# Default starters per position at 12-team (with flex: RB gets ~3, WR gets ~4)
DEFAULT_STARTERS = {"QB": 12, "RB": 27, "WR": 33, "TE": 12}
# Also rostered counts for bench tier
DEFAULT_ROSTERED = {"QB": 27, "RB": 55, "WR": 68, "TE": 18}

SEASON_WEEKS = 18  # NFL regular season weeks (post-2021)


def load_weekly_actuals(scoring: str = "ppr"):
    """Load weekly actuals: {(season, player_id): {week: points}, pos_of}."""
    weekly = defaultdict(dict)
    pos_of = {}
    with gzip.open(ACTUALS, "rt") as f:
        reader = csv.DictReader(f)
        for row in reader:
            pid = row["player_id"]
            pos = row.get("pos", "")
            if pos not in POSITIONS:
                continue
            pos_of[pid] = pos
            season = int(row["season"])
            week = int(row["week"])
            pts = float(row.get(scoring, 0) or 0)
            weekly[(season, pid)][week] = pts
    return weekly, pos_of


def season_to_date_rankings(weekly, pos_of, season, through_week, teams=12,
                             starters=None):
    """Rank players by season-to-date PPG through a given week.

    Returns {pos: [(player_id, ppg, rank, tier)]} where tier is
    'starter', 'bench', or 'waiver'.
    """
    if starters is None:
        starters = DEFAULT_STARTERS

    # Compute STD PPG for each player active this season through this week
    ppg_by_pos = defaultdict(list)
    for (s, pid), weeks in weekly.items():
        if s != season:
            continue
        pos = pos_of.get(pid)
        if pos not in POSITIONS:
            continue
        games = [pts for w, pts in weeks.items() if w <= through_week]
        if not games:
            continue
        avg = sum(games) / len(games)
        ppg_by_pos[pos].append((pid, avg, len(games)))

    rankings = {}
    for pos in POSITIONS:
        # Sort by PPG descending
        ranked = sorted(ppg_by_pos[pos], key=lambda x: (-x[1], x[0]))
        s_count = starters.get(pos, 12)
        r_count = DEFAULT_ROSTERED.get(pos, s_count * 2)
        result = []
        for i, (pid, ppg, games) in enumerate(ranked):
            rank = i + 1
            if rank <= s_count:
                tier = "starter"
            elif rank <= r_count:
                tier = "bench"
            else:
                tier = "waiver"
            result.append((pid, ppg, rank, tier))
        rankings[pos] = result
    return rankings


def measure_transitions(weekly, pos_of, scoring="ppr", teams=12,
                        starters=None, min_games=3):
    """Measure promotion and demotion rates by week of season.

    For each week W (1 through 17), measures:
    - How many bench players at week W become starters by end of season
    - How many starters at week W become bench by end of season
    - Rates by position and backup depth
    """
    if starters is None:
        starters = DEFAULT_STARTERS

    seasons = sorted(set(s for (s, _) in weekly.keys()))
    # Only use seasons with 17+ weeks (post-2021 has 18 weeks)
    # Pre-2021 seasons have 16-17 weeks; use whatever is available

    results = defaultdict(lambda: defaultdict(lambda: {
        "promoted": 0, "stayed_bench": 0, "demoted": 0, "stayed_starter": 0,
        "bench_total": 0, "starter_total": 0,
        "promoted_by_depth": defaultdict(int), "bench_by_depth": defaultdict(int),
    }))

    for season in seasons:
        # Determine max week for this season
        max_week = max(w for (s, pid), wks in weekly.items()
                       for w in wks if s == season)

        for check_week in range(1, max_week):
            end_week = max_week

            # Ranking at check_week
            rank_at_w = season_to_date_rankings(weekly, pos_of, season, check_week,
                                                 teams, starters)
            # Ranking at end of season
            rank_at_end = season_to_date_rankings(weekly, pos_of, season, end_week,
                                                   teams, starters)

            # Build lookup for end-of-season tier
            end_tier = {}
            for pos in POSITIONS:
                for pid, ppg, rank, tier in rank_at_end.get(pos, []):
                    end_tier[pid] = (pos, tier, rank)

            for pos in POSITIONS:
                for pid, ppg, rank, tier in rank_at_w.get(pos, []):
                    end_info = end_tier.get(pid)
                    if end_info is None:
                        continue  # player disappeared
                    end_pos, end_t, end_rank = end_info
                    if end_pos != pos:
                        continue  # position changed (rare)

                    s_count = starters.get(pos, 12)
                    depth = rank - s_count  # depth 1 = first backup

                    r = results[check_week][pos]
                    if tier == "bench":
                        r["bench_total"] += 1
                        r["bench_by_depth"][depth] += 1
                        if end_t == "starter":
                            r["promoted"] += 1
                            r["promoted_by_depth"][depth] += 1
                        else:
                            r["stayed_bench"] += 1
                    elif tier == "starter":
                        r["starter_total"] += 1
                        if end_t != "starter":
                            r["demoted"] += 1
                        else:
                            r["stayed_starter"] += 1

    return results


def format_results(results, max_week=17):
    """Format the results as markdown tables."""
    lines = []
    lines.append("# Promotion and demotion rates by week of season")
    lines.append("")
    lines.append("## Overall rates by week")
    lines.append("")
    lines.append("| Week | Pos | Bench | Promoted | Promo rate | Starters | Demoted | Demo rate |")
    lines.append("|---|---|---|---|---|---|---|---|")

    for week in range(1, max_week + 1):
        if week not in results:
            continue
        for pos in POSITIONS:
            r = results[week][pos]
            if r["bench_total"] == 0 and r["starter_total"] == 0:
                continue
            promo_rate = r["promoted"] / r["bench_total"] if r["bench_total"] else 0
            demo_rate = r["demoted"] / r["starter_total"] if r["starter_total"] else 0
            lines.append(f"| {week} | {pos} | {r['bench_total']} | {r['promoted']} | "
                        f"{100*promo_rate:.1f}% | {r['starter_total']} | {r['demoted']} | "
                        f"{100*demo_rate:.1f}% |")

    # Summary by position (average over weeks 1-8, 9-17)
    lines.append("")
    lines.append("## Summary: promotion rate by position and season phase")
    lines.append("")
    lines.append("| Position | Weeks 1-4 | Weeks 5-8 | Weeks 9-12 | Weeks 13-17 |")
    lines.append("|---|---|---|---|---|")
    for pos in POSITIONS:
        phases = []
        for start, end in [(1, 4), (5, 8), (9, 12), (13, 17)]:
            total_bench = sum(results[w][pos]["bench_total"] for w in range(start, end + 1) if w in results)
            total_promo = sum(results[w][pos]["promoted"] for w in range(start, end + 1) if w in results)
            rate = total_promo / total_bench if total_bench else 0
            phases.append(f"{100*rate:.1f}%")
        lines.append(f"| {pos} | {' | '.join(phases)} |")

    # Promotion by depth
    lines.append("")
    lines.append("## Promotion rate by backup depth (all weeks)")
    lines.append("")
    lines.append("| Position | Depth 1 | Depth 2 | Depth 3 | Depth 4+ |")
    lines.append("|---|---|---|---|---|")
    for pos in POSITIONS:
        depths = []
        for d in [1, 2, 3]:
            total = sum(results[w][pos]["bench_by_depth"][d] for w in results)
            promo = sum(results[w][pos]["promoted_by_depth"][d] for w in results)
            rate = promo / total if total else 0
            depths.append(f"{100*rate:.1f}%")
        # Depth 4+
        total_4p = sum(results[w][pos]["bench_by_depth"].get(d, 0)
                       for w in results for d in results[w][pos]["bench_by_depth"] if d >= 4)
        promo_4p = sum(results[w][pos]["promoted_by_depth"].get(d, 0)
                       for w in results for d in results[w][pos]["promoted_by_depth"] if d >= 4)
        rate_4p = promo_4p / total_4p if total_4p else 0
        depths.append(f"{100*rate_4p:.1f}%")
        lines.append(f"| {pos} | {' | '.join(depths)} |")

    # Demotion summary
    lines.append("")
    lines.append("## Demotion rate by position and season phase")
    lines.append("")
    lines.append("| Position | Weeks 1-4 | Weeks 5-8 | Weeks 9-12 | Weeks 13-17 |")
    lines.append("|---|---|---|---|---|")
    for pos in POSITIONS:
        phases = []
        for start, end in [(1, 4), (5, 8), (9, 12), (13, 17)]:
            total_s = sum(results[w][pos]["starter_total"] for w in range(start, end + 1) if w in results)
            total_d = sum(results[w][pos]["demoted"] for w in range(start, end + 1) if w in results)
            rate = total_d / total_s if total_s else 0
            phases.append(f"{100*rate:.1f}%")
        lines.append(f"| {pos} | {' | '.join(phases)} |")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Promotion/demotion rates from NFL history")
    parser.add_argument("--teams", type=int, default=12)
    parser.add_argument("--scoring", default="ppr", choices=["standard", "half_ppr", "ppr"])
    args = parser.parse_args()

    weekly, pos_of = load_weekly_actuals(args.scoring)
    results = measure_transitions(weekly, pos_of, args.scoring, args.teams)
    max_week = max(results.keys()) if results else 17
    print(format_results(results, min(max_week, 17)))


if __name__ == "__main__":
    main()
