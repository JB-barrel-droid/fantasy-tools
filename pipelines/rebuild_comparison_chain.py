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
the rebuilt fixture section fail-closed. razzball (Razzball rest-of-season
projections) runs the same path; a razzball failure keeps its last promoted
section (isolated, like a review hold) instead of failing the chain.

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
- Source resiliency (Jeremy 2026-10-08, decision source-resiliency-001):
  the isolation above now covers ANY single-source failure, not only a
  review hold. A source whose import left no snapshot, whose match,
  reference, section, reindex, review or promote stage failed, whose review
  returned a malformed or non-'ready' verdict, or whose stage script
  crashed keeps its last promoted fixture section byte-for-byte (the whole
  fixture is restored to its state just before that source ran), and the
  other sources publish. ESPN and cbsros are covered too: their DDF legs
  under data/ddf-two-tier are restored with the section, so a failed ESPN
  refresh leaves the last good anchor in place and every other source is
  reindexed against it. Still fail-closed: a restore that cannot be
  verified, a run in which every review-gated source held or failed, and
  any failure in the shared stages (re-index + rank guard, fit, _adjusted).
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

sys.path.insert(0, str(Path(__file__).resolve().parent))
import projection_identity  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
# razzball (GAP-RAZZBALL-SUFFIX-POOL, 2026-10-08): the workflow imported the
# razzball snapshot every run, but nothing rebuilt its legs or section, so the
# published section stayed on the vintage of its last hand build.
SOURCES = ["usatoday", "fantasycalc", "fantasypros", "espn", "cbs", "cbsros", "razzball"]

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

# source-resiliency-001 (Jeremy 2026-10-08): ANY failure in one of these
# sources is isolated -- the source keeps its last promoted section, the
# others publish. HOLD_ISOLATED_SOURCES above stays the review-gated set
# (the "every review-gated source held or failed" rule reads it).
FAILURE_ISOLATED_SOURCES = tuple(SOURCES)

# Sources whose stages also write DDF legs under data/ddf-two-tier that later
# stages read (the fit reads the newest ESPN leg). A failed run of these
# sources restores its legs together with its fixture section.
LEG_FILES = {"espn": "ddf_leg.json", "cbsros": "ddf_leg_cbsros.json",
             "razzball": "ddf_leg_razzball.json"}
LEG_ROOT_REL = Path("data") / "ddf-two-tier"

FIXTURE_REL = Path("data") / "fixtures" / "current" / "comparison-sources-data.json"
PROMOTIONS_REL = Path("output") / "comparison-promotions"

# cbsros DDF-leg build matrix: the section builder expects one leg per
# (scoring, teams) pair, 3 scorings x 4 team counts = 12 legs.
CBSROS_LEG_SCORINGS = ("standard", "half_ppr", "ppr")
CBSROS_LEG_TEAMS = (8, 10, 12, 14)
CBSROS_COMBO_KEYS = [f"{s}_{t}" for s in ("full", "half", "standard")
                     for t in CBSROS_LEG_TEAMS]

# Projection sources priced through their own DDF leg (snapshot -> 12 legs ->
# section), never the quantile-reindex path. Same 12-combo matrix as cbsros.
LEG_SECTION_SCRIPTS = {
    "cbsros": ("pipelines/build_cbsros_ddf_leg.py",
               "pipelines/build_cbsros_section_from_ddf_leg.py"),
    "razzball": ("pipelines/build_razzball_ddf_leg.py",
                 "pipelines/build_razzball_section_from_ddf_leg.py"),
}

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
    # Sort chronologically. A plain name sort put "week-10" before "week-4"
    # (and before the committed week-4 fantasycalc snapshot in CI), so from
    # Week 10 the chain would have rebuilt FantasyCalc and CBS from an old
    # week. Dates (YYYY-MM-DD) and week-N both order by their numbers.
    candidates.sort(key=snapshot_sort_key)
    return candidates[-1] / "snapshot.json"


