#!/usr/bin/env python3
"""JEG-211: DDF two-tier value-above-waivers leg for K and DST positions.

K and DST are SEPARATE and OPTIONAL from the eight skill-position groups
(QB/RB/WR/TE x starter/bench). Per docs/kdst-group-contract.md the groups
are (K starter), (K bench), (DST starter), (DST bench); the 8-group logic in
build_ddf_two_tier_leg.py is NOT modified. K/DST only exist because ESPN
projects both; every other dashboard source lacks K/DST data (audit:
docs/kdst-source-audit.md, 2026-10-01).

This module reuses the locked two-tier math from build_ddf_two_tier_leg
(softplus, slice_exposures, solve_tier_prices, build_position_tiers,
calibrate_position, price_for_projection). Only the input layer and the
roster config differ:

  - K/DST roster config: K slots=1, DST slots=1 (one each per team); no
    flex applies (leagues start exactly one K and one DST). bench_total
    defaults to teams (mirroring the dedicated count) -- K/DST typically
    have very thin bench coverage in real leagues.
  - K input: data/inputs/espn_k_ppg_2026-09-21.json -- per-kicker ppg
    (mean weekly appliedTotal w3-18, bye 0 included).
  - DST input: data/inputs/espn_dst_ros_2026-09-21.json -- per-defense ppg
    (mean w3-18 of the standard D/ST recipe, bye included).
  - Identity: K resolves to fixture player_keys by exact name match
    (player_keys is keyed by lower-cased full_name; players.json names
    match the ESPN K/DST file names byte-for-byte). DST resolves to the
    fixture's DST player_key by team abbr (team -> player_key).
  - No rescoring: K and DST projections are scoring-invariant (one number
    serves standard/half/full), per the audit. The bench_share parameter
    is still passed through for the calibration math.

The output leg is byte-distinct from the 8-group leg (different schema
name and different values list) so glob-based tools that read
*/ddf_leg.json never accidentally pick up K/DST.

Output: data/ddf-two-tier/<bake_id>/ddf_leg_kdst.json
  bake_id = ddf-kdst-<YYYYMMDD>-espn-<teams>t-0p15

Fail-closed:
  * Missing/unreadable K or DST input -> SystemExit.
  * Snapshot date undeterminable (mismatched as_of) -> SystemExit.
  * Empty pool for K or DST -> ValueError (mirrors skill leg behavior).
  * Infeasible calibration at the requested bench share -> max feasible
    share per position, same fallback the skill leg applies.
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
    DEFAULT_BENCH_SHARE,
    build_position_tiers,
    calibrate_position,
    price_for_projection,
)

# K and DST are independent positions in this leg. K never enters DST math
# and vice versa. The 8-group logic (QB/RB/WR/TE) is NOT touched.
KDST_POSITIONS = ["K", "DST"]
SCHEMA = "trade-value-ddf-leg-kdst-v1"

DEFAULT_OUTPUT_DIR = ROOT / "data" / "ddf-two-tier"
DEFAULT_K_INPUT = ROOT / "data" / "inputs" / "espn_k_ppg_2026-09-21.json"
DEFAULT_DST_INPUT = ROOT / "data" / "inputs" / "espn_dst_ros_2026-09-21.json"
DEFAULT_FIXTURE = ROOT / "data" / "fixtures" / "current" / "players.json"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _kdst_slots(teams: int) -> dict[str, int]:
    # K slots=1, DST slots=1 per team; flex does not apply (contract).
    return {pos: 1 for pos in KDST_POSITIONS}


def _kdst_bench_mix(teams: int) -> dict[str, int]:
    # Default bench_total = teams (mirrors the dedicated count). Real leagues
    # often carry 0-1 bench K/DST; this default is conservative and scales
    # linearly so the waiver line moves with league size. Override via
    # --bench-k and --bench-dst when a league measurement is available.
    return {pos: teams for pos in KDST_POSITIONS}


def load_kicker_pool(k_input: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Return (rows, meta). rows: [{name, ppg}, ...] sorted descending by ppg."""
    data = json.loads(k_input.read_text(encoding="utf-8"))
    meta = data.get("meta") or {}
    as_of = meta.get("as_of")
    if not as_of:
        raise SystemExit(f"Fail closed: kicker input {k_input} is missing meta.as_of")
    rows = []
    for k in data.get("kickers") or []:
        name = str(k.get("name") or "").strip()
        ppg = k.get("ppg")
        if not name:
            continue
        if not isinstance(ppg, (int, float)) or not math.isfinite(ppg) or ppg < 0:
            # Zero or null ppg means an effectively-zero projection. The
            # tier math will still price them at 0.0; we keep them in the
            # pool so the waiver line is honest about who is below it.
            ppg = 0.0 if (isinstance(ppg, (int, float)) and math.isfinite(ppg)) else 0.0
        rows.append({"name": name, "ppg": float(ppg)})
    rows.sort(key=lambda r: (-r["ppg"], r["name"].lower()))
    return rows, {"as_of": str(as_of), "source": meta.get("source"),
                  "method": meta.get("method"),
                  "n_input": len(data.get("kickers") or []),
                  "n_resolved": len(rows)}


