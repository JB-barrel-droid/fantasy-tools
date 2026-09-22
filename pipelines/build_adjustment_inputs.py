#!/usr/bin/env python3
"""Build versioned stage-2 adjustment inputs from the DDF two-tier leg.

Stage 2 of the repo pipeline: for each of fantasycalc / usatoday /
fantasypros / cbs, fit affine adjustment cells

    adjusted = max(0, alpha + beta * published_value)

per (source, position, tier in {starter, bench}) against the DDF two-tier
leg (pipelines/build_ddf_two_tier_leg.py), then write the result to the
live asset the chart loads:

    app/trade-value-chart/assets/adjustment-inputs.json

plus a versioned copy under data/adjustment-inputs/<bake_id>/.

Fit design (mirrors the widget exactly):
  - x (published) comes from the same fixture reference combos the chart's
    default Full-PPR 12-team view reads: fantasycalc -> full_12_qb1,
    usatoday/fantasypros/cbs -> full_12. FantasyPros rows without a native
    entry are skipped, exactly like buildPublishedSourceMap.
  - Tiers are the render-time roles: roleMapForValues() assigns
    starter/bench from each SOURCE's OWN published values at the reference
    roster shape (12 teams; QB 1 / RB 2 / WR 2 / TE 1 / FLEX 2 / BENCH 6).
    The baked cells are (position, role)-conditional, so the widget applies
    them under whatever roster shape the user selects at render time.
  - y (target) is the DDF leg's full-precision value (70/max scaled, never
    rounded in the artifact). ESPN-pure: the leg is built only from ESPN
    projections.
  - Waiver-tier players are never adjusted (no cell, exactly like the
    browser).
  - Guards per (source, position, tier), stricter than the browser's live
    refit (baking fewer cells is always safe -- the widget falls back to the
    raw published value where no cell exists): fewer than 5 pairs -> no
    cell; zero x variance -> no cell; non-finite alpha/beta -> no cell;
    non-positive slope -> no cell (an inverting map is never published).

Fail-closed rules:
  - A source whose reference combo is missing from the fixture gets NO
    cells (stays paused), never a fabricated fit.
  - Conflicting canonical duplicates in a source's combo become review
    rows and are excluded from that source's fit (the browser would throw;
    the bake quarantines instead of killing the other sources).
  - Unresolvable source ids become review rows, never guesses.
  - Missing values stay absent; no zero-filling.

Writing the live asset with non-empty cells automatically un-pauses that
source's *_adjusted curve (the pause predicate reads only entry.cells);
no widget code change is needed, and a source with no fittable cells
stays paused and greyed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LEG_DIR = ROOT / "data" / "ddf-two-tier"
DEFAULT_FIXTURE = ROOT / "data" / "fixtures" / "current" / "comparison-sources-data.json"
DEFAULT_PLAYERS = ROOT / "data" / "fixtures" / "current" / "players.json"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "adjustment-inputs"
LIVE_ASSET = ROOT / "app" / "trade-value-chart" / "assets" / "adjustment-inputs.json"

SCHEMA = "trade-value-adjustment-inputs-v1"

# Reference combos the chart's default Full-PPR 12-team view reads
# (comboKey in curve-widget.js: ppr -> "full", fantasycalc takes _qb1).
REFERENCE_COMBOS = {
    "fantasycalc": "full_12_qb1",
    "usatoday": "full_12",
    "fantasypros": "full_12",
    "cbs": "full_12",
}

POSITION_ORDER = ["QB", "RB", "WR", "TE"]
# Fit guards: a (position, tier) cell is only baked when the affine map is
# worth publishing. MIN_FIT_PAIRS keeps a 2-parameter fit off noise;
# beta > 0 is the economic sanity check (a negative slope would invert the
# source's own ordering -- indefensible for an adjustment map). A guarded
# (pos, tier) simply gets no cell; the widget falls back to the source's
# raw published value for those players.
MIN_FIT_PAIRS = 5
# Reference roster shape (widget DEFAULT_ROSTER) for role assignment.
ROLE_TEAMS = 12
ROLE_ROSTER = {"QB": 1, "RB": 2, "WR": 2, "TE": 1, "FLEX": 2, "BENCH": 6}
ROLE_FLEX_ELIGIBLE = ["RB", "WR", "TE"]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def clamp_value(raw) -> float | None:
    if raw is None or raw == "":
        return None
    try:
        number = float(raw)
    except (TypeError, ValueError):
        return None
    return max(0.0, number) if math.isfinite(number) else None


def find_leg(ddf_dir: Path) -> Path:
    legs = sorted(ddf_dir.glob("*/ddf_leg.json"))
    if not legs:
        raise SystemExit(f"No DDF leg found under {ddf_dir}; run pipelines/build_ddf_two_tier_leg.py first.")
    # Newest bake wins when several exist.
    legs.sort(key=lambda p: json.loads(p.read_text(encoding="utf-8"))["generated_at"])
    return legs[-1]


def load_canonical(fixture: dict) -> dict[int, dict]:
    """player_key -> {pos, preseason_rank, name} from players.json shape."""
    players = fixture.get("players") or []
    out = {}
    for p in players:
        try:
            key = int(p["player_key"])
        except (TypeError, ValueError):
            continue
        name = str(p.get("full_name") or p.get("name") or "").strip()
        if not name or p.get("pos") not in POSITION_ORDER:
            continue
        rank_raw = p.get("preseasonRank", p.get("preseason_ecr_rank"))
        try:
            rank = float(rank_raw)
            rank = rank if math.isfinite(rank) else None
        except (TypeError, ValueError):
            rank = None
        out[key] = {"pos": p["pos"], "preseason_rank": rank, "name": name}
    return out


def build_published_source_map(source: str, fixture: dict,
                               canonical: dict[int, dict]) -> tuple[dict[int, float], list[dict]]:
    """Port of the widget's buildPublishedSourceMap (reference combos only)."""
    section = (fixture.get("sources") or {}).get(source) or {}
    combo_name = REFERENCE_COMBOS[source]
    combo = (section.get("combos") or {}).get(combo_name) or {}
    raw = combo.get("values") or combo.get("reindexed") or {}
    native = combo.get("native") or {}
    player_keys = fixture.get("player_keys") or {}
    published: dict[int, float] = {}
    review: list[dict] = []
    for source_id, raw_value in raw.items():
        if source in ("fantasypros",) and source_id not in native:
            continue
        key_raw = player_keys.get(source_id)
        try:
            key = int(key_raw)
        except (TypeError, ValueError):
            key = None
        player = canonical.get(key) if key is not None else None
        value = clamp_value(raw_value)
        if player is None or value is None:
            review.append({"reason": "unresolved_identity" if player is None else "non_numeric_value",
                           "source": source, "source_id": source_id})
            continue
        if key in published and published[key] != value:
            # Conflicting canonical duplicate: quarantine, never blend.
            review.append({"reason": "conflicting_duplicate", "source": source,
                           "player_key": key, "player": player["name"],
                           "values": sorted({published[key], value})})
            del published[key]
            continue
        published[key] = value
    return published, review


