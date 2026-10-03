#!/usr/bin/env python3
"""JEG-182: 8-group proportional imputed VORP (JEG-180 methodology).

For each as-published source (FantasyCalc, USA Today, FantasyPros, CBS):
1. Infer roster: flex = top flex-eligible non-starters by value; bench = top remaining.
2. For each of 8 groups: alloc_factor = our_group_VORP / sum(publisher_values_in_group).
3. Imputed VORP = published_value * alloc_factor.

Our group VORPs come from JEG-206 (pipelines/build_ddf_groups.py).
This is the production implementation of the Option C Sheet logic.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

# 8 groups: (position, role). Flex maps to Starter.
GROUPS = [
    ("QB", "starter"), ("QB", "bench"),
    ("RB", "starter"), ("RB", "bench"),
    ("WR", "starter"), ("WR", "bench"),
    ("TE", "starter"), ("TE", "bench"),
]

FLEX_ELIGIBLE = ("RB", "WR", "TE")

# Standard roster: 12 teams, 1 QB / 2 RB / 3 WR / 1 TE / 1 flex / 6 bench
TEAMS = 12
DEDICATED = {"QB": 1, "RB": 2, "WR": 3, "TE": 1}
FLEX_PER_TEAM = 1
BENCH_PER_TEAM = 6


def infer_roster(
    values: dict[str, tuple[str, float]],
) -> dict[str, str]:
    """Infer role (starter/bench) for each player from publisher values.

    values: {player_key: (position, published_value)}
    Returns: {player_key: "starter" | "bench"}

    Logic (matches Option C Sheet):
    - Dedicated starters: top N per position by value (N = teams * slots).
    - Flex: top flex-eligible non-starters by value (12 total).
    - Bench: top remaining by value (72 total).
    - Flex maps to "starter" for the 8-group model.
    """
    # Sort by value descending
    ranked = sorted(values.items(), key=lambda kv: kv[1][1], reverse=True)

    roles: dict[str, str] = {}
    dedicated_done: dict[str, int] = {pos: 0 for pos in DEDICATED}
    flex_pool: list[tuple[str, float]] = []

    # First pass: dedicated starters
    for pkey, (pos, val) in ranked:
        need = TEAMS * DEDICATED.get(pos, 0)
        if dedicated_done.get(pos, 0) < need:
            roles[pkey] = "starter"
            dedicated_done[pos] = dedicated_done.get(pos, 0) + 1
        elif pos in FLEX_ELIGIBLE:
            flex_pool.append((pkey, val))
        # else: not rostered (cut)

    # Second pass: flex (top flex-eligible non-starters)
    flex_pool.sort(key=lambda kv: kv[1], reverse=True)
    n_flex = TEAMS * FLEX_PER_TEAM
    for pkey, _ in flex_pool[:n_flex]:
        roles[pkey] = "starter"  # flex maps to starter

    # Third pass: bench (top remaining)
    remaining = [
        (pkey, val) for pkey, (pos, val) in ranked
        if pkey not in roles
    ]
    remaining.sort(key=lambda kv: kv[1], reverse=True)
    n_bench = TEAMS * BENCH_PER_TEAM
    for pkey, _ in remaining[:n_bench]:
        roles[pkey] = "bench"

    return roles


def compute_imputed_vorps(
    values: dict[str, tuple[str, float]],
    our_group_vorps: dict[tuple[str, str], float],
) -> dict[str, dict[str, Any]]:
    """Compute imputed VORP per player via 8-group proportional allocation.

    values: {player_key: (position, published_value)}
    our_group_vorps: {(position, role): total_vorp} from JEG-206

    Returns: {player_key: {"group": "POS|role", "alloc_factor": float,
                           "imputed_vorp": float, "native": float}}
    """
    roles = infer_roster(values)

    # Sum publisher values per group
    group_sums: dict[tuple[str, str], float] = {
        g: 0.0 for g in GROUPS
    }
    for pkey, (pos, val) in values.items():
        role = roles.get(pkey)
        if role is None:
            continue  # cut player
        group_sums[(pos, role)] += val

    # Allocation factor per group
    alloc: dict[tuple[str, str], float] = {}
    for g in GROUPS:
        s = group_sums[g]
        if s > 0:
            alloc[g] = our_group_vorps[g] / s
        else:
            alloc[g] = 0.0

    # Imputed VORP per player
    result = {}
    for pkey, (pos, val) in values.items():
        role = roles.get(pkey)
        if role is None:
            continue
        g = (pos, role)
        result[pkey] = {
            "group": f"{pos}|{role.title()}",
            "alloc_factor": round(alloc[g], 6),
            "imputed_vorp": round(val * alloc[g], 2),
            "native": val,
        }
    return result


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--values", type=Path, required=True,
                    help="JSON: {player_key: [position, published_value]}")
    ap.add_argument("--group-vorps", type=Path, required=True,
                    help="JSON: JEG-206 output (dist/modules/ddf-group-vorps.json)")
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args(argv)

    values_raw = json.loads(args.values.read_text())
    values = {k: (v[0], float(v[1])) for k, v in values_raw.items()}

    gv_raw = json.loads(args.group_vorps.read_text())
    our_vorps = {
        (g["position"], g["role"]): float(g["total_vorp"])
        for g in gv_raw["groups"]
    }

    result = compute_imputed_vorps(values, our_vorps)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, sort_keys=True))
    print(f"Wrote {len(result)} imputed VORPs -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
