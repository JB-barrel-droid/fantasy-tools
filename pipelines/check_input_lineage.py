#!/usr/bin/env python3
"""JEG-132 R5b: input lineage mismatch checker.

Detects derived sections that lag their raw input. The sibling R5a writers
stamp an immutable `lineage` block (raw_vintage, raw_content_sha256,
raw_built_at, vintage_source) onto every derived section at build time.
This checker recomputes what the raw input currently looks like and compares
it against what each derived section claims.

Derived sections covered (all R5a-stamped):
  - {fantasycalc, usatoday, fantasypros, cbs}_adjusted -> parent raw fixture section
  - cbsros / espn / razzingball                      -> freshest DDF leg file
  - comparison candidates (output/comparison-candidates/*.json) -> reference artifact(s)

Raw sections (fantasycalc, usatoday, fantasypros, cbs) MUST NOT carry a
lineage block (they are inputs, not derivations). A missing lineage block
on a derived section is a mismatch (missing provenance is not a pass).

CLI:
  python3 pipelines/check_input_lineage.py [--fixture PATH]

Exit codes:
  0 = every derived section's lineage matches the current raw input.
  1 = at least one mismatch (named in output/input-lineage.json).

Side effect: writes output/input-lineage.json (the monitor surface). Never
touches dist/modules/pipeline-checkpoints.json (the dispatcher's R5c wiring
is a different beat).
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PIPELINES = ROOT / "pipelines"
LIB = PIPELINES / "lib"
DEFAULT_FIXTURE = ROOT / "data" / "fixtures" / "current" / "comparison-sources-data.json"
DEFAULT_OUTPUT = ROOT / "output" / "input-lineage.json"
LEG_DIR = ROOT / "data" / "ddf-two-tier"
CANDIDATES_DIR = ROOT / "output" / "comparison-candidates"

# Make lib importable regardless of how the script is invoked.
sys.path.insert(0, str(PIPELINES))
sys.path.insert(0, str(LIB))

from lib.lineage_block import (  # noqa: E402
    collect_fixture_section_triples,
    collect_leg_triples,
    collect_reference_triples,
    compute_raw_sha,
    resolve_raw_vintage,
)


# Map: derived fixture-section key -> (raw-input kind, raw-input key).
# raw-input kind = "fixture" | "leg".
ADJUSTED_PARENTS = {
    "fantasycalc_adjusted": ("fixture", "fantasycalc"),
    "usatoday_adjusted": ("fixture", "usatoday"),
    "fantasypros_adjusted": ("fixture", "fantasypros"),
    "cbs_adjusted": ("fixture", "cbs"),
}
LEG_DERIVED = {
    "espn":     {"mark": "-espn-",     "filename": "ddf_leg_espn.json",     "snapshot_field": "espn_snapshot_date"},
    "cbsros":   {"mark": "-cbsros-",   "filename": "ddf_leg_cbsros.json",   "snapshot_field": "cbsros_snapshot_date"},
    "razzball": {"mark": "-razzball-", "filename": "ddf_leg_razzball.json", "snapshot_field": "razzball_snapshot_date"},
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def recompute_fixture_lineage(raw_section: dict) -> dict:
    """Recompute the lineage block the R5a writer would stamp on a derived
    section built from `raw_section` (a raw fixture section)."""
    triples = collect_fixture_section_triples(raw_section)
    raw_vintage, vintage_source = resolve_raw_vintage(
        content_vintage=raw_section.get("content_vintage"),
        espn_snapshot=raw_section.get("espn_snapshot"),
        vintage=raw_section.get("vintage"),
        fetched_at=raw_section.get("fetched_at"),
    )
    return {
        "raw_vintage": raw_vintage,
        "raw_content_sha256": compute_raw_sha(triples),
        "raw_built_at": raw_section.get("built_at"),
        "vintage_source": vintage_source,
    }


def find_freshest_leg_for_source(derived_key: str) -> Path | None:
    """Find the freshest leg file for a leg-derived fixture section.

    Mirrors the writer's glob/select: pick the leg whose inputs.{snapshot_field}
    + generated_at sort highest. The leg filename is fixed per source so we
    never confuse it with another leg type.
    """
    spec = LEG_DERIVED[derived_key]
    mark = spec["mark"]
    filename = spec["filename"]
    hits: list[tuple[str, str, Path]] = []
    for leg_path in LEG_DIR.glob(f"*/{filename}"):
        try:
            doc = json.loads(leg_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        bake_id = doc.get("bake_id", "")
        if mark not in bake_id:
            continue
        inputs = doc.get("inputs") or {}
        snapshot = inputs.get(spec["snapshot_field"], "")
        hits.append((snapshot, doc.get("generated_at", ""), leg_path))
    if not hits:
        return None
    hits.sort(reverse=True)
    return hits[0][2]


def recompute_leg_lineage(leg_path: Path, derived_key: str) -> dict:
    """Recompute the lineage block the R5a writer would stamp on a derived
    section built from this leg."""
    leg = json.loads(leg_path.read_text(encoding="utf-8"))
    triples = collect_leg_triples(leg)
    inputs_block = leg.get("inputs") or {}
    spec = LEG_DERIVED[derived_key]
    snapshot_field = spec["snapshot_field"]
    legacy_vintage = inputs_block.get(snapshot_field)
    raw_vintage, vintage_source = resolve_raw_vintage(
        content_vintage=inputs_block.get("content_vintage"),
        vintage=legacy_vintage,
        fetched_at=leg.get("fetched_at"),
    )
    return {
        "raw_vintage": raw_vintage,
        "raw_content_sha256": compute_raw_sha(triples),
        "raw_built_at": leg.get("generated_at"),
        "vintage_source": vintage_source,
    }


def recompute_reference_lineage(reference_paths: list[Path]) -> dict:
    """Recompute the lineage block the R5a writer would stamp on a candidate
    built from one or more reference artifacts."""
    refs: list[dict] = []
    for p in reference_paths:
        refs.append(json.loads(p.read_text(encoding="utf-8")))
    triples: list = []
    for ref in refs:
        triples.extend(collect_reference_triples(ref))
    provenance = refs[0].get("source_provenance") or {}
    content_vintage = provenance.get("content_vintage") if isinstance(provenance, dict) else None
    raw_vintage, vintage_source = resolve_raw_vintage(
        content_vintage=content_vintage,
        fetched_at=refs[0].get("fetched_at"),
    )
    return {
        "raw_vintage": raw_vintage,
        "raw_content_sha256": compute_raw_sha(triples),
        # Reference artifacts don't carry a unified built_at; the writer uses
        # fetched_at for vintage fallback and None for built_at when unioned,
        # but the comparable field is raw_content_sha256 + raw_vintage.
        "raw_built_at": refs[0].get("built_at"),
        "vintage_source": vintage_source,
    }


def find_candidate_reference_paths(candidate: dict) -> list[Path]:
    """Resolve the reference input(s) a candidate was built from.

    `input_reference` is a path string (single input) or list of paths.
    """
    raw = candidate.get("input_reference")
    paths: list[Path] = []
    if isinstance(raw, str):
        paths = [Path(raw)]
    elif isinstance(raw, list):
        paths = [Path(p) for p in raw]
    # Resolve relative paths against ROOT (writer's working dir at build time).
    resolved: list[Path] = []
    for p in paths:
        if not p.is_absolute():
            p = ROOT / p
        resolved.append(p)
    return resolved


def mismatch(section: str, reason: str,
             claimed: Any = None, actual: Any = None) -> dict:
    """Build a mismatch record for the monitor artifact."""
    out: dict = {"section": section, "reason": reason}
    if claimed is not None:
        out["claimed"] = claimed
    if actual is not None:
        out["actual"] = actual
    return out


def check_fixture_sections(fixture: dict, mismatches: list) -> int:
    """Check all derived fixture sections. Returns the count of sections
    examined (for the artifact's `checked` field)."""
    sources = fixture.get("sources") or {}
    checked = 0
    # 1) Adjusted sections derived from a parent raw fixture section.
    for derived_key, (_, raw_key) in ADJUSTED_PARENTS.items():
        if derived_key not in sources:
            continue  # not all adjusted sources are always present
        checked += 1
        section = sources[derived_key]
        lineage = section.get("lineage")
        if lineage is None:
            mismatches.append(mismatch(
                derived_key,
                "missing_lineage_block",
                claimed=None,
                actual="derived section has no `lineage` block (provenance not stamped)",
            ))
            continue
        raw = sources.get(raw_key)
        if raw is None:
            mismatches.append(mismatch(
                derived_key,
                "raw_parent_missing",
                claimed=None,
                actual=f"raw parent section {raw_key!r} not present in fixture",
            ))
            continue
        actual_lineage = recompute_fixture_lineage(raw)
        for field in ("raw_vintage", "raw_content_sha256",
                      "raw_built_at", "vintage_source"):
            if lineage.get(field) != actual_lineage[field]:
                mismatches.append(mismatch(
                    derived_key,
                    f"lineage_{field}_mismatch",
                    claimed=lineage.get(field),
                    actual=actual_lineage[field],
                ))
    # 2) Leg-derived sections (espn / cbsros / razzball).
    for derived_key in LEG_DERIVED:
        if derived_key not in sources:
            continue
        checked += 1
        section = sources[derived_key]
        lineage = section.get("lineage")
        if lineage is None:
            mismatches.append(mismatch(
                derived_key,
                "missing_lineage_block",
                claimed=None,
                actual="derived section has no `lineage` block (provenance not stamped)",
            ))
            continue
        leg_path = find_freshest_leg_for_source(derived_key)
        if leg_path is None:
            mismatches.append(mismatch(
                derived_key,
                "leg_raw_missing",
                claimed=None,
                actual=f"no leg file found under {LEG_DIR}",
            ))
            continue
        actual_lineage = recompute_leg_lineage(leg_path, derived_key)
        for field in ("raw_vintage", "raw_content_sha256",
                      "raw_built_at", "vintage_source"):
            if lineage.get(field) != actual_lineage[field]:
                mismatches.append(mismatch(
                    derived_key,
                    f"lineage_{field}_mismatch",
                    claimed=lineage.get(field),
                    actual=actual_lineage[field],
                ))
    return checked


def check_comparison_candidates(mismatches: list) -> int:
    """Check every comparison-candidate JSON under output/comparison-candidates/.
    Each candidate is derived from one or more reference artifacts."""
    if not CANDIDATES_DIR.is_dir():
        return 0
    checked = 0
    for candidate_path in sorted(CANDIDATES_DIR.glob("*.json")):
        try:
            candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(candidate, dict):
            continue
        if candidate.get("schema") != "trade-value-comparison-section-candidate-v1":
            continue  # not a candidate (e.g. review file)
        checked += 1
        section_key = candidate.get("section_key") or candidate_path.stem
        lineage = candidate.get("lineage")
        if lineage is None:
            mismatches.append(mismatch(
                section_key,
                "missing_lineage_block",
                claimed=None,
                actual=f"candidate {candidate_path.name} has no `lineage` block",
            ))
            continue
        ref_paths = find_candidate_reference_paths(candidate)
        missing = [str(p) for p in ref_paths if not p.exists()]
        if missing:
            mismatches.append(mismatch(
                section_key,
                "reference_raw_missing",
                claimed=None,
                actual=f"reference artifact(s) missing: {', '.join(missing)}",
            ))
            continue
        actual_lineage = recompute_reference_lineage(ref_paths)
        for field in ("raw_vintage", "raw_content_sha256",
                      "raw_built_at", "vintage_source"):
            if lineage.get(field) != actual_lineage[field]:
                mismatches.append(mismatch(
                    section_key,
                    f"lineage_{field}_mismatch",
                    claimed=lineage.get(field),
                    actual=actual_lineage[field],
                ))
    return checked


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE,
                        help="Path to comparison-sources-data.json")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT,
                        help="Where to write the input-lineage.json monitor artifact")
    args = parser.parse_args()

    if not args.fixture.exists():
        # Fail closed: a missing fixture means no provenance to verify.
        artifact = {
            "generated_at": utc_now(),
            "mismatches": [{
                "section": "(fixture)",
                "reason": "fixture_missing",
                "actual": f"{args.fixture} not found",
            }],
            "checked": 0,
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n",
                               encoding="utf-8")
        return 1

    fixture = load_json(args.fixture)
    mismatches: list = []
    checked = check_fixture_sections(fixture, mismatches)
    checked += check_comparison_candidates(mismatches)

    artifact = {
        "generated_at": utc_now(),
        "mismatches": mismatches,
        "checked": checked,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n",
                           encoding="utf-8")

    if mismatches:
        print(f"FAIL: {len(mismatches)} lineage mismatch(es) across {checked} derived section(s).",
              file=sys.stderr)
        for m in mismatches:
            print(f"  - {m['section']}: {m['reason']}", file=sys.stderr)
        return 1
    print(f"OK: all {checked} derived section(s) match current raw input.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())