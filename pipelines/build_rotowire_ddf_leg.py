#!/usr/bin/env python3
"""Build the DDF two-tier value-above-waivers leg from RotoWire projections.

RotoWire analog of pipelines/build_cbsros_ddf_leg.py. The two-tier MATH is
not duplicated here -- every pricing function is imported from
build_ddf_two_tier_leg. Only the INPUT layer differs:

  - CBS reads data/raw/sources/cbsros/<date>/snapshot.json (ROS totals +
    per-player gp; per-game = ROS / gp).
  - RotoWire reads data/inputs/weekly_projections_sleeper.csv.gz (per-week
    projections via Sleeper) and data/inputs/sleeper_projection_idmap.csv
    (sleeper_id -> player_key mapping). Per-game PPG is the average of
    remaining-week projections (weeks >= current_week through 18) for the
    current season.
  - Each scoring column maps directly: pts_ppr, pts_half_ppr, pts_std.
  - Pies are measured from the current RotoWire data (tier surplus), never
    from a stale file (same approach as CBS ROS).

Identity: sleeper_id -> player_key via sleeper_projection_idmap.csv (only
status='matched' or 'gsis_not_in_players'). player_key -> player_norm via
the fixture's reversed player_keys dict. Unresolvable identities go to
review_rows, never guessed.

Output: data/ddf-two-tier/<bake_id>/ddf_leg_rotowire.json
  bake_id = ddf-<YYYYMMDD>-rotowire-<scoring>-<teams>t-0p15

Fail-closed: same rules as the CBS leg (infeasible calibration, non-positive
pie, no surplus, no positive raw value -> NO leg).
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import math
import sys
from collections import defaultdict
from datetime import datetime, date, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))
import projection_identity  # noqa: E402
from build_ddf_two_tier_leg import (  # noqa: E402 -- the shared math, not duplicated
    FixtureIdentity,
    write_leg_json,
    drop_duplicate_keys,
    identity_review_row,
    DEFAULT_BENCH_SHARE,
    POSITIONS,
    REF_FLEX_COUNT,
    REF_FLEX_ELIGIBLE,
    REF_SLOTS,
    bench_mix_for_teams,
    build_position_tiers,
    calibrate_feasible,
    calibrate_position,
    price_for_projection,
)

SCHEMA = "trade-value-ddf-leg-v1"
SOURCE_TAG = "rotowire"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "ddf-two-tier"
DEFAULT_WEEKLY = ROOT / "data" / "inputs" / "weekly_projections_sleeper.csv.gz"
DEFAULT_IDMAP = ROOT / "data" / "inputs" / "sleeper_projection_idmap.csv"
DEFAULT_FIXTURE = ROOT / "data" / "fixtures" / "current" / "comparison-sources-data.json"

SCORING_COL = {
    "standard": "pts_std",
    "half_ppr": "pts_half_ppr",
    "ppr": "pts_ppr",
}

# Current NFL season.
CURRENT_SEASON = 2026
# Default current week if not in fixture.
DEFAULT_CURRENT_WEEK = 7


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_sleeper_idmap(idmap_path: Path) -> dict[str, dict[str, Any]]:
    """Load sleeper_projection_idmap.csv -> {sleeper_id: {player_key, pos, ...}}.

    Only rows with status 'matched' or 'gsis_not_in_players' are included.
    """
    result: dict[str, dict[str, Any]] = {}
    with open(idmap_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            status = (row.get("status") or "").strip()
            if status not in ("matched", "gsis_not_in_players"):
                continue
            sleeper_id = str(row.get("sleeper_id") or "").strip()
            if not sleeper_id:
                continue
            pk_raw = row.get("player_key", "").strip()
            if not pk_raw:
                continue
            try:
                player_key = int(pk_raw)
            except ValueError:
                continue
            result[sleeper_id] = {
                "player_key": player_key,
                "name": (row.get("name") or "").strip(),
                "pos": (row.get("pos") or "").strip(),
            }
    return result


def load_rotowire_ppg(
    weekly_path: Path,
    idmap_path: Path,
    fixture_path: Path,
    scoring: str,
    current_week: int,
) -> tuple[dict[str, list[dict[str, Any]]], list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    """Return (resolved, review_rows, aliases_used, meta).

    resolved: {pos: [{player_key, player_norm, player, pos, team, x: per-game PPG}]}.
    Per-game PPG = average of remaining-week projections (weeks >= current_week
    through 18) for the current season.
    """
    if scoring not in SCORING_COL:
        raise SystemExit(f"Unknown scoring '{scoring}'")
    pts_col = SCORING_COL[scoring]

    # Load the idmap: sleeper_id -> player_key (+ pos, name)
    idmap = load_sleeper_idmap(idmap_path)

    # Build reverse map: player_key -> player_norm from fixture
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    player_keys = fixture.get("player_keys") or {}
    key_to_norm: dict[int, str] = {}
    for slug, key in player_keys.items():
        if isinstance(key, int):
            key_to_norm.setdefault(key, slug)

    # Read weekly projections and accumulate per-player remaining-week points
    # Structure: {sleeper_id: {weeks: [pts...], name, pos, team}}
    player_weeks: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"weeks": [], "name": "", "pos": "", "team": ""}
    )

    with gzip.open(weekly_path, "rt", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            season_str = (row.get("season") or "").strip()
            if not season_str:
                continue
            try:
                season = int(season_str)
            except ValueError:
                continue
            if season != CURRENT_SEASON:
                continue
            try:
                week = int(row.get("week", "0"))
            except ValueError:
                continue
            if week < current_week or week > 18:
                continue
            sleeper_id = str(row.get("sleeper_id") or "").strip()
            if not sleeper_id:
                continue
            pts_raw = (row.get(pts_col) or "").strip()
            if not pts_raw:
                continue
            try:
                pts = float(pts_raw)
            except ValueError:
                continue
            if not math.isfinite(pts):
                continue

            entry = player_weeks[sleeper_id]
            entry["weeks"].append(pts)
            # Keep latest name/pos/team
            entry["name"] = (row.get("name") or "").strip() or entry["name"]
            entry["pos"] = (row.get("pos") or "").strip() or entry["pos"]
            entry["team"] = (row.get("team") or "").strip() or entry["team"]

    # Compute per-game PPG and resolve identity
    resolved: dict[str, list[dict[str, Any]]] = {pos: [] for pos in POSITIONS}
    review: list[dict[str, Any]] = []
    aliases_used: list[dict[str, Any]] = []
    n_total_players = 0

    for sleeper_id, pdata in player_weeks.items():
        weeks = pdata["weeks"]
        if not weeks:
            continue
        name = pdata["name"]
        pos = pdata["pos"]
        team = pdata["team"]
        n_total_players += 1

        if pos not in POSITIONS:
            review.append({"reason": "non_skill_position", "player": name, "pos": pos,
                           "sleeper_id": sleeper_id})
            continue

        ppg = sum(weeks) / len(weeks)

        # Resolve identity via idmap
        idmap_entry = idmap.get(sleeper_id)
        if idmap_entry is None:
            review.append({"reason": "sleeper_id_not_in_idmap", "player": name,
                           "pos": pos, "sleeper_id": sleeper_id})
            continue

        player_key = idmap_entry["player_key"]
        player_norm = key_to_norm.get(player_key)
        if player_norm is None:
            review.append({"reason": "player_key_not_in_fixture", "player": name,
                           "pos": pos, "player_key": player_key, "sleeper_id": sleeper_id})
            continue

        resolved[pos].append({
            "player_key": player_key,
            "player_norm": player_norm,
            "source_norm": name,
            "player": name,
            "pos": pos,
            "team": team or None,
            "weeks_averaged": len(weeks),
            "x": float(ppg),
        })

    drop_duplicate_keys(resolved, review, "player")
    meta = {
        "current_week": current_week,
        "weeks_range": f"{current_week}-18",
        "total_sleeper_players": n_total_players,
        "idmap_matched": len(idmap),
    }
    return resolved, review, aliases_used, meta


def build_leg(
    weekly_path: Path,
    idmap_path: Path,
    fixture_path: Path,
    scoring: str,
    teams: int,
    bench_share: float,
    current_week: int,
) -> dict[str, Any]:
    resolved, review_rows, aliases_used, snap_meta = load_rotowire_ppg(
        weekly_path, idmap_path, fixture_path, scoring, current_week)

    pool_lists = {pos: [{"id": d["player_key"], "x": d["x"]} for d in resolved[pos]]
                  for pos in POSITIONS}
    pool = build_position_tiers(pool_lists, teams, dict(REF_SLOTS), REF_FLEX_COUNT,
                                list(REF_FLEX_ELIGIBLE), bench_mix_for_teams(teams))
    calibration: dict[str, Any] = {}
    calibration_notes = []
    for pos in POSITIONS:
        tier = pool["tiers"][pos]
        pie = tier["surplus"] if tier else 0
        feasible_share, calibration[pos], note = calibrate_feasible(tier, pie, bench_share)
        if note:
            calibration_notes.append(f"{pos}: {note}")

    raw: dict[int, float] = {}
    for pos in POSITIONS:
        cal = calibration[pos]
        for d in resolved[pos]:
            raw[d["player_key"]] = price_for_projection(d["x"], cal)
    mx = max(raw.values()) if raw else 0.0
    if not (mx > 0):
        raise SystemExit("Fail closed: RotoWire leg has no positive raw value; nothing to normalize.")
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
                "weeks_averaged": d["weeks_averaged"],
                "tier": tier,
                "raw_value": raw[key],
                "value": raw[key] * scale,
            })
    values.sort(key=lambda v: (-v["value"], v["player_key"]))

    vintage_date = date.today().isoformat()
    bake_id = (f"ddf-{vintage_date.replace('-', '')}-{SOURCE_TAG}-"
               f"{scoring}-{teams}t-{str(bench_share).replace('.', 'p')}")
    return {
        "schema": SCHEMA,
        "bake_id": bake_id,
        "generated_at": utc_now(),
        "inputs": {
            "weekly_projections": str(weekly_path),
            "weekly_projections_sha256": sha256_file(weekly_path),
            "idmap": str(idmap_path),
            "idmap_sha256": sha256_file(idmap_path),
            "vintage_date": vintage_date,
            "current_week": snap_meta["current_week"],
            "weeks_range": snap_meta["weeks_range"],
            "total_sleeper_players": snap_meta["total_sleeper_players"],
            "per_game_note": (
                "Per-game PPG = average of remaining-week RotoWire projections "
                f"(via Sleeper; weeks {snap_meta['weeks_range']} for {CURRENT_SEASON} season). "
                "pts_ppr / pts_half_ppr / pts_std columns used directly from "
                "weekly_projections_sleeper.csv.gz. Identity via "
                "sleeper_projection_idmap.csv (sleeper_id -> player_key)."
            ),
            "pies_note": ("Positional pies measured from the current RotoWire data "
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
            "alias_note": ("Identity via sleeper_projection_idmap.csv: "
                           "sleeper_id -> player_key (status 'matched' or "
                           "'gsis_not_in_players'). player_key -> player_norm via "
                           "fixture player_keys (reversed). Unresolvable identities "
                           "are excluded, never guessed."),
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
    parser.add_argument("--weekly", type=Path, default=DEFAULT_WEEKLY,
                        help="data/inputs/weekly_projections_sleeper.csv.gz")
    parser.add_argument("--idmap", type=Path, default=DEFAULT_IDMAP,
                        help="data/inputs/sleeper_projection_idmap.csv")
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--scoring", default="ppr", help="standard | half_ppr | ppr")
    parser.add_argument("--teams", type=int, default=12)
    parser.add_argument("--bench-share", type=float, default=DEFAULT_BENCH_SHARE)
    parser.add_argument("--current-week", type=int, default=None,
                        help=f"First remaining week (default: fixture current_week or {DEFAULT_CURRENT_WEEK})")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    for path in (args.weekly, args.idmap, args.fixture):
        if not path.is_file():
            raise SystemExit(f"Input not found: {path}")

    # Determine current week from fixture or CLI override
    current_week = args.current_week
    if current_week is None:
        fx = json.loads(args.fixture.read_text(encoding="utf-8"))
        current_week = fx.get("current_week") or DEFAULT_CURRENT_WEEK

    leg = build_leg(args.weekly, args.idmap, args.fixture,
                    args.scoring, args.teams, args.bench_share, current_week)
    out_dir = args.output_dir / leg["bake_id"]
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "ddf_leg_rotowire.json"
    leg = write_leg_json(out_path, leg)
    summary = leg["summary"]
    print(f"Built RotoWire DDF leg {leg['bake_id']}: {summary['n_values']} values "
          f"({summary['n_starters']} starters / {summary['n_bench']} bench / "
          f"{summary['n_waiver']} waiver), {summary['n_review']} review -> {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
