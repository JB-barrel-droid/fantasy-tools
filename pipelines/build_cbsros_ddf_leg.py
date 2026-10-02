#!/usr/bin/env python3
"""Build the DDF two-tier value-above-waivers leg from CBS rest-of-season projections.

CBS-ROS analog of pipelines/build_ddf_two_tier_leg.py (ESPN). The two-tier
MATH is not duplicated here -- every pricing function is imported from
build_ddf_two_tier_leg (softplus, slice_exposures, solve_tier_prices,
build_position_tiers, calibrate_position, price_for_projection,
bench_mix_for_teams). Only the INPUT layer differs:

  - ESPN reads data/inputs/espn_projections.csv (ROS components, fixed
    divisor 16). CBS reads data/raw/sources/cbsros/<date>/snapshot.json
    (ROS totals + per-player gp; per-game = ROS / gp).
  - CBS publishes nonppr totals only; half_ppr/ppr are CBS fpts + 0.5/1.0
    per reception (reception points are the only scoring difference --
    same rescoring pattern as the ESPN leg).
  - Pies are measured from the current CBS data (tier surplus), never from
    a stale file. The ESPN leg's pies file is vintage reference only since
    2026-09-29; the CBS leg skips the file entirely and records the
    measurement method in the leg metadata.

CBS-purity: every number labeled CBS ROS comes from CBS's ROS projections
only. Per-game projections are arithmetic on CBS components. Identity is
numeric player_key via the fixture's player_keys map (same verified ALIASES
as the ESPN leg). Unresolvable identities go to review_rows, never guessed.

Output: data/ddf-two-tier/<bake_id>/ddf_leg_cbsros.json
  bake_id = ddf-<YYYYMMDD>-cbsros-<scoring>-<teams>t-0p15
The filename is deliberately NOT ddf_leg.json: several ESPN-path tools glob
*/ddf_leg.json (build_adjustment_inputs.find_leg, build_espn_raw_values,
build_espn_section_from_ddf_leg, build_index_math.verify_espn). A CBS leg
named ddf_leg.json would poison those globs.

Fail-closed: infeasible calibration at the requested bench share falls back
to the max feasible share per position (same as the ESPN leg and the UI's
bounded slider); a non-positive pie, a position with no surplus, or no
positive raw value publishes NO leg.
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
from build_ddf_two_tier_leg import (  # noqa: E402 -- the shared math, not duplicated
    ALIASES,
    BENCH_MIX_12,
    DEFAULT_BENCH_SHARE,
    POSITIONS,
    REF_FLEX_COUNT,
    REF_FLEX_ELIGIBLE,
    REF_SLOTS,
    bench_mix_for_teams,
    build_position_tiers,
    calibrate_position,
    price_for_projection,
)

SCHEMA = "trade-value-ddf-leg-v1"
SOURCE_TAG = "cbsros"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "ddf-two-tier"

SCORING_PG = {
    "standard": "per_game_standard",
    "half_ppr": "per_game_half_ppr",
    "ppr": "per_game_ppr",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_cbsros_lists(snapshot_path: Path, scoring: str, fixture_path: Path):
    """Return (resolved, review_rows, aliases_used, meta).

    resolved: {pos: [{player_key, player_norm, player, pos, team, x: per-game}]}.
    Identity join is fixture player_keys on the snapshot's normalized name,
    with the shared verified ALIASES. Unresolvable -> review, never guessed.
    """
    if scoring not in SCORING_PG:
        raise SystemExit(f"Unknown scoring '{scoring}'")
    snap = json.loads(snapshot_path.read_text(encoding="utf-8"))
    vintage = snap.get("vintage_date")
    if not vintage:
        raise SystemExit("Fail closed: CBS ROS snapshot has no vintage_date.")
    pg_key = SCORING_PG[scoring]
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    player_keys = fixture.get("player_keys") or {}

    resolved: dict[str, list[dict[str, Any]]] = {pos: [] for pos in POSITIONS}
    review: list[dict[str, Any]] = []
    aliases_used: list[dict[str, Any]] = []
    for row in snap.get("rows", []):
        name = str(row.get("player_name") or "").strip()
        norm = str(row.get("player_norm") or "").strip()
        pos = str(row.get("pos") or "").strip()
        if not name or not norm:
            review.append({"reason": "missing_name", "row": {k: row.get(k) for k in ("pos", "team")}})
            continue
        if pos not in POSITIONS:
            review.append({"reason": "non_skill_position", "player": name, "pos": pos})
            continue
        x = row.get(pg_key)
        if not isinstance(x, (int, float)) or not math.isfinite(x):
            review.append({"reason": "missing_per_game", "player": name, "pos": pos})
            continue
        key = player_keys.get(norm)
        alias = None
        if key is None and norm in ALIASES:
            alias = ALIASES[norm]
            key = player_keys.get(alias)
        if not isinstance(key, int):
            review.append({"reason": "unresolved_identity", "player": name,
                           "player_norm": norm, "pos": pos})
            continue
        if alias:
            aliases_used.append({"cbsros_norm": norm, "canonical_id": alias,
                                 "player_key": key})
        resolved[pos].append({
            "player_key": key,
            "player_norm": norm,
            "player": name,
            "pos": pos,
            "team": str(row.get("team") or "").strip() or None,
            "gp": row.get("gp"),
            "x": float(x),
        })
    meta = {"cbsros_vintage_date": vintage,
            "snapshot_rows": len(snap.get("rows", [])),
            "snapshot_review_rows": len(snap.get("review_rows", []))}
    return resolved, review, aliases_used, meta


def build_leg(snapshot_path: Path, fixture_path: Path,
              scoring: str, teams: int, bench_share: float) -> dict[str, Any]:
    resolved, review_rows, aliases_used, snap_meta = load_cbsros_lists(
        snapshot_path, scoring, fixture_path)

    # JEG-67 (reverts JEG-52 pool cap): the cap was a value no-op. Discrimination
    # test (2026-10-02) on real snapshots proved capping the pool at 3x starters
    # changed zero shared values and left calibration byte-identical, while
    # dropping 100+ players per source from leg outputs. The surplus sums only
    # players above the waiver line, and the waiver line is set by the fixed
    # roster shape -- deep tails below it never inflated anything. Every
    # resolved player is priced (tails below the line price to exactly 0.0).

    pool_lists = {pos: [{"id": d["player_key"], "x": d["x"]} for d in resolved[pos]]
                  for pos in POSITIONS}
    pool = build_position_tiers(pool_lists, teams, dict(REF_SLOTS), REF_FLEX_COUNT,
                                list(REF_FLEX_ELIGIBLE), bench_mix_for_teams(teams))
    calibration: dict[str, Any] = {}
    calibration_notes = []
    for pos in POSITIONS:
        tier = pool["tiers"][pos]
        # Pies are measured from the current CBS data (tier surplus), never a
        # stale file. The surplus IS the CBS-measured pie for this dataset.
        pie = tier["surplus"] if tier else 0
        feasible_share = bench_share
        try:
            calibration[pos] = calibrate_position(tier, pie, feasible_share)
        except ValueError as e:
            if "economics break" in str(e) or "does not exceed" in str(e):
                lo, hi = 0.01, bench_share
                best = None
                for _ in range(20):
                    mid = (lo + hi) / 2
                    try:
                        test_cal = calibrate_position(tier, pie, mid)
                        best = (mid, test_cal)
                        lo = mid
                    except ValueError:
                        hi = mid
                if best:
                    feasible_share, calibration[pos] = best
                    calibration_notes.append(
                        f"{pos}: bench share {bench_share} infeasible, using {feasible_share:.3f}")
                else:
                    raise
            else:
                raise

    raw: dict[int, float] = {}
    for pos in POSITIONS:
        cal = calibration[pos]
        for d in resolved[pos]:
            raw[d["player_key"]] = price_for_projection(d["x"], cal)
    mx = max(raw.values()) if raw else 0.0
    if not (mx > 0):
        raise SystemExit("Fail closed: CBS ROS leg has no positive raw value; nothing to normalize.")
    scale = 70.0 / mx

    # 85/15 pie identity, verified pre-rounding (the locked guarantee).
    for pos in POSITIONS:
        cal = calibration[pos]
        pie = cal.get("pie_used")
        share_used = cal.get("bench_share_used", bench_share)
        if abs(cal["bench_raw"] - share_used * pie) > 1e-9 * pie or \
           abs(cal["starter_raw"] - (1 - share_used) * pie) > 1e-9 * pie:
            raise SystemExit(f"Fail closed: {pos} pie identity broken pre-rounding.")

    values = []
    for pos in POSITIONS:
        for d in resolved[pos]:
            key = d["player_key"]
            tier = ("starter" if key in pool["starters"]
                    else ("bench" if key in pool["bench"] else "waiver"))
            values.append({
                "player_key": key,
                "player_norm": d["player_norm"],
                "player": d["player"],
                "pos": pos,
                "team": d["team"],
                "ppg": d["x"],
                "tier": tier,
                "raw_value": raw[key],
                "value": raw[key] * scale,
            })
    values.sort(key=lambda v: (-v["value"], v["player_key"]))

    bake_id = (f"ddf-{snap_meta['cbsros_vintage_date'].replace('-', '')}-{SOURCE_TAG}-"
               f"{scoring}-{teams}t-{str(bench_share).replace('.', 'p')}")
    return {
        "schema": SCHEMA,
        "bake_id": bake_id,
        "generated_at": utc_now(),
        "inputs": {
            "cbsros_snapshot": str(snapshot_path),
            "cbsros_snapshot_sha256": sha256_file(snapshot_path),
            "cbsros_snapshot_date": snap_meta["cbsros_vintage_date"],
            "cbsros_snapshot_rows": snap_meta["snapshot_rows"],
            "per_game_note": ("per-game = CBS ROS total / gp (per-player games). "
                              "CBS publishes nonppr totals only; half_ppr/ppr add "
                              "0.5/1.0 per reception (reception points are the only "
                              "scoring difference). Arithmetic on CBS components "
                              "only; no expert blending."),
            "pies_note": ("Positional pies measured from the current CBS data "
                          "(tier surplus). No pies file: a static file goes stale "
                          "when the player pool changes."),
            "scoring": scoring,
            "teams": teams,
            "bench_share": bench_share,
            "source_tag": SOURCE_TAG,
        },
        "reference_shape": {
            "slots": REF_SLOTS, "flex_count": REF_FLEX_COUNT,
            "flex_eligible": REF_FLEX_ELIGIBLE,
            "bench_mix": bench_mix_for_teams(teams),
        },
        "calibration": {
            pos: {
                "rw": c["rw"], "rs": c["rs"], "tau": c["tau"], "pie": c.get("pie_used"),
                "pb": c["pb"], "ps": c["ps"],
                "bench_share_used": c.get("bench_share_used", bench_share),
                "n_starters": sum(1 for d in resolved[pos] if d["player_key"] in pool["starters"]),
                "n_bench": sum(1 for d in resolved[pos] if d["player_key"] in pool["bench"]),
                "n_pool": len(resolved[pos]),
                "bench_raw": c["bench_raw"], "starter_raw": c["starter_raw"],
            } for pos, c in calibration.items()
        },
        "scale_70_over_max": scale,
        "max_raw_value": mx,
        "identity": {
            "aliases_used": aliases_used,
            "alias_note": ("Shared verified alias map with the ESPN DDF leg "
                           "(build_ddf_two_tier_leg.ALIASES). Unresolvable "
                           "identities are excluded, never guessed."),
        },
        "values": values,
        "review_rows": review_rows,
        "summary": {
            "n_values": len(values),
            "n_review": len(review_rows),
            "n_starters": sum(1 for v in values if v["tier"] == "starter"),
            "n_bench": sum(1 for v in values if v["tier"] == "bench"),
            "n_waiver": sum(1 for v in values if v["tier"] == "waiver"),
            "calibration_notes": calibration_notes,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True,
                        help="data/raw/sources/cbsros/<date>/snapshot.json")
    parser.add_argument("--fixture", type=Path,
                        default=ROOT / "data" / "fixtures" / "current" / "comparison-sources-data.json")
    parser.add_argument("--scoring", default="ppr", help="standard | half_ppr | ppr")
    parser.add_argument("--teams", type=int, default=12)
    parser.add_argument("--bench-share", type=float, default=DEFAULT_BENCH_SHARE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    for path in (args.snapshot, args.fixture):
        if not path.is_file():
            raise SystemExit(f"Input not found: {path}")

    leg = build_leg(args.snapshot, args.fixture, args.scoring, args.teams, args.bench_share)
    out_dir = args.output_dir / leg["bake_id"]
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "ddf_leg_cbsros.json"
    out_path.write_text(json.dumps(leg, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    summary = leg["summary"]
    print(f"Built CBS ROS DDF leg {leg['bake_id']}: {summary['n_values']} values "
          f"({summary['n_starters']} starters / {summary['n_bench']} bench / "
          f"{summary['n_waiver']} waiver), {summary['n_review']} review -> {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