def role_map_for_values(published: dict[int, float],
                        canonical: dict[int, dict]) -> dict[int, str]:
    """Port of the widget's roleMapForValues at the reference roster shape.

    Rows: canonical skill players with finite positive published value,
    sorted by value desc with the preseasonComparator ALL-branch tie-break
    (finite preseason rank asc, missing last; then position order, name,
    player_key). Top teams*slots per position -> starter; then top
    teams*FLEX of remaining flex-eligible -> starter; then top teams*BENCH
    of the rest (any position) -> bench. Everyone else is waiver (no role).
    """
    rows = []
    for key, value in published.items():
        player = canonical.get(key)
        if player is None or not math.isfinite(value) or not (value > 0):
            continue
        rows.append({"key": key, "value": value, "player": player})
    pos_order = {pos: i for i, pos in enumerate(POSITION_ORDER)}

    def sort_key(r):
        rank = r["player"]["preseason_rank"]
        return (-r["value"],
                0 if rank is not None else 1,
                rank if rank is not None else 0,
                pos_order[r["player"]["pos"]],
                r["player"]["name"].lower(),
                r["key"])

    rows.sort(key=sort_key)
    roles: dict[int, str] = {}
    for pos in POSITION_ORDER:
        for r in [r for r in rows if r["player"]["pos"] == pos][: ROLE_TEAMS * ROLE_ROSTER[pos]]:
            roles[r["key"]] = "starter"
    flex_rows = [r for r in rows
                 if r["player"]["pos"] in ROLE_FLEX_ELIGIBLE and r["key"] not in roles]
    for r in flex_rows[: ROLE_TEAMS * ROLE_ROSTER["FLEX"]]:
        roles[r["key"]] = "starter"
    rest = [r for r in rows if r["key"] not in roles]
    for r in rest[: ROLE_TEAMS * ROLE_ROSTER["BENCH"]]:
        roles[r["key"]] = "bench"
    return roles


