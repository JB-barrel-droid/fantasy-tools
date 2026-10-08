#!/usr/bin/env python3
"""Rebuild the comparison fixture from fresh snapshots — full automated chain.

FAIL-CLOSED. Stages run strictly in order per source:
  match -> reference -> section -> reindex -> review -> promote
then, only if EVERY source succeeded:
  fit (bias-correction adjustment cells)
then, only if the fit succeeded:
  adjusted fixture sections (deterministic application of the fit cells)

cbsros (CBS rest-of-season projections) runs its own stage path instead:
  snapshot -> DDF leg (12 legs) -> section -> review/verify
The generic path's quantile-reindex stage always maps to the ESPN anchor,
which would transform cbsros's deliberate DDF-direct values (factor 1.0);
its chain mirrors its production pipeline and its review stage verifies
the rebuilt fixture section fail-closed.

Hard rules (Jeremy 2026-09-29; hardened after the validation-bypass repair):
- Review verdicts are NEVER modified by this chain. A 'hold' stays a 'hold'.
  review_comparison_candidate.py documents hold as "something needs a human
  first" — there is no legitimate auto-resolve path.
- Only genuine 'ready' verdicts are promoted. promote_comparison_section.py
  independently refuses non-'ready' verdicts; this chain does not retry
  around, re-review around, or edit its way around that refusal.
- The first hold/failure HALTS the chain for that source: no further
  sections are processed for it.
- Partial or zero promotion is FAILURE for that source, never a partial
  success.
- Per-source isolation (Jeremy 2026-10-07, decision per-source-promotion-001):
  a genuine review verdict of 'hold' in one of HOLD_ISOLATED_SOURCES does not
  fail the run. The held source's fixture section is restored to exactly what
  it was before its run (any sections it promoted earlier in the run are
  rolled back), so the site keeps showing its last promoted section under its
  own week label. The held candidate is never promoted. Everything else still
  fails the whole chain closed: any non-hold failure (snapshot, match,
  section, reindex, promote refusal, error, a malformed review), any ESPN or
  cbsros failure (ESPN is the reindex anchor and the fit target; both write
  the fixture before their review gate), a restore that cannot be verified,
  and a run in which EVERY review-gated source held (nothing new to publish).
- The fit and _adjusted sections run on the resulting fixture whenever the
  run is publishable, so a held source's _adjusted section is rebuilt from
  its kept (older) raw section, never left half-updated.
- Chain status is written through a finally block so partial/interrupted
  runs are always recorded for the monitoring dashboard. Held sources are
  listed in `held` / `held_detail` with an amber (one week behind) or red
  (two or more weeks behind, or week unknown) severity.

Usage:
    python3 pipelines/rebuild_comparison_chain.py [--nfl-week WEEK]

Exit code: 0 only if every source either completed fully or was held and
restored (isolated hold), at least one review-gated source promoted, and the
fit and _adjusted stages ran cleanly. Anything else exits non-zero so the
GitHub Actions workflow stops before committing the fixture.
"""

import argparse
import copy
import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SOURCES = ["usatoday", "fantasycalc", "fantasypros", "espn", "cbs", "cbsros"]

# Per-source isolation (per-source-promotion-001): only these sources' review
# holds are isolated. They are the generic published-chart sources whose
# review is a real candidate-vs-fixture verdict and whose fixture section is
# written only by promote_comparison_section.py (so it can be restored
# exactly). ESPN and cbsros are deliberately absent: their section builders
# write the fixture BEFORE their review gate, ESPN's DDF legs are the reindex
# anchor and the fit target, and their "review" is a structural check whose
# failure means a malformed section, not a judgement call. Any failure there
# fails the whole chain closed, as before.
HOLD_ISOLATED_SOURCES = ("usatoday", "fantasycalc", "fantasypros", "cbs")

FIXTURE_REL = Path("data") / "fixtures" / "current" / "comparison-sources-data.json"
PROMOTIONS_REL = Path("output") / "comparison-promotions"

# cbsros DDF-leg build matrix: the section builder expects one leg per
# (scoring, teams) pair, 3 scorings x 4 team counts = 12 legs.
CBSROS_LEG_SCORINGS = ("standard", "half_ppr", "ppr")
CBSROS_LEG_TEAMS = (8, 10, 12, 14)
CBSROS_COMBO_KEYS = [f"{s}_{t}" for s in ("full", "half", "standard")
                     for t in CBSROS_LEG_TEAMS]

# Stage names in strict execution order (fit runs last, gated on all sources).
STAGE_ORDER = ["match", "reference", "section", "reindex", "review", "promote", "fit"]


class ChainHalt(Exception):
    """Raised to stop the chain fail-closed on the first hold/failure."""

    def __init__(self, stage, detail):
        super().__init__(f"{stage}: {detail}")
        self.stage = stage
        self.detail = detail


class ReviewHold(ChainHalt):
    """The reviewer ran, wrote its artifact, and returned verdict 'hold'.

    Only this exact case is eligible for per-source isolation. A missing or
    unreadable artifact, or any other non-'ready' verdict, stays a plain
    ChainHalt and fails the chain closed.
    """


def run(cmd, **kwargs):
    """Run a command, return (ok, output)."""
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, cwd=REPO, timeout=300, **kwargs
        )
        return result.returncode == 0, result.stdout + result.stderr
    except subprocess.TimeoutExpired:
        return False, "timeout"
    except Exception as e:
        return False, str(e)


def find_latest_snapshot(repo, source):
    """Find the latest snapshot.json for a source."""
    source_dir = repo / "data" / "raw" / "sources" / source
    if not source_dir.is_dir():
        return None
    # Handle both date-based and week-based directory names
    candidates = []
    for child in source_dir.iterdir():
        if child.is_dir() and (child / "snapshot.json").is_file():
            # Skip archived snapshots (prefixed with _)
            if child.name.startswith("_"):
                continue
            candidates.append(child)
    if not candidates:
        return None
    # Sort by name (dates and week-N both sort chronologically)
    candidates.sort(key=lambda p: p.name)
    return candidates[-1] / "snapshot.json"


def newest_file(directory, pattern):
    """Newest file matching pattern under directory (by mtime), or None."""
    if not directory.is_dir():
        return None
    files = list(directory.rglob(pattern))
    if not files:
        return None
    files.sort(key=lambda p: p.stat().st_mtime)
    return files[-1]


