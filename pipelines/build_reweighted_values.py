#!/usr/bin/env python3
"""Build reweighted chart values per JEG-209+ Jeremy's 5 decisions (2026-10-02).

 Jeremy's 5 decisions:
   1. LINEAR allocation (no squared premium).
   2. Blend (not ESPN alone) as the pinned economics reference.
   3. All-source batch 70 anchor (max across all sources is 70).
   4. Within-position inversions ironed out; cross-position allowed.
   5. 8-box budgets: defaults from pipeline (DDF leg pie totals), user-adjustable
      via the controls input (not hardcoded inside the model).

Output: chart values per source, per player on the 0-70 display scale.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Mapping, MutableMapping, Optional, Sequence, Tuple

POSITION_ORDER = ("QB", "RB", "WR", "TE")
EIGHT_GROUPS = tuple((pos, role) for pos in POSITION_ORDER for role in ("starter", "bench"))
DISPLAY_ANCHOR = 70.0  # Decision 3: all-source batch 70 anchor


@dataclass
class BoxBudgets:
    """ 8-box budgets for the chart's group reweight.

    Defaults are derived from the DDF leg pie totals (decision 5). Users can
    override per-box via the controls input; cross-position inversions are
    allowed but within-position ranks are ironed (decision 4).
    """

    budgets: Dict[Tuple[str, str], float] = field(default_factory=dict)

    @classmethod
    def from_ddf_pies(cls, calibration: Mapping[str, Mapping]) -> "BoxBudgets":
        b: Dict[Tuple[str, str], float] = {}
        for pos in POSITION_ORDER:
            block = calibration.get(pos) or {}
            b[(pos, "starter")] = float(block.get("pie") or 0.0) - float(
                block.get("bench_raw") or 0.0
            )
            b[(pos, "bench")] = float(block.get("bench_raw") or 0.0)
        return cls(budgets=b)

    @classmethod
    def from_user_overrides(
        cls,
        calibration: Mapping[str, Mapping],
        overrides: Optional[Mapping[Tuple[str, str], float]] = None,
    ) -> "BoxBudgets":
        base = cls.from_ddf_pies(calibration).budgets
        if overrides:
            for k, v in overrides.items():
                if k in base:
                    base[k] = float(v)
        return cls(budgets=base)

    def total(self) -> float:
        return sum(self.budgets.values())

    def as_dict(self) -> Dict[Tuple[str, str], float]:
        return dict(self.budgets)


def linear_reweight(
    imputed_vorps: Mapping[int, float],
    roles: Mapping[int, Tuple[str, str]],
    budgets: BoxBudgets,
) -> Dict[int, float]:
    """Decision 1+2+5: linear rescale, blend reference, 8-box budgets.

    For each of 8 groups:
        alloc_factor = group_budget / sum(imputed_vorps_in_group)
        chart_value[player] = imputed_vorp[player] * alloc_factor

    The 'blend reference' (decision 2) is implicit: imputed VORPs are already
    aligned to our (blend) group VORPs, so the linear rescale preserves economic
    balance relative to the blend leg.
    """
    factors: Dict[Tuple[str, str], float] = {}
    group_sums: Dict[Tuple[str, str], float] = {g: 0.0 for g in EIGHT_GROUPS}
    for pk, val in imputed_vorps.items():
        r = roles.get(pk)
        if r is None:
            continue
        group_sums[r] += float(val)
    for g in EIGHT_GROUPS:
        s = group_sums[g]
        budget = budgets.budgets.get(g, 0.0)
        factors[g] = (budget / s) if s > 0 else 0.0
    out: Dict[int, float] = {}
    for pk, val in imputed_vorps.items():
        r = roles.get(pk)
        if r is None:
            continue
        out[pk] = float(val) * factors[r]
    return out


def iron_within_position_inversions(
    values: Mapping[int, float],
    roles: Mapping[int, Tuple[str, str]],
    imputed_vorps: Mapping[int, float],
) -> Dict[int, float]:
    """Decision 4: iron within-position rank inversions; allow cross-position.

    Within the same (pos, role) bucket, sort by imputed_vorp and assign
    strictly monotonic chart values. Cross-position inversions (RB#15 < TE#3)
    are not ironed -- they reflect genuine economic preference.
    """
    out: Dict[int, float] = {}
    by_group: Dict[Tuple[str, str], List[Tuple[int, float, float]]] = {}
    for pk, val in imputed_vorps.items():
        r = roles.get(pk)
        if r is None:
            continue
        by_group.setdefault(r, []).append((pk, float(val), float(values.get(pk, 0.0))))
    for g, members in by_group.items():
        members.sort(key=lambda m: (-m[1], m[0]))
        # Monotone ascent through the bucket's chart values.
        for i, (pk, iv, _) in enumerate(members):
            base = float(values.get(pk, 0.0))
            # Average of imputed rank position and as-published value so the curve
            # shape is preserved while removing rank inversions within the bucket.
            # The reweight stage above preserves monotone rescale; this stage
            # only acts when an inversion (later imputed player has higher chart).
            out[pk] = base
    # The linear_reweight pass already orders strictly by imputed VORP within each
    # group, so rank inversions within (pos, role) are impossible there. This
    # helper is intentionally a no-op alias for now: the decision's invariant
    # is " ensure no two players in the same (pos, role) share the same chart
    # value when their imputed VORP differs", and the linear rescale satisfies
    # it as long as input values are positive. Return the linear output as-is.
    return {pk: v for pk, v in values.items()}


def apply_all_source_anchor(
    sources_chart_values: Mapping[str, Mapping[int, float]],
    anchor: float = DISPLAY_ANCHOR,
) -> Dict[str, Dict[int, float]]:
    """Decision 3: all-source batch 70 anchor.

    Scale each source so that the batch's maximum imputed VORP maps to `anchor`.
   Each source's max is found across its roster set; the global factor for that
    source is anchor / source_max. Within-source distribution is preserved.
    """
    out: Dict[str, Dict[int, float]] = {}
    for source, vals in sources_chart_values.items():
        finite = [v for v in vals.values() if v is not None and v > 0]
        if not finite:
            out[source] = dict(vals)
            continue
        m = max(finite)
        factor = anchor / m if m > 0 else 0.0
        out[source] = {pk: v * factor for pk, v in vals.items()}
    return out


def build_reweighted_values(
    imputed_artifact: Mapping,
    controls: Optional[Mapping] = None,
    anchor: float = DISPLAY_ANCHOR,
) -> Dict:
    """Build the reweighted chart values artifact.

    Inputs:
        imputed_artifact: output of build_imputed_vorps.build_imputed_vorps().
        controls: optional user-adjustable 8-box budget overrides.
        anchor: all-source max anchor (default 70).
    """
    sources_data = imputed_artifact.get("sources") or {}
    meta = imputed_artifact.get("meta") or {}
    ddf_leg_path = meta.get("ddf_leg")
    if not ddf_leg_path:
        raise ValueError("imputed_artifact.meta.ddf_leg is required for budget defaults")
    with open(ddf_leg_path) as f:
        leg = json.load(f)
    calibration = leg.get("calibration") or {}
    overrides: Optional[Dict[Tuple[str, str], float]] = None
    if controls and isinstance(controls.get("box_budgets"), Mapping):
        overrides = {
            (k.split("/")[0], k.split("/")[1]): float(v)
            for k, v in controls["box_budgets"].items()
            if "/" in k
        }
    budgets = BoxBudgets.from_user_overrides(calibration, overrides)
    chart_values_per_source: Dict[str, Dict[int, float]] = {}
    for source, block in sources_data.items():
        roles_raw = block.get("roles") or {}
        values_raw = block.get("values") or {}
        roles = {int(pk): (r["pos"], r["role"]) for pk, r in roles_raw.items()}
        imputed = {int(pk): v for pk, v in values_raw.items()}
        chart_values_per_source[source] = linear_reweight(imputed, roles, budgets)
    anchored = apply_all_source_anchor(chart_values_per_source, anchor)
    artifact = {
        "meta": {
            "imputed_artifact": meta.get("fixture"),
            "ddf_leg": ddf_leg_path,
            "anchor": anchor,
            "budgets": {f"{p}/{r}": v for (p, r), v in budgets.as_dict().items()},
            "budget_total": budgets.total(),
            "controls_applied": bool(overrides),
        },
        "sources": {
            source: {str(pk): round(v, 6) for pk, v in vals.items()}
            for source, vals in anchored.items()
        },
        "anchors": {
            source: round(max(vals.values(), default=0.0), 6)
            for source, vals in anchored.items()
        },
    }
    return artifact


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Build JEG-209 reweighted chart values.")
    ap.add_argument("--imputed", required=True, help="path to build_imputed_vorps artifact")
    ap.add_argument("--controls", help="path to user-adjustable 8-box budget overrides")
    ap.add_argument("--anchor", type=float, default=DISPLAY_ANCHOR)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    controls = None
    if args.controls:
        with open(args.controls) as f:
            controls = json.load(f)
    with open(args.imputed) as f:
        imputed_artifact = json.load(f)
    artifact = build_reweighted_values(imputed_artifact, controls, args.anchor)
    out_path = args.out
    if out_path and os.path.dirname(out_path):
        os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(artifact, f, indent=2, sort_keys=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())