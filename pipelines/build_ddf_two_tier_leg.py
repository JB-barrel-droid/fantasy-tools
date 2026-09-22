#!/usr/bin/env python3
"""Build the DDF two-tier value-above-waivers leg from ESPN projections.

Stage 2 of the repo pipeline: ESPN projections -> DDF two-tier leg ->
versioned adjustment inputs (pipelines/build_adjustment_inputs.py).

This is a pure-Python port of the browser's TwoTier calibration in
app/trade-value-chart/assets/curve-widget.js (itself a port of
lottery/bin/starter_model.py, the reference implementation). The port is
verified bit-exact against the JS harness in tests/test_ddf_two_tier_leg.py
(pinned vectors + the real ESPN inputs, 1e-9 tolerance).

Locked decisions (Jeremy, 2026-09-21/22):
  - ESPN-purity: every number labeled ESPN comes from ESPN projections only.
    Per-game projections are the CSV's ROS components rescored per scoring
    (arithmetic on ESPN components only -- never expert blending), divided
    by 16 (weeks 3-18, the same divisor the pie measurement used).
  - Positional pies: ESPN-measured pools (lottery/bin/espn_pies.json),
    vintage-recorded. Never guessed.
  - bench_share: 0.15 default (the UI parameter; the leg is built at the
    recommended share).
  - Glide width tau = 25% of (starter line - waiver line) per position.
  - normalize-then-round: full precision through calibration; ONE 70/max
    multiplier applied before any rounding; rounding is display-only and
    never enters this artifact. The 85/15 pie identity is verified
    pre-rounding (bench_raw == 0.15*pie, starter_raw == 0.85*pie).
  - Fail closed: an infeasible calibration at the active share, a
    non-positive pie, a position with no surplus, or an unresolvable
    identity publishes NO leg. Missing values stay absent (review rows),
    never zero-filled or guessed.

Identity: numeric player_key via the fixture's player_keys map
(source-id -> canonical key). Four CSV spellings are verified aliases of
canonical chart names (2026-09-19 waiver investigation, confirmed against
Supabase players.full_name 2026-09-22): c Cameron Ward (697),
'cameron skattebo' -> 'cam skattebo' (3664), 'travis etienne jr' ->
'travis etienne' (810), 'michael pittman jr' -> 'michael pittman' (561).
Anything else unresolvable is excluded to review_rows, never guessed.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CSV = ROOT / "data" / "inputs" / "espn_projections.csv"
DEFAULT_PIES = ROOT / "data" / "inputs" / "espn_pies.json"
DEFAULT_FIXTURE = ROOT / "data" / "fixtures" / "current" / "comparison-sources-data.json"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "ddf-two-tier"

SCHEMA = "trade-value-ddf-leg-v1"

POSITIONS = ["QB", "RB", "WR", "TE"]
DEFAULT_BENCH_SHARE = 0.15
GLIDE_WIDTH_FRAC = 0.25
GAMES_DIVISOR = 16  # weeks 3-18; the same divisor the pie measurement used

# Reference league shape (mirrors the widget's TwoTier constants exactly).
REF_SLOTS = {"QB": 1, "RB": 2, "WR": 3, "TE": 1}
REF_FLEX_COUNT = 1
REF_FLEX_ELIGIBLE = ["RB", "WR", "TE"]
REF_BENCH_SLOTS = 6            # bench spots per team in the reference shape
# Retained only as the pre-derivation reference point for the regression test
# that pins benchMixFor against the constant it replaced. Never read at runtime.
LEGACY_BENCH_MIX_12 = {"QB": 10, "RB": 27, "WR": 33, "TE": 10}
# Slope threshold for the irrelevance floor: the rank below which a position's
# projections stop separating and the players are interchangeable. Cross-checked
# against a Kneedle elbow (agrees within a few ranks at QB/WR/TE; RB decays
# smoothly and has no sharp bend, so the floor there is advisory, not binding).
FLOOR_SLOPE_FRAC = 0.01
FLOOR_WINDOW = 5

# Verified spelling aliases: csv player_norm -> fixture player_keys id.
# (Same humans; verified 2026-09-19, re-confirmed vs players.full_name.)
ALIASES = {
    "cameron ward": "cam ward",
    "cameron skattebo": "cam skattebo",
    "travis etienne jr": "travis etienne",
    "michael pittman jr": "michael pittman",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ---------------------------------------------------------------------------
# Two-tier math: exact port of the widget's TwoTier helpers.
# ---------------------------------------------------------------------------

def softplus(z: float) -> float:
    return math.log1p(math.exp(-abs(z))) + (z if z > 0 else 0.0)


def slice_exposures(x: float, rw: float, rs: float, tau: float) -> tuple[float, float]:
    if not (x > rw):
        return (0.0, 0.0)
    glide = tau * (softplus((x - rs) / tau) - softplus((rw - rs) / tau))
    return ((x - rw) - glide, glide)


def check_share(share: Any, pos: str = "?") -> float:
    s = float(share)
    if not math.isfinite(s) or not (s > 0 and s < 1):
        raise ValueError(f"cannot calibrate {pos}: bench share {share!r} is not between 0 and 1 (exclusive)")
    return s


def solve_tier_prices(a_bench: float, b_bench: float, a_start: float, b_start: float,
                      pie: float, pos: str = "?", bench_share: float = DEFAULT_BENCH_SHARE) -> tuple[float, float]:
    share = check_share(bench_share, pos)
    starter_share = 1.0 - share
    if not (pie > 0):
        raise ValueError(f"cannot calibrate {pos}: non-positive pie {pie!r}")
    det = a_bench * b_start - a_start * b_bench
    if det == 0:
        raise ValueError(f"cannot calibrate {pos}: degenerate slice exposures")
    pb = (share * pie * b_start - b_bench * starter_share * pie) / det
    ps = (a_bench * starter_share * pie - share * pie * a_start) / det
    if not (pb > 0):
        raise ValueError(f"cannot calibrate {pos} at bench share {share}: bench rate {pb} not positive")
    if not (ps > pb):
        raise ValueError(
            f"cannot calibrate {pos} at bench share {share}: starter rate {ps} does not exceed "
            f"bench rate {pb} -- the economics break (bench slices would pay more than starter slices)")
    tol = 1e-9 * pie
    if abs(pb * a_bench + ps * b_bench - share * pie) > tol or \
       abs(pb * a_start + ps * b_start - starter_share * pie) > tol:
        raise ValueError(f"cannot calibrate {pos} at bench share {share}: solved rates miss the split")
    return pb, ps


def tail_floor(xs: list[float], frac: float = FLOOR_SLOPE_FRAC,
               win: int = FLOOR_WINDOW) -> int:
    """Rank where a position's projections stop separating (1-based).

    Scanned from the BOTTOM up: the floor is the last rank whose smoothed
    drop/rank still clears the threshold. Scanning top-down instead finds the
    UPPER plateau (QB is flat from ~#6-20 as well) and returns nonsense.
    """
    if len(xs) <= win:
        return len(xs)
    thr = frac * (xs[0] - xs[-1])
    if not (thr > 0):
        return len(xs)
    for s in range(len(xs) - win - 1, -1, -1):
        if (xs[s] - xs[s + win]) / win >= thr:
            return s + win + 1
    return 1


def bench_mix_for(teams: int, bench_slots: int, slots: dict[str, int],
                  flex_count: int, flex_eligible: list[str],
                  pools: dict[str, list[float]]) -> dict[str, int]:
    """Bench spots per position, derived rather than pinned.

    A bench spot exists to cover a starting slot when its starter is out, so
    total cover demand at a position is the expected number of simultaneous
    absences among its starters. For absences at per-starter rate q, that is
    sum_n P(>= n out) == lambda == S_p * q. Demand is therefore EXACTLY
    proportional to S_p, the starting-slot load, and q cancels in the
    normalisation -- the model carries no free parameter and never has to
    estimate an injury rate.

    S_p is dedicated slots plus the position's realised share of the flex, so
    the mix responds to the league shape the user actually selected. The
    irrelevance floor caps each position (never roster into dead pool), and
    largest-remainder rounding makes the parts sum EXACTLY to the league's
    bench capacity -- teams * bench_slots -- which the pinned constant never
    did (it totalled 80 across 12 teams, i.e. 6.67 bench spots per team, and
    drifted to a different implied depth at every other team count).
    """
    capacity = teams * bench_slots
    if capacity <= 0:
        return {pos: 0 for pos in POSITIONS}

    ranked = {pos: sorted(pools.get(pos, []), reverse=True) for pos in POSITIONS}
    # Starters, by the same rule build_position_tiers uses, to get S_p.
    taken = {pos: teams * slots.get(pos, 0) for pos in POSITIONS}
    flex_pool: list[tuple[float, str]] = []
    for pos in POSITIONS:
        if pos in flex_eligible:
            flex_pool.extend((x, pos) for x in ranked[pos][taken[pos]:])
    flex_pool.sort(key=lambda t: -t[0])
    flex_hits = {pos: 0 for pos in POSITIONS}
    for _, pos in flex_pool[: teams * flex_count]:
        flex_hits[pos] += 1
    starters = {pos: taken[pos] + flex_hits[pos] for pos in POSITIONS}
    load = {pos: slots.get(pos, 0) + flex_hits[pos] / teams for pos in POSITIONS}

    cap = {pos: max(0, tail_floor(ranked[pos]) - starters[pos]) for pos in POSITIONS}
    alloc = {pos: 0.0 for pos in POSITIONS}
    remaining = float(capacity)
    for _ in range(8):
        open_pos = [p for p in POSITIONS if alloc[p] < cap[p] - 1e-9 and load[p] > 0]
        weight = sum(load[p] for p in open_pos)
        if not open_pos or weight <= 0 or remaining < 1e-9:
            break
        for p in open_pos:
            alloc[p] = min(float(cap[p]), alloc[p] + remaining * load[p] / weight)
        remaining = capacity - sum(alloc.values())

    out = {pos: int(alloc[pos]) for pos in POSITIONS}
    order = sorted(POSITIONS, key=lambda p: -(alloc[p] - int(alloc[p])))
    guard = 0
    while sum(out.values()) < capacity and guard < 10000:
        p = order[guard % len(order)]
        if out[p] < cap[p]:
            out[p] += 1
        guard += 1
    return out


def build_position_tiers(lists: dict[str, list[dict[str, Any]]], teams: int,
                         slots: dict[str, int], flex_count: int,
                         flex_eligible: list[str], bench_mix: dict[str, int]) -> dict[str, Any]:
    by_pos: dict[str, list[dict[str, Any]]] = {}
    for pos in POSITIONS:
        rows = [{"id": d["id"], "x": d["x"]} for d in lists.get(pos, [])
                if isinstance(d.get("x"), float) and math.isfinite(d["x"])]
        rows.sort(key=lambda d: (-d["x"], d["id"]))
        by_pos[pos] = rows
    dedicated: set[str] = set()
    starters: set[str] = set()
    for pos in POSITIONS:
        for d in by_pos[pos][: teams * slots.get(pos, 0)]:
            dedicated.add(d["id"])
            starters.add(d["id"])
    flex_pool: list[dict[str, Any]] = []
    for pos in POSITIONS:
        if pos not in flex_eligible:
            continue
        for d in by_pos[pos]:
            if d["id"] not in dedicated:
                flex_pool.append(d)
    flex_pool.sort(key=lambda d: (-d["x"], d["id"]))
    for d in flex_pool[: teams * flex_count]:
        starters.add(d["id"])
    rostered = set(starters)
    bench: set[str] = set()
    for pos in POSITIONS:
        for d in [d for d in by_pos[pos] if d["id"] not in rostered][: bench_mix.get(pos, 0)]:
            rostered.add(d["id"])
            bench.add(d["id"])
    tiers: dict[str, Any] = {}
    for pos in POSITIONS:
        lst = by_pos[pos]
        if not lst:
            tiers[pos] = None
            continue
        nxt = next((d for d in lst if d["id"] not in rostered), None)
        rw = nxt["x"] if nxt else 0.0
        s_projs = [d["x"] for d in lst if d["id"] in starters]
        b_projs = [d["x"] for d in lst if d["id"] not in starters]
        if not s_projs:
            rs = lst[0]["x"] + 1
        elif not b_projs:
            rs = lst[-1]["x"] - 1
        else:
            rs = (min(s_projs) + max(b_projs)) / 2
        if not (rs > rw):
            raise ValueError(f"buildPositionTiers: starter line {rs} must exceed waiver line {rw} at {pos}")
        tau = GLIDE_WIDTH_FRAC * (rs - rw)
        a_bench = b_bench = a_start = b_start = surplus = 0.0
        for d in lst:
            if not (d["x"] > rw):
                continue
            surplus += d["x"] - rw
            a, b = slice_exposures(d["x"], rw, rs, tau)
            if d["id"] in starters:
                a_start += a
                b_start += b
            else:
                a_bench += a
                b_bench += b
        tiers[pos] = {"rw": rw, "rs": rs, "tau": tau, "a_bench": a_bench,
                      "b_bench": b_bench, "a_start": a_start, "b_start": b_start,
                      "surplus": surplus}
    return {"tiers": tiers, "starters": starters, "bench": bench, "rostered": rostered}


def calibrate_position(tier: dict[str, Any] | None, pie: float,
                       bench_share: float = DEFAULT_BENCH_SHARE) -> dict[str, Any]:
    if tier is None:
        raise ValueError("cannot calibrate: missing tier (no players at this position)")
    if not (tier["surplus"] > 0):
        raise ValueError("cannot calibrate: position has no above-waiver surplus")
    if not (pie > 0):
        raise ValueError(f"cannot calibrate: non-positive pie {pie!r}")
    pb, ps = solve_tier_prices(tier["a_bench"], tier["b_bench"], tier["a_start"],
                               tier["b_start"], pie, "?", bench_share)
    return {**tier, "pb": pb, "ps": ps,
            "bench_raw": pb * tier["a_bench"] + ps * tier["b_bench"],
            "starter_raw": pb * tier["a_start"] + ps * tier["b_start"]}


def price_for_projection(x: float, cal: dict[str, Any]) -> float:
    if not (x > cal["rw"]):
        return 0.0
    a, b = slice_exposures(x, cal["rw"], cal["rs"], cal["tau"])
    return cal["pb"] * a + cal["ps"] * b


# ---------------------------------------------------------------------------
# ESPN input: ROS components -> per-game, rescored per scoring.
# ---------------------------------------------------------------------------

def parse_float(raw: Any) -> float | None:
    try:
        value = float(str(raw).strip())
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def load_espn_lists(csv_path: Path, scoring: str) -> tuple[dict[str, list[dict[str, Any]]], dict[str, Any], list[dict[str, Any]]]:
    """Return (lists, input_meta, review_rows).

    lists: {pos: [{id: player_norm, name, team, x: per-game}]}.
    Per-game = ROS components rescored per scoring / 16 (weeks 3-18).
    Rescoring is arithmetic on ESPN components only (reception points are
    the only scoring difference): ppr = half_ppr + 0.5*receptions,
    standard = half_ppr - 0.5*receptions. ESPN-pure by construction.
    """
    if scoring not in ("standard", "half_ppr", "ppr"):
        raise SystemExit(f"Unknown scoring '{scoring}'")
    with csv_path.open(newline="", encoding="utf-8") as handle:
        raw_rows = list(csv.DictReader(handle))
    dates = {r.get("espn_snapshot_date") for r in raw_rows if r.get("espn_snapshot_date")}
    if len(dates) != 1:
        raise SystemExit(
            f"Fail closed: ESPN content vintage undeterminable "
            f"(espn_snapshot_date values: {sorted(dates)[:5]}).")
    vintage = next(iter(dates))
    lists: dict[str, list[dict[str, Any]]] = {pos: [] for pos in POSITIONS}
    review_rows: list[dict[str, Any]] = []
    for row in raw_rows:
        name = str(row.get("player") or "").strip()
        norm = str(row.get("player_norm") or "").strip()
        pos = str(row.get("pos") or "").strip()
        projected = str(row.get("has_espn_projection") or "").strip().lower() in ("true", "1", "yes")
        eligible = str(row.get("eligible") or "").strip().lower() in ("true", "1", "yes")
        if not name or not projected or not eligible:
            review_rows.append({"reason": "no_espn_projection", "player": name or None})
            continue
        if pos not in POSITIONS:
            review_rows.append({"reason": "non_skill_position", "player": name, "pos": pos})
            continue
        ros_half = parse_float(row.get("ros_half_ppr"))
        receptions = parse_float(row.get("r_receptions"))
        if ros_half is None or receptions is None:
            review_rows.append({"reason": "missing_components", "player": name})
            continue
        if scoring == "ppr":
            ros = ros_half + 0.5 * receptions
        elif scoring == "standard":
            ros = ros_half - 0.5 * receptions
        else:
            ros = ros_half
        lists[pos].append({
            "id": norm,
            "name": name,
            "team": str(row.get("team") or "").strip() or None,
            "x": ros / GAMES_DIVISOR,
        })
    meta = {"espn_snapshot_date": vintage, "csv_rows": len(raw_rows)}
    return lists, meta, review_rows


def load_pies(pies_path: Path, scoring: str, teams: int) -> tuple[dict[str, float], dict[str, Any]]:
    data = json.loads(pies_path.read_text(encoding="utf-8"))
    try:
        pies_raw = data["pies"][scoring][str(teams)]
    except KeyError:
        raise SystemExit(
            f"Fail closed: no ESPN-measured pies for scoring={scoring} teams={teams} "
            f"in {pies_path}. A guessed pie would silently re-weight every position.")
    pies = {pos: float(pies_raw[pos]) for pos in POSITIONS if pos in pies_raw}
    missing = [pos for pos in POSITIONS if pos not in pies]
    if missing:
        raise SystemExit(f"Fail closed: pies missing positions {missing} in {pies_path}")
    if any(not (v > 0) for v in pies.values()):
        raise SystemExit(f"Fail closed: non-positive pie in {pies_path}: {pies}")
    meta = {
        "pies_file": str(pies_path),
        "pies_sha256": sha256_file(pies_path),
        "pies_vintage": (data.get("meta") or {}).get("vintage", {}).get("skill", {}).get("espn_snapshot_date"),
        "pies_method": (data.get("meta") or {}).get("method"),
    }
    return pies, meta


def resolve_identities(lists: dict[str, list[dict[str, Any]]],
                       fixture_path: Path) -> tuple[dict[str, list[dict[str, Any]]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Attach canonical player_key to every leg row.

    Join: csv player_norm -> fixture player_keys (with the verified alias
    map). Unresolvable norms are excluded to review_rows, never guessed.
    """
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    player_keys = fixture.get("player_keys") or {}
    resolved: dict[str, list[dict[str, Any]]] = {pos: [] for pos in POSITIONS}
    review: list[dict[str, Any]] = []
    aliases_used: list[dict[str, Any]] = []
    for pos in POSITIONS:
        for d in lists[pos]:
            norm = d["id"]
            key = player_keys.get(norm)
            alias = None
            if key is None and norm in ALIASES:
                alias = ALIASES[norm]
                key = player_keys.get(alias)
            if not isinstance(key, int):
                review.append({"reason": "unresolved_identity", "player": d["name"],
                               "player_norm": norm, "pos": pos})
                continue
            if alias:
                aliases_used.append({"csv_norm": norm, "canonical_id": alias, "player_key": key})
            resolved[pos].append({**d, "player_key": key})
    return resolved, review, aliases_used


def build_leg(csv_path: Path, pies_path: Path, fixture_path: Path,
              scoring: str, teams: int, bench_share: float) -> dict[str, Any]:
    lists, csv_meta, csv_review = load_espn_lists(csv_path, scoring)
    pies, pies_meta = load_pies(pies_path, scoring, teams)
    resolved, id_review, aliases_used = resolve_identities(lists, fixture_path)
    review_rows = csv_review + id_review

    # Tier pool keyed by canonical player_key (stable total order by key).
    pool_lists = {pos: [{"id": d["player_key"], "x": d["x"]} for d in resolved[pos]] for pos in POSITIONS}

    # Bench depth is DERIVED from the league shape and the projection pools
    # (see bench_mix_for), not pinned to a 12-team constant.
    bench_mix = bench_mix_for(teams, REF_BENCH_SLOTS, dict(REF_SLOTS),
                              REF_FLEX_COUNT, list(REF_FLEX_ELIGIBLE),
                              {pos: [d["x"] for d in pool_lists[pos]] for pos in POSITIONS})
    if sum(bench_mix.values()) != teams * REF_BENCH_SLOTS:
        raise ValueError(
            f"bench mix {bench_mix} sums to {sum(bench_mix.values())}, "
            f"not the league's {teams * REF_BENCH_SLOTS} bench spots")
    pool = build_position_tiers(pool_lists, teams, dict(REF_SLOTS), REF_FLEX_COUNT,
                                list(REF_FLEX_ELIGIBLE), bench_mix)
    calibration: dict[str, Any] = {}
    for pos in POSITIONS:
        tier = pool["tiers"][pos]
        # calibrate_position raises fail-closed on any broken economics.
        calibration[pos] = calibrate_position(tier, pies[pos], bench_share)

    # Full-precision raw values; the single 70/max multiplier applies BEFORE
    # any rounding (rounding is display-only and never enters this artifact).
    raw: dict[int, float] = {}
    for pos in POSITIONS:
        cal = calibration[pos]
        for d in resolved[pos]:
            raw[d["player_key"]] = price_for_projection(d["x"], cal)
    mx = max(raw.values()) if raw else 0.0
    if not (mx > 0):
        raise SystemExit("Fail closed: leg has no positive raw value; nothing to normalize.")
    scale = 70.0 / mx

    # 85/15 pie identity, verified pre-rounding (the locked guarantee).
    for pos in POSITIONS:
        cal = calibration[pos]
        pie = pies[pos]
        if abs(cal["bench_raw"] - bench_share * pie) > 1e-9 * pie or \
           abs(cal["starter_raw"] - (1 - bench_share) * pie) > 1e-9 * pie:
            raise SystemExit(f"Fail closed: {pos} pie identity broken pre-rounding.")

    values = []
    for pos in POSITIONS:
        for d in resolved[pos]:
            key = d["player_key"]
            tier = "starter" if key in pool["starters"] else ("bench" if key in pool["bench"] else "waiver")
            values.append({
                "player_key": key,
                "player_norm": d["id"],
                "player": d["name"],
                "pos": pos,
                "team": d["team"],
                "ppg": d["x"],
                "tier": tier,
                "raw_value": raw[key],
                "value": raw[key] * scale,
            })
    values.sort(key=lambda v: (-v["value"], v["player_key"]))

    bake_id = (f"ddf-{csv_meta['espn_snapshot_date'].replace('-', '')}-espn-"
               f"{scoring}-{teams}t-{str(bench_share).replace('.', 'p')}")
    return {
        "schema": SCHEMA,
        "bake_id": bake_id,
        "generated_at": utc_now(),
        "inputs": {
            "espn_csv": str(csv_path),
            "espn_csv_sha256": sha256_file(csv_path),
            "espn_snapshot_date": csv_meta["espn_snapshot_date"],
            "espn_csv_rows": csv_meta["csv_rows"],
            "games_divisor": GAMES_DIVISOR,
            "rescoring_note": ("per-game = ROS components rescored per scoring / 16 "
                               "(weeks 3-18). Reception points are the only scoring "
                               "difference: ppr = half_ppr + 0.5*receptions, "
                               "standard = half_ppr - 0.5*receptions. Arithmetic on "
                               "ESPN components only; no expert blending."),
            **pies_meta,
            "scoring": scoring,
            "teams": teams,
            "bench_share": bench_share,
        },
        "reference_shape": {
            "slots": REF_SLOTS, "flex_count": REF_FLEX_COUNT,
            "flex_eligible": REF_FLEX_ELIGIBLE,
            "bench_slots": REF_BENCH_SLOTS,
            "bench_mix": bench_mix,
            "bench_mix_source": "derived: starting-slot load, capped by irrelevance floor",
        },
        "calibration": {
            pos: {
                "rw": c["rw"], "rs": c["rs"], "tau": c["tau"], "pie": pies[pos],
                "pb": c["pb"], "ps": c["ps"],
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
            "alias_note": ("Four CSV spellings verified as the same humans as "
                           "canonical chart names (2026-09-19 investigation, "
                           "re-confirmed vs Supabase players.full_name)."),
        },
        "values": values,
        "review_rows": review_rows,
        "summary": {
            "n_values": len(values),
            "n_review": len(review_rows),
            "n_starters": sum(1 for v in values if v["tier"] == "starter"),
            "n_bench": sum(1 for v in values if v["tier"] == "bench"),
            "n_waiver": sum(1 for v in values if v["tier"] == "waiver"),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--pies", type=Path, default=DEFAULT_PIES)
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--scoring", default="ppr", help="standard | half_ppr | ppr")
    parser.add_argument("--teams", type=int, default=12)
    parser.add_argument("--bench-share", type=float, default=DEFAULT_BENCH_SHARE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    for path in (args.csv, args.pies, args.fixture):
        if not path.is_file():
            raise SystemExit(f"Input not found: {path}")

    leg = build_leg(args.csv, args.pies, args.fixture, args.scoring, args.teams, args.bench_share)
    out_dir = args.output_dir / leg["bake_id"]
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "ddf_leg.json"
    out_path.write_text(json.dumps(leg, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    summary = leg["summary"]
    print(f"Built DDF leg {leg['bake_id']}: {summary['n_values']} values "
          f"({summary['n_starters']} starters / {summary['n_bench']} bench / "
          f"{summary['n_waiver']} waiver), {summary['n_review']} review -> {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
