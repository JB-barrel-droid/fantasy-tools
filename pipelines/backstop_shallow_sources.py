#!/usr/bin/env python3
"""JEG-242: Cross-source average line + backstop for shallow publisher lists.

Jeremy (2026-10-03): "we need to populate all players in a league, we can
create an avg across sources as another set of lines and then create a cb
backstopped by avg for their lines"

This stage runs between imputation and reweight:
1. Loads imputed VORPs for all "published" sources from a vorp-source-batch-v1.
2. Computes per-player average imputed VORP across sources (VORP units are
   comparable; native publisher units are not).
3. Writes an "avg" source artifact -- a real line on the chart.
4. For any published source below the coverage threshold (e.g. CBS with ~104
   players vs 168 needed), fills missing players from the avg line, marked
   as backstopped in lineage.
5. Outputs an augmented batch JSON including the "avg" source.

Group assignment for avg/backstopped records: majority vote across sources
that ranked the player (each source's imputation already assigned groups
via infer_roster). Ties break toward the higher-value role.

Usage:
    python3 pipelines/backstop_shallow_sources.py \
        --batch <vorp-source-batch-v1.json> \
        --out-dir <dir> \
        [--coverage-threshold 0.9] \
        [--min-sources 2]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))

# Published sources eligible for averaging (must match SOURCE_KINDS "published")
PUBLISHED_SOURCES = ("fantasycalc", "usat", "fantasypros", "cbs")

# Role priority for tie-breaking (higher value role wins)
ROLE_PRIORITY = {"starter": 3, "bench": 2, "cut": 1}


def _unique_object(pairs):
    d = {}
    for k, v in pairs:
        if k in d:
            raise ValueError(f"duplicate key: {k}")
        d[k] = v
    return d


def load_imputed(batch_path: Path, source: str) -> dict:
    """Load imputed VORP artifact for a source from the batch."""
    batch = json.loads(batch_path.read_bytes(), object_pairs_hook=_unique_object)
    entry = batch["sources"][source]
    values_path = batch_path.parent / entry["values"]
    manifest_path = batch_path.parent / entry["manifest"]
    values = json.loads(values_path.read_bytes(), object_pairs_hook=_unique_object)
    manifest = json.loads(manifest_path.read_bytes(), object_pairs_hook=_unique_object)
    # Verify hash
    digest = hashlib.sha256(values_path.read_bytes()).hexdigest()
    if manifest.get("output_sha256") != digest:
        raise ValueError(f"hash mismatch for {source}")
    return values, manifest


def majority_group(groups: list[str]) -> str:
    """Majority vote on group; ties break toward higher-value role."""
    counts = Counter(groups)
    best = max(counts, key=lambda g: (counts[g], ROLE_PRIORITY.get(g.split("|")[1].lower(), 0)))
    return best


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--batch", type=Path, required=True,
                    help="vorp-source-batch-v1 JSON")
    ap.add_argument("--out-dir", type=Path, required=True,
                    help="Output directory for avg artifact + augmented batch")
    ap.add_argument("--coverage-threshold", type=float, default=0.9,
                    help="Sources below this fraction of max coverage get backstopped")
    ap.add_argument("--min-sources", type=int, default=2,
                    help="Minimum sources ranking a player for avg inclusion")
    args = ap.parse_args(argv)

    batch_path = args.batch
    out_dir = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    # Load imputed VORPs for all published sources present in batch
    batch = json.loads(batch_path.read_bytes(), object_pairs_hook=_unique_object)
    present = [s for s in PUBLISHED_SOURCES if s in batch.get("sources", {})]
    if len(present) < 2:
        print("ERROR: need at least 2 published sources for averaging", file=sys.stderr)
        return 1

    imputed = {}
    for source in present:
        values, _ = load_imputed(batch_path, source)
        imputed[source] = values
        print(f"  {source}: {len(values)} players", file=sys.stderr)

    # Per-player: collect (source, imputed_vorp, group)
    players: dict[str, list[tuple[str, float, str]]] = {}
    for source, pool in imputed.items():
        for pkey, rec in pool.items():
            vorp = rec.get("imputed_vorp")
            group = rec.get("group")
            if not isinstance(vorp, (int, float)) or vorp < 0:
                continue
            if not isinstance(group, str) or "|" not in group:
                continue
            players.setdefault(pkey, []).append((source, float(vorp), group))

    # Build avg source: mean imputed VORP, majority-vote group
    avg_pool = {}
    for pkey, entries in players.items():
        if len(entries) < args.min_sources:
            continue
        vorps = [e[1] for e in entries]
        avg_vorp = sum(vorps) / len(vorps)
        group = majority_group([e[2] for e in entries])
        # Position from group
        pos = group.split("|")[0]
        avg_pool[pkey] = {
            "group": group,
            "imputed_vorp": round(avg_vorp, 4),
            "native": None,  # avg has no native publisher value
            "avg_sources": sorted(e[0] for e in entries),
            "avg_n": len(entries),
        }

    print(f"  avg: {len(avg_pool)} players (from {len(present)} sources)", file=sys.stderr)

    # Write avg artifact + manifest
    avg_values_path = out_dir / "avg.imputed.json"
    avg_json = json.dumps(avg_pool, indent=2, sort_keys=True, allow_nan=False)
    avg_values_path.write_text(avg_json + "\n", encoding="utf-8")
    # Inherit publisher_roster from the first source (all share the batch config)
    _, first_manifest = load_imputed(batch_path, present[0])
    avg_manifest = {
        "schema": "option-c-imputation-manifest-v1",
        "method": "cross-source-average-v1",
        "description": "Per-player mean imputed VORP across published sources; Jeremy 2026-10-03",
        "input_sources": sorted(present),
        "min_sources": args.min_sources,
        "publisher_roster": first_manifest.get("publisher_roster"),
        "output_sha256": hashlib.sha256(avg_json.encode("utf-8")).hexdigest(),
    }
    avg_manifest_path = out_dir / "avg.imputed.manifest.json"
    avg_manifest_path.write_text(json.dumps(avg_manifest, indent=2, sort_keys=True) + "\n")

    # Backstop shallow sources
    max_coverage = max(len(pool) for pool in imputed.values())
    augmented_sources = dict(batch["sources"])
    backstop_report = {}

    for source in present:
        pool = imputed[source]
        coverage = len(pool) / max_coverage if max_coverage else 0
        if coverage >= args.coverage_threshold:
            print(f"  {source}: coverage {coverage:.1%} -- no backstop needed", file=sys.stderr)
            continue

        # Preserve original manifest's roster config
        _, orig_manifest = load_imputed(batch_path, source)

        # Fill missing players from avg
        backstopped = dict(pool)  # shallow copy; values are dicts we won't mutate
        filled = 0
        for pkey, avg_rec in avg_pool.items():
            if pkey not in backstopped:
                backstopped[pkey] = {
                    "group": avg_rec["group"],
                    "imputed_vorp": avg_rec["imputed_vorp"],
                    "native": None,
                    "backstopped_by": "avg",
                    "backstop_sources": avg_rec["avg_sources"],
                }
                filled += 1

        # Write backstopped artifact
        bs_values_path = out_dir / f"{source}.backstopped.imputed.json"
        bs_json = json.dumps(backstopped, indent=2, sort_keys=True, allow_nan=False)
        bs_values_path.write_text(bs_json + "\n", encoding="utf-8")
        bs_manifest = {
            "schema": "option-c-imputation-manifest-v1",
            "method": "eight-group-proportional-v1+avg-backstop-v1",
            "description": f"Native {source} imputation with avg backstop for missing players",
            "publisher_roster": orig_manifest.get("publisher_roster"),
            "backstop_filled": filled,
            "backstop_source": "avg",
            "output_sha256": hashlib.sha256(bs_json.encode("utf-8")).hexdigest(),
        }
        bs_manifest_path = out_dir / f"{source}.backstopped.imputed.manifest.json"
        bs_manifest_path.write_text(json.dumps(bs_manifest, indent=2, sort_keys=True) + "\n")

        # Point batch at backstopped artifact (relative paths)
        augmented_sources[source] = {
            "values": bs_values_path.name,
            "manifest": bs_manifest_path.name,
        }
        backstop_report[source] = {
            "native_players": len(pool),
            "backstopped_players": filled,
            "total_players": len(backstopped),
        }
        print(f"  {source}: backstopped {filled} players (native {len(pool)} -> total {len(backstopped)})",
              file=sys.stderr)

    # Add avg source to batch
    # Use relative paths from batch location; out_dir may differ from batch parent
    # For simplicity, require out_dir == batch parent or use absolute resolution
    augmented_sources["avg"] = {
        "values": avg_values_path.name,
        "manifest": avg_manifest_path.name,
    }

    augmented = dict(batch)
    augmented["sources"] = augmented_sources
    # avg is a published-kind source for reweight purposes
    augmented["_backstop"] = {
        "method": "cross-source-average-v1",
        "backstopped_sources": backstop_report,
        "avg_players": len(avg_pool),
    }

    out_batch = out_dir / "vorp-source-batch-augmented-v1.json"
    out_batch.write_text(json.dumps(augmented, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote augmented batch -> {out_batch}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
