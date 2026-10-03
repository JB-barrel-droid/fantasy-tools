#!/usr/bin/env python3
"""JEG-242: Transform shared-batch70-views-v1 into the comparison-data view contract.

The new as-published VORP pipeline (build_imputed_vorps.py +
build_reweighted_values.py, orchestrated by run_as_published_vorp.py and
gated by review_batch70_views.py) produces shared-batch70-views-v1 candidates
with three views per source: indexed (native publisher values), vorp (imputed
value above waivers), adj_values (0-70 shared-model chart values).

This transformer bridges those candidates into comparison-sources-data.json in
the exact shape the chart's JEG-210 view toggle consumes:
  sources[<as-published source>].vorp_views = {
      schema: "vorp-views-v1", scoring, teams, batch_sha256,
      candidate_status, generated_at,
      views: {indexed: {display_name: value},
              vorp: {display_name: value},
              adj_values: {display_name: value}}}

Keys are display names resolved through the comparison payload's own
player_keys table (canonical numeric key -> display name), the same mapping
the dashboard widgets use. Values are carried at full pipeline precision;
rounding is a display-layer concern.

Fail-closed:
  - batch70 schema must be shared-batch70-views-v1.
  - scoring/teams must be present on the candidate manifest (the views are
    only valid for the roster configuration that produced them; the widget
    gates rendering on an exact scoring/teams match).
  - any batch70 player key that does not resolve through player_keys aborts
    and names the key (no silent drops, no invented names).
  - a batch70 source with no SOURCE_MAP entry is skipped with an explicit
    reason recorded in the transform manifest (never silently admitted).

Usage:
    python3 pipelines/transform_batch70_to_comparison.py \
        --batch70 <shared-batch70-views-v1 candidate.json> \
        --comparison <comparison-sources-data.json> \
        --out <output.json>
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = "vorp-views-v1"
BATCH70_SCHEMA = "shared-batch70-views-v1"

# Map pipeline source names to comparison data source keys.
# Note: the pipeline uses "usat" but comparison data uses "usatoday".
SOURCE_MAP = {
    "fantasycalc": "fantasycalc",
    "usat": "usatoday",
    "fantasypros": "fantasypros",
    "cbs": "cbs",
}

VIEW_KEYS = ("indexed", "vorp", "adj_values")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _invert_player_keys(player_keys: dict) -> dict[str, str]:
    """Invert display-name -> canonical-key into canonical-key -> display-name."""
    inverted: dict[str, str] = {}
    for name, key in player_keys.items():
        number = int(key)  # canonical keys are positive ints; fail closed otherwise
        if number <= 0:
            raise ValueError(f"non-positive canonical key for {name!r}")
        token = str(number)
        if token in inverted:
            raise ValueError(f"duplicate display name in player_keys: {name!r}")
        inverted[token] = name
    return inverted


def _map_view(view: dict, key_to_name: dict[str, str], source: str, view_name: str) -> dict[str, float]:
    if not isinstance(view, dict):
        raise ValueError(f"{source}/{view_name}: view must be a player mapping")
    mapped: dict[str, float] = {}
    for canon_key, value in view.items():
        name = key_to_name.get(str(canon_key))
        if name is None:
            raise ValueError(
                f"{source}/{view_name}: canonical key {canon_key!r} has no "
                f"display name in comparison player_keys; refusing to drop it")
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise ValueError(f"{source}/{view_name}: non-numeric value for {name!r}")
        if name in mapped:
            raise ValueError(f"{source}/{view_name}: duplicate display name {name!r}")
        mapped[name] = value
    return mapped


def transform(batch70_path: Path, comparison_path: Path, out_path: Path) -> int:
    batch70_bytes = batch70_path.read_bytes()
    batch70 = json.loads(batch70_bytes)
    comparison = json.loads(comparison_path.read_text())

    if batch70.get("schema") != BATCH70_SCHEMA:
        print(f"ERROR: expected {BATCH70_SCHEMA} schema, got {batch70.get('schema')!r}",
              file=sys.stderr)
        return 1

    manifest = batch70.get("manifest")
    if not isinstance(manifest, dict):
        print("ERROR: candidate has no manifest; refusing to transform an "
              "unreviewed artifact", file=sys.stderr)
        return 1
    configuration = manifest.get("configuration")
    if (not isinstance(configuration, dict)
            or not isinstance(configuration.get("scoring"), str)
            or not isinstance(configuration.get("teams"), int)):
        print("ERROR: candidate manifest lacks scoring/teams configuration; "
              "views are only valid for the roster configuration that produced them",
              file=sys.stderr)
        return 1
    scoring, teams = configuration["scoring"], configuration["teams"]

    player_keys = comparison.get("player_keys")
    if not isinstance(player_keys, dict) or not player_keys:
        print("ERROR: comparison payload has no player_keys table", file=sys.stderr)
        return 1
    try:
        key_to_name = _invert_player_keys(player_keys)
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    batch_sources = batch70.get("sources")
    if not isinstance(batch_sources, dict) or not batch_sources:
        print("ERROR: candidate has no sources", file=sys.stderr)
        return 1

    comp_sources = comparison.get("sources")
    if not isinstance(comp_sources, dict):
        print("ERROR: comparison payload has no sources", file=sys.stderr)
        return 1

    generated_at = datetime.now(timezone.utc).isoformat()
    per_source: dict[str, dict] = {}
    try:
        for pipe_src, views in batch_sources.items():
            comp_src = SOURCE_MAP.get(pipe_src)
            if comp_src is None:
                per_source[pipe_src] = {"status": "skipped",
                                        "reason": "no comparison source mapping"}
                print(f"  Skip {pipe_src}: no comparison source mapping", file=sys.stderr)
                continue
            if comp_src not in comp_sources:
                per_source[pipe_src] = {"status": "skipped",
                                        "reason": "absent from comparison sources"}
                print(f"  Skip {comp_src}: not in comparison data", file=sys.stderr)
                continue
            if not isinstance(views, dict):
                raise ValueError(f"{pipe_src}: malformed source views")
            mapped_views = {}
            for view_name in VIEW_KEYS:
                if view_name not in views:
                    raise ValueError(f"{pipe_src}: candidate missing {view_name} view")
                mapped_views[view_name] = _map_view(views[view_name], key_to_name,
                                                    pipe_src, view_name)
            comp_sources[comp_src]["vorp_views"] = {
                "schema": SCHEMA,
                "scoring": scoring,
                "teams": teams,
                "batch_sha256": hashlib.sha256(batch70_bytes).hexdigest(),
                "candidate_status": batch70.get("artifact_status", "unknown"),
                "generated_at": generated_at,
                "source": comp_src,
                "views": mapped_views,
            }
            per_source[pipe_src] = {"status": "updated", "comparison_source": comp_src,
                                    "n_players": len(mapped_views["indexed"])}
            print(f"  Updated {comp_src}.vorp_views "
                  f"({len(mapped_views['indexed'])} players, {scoring}/{teams}t)",
                  file=sys.stderr)
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    comparison["_jeg242_transform"] = {
        "transformed_at": generated_at,
        "transformer": "pipelines/transform_batch70_to_comparison.py",
        "batch70_schema": BATCH70_SCHEMA,
        "batch_sha256": hashlib.sha256(batch70_bytes).hexdigest(),
        "sources": per_source,
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(comparison, indent=2, sort_keys=True) + "\n")
    updated = sum(1 for s in per_source.values() if s["status"] == "updated")
    print(f"Wrote {out_path} ({updated} sources updated, "
          f"{len(per_source) - updated} skipped)", file=sys.stderr)
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--batch70", type=Path, required=True,
                    help="shared-batch70-views-v1 candidate JSON")
    ap.add_argument("--comparison", type=Path, required=True,
                    help="comparison-sources-data.json to bridge into")
    ap.add_argument("--out", type=Path, required=True,
                    help="Output path (candidate copy; promotion is separate)")
    args = ap.parse_args(argv)
    return transform(args.batch70, args.comparison, args.out)


if __name__ == "__main__":
    sys.exit(main())