def snapshot_sort_key(path):
    """Chronological key for a snapshot directory name (week-N or a date)."""
    import re
    return (tuple(int(n) for n in re.findall(r"\d+", path.name)), path.name)


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
    """Reindex -> review -> promote ONE section. Fail-closed.

    Returns "promoted". Raises ChainHalt on any hold/failure/error.
    NEVER modifies the review artifact: a hold stays a hold.

    JEG-482 removed the VORP-translate step (JEG-64) that ran between reindex
    and review: it overwrote a published chart's Indexed values with its
    value-above-waivers translation, which reordered the chart. Indexed is
    the reindex stage's one-factor rescale; value above waivers is the VORP
    vs waivers view, derived in the browser from the natives.
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
    try:
        fixture_bytes = (Path(repo) / FIXTURE_REL).read_bytes()
    except OSError:
        return None
    return {
        "present": source in sources,
        "section": copy.deepcopy(sources.get(source)),
        "sha": _canonical_sha(sources.get(source)),
        "built_at": fixture.get("built_at"),
        "promotion_records": records,
        # source-resiliency-001: the whole fixture as it was just before this
        # source ran. Only this source's stages write the fixture during its
        # run, so restoring these bytes undoes exactly that source's writes
        # (section, built_at, source_validation, anything else its builder
        # touched) and nothing of the sources that ran before it.
        "fixture_bytes": fixture_bytes,
        "fixture_sha": _canonical_sha(fixture),
        "legs": _leg_files(repo, source),
    }


def _leg_paths(repo, source):
    name = LEG_FILES.get(source)
    root = Path(repo) / LEG_ROOT_REL
    if not name or not root.is_dir():
        return []
    return sorted(p for p in root.rglob(name)
                  if f"-{source}-" in str(p.relative_to(root)))


def _leg_files(repo, source):
    """{relative path: bytes} of a source's DDF legs (empty for chart sources)."""
    return {str(p.relative_to(repo)): p.read_bytes() for p in _leg_paths(repo, source)}


def _restore_legs(repo, source, before_legs):
    """Put a source's DDF legs back exactly as they were before its run."""
    repo = Path(repo)
    root = repo / LEG_ROOT_REL
    for p in _leg_paths(repo, source):
        rel = str(p.relative_to(repo))
        if rel not in before_legs:
            p.unlink()
            parent = p.parent
            while parent != root and parent.is_dir() and not any(parent.iterdir()):
                parent.rmdir()
                parent = parent.parent
    for rel, data in before_legs.items():
        path = repo / rel
        if not path.is_file() or path.read_bytes() != data:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
    if _leg_files(repo, source) != before_legs:
        raise ValueError(f"{source} DDF legs do not match the pre-run legs")


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
    """Restore a failed or held source's pre-run state; mark it held.

    Covers a review hold (per-source-promotion-001) and, since
    source-resiliency-001, any other failure of that one source. The whole
    fixture goes back to its bytes from just before this source ran, and a
    DDF-leg source (espn, cbsros) gets its legs back too.

    Fail-closed: when the pre-run state is unknown, or the restore cannot be
    verified (canonical sha of the whole fixture, and of the section), the
    result stays 'failed' and the chain fails. Promotion records written for
    sections that were rolled back are renamed so no monitor reads them as
    promoted.
    """
    failed_stage = result.get("stage")
    reason = ("review hold" if result.get("held")
              else f"failed at stage '{failed_stage}'")
    if before is None:
        result["detail"] += " | NOT isolated: pre-run fixture state unknown"
        return result
    fixture_path = Path(repo) / FIXTURE_REL
    try:
        try:
            current = _read_fixture(repo)
        except (OSError, ValueError):
            current = None  # a crashed builder may leave it unreadable
        if current is None or _canonical_sha(current) != before["fixture_sha"]:
            fixture_path.write_bytes(before["fixture_bytes"])
        restored = _read_fixture(repo)
        if _canonical_sha(restored) != before["fixture_sha"]:
            raise ValueError("restored fixture does not match the pre-run fixture")
        after = restored["sources"]
        if _canonical_sha(after.get(source)) != before["sha"] or (source in after) != before["present"]:
            raise ValueError("restored section does not match the pre-run section")
        _restore_legs(repo, source, before.get("legs") or {})
    except (OSError, ValueError, KeyError, TypeError) as exc:
        result["stage"] = "restore"
        result["detail"] += f" | NOT isolated: restore failed: {exc}"
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
        "held_reason": reason,
        "failed_stage": failed_stage,
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
    print(f"  ⚠ HELD (isolated, {reason}): kept last promoted {source} section "
          f"(week {kept_week}, {weeks_behind} week(s) behind -> {severity}); "
          f"rolled back {result['rolled_back']} section(s) promoted this run")
    return result