def fit_cells(published: dict[int, float], roles: dict[int, str],
              leg_values: dict[int, float],
              canonical: dict[int, dict]) -> tuple[list[dict], dict]:
    """OLS per (position, tier); mirrors the widget's refitLiveCells guards."""
    cells: list[dict] = []
    diagnostics: dict[str, dict] = {}
    for pos in POSITION_ORDER:
        for tier in ("starter", "bench"):
            xs, ys = [], []
            for key, x in published.items():
                player = canonical.get(key)
                if player is None or player["pos"] != pos:
                    continue
                if roles.get(key) != tier:
                    continue
                y = leg_values.get(key)
                if not math.isfinite(x) or y is None or not math.isfinite(y):
                    continue
                xs.append(x)
                ys.append(y)
            info = {"n_pairs": len(xs), "cell": False, "reason": None}
            if len(xs) < MIN_FIT_PAIRS:
                # Subsumes the widget's own <2-pairs guard (MIN_FIT_PAIRS >= 2).
                info["reason"] = f"fewer_than_{MIN_FIT_PAIRS}_pairs"
            else:
                n = len(xs)
                mx = sum(xs) / n
                my = sum(ys) / n
                sxx = sum((v - mx) ** 2 for v in xs)
                sxy = sum((xs[i] - mx) * (ys[i] - my) for i in range(n))
                if not (sxx > 0):
                    info["reason"] = "zero_x_variance"
                else:
                    beta = sxy / sxx
                    alpha = my - beta * mx
                    if not (math.isfinite(alpha) and math.isfinite(beta)):
                        info["reason"] = "non_finite_coefficients"
                    elif not (beta > 0):
                        # A negative slope inverts the source's own ordering;
                        # never publish an inverting adjustment map.
                        info["reason"] = "non_positive_slope"
                    else:
                        cells.append({"source": None, "position": pos, "tier": tier,
                                      "alpha": alpha, "beta": beta, "n": n,
                                      "x_mean": mx, "y_mean": my})
                        info.update({"cell": True, "alpha": alpha, "beta": beta,
                                     "x_mean": mx, "y_mean": my})
            diagnostics[f"{pos}|{tier}"] = info
    return cells, diagnostics