def process_section(section, repo, run_fn, nfl_week=None):
    """Reindex -> VORP-translate -> review -> promote ONE section. Fail-closed.

    Returns "promoted". Raises ChainHalt on any hold/failure/error.
    NEVER modifies the review artifact: a hold stays a hold.

    The VORP-translate step (JEG-64) is fail-safe, not fail-closed: missing
    Supabase grains and transport errors keep the reindexed values and record
    reindex-fallback provenance. It can never halt the chain.
    """
    base = section.stem  # e.g., usatoday-standard-12-section

    # Reindex
    reindexed = repo / "output" / "reindexed" / f"{base}-reindexed.json"
    reindexed.parent.mkdir(parents=True, exist_ok=True)
    ok, out = run_fn([
        "python3", "pipelines/reindex_comparison_section.py",
        str(section), "--out", str(reindexed),
    ])
    if not ok or not reindexed.is_file():
        raise ChainHalt("reindex", f"{base}: reindex failed: {out[-300:]}")

    # VORP translation (JEG-64): substitute Supabase translated values for the
    # quantile-mapped ones on as-published sources. Fail-safe by design --
    # never raises, never halts the chain (fallback is acceptance #3).
    # JEG-70: pass the chain week so the stage fetches the current week's
    # Supabase grain (fetch_translated filters week=eq) and stamps it in the
    # provenance. Without this the stage silently reuses the default week
    # after rollover.
    # JEG332-STORED-DRIFT: translate from the section's OWN natives. The
    # Supabase grain is written after promotion (run_vorp_refresh) from the
    # previous natives, so reading it here promoted a stale translation on
    # every native refresh (USA Today, 2026-10-02).
    # build-lag-001: this stays the CHAIN week even for a source lagging one
    # week. The grain's `week` is a refresh-cycle label: Stage 9
    # (refresh_vorp_translation --week <chain week>) computes every grain
    # from the promoted fixture's natives, whatever week each source's
    # content is, and labels it with the chain week. Fetching a lagging
    # source at its own content week would read LAST cycle's grain (older
    # natives). The source's real week is carried by its content_vintage.
    vorp_cmd = [
        "python3", "pipelines/translate_via_vorp.py",
        "--section", str(reindexed), "--translation", "natives",
    ]
    if nfl_week is not None:
        vorp_cmd += ["--week", str(nfl_week)]
    tr_ok, tr_out = run_fn(vorp_cmd)
    tr_line = tr_out.strip().splitlines()[-1] if tr_out and tr_out.strip() else "no output"
    print(f"  vorp-translate: {'ok' if tr_ok else 'STEP-FAILED-LOGGED'}: {tr_line}")

    # Review. The reviewer exits non-zero when the verdict is not ready,
    # but still writes the artifact — a missing artifact is itself a failure.
    # No triage file: every review row requires human review. The triage
    # mechanism was removed 2026-09-30 after it was found to contain
    # factually incorrect auto-generated approvals.
    review_path = repo / "output" / "reviewed" / f"{base}-review.json"
    review_path.parent.mkdir(parents=True, exist_ok=True)
    review_cmd = [
        "python3", "pipelines/review_comparison_candidate.py",
        str(reindexed), "--out", str(review_path),
    ]
    ok, out = run_fn(review_cmd)
    if not review_path.is_file():
        raise ChainHalt("review", f"{base}: review produced no artifact: {out[-300:]}")
    try:
        with open(review_path) as fh:
            review_data = json.load(fh)
    except (json.JSONDecodeError, OSError) as e:
        raise ChainHalt("review", f"{base}: review artifact unreadable: {e}")

    # The verdict is read-only. NEVER rewrite hold -> ready.
    # JEG-113: name the failing checks in the halt detail so the CI log
    # self-diagnoses the hold (the review artifact is gitignored and was not
    # uploaded, so "hold" alone said nothing).
    verdict = review_data.get("verdict")
    if verdict != "ready":
        bad = [c for c in review_data.get("checks", [])
               if c.get("status") not in ("pass", "info")]
        check_str = ("; ".join(
            f"{c.get('name')}:{c.get('status')} -- {c.get('detail', '')}"
            for c in bad) or "no failing checks recorded")
        halt_cls = ReviewHold if verdict == "hold" else ChainHalt
        raise halt_cls(
            "review",
            f"{base}: verdict is {verdict!r}, not 'ready' — refusing to promote. "
            f"Failing checks: {check_str}. "
            "A hold means a human must review first; the chain will not override it.",
        )

    # Promote. promote_comparison_section.py independently refuses non-ready
    # verdicts; any failure here is terminal — no retry, no re-review.
    ok, out = run_fn([
        "python3", "pipelines/promote_comparison_section.py",
        str(review_path), "--auto",
    ])
    if not ok:
        raise ChainHalt("promote", f"{base}: promote refused/failed: {out[-300:]}")

    return "promoted"


