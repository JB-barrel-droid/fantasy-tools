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
import math
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


def _nonnegative_finite(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label}: expected finite nonnegative number")
    try:
        number = float(value)
    except (OverflowError, ValueError) as exc:
        raise ValueError(f"{label}: number out of range") from exc
    if not math.isfinite(number) or number < 0:
        raise ValueError(f"{label}: expected finite nonnegative number")
    return number


def _validate_values(values):
    if not isinstance(values, dict):
        raise ValueError("values must be a player-key mapping")
    for key, row in values.items():
        if not isinstance(row, (list, tuple)) or len(row) != 2 or not isinstance(row[0], str) or row[0] not in DEDICATED:
            raise ValueError(f"player {key}: expected skill position and native value")
        _nonnegative_finite(row[1], f"player {key} native")


def _finite_sum(values, label):
    try:
        total = math.fsum(values)
    except OverflowError as exc:
        raise ValueError(f"{label}: aggregate overflow") from exc
    return _nonnegative_finite(total, label)


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


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
    _validate_values(values)
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
    if not isinstance(our_group_vorps, dict) or set(our_group_vorps) != set(GROUPS):
        raise ValueError("group targets must contain exactly the eight skill position/role groups")
    targets = {g: _nonnegative_finite(our_group_vorps[g], f"target {g}") for g in GROUPS}
    roles = infer_roster(values)

    # Sum publisher values per group
    group_sums: dict[tuple[str, str], float] = {
        g: [] for g in GROUPS
    }
    for pkey, (pos, val) in values.items():
        role = roles.get(pkey)
        if role is None:
            continue  # cut player
        group_sums[(pos, role)].append(val)

    # Allocation factor per group
    alloc: dict[tuple[str, str], float] = {}
    for g in GROUPS:
        s = _finite_sum(group_sums[g], f"native sum {g}")
        if s == 0 and targets[g] > 0:
            raise ValueError(f"infeasible group {g}: positive target without positive native pool")
        alloc[g] = _nonnegative_finite(targets[g] / s if s else 0.0, f"factor {g}")

    # Imputed VORP per player
    result = {}
    for pkey, (pos, val) in values.items():
        role = roles.get(pkey)
        if role is None:
            continue
        g = (pos, role)
        imputed = _nonnegative_finite(val * alloc[g], f"imputed {pkey}")
        result[pkey] = {
            "group": f"{pos}|{role.title()}",
            "alloc_factor": alloc[g],
            "imputed_vorp": imputed,
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

    values = json.loads(args.values.read_text(), object_pairs_hook=_unique_object)

    gv_raw = json.loads(args.group_vorps.read_text(), object_pairs_hook=_unique_object)
    if not isinstance(gv_raw, dict) or not isinstance(gv_raw.get("groups"), list):
        raise ValueError("group artifact must have a groups list")
    our_vorps = {}
    for row in gv_raw["groups"]:
        if not isinstance(row, dict) or not {"position", "role", "total_vorp"}.issubset(row):
            raise ValueError("malformed group target row")
        group = row["position"], row["role"]
        if group not in GROUPS or group in our_vorps:
            raise ValueError(f"unknown or duplicate group target: {group}")
        our_vorps[group] = row["total_vorp"]

    result = compute_imputed_vorps(values, our_vorps)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))
    print(f"Wrote {len(result)} imputed VORPs -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
