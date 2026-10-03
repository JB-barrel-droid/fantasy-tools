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
4. Derives the configured league cohort size from the roster contract
   (12-team default = 168 rostered players), then selects that many highest
   available-source-mean VORP players from the FULL publisher union. The run
   fails closed if any player in that league cohort has fewer than min-sources,
   so a high-value single-source player cannot silently disappear from AVG.
5. Backstops every published source that is missing members of that league
   cohort. Deeper publisher-only rows remain untouched; no publisher is judged
   against another publisher's arbitrary list depth.
6. Outputs an augmented batch JSON including the "avg" source.

Group assignment for avg/backstopped records: majority vote across sources
that ranked the player (each source's imputation already assigned groups
via infer_roster). Ties break toward the higher-value role. Reweighting still
enforces the eight group budgets exactly; the majority vote is only the
lineage-explicit role assignment for rows a publisher did not rank.

Usage:
    python3 pipelines/backstop_shallow_sources.py \
        --batch <vorp-source-batch-v1.json> \
        --out-dir <dir> \
        [--coverage-threshold 1.0] \
        [--min-sources 2] \
        [--target-count 168]
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


def consensus_group(entries: list[tuple[str, float, str]]) -> str:
    """Assign an AVG row without allowing positive VORP to be labeled Cut."""
    positive_groups = [group for _source, vorp, group in entries if vorp > 0]
    return majority_group(
        positive_groups or [group for _source, _vorp, group in entries]
    )


def configured_target_count(publisher_roster: dict) -> int:
    """Rostered-player cohort size implied by option-c-publisher-roster-v1."""
    if not isinstance(publisher_roster, dict):
        raise ValueError("publisher_roster required to derive league target count")
    teams = publisher_roster.get("teams")
    slots = publisher_roster.get("slots")
    flex_count = publisher_roster.get("flex_count")
    bench_total = publisher_roster.get("bench_total")
    if (type(teams) is not int or teams <= 0 or not isinstance(slots, dict)
            or set(slots) != {"QB", "RB", "WR", "TE"}
            or any(type(v) is not int or v < 0 for v in slots.values())
            or type(flex_count) is not int or flex_count < 0
            or type(bench_total) is not int or bench_total < 0):
        raise ValueError("invalid publisher_roster for league target derivation")
    return teams * (sum(slots.values()) + flex_count) + bench_total


