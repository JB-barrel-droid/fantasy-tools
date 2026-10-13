#!/usr/bin/env python3
"""Draft composition ratios from Fantasy Football Calculator ADP, 2016-2024.

Reproduces: findings 9 (what real drafters do) and 2 (the final bench rule:
bench spots proportional to starters x measured backups per starter).

FFC 12-team PPR listed players by position (QB, RB, WR, TE, PK, DEF).
Computes per-team drafted counts, backups per starter, and the bench-mix
weights that the chosen rule uses.

Source: 2026-10-10 bench research session (JEG-556 -> JEG-557 kdef.py).

Usage:
    python3 tools/bench_research/draft_composition.py [--rounds 15]
"""
from __future__ import annotations

import argparse
import statistics
from pathlib import Path

# FFC 12-team PPR listed players by position: (QB, RB, WR, TE, PK, DEF)
# 2022 was truncated and excluded from the original analysis
FFC = {
    2016: (24, 57, 65, 17, 11, 14),
    2018: (25, 60, 65, 18, 14, 15),
    2020: (24, 65, 66, 19, 14, 15),
    2024: (26, 60, 72, 20, 14, 12),
}
POS6 = ("QB", "RB", "WR", "TE", "K", "DEF")
POS4 = ("QB", "RB", "WR", "TE")
TEAMS = 12


def compute_ratios(rounds=15):
    """Compute draft composition shares and backups-per-starter ratios."""
    # Average share across years
    shares = [
        statistics.mean(c[i] / sum(c) for c in FFC.values())
        for i in range(6)
    ]
    per_team = [s * rounds for s in shares]

    # Default starters: 1 QB, 2 RB, 2 WR, 1 TE, 1 FLEX (split RB/WR), K, DEF
    starters = {"QB": 1, "RB": 2.5, "WR": 2.5, "TE": 1, "K": 1, "DEF": 1}
    ratios = {p: (pt - starters[p]) / starters[p] for p, pt in zip(POS6, per_team)}

    print(f"Draft composition: FFC 12-team PPR, {rounds}-round drafts")
    print(f"\n{'Year':>6s}  " + "  ".join(f"{p:>5s}" for p in POS6) + "  Total")
    for year, counts in sorted(FFC.items()):
        total = sum(counts)
        print(f"{year:>6d}  " + "  ".join(f"{c:>5d}" for c in counts) + f"  {total:>5d}")

    print(f"\nAverage shares:")
    for p, s in zip(POS6, shares):
        print(f"  {p:4s}  {s * 100:5.1f}%")

    print(f"\nPer team ({rounds} rounds):")
    for p, pt in zip(POS6, per_team):
        print(f"  {p:4s}  {pt:5.2f}")

    print(f"\nBackups per starter (the bench-mix ratio):")
    for p in POS6:
        print(f"  {p:4s}  {ratios[p]:5.2f}")

    # Skill-only (no K/DEF) for the scorecard
    skill_per_team = [s * 13 for s in shares[:4]]  # 13 skill players per team
    skill_ratios = {
        p: (pt - starters[p]) / starters[p]
        for p, pt in zip(POS4, skill_per_team)
    }
    print(f"\nSkill-only ratios (13 players/team, for scorecard):")
    for p in POS4:
        print(f"  {p:4s}  {skill_ratios[p]:5.2f}")

    # Per-year stability
    print(f"\nPer-year shares (stability check):")
    for i, p in enumerate(POS4):
        year_shares = [c[i] / sum(c) * 100 for c in FFC.values()]
        print(f"  {p:4s}  " + "  ".join(f"{s:5.1f}%" for s in year_shares)
              + f"  range {max(year_shares) - min(year_shares):.1f}pp")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--rounds", type=int, default=15)
    args = parser.parse_args()
    compute_ratios(rounds=args.rounds)


if __name__ == "__main__":
    main()
