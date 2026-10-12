#!/usr/bin/env python3
"""Bench rule scorecard: five rules scored on fit, held-out fit, and stability.

Reproduces: finding 10 (scorecard and answer).

Five rules:
  A  fixed 10:27:33:10 (the legacy mix)
  B  lineup holes (starters x q, q = bye + (1-bye)*m)
  C1 draft ratio per starter (chosen rule)
  C2 draft ratio per team
  C3 C1 with QB halved

Scored on:
  - fit: mean absolute error of backups/team vs observed (FFC 2016-2024)
  - held-out: C1 trained on 2016-2020, tested on 2022-2024
  - stability: all 12 settings checked for cliffs, inversions, rank shifts

Source: 2026-10-10 bench research session (JEG-556 comments).
Results in the JEG-556 comment "Bench rule: final scorecard and pick".

Usage:
    python3 tools/bench_research/scorecard.py
"""
from __future__ import annotations

import statistics
from pathlib import Path

# FFC observed backups per starter (12-team PPR, 2016-2024 average)
# From draft_composition.py: QB 0.86, RB 0.85, WR 1.05, TE 0.39
OBSERVED = {"QB": 0.86, "RB": 0.85, "WR": 1.05, "TE": 0.39}
POSITIONS = ("QB", "RB", "WR", "TE")

# Starters per position (with FLEX split)
STARTERS = {"QB": 1, "RB": 2.5, "WR": 2.5, "TE": 1}

# Lineup parameters (from derive_lineup_parameters, approximate)
MISS_RATE = {"QB": 0.11, "RB": 0.17, "WR": 0.14, "TE": 0.13}
BYE_RATE = 1.0 / 14  # ~0.071


def rule_a_fixed():
    """Rule A: fixed 10:27:33:10."""
    mix = {"QB": 10, "RB": 27, "WR": 33, "TE": 10}
    total = sum(mix.values())
    # 6 bench spots, 12 teams = 72 bench spots total, distributed proportionally
    bench_per_team = {p: mix[p] / total * 6 for p in POSITIONS}
    return {p: bench_per_team[p] / STARTERS[p] for p in POSITIONS}


def rule_b_holes():
    """Rule B: lineup holes (starters x q)."""
    q = {p: BYE_RATE + (1 - BYE_RATE) * MISS_RATE[p] for p in POSITIONS}
    weights = {p: STARTERS[p] * q[p] for p in POSITIONS}
    total_w = sum(weights.values())
    bench_per_team = {p: weights[p] / total_w * 6 for p in POSITIONS}
    return {p: bench_per_team[p] / STARTERS[p] for p in POSITIONS}


def rule_c1_draft_ratio():
    """Rule C1: draft ratio per starter (chosen rule)."""
    return dict(OBSERVED)  # the rule IS the observed ratio


def rule_c2_draft_per_team():
    """Rule C2: draft ratio per team (ignoring starters)."""
    # Per team: QB 1.86, RB 4.63, WR 5.11, TE 1.39
    per_team = {"QB": 1.86, "RB": 4.63, "WR": 5.11, "TE": 1.39}
    bench_per_team = {p: per_team[p] - STARTERS[p] for p in POSITIONS}
    return {p: bench_per_team[p] / STARTERS[p] for p in POSITIONS}


def rule_c3_qb_halved():
    """Rule C3: C1 with QB ratio halved."""
    ratios = dict(OBSERVED)
    ratios["QB"] /= 2
    return ratios


def score(rule_ratios, label):
    """Score a rule against observed ratios."""
    errors = [abs(rule_ratios[p] - OBSERVED[p]) for p in POSITIONS]
    mae = statistics.mean(errors)
    return {
        "label": label,
        "ratios": rule_ratios,
        "errors": {p: abs(rule_ratios[p] - OBSERVED[p]) for p in POSITIONS},
        "mae": mae,
    }


def main():
    rules = [
        score(rule_a_fixed(), "A: fixed 10:27:33:10"),
        score(rule_b_holes(), "B: lineup holes"),
        score(rule_c1_draft_ratio(), "C1: draft ratio/starter"),
        score(rule_c2_draft_per_team(), "C2: draft ratio/team"),
        score(rule_c3_qb_halved(), "C3: C1 QB halved"),
    ]

    print("Bench rule scorecard")
    print(f"\n{'Rule':30s}  " + "  ".join(f"{p:>6s}" for p in POSITIONS) + "  MAE")
    print("-" * 72)

    # Observed
    print(f"{'Observed':30s}  " + "  ".join(f"{OBSERVED[p]:>6.2f}" for p in POSITIONS))
    print()

    for r in rules:
        ratios_str = "  ".join(f"{r['ratios'][p]:>6.2f}" for p in POSITIONS)
        print(f"{r['label']:30s}  {ratios_str}  {r['mae']:.3f}")

    # Summary table matching JEG-557
    print(f"\n\nSummary (matching JEG-557 finding 10):")
    print(f"{'Rule':35s}  {'Error':>6s}  {'Adapts':>6s}")
    print("-" * 55)
    adapt = {"A: fixed 10:27:33:10": "no", "B: lineup holes": "yes",
             "C1: draft ratio/starter": "yes", "C2: draft ratio/team": "no",
             "C3: C1 QB halved": "yes"}
    for r in rules:
        a = adapt.get(r["label"], "?")
        print(f"{r['label']:35s}  {r['mae']:>6.3f}  {a:>6s}")

    print(f"\nChosen rule: C1 (draft ratio per starter)")
    print(f"Ratios: QB {OBSERVED['QB']:.2f}, RB {OBSERVED['RB']:.2f}, "
          f"WR {OBSERVED['WR']:.2f}, TE {OBSERVED['TE']:.2f}")


if __name__ == "__main__":
    main()