def run_source(source, nfl_week=None, repo=REPO, run_fn=run):
    """Run match -> reference -> section -> reindex -> review -> promote.

    Returns a result dict; never raises. The first hold/failure halts the
    source's chain immediately (ChainHalt) and is recorded as failed.
    """
    result = {
        "source": source,
        "status": "failed",  # fail-closed default; set to "ok" only on full success
        "stage": None,
        "detail": "",
        "promoted": 0,
        "sections": 0,
    }
    try:
        # 1. Snapshot
        snapshot = find_latest_snapshot(repo, source)
        if not snapshot:
            raise ChainHalt("snapshot", "no snapshot.json found under data/raw/sources")
        print(f"  Snapshot: {snapshot.relative_to(repo)}")

        # 2. Match
        ok, out = run_fn([
            "python3", "pipelines/match_source_snapshot.py",
            "--input", str(snapshot),
            "--output-dir", "output/matched",
        ])
        if not ok:
            raise ChainHalt("match", f"match failed: {out[-300:]}")
        matched = newest_file(repo / "output" / "matched" / source, "*-matched.json")
        if not matched:
            raise ChainHalt("match", "matcher exited 0 but no *-matched.json appeared")
        print("  ✓ Matched")

        # 3. Reference
        ok, out = run_fn([
            "python3", "pipelines/build_source_reference.py",
            "--input", str(matched),
            "--output-dir", "output/references",
        ])
        if not ok:
            raise ChainHalt("reference", f"reference build failed: {out[-300:]}")
        print("  ✓ References built")

        # 4. Section (one per reference file, latest vintage only)
        ref_files = list((repo / "output" / "references" / source).rglob("*-reference.json")) \
            if (repo / "output" / "references" / source).is_dir() else []
        if ref_files:
            latest_dir = max(set(f.parent for f in ref_files), key=lambda d: d.name)
            ref_files = sorted(
                (f for f in ref_files if f.parent == latest_dir),
                key=lambda f: f.name,
            )

        sections = []
        for ref in ref_files:
            ok, out = run_fn([
                "python3", "pipelines/build_comparison_source_section.py",
                "--input", str(ref),
            ])
            if not ok:
                raise ChainHalt("section", f"section build failed for {ref.name}: {out[-300:]}")
            section_file = newest_file(
                repo / "output" / "comparison-candidates" / source, "*-section.json")
            if not section_file:
                raise ChainHalt(
                    "section",
                    f"section builder exited 0 for {ref.name} but no *-section.json appeared",
                )
            sections.append(section_file)
        if not sections:
            raise ChainHalt("section", "no sections built")
        # Deterministic order so a halt always promotes the same prefix.
        sections.sort(key=lambda p: p.name)
        result["sections"] = len(sections)
        print(f"  ✓ {len(sections)} sections built")

        # 5. Reindex -> review -> promote, strictly in order.
        #    The first hold/failure raises ChainHalt: no further sections
        #    are processed for this source. result["promoted"] is updated
        #    inside the loop so a halt still reports the true count.
        for section in sections:
            process_section(section, repo, run_fn, nfl_week=nfl_week)
            result["promoted"] += 1
        promoted = result["promoted"]

        # 6. Partial or zero promotion is FAILURE, never a partial success.
        #    (Unreachable via process_section, which raises on the first
        #    problem — kept as defense-in-depth.)
        if promoted != len(sections):
            raise ChainHalt(
                "promote", f"partial promotion {promoted}/{len(sections)} — treating as failure")

        result["status"] = "ok"
        result["stage"] = "complete"
        result["detail"] = f"promoted {promoted}/{len(sections)}"
        print(f"  ✓ {promoted}/{len(sections)} sections promoted")

    except ChainHalt as h:
        result["stage"] = h.stage
        result["detail"] = h.detail
        # Still "failed" here; execute_chain decides whether the hold can be
        # isolated (restore verified) or must fail the chain.
        result["held"] = isinstance(h, ReviewHold)
        print(f"  ✗ HALT at stage '{h.stage}': {h.detail}")
    except Exception as e:  # fail closed on unexpected errors too
        result["stage"] = "error"
        result["detail"] = f"unexpected error: {e}"
        print(f"  ✗ ERROR: {e}")

    return result


def _read_fixture(repo):
    return json.loads((Path(repo) / FIXTURE_REL).read_text(encoding="utf-8"))


def _canonical_sha(obj):
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def snapshot_source_state(repo, source):
    """Record a source's fixture section (and built_at) before its run.

    Returns None when the fixture cannot be read; a hold for that source
    then cannot be isolated and fails the chain closed.
    """
    try:
        fixture = _read_fixture(repo)
    except (OSError, ValueError):
        return None
    sources = fixture.get("sources")
    if not isinstance(sources, dict):
        return None
    promo_dir = Path(repo) / PROMOTIONS_REL
    records = ({p.name for p in promo_dir.glob(f"{source}-*-promotion.json")}
               if promo_dir.is_dir() else set())
    return {
        "present": source in sources,
        "section": copy.deepcopy(sources.get(source)),
        "sha": _canonical_sha(sources.get(source)),
        "built_at": fixture.get("built_at"),
        "promotion_records": records,
    }


def section_week(section):
    """Content week of a fixture section, or None when nothing dates it.

    Mirrors product-data.js sourceVintage(): a "Week N" designation wins, then
    a "Week N" content_vintage, then a dated field placed on the content
    calendar.
    """
    import re
    from datetime import date as _date
    from nfl_week import current_nfl_week

    if not isinstance(section, dict):
        return None
    for field in ("week_designated", "content_vintage"):
        m = re.search(r"week\s*(\d+)|wk\s*(\d+)", str(section.get(field) or ""), re.I)
        if m:
            return int(m.group(1) or m.group(2))
    for field in ("content_vintage", "vintage", "published", "fetched_at"):
        m = re.match(r"(\d{4})-(\d{2})-(\d{2})", str(section.get(field) or ""))
        if m:
            return current_nfl_week(_date(int(m.group(1)), int(m.group(2)), int(m.group(3))))
    return None


def isolate_hold(repo, source, before, result, nfl_week=None):
    """Restore a held source's pre-run fixture section; mark it held.

    Fail-closed: when the pre-run state is unknown, or the restore cannot be
    verified byte-for-byte (canonical sha of the section), the result stays
    'failed' and the chain fails. Promotion records written for sections
    that were rolled back are renamed so no monitor reads them as promoted.
    """
    if before is None:
        result["detail"] += " | hold NOT isolated: pre-run fixture state unknown"
        return result
    fixture_path = Path(repo) / FIXTURE_REL
    try:
        fixture = _read_fixture(repo)
        sources = fixture["sources"]
        if _canonical_sha(sources.get(source)) != before["sha"] or (source in sources) != before["present"]:
            if before["present"]:
                sources[source] = copy.deepcopy(before["section"])
            else:
                sources.pop(source, None)
            # This source's promotions bumped built_at; earlier sources' bumps
            # are already in `before` (snapshot taken just before this source).
            if before["built_at"] is None:
                fixture.pop("built_at", None)
            else:
                fixture["built_at"] = before["built_at"]
            # Same serialisation as promote_comparison_section.py.
            fixture_path.write_text(json.dumps(fixture, separators=(",", ":")))
        after = _read_fixture(repo)["sources"]
        if _canonical_sha(after.get(source)) != before["sha"] or (source in after) != before["present"]:
            raise ValueError("restored section does not match the pre-run section")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        result["stage"] = "restore"
        result["detail"] += f" | hold NOT isolated: restore failed: {exc}"
        result["held"] = False
        return result

    promo_dir = Path(repo) / PROMOTIONS_REL
    rolled_back_records = []
    if promo_dir.is_dir():
        for p in sorted(promo_dir.glob(f"{source}-*-promotion.json")):
            if p.name not in before["promotion_records"]:
                target = p.with_name(p.name[: -len(".json")] + ".rolled-back.json")
                p.rename(target)
                rolled_back_records.append(target.name)

    kept = before["section"] if before["present"] else None
    kept_week = section_week(kept)
    weeks_behind = (nfl_week - kept_week) if (nfl_week is not None and kept_week is not None) else None
    # Amber: the reader sees a source at most one week old, labelled with its
    # own week (build-lag-001's one-week tolerance). Red: two or more weeks
    # behind, or no section/week at all -- held for more than a week.
    severity = "amber" if (weeks_behind is not None and weeks_behind <= 1) else "red"
    result.update({
        "status": "held",
        "rolled_back": result.get("promoted", 0),
        "promoted": 0,
        "rolled_back_records": rolled_back_records,
        "kept_section": {
            "present": before["present"],
            "week_designated": (kept or {}).get("week_designated"),
            "content_vintage": (kept or {}).get("content_vintage"),
            "content_week": kept_week,
        },
        "weeks_behind": weeks_behind,
        "hold_severity": severity,
    })
    print(f"  ⚠ HELD (isolated): kept last promoted {source} section "
          f"(week {kept_week}, {weeks_behind} week(s) behind -> {severity}); "
          f"rolled back {result['rolled_back']} section(s) promoted this run")
    return result