def _cohort_sha(keys: list[str]) -> str:
    payload = ("\n".join(keys) + "\n").encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--batch", type=Path, required=True,
                    help="vorp-source-batch-v1 JSON")
    ap.add_argument("--out-dir", type=Path, required=True,
                    help="Output directory for avg artifact + augmented batch")
    ap.add_argument("--coverage-threshold", type=float, default=1.0,
                    help="Backstop when a source covers less than this fraction of the configured league cohort")
    ap.add_argument("--min-sources", type=int, default=2,
                    help="Minimum sources ranking a player for avg inclusion")
    ap.add_argument("--target-count", type=int, default=None,
                    help="Override configured league cohort size (tests/audits only)")
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
    source_pins = {}
    first_manifest = None
    for source in present:
        values, manifest = load_imputed(batch_path, source)
        imputed[source] = values
        if first_manifest is None:
            first_manifest = manifest
        entry = batch["sources"][source]
        values_path = batch_path.parent / entry["values"]
        manifest_path = batch_path.parent / entry["manifest"]
        source_pins[source] = {
            "values_sha256": hashlib.sha256(values_path.read_bytes()).hexdigest(),
            "manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        }
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

    # Build a union score first. Target selection must not happen AFTER
    # min-sources filtering, or a high-value player ranked by one publisher can
    # silently disappear from the 168-player league cohort.
    consensus_candidates = {}
    for pkey, entries in players.items():
        vorps = [e[1] for e in entries]
        consensus_candidates[pkey] = {
            "group": consensus_group(entries),
            "imputed_vorp": sum(vorps) / len(vorps),
            "native": None,
            "avg_sources": sorted(e[0] for e in entries),
            "avg_n": len(entries),
        }

    target_count = args.target_count if args.target_count is not None else configured_target_count(
        first_manifest.get("publisher_roster") if first_manifest else None
    )
    if type(target_count) is not int or target_count <= 0:
        raise ValueError("target_count must be a positive integer")
    if len(consensus_candidates) < target_count:
        raise ValueError(
            f"published union covers only {len(consensus_candidates)} players; "
            f"configured league cohort requires {target_count}"
        )
    target_keys = [
        pkey for pkey, _rec in sorted(
            consensus_candidates.items(),
            key=lambda item: (-item[1]["imputed_vorp"], str(item[0])),
        )[:target_count]
    ]
    target_holes = [
        pkey for pkey in target_keys
        if consensus_candidates[pkey]["avg_n"] < args.min_sources
    ]
    if target_holes:
        preview = ", ".join(target_holes[:10])
        suffix = "" if len(target_holes) <= 10 else f" (+{len(target_holes) - 10} more)"
        raise ValueError(
            f"league cohort has {len(target_holes)} player(s) below min_sources="
            f"{args.min_sources}: {preview}{suffix}; refusing to silently drop them"
        )

    # AVG can include every player meeting the consensus threshold, not just
    # the target cohort. Full precision is preserved; rounding is display-only.
    avg_pool = {
        pkey: rec for pkey, rec in consensus_candidates.items()
        if rec["avg_n"] >= args.min_sources
    }
    target_key_set = set(target_keys)
    target_sha = _cohort_sha(target_keys)

    print(
        f"  avg: {len(avg_pool)} players (from {len(present)} sources); "
        f"league cohort: {target_count}",
        file=sys.stderr,
    )

    # Write avg artifact + manifest
    avg_values_path = out_dir / "avg.imputed.json"
    avg_json = json.dumps(avg_pool, indent=2, sort_keys=True, allow_nan=False) + "\n"
    avg_values_path.write_text(avg_json, encoding="utf-8")
    # Inherit publisher_roster from the first source (all share the batch config)
    avg_manifest = {
        "schema": "option-c-imputation-manifest-v1",
        "method": "cross-source-average-v1",
        "description": "Per-player mean imputed VORP across published sources; Jeremy 2026-10-03",
        "input_sources": sorted(present),
        "input_pins": source_pins,
        "min_sources": args.min_sources,
        "publisher_roster": first_manifest.get("publisher_roster"),
        "target_policy": "top-available-source-average-vorp-v1",
        "target_selection_universe": "all-published-union",
        "target_count": target_count,
        "target_sha256": target_sha,
        "group_assignment": "cross-source-positive-majority-vote-v1",
        "output_sha256": hashlib.sha256(avg_json.encode("utf-8")).hexdigest(),
    }
    avg_manifest_path = out_dir / "avg.imputed.manifest.json"
    avg_manifest_path.write_text(json.dumps(avg_manifest, indent=2, sort_keys=True) + "\n")

    # Backstop sources against the configured league cohort, never against
    # another publisher's arbitrary list depth.
    augmented_sources = dict(batch["sources"])
    backstop_report = {}

    for source in present:
        pool = imputed[source]
        target_present = sum(1 for pkey in target_keys if pkey in pool)
        coverage = target_present / target_count if target_count else 0
        if coverage >= args.coverage_threshold:
            print(
                f"  {source}: league-cohort coverage {coverage:.1%} -- no backstop needed",
                file=sys.stderr,
            )
            continue

        # Preserve original manifest's roster config
        _, orig_manifest = load_imputed(batch_path, source)

        # Fill missing players from avg
        backstopped = dict(pool)  # shallow copy; values are dicts we won't mutate
        filled = 0
        for pkey in target_keys:
            avg_rec = avg_pool[pkey]
            if pkey not in backstopped:
                backstopped[pkey] = {
                    "group": avg_rec["group"],
                    "imputed_vorp": avg_rec["imputed_vorp"],
                    "native": None,
                    "backstopped_by": "avg",
                    "backstop_sources": avg_rec["avg_sources"],
                    "backstop_n": avg_rec["avg_n"],
                    "backstop_group_assignment": "cross-source-positive-majority-vote-v1",
                    "backstop_target_policy": "top-available-source-average-vorp-v1",
                }
                filled += 1

        # Write backstopped artifact
        bs_values_path = out_dir / f"{source}.backstopped.imputed.json"
        bs_json = json.dumps(backstopped, indent=2, sort_keys=True, allow_nan=False) + "\n"
        bs_values_path.write_text(bs_json, encoding="utf-8")
        bs_manifest = {
            "schema": "option-c-imputation-manifest-v1",
            "method": "eight-group-proportional-v1+avg-backstop-v1",
            "description": f"Native {source} imputation with avg backstop for missing players",
            "publisher_roster": orig_manifest.get("publisher_roster"),
            "backstop_filled": filled,
            "backstop_source": "avg",
            "backstop_target_count": target_count,
            "backstop_target_sha256": target_sha,
            "backstop_target_policy": "top-available-source-average-vorp-v1",
            "backstop_group_assignment": "cross-source-positive-majority-vote-v1",
            "input_source_values_sha256": source_pins[source]["values_sha256"],
            "input_source_manifest_sha256": source_pins[source]["manifest_sha256"],
            "avg_values_sha256": hashlib.sha256(avg_json.encode("utf-8")).hexdigest(),
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
            "target_players_present_before": target_present,
            "target_players_required": target_count,
            "target_coverage_before": coverage,
            "backstopped_players": filled,
            "target_players_present_after": sum(1 for pkey in target_key_set if pkey in backstopped),
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
    augmented_excluded = dict(batch.get("excluded_sources", {}))
    augmented_excluded.pop("avg", None)
    augmented["excluded_sources"] = augmented_excluded
    augmented["_backstop"] = {
        "method": "cross-source-average-v1",
        "target_policy": "top-available-source-average-vorp-v1",
        "target_selection_universe": "all-published-union",
        "target_count": target_count,
        "target_sha256": target_sha,
        "min_sources": args.min_sources,
        "group_assignment": "cross-source-positive-majority-vote-v1",
        "backstopped_sources": backstop_report,
        "avg_players": len(avg_pool),
    }

    out_batch = out_dir / "vorp-source-batch-augmented-v1.json"
    out_batch.write_text(json.dumps(augmented, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote augmented batch -> {out_batch}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
