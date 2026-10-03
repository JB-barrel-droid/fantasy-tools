#!/usr/bin/env python3
"""JEG-211: 4-group VORP totals for K and DST (computed but not displayed).

This is the K/DST analog of pipelines/build_ddf_groups.py (JEG-206). It
computes per-(position, role) totals for the four K/DST groups defined in
docs/kdst-group-contract.md:

    (K, starter)   --   top `teams` kickers by native ROS
    (K, bench)     --   next `bench_k` kickers
    (DST, starter) --   top `teams` defenses
    (DST, bench)   --   next `bench_dst` defenses

The contract is explicit that K/DST never enter the 8-group arithmetic
(`build_ddf_groups.compute_groups` raises on unknown positions). This
module is a SEPARATE artifact: dist/modules/ddf-kdst-group-vorps.json.
The 8-group artifact at dist/modules/ddf-group-vorps.json is never
read or modified by this code -- its byte-identity depends on K/DST
data being absent from the skill leg, which the upstream skill leg
already guarantees (K/DST are not in data/inputs/espn_projections.csv).

Same methodology as the 8-group artifact:
  - raw_surplus_ppg = sum(max(0, ppg - calibration[pos].rw)) for
    starter/bench rows (no rounding, no softplus).
  - total_vorp = sum(row.value) -- legacy calibrated chart value,
    retained for symmetry with the skill artifact.
  - Fail-closed on missing legs, empty groups, non-finite values,
    negative values, or group-sum vs total-mismatch.

Display marker (per docs/kdst-group-contract.md, "Display contract"):
  display_status = "computed_not_displayed"
  display_status_reason cites the contract and notes the chart
    exclude.
  excluded_from_guards = ["fixedPieIndexed", "sourceScaleAgreement"]
    (K/DST must not move skill guards).
  source_note carries the "ESPN only; no peer" caveat.

The artifact is committed under dist/ so the chart UI can (in a future
ticket) opt in to rendering it; until then, the chart UI never reads it.
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

from build_ddf_kdst_leg import (  # noqa: E402
    KDST_POSITIONS,
    SCHEMA as LEG_SCHEMA,
    utc_now as _leg_utc_now,
)

SCHEMA = "trade-value-ddf-kdst-groups-v1"
DIST_PATH = ROOT / "dist" / "modules" / "ddf-kdst-group-vorps.json"
DEFAULT_LEG_DIR = ROOT / "data" / "ddf-two-tier"
LEG_FILENAME = "ddf_leg_kdst.json"

# The 4 groups; locked by docs/kdst-group-contract.md.
GROUPS = [(pos, role) for pos in KDST_POSITIONS for role in ("starter", "bench")]
VALID_TIERS = ("starter", "bench", "waiver")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _empty_groups() -> dict[tuple[str, str], dict[str, Any]]:
    return {(pos, role): {"position": pos, "role": role,
                          "total_vorp": 0.0, "raw_surplus_ppg": 0.0,
                          "n_players": 0}
            for pos, role in GROUPS}


def find_latest_leg(leg_dir: Path = DEFAULT_LEG_DIR) -> Path:
    """Select the freshest */ddf_leg_kdst.json, by snapshot date then
    generated_at then path. Fails closed when no K/DST leg exists.
    """
    legs = sorted(leg_dir.glob(f"*/{LEG_FILENAME}"))
    if not legs:
        raise SystemExit(
            f"No K/DST DDF leg found under {leg_dir}; "
            f"run pipelines/build_ddf_kdst_leg.py first.")

    def leg_meta(p: Path) -> dict:
        try:
            doc = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            raise SystemExit(f"Fail closed: cannot read K/DST leg {p}: {e}")
        inputs = doc.get("inputs") or {}
        snap = inputs.get("snapshot_date")
        gen = doc.get("generated_at")
        if not snap or not gen:
            missing = ("snapshot_date" if not snap else "generated_at")
            raise SystemExit(
                f"Fail closed: K/DST leg {p} is missing {missing}; refusing to guess.")
        return {"path": p, "snapshot_date": str(snap),
                "generated_at": str(gen)}

    metas = [leg_meta(p) for p in legs]
    metas.sort(key=lambda m: (m["snapshot_date"], m["generated_at"], str(m["path"])))
    return metas[-1]["path"]


def compute_groups(leg: dict[str, Any]) -> dict[str, Any]:
    """Compute the 4-group totals from a K/DST DDF leg dict.

    Returns the artifact dict. Raises ValueError on fail-closed paths.
    """
    if leg.get("schema") != LEG_SCHEMA:
        raise ValueError(
            f"unsupported leg schema {leg.get('schema')!r}; expected {LEG_SCHEMA!r}")
    values = leg.get("values")
    if not isinstance(values, list):
        raise ValueError("K/DST leg is missing a `values` list")

    inputs = leg.get("inputs") or {}
    teams = inputs.get("teams")
    if not isinstance(teams, int):
        raise ValueError("K/DST leg is missing inputs.teams")

    calibration = leg.get("calibration") or {}
    waiver_ppg: dict[str, float] = {}
    for pos in KDST_POSITIONS:
        entry = calibration.get(pos)
        rw = entry.get("rw") if isinstance(entry, dict) else None
        if (isinstance(rw, bool) or not isinstance(rw, (int, float))
                or not math.isfinite(rw)):
            raise ValueError(f"missing or non-finite waiver PPG for {pos}: {rw!r}")
        waiver_ppg[pos] = float(rw)

    groups = _empty_groups()
    raw_rows: list[float] = []
    total_vorp = 0.0
    n_total = 0

    for v in values:
        pos = v.get("pos")
        tier = v.get("tier")
        value = v.get("value")
        if pos not in KDST_POSITIONS:
            raise ValueError(
                f"unknown K/DST position {pos!r} for player {v.get('player')}")
        if tier not in VALID_TIERS:
            raise ValueError(
                f"unknown tier {tier!r} for player {v.get('player')}")
        if (isinstance(value, bool) or not isinstance(value, (int, float))
                or not math.isfinite(value) or value < 0):
            raise ValueError(
                f"non-finite or negative value for player {v.get('player')}: {value!r}")
        total_vorp += float(value)
        n_total += 1
        if tier in ("starter", "bench"):
            ppg = v.get("ppg")
            if (isinstance(ppg, bool) or not isinstance(ppg, (int, float))
                    or not math.isfinite(ppg)):
                raise ValueError(
                    f"missing or non-finite projection PPG for player {v.get('player')}: {ppg!r}")
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
            "fail-closed: K/DST 4-group schema requires every group to have "
            f"at least one player; empty groups: {missing_groups}")

    sum_groups = sum(g["total_vorp"] for g in groups.values())
    raw_total = math.fsum(raw_rows)
    raw_sum_groups = math.fsum(g["raw_surplus_ppg"] for g in groups.values())
    if not all(math.isfinite(x) for x in (total_vorp, sum_groups, raw_total, raw_sum_groups)):
        raise ValueError("non-finite K/DST group aggregate")
    if not math.isclose(raw_total, raw_sum_groups, rel_tol=1e-12, abs_tol=1e-12):
        raise ValueError("raw surplus group leakage in K/DST leg")
    tol = 1e-6 * max(1.0, total_vorp)
    if abs(sum_groups - total_vorp) > tol:
        raise ValueError(
            f"K/DST group totals {sum_groups:.6f} do not sum to overall VORP "
            f"pie {total_vorp:.6f} (diff {sum_groups - total_vorp:+.6f}, "
            f"tol {tol:.6f}); leakage detected.")

    groups_list = [{"position": p, "role": r,
                    "total_vorp": round(groups[(p, r)]["total_vorp"], 4),
                    "raw_surplus_ppg": groups[(p, r)]["raw_surplus_ppg"],
                    "n_players": groups[(p, r)]["n_players"]}
                   for (p, r) in GROUPS]

    snapshot = inputs.get("snapshot_date")
    # Stale check: the 2026-09-21 pull is older than the contract's freshness
    # expectation. We surface a stale marker so any consumer that reads the
    # artifact knows the data is older than a week.
    stale_warning = False
    if snapshot:
        try:
            from datetime import date
            snap_date = date.fromisoformat(snapshot)
            age_days = (date.fromtimestamp(_leg_utc_now()) if False
                        else date.today()).toordinal() - snap_date.toordinal()
            stale_warning = age_days > 7
        except (TypeError, ValueError):
            stale_warning = False

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
        "teams": teams,
        "snapshot_date": snapshot,
        "groups": groups_list,
        "totals": {
            "total_vorp": round(total_vorp, 4),
            "sum_groups": round(sum_groups, 4),
            "raw_surplus_ppg": raw_total,
            "raw_sum_groups": raw_sum_groups,
            "n_players": n_total,
            "n_waiver": sum(1 for v in values if v.get("tier") == "waiver"),
        },
        "display_status": "computed_not_displayed",
        "display_status_reason": (
            "K/DST are computed per docs/kdst-group-contract.md but the main "
            "trade-value chart (app/trade-value-chart/) excludes them. The "
            "8-group artifact at ddf-group-vorps.json is untouched. "
            "Surface requires Jeremy's separate display design decision."
        ),
        "excluded_from_guards": ["fixedPieIndexed", "sourceScaleAgreement"],
        "source_note": (
            "ESPN projections only (no peer source to compare against; "
            "see docs/kdst-source-audit.md). K = mean weekly appliedTotal "
            "w3-18 (bye 0 included). DST = standard-scoring recipe mean "
            "w3-18. Scoring-invariant: one number per kicker/defense."
        ),
        "stale_warning": stale_warning,
        "derivation": {
            "raw_surplus": ("sum(max(0, row.ppg - calibration[position].rw)) "
                            "for starter/bench rows; no softplus, no blending"),
            "legacy_total_vorp": "sum(row.value); calibrated chart value",
            "flex_allocation": "none (K/DST do not flex)",
            "waiver_excluded": True,
            "waiver_value_zero_by_construction": True,
        },
    }


def build_groups_from_leg(leg_path: Path, out_path: Path = DIST_PATH) -> dict[str, Any]:
    input_bytes = leg_path.read_bytes()
    leg = json.loads(input_bytes)
    artifact = compute_groups(leg)
    artifact["input_leg_sha256"] = hashlib.sha256(input_bytes).hexdigest()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(artifact, indent=2, sort_keys=True,
                                   allow_nan=False) + "\n", encoding="utf-8")
    return artifact


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--leg", type=Path, default=None,
                    help="K/DST DDF leg path (default: freshest */ddf_leg_kdst.json).")
    ap.add_argument("--leg-dir", type=Path, default=DEFAULT_LEG_DIR)
    ap.add_argument("--out", type=Path, default=DIST_PATH)
    args = ap.parse_args(argv)

    leg_path = args.leg or find_latest_leg(args.leg_dir)
    artifact = build_groups_from_leg(leg_path, args.out)
    t = artifact["totals"]
    print(f"Wrote {len(artifact['groups'])} K/DST group rows -> {args.out} "
          f"(total_vorp={t['total_vorp']} sum_groups={t['sum_groups']} "
          f"n_players={t['n_players']}, display_status={artifact['display_status']})")
    for g in artifact["groups"]:
        print(f"  {g['position']:<4} {g['role']:<8} "
              f"n={g['n_players']:>3} vorp={g['total_vorp']:>10.2f} "
              f"raw_surplus_ppg={g['raw_surplus_ppg']:>8.4f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())