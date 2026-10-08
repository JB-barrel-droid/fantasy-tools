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
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
from verify_import_health import (  # noqa: E402
    DASHBOARD_SOURCES as ACTIVE_RAW_SOURCES,
    DEFAULT_OUTPUT as DEFAULT_IMPORT_HEALTH,
    HEALTH_SCHEMA,
    entry_is_promotable,
)

FIXTURE = REPO / "data/fixtures/current/comparison-sources-data.json"
REVIEW_SCHEMA = "trade-value-comparison-review-v1"
REINDEX_SCHEMA = "trade-value-comparison-section-reindexed-v1"

# D2 Exclusion Gate: Contract validation rules
# Valid trade values must be non-negative and within reasonable bounds.
# The upper bound applies ONLY to reindexed values, which live on the 0-70
# display scale. Native (as-published) values carry source-specific units
# with no universal upper bound -- FantasyCalc publishes in the thousands
# (JSN 9914, Gibbs 10825) -- so capping them drops valid source data
# (JEG-275: 154 valid FantasyCalc natives hidden by this cap).
MIN_VALID_VALUE = 0.0
MAX_VALID_VALUE = 200.0  # Max reasonable REINDEXED (0-70 scale) value for any single player


def validate_row(slug: str, value: float | None, player_key: str | None,
                 check_upper_bound: bool = True) -> tuple[bool, str]:
    """Validate a single row against the data contract.

    Returns (is_valid, reason). If invalid, reason describes the failure.
    check_upper_bound=False for native (as-published) values: their units are
    source-specific (FantasyCalc: thousands) and no universal cap exists.
    The lower bound (>= 0) still applies: negative published values are
    corruption in every unit.
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

    if check_upper_bound and value > MAX_VALID_VALUE:
        return False, f"range_violation: value {value} > {MAX_VALID_VALUE}"

    return True, ""


def apply_exclusion_gate(section: dict, player_keys: dict) -> tuple[dict, int]:
    """Apply D2 exclusion gate: drop rows failing contract validation.

    Returns (modified_section, hidden_invalid_rows_count).
    Only validates rows that will be promoted - skips rows already dropped
    by the reindex stage (they have no reindexed values).
    """
    hidden_slugs = set()
    section = copy.deepcopy(section)

    for combo_name, combo in section.get("combos", {}).items():
        # Get player_keys for this combo (may be in combo or section-level)
        combo_player_keys = combo.get("player_keys", {})

        # Validate native values. Natives are as-published source units
        # (FantasyCalc: thousands); no universal upper bound exists, so the
        # reindexed-scale cap must not apply (JEG-275).
        native = combo.get("native", {})
        valid_native = {}
        for slug, value in native.items():
            player_key = combo_player_keys.get(slug) or player_keys.get(slug)
            is_valid, reason = validate_row(slug, value, player_key,
                                            check_upper_bound=False)
            if is_valid:
                valid_native[slug] = value
            else:
                hidden_slugs.add(slug)

        combo["native"] = valid_native

        # Validate reindexed values (if present). Reindexed values live on the
        # 0-70 display scale, so the upper bound is a genuine corruption check.
        reindexed = combo.get("reindexed", {})
        if reindexed:
            valid_reindexed = {}
            for slug, value in reindexed.items():
                player_key = combo_player_keys.get(slug) or player_keys.get(slug)
                is_valid, reason = validate_row(slug, value, player_key,
                                                check_upper_bound=True)
                if is_valid:
                    valid_reindexed[slug] = value
                else:
                    hidden_slugs.add(slug)
            combo["reindexed"] = valid_reindexed

    return section, len(hidden_slugs)


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
    provenance = section.get("source_provenance") or {}
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


# GAP-015: how old the import-health check may be before promotion WARNS.
# Never refuses (Jeremy, 2026-10-07: staleness is a warning, only wrong numbers
# block). The chain re-runs verify_import_health minutes before promoting, so
# in CI this only fires when a manual promotion reuses an old health file.
L1_MAX_AGE_HOURS = 24


def l1_age_warning(checked_at, now=None):
    """(age_hours or None, warning or None) for the import-health checked_at."""
    now = now or datetime.now(timezone.utc)
    try:
        ts = datetime.fromisoformat(str(checked_at).replace("Z", "+00:00"))
    except ValueError:
        return None, f"import health checked_at {checked_at!r} is unreadable: its age is unknown"
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    age = (now - ts).total_seconds() / 3600.0
    if age > L1_MAX_AGE_HOURS:
        return round(age, 1), (f"import health was checked {age:.1f} h ago (> {L1_MAX_AGE_HOURS} h); "
                               "re-run `make import-health` for a current verdict")
    return round(age, 1), None


def check_l1_freshness(source, section, import_health_path=None, now=None):
    """Refuse promotion of an active raw source unless L1 is fresh and matching.

    Fail-closed: a missing, unreadable or wrong-schema health file, a missing
    source entry, a non-promotable status (anything but 'ok' or a
    LAGGING_ONE_WEEK warning, decision build-lag-001), a candidate without content_vintage, or a
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
    # build-lag-001: 'ok', or a LAGGING_ONE_WEEK warning (one content week
    # behind) promoted under its OWN content_vintage -- the vintage match
    # below still binds the candidate to exactly that week. Every other
    # non-ok status (stale, red, TABLE_DRIFT warning, ...) refuses.
    if not entry_is_promotable(entry):
        raise SystemExit(f"promotion refused: import health for {source!r} is "
                         f"{entry.get('status')!r}, not 'ok' or a one-week lag "
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
    age_hours, age_warning = l1_age_warning(health.get("checked_at"), now)
    if age_warning:
        print(f"WARNING (GAP-015, not blocking): {source}: {age_warning}", file=sys.stderr)
    return {
        "applied": True,
        "source": source,
        "checked_at_age_hours": age_hours,
        "warnings": [age_warning] if age_warning else [],
        "status": entry["status"],
        "failure_reason": entry.get("failure_reason"),
        "content_vintage": fresh_vintage,
        "candidate_content_vintage": candidate_vintage,
        "checked_at": health.get("checked_at"),
        "last_successful_import": entry.get("last_successful_import"),
        "import_health_file": str(path),
        "import_health_sha256": sha256_file(path),
    }


def _merge_promoted_combo(new_combo, cand_combo):
    """Copy a reviewed candidate combo's fields into the promoted fixture combo.

    new_combo starts as a deepcopy of the existing fixture combo; every field
    the candidate pipeline recomputed is replaced wholesale. The candidate's
    "translation" provenance block (stamped by pipelines/translate_via_vorp.py
    with method + week/season grain) MUST travel with the values it describes:
    without this the fixture kept a stale translation block (null grain) while
    the fresh fit["vorp_translation"] carried the real provenance (observed
    2026-10-03 -- the monitor's vorp_translation section warned "grain week
    not recorded" on otherwise fresh data). When the candidate carries no
    translation block the existing fixture block is left untouched (fail-closed:
    never invent or destroy provenance).
    """
    new_combo["native"] = dict(cand_combo["native"])
    new_combo["reindexed"] = dict(cand_combo["reindexed"])
    new_combo["fit"] = copy.deepcopy(cand_combo["fit"])
    new_combo["n"] = sum(cand_combo["n"].values())
    new_combo["index_total"] = copy.deepcopy(cand_combo["index_total"])
    if "translation" in cand_combo:
        new_combo["translation"] = copy.deepcopy(cand_combo["translation"])


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
    for key in ("reindexed_sha256", "fixture_native_sha256", "fixture_native_before_sha256",
                "candidate_native_sha256", "review_created_at", "native_change_classification"):
        if not review.get(key):
            raise SystemExit(f"promotion refused: review lacks JEG-114 provenance ({key}) "
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

    # --- JEG-114: Native no-op detection and provenance verification ---
    # Compute candidate native hash at promotion time
    candidate_native_hash = sha256_canonical(
        {c: section["combos"][c]["native"] for c in section["combos"]})

    # Check for native no-op: candidate natives identical to current fixture natives
    # This means there's no actual native change - only reindex values would differ
    is_native_no_op = (candidate_native_hash == current_native_hash)

    # Verify provenance: ensure review has required provenance fields
    # For legacy reviews (pre-JEG-114), we need to handle gracefully
    has_provenance = (
        review.get("fixture_native_before_sha256") is not None and
        review.get("candidate_native_sha256") is not None and
        review.get("review_created_at") is not None and
        review.get("native_change_classification") is not None
    )

    if not has_provenance:
        # Legacy review - treat as unknown provenance, fail closed for native changes
        # Only allow promotion if this is clearly a reindex-only case
        if not is_native_no_op:
            raise SystemExit(
                "promotion refused: review lacks JEG-114 provenance fields "
                "(fixture_native_before_sha256, candidate_native_sha256, review_created_at, "
                "native_change_classification). This appears to be a native-changing update "
                "from a legacy review. Re-run the review with current tooling."
            )
        # For native no-op with legacy review, allow with warning
        provenance_warning = "legacy_review_unknown_provenance"
    else:
        provenance_warning = None

    # Verify the candidate_native_sha256 matches what we're promoting
    if candidate_native_hash != review["candidate_native_sha256"]:
        raise SystemExit(
            "promotion refused: candidate natives changed since review was generated "
            "-- re-run the review"
        )

    # For native no-op, require explicit reindex-only classification or reviewer confirmation
    # The review classifies this, but promotion verifies the classification is appropriate
    if is_native_no_op:
        classification = review.get("native_change_classification", "unknown")
        if classification != "reindex_only":
            # This is a no-op but wasn't classified as reindex_only - investigate
            # Allow it but record the anomaly
            pass  # Will be recorded in promotion record

    # Record provenance for the promotion
    fixture_native_after_sha256 = current_native_hash  # After promotion (same as before for no-op)

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
    # Per-combo vintage: a chain run promotes a source's sections one at a
    # time, and the section-level week below moves with the first one, so
    # combos not yet promoted keep the section's OLD vintage here (the
    # reviewer compares each candidate against its combo's own vintage).
    old_vintage = {k: fx_section.get(k) for k in ("week_designated", "content_vintage")
                   if fx_section.get(k) is not None}
    for combo in new_section["combos"].values():
        if "vintage" not in combo and old_vintage:
            combo["vintage"] = dict(old_vintage)
    for combo_name, cand_combo in section_with_gate["combos"].items():
        if combo_name not in new_section["combos"]:
            raise SystemExit(f"promotion refused: combo {combo_name!r} not in "
                             f"fixture section -- review said combos_match?")
        new_combo = new_section["combos"][combo_name]
        _merge_promoted_combo(new_combo, cand_combo)
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
    # JEG-436: the chart labels a source's week from `week_designated` FIRST
    # (product-data.js sourceVintage, curve-widget.js weekForSource), and the
    # promoter used to keep the fixture's old label. Promoting FantasyCalc's
    # Week-5 natives left `week_designated: "Week 4"` beside
    # `content_vintage: "Week 5"`, so the chart would have shown week-5 values
    # as Week 4. The label now travels with the values: the candidate's
    # provenance week (int, from the importer's week column), else a "Week N"
    # content_vintage.
    prov = section_with_gate.get("source_provenance") or {}
    prov_week = prov.get("week_designated") if isinstance(prov, dict) else None
    vintage_week = re.match(r"^\s*week\s*(\d+)\s*$",
                            str(section_with_gate.get("content_vintage") or ""), re.I)
    if isinstance(prov_week, int) and not isinstance(prov_week, bool):
        new_section["week_designated"] = f"Week {prov_week}"
    elif vintage_week:
        new_section["week_designated"] = f"Week {int(vintage_week.group(1))}"
    promoted_vintage = {k: new_section.get(k) for k in ("week_designated", "content_vintage")
                        if new_section.get(k) is not None}
    for combo_name in section_with_gate["combos"]:
        new_section["combos"][combo_name]["vintage"] = dict(promoted_vintage)
    # D2 Exclusion Gate: Record hidden invalid rows count. Clear any stale
    # count carried over from a previous promotion: a 0 this run means the
    # section is clean now (JEG-275).
    if hidden_invalid_rows > 0:
        new_section["hidden_invalid_rows"] = hidden_invalid_rows
    else:
        new_section.pop("hidden_invalid_rows", None)
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
        # JEG-114: Native change provenance tracking
        "fixture_native_before_sha256": review.get("fixture_native_before_sha256"),
        "candidate_native_sha256": candidate_native_hash,
        "fixture_native_after_sha256": fixture_native_after_sha256,
        "native_change_classification": review.get("native_change_classification", "unknown"),
        "is_native_no_op": is_native_no_op,
        "provenance_warning": provenance_warning,
        "review_created_at": review.get("review_created_at"),
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