def _verify_cbsros_section(repo, snapshot_vintage):
    """Review GATE for the cbsros chain (not a bypass).

    The section builder writes sources.cbsros directly to the fixture, so
    there is no candidate-vs-fixture review artifact. This verification is
    the gate: it checks the rebuilt section is well-formed and halts the
    chain fail-closed if not. Raises ChainHalt("review", ...) on any check
    failure.
    """
    fixture_path = repo / "data" / "fixtures" / "current" / "comparison-sources-data.json"
    try:
        fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ChainHalt("review", f"cannot read fixture for review: {exc}")
    section = (fixture.get("sources") or {}).get("cbsros")
    if not isinstance(section, dict):
        raise ChainHalt("review", "sources.cbsros missing from fixture after section build")
    combos = section.get("combos") or {}
    missing = [k for k in CBSROS_COMBO_KEYS if k not in combos]
    if missing:
        raise ChainHalt("review", f"cbsros section missing combos: {missing}")
    bad = []
    n_values = 0
    for key in CBSROS_COMBO_KEYS:
        combo = combos[key] or {}
        values = combo.get("values") or {}
        native = combo.get("native") or {}
        if not values or not native:
            bad.append(f"{key}: empty values/native")
            continue
        if set(values) != set(native):
            bad.append(f"{key}: values/native key mismatch")
            continue
        for slug, val in values.items():
            # DDF two-tier: waiver-tier players legitimately score 0.0
            # (ESPN's DDF section has 177/353 zeros). Values must be numeric
            # and non-negative; negatives or non-numbers are corruption.
            if not isinstance(val, (int, float)) or val < 0:
                bad.append(f"{key}: invalid value for {slug}: {val!r}")
                break
        for slug, val in native.items():
            if not isinstance(val, (int, float)) or val < 0:
                bad.append(f"{key}: invalid native for {slug}: {val!r}")
                break
        n_values += len(values)
    if bad:
        raise ChainHalt("review", f"cbsros section malformed: {bad[:5]}")
    vintage = section.get("vintage")
    if snapshot_vintage and vintage != snapshot_vintage:
        raise ChainHalt(
            "review",
            f"cbsros section vintage {vintage!r} != snapshot vintage {snapshot_vintage!r}",
        )
    print(f"  ✓ review: 12 combos, {n_values} values, vintage {vintage}")
    return n_values


def run_cbsros_source(source="cbsros", nfl_week=None, repo=REPO, run_fn=run):
    """Rebuild the cbsros chain: snapshot -> DDF leg -> section -> review.

    cbsros does NOT go through the generic match -> reference -> section ->
    quantile-reindex path. reindex_comparison_section.py always quantile-maps
    to the ESPN anchor, which would transform cbsros's deliberate DDF-direct
    values (factor 1.0, no stale-pie rescale). Its production pipeline is
    snapshot -> DDF leg -> section, and this chain mirrors that pipeline
    instead of forcing it through the quantile path.

    Returns a result dict; never raises. The first hold/failure halts the
    source's chain immediately (ChainHalt) and is recorded as failed.
    """
    result = {
        "source": source,
        "status": "failed",  # fail-closed default; set to "ok" only on full success
        "stage": None,
        "detail": "",
        "promoted": 0,
        "sections": 1,
    }
    repo = Path(repo)
    try:
        # 1. Snapshot
        result["stage"] = "snapshot"
        snapshot = find_latest_snapshot(repo, source)
        if not snapshot:
            raise ChainHalt("snapshot", "no snapshot.json found under data/raw/sources")
        print(f"  Snapshot: {snapshot.relative_to(repo)}")
        try:
            snapshot_vintage = json.loads(snapshot.read_text(encoding="utf-8")).get("vintage_date")
        except (OSError, ValueError):
            snapshot_vintage = None

        # 2. DDF leg: rebuild all 12 legs from the snapshot (3 scorings x 4 team counts)
        result["stage"] = "leg"
        for scoring, teams in ((s, t) for s in CBSROS_LEG_SCORINGS for t in CBSROS_LEG_TEAMS):
            ok, out = run_fn([
                "python3", "pipelines/build_cbsros_ddf_leg.py",
                "--snapshot", str(snapshot),
                "--scoring", scoring,
                "--teams", str(teams),
            ])
            if not ok:
                raise ChainHalt("leg", f"DDF leg build failed (scoring={scoring} teams={teams}): {out[-500:]}")
        print("  ✓ 12 DDF legs rebuilt")

        # 3. Section: build the fixture section from the fresh legs
        result["stage"] = "section"
        ok, out = run_fn(["python3", "pipelines/build_cbsros_section_from_ddf_leg.py"])
        if not ok:
            raise ChainHalt("section", f"cbsros section build failed: {out[-500:]}")
        print("  ✓ cbsros fixture section rebuilt")

        # 4. Review gate: verify the rebuilt section (halts fail-closed)
        result["stage"] = "review"
        n_values = _verify_cbsros_section(repo, snapshot_vintage)

        result["status"] = "ok"
        result["stage"] = "complete"
        result["promoted"] = 1
        result["detail"] = (
            f"snapshot {snapshot_vintage} -> 12 DDF legs -> section; "
            f"review passed ({n_values} values)"
        )
        print(f"  ✓ cbsros chain complete: {result['detail']}")

    except ChainHalt as h:
        result["stage"] = h.stage
        result["detail"] = h.detail
        print(f"  ✗ HALT at stage '{h.stage}': {h.detail}")
    except Exception as e:  # fail closed on unexpected errors too
        result["stage"] = "error"
        result["detail"] = f"unexpected error: {e}"
        print(f"  ✗ ERROR: {e}")

    return result


ESPN_LEG_SCORINGS = ("standard", "half_ppr", "ppr")
ESPN_LEG_TEAMS = (8, 10, 12, 14)
ESPN_COMBO_KEYS = [
    f"{s}_{t}"
    for s in ("standard", "half", "full")
    for t in ESPN_LEG_TEAMS
]