def load_dst_pool(dst_input: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Return (rows, meta). rows: [{name, team, ppg}, ...] sorted by ppg desc."""
    data = json.loads(dst_input.read_text(encoding="utf-8"))
    meta = data.get("meta") or {}
    as_of = meta.get("as_of")
    if not as_of:
        raise SystemExit(f"Fail closed: DST input {dst_input} is missing meta.as_of")
    rows = []
    for d in data.get("defenses") or []:
        abbr = str(d.get("abbr") or "").strip().upper()
        ppg = d.get("ppg")
        if not abbr:
            continue
        if not isinstance(ppg, (int, float)) or not math.isfinite(ppg) or ppg < 0:
            ppg = 0.0 if (isinstance(ppg, (int, float)) and math.isfinite(ppg)) else 0.0
        rows.append({"name": abbr, "team": abbr, "ppg": float(ppg)})
    rows.sort(key=lambda r: (-r["ppg"], r["name"]))
    return rows, {"as_of": str(as_of), "source": meta.get("source"),
                  "method": meta.get("method"),
                  "n_input": len(data.get("defenses") or []),
                  "n_resolved": len(rows)}


def build_identity_index(fixture_path: Path) -> dict[str, Any]:
    """Build name -> player_key and team abbr -> player_key maps from the
    fixture. K resolves by exact lower-cased full_name. DST resolves by
    team abbr (DST entries are team-keyed, not player-keyed).
    """
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    players = fixture.get("players") or []
    by_name: dict[str, int] = {}
    by_team: dict[str, int] = {}
    for pl in players:
        name = str(pl.get("name") or "").strip().lower()
        team = str(pl.get("team") or "").strip().upper()
        key = pl.get("player_key")
        if name and isinstance(key, int) and pl.get("pos") == "K":
            # First wins on name collision (the fixture has unique names).
            by_name.setdefault(name, key)
        elif team and isinstance(key, int) and pl.get("pos") == "DST":
            by_team.setdefault(team, key)
    return {"by_name": by_name, "by_team": by_team}


def build_leg(k_input: Path, dst_input: Path, fixture_path: Path,
              teams: int, bench_share: float,
              bench_k: int | None = None,
              bench_dst: int | None = None) -> dict[str, Any]:
    k_rows, k_meta = load_kicker_pool(k_input)
    d_rows, d_meta = load_dst_pool(dst_input)
    identities = build_identity_index(fixture_path)

    # Vintage check -- both inputs must carry the same snapshot date, else
    # the leg would silently mix vintages. The contract calls this out.
    if k_meta["as_of"] != d_meta["as_of"]:
        raise SystemExit(
            f"Fail closed: K and DST inputs have different as_of dates "
            f"(K={k_meta['as_of']}, DST={d_meta['as_of']}); refusing to mix vintages.")
    snapshot = k_meta["as_of"]

    # Resolve identities; unmatched go to review_rows (never guessed).
    review_rows: list[dict[str, Any]] = []
    resolved: dict[str, list[dict[str, Any]]] = {pos: [] for pos in KDST_POSITIONS}

    for r in k_rows:
        key = identities["by_name"].get(r["name"].lower())
        if not isinstance(key, int):
            review_rows.append({"reason": "unresolved_identity", "pos": "K",
                                "name": r["name"], "ppg": r["ppg"]})
            continue
        resolved["K"].append({"name": r["name"], "team": None,
                              "ppg": r["ppg"], "player_key": key})
    for r in d_rows:
        key = identities["by_team"].get(r["team"])
        if not isinstance(key, int):
            review_rows.append({"reason": "unresolved_identity", "pos": "DST",
                                "name": r["name"], "team": r["team"],
                                "ppg": r["ppg"]})
            continue
        resolved["DST"].append({"name": r["name"], "team": r["team"],
                                "ppg": r["ppg"], "player_key": key})

    # Build two-tier tiers using the shared math. K/DST have no flex and
    # bench count defaults to teams (override via bench_k/bench_dst).
    slots = _kdst_slots(teams)
    bench_mix = {"K": bench_k if isinstance(bench_k, int) else teams,
                 "DST": bench_dst if isinstance(bench_dst, int) else teams}

    pool_lists = {pos: [{"id": d["player_key"], "x": d["ppg"]} for d in resolved[pos]]
                  for pos in KDST_POSITIONS}

    # Empty pools for K or DST fail closed -- the contract requires every
    # K/DST group to have at least one player.
    for pos in KDST_POSITIONS:
        if not pool_lists[pos]:
            raise ValueError(f"cannot build K/DST leg: empty pool for {pos}")

    pool = build_position_tiers(pool_lists, teams, slots, flex_count=0,
                                flex_eligible=[], bench_mix=bench_mix)
    calibration: dict[str, Any] = {}
    calibration_notes: list[str] = []
    for pos in KDST_POSITIONS:
        tier = pool["tiers"][pos]
        # Use the measured surplus as the pie (same approach the skill leg
        # adopted on 2026-09-29: a static pie file goes stale when the
        # player pool changes). K/DST pies are tiny (~2% of the skill pie)
        # so any staleness affects them proportionally less, but the rule
        # is the rule.
        pie = tier["surplus"] if tier else 0.0
        feasible_share = bench_share
        try:
            calibration[pos] = calibrate_position(tier, pie, feasible_share)
        except ValueError as e:
            msg = str(e)
            if "not positive" in msg:
                best = None
                lo = bench_share
                hi = None
                s = bench_share
                while s < 0.99:
                    s = min(0.99, s + 0.01)
                    try:
                        test_cal = calibrate_position(tier, pie, s)
                        hi = s
                        best = (s, test_cal)
                        break
                    except ValueError:
                        lo = s
                if best is not None:
                    feasible_share, calibration[pos] = best
                    calibration_notes.append(
                        f"{pos}: bench share {bench_share} infeasible, using {feasible_share:.3f}")
                else:
                    raise
            elif "economics break" in msg or "does not exceed" in msg:
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
    for pos in KDST_POSITIONS:
        cal = calibration[pos]
        for d in resolved[pos]:
            raw[d["player_key"]] = price_for_projection(d["ppg"], cal)
    mx = max(raw.values()) if raw else 0.0
    if not (mx > 0):
        raise SystemExit("Fail closed: K/DST leg has no positive raw value; nothing to normalize.")
    scale = 70.0 / mx

    values = []
    for pos in KDST_POSITIONS:
        cal = calibration[pos]
        for d in resolved[pos]:
            key = d["player_key"]
            tier = ("starter" if key in pool["starters"]
                    else ("bench" if key in pool["bench"] else "waiver"))
            values.append({
                "player_key": key,
                "player_norm": d["name"].lower().replace(" ", "-"),
                "player": d["name"],
                "pos": pos,
                "team": d["team"],
                "ppg": d["ppg"],
                "tier": tier,
                "raw_value": raw[key],
                "value": raw[key] * scale,
            })
    values.sort(key=lambda v: (-v["value"], v["player_key"]))

    bake_id = (f"ddf-kdst-{snapshot.replace('-', '')}-espn-"
               f"{teams}t-{str(bench_share).replace('.', 'p')}")
    return {
        "schema": SCHEMA,
        "bake_id": bake_id,
        "generated_at": utc_now(),
        "inputs": {
            "k_input": str(k_input),
            "k_input_sha256": sha256_file(k_input),
            "k_as_of": k_meta["as_of"],
            "k_n_input": k_meta["n_input"],
            "k_n_resolved": k_meta["n_resolved"],
            "dst_input": str(dst_input),
            "dst_input_sha256": sha256_file(dst_input),
            "dst_as_of": d_meta["as_of"],
            "dst_n_input": d_meta["n_input"],
            "dst_n_resolved": d_meta["n_resolved"],
            "fixture": str(fixture_path),
            "fixture_sha256": sha256_file(fixture_path),
            "teams": teams,
            "bench_share": bench_share,
            "bench_k": bench_mix["K"],
            "bench_dst": bench_mix["DST"],
            "snapshot_date": snapshot,
        },
        "reference_shape": {
            "slots": slots,
            "flex_count": 0,
            "flex_eligible": [],
            "bench_mix": bench_mix,
        },
        "calibration": {
            pos: {
                "rw": c["rw"], "rs": c["rs"], "tau": c["tau"],
                "pie": c.get("pie_used"),
                "pb": c["pb"], "ps": c["ps"],
                "bench_share_used": c.get("bench_share_used", bench_share),
                "n_starters": sum(1 for d in resolved[pos]
                                  if d["player_key"] in pool["starters"]),
                "n_bench": sum(1 for d in resolved[pos]
                               if d["player_key"] in pool["bench"]),
                "n_pool": len(resolved[pos]),
                "bench_raw": c["bench_raw"], "starter_raw": c["starter_raw"],
            } for pos, c in calibration.items()
        },
        "scale_70_over_max": scale,
        "max_raw_value": mx,
        "k_meta": k_meta,
        "dst_meta": d_meta,
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
        "display_status": "computed_not_displayed",
        "display_status_reason": (
            "K/DST require separate reviewed producer per docs/kdst-group-contract.md; "
            "computed here but the main trade-value chart excludes them (verified 2026-10-02)."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--k-input", type=Path, default=DEFAULT_K_INPUT)
    parser.add_argument("--dst-input", type=Path, default=DEFAULT_DST_INPUT)
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--teams", type=int, default=12)
    parser.add_argument("--bench-share", type=float, default=DEFAULT_BENCH_SHARE)
    parser.add_argument("--bench-k", type=int, default=None,
                        help="Override the K bench count (default: teams).")
    parser.add_argument("--bench-dst", type=int, default=None,
                        help="Override the DST bench count (default: teams).")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    for path in (args.k_input, args.dst_input, args.fixture):
        if not path.is_file():
            raise SystemExit(f"Input not found: {path}")

    leg = build_leg(args.k_input, args.dst_input, args.fixture,
                    args.teams, args.bench_share,
                    bench_k=args.bench_k, bench_dst=args.bench_dst)
    out_dir = args.output_dir / leg["bake_id"]
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "ddf_leg_kdst.json"
    out_path.write_text(json.dumps(leg, indent=2, sort_keys=True) + "\n",
                        encoding="utf-8")
    summary = leg["summary"]
    print(f"Built K/DST leg {leg['bake_id']}: {summary['n_values']} values "
          f"({summary['n_starters']} starters / {summary['n_bench']} bench / "
          f"{summary['n_waiver']} waiver), {summary['n_review']} review -> {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())