def build_inputs(ddf_dir: Path, fixture_path: Path, players_path: Path) -> dict:
    leg_path = find_leg(ddf_dir)
    leg = json.loads(leg_path.read_text(encoding="utf-8"))
    if leg.get("schema") != "trade-value-ddf-leg-v1":
        raise SystemExit(f"Fail closed: {leg_path} is not a DDF leg artifact.")
    leg_values = {int(v["player_key"]): float(v["value"]) for v in leg["values"]}
    if any(not math.isfinite(y) or y < 0 for y in leg_values.values()):
        raise SystemExit("Fail closed: DDF leg carries non-finite or negative values.")

    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    players_doc = json.loads(players_path.read_text(encoding="utf-8"))
    canonical = load_canonical(players_doc)
    if not canonical:
        raise SystemExit(f"Fail closed: no canonical players in {players_path}.")

    sources_out: dict[str, dict] = {}
    review_rows: list[dict] = list(leg.get("review_rows") or [])
    any_cells = False
    for source, combo_name in REFERENCE_COMBOS.items():
        section = (fixture.get("sources") or {}).get(source) or {}
        combo = (section.get("combos") or {}).get(combo_name)
        if not combo:
            sources_out[source] = {
                "status": "pending-stage2",
                "reference_combo": combo_name,
                "cells": [],
                "diagnostics": {"reason": f"reference combo {combo_name} missing from fixture"},
            }
            review_rows.append({"reason": "missing_reference_combo", "source": source,
                                "reference_combo": combo_name})
            continue
        published, pub_review = build_published_source_map(source, fixture, canonical)
        review_rows.extend(pub_review)
        roles = role_map_for_values(published, canonical)
        cells, diagnostics = fit_cells(published, roles, leg_values, canonical)
        for cell in cells:
            cell["source"] = source
        status = "live" if cells else "pending-stage2"
        any_cells = any_cells or bool(cells)
        role_counts = {"starter": sum(1 for r in roles.values() if r == "starter"),
                       "bench": sum(1 for r in roles.values() if r == "bench")}
        sources_out[source] = {
            "status": status,
            "reference_combo": combo_name,
            "n_published": len(published),
            "role_counts": role_counts,
            "cells": cells,
            "diagnostics": diagnostics,
        }

    inputs_meta = leg["inputs"]
    return {
        "schema": SCHEMA,
        "version": leg["bake_id"],
        "status": "live" if any_cells else "pending-stage2",
        "generated_at": utc_now(),
        "fit": {
            "ddf_leg_bake_id": leg["bake_id"],
            "ddf_leg_path": str(leg_path.relative_to(ROOT)),
            "ddf_leg_sha256": sha256_file(leg_path),
            "espn_snapshot_date": inputs_meta["espn_snapshot_date"],
            "espn_purity_note": ("y targets are the DDF two-tier leg built from "
                                 "ESPN projections only (no expert blending)."),
            "scoring": inputs_meta["scoring"],
            "teams": inputs_meta["teams"],
            "bench_share": inputs_meta["bench_share"],
            "fixture": str(fixture_path.relative_to(ROOT)),
            "fixture_players": str(players_path.relative_to(ROOT)),
            "fixture_built_at": (fixture.get("meta") or {}).get("built_at"),
            "reference_combos": dict(REFERENCE_COMBOS),
            "combo_note": ("Matches the chart's default Full-PPR 12-team view "
                           "(comboKey: ppr -> 'full'; fantasycalc takes the _qb1 variant)."),
            "role_config": {
                "teams": ROLE_TEAMS, "roster": ROLE_ROSTER,
                "note": ("Roles are assigned from each source's OWN published values "
                         "at the reference shape; the widget applies baked cells by "
                         "(position, role) under whatever roster shape is active at "
                         "render time."),
            },
            "pie_source": inputs_meta["pies_file"],
            "pie_vintage": inputs_meta.get("pies_vintage"),
        },
        "sources": sources_out,
        "stage2_cell_format": {
            "position": "QB | RB | WR | TE",
            "tier": "starter | bench (the render-time role under the reference roster shape; waiver players are never adjusted)",
            "alpha": "intercept of the affine fit (full precision)",
            "beta": "slope of the affine fit (full precision)",
            "n": "fit pairs used",
            "x_mean": "mean published value over the fit pairs",
            "y_mean": "mean DDF leg value over the fit pairs",
            "application": "adjusted = max(0, alpha + beta * published_value)",
            "target": "the DDF two-tier value-above-waivers leg (ESPN projections only, 70/max scaled, full precision)",
        },
        "review_rows": review_rows,
        "summary": {
            "sources_live": sum(1 for s in sources_out.values() if s["status"] == "live"),
            "cells_total": sum(len(s["cells"]) for s in sources_out.values()),
            "review_rows": len(review_rows),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ddf-dir", type=Path, default=DEFAULT_LEG_DIR)
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--players", type=Path, default=DEFAULT_PLAYERS)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--live-asset", type=Path, default=LIVE_ASSET)
    parser.add_argument("--no-live", action="store_true",
                        help="Write only the versioned copy; do not touch the live asset.")
    args = parser.parse_args()

    if not args.fixture.is_file():
        raise SystemExit(f"Fixture not found: {args.fixture}")
    if not args.players.is_file():
        raise SystemExit(f"Players fixture not found: {args.players}")

    payload = build_inputs(args.ddf_dir, args.fixture, args.players)
    version = payload["version"]
    versioned_dir = args.output_dir / version
    versioned_dir.mkdir(parents=True, exist_ok=True)
    versioned_path = versioned_dir / f"adjustment-inputs-{version}.json"
    versioned_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote versioned adjustment inputs {version} -> {versioned_path}")

    if not args.no_live:
        args.live_asset.parent.mkdir(parents=True, exist_ok=True)
        args.live_asset.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"Wrote live asset -> {args.live_asset}")

    summary = payload["summary"]
    live = [s for s, e in payload["sources"].items() if e["status"] == "live"]
    print(f"Status: {payload['status']}; live sources: {live}; "
          f"cells: {summary['cells_total']}; review rows: {summary['review_rows']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
