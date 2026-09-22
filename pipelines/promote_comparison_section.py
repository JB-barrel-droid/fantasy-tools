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
  5. explicit human approval: --approve "<name> <YYYY-MM-DD> <reason>"

What promotion does:
  - replaces the source's combos' reindexed values, fit metadata, and
    index_total with the candidate's
  - native values are carried over byte-identical; their vintage (fetched_at)
    is NOT touched -- only the reindex anchor changes, recorded as
    section-level reindex_anchor='espn_leg' plus promoted_at/promoted_from_review
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
FIXTURE = REPO / "data/fixtures/current/comparison-sources-data.json"
REVIEW_SCHEMA = "trade-value-comparison-review-v1"
REINDEX_SCHEMA = "trade-value-comparison-section-reindexed-v1"


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


def promote(review_path, approve, fixture_path=None, record_dir=None):
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

    player_keys = fixture.get("player_keys", {})
    unknown = [s for combo in section["combos"].values()
               for s in combo["native"] if s not in player_keys]
    if unknown:
        raise SystemExit(f"promotion refused: {len(unknown)} candidate slugs "
                         f"not in fixture player_keys (e.g. {unknown[:3]})")

    # --- build the promoted section: fixture shape, candidate math ---
    new_section = copy.deepcopy(fx_section)
    for combo_name, cand_combo in section["combos"].items():
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
    new_section["promotion_note"] = (
        "Re-anchored from the retired Monday rail to the fixture ESPN leg. "
        f"Native values byte-identical (vintage {fx_section.get('fetched_at')}); "
        "only the reindex mapping changed.")

    before_hash = sha256_canonical(fx_section)
    fixture["sources"][source] = new_section
    after_hash = sha256_canonical(new_section)
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
    ap.add_argument("--approve", required=True,
                    help='"<name> <YYYY-MM-DD> <reason>" -- recorded in the promotion record')
    args = ap.parse_args(argv)
    result = promote(args.review, args.approve)
    print(f"promoted {result['source']}: "
          f"{result['before']} -> {result['after']}")
    print(f"record -> {result['promotion_record']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
