#!/usr/bin/env python3
"""JEG-209: Reweight imputed VORPs to 0-70 chart values.

Implements Jeremy's 5 decisions (2026-10-02):
1. LINEAR allocation — no squared premium. Budget share = VORP / sum(VORP).
2. BLEND reference — group budgets from the DDF blend leg's pie totals, not ESPN alone.
3. 70 ANCHOR — each source's batch max scales to 70 (all-source batch anchor).
4. INVERSIONS — within-position (bench > starter) ironed out; cross-position allowed.
5. 8-BOX CONTROLS — budgets default from pipeline, user-adjustable via --controls JSON.

Input: imputed VORP artifact from build_imputed_vorps.py
Output: chart values 0-70 per player per source (three views: Indexed, VORP, Adj Values)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

# 8 groups for budget allocation
GROUPS = [
    ("QB", "starter"), ("QB", "bench"),
    ("RB", "starter"), ("RB", "bench"),
    ("WR", "starter"), ("WR", "bench"),
    ("TE", "starter"), ("TE", "bench"),
]

DISPLAY_MAX = 70.0


def load_group_budgets(
    ddf_leg_path: Path,
    controls_path: Path | None = None,
) -> dict[tuple[str, str], float]:
    """Load 8-box budgets. Defaults from DDF blend leg pie totals.

    Decision 2: blend (not ESPN alone) as pinned economics reference.
    Decision 5: defaults from pipeline, user-adjustable via --controls JSON.
    Controls format: {"QB/starter": 123.4, ...} — overrides specific boxes.
    """
    leg = json.loads(ddf_leg_path.read_text())
    budgets = {}
    for pos, role in GROUPS:
        # DDF leg calibration: {POS: {starter_raw, bench_raw, pie}}
        cal = leg["calibration"][pos]
        key = "starter_raw" if role == "starter" else "bench_raw"
        budgets[(pos, role)] = float(cal[key])

    if controls_path:
        overrides = json.loads(controls_path.read_text())
        for k, v in overrides.items():
            pos, role = k.split("/")
            budgets[(pos, role)] = float(v)

    return budgets


def linear_reweight(
    imputed: dict[str, dict[str, Any]],
    budgets: dict[tuple[str, str], float],
) -> dict[str, float]:
    """Reweight imputed VORPs to chart values via linear allocation.

    Decision 1: LINEAR — no squared premium.
    For each group: chart_value = imputed_vorp * (budget / sum_imputed_in_group).

    This preserves within-group ordering (linear rescale is monotone).
    """
    # Group players
    groups: dict[tuple[str, str], list[str]] = {g: [] for g in GROUPS}
    for pkey, rec in imputed.items():
        pos, role = rec["group"].split("|")
        role = role.lower()
        groups[(pos, role)].append(pkey)

    result = {}
    for g, pkeys in groups.items():
        if not pkeys:
            continue
        total_imputed = sum(imputed[p]["imputed_vorp"] for p in pkeys)
        budget = budgets[g]
        if total_imputed <= 0:
            for p in pkeys:
                result[p] = 0.0
            continue
        # Linear: each player's share = their VORP / total VORP * budget
        for p in pkeys:
            result[p] = imputed[p]["imputed_vorp"] / total_imputed * budget

    return result


def iron_within_position_inversions(
    values: dict[str, float],
    imputed: dict[str, dict[str, Any]],
) -> dict[str, float]:
    """Iron out within-position inversions (bench player > starter at same position).

    Decision 4: within-position inversions are bugs, iron them out.
    Cross-position inversions (bench RB > starter TE) are legitimate economics — leave them.

    Linear rescale preserves order within (pos, role) groups, so true inversions
    should not occur. This is a safety net: if a bench player's value exceeds
    the lowest starter at the same position, clamp it.
    """
    # Group by position, separate starter/bench
    by_pos: dict[str, dict[str, list[tuple[str, float]]]] = {}
    for pkey, rec in imputed.items():
        pos, role = rec["group"].split("|")
        role = role.lower()
        by_pos.setdefault(pos, {"starter": [], "bench": []})
        by_pos[pos][role].append((pkey, values[pkey]))

    result = dict(values)
    for pos, roles in by_pos.items():
        if not roles["starter"] or not roles["bench"]:
            continue
        min_starter = min(v for _, v in roles["starter"])
        for pkey, val in roles["bench"]:
            if val > min_starter:
                # Iron out: clamp bench to just below lowest starter
                result[pkey] = min_starter * 0.999

    return result


def apply_70_anchor(
    values: dict[str, float],
) -> dict[str, float]:
    """Scale so max value = 70 (all-source batch anchor).

    Decision 3: all-source batch 70 anchor.
    Each source's batch is scaled independently so its max = 70.
    """
    if not values:
        return values
    max_v = max(values.values())
    if max_v <= 0:
        return values
    scale = DISPLAY_MAX / max_v
    return {k: round(v * scale, 1) for k, v in values.items()}


def build_three_views(
    imputed: dict[str, dict[str, Any]],
    native_values: dict[str, float],
    budgets: dict[tuple[str, str], float],
) -> dict[str, dict[str, float]]:
    """Build the three chart views.

    1. Indexed: as-published native values, no VORP logic (handled by JEG-210 toggle).
    2. VORP ("Value above waivers"): imputed VORPs in VORP units.
    3. Adj Values: reweighted to 0-70 via linear allocation + 70 anchor.
    """
    # View 2: VORP (raw imputed, no rescale)
    vorp_view = {k: rec["imputed_vorp"] for k, rec in imputed.items()}

    # View 3: Adj Values (linear reweight → iron inversions → 70 anchor)
    reweighted = linear_reweight(imputed, budgets)
    ironed = iron_within_position_inversions(reweighted, imputed)
    adj_view = apply_70_anchor(ironed)

    return {
        "indexed": native_values,  # as-published, JEG-210 handles display
        "vorp": vorp_view,
        "adj_values": adj_view,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--imputed", type=Path, required=True,
                    help="JSON from build_imputed_vorps.py")
    ap.add_argument("--ddf-leg", type=Path, required=True,
                    help="JSON: DDF blend leg calibration (for budgets)")
    ap.add_argument("--controls", type=Path, default=None,
                    help="JSON: user overrides for 8-box budgets")
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args(argv)

    imputed_raw = json.loads(args.imputed.read_text())
    # imputed format: {player_key: {group, alloc_factor, imputed_vorp, native}}
    native_values = {k: rec["native"] for k, rec in imputed_raw.items()}

    budgets = load_group_budgets(args.ddf_leg, args.controls)
    views = build_three_views(imputed_raw, native_values, budgets)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(views, indent=2, sort_keys=True))
    print(f"Wrote 3 views -> {args.out}")
    print(f"  indexed: {len(views['indexed'])} players")
    print(f"  vorp: {len(views['vorp'])} players")
    print(f"  adj_values: {len(views['adj_values'])} players, "
          f"max={max(views['adj_values'].values())}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