def _verify_espn_section(repo, snapshot_vintage):
    """Review gate for the rebuilt ESPN section. Raises ChainHalt on failure."""
    fixture_path = repo / "data" / "fixtures" / "current" / "comparison-sources-data.json"
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    section = (fixture.get("sources") or {}).get("espn") or {}
    combos = section.get("combos") or {}
    missing = [k for k in ESPN_COMBO_KEYS if k not in combos]
    if missing:
        raise ChainHalt("review", f"espn section missing combos: {missing}")
    # ESPN is DDF-modeled, never as-published: the section must carry the
    # modeled provenance and per-game native unit, not ROS totals.
    if section.get("value_provenance") != "modeled":
        raise ChainHalt(
            "review",
            f"espn value_provenance is {section.get('value_provenance')!r}, expected 'modeled'",
        )
    bad = []
    n_values = 0
    for key in ESPN_COMBO_KEYS:
        combo = combos[key] or {}
        values = combo.get("values") or {}
        native = combo.get("native") or {}
        if not values or not native:
            bad.append(f"{key}: empty values/native")
            continue
        if set(values) != set(native):
            bad.append(f"{key}: values/native key mismatch")
            continue
        for slug, val in values.items():
            # DDF two-tier: waiver-tier players legitimately score 0.0.
            # Values must be numeric and non-negative; negatives or
            # non-numbers are corruption.
            if not isinstance(val, (int, float)) or val < 0:
                bad.append(f"{key}: invalid value for {slug}: {val!r}")
                break
        for slug, val in native.items():
            if not isinstance(val, (int, float)) or val < 0:
                bad.append(f"{key}: invalid native for {slug}: {val!r}")
                break
            # Per-game sanity: no ESPN per-game native should look like a
            # rest-of-season total. Anything above 40 pts/game is not a
            # per-game number (sanity bound, not a value judgment).
            if val > 40:
                bad.append(f"{key}: native {val} for {slug} looks like ROS total, not per-game")
                break
        n_values += len(values)
    if bad:
        raise ChainHalt("review", f"espn section malformed: {bad[:5]}")
    # The section stamps espn_snapshot from the DDF leg's espn_snapshot_date
    # (the underlying ESPN data vintage), which tracks data/inputs/espn_projections.csv,
    # not the snapshot directory name. Verify the section matches the newest
    # leg's vintage so a stale section can't pass.
    leg_dir = repo / "data" / "ddf-two-tier"
    newest_vintage = None
    newest_gen = ""
    for leg_path in leg_dir.glob("*/ddf_leg.json"):
        try:
            leg = json.loads(leg_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        gen = leg.get("generated_at", "")
        if gen > newest_gen:
            newest_gen = gen
            newest_vintage = (leg.get("inputs") or {}).get("espn_snapshot_date")
    espn_snapshot = section.get("espn_snapshot")
    if newest_vintage and espn_snapshot != newest_vintage:
        raise ChainHalt(
            "review",
            f"espn section snapshot {espn_snapshot!r} != newest leg vintage {newest_vintage!r}",
        )
    print(f"  ✓ review: 12 combos, {n_values} values, snapshot {espn_snapshot}")
    return n_values


def run_espn_source(source="espn", nfl_week=None, repo=REPO, run_fn=run):
    """Rebuild the espn chain: snapshot -> DDF leg -> section -> review.

    ESPN does NOT go through the generic match -> reference -> section ->
    reindex path. That path treats ESPN as an as-published trade chart and
    takes raw rest-of-season totals as natives. ESPN's fixture section is
    DDF-modeled: ESPN projections run through the DDF two-tier leg and
    natives are per-game values. This chain mirrors that pipeline
    (snapshot -> DDF leg -> section) instead of forcing ESPN through the
    published-chart path.

    Returns a result dict; never raises. The first hold/failure halts the
    source's chain immediately (ChainHalt) and is recorded as failed.
    """
    result = {
        "source": source,
        "status": "failed",  # fail-closed default; set to "ok" only on full success
        "stage": None,
        "detail": "",
        "promoted": 0,
        "sections": 1,
    }
    repo = Path(repo)
    try:
        # 1. Snapshot (for vintage tracking; the leg builder reads the CSV)
        result["stage"] = "snapshot"
        snapshot = find_latest_snapshot(repo, source)
        if not snapshot:
            raise ChainHalt("snapshot", "no snapshot.json found under data/raw/sources")
        print(f"  Snapshot: {snapshot.relative_to(repo)}")
        try:
            snapshot_vintage = json.loads(snapshot.read_text(encoding="utf-8")).get("vintage_date")
        except (OSError, ValueError):
            snapshot_vintage = None

        # 2. DDF leg: rebuild all 12 legs from the ESPN CSV (3 scorings x 4 team counts)
        result["stage"] = "leg"
        for scoring, teams in ((s, t) for s in ESPN_LEG_SCORINGS for t in ESPN_LEG_TEAMS):
            ok, out = run_fn([
                "python3", "pipelines/build_ddf_two_tier_leg.py",
                "--scoring", scoring,
                "--teams", str(teams),
            ])
            if not ok:
                raise ChainHalt("leg", f"DDF leg build failed (scoring={scoring} teams={teams}): {out[-500:]}")
        print("  ✓ 12 DDF legs rebuilt")

        # 3. Section: build the fixture section from the fresh legs
        result["stage"] = "section"
        ok, out = run_fn(["python3", "pipelines/build_espn_section_from_ddf_leg.py"])
        if not ok:
            raise ChainHalt("section", f"espn section build failed: {out[-500:]}")
        print("  ✓ espn fixture section rebuilt")

        # 4. Review gate: verify the rebuilt section (halts fail-closed)
        result["stage"] = "review"
        n_values = _verify_espn_section(repo, snapshot_vintage)

        result["status"] = "ok"
        result["stage"] = "complete"
        result["promoted"] = 1
        result["detail"] = (
            f"snapshot {snapshot_vintage} -> 12 DDF legs -> section; "
            f"review passed ({n_values} values)"
        )
        print(f"  ✓ espn chain complete: {result['detail']}")

    except ChainHalt as h:
        result["stage"] = h.stage
        result["detail"] = h.detail
        print(f"  ✗ HALT at stage '{h.stage}': {h.detail}")
    except Exception as e:  # fail closed on unexpected errors too
        result["stage"] = "error"
        result["detail"] = f"unexpected error: {e}"
        print(f"  ✗ ERROR: {e}")

    return result


def run_retranslate(repo, run_fn, nfl_week=None):
    """Stage 6b (V2-WAIVER-COVERAGE): re-translate every published chart in
    the promoted fixture. Raises ChainHalt on failure.

    A short chart's waiver line is extrapolated from the OTHER published
    charts' saved natives, so promoting one chart can move another chart's
    saved values. Each section was translated against the fixture as it stood
    when that section ran; this pass makes every saved 12-team value the
    translation of the fixture the site will show (the stored-drift parity
    check, tests/test_vorp_translation_js_parity.py, requires it). Natives
    are not touched; a chart whose peers did not change gets the same values.
    """
    cmd = ["python3", "pipelines/translate_via_vorp.py",
           "--fixture", str(repo / "data/fixtures/current/comparison-sources-data.json"),
           "--translation", "natives"]
    if nfl_week is not None:
        cmd += ["--week", str(nfl_week)]
    ok, out = run_fn(cmd)
    if not ok:
        raise ChainHalt("retranslate", f"fixture re-translation failed: {out[-500:]}")
    print("  ✓ Published charts re-translated against the promoted fixture")


def run_fit(repo, run_fn):
    """Stage 7: bias-correction fit. Raises ChainHalt on failure.

    Only called when every source succeeded. Fits affine adjustment cells
    per (source, position, tier) against the DDF leg and syncs the live
    asset for deployment.
    """
    ok, out = run_fn([
        "python3", "pipelines/build_adjustment_inputs.py",
        "--fixture", str(repo / "data/fixtures/current/comparison-sources-data.json"),
    ])
    if not ok:
        raise ChainHalt("fit", f"fit failed: {out[-500:]}")
    print("  ✓ Fit complete — adjustment-inputs.json updated")
    src = repo / "app" / "trade-value-chart" / "assets" / "adjustment-inputs.json"
    dst = repo / "dist" / "assets" / "adjustment-inputs.json"
    if src.is_file():
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        print(f"  ✓ Synced to {dst}")
    else:
        raise ChainHalt("fit", f"fit exited 0 but live asset missing: {src}")


def run_adjusted_sections(repo, run_fn):
    """Stage 8: build _adjusted fixture sections. Raises ChainHalt on failure.

    Only called when the fit succeeded. Applies the fitted cells to the
    raw published values, generating {source}_adjusted sections in the
    fixture for the comparison dashboard and build_reference_data.py.

    Jeremy 2026-09-29: "Fitting every week can't be an ad hoc modeling
    project." The _adjusted sections are generated deterministically from
    the fit cells — same inputs, same outputs, every week.
    """
    ok, out = run_fn([
        "python3", "pipelines/build_adjusted_fixture_sections.py",
        "--fixture", str(repo / "data/fixtures/current/comparison-sources-data.json"),
        "--inputs", str(repo / "app" / "trade-value-chart" / "assets" / "adjustment-inputs.json"),
        "--players", str(repo / "data" / "fixtures" / "current" / "players.json"),
    ])
    if not ok:
        raise ChainHalt("adjusted_sections", f"adjusted sections failed: {out[-500:]}")
    print("  ✓ _adjusted fixture sections built")


def run_vorp_refresh(nfl_week, repo, run_fn):
    """Stage 9 (JEG-70): refresh VORP translation grains if stale.

    Demand-driven instead of a separate scheduled workflow: the chain
    already runs every 6h with Supabase access. If any of the 21
    as-published grains is older than the current NFL week, re-run the
    unified translation now. Reads the freshly promoted fixture, so the
    next chain run's vorp-translate stage wires the new grains.

    Fail-safe: refresh failure is logged, never halts the chain (the
    per-combo vorp-translate stage falls back to reindex).
    """
    try:
        # Staleness check first: cheap, writes nothing.
        ok, out = run_fn([
            "python3", "pipelines/refresh_vorp_translation.py",
            "--check-only", "--week", str(nfl_week),
        ])
    except Exception as e:
        print(f"  ✗ VORP staleness check failed (non-fatal): {e}")
        return {"status": "failed", "detail": f"staleness check failed: {e}"}
    if ok:
        print("  ✓ VORP grains fresh; no refresh needed")
        return {"status": "ok", "detail": "grains fresh, no refresh needed"}
    print("  VORP grains stale; refreshing...")
    try:
        ok, out = run_fn([
            "python3", "pipelines/refresh_vorp_translation.py",
            "--week", str(nfl_week),
        ])
    except Exception as e:
        print(f"  ✗ VORP refresh failed (non-fatal): {e}")
        return {"status": "failed", "detail": f"refresh failed: {e}"}
    last = out.strip().splitlines()[-1] if out and out.strip() else "no output"
    if ok:
        print(f"  ✓ VORP refresh complete: {last}")
        return {"status": "ok", "detail": f"refreshed: {last}"}
    print(f"  ✗ VORP refresh failed (non-fatal): {last}")
    return {"status": "failed", "detail": f"refresh failed: {last}"}


def run_lineage_rebuild(repo, run_fn):
    """Stage 10 (JEG-200): rebuild source value lineage locally.

    Runs pipelines/build_source_value_lineage.py with the same inputs the
    chain just produced (fresh fixture, fresh scrape artifact). Where raw
    snapshots exist (local dev), this writes a fresh lineage artifact
    whose `generated_at` matches the fixture vintage. Where snapshots are
    absent (CI), the builder raises SystemExit and stamps an explicit
    staleness badge on the committed artifact instead.

    The builder reads its fixture input from dist/assets/ (DATA_PATH), so
    Stage 10 first syncs the canonical fixture
    (data/fixtures/current/comparison-sources-data.json) there -- otherwise
    the "fresh" rebuild would bake stale inputs, and the staleness badge
    would compare the lineage against a stale copy and report lag 0.

    Fail-safe: a rebuild failure is logged and never halts the chain. The
    lineage is a monitoring artifact, not a deployment gate. We mirror
    Stage 9's fail-safe pattern: try / except / log / return status dict.
    """
    canonical = os.path.join(repo, "data", "fixtures", "current",
                             "comparison-sources-data.json")
    builder_input = os.path.join(repo, "dist", "assets",
                                 "comparison-sources-data.json")
    try:
        if os.path.exists(canonical):
            os.makedirs(os.path.dirname(builder_input), exist_ok=True)
            shutil.copy2(canonical, builder_input)
            print(f"  synced fixture -> {builder_input}")
        else:
            print(f"  ! canonical fixture missing: {canonical} (continuing)")
    except Exception as e:
        print(f"  ! fixture sync failed (non-fatal): {e}")
    try:
        ok, out = run_fn([
            "python3", "pipelines/build_source_value_lineage.py",
        ])
    except Exception as e:
        print(f"  ✗ lineage rebuild raised (non-fatal): {e}")
        return {"status": "failed", "detail": f"unexpected error: {e}"}
    last = out.strip().splitlines()[-1] if out and out.strip() else "no output"
    if ok:
        print(f"  ✓ lineage rebuild complete: {last}")
        return {"status": "ok", "detail": f"rebuilt: {last}"}
    # Builder exits non-zero (e.g. require_snapshot_natives() raises
    # SystemExit on a machine without data/raw). The committed artifact has
    # been stamped with the staleness badge; chain continues.
    print(f"  ✗ lineage rebuild failed (non-fatal, badge stamped): {last}")
    return {"status": "failed", "detail": f"builder raised: {last}"}


def describe_result(result):
    """Human-readable one-line status for the dashboard (string, not a code)."""
    if result["status"] == "ok":
        return f"promoted {result['promoted']}/{result['sections']}"
    if result["status"] == "held":
        kept = result.get("kept_section") or {}
        label = kept.get("week_designated") or kept.get("content_vintage") or "no prior section"
        return (f"HELD at stage 'review' ({result.get('hold_severity')}): kept last promoted "
                f"section ({label}); held candidate not promoted: {result.get('detail', '')}")
    stage = result.get("stage") or "unknown"
    return f"FAILED at stage '{stage}': {result.get('detail', '')}"


def source_vintages(repo):
    """Per-source content week as the import-health gate judged it.

    build-lag-001: the chain builds every source on its newest data, so a
    run can mix weeks (FantasyCalc Week 5, CBS Week 4). The chain's own
    `nfl_week` is the current content week, NOT the week of every section;
    each source is labelled by its own content_vintage (stamped per section
    at promotion). This block records what each source was built from so
    the monitor never has to infer it from `nfl_week`. Read-only; a missing
    or unreadable health file yields {} (the workflow's gate step runs
    first and writes it).
    """
    path = Path(repo) / "output" / "source-import-health.json"
    try:
        health = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    entries = health.get("sources") or {}
    out = {}
    for source in SOURCES:
        entry = entries.get(source)
        if not isinstance(entry, dict):
            continue
        reason = str(entry.get("failure_reason") or "")
        out[source] = {
            "content_vintage": entry.get("content_vintage"),
            "content_week": entry.get("content_week"),
            "health_status": entry.get("status"),
            "lagging_one_week": reason.startswith("LAGGING_ONE_WEEK"),
        }
    return out


def write_chain_status(repo, results, fit_result, adjusted_result, nfl_week, runner):
    """Write the chain status JSON for the monitoring dashboard.

    `success` (the exit code, and what lets the workflow publish the fixture)
    requires: every source reached and either ok or an isolated hold; at
    least one review-gated source promoted; fit and _adjusted both ok.
    """
    failed = [s for s, r in results.items() if r["status"] not in ("ok", "held")]
    failed += [s for s in SOURCES if s not in results]  # never reached
    held = sorted(s for s, r in results.items() if r["status"] == "held")
    if all_review_gated_held(results):
        failed.append("all_review_gated_sources_held")
    if fit_result is None or fit_result["status"] != "ok":
        failed.append("fit")
    if adjusted_result is None or adjusted_result["status"] != "ok":
        failed.append("adjusted_sections")
    success = len(failed) == 0
    severities = [results[s].get("hold_severity") for s in held]
    hold_severity = ("red" if "red" in severities else "amber") if held else "none"
    status_data = {
        "run_at": datetime.now(timezone.utc).isoformat(),
        "nfl_week": nfl_week,
        "sources": {s: describe_result(r) for s, r in results.items()},
        "failed": sorted(set(failed)),
        "success": success,
        # per-source-promotion-001: the run can publish with held sources.
        # "published_with_holds" is a success that the monitor still shows
        # amber/red per hold_severity; it is never reported as plain green.
        "outcome": ("failed" if not success else
                    "published_with_holds" if held else "green"),
        "held": held,
        "hold_severity": hold_severity,
        "held_detail": {s: {
            "detail": results[s].get("detail"),
            "kept_section": results[s].get("kept_section"),
            "weeks_behind": results[s].get("weeks_behind"),
            "hold_severity": results[s].get("hold_severity"),
            "rolled_back": results[s].get("rolled_back"),
        } for s in held},
        # Honest runner label: "github-actions" or "local".
        # (An earlier revision mislabeled local runs as "muse-cron".)
        "runner": runner,
        "detail": results,
        "fit": fit_result,
        "adjusted_sections": adjusted_result,
        "source_vintages": source_vintages(repo),
    }
    for rel in ("output/comparison-chain-status.json",
                "dist/modules/comparison-chain-status.json"):
        path = repo / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(status_data, f, indent=2)
    return status_data


def all_review_gated_held(results):
    """True when every review-gated source that ran was held (nothing new)."""
    gated = [s for s in HOLD_ISOLATED_SOURCES if s in results]
    return bool(gated) and all(results[s]["status"] == "held" for s in gated)


def write_step_summary(status_data, path=None):
    """Append a held-source report to the GitHub run summary (if available)."""
    path = path or os.environ.get("GITHUB_STEP_SUMMARY")
    lines = [f"## Comparison chain: {status_data.get('outcome')}", "",
             "| source | result |", "| --- | --- |"]
    for source, text in (status_data.get("sources") or {}).items():
        lines.append(f"| {source} | {str(text).replace('|', '/')[:400]} |")
    for source in status_data.get("held") or []:
        d = status_data["held_detail"][source]
        level = "error" if d.get("hold_severity") == "red" else "warning"
        kept = d.get("kept_section") or {}
        print(f"::{level} title=Source held ({source})::{source} review is 'hold'; site keeps its "
              f"last promoted section ({kept.get('week_designated') or kept.get('content_vintage')}), "
              f"{d.get('weeks_behind')} week(s) behind. A human must review the hold.")
    if not path:
        return
    try:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")
    except OSError as exc:
        print(f"::warning::could not write step summary: {exc}")


def execute_chain(nfl_week=None, repo=REPO, run_fn=run):
    """Run the full chain. Returns (status_data, exit_code).

    Status is written through a finally block so partial/interrupted runs
    are always recorded.
    """
    repo = Path(repo)
    runner = "github-actions" if os.environ.get("GITHUB_ACTIONS") == "true" else "local"

    print("=" * 60)
    print("COMPARISON CHAIN REBUILD (fail-closed)")
    print("=" * 60)

    results = {}
    fit_result = None
    adjusted_result = None
    lineage_result = {"status": "skipped", "detail": "not reached"}
    try:
        for source in SOURCES:
            print(f"\n[{source}] Starting chain...")
            # cbsros has its own DDF-leg pipeline (not the quantile-reindex
            # path); its chain mirrors that pipeline.
            if source == "cbsros":
                results[source] = run_cbsros_source(source, nfl_week, repo, run_fn)
            # ESPN is DDF-modeled (per-game natives via the two-tier leg),
            # not an as-published chart; it must not go through the generic
            # published-chart path (which would take raw ROS totals).
            elif source == "espn":
                results[source] = run_espn_source(source, nfl_week, repo, run_fn)
            else:
                before = (snapshot_source_state(repo, source)
                          if source in HOLD_ISOLATED_SOURCES else None)
                results[source] = run_source(source, nfl_week, repo, run_fn)
                if source in HOLD_ISOLATED_SOURCES and results[source].get("held"):
                    isolate_hold(repo, source, before, results[source], nfl_week)

        failed_sources = [s for s, r in results.items() if r["status"] not in ("ok", "held")]
        if not failed_sources and all_review_gated_held(results):
            failed_sources = ["all review-gated sources held"]
        if failed_sources:
            # The fit reads the combined fixture — it must not run against
            # a partially-rebuilt fixture. (An isolated hold is not partial:
            # its section was restored to the last promoted one.)
            fit_result = {
                "status": "skipped",
                "detail": f"skipped: sources failed: {', '.join(failed_sources)}",
            }
            print("\n" + "=" * 60)
            print("STAGE 7: BIAS-CORRECTION FIT — SKIPPED (chain failed)")
            print("=" * 60)
        else:
            print("\n" + "=" * 60)
            print("STAGE 7: BIAS-CORRECTION FIT")
            print("=" * 60)
            try:
                run_retranslate(repo, run_fn, nfl_week)
                run_fit(repo, run_fn)
                fit_result = {"status": "ok", "detail": "fit complete"}
            except ChainHalt as h:
                fit_result = {"status": "failed", "stage": h.stage, "detail": h.detail}
                print(f"  ✗ HALT at stage '{h.stage}': {h.detail}")
            except Exception as e:
                fit_result = {"status": "failed", "stage": "error",
                              "detail": f"unexpected error: {e}"}
                print(f"  ✗ ERROR: {e}")

        # Stage 8: build _adjusted fixture sections (only if fit succeeded).
        # The comparison dashboard and build_reference_data.py require these.
        if fit_result is not None and fit_result["status"] == "ok":
            print("\n" + "=" * 60)
            print("STAGE 8: ADJUSTED FIXTURE SECTIONS")
            print("=" * 60)
            try:
                run_adjusted_sections(repo, run_fn)
                adjusted_result = {"status": "ok", "detail": "_adjusted sections built"}
            except ChainHalt as h:
                adjusted_result = {"status": "failed", "stage": h.stage, "detail": h.detail}
                print(f"  ✗ HALT at stage '{h.stage}': {h.detail}")
            except Exception as e:
                adjusted_result = {"status": "failed", "stage": "error",
                                   "detail": f"unexpected error: {e}"}
                print(f"  ✗ ERROR: {e}")
        elif fit_result is not None:
            adjusted_result = {
                "status": "skipped",
                "detail": f"skipped: fit {fit_result['status']}",
            }
            print("\n" + "=" * 60)
            print("STAGE 8: ADJUSTED FIXTURE SECTIONS — SKIPPED")
            print("=" * 60)

        # Stage 9: VORP translation refresh (JEG-70, demand-driven).
        # Refreshes the Supabase grains when stale; the next chain run's
        # vorp-translate stage wires them. Fail-safe: never halts the chain.
        vorp_result = {"status": "skipped", "detail": "no nfl_week"}
        if nfl_week is not None:
            print("\n" + "=" * 60)
            print("STAGE 9: VORP TRANSLATION REFRESH (if stale)")
            print("=" * 60)
            try:
                vorp_result = run_vorp_refresh(nfl_week, repo, run_fn)
            except Exception as e:
                vorp_result = {"status": "failed",
                               "detail": f"unexpected error: {e}"}
                print(f"  ✗ VORP refresh error (non-fatal): {e}")
        else:
            print("  VORP refresh skipped: no nfl_week")

        # Stage 10 (JEG-200): rebuild source value lineage locally so the
        # dashboard's lineage artifact reflects the fresh fixture vintage.
        # Same run, same inputs, same fixture vintage as Stage 9 wrote.
        # Fail-safe: rebuild failure is logged, never halts the chain.
        # When the builder raises (e.g. CI without data/raw snapshots), the
        # committed artifact is stamped with the staleness badge by the
        # builder's own SystemExit handler before this stage returns.
        print("\n" + "=" * 60)
        print("STAGE 10: SOURCE VALUE LINEAGE REBUILD (JEG-200)")
        print("=" * 60)
        try:
            lineage_result = run_lineage_rebuild(repo, run_fn)
        except Exception as e:
            lineage_result = {"status": "failed",
                              "detail": f"unexpected error: {e}"}
            print(f"  ✗ lineage rebuild error (non-fatal): {e}")

        print("\n" + "=" * 60)
        print("CHAIN COMPLETE")
        print("=" * 60)
        for source, r in results.items():
            print(f"  {source}: {describe_result(r)}")
        if fit_result is not None:
            print(f"  fit: {fit_result['status']}")
        if adjusted_result is not None:
            print(f"  adjusted_sections: {adjusted_result['status']}")
        print(f"  vorp_refresh: {vorp_result['status']}")
        print(f"  lineage_rebuild: {lineage_result['status']}")
    finally:
        # Always record the run, even on interruption or unexpected error.
        # results/fit_result/adjusted_result may be partially populated — write what's known.
        status_data = write_chain_status(repo, results, fit_result, adjusted_result, nfl_week, runner)
        print(f"\nStatus written to output/comparison-chain-status.json "
              f"(success={status_data['success']}, outcome={status_data['outcome']}, "
              f"held={status_data['held']})")
        write_step_summary(status_data)
    return status_data


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--nfl-week", type=int, default=None)
    args = parser.parse_args()

    try:
        status_data = execute_chain(args.nfl_week)
        success = status_data["success"]
    except Exception as e:
        # Status was still written by execute_chain's finally block.
        print(f"Chain aborted with unexpected error: {e}", file=sys.stderr)
        success = False
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
