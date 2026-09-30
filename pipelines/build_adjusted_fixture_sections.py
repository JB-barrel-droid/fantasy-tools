#!/usr/bin/env python3
"""Build _adjusted fixture sections from live adjustment cells.

Stage 8 of the repo pipeline (after Stage 7 fit): for each of
fantasycalc / usatoday / fantasypros / cbs, apply the fitted adjustment cells
from adjustment-inputs.json to the raw published values in each combo,
writing the result as {source}_adjusted sections in
data/fixtures/current/comparison-sources-data.json.

This restores the _adjusted sources that the comparison dashboard and
build_reference_data.py require, but with FRESH data from the current
fit — not the stale Week 2 bake that was removed.

The adjustment is deterministic: same cells + same inputs = same outputs.
Cells are (position, tier)-conditional affine maps:
    adjusted = max(0, alpha + beta * published_value)
Players without a cell for their (position, tier) keep their raw value
(exactly like the widget's buildLiveAdjustedMap fallback).

Fail-closed:
- If adjustment-inputs.json is missing or has no cells for a source,
  that source gets NO _adjusted section (and source_validation is NOT
  marked live for it). The dashboard's pause logic handles this.
- Unresolvable player identities are skipped, never guessed.
- Non-finite values are skipped.

Usage:
    python3 pipelines/build_adjusted_fixture_sections.py \
        [--fixture data/fixtures/current/comparison-sources-data.json] \
        [--inputs app/trade-value-chart/assets/adjustment-inputs.json] \
        [--players data/fixtures/current/players.json]
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))
from build_adjustment_inputs import (
    POSITION_ORDER,
    ROLE_ROSTER,
    ROLE_FLEX_ELIGIBLE,
    load_canonical,
    clamp_value,
)
import re


def role_map_for_teams(published: dict[int, float],
                       canonical: dict[int, dict],
                       n_teams: int) -> dict[int, str]:
    """Port of role_map_for_values with configurable team count.
    
    Mirrors the widget's roleMapForValues: starter/bench from each source's
    own published values at the given roster shape.
    """
    rows = []
    for key, value in published.items():
        player = canonical.get(key)
        if player is None:
            continue
        rows.append({"key": key, "value": value, "player": player})
    
    def sort_key(r):
        rank = r["player"].get("preseason_rank")
        try:
            rank = float(rank) if rank is not None else None
        except (TypeError, ValueError):
            rank = None
        pos_order = {p: i for i, p in enumerate(POSITION_ORDER)}
        return (-r["value"],
                0 if rank is not None else 1,
                rank if rank is not None else 0,
                pos_order.get(r["player"]["pos"], 99),
                r["player"].get("name", "").lower(),
                r["key"])
    
    rows.sort(key=sort_key)
    roles: dict[int, str] = {}
    for pos in POSITION_ORDER:
        pos_rows = [r for r in rows if r["player"]["pos"] == pos]
        for r in pos_rows[: n_teams * ROLE_ROSTER[pos]]:
            roles[r["key"]] = "starter"
    flex_rows = [r for r in rows
                 if r["player"]["pos"] in ROLE_FLEX_ELIGIBLE and r["key"] not in roles]
    for r in flex_rows[: n_teams * ROLE_ROSTER["FLEX"]]:
        roles[r["key"]] = "starter"
    rest = [r for r in rows if r["key"] not in roles]
    for r in rest[: n_teams * ROLE_ROSTER["BENCH"]]:
        roles[r["key"]] = "bench"
    return roles


def parse_teams_from_combo(combo_name: str) -> int:
    """Extract team count from combo name like 'full_12_qb1' or 'standard_8'."""
    m = re.search(r'_(\d+)(?:_|$)', combo_name)
    if m:
        try:
            return int(m.group(1))
        except ValueError:
            pass
    return 12  # default

DEFAULT_FIXTURE = ROOT / "data" / "fixtures" / "current" / "comparison-sources-data.json"
DEFAULT_INPUTS = ROOT / "app" / "trade-value-chart" / "assets" / "adjustment-inputs.json"
DEFAULT_PLAYERS = ROOT / "data" / "fixtures" / "current" / "players.json"

ADJUSTED_SOURCES = ["fantasycalc", "usatoday", "fantasypros", "cbs"]
# NOTE: "cbsros" (CBS rest-of-season projections) is intentionally NOT listed.
# The adjusted family carries bias-correction cells fitted against actuals from
# a prior season; no CBS-ROS cells have been fitted, so there is no
# cbsros_adjusted variant. (Same reason "espn" is absent.)

# Human-readable metadata for the _adjusted sources
ADJUSTED_META = {
    "fantasycalc": {
        "name": "FantasyCalc (bias-adjusted)",
        "kind": "crowd trade value chart, bias-corrected to our methodology",
    },
    "usatoday": {
        "name": "USA Today (bias-adjusted)",
        "kind": "editorial trade value chart, bias-corrected to our methodology",
    },
    "fantasypros": {
        "name": "FantasyPros (bias-adjusted)",
        "kind": "analyst-consensus trade value chart, bias-corrected to our methodology",
    },
    "cbs": {
        "name": "CBS (bias-adjusted)",
        "kind": "editorial trade value chart, bias-corrected to our methodology",
    },
}


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def build_adjusted_sections(fixture_path: Path, inputs_path: Path, players_path: Path) -> dict:
    """Generate _adjusted source sections. Returns stats dict."""
    fixture = load_json(fixture_path)
    inputs = load_json(inputs_path)
    players_data = load_json(players_path)

    # Canonical: player_key -> {pos, preseason_rank, name}
    # players.json has a different shape than fixture; adapt it
    canonical = {}
    players_list = players_data.get("players", [])
    for p in players_list:
        try:
            key = int(p.get("player_key"))
        except (TypeError, ValueError):
            continue
        pos = p.get("pos")
        if pos not in POSITION_ORDER:
            continue
        canonical[key] = {
            "pos": pos,
            "preseason_rank": p.get("preseasonRank") or p.get("preseason_ecr_rank"),
            "name": str(p.get("full_name") or p.get("name") or ""),
        }

    # player_keys: slug -> player_key (from fixture)
    player_keys = fixture.get("player_keys") or {}
    key_to_slug = {v: k for k, v in player_keys.items() if isinstance(v, int)}

    # Cells: source -> {(pos, tier): (alpha, beta)}
    cells_by_source = {}
    fit_bake_id = inputs.get("version") or inputs.get("fit", {}).get("ddf_leg_bake_id", "unknown")
    for source in ADJUSTED_SOURCES:
        entry = (inputs.get("sources") or {}).get(source) or {}
        cells = entry.get("cells") or []
        cell_map = {}
        for c in cells:
            pos = str(c.get("position", "")).upper()
            tier = str(c.get("tier", "")).lower()
            alpha = c.get("alpha")
            beta = c.get("beta")
            if pos in POSITION_ORDER and tier in ("starter", "bench"):
                if isinstance(alpha, (int, float)) and isinstance(beta, (int, float)):
                    if math.isfinite(alpha) and math.isfinite(beta) and beta > 0:
                        cell_map[(pos, tier)] = (float(alpha), float(beta))
        cells_by_source[source] = cell_map

    sources = fixture.get("sources") or {}
    source_validation = fixture.get("source_validation") or {}
    stats = {}

    for source in ADJUSTED_SOURCES:
        raw_source = sources.get(source)
        if not raw_source:
            stats[source] = {"status": "skipped", "reason": "raw source missing from fixture"}
            continue

        cell_map = cells_by_source[source]
        if not cell_map:
            stats[source] = {"status": "skipped", "reason": "no cells in adjustment-inputs.json"}
            # Ensure validation does NOT claim live
            if f"{source}_adjusted" in source_validation:
                del source_validation[f"{source}_adjusted"]
            # Remove stale section if present
            sources.pop(f"{source}_adjusted", None)
            continue

        # Build adjusted combos
        raw_combos = raw_source.get("combos") or {}
        adjusted_combos = {}
        total_players = 0

        for combo_name, combo in raw_combos.items():
            raw_values = combo.get("values") or combo.get("reindexed") or {}
            if not raw_values:
                continue

            # slug -> (player_key, raw_value)
            published = {}
            slug_for_key = {}
            for slug, raw_val in raw_values.items():
                key_raw = player_keys.get(slug)
                try:
                    key = int(key_raw)
                except (TypeError, ValueError):
                    continue
                player = canonical.get(key)
                val = clamp_value(raw_val)
                if player is None or val is None:
                    continue
                # Conflicting duplicates: keep first, skip rest (fail-closed)
                if key in published:
                    continue
                published[key] = val
                slug_for_key[key] = slug

            if not published:
                continue

            # Determine roles using the team count from the combo name
            # (e.g., 'full_12_qb1' -> 12 teams, 'standard_8' -> 8 teams)
            n_teams = parse_teams_from_combo(combo_name)
            roles = role_map_for_teams(published, canonical, n_teams)

            # Apply cells
            adjusted = {}
            native = {}
            for key, raw_val in published.items():
                player = canonical[key]
                pos = player["pos"]
                tier = roles.get(key)
                slug = slug_for_key[key]
                native[slug] = raw_val

                cell = cell_map.get((pos, tier)) if tier else None
                if cell:
                    alpha, beta = cell
                    adj_val = max(0.0, alpha + beta * raw_val)
                else:
                    # No cell for this (pos, tier): keep raw (widget fallback)
                    adj_val = raw_val
                adjusted[slug] = round(adj_val, 1)

            # The cells output DDF 70/max-scale values, but the comparison
            # fixture is pie-indexed: rescale each position's adjusted total
            # to the raw combo's pie target (fixed-pie invariant). Without
            # this the _adjusted series sits on a different scale than the
            # ESPN leg and the curves diverge.
            index_total = combo.get("index_total") or {}
            pos_totals: dict[str, float] = {}
            pos_slugs: dict[str, list[str]] = {}
            for slug, adj_val in adjusted.items():
                key = int(player_keys.get(slug, -1))
                player = canonical.get(key)
                if player is None:
                    continue
                pos = player["pos"]
                pos_totals[pos] = pos_totals.get(pos, 0.0) + adj_val
                pos_slugs.setdefault(pos, []).append(slug)
            for pos, total in pos_totals.items():
                target = (index_total.get(pos) or {}).get("target_total")
                if target and total > 0:
                    factor = target / total
                    for slug in pos_slugs[pos]:
                        adjusted[slug] = round(adjusted[slug] * factor, 1)

            adjusted_combos[combo_name] = {
                "reindexed": adjusted,
                "native": native,
                "fit": {"method": "bias_adjusted", "bake_id": fit_bake_id},
                "n": len(adjusted),
                # index_total carries over: after the rescale above, the
                # adjusted position totals match the raw pie targets exactly.
                "index_total": combo.get("index_total"),
            }
            total_players += len(adjusted)

        if not adjusted_combos:
            stats[source] = {"status": "skipped", "reason": "no combos with values"}
            continue

        # Build the _adjusted source entry
        meta = ADJUSTED_META[source]
        adjusted_key = f"{source}_adjusted"
        sources[adjusted_key] = {
            "name": meta["name"],
            "kind": meta["kind"],
            "position_coverage": raw_source.get("position_coverage"),
            "claimed_settings": raw_source.get("claimed_settings"),
            "value_provenance": "modeled",
            "provenance_note": (
                f"Published values corrected by the source_value_adjustments fit "
                f"({fit_bake_id}); players outside the fit universe keep published values. "
                f"Generated deterministically by pipelines/build_adjusted_fixture_sections.py."
            ),
            "update_cadence": raw_source.get("update_cadence"),
            "week_designated": raw_source.get("week_designated"),
            "url": raw_source.get("url"),
            "native_unit": raw_source.get("native_unit"),
            "fetched_at": raw_source.get("fetched_at"),
            "fit_bake_id": fit_bake_id,
            "combos": adjusted_combos,
        }
        source_validation[adjusted_key] = "live"
        stats[source] = {
            "status": "built",
            "combos": len(adjusted_combos),
            "players": total_players,
            "fit_bake_id": fit_bake_id,
        }

    fixture["sources"] = sources
    fixture["source_validation"] = source_validation

    # Write back
    fixture_path.write_text(json.dumps(fixture, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    return stats


def main() -> int:
    ap = argparse.ArgumentParser(description="Build _adjusted fixture sections from live cells")
    ap.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    ap.add_argument("--inputs", type=Path, default=DEFAULT_INPUTS)
    ap.add_argument("--players", type=Path, default=DEFAULT_PLAYERS)
    args = ap.parse_args()

    for path, label in [(args.fixture, "fixture"), (args.inputs, "inputs"), (args.players, "players")]:
        if not path.exists():
            print(f"Fail closed: {label} not found: {path}", file=sys.stderr)
            return 1

    stats = build_adjusted_sections(args.fixture, args.inputs, args.players)
    print(json.dumps(stats, indent=2))

    # Fail closed: all three sources must be built
    failed = [s for s, st in stats.items() if st.get("status") != "built"]
    if failed:
        print(f"Fail closed: missing _adjusted sections for: {', '.join(failed)}", file=sys.stderr)
        return 1
    print("✓ All _adjusted fixture sections built")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
