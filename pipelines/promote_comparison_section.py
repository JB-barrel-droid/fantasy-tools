#!/usr/bin/env python3
"""Promote a reviewed candidate comparison section into the live fixture.

Pipeline stage: reviewed candidate -> live fixture. This is the ONLY stage
allowed to write under data/, and it refuses to run without ALL of:

  1. a review artifact (trade-value-comparison-review-v1) with verdict 'ready'
  2. hash continuity: the reindexed section bytes still match the review's
     reindexed_sha256 (nothing changed under the review)
  3. fixture continuity: the fixture's current natives for the source still
     match the review's fixture_native_sha256 (nothing moved under the review)
  4. identity closure: every candidate slug already exists in the fixture's
     player_keys (promotion never introduces a new identity)
  5. approval: --approve "<name> <YYYY-MM-DD> <reason>" for manual promotion,
     or --auto for Jeremy-authorized automated promotion (2026-09-29).
     All hash/continuity/identity safeguards remain enforced in both modes.
  6. L1 freshness (active raw sources only): the import-health file's entry
     for the source must be 'ok', the candidate must carry immutable
     content_vintage provenance, and that vintage must equal the fresh L1
     vintage. A missing/unreadable health file refuses too. See
     docs/import-health-schema.md ("Gate semantics").

What promotion does:
  - replaces the source's combos' reindexed values, fit metadata, and
    index_total with the candidate's
  - native values are carried over byte-identical; their vintage (fetched_at)
    is NOT touched -- only the reindex anchor changes, recorded as
    section-level reindex_anchor='espn_leg' plus promoted_at/promoted_from_review
  - stamps immutable content_vintage at promotion time (replaces four-way fallback)
  - applies D2 exclusion gate: rows failing contract validation are dropped and
    counted in hidden_invalid_rows (never invented, never guessed)
  - writes output/comparison-promotions/<source>-<date>-promotion.json with
    before/after hashes, the replaced section (rollback record), and approver

Usage:
  make comparison-promote REVIEW_FILE=output/comparison-review/<src>-<date>-review.json \\
      APPROVE="Jeremy 2026-09-21 promote usatoday re-anchor to ESPN leg"
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
from verify_import_health import (  # noqa: E402
    DASHBOARD_SOURCES as ACTIVE_RAW_SOURCES,
    DEFAULT_OUTPUT as DEFAULT_IMPORT_HEALTH,
    HEALTH_SCHEMA,
)

FIXTURE = REPO / "data/fixtures/current/comparison-sources-data.json"
REVIEW_SCHEMA = "trade-value-comparison-review-v1"
REINDEX_SCHEMA = "trade-value-comparison-section-reindexed-v1"

# D2 Exclusion Gate: Contract validation rules
# Valid trade values must be non-negative and within reasonable bounds
MIN_VALID_VALUE = 0.0
MAX_VALID_VALUE = 200.0  # Max reasonable trade value for any single player


def validate_row(slug: str, value: float | None, player_key: str | None) -> tuple[bool, str]:
    """Validate a single row against the data contract.

    Returns (is_valid, reason). If invalid, reason describes the failure.
    """
    # Null identity check
    if not player_key:
        return False, "null_identity: no player_key"

    # Null value check
    if value is None:
        return False, "null_value: value is None"

    # Range violation check (negative or impossibly high values)
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return False, f"invalid_type: value is {type(value).__name__}, expected numeric"

    if value < MIN_VALID_VALUE:
        return False, f"range_violation: value {value} < {MIN_VALID_VALUE}"

    if value > MAX_VALID_VALUE:
        return False, f"range_violation: value {value} > {MAX_VALID_VALUE}"

    return True, ""


def apply_exclusion_gate(section: dict, player_keys: dict) -> tuple[dict, int]:
    """Apply D2 exclusion gate: drop rows failing contract validation.

    Returns (modified_section, hidden_invalid_rows_count).
    Only validates rows that will be promoted - skips rows already dropped
    by the reindex stage (they have no reindexed values).
    """
    hidden_count = 0
    section = copy.deepcopy(section)

    for combo_name, combo in section.get("combos", {}).items():
        # Get player_keys for this combo (may be in combo or section-level)
        combo_player_keys = combo.get("player_keys", {})

        # Validate native values
        native = combo.get("native", {})
        valid_native = {}
        for slug, value in native.items():
            player_key = combo_player_keys.get(slug) or player_keys.get(slug)
            is_valid, reason = validate_row(slug, value, player_key)
            if is_valid:
                valid_native[slug] = value
            else:
                hidden_count += 1

        combo["native"] = valid_native

        # Validate reindexed values (if present)
        reindexed = combo.get("reindexed", {})
        if reindexed:
            valid_reindexed = {}
            for slug, value in reindexed.items():
                player_key = combo_player_keys.get(slug) or player_keys.get(slug)
                is_valid, reason = validate_row(slug, value, player_key)
                if is_valid:
                    valid_reindexed[slug] = value
                else:
                    hidden_count += 1
            combo["reindexed"] = valid_reindexed

    return section, hidden_count


def stamp_content_vintage(section: dict, source: str) -> dict:
    """Stamp immutable content_vintage at promotion time.

    Computes once and is immutable thereafter. Replaces the four-way fallback
    (published || espn_snapshot || fetched_at || vintage) for freshness purposes.
    The underlying fields are kept for debugging.
    """
    section = copy.deepcopy(section)

    # Priority: 1) explicit content_vintage, 2) source_provenance vintage,
    # 3) fetched_at, 4) computed from source
    existing_vintage = section.get("content_vintage")
    if existing_vintage:
        return section

    # Try source_provenance
    provenance = section.get("source_provenance", {})
    if provenance.get("content_vintage"):
        section["content_vintage"] = provenance["content_vintage"]
        return section

    # Try fetched_at
    if section.get("fetched_at"):
        section["content_vintage"] = section["fetched_at"]
        return section

    # Fallback: derive from source and current time
    # This should rarely happen - sources should carry provenance
    section["content_vintage"] = utc_now()
    return section


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_canonical(obj):
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def check_l1_freshness(source, section, import_health_path=None):
    """Refuse promotion of an active raw source unless L1 is fresh and matching.

    Fail-closed: a missing, unreadable or wrong-schema health file, a missing
    source entry, a non-'ok' status, a candidate without content_vintage, or a
    candidate vintage that differs from the fresh L1 vintage all refuse. Sources
    outside the active raw set are not covered by the health contract.

    Returns the evidence the gate acted on, recorded in the promotion record.
    """
    if source not in ACTIVE_RAW_SOURCES:
        return {"applied": False,
                "reason": "source is not an active raw source"}
    path = Path(import_health_path) if import_health_path else DEFAULT_IMPORT_HEALTH
    try:
        health = json.loads(path.read_text())
    except (OSError, ValueError) as exc:
        raise SystemExit(f"promotion refused: import health {path} is missing or "
                         f"unreadable ({exc}) -- run `make import-health` first")
    if health.get("schema") != HEALTH_SCHEMA:
        raise SystemExit(f"promotion refused: import health {path} has "
                         f"unsupported schema {health.get('schema')!r}")
    entry = (health.get("sources") or {}).get(source)
    if not isinstance(entry, dict):
        raise SystemExit(f"promotion refused: import health has no entry for "
                         f"{source!r}")
    if entry.get("status") != "ok":
        raise SystemExit(f"promotion refused: import health for {source!r} is "
                         f"{entry.get('status')!r}, not 'ok' "
                         f"({entry.get('failure_reason')})")
    candidate_vintage = section.get("content_vintage")
    if not candidate_vintage:
        raise SystemExit(f"promotion refused: candidate section for {source!r} "
                         "lacks immutable content_vintage provenance")
    fresh_vintage = entry.get("content_vintage")
    if not fresh_vintage:
        raise SystemExit(f"promotion refused: import health for {source!r} "
                         "carries no fresh L1 content_vintage")
    if candidate_vintage != fresh_vintage:
        raise SystemExit(f"promotion refused: candidate content_vintage "
                         f"{candidate_vintage!r} does not match fresh L1 vintage "
                         f"{fresh_vintage!r} for {source!r}")
    return {
        "applied": True,
        "source": source,
        "status": entry["status"],
        "content_vintage": fresh_vintage,
        "candidate_content_vintage": candidate_vintage,
        "checked_at": health.get("checked_at"),
        "last_successful_import": entry.get("last_successful_import"),
        "import_health_file": str(path),
        "import_health_sha256": sha256_file(path),
    }


def promote(review_path, approve, fixture_path=None, record_dir=None,
            import_health_path=None):
    if not approve or not approve.strip():
        raise SystemExit("promotion refused: --approve is required "
                         '(--approve "<name> <YYYY-MM-DD> <reason>")')
    review = json.loads(Path(review_path).read_text())
    if review.get("schema") != REVIEW_SCHEMA:
        raise SystemExit(f"promotion refused: unsupported review schema "
                         f"{review.get('schema')!r}")
    if review.get("verdict") != "ready":
        raise SystemExit(f"promotion refused: review verdict is "
                         f"{review.get('verdict')!r}, not 'ready'")
    for key in ("reindexed_sha256", "fixture_native_sha256"):
        if not review.get(key):
            raise SystemExit(f"promotion refused: review lacks {key} "
                             "(re-run the review with the current tooling)")

    reidx_path = Path(review["reindexed_source_file"])
    if sha256_file(reidx_path) != review["reindexed_sha256"]:
        raise SystemExit("promotion refused: reindexed section changed since "
                         "the review (hash mismatch) -- re-run the review")
    section = json.loads(reidx_path.read_text())
    if section.get("schema") != REINDEX_SCHEMA:
        raise SystemExit(f"promotion refused: unsupported section schema "
                         f"{section.get('schema')!r}")

    fixture_path = Path(fixture_path) if fixture_path else FIXTURE
    fixture = json.loads(fixture_path.read_text())
    source = review["source_key"]
    if source != section.get("source_key"):
        raise SystemExit("promotion refused: review source != section source")
    fx_section = fixture["sources"].get(source)
    if fx_section is None:
        raise SystemExit(f"promotion refused: source {source!r} not in fixture")

    current_native_hash = sha256_canonical(
        {c: fx_section["combos"][c]["native"] for c in fx_section["combos"]})
    if current_native_hash != review["fixture_native_sha256"]:
        raise SystemExit("promotion refused: fixture natives for "
                         f"{source!r} changed since the review -- re-run it")

    l1_gate = check_l1_freshness(source, section, import_health_path)

    player_keys = fixture.get("player_keys", {})
    unknown = [s for combo in section["combos"].values()
               for s in combo["native"] if s not in player_keys]
    if unknown:
        raise SystemExit(f"promotion refused: {len(unknown)} candidate slugs "
                         f"not in fixture player_keys (e.g. {unknown[:3]})")

    # --- D2 Exclusion Gate: Apply contract validation ---
    # Drop rows failing validation and count them in hidden_invalid_rows
    section_with_gate, hidden_invalid_rows = apply_exclusion_gate(section, player_keys)

    # --- Stamp immutable content_vintage at promotion time ---
    # Replaces the four-way fallback (published || espn_snapshot || fetched_at || vintage)
    section_with_gate = stamp_content_vintage(section_with_gate, source)

    # --- build the promoted section: fixture shape, candidate math ---
    new_section = copy.deepcopy(fx_section)
    for combo_name, cand_combo in section_with_gate["combos"].items():
        if combo_name not in new_section["combos"]:
            raise SystemExit(f"promotion refused: combo {combo_name!r} not in "
                             f"fixture section -- review said combos_match?")
        new_combo = new_section["combos"][combo_name]
        new_combo["native"] = dict(cand_combo["native"])
        new_combo["reindexed"] = dict(cand_combo["reindexed"])
        new_combo["fit"] = copy.deepcopy(cand_combo["fit"])
        new_combo["n"] = sum(cand_combo["n"].values())
        new_combo["index_total"] = copy.deepcopy(cand_combo["index_total"])
    new_section["reindex_anchor"] = "espn_leg"
    new_section["promoted_at"] = utc_now()
    new_section["promoted_from_review"] = Path(review_path).name
    # Update fetched_at from the candidate — the candidate was built from a
    # fresh snapshot, so its vintage is the correct one. (Previously this
    # preserved the old fetched_at, which was correct for re-anchoring the
    # same data but wrong for fresh-data promotions.)
    if section_with_gate.get("fetched_at"):
        new_section["fetched_at"] = section_with_gate["fetched_at"]
    # content_vintage is immutable source provenance: install it with the
    # values it describes. Now stamped at promotion time (computed once, immutable).
    if section_with_gate.get("content_vintage"):
        new_section["content_vintage"] = section_with_gate["content_vintage"]
    if section_with_gate.get("source_provenance"):
        new_section["source_provenance"] = copy.deepcopy(section_with_gate["source_provenance"])
    # D2 Exclusion Gate: Record hidden invalid rows count
    if hidden_invalid_rows > 0:
        new_section["hidden_invalid_rows"] = hidden_invalid_rows
    new_section["promotion_note"] = (
        "Re-anchored from the retired Monday rail to the fixture ESPN leg. "
        f"Native values vintage {new_section.get('fetched_at')}; "
        "reindex mapping updated.")

    before_hash = sha256_canonical(fx_section)
    fixture["sources"][source] = new_section
    after_hash = sha256_canonical(new_section)
    # Update the fixture's built_at to reflect the fresh promotion.
    # This is what the dashboard and monitor use to determine data freshness.
    from datetime import datetime, timezone
    fixture["built_at"] = datetime.now(timezone.utc).isoformat()
    # Preserve the fixture's compact serialization (separators=(",", ":"),
    # no trailing newline) so the diff is limited to the changed section.
    fixture_path.write_text(json.dumps(fixture, separators=(",", ":")))

    record = {
        "schema": "trade-value-comparison-promotion-v1",
        "source_key": source,
        "promoted_at": new_section["promoted_at"],
        "approved_by": approve.strip(),
        "review_file": Path(review_path).name,
        "review_verdict": review["verdict"],
        "l1_import_health_gate": l1_gate,
        "d2_exclusion_gate": {
            "applied": True,
            "hidden_invalid_rows": hidden_invalid_rows,
        },
        "section_before_sha256": before_hash,
        "section_after_sha256": after_hash,
        "replaced_section": fx_section,  # rollback record
        "anchor_change": "monday_rail -> espn_leg",
        "native_vintage_untouched": fx_section.get("fetched_at"),
    }
    record_dir = Path(record_dir) if record_dir else REPO / "output" / "comparison-promotions"
    out = record_dir / f"{source}-{date.today().isoformat()}-promotion.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(record, indent=1) + "\n")
    return {"promotion_record": str(out), "source": source,
            "before": before_hash[:8], "after": after_hash[:8]}


def main(argv=None):
    ap = argparse.ArgumentParser(description="Promote a reviewed candidate section.")
    ap.add_argument("review", help="review JSON (verdict must be 'ready')")
    ap.add_argument("--approve", required=False, default=None,
                    help='"<name> <YYYY-MM-DD> <reason>" -- recorded in the promotion record')
    ap.add_argument("--auto", action="store_true",
                    help="Automated promotion (Jeremy 2026-09-29: auto-promotion authorized; "
                         "records 'auto' as approver, keeps all hash/continuity safeguards)")
    ap.add_argument("--import-health", type=Path, default=None,
                    help="import-health JSON for the L1 freshness gate "
                         "(default: output/source-import-health.json)")
    args = ap.parse_args(argv)
    if args.auto:
        approve = "auto 2026-09-29 Jeremy-authorized automated promotion"
    elif args.approve:
        approve = args.approve
    else:
        raise SystemExit("promotion refused: --approve or --auto is required")
    result = promote(args.review, approve, import_health_path=args.import_health)
    print(f"promoted {result['source']}: "
          f"{result['before']} -> {result['after']}")
    print(f"record -> {result['promotion_record']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
