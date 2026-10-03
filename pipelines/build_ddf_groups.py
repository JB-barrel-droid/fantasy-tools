#!/usr/bin/env python3
"""JEG-206/233: eight-group totals with explicit raw-vs-calibrated units.

JEG-233 adds raw_surplus_ppg using ppg minus waiver; total_vorp remains the
legacy sum of calibrated row.value for compatibility. units and derivation
identify each quantity. Raw consumers must use raw_surplus_contract and
raw_surplus_ppg, never total_vorp. Raw inputs fail closed when unavailable.

Legacy artifact contract follows:

Refactor target: emit total VORP per (position x role) for the eight groups
    QB Starter, QB Bench,RB Starter, RB Bench, WR Starter, WR Bench,
    TE Starter, TE Bench
  where
    Starter = dedicated starters + flex (who start each week), per the
    tier classification in build_ddf_two_tier_leg.build_position_tiers.
    Bench = bench-tier players only.
    The waiver tier (below the bench line) is NOT one of the eight groups;
    waiver players price to 0 by construction, so excluding them does not
    leak value from the pie.

Inputs:
  A DDF two-tier leg (pipelines/build_ddf_two_tier_leg.build_leg output)
  whose `values` array carries {pos, tier, value, raw_value, ppg, ... per
  player. The DDF leg's `tier` field already implements the starter/bench/
  waiver split that the flex allocation requires (the flex pool is added
  to `pool["starters"]`, not pooled into a separate flex bucket).

Output:
  dist/modules/ddf-group-vorps.json with shape:
    {
      "schema": "trade-value-ddf-groups-v1",
      "generated_at": "...",
      "bake_id": "<from leg>",
      "scoring": "...",
      "teams": 12,
      "roster": {slots, flex_count, flex_eligible, bench_mix},
      "groups": [
        {position, role, total_vorp, n_players}, ... 8 rows
      ],
      "totals": {total_vorp, sum_groups, n_players}
    }
  The 8 group totals must sum to total_vorp (no leakage). The function
  fails closed when:
    * the leg lacks the expected schema/values block
    * any of the 8 groups is empty (a position with zero players)
    * sum(groups) != sum(all values) to within 1e-6 tolerance
    * a player has an unknown position or tier

Wired into pipelines/sync_dashboard_artifacts.py via build_groups_from_leg
 + main() so the artifact is rewritten on every bake alongside the rest
 of dist/modules/*.json. No cron; the bake's existing sync step drives it.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))

from build_ddf_two_tier_leg import (  # noqa: E402
    POSITIONS,
    REF_FLEX_COUNT,
    REF_FLEX_ELIGIBLE,
    REF_SLOTS,
    bench_mix_for_teams,
    utc_now as _leg_utc_now,
)

SCHEMA = "trade-value-ddf-groups-v1"
DIST_PATH = ROOT / "dist" / "modules" / "ddf-group-vorps.json"
DEFAULT_LEG_DIR = ROOT / "data" / "ddf-two-tier"
LEG_FILENAME = "ddf_leg.json"

# The 8 groups; locked by JEG-206. Order is position x role (QB before RB
# before WR before TE; starter before bench within each position).
GROUPS = [(pos, role) for pos in POSITIONS for role in ("starter", "bench")]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _empty_groups() -> dict[tuple[str, str], dict[str, Any]]:
    return {(pos, role): {"position": pos, "role": role,
                          "total_vorp": 0.0, "raw_surplus_ppg": 0.0, "n_players": 0}
            for pos, role in GROUPS}


def find_latest_leg(leg_dir: Path = DEFAULT_LEG_DIR) -> Path:
    """Select the freshest */ddf_leg.json, by content vintage then generated_at
    then path. Same selection logic build_adjustment_inputs uses, so the
    groups artifact tracks the leg the rest of the bake consumes.
    Raises SystemExit (fail-closed) when no leg exists.
    """
    legs = sorted(leg_dir.glob(f"*/{LEG_FILENAME}"))
    if not legs:
        raise SystemExit(
            f"No DDF leg found under {leg_dir}; run pipelines/build_ddf_two_tier_leg.py first.")

    def leg_meta(p: Path) -> dict:
        try:
            doc = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            raise SystemExit(f"Fail closed: cannot read DDF leg {p}: {e}")
        inputs = doc.get("inputs") or {}
        snap = inputs.get("espn_snapshot_date")
        gen = doc.get("generated_at")
        if not snap or not gen:
            missing = "espn_snapshot_date" if not snap else "generated_at"
            raise SystemExit(
                f"Fail closed: DDF leg {p} is missing {missing}; refusing to guess.")
        return {"path": p, "snapshot_date": str(snap), "generated_at": str(gen)}

    metas = [leg_meta(p) for p in legs]
    metas.sort(key=lambda m: (m["snapshot_date"], m["generated_at"], str(m["path"])))
    return metas[-1]["path"]


def compute_groups(leg: dict[str, Any]) -> dict[str, Any]:
    """Compute the 8-group totals from a DDF leg dict.

    Returns the artifact dict. Raises ValueError on fail-closed paths so the
    CLI surfaces a clear error and the bake stops (matching the leg's own fail-closed style).
    """
    if leg.get("schema") != "trade-value-ddf-leg-v1":
        raise ValueError(
            f"unsupported leg schema {leg.get('schema')!r}; expected 'trade-value-ddf-leg-v1'")
    values = leg.get("values")
    if not isinstance(values, list):
        raise ValueError("leg is missing a `values` list")

    inputs = leg.get("inputs") or {}
    scoring = inputs.get("scoring")
    teams = inputs.get("teams")
    if not scoring or not isinstance(teams, int):
        raise ValueError("leg is missing inputs.scoring or inputs.teams")

    bench_mix = bench_mix_for_teams(teams)
    n_dedicated = {pos: teams * REF_SLOTS.get(pos, 0) for pos in POSITIONS}
    n_flex_target = teams * REF_FLEX_COUNT

    calibration = leg.get("calibration") or {}
    waiver_ppg = {}
    for pos in POSITIONS:
        entry = calibration.get(pos)
        rw = entry.get("rw") if isinstance(entry, dict) else None
        if isinstance(rw, bool) or not isinstance(rw, (int, float)) or not math.isfinite(rw):
            raise ValueError(f"missing or non-finite waiver PPG for {pos}: {rw!r}")
        waiver_ppg[pos] = float(rw)

    groups = _empty_groups()
    raw_rows = []
    total_vorp = 0.0
    n_total = 0
    seen_positions: set[str] = set()
    seen_tiers: set[str] = set()

    for v in values:
        pos = v.get("pos")
        tier = v.get("tier")
        value = v.get("value")
        if pos not in POSITIONS:
            raise ValueError(f"unknown position {pos!r} for player {v.get('player')}")
        if tier not in ("starter", "bench", "waiver"):
            raise ValueError(f"unknown tier {tier!r} for player {v.get('player')}")
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
            raise ValueError(f"non-finite or negative value for player {v.get('player')}: {value!r}")
        seen_positions.add(pos)
        seen_tiers.add(tier)
        total_vorp += float(value)
        n_total += 1
        if tier in ("starter", "bench"):
            ppg = v.get("ppg")
            if isinstance(ppg, bool) or not isinstance(ppg, (int, float)) or not math.isfinite(ppg):
                raise ValueError(f"missing or non-finite projection PPG for player {v.get('player')}: {ppg!r}")
            raw = max(0.0, float(ppg) - waiver_ppg[pos])
            if not math.isfinite(raw):
                raise ValueError("raw surplus overflow")
            raw_rows.append(raw)
            g = groups[(pos, tier)]
            g["raw_surplus_ppg"] += raw
            g["total_vorp"] += float(value)
            g["n_players"] += 1

    missing_groups = [f"{p}/{r}" for (p, r) in GROUPS
                      if groups[(p, r)]["n_players"] == 0]
    if missing_groups:
        raise ValueError(
            "fail-closed: 8-group schema requires every group to have at least one player; "
            f"empty groups: {missing_groups}")

    sum_groups = sum(g["total_vorp"] for g in groups.values())
    raw_total = math.fsum(raw_rows)
    raw_sum_groups = math.fsum(g["raw_surplus_ppg"] for g in groups.values())
    if not all(math.isfinite(x) for x in (total_vorp, sum_groups, raw_total, raw_sum_groups)):
        raise ValueError("non-finite group aggregate")
    if not math.isclose(raw_total, raw_sum_groups, rel_tol=1e-12, abs_tol=1e-12):
        raise ValueError("raw surplus group leakage")
    tol = 1e-6 * max(1.0, total_vorp)
    if abs(sum_groups - total_vorp) > tol:
        raise ValueError(
            f"group totals {sum_groups:.6f} do not sum to overall VORP pie {total_vorp:.6f} "
            f"(diff {sum_groups - total_vorp:+.6f}, tol {tol:.6f}); leakage detected.")

    #Derive the flex count actually used by the leg so the artifact shows the
    # same number of flex slots (VORP-weighted allocation may produce different
    # per-position flex totals; we report the target, which matches the locked
    # roster shape).
    groups_list = [{"position": p, "role": r,
                    "total_vorp": round(groups[(p, r)]["total_vorp"], 4),
                    "raw_surplus_ppg": groups[(p, r)]["raw_surplus_ppg"],
                    "n_players": groups[(p, r)]["n_players"]}
                   for (p, r) in GROUPS]

    n_flex_by_pos = {}
    for pos in POSITIONS:
        n_flex_by_pos[pos] = groups[(pos, "starter")]["n_players"] - n_dedicated[pos]

    return {
        "schema": SCHEMA,
        "raw_surplus_contract": "ddf-raw-surplus-ppg-v1",
        "units": {
            "total_vorp": "legacy_calibrated_chart_value",
            "sum_groups": "legacy_calibrated_chart_value",
            "raw_surplus_ppg": "fantasy_points_per_game_above_position_waiver",
            "raw_sum_groups": "fantasy_points_per_game_above_position_waiver",
        },
        "source_generated_at": leg.get("generated_at"),
        "source_inputs": inputs,
        "waiver_ppg": waiver_ppg,
        "generated_at": utc_now(),
        "bake_id": leg.get("bake_id"),
        "scoring": scoring,
        "teams": teams,
        "espn_snapshot_date": inputs.get("espn_snapshot_date"),
        "roster": {
            "slots": REF_SLOTS,
            "flex_count": REF_FLEX_COUNT,
            "flex_eligible": list(REF_FLEX_ELIGIBLE),
            "bench_mix": bench_mix,
        },
        "groups": groups_list,
        "totals": {
            "total_vorp": round(total_vorp, 4),
            "sum_groups": round(sum_groups, 4),
            "raw_surplus_ppg": raw_total,
            "raw_sum_groups": raw_sum_groups,
            "n_players": n_total,
            "n_waiver": sum(1 for v in values if v.get("tier") == "waiver"),
        },
        "derivation": {
            "raw_surplus": "sum(max(0, row.ppg - calibration[position].rw)) for starter/bench rows; no legacy value/raw_value or softplus",
            "legacy_total_vorp": "sum(row.value); retained for existing consumers, not raw VORP PPG",
            "flex_allocation": "highest-vorp at margin (see build_ddf_two_tier_leg.build_position_tiers)",
            "waiver_excluded": True,
            "waiver_value_zero_by_construction": True,
        },
    }


def build_groups_from_leg(leg_path: Path, out_path: Path = DIST_PATH) -> dict[str, Any]:
    """Build the 8-group artifact from a specific DDF leg path.

    The sync step uses this; tests use compute_groups + a fixture leg.
    """
    input_bytes = leg_path.read_bytes()
    leg = json.loads(input_bytes)
    artifact = compute_groups(leg)
    artifact["input_leg_sha256"] = hashlib.sha256(input_bytes).hexdigest()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(artifact, indent=2, sort_keys=True, allow_nan=False) + "\n",
                        encoding="utf-8")
    return artifact


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--leg", type=Path, default=None,
                    help="DDF leg path (default: freshest */ddf_leg.json).")
    ap.add_argument("--leg-dir", type=Path, default=DEFAULT_LEG_DIR)
    ap.add_argument("--out", type=Path, default=DIST_PATH)
    args = ap.parse_args(argv)

    leg_path = args.leg or find_latest_leg(args.leg_dir)
    artifact = build_groups_from_leg(leg_path, args.out)
    t = artifact["totals"]
    print(f"Wrote {len(artifact['groups'])} group rows -> {args.out} "
          f"(total_vorp={t['total_vorp']} sum_groups={t['sum_groups']} "
          f"n_players={t['n_players']})")
    for g in artifact["groups"]:
        print(f"  {g['position']:<2} {g['role']:<8} "
              f"n={g['n_players']:>3} vorp={g['total_vorp']:>10.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())