def _verify_cbsros_section(repo, snapshot_vintage, source="cbsros"):
    """Review GATE for the cbsros (and razzball) chain (not a bypass).

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
    section = (fixture.get("sources") or {}).get(source)
    if not isinstance(section, dict):
        raise ChainHalt("review", f"sources.{source} missing from fixture after section build")
    combos = section.get("combos") or {}
    missing = [k for k in CBSROS_COMBO_KEYS if k not in combos]
    if missing:
        raise ChainHalt("review", f"{source} section missing combos: {missing}")
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
        raise ChainHalt("review", f"{source} section malformed: {bad[:5]}")
    vintage = section.get("vintage")
    if snapshot_vintage and vintage != snapshot_vintage:
        raise ChainHalt(
            "review",
            f"{source} section vintage {vintage!r} != snapshot vintage {snapshot_vintage!r}",
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
        # GAP-BAKE-ON-CHANGE: never build a section players.json was not
        # baked from (razzball checks this in run_razzball_source).
        reason = bake_identity_mismatch(repo, source, snapshot)
        if reason:
            raise ChainHalt("snapshot", reason)

        # 2. DDF leg: rebuild all 12 legs from the snapshot (3 scorings x 4 team counts)
        result["stage"] = "leg"
        leg_script, section_script = LEG_SECTION_SCRIPTS[source]
        for scoring, teams in ((s, t) for s in CBSROS_LEG_SCORINGS for t in CBSROS_LEG_TEAMS):
            ok, out = run_fn([
                "python3", leg_script,
                "--snapshot", str(snapshot),
                "--scoring", scoring,
                "--teams", str(teams),
            ])
            if not ok:
                raise ChainHalt("leg", f"DDF leg build failed (scoring={scoring} teams={teams}): {out[-500:]}")
        print("  ✓ 12 DDF legs rebuilt")

        # 3. Section: build the fixture section from the fresh legs
        result["stage"] = "section"
        ok, out = run_fn(["python3", section_script])
        if not ok:
            raise ChainHalt("section", f"{source} section build failed: {out[-500:]}")
        print(f"  ✓ {source} fixture section rebuilt")

        # 4. Review gate: verify the rebuilt section (halts fail-closed)
        result["stage"] = "review"
        n_values = _verify_cbsros_section(repo, snapshot_vintage, source)
        reason = section_identity_mismatch(repo, source)
        if reason:
            raise ChainHalt("review", reason)
        if source == "razzball":
            reason = razzball_values_mismatch(repo, snapshot)
            if reason:
                raise ChainHalt("review", reason)

        result["status"] = "ok"
        result["stage"] = "complete"
        result["promoted"] = 1
        result["detail"] = (
            f"snapshot {snapshot_vintage} -> 12 DDF legs -> section; "
            f"review passed ({n_values} values)"
        )
        print(f"  ✓ {source} chain complete: {result['detail']}")

    except ChainHalt as h:
        result["stage"] = h.stage
        result["detail"] = h.detail
        print(f"  ✗ HALT at stage '{h.stage}': {h.detail}")
    except Exception as e:  # fail closed on unexpected errors too
        result["stage"] = "error"
        result["detail"] = f"unexpected error: {e}"
        print(f"  ✗ ERROR: {e}")

    return result


PLAYERS_REL = Path("data") / "fixtures" / "current" / "players.json"
ESPN_CSV_REL = Path("data") / "inputs" / "espn_projections.csv"


def bake_identity_mismatch(repo, source, input_path):
    """Why `source`'s section must not be built from `input_path`, or None.

    GAP-BAKE-ON-CHANGE (2026-10-08): the browser prices ESPN, CBS ROS and
    Razzball from players.json; the main table and chart read the chain's
    sections. They must be built from the same snapshot, and a date cannot
    tell two same-day saves apart (CBS ROS 08:48 vs 13:54 on 2026-10-08), so
    the check is the content id (pipelines/projection_identity.py). A
    mismatch holds the source (isolated: its last good section and legs are
    kept, every other source publishes) until a bake from this snapshot.
    """
    try:
        current = projection_identity.file_id(input_path)
    except (OSError, ValueError) as exc:
        return f"unreadable {source} input {input_path}: {exc}"
    reason = projection_identity.mismatch(source, current, Path(repo) / PLAYERS_REL)
    return f"awaiting players bake: {reason}" if reason else None


def section_identity_mismatch(repo, source):
    """Why the built `source` section disagrees with players.json, or None."""
    try:
        section = (_read_fixture(repo).get("sources") or {}).get(source) or {}
    except (OSError, ValueError) as exc:
        return f"cannot read fixture: {exc}"
    reason = projection_identity.mismatch(source, section.get("snapshot_id"),
                                          Path(repo) / PLAYERS_REL)
    return f"section vs players.json: {reason}" if reason else None


RZ_SCORING_COLUMNS = {"standard": "rz_std_ppg", "half_ppr": "rz_half_ppr_ppg", "ppr": "rz_ppr_ppg"}
RZ_COMBO_SCORING = {"standard": "standard", "half": "half_ppr", "full": "ppr"}


def razzball_values_mismatch(repo, snapshot, limit=3):
    """Why the Razzball values about to be served are not the snapshot's, or None.

    The ids prove only that the section and players.json *say* they come from
    `snapshot` (GAP-RAZZBALL-CHART-BEHIND-STORED). This checks the numbers:
    every per-game value in the section (natives, joined by the fixture's
    player_keys) and in players.json (rz_ppg, by player_key) must equal that
    player's snapshot row, and no served player may be missing from the
    snapshot. A stale bake or section stamped with the new id holds Razzball
    (isolated: the last good section is kept) instead of publishing old
    numbers under the new snapshot's name.
    """
    try:
        snap = json.loads(Path(snapshot).read_text(encoding="utf-8"))
        fixture = _read_fixture(repo)
        players = json.loads((Path(repo) / PLAYERS_REL).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return f"razzball values not checkable: {exc}"
    by_key = {}
    for row in snap.get("rows") or []:
        key = row.get("player_key")
        if isinstance(key, int) and not isinstance(key, bool):
            by_key[key] = {s: row.get(col) for s, col in RZ_SCORING_COLUMNS.items()}
    slug_key = fixture.get("player_keys") or {}
    section = (fixture.get("sources") or {}).get("razzball") or {}
    problems = []

    def check(where, key, scoring, served):
        if key not in by_key:
            problems.append(f"{where}: not in snapshot")
            return
        stored = by_key[key].get(scoring)
        if not isinstance(stored, (int, float)) or abs(float(served) - float(stored)) > 1e-9:
            problems.append(f"{where} {scoring} {served} vs snapshot {stored}")

    for combo, block in sorted((section.get("combos") or {}).items()):
        scoring = RZ_COMBO_SCORING.get(combo.rsplit("_", 1)[0])
        for slug, ppg in sorted((block.get("native") or {}).items()):
            key = slug_key.get(slug)
            if scoring and key is not None:
                check(f"section {combo} {slug}", key, scoring, ppg)
    for player in players.get("players") or []:
        for scoring, ppg in sorted((player.get("rz_ppg") or {}).items()):
            if scoring in RZ_SCORING_COLUMNS and ppg is not None:
                check(f"players.json {player.get('name') or player.get('player_key')}",
                      player.get("player_key"), scoring, ppg)
    if not problems:
        return None
    return (f"razzball values are not snapshot {projection_identity.file_id(snapshot)[:19]}'s "
            f"({len(problems)} differ, e.g. {'; '.join(problems[:limit])}); the section waits "
            "for a bake and legs built from that snapshot")


def razzball_bake_mismatch(repo, snapshot):
    """Why the Razzball section must not move to this snapshot, or None.

    The browser prices Razzball from players.json rz_ppg (baked by
    bake_players.py) and the main table reads the chain's Razzball section.
    Both must be one snapshot (GAP-RAZZBALL-SUFFIX-POOL: the section said
    2026-10-01 while the browser priced a 2026-09-22 file). Since
    GAP-BAKE-ON-CHANGE the test is the snapshot's content id, not its date.
    """
    return bake_identity_mismatch(repo, "razzball", snapshot)


def run_razzball_source(source="razzball", nfl_week=None, repo=REPO, run_fn=run):
    """Rebuild the razzball chain: snapshot -> 12 DDF legs -> section -> review.

    Same pipeline and gate as cbsros (run_cbsros_source); the snapshot is the
    one import_supabase_references.py wrote from public.razzball_projections.
    It first requires players.json to be baked from the same vintage
    (razzball_bake_mismatch). Unlike cbsros, a razzball failure is isolated
    by execute_chain: the site keeps the last promoted razzball section and
    the other sources publish.
    """
    snapshot = find_latest_snapshot(Path(repo), source)
    reason = razzball_bake_mismatch(repo, snapshot) if snapshot else None
    if reason:
        print(f"  ✗ HALT at stage 'snapshot': {reason}")
        return {"source": source, "status": "failed", "stage": "snapshot",
                "detail": reason, "promoted": 0, "sections": 1}
    return run_cbsros_source(source, nfl_week, repo, run_fn)


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

        # GAP-BAKE-ON-CHANGE: the legs read the ESPN CSV; players.json must
        # have been baked from that exact file.
        reason = bake_identity_mismatch(repo, "espn", repo / ESPN_CSV_REL)
        if reason:
            raise ChainHalt("snapshot", reason)

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
        reason = section_identity_mismatch(repo, "espn")
        if reason:
            raise ChainHalt("review", reason)

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


def run_reindex_fixture(repo, run_fn):
    """Stage 6b (JEG-482): re-index every published chart in the promoted
    fixture from its own natives, then hold the result to the rank guard.
    Raises ChainHalt on failure.

    Each section was indexed against the ESPN leg as it stood when that
    section ran; the ESPN leg can be promoted later in the same run. This
    pass indexes every saved 12-team value against the leg the site will
    show (one factor per chart x combo, reindex_comparison_section.
    order_preserving_rescale). The rank guard then requires every published
    chart's Indexed order to equal its native order (fail closed: the order
    is the data the page promises). Replaced run_retranslate, which wrote
    value-above-waivers translations into the Indexed values.
    """
    fixture = str(repo / "data/fixtures/current/comparison-sources-data.json")
    ok, out = run_fn(["python3", "pipelines/reindex_published_fixture.py", "--fixture", fixture])
    if not ok:
        raise ChainHalt("reindex_fixture", f"fixture re-index failed: {out[-500:]}")
    print("  ✓ Published charts re-indexed against the promoted fixture")
    ok, out = run_fn(["python3", "pipelines/check_rank_guard.py", "--fixture", fixture])
    if not ok:
        raise ChainHalt("rank_guard", f"published chart order broken: {out[-500:]}")
    print("  ✓ Rank guard: every published chart keeps its own order")


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
    unified translation now. Reads the freshly promoted fixture. The grains
    (publisher_translated_values) are a record only since JEG-482: no saved
    chart value is read from them.

    Fail-safe: refresh failure is logged, never halts the chain.
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


def describe_result(result):
    """Human-readable one-line status for the dashboard (string, not a code)."""
    if result["status"] == "ok":
        return f"promoted {result['promoted']}/{result['sections']}"
    if result["status"] == "held":
        kept = result.get("kept_section") or {}
        label = kept.get("week_designated") or kept.get("content_vintage") or "no prior section"
        return (f"HELD at stage '{result.get('failed_stage') or 'review'}' "
                f"({result.get('hold_severity')}, {result.get('held_reason') or 'review hold'}): "
                f"kept last promoted section ({label}); candidate not promoted: "
                f"{result.get('detail', '')}")
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
            "reason": results[s].get("held_reason"),
            "stage": results[s].get("failed_stage"),
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
    # GAP-UNIVERSE-CHART-ONLY: every players.json player (now including
    # those only a published chart or projection prices) gets a fixture slug
    # before any section is keyed through the fixture's player_keys.
    try:
        import sync_universe_keys
        added = sync_universe_keys.sync_files(
            repo / "data" / "fixtures" / "current" / "players.json",
            repo / "data" / "fixtures" / "current" / "comparison-sources-data.json")
        print(f"universe keys: {len(added)} players added to the fixture's "
              f"player_keys" + (f": {added}" if added else ""))
    except Exception as e:  # noqa: BLE001 -- sections keep the old universe
        print(f"universe keys: sync failed ({e}); sections keep the fixture's keys")
    try:
        for source in SOURCES:
            print(f"\n[{source}] Starting chain...")
            isolatable = source in FAILURE_ISOLATED_SOURCES or source in HOLD_ISOLATED_SOURCES
            before = snapshot_source_state(repo, source) if isolatable else None
            # cbsros has its own DDF-leg pipeline (not the quantile-reindex
            # path); its chain mirrors that pipeline.
            if source == "cbsros":
                results[source] = run_cbsros_source(source, nfl_week, repo, run_fn)
            # ESPN is DDF-modeled (per-game natives via the two-tier leg),
            # not an as-published chart; it must not go through the generic
            # published-chart path (which would take raw ROS totals).
            elif source == "espn":
                results[source] = run_espn_source(source, nfl_week, repo, run_fn)
            # razzball: the cbsros DDF-leg pipeline (isolated below on failure).
            elif source == "razzball":
                results[source] = run_razzball_source(source, nfl_week, repo, run_fn)
            else:
                results[source] = run_source(source, nfl_week, repo, run_fn)
            # source-resiliency-001: any failure in an isolated source (and a
            # review hold in a review-gated one) keeps that source's last
            # promoted section; the other sources still publish.
            res = results[source]
            # A runner that already isolated its own failure returns "held";
            # isolating twice would only overwrite its rolled_back count.
            if res["status"] not in ("ok", "held") and (
                    source in FAILURE_ISOLATED_SOURCES
                    or (source in HOLD_ISOLATED_SOURCES and res.get("held"))):
                isolate_hold(repo, source, before, res, nfl_week)

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
                run_reindex_fixture(repo, run_fn)
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
        # Refreshes the Supabase grains (a record; JEG-482) when stale.
        # Fail-safe: never halts the chain.
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

        # Stage 10 (the JEG-200 source value lineage rebuild) was retired
        # 2026-10-08 (GAP-LIVE-SCRAPE-STALE). It could never succeed here: the
        # builder needs the gitignored data/raw Week 4 source snapshots and a
        # live-page scrape of the Week 4 article URLs, and the chain never
        # committed its output. It logged a failure every run and changed
        # nothing. The lineage audit itself was then retired the same day
        # (chore/retire-extras); git history before aefb8f7 keeps it.

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
