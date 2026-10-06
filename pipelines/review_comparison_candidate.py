#!/usr/bin/env python3
"""Promotion review for a reindexed candidate comparison section.

Pipeline stage: reindexed candidate -> reviewed candidate comparison artifact.

Compares the reindexed candidate (schema
trade-value-comparison-section-reindexed-v1) against the fixture's existing
section for the same source and renders a verdict:

  ready  -- every check passes; the candidate MAY be promoted by a human
  hold   -- something needs a human first; the report says what

The script NEVER promotes anything itself and NEVER writes under data/.
Promotion (writing into the live fixture) is a separate, human-approved step.

Checks:
  combos_match        candidate combos == fixture combos for the source
  native_drift        candidate native vs fixture native (source moved?)
  coverage            candidate priced counts vs fixture (lost players?)
  zero_preservation   zero-native positions identical
  pie_factors_sane    index_total factors within sane bounds, pre_total > 0
  review_rows_triaged every review row triaged via --triage
  anchor_disclosure   always informational: candidate anchors to the fixture
                      ESPN leg; the fixture's existing sections were baked
                      against the retired Monday rail. Divergence is measured
                      and reported, never asserted equal.
  native_change_classification: classify as native_change, reindex_only, or
                      native_no_op (candidate natives identical to fixture natives)

Provenance tracking (JEG-114):
  - fixture_native_before_sha256: hash of fixture natives at review creation time
  - candidate_native_sha256: hash of candidate's native values
  - review_created_at: ISO timestamp when review was generated
  - These enable promotion to verify the review was created BEFORE any fixture edits

Writes (under output/ only):
  output/comparison-review/<source>-<asof>-review.json
  (schema: trade-value-comparison-review-v1)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path

# JEG-75: live-name matching uses the canonical normalizer -- never an ad-hoc
# one. (An earlier _normalize_name helper was flagged by
# tests.test_player_identity_guard; the canonical module is the only
# legitimate normalizer.)
sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
from canonical_players import norm_player_name

REPO = Path(__file__).resolve().parent.parent
SCHEMA = "trade-value-comparison-review-v1"
POSITIONS = ("QB", "RB", "WR", "TE")
DRIFT_TOL = 0.05       # per-value tolerance for "same" native
DRIFT_WARN_FRAC = 0.0  # any drift warns
DRIFT_FAIL_FRAC = 0.05  # >5% of values drifted fails
# Live-verification (Jeremy 2026-10-04): when native_drift fails for a source
# with a live API, verify the top-25 candidate natives against the live site.
# If they match, the drift is genuine (source moved, not a pipeline bug) and
# the check passes with a "live-verified" note instead of failing.
LIVE_VERIFY_N = 25
LIVE_VERIFY_TOL = 0.05  # per-value tolerance for live match
LIVE_VERIFY_MIN_MATCH_FRAC = 0.80  # 20+/25 must match to verify
# Live API endpoints by source key (only sources with a live API get the
# live-verification bypass; others keep the hard fail on drift).
LIVE_API_URLS = {
    "fantasycalc": ("https://api.fantasycalc.com/values/current"
                    "?isDynasty=false&numQbs=1&numTeams=12&ppr=0.5"),
}
# JEG-366 follow-up (2026-10-05): the live check used the fixed 12-team /
# half-PPR URL above for EVERY combo, so a 10-team full-PPR candidate was
# compared against 12-team half-PPR live values and could never verify
# (19/25 on the 2026-10-05 chain). The URL now follows the combo. numQbs stays
# 1: the pipeline only pulls 1-QB values and derives the qb2 combos from them
# (source_trade_values.qb_slots is 1 for every fantasycalc row).
FC_PPR = {"standard": 0, "half": 0.5, "full": 1.0}


def live_api_url(source, combo_name=None):
    """Live API URL for ``source`` matching ``combo_name`` (e.g. full_10_qb1)."""
    if source != "fantasycalc" or not combo_name:
        return LIVE_API_URLS.get(source)
    m = re.match(r"^(standard|half|full)_(\d+)", combo_name)
    if not m:
        return LIVE_API_URLS.get(source)
    return ("https://api.fantasycalc.com/values/current?isDynasty=false"
            f"&numQbs=1&numTeams={int(m.group(2))}&ppr={FC_PPR[m.group(1)]}")
# Factor bounds: as-published sources on the 10,000-scale (FantasyCalc) have
# factors ~0.007 to reach the 0-70 indexed scale. Per-position DDF sources
# have factors ~0.2-5.0. The lower bound accommodates both.
FACTOR_LO, FACTOR_HI = 0.001, 5.0


def _load_json(path):
    with open(path) as fh:
        return json.load(fh)


def _check(name, status, detail=""):
    return {"name": name, "status": status, "detail": detail}


def _sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _sha256_canonical(obj):
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def verify_top25_live(source, candidate_natives, combo_name=None):
    """Verify the top-25 candidate natives against the source's live site.

    Returns (verified: bool, detail: str). Only sources in LIVE_API_URLS are
    verifiable; others return (False, "no live API for source").
    A network failure returns (False, ...) -- fail closed, never pass on
    an unverifiable live check.
    """
    url = live_api_url(source, combo_name)
    if not url:
        return False, f"no live API configured for source {source}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.load(resp)
    except Exception as e:
        return False, f"live fetch failed: {e}"
    live = {}
    for p in data:
        pl = p.get("player", {})
        name = pl.get("name")
        val = p.get("value")
        if name and val is not None:
            live[name] = float(val)
    if not live:
        return False, "live API returned no players"
    # Top-25 by candidate native value (these matter most for the chart).
    # Candidate natives are keyed by slug; match to live names via the
    # canonical norm_player_name (JEG-75: never an ad-hoc normalizer).
    live_norm = {norm_player_name(n): v for n, v in live.items()}
    top = sorted(candidate_natives.items(), key=lambda kv: float(kv[1]),
                 reverse=True)[:LIVE_VERIFY_N]
    matched = 0
    checked = 0
    mismatches = []
    for slug, cand_val in top:
        live_val = live_norm.get(norm_player_name(slug))
        if live_val is None:
            continue
        checked += 1
        cand_f = float(cand_val)
        if cand_f == 0:
            continue
        if abs(live_val - cand_f) / cand_f <= LIVE_VERIFY_TOL:
            matched += 1
        else:
            mismatches.append(slug)
    if checked == 0:
        return False, "no top-25 slugs matched live API names"
    frac = matched / checked
    if frac >= LIVE_VERIFY_MIN_MATCH_FRAC:
        return True, (f"live-verified {matched}/{checked} top-25 "
                      f"within {LIVE_VERIFY_TOL:.0%}")
    return False, (f"live mismatch {matched}/{checked} top-25 match "
                   f"(need {LIVE_VERIFY_MIN_MATCH_FRAC:.0%}); "
                   f"e.g. {', '.join(mismatches[:3])}")


def fetch_live_values(source, combo_name=None):
    """Live API values for ``source``/``combo_name`` as {norm_name: value}.

    Returns (values, error). Fail closed: any fetch/parse problem returns
    (None, reason), never an empty "verified" set.
    """
    url = live_api_url(source, combo_name)
    if not url:
        return None, f"no live API configured for source {source}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.load(resp)
    except Exception as e:  # noqa: BLE001 - fail closed
        return None, f"live fetch failed: {e}"
    live = {}
    for p in data:
        name = (p.get("player") or {}).get("name")
        val = p.get("value")
        if name and val is not None:
            live[norm_player_name(name)] = float(val)
    if not live:
        return None, "live API returned no players"
    return live, None


def verify_coverage_drop_live(source, combo_name, dropped_slugs):
    """Jeremy 2026-10-05 (extends the 2026-10-04 drift rule to coverage):
    a priced-count drop is a genuine source change -- not a pipeline loss --
    only when EVERY player the fixture priced and the candidate lost is also
    absent (or unpriced) in the live source for the same combo. One dropped
    player still listed live means the pipeline lost them: stay on hold.
    """
    if not dropped_slugs:
        return False, "no dropped players identified for the count drop"
    live, err = fetch_live_values(source, combo_name)
    if live is None:
        return False, err
    still_live = sorted(s for s in dropped_slugs
                        if live.get(norm_player_name(s), 0.0) > 0)
    if still_live:
        return False, (f"{len(still_live)} dropped player(s) still priced live "
                       f"(e.g. {', '.join(still_live[:3])}) -- pipeline loss")
    return True, (f"live-verified: all {len(dropped_slugs)} dropped player(s) "
                  f"absent from the live source ({', '.join(sorted(dropped_slugs)[:4])})")


def review_candidate(reindexed_path, triage_path=None, fixture_path=None,
                     players_path=None, no_live_verify=False):
    cand = _load_json(reindexed_path)
    if cand.get("schema") != "trade-value-comparison-section-reindexed-v1":
        raise SystemExit(f"review: unsupported schema {cand.get('schema')}")
    if cand.get("reindex_status") != "complete":
        raise SystemExit("review: reindex_status is not 'complete' -- refusing to review unfinished math")
    fixture_path = fixture_path or REPO / "data/fixtures/current/comparison-sources-data.json"
    fixture = _load_json(fixture_path)
    players_path = players_path or REPO / "data/fixtures/current/players.json"
    pos_by_key = {p["player_key"]: p["pos"]
                  for p in _load_json(players_path)["players"]}
    player_keys = fixture.get("player_keys", {})
    source = cand["source_key"]
    fx_section = fixture["sources"].get(source)

    triaged = {}
    if triage_path:
        triaged = _load_json(triage_path)

    checks = []
    combos_detail = {}

    # --- review rows triage ---
    untriaged = [r for r in cand.get("review_rows", [])
                 if r.get("slug") not in triaged]
    if untriaged:
        checks.append(_check("review_rows_triaged", "fail",
                             f"{len(untriaged)} untriaged review rows"))
    else:
        checks.append(_check("review_rows_triaged", "pass",
                             f"{len(cand.get('review_rows', []))} rows, all triaged"))

    # --- identity closure: every candidate slug must already exist in the
    # fixture's player_keys (promotion never introduces a new identity) ---
    unknown = sorted({s for combo in cand["combos"].values()
                      for s in combo["native"] if s not in player_keys})
    if unknown:
        checks.append(_check("identity_closure", "fail",
                             f"{len(unknown)} candidate slugs not in fixture "
                             f"player_keys (e.g. {unknown[:3]})"))
    else:
        checks.append(_check("identity_closure", "pass",
                             "all candidate slugs resolve in fixture player_keys"))

    # --- pie factor sanity (no fixture needed) ---
    # As-published sources use global (not per-position) scaling; check the
    # "global" key for those, per-position keys for DDF-methodology sources.
    sane, bad = True, []
    for combo_name, combo in cand["combos"].items():
        it_map = combo.get("index_total", {})
        positions_to_check = ["global"] if "global" in it_map else POSITIONS
        for pos in positions_to_check:
            it = it_map.get(pos, {})
            f = it.get("factor")
            if not (isinstance(f, (int, float)) and FACTOR_LO <= f <= FACTOR_HI):
                sane, bad = False, bad + [f"{combo_name}/{pos} factor={f}"]
            if not it.get("pre_total", 0) > 0:
                sane, bad = False, bad + [f"{combo_name}/{pos} pre_total<=0"]
    checks.append(_check("pie_factors_sane", "pass" if sane else "fail",
                         "; ".join(bad) if bad else "all factors in "
                         f"[{FACTOR_LO}, {FACTOR_HI}], pre_totals positive"))

    if fx_section is None:
        checks.append(_check("baseline", "info",
                             f"source {source!r} not in fixture -- new source, "
                             "no baseline comparison possible"))
        fx_combos = {}
        fixture_native_sha256 = None
    else:
        fx_combos = fx_section.get("combos", {})
        fixture_native_sha256 = _sha256_canonical(
            {c: fx_combos[c]["native"] for c in fx_combos})

    # --- combos match ---
    # Note: Candidates are built per-section (subset of combos). A candidate
    # is NOT expected to contain all fixture combos — promote merges the
    # candidate's combos into the fixture. We only verify that the candidate's
    # combos exist in the fixture (no unknown combos).
    if fx_section is not None:
        extra = [c for c in cand["combos"] if c not in fx_combos]
        if extra:
            checks.append(_check("combos_match", "fail", f"unknown combos not in fixture: {extra}"))
        else:
            checks.append(_check("combos_match", "pass",
                                 f"{len(cand['combos'])} candidate combos exist in fixture"))

    # --- per-combo baseline comparisons ---
    for combo_name, combo in cand["combos"].items():
        fx = fx_combos.get(combo_name)
        detail = {}
        if fx is None:
            detail["baseline"] = "no fixture combo -- skipped"
            combos_detail[combo_name] = detail
            continue
        fx_native = fx.get("native", {})
        fx_reidx = fx.get("reindexed", fx.get("values", {}))
        native, reidx = combo["native"], combo["reindexed"]

        # native drift
        shared = [s for s in native if s in fx_native]
        drifted = [s for s in shared
                   if abs(float(native[s]) - float(fx_native[s])) > DRIFT_TOL]
        frac = len(drifted) / len(shared) if shared else 0.0
        detail["native_shared"] = len(shared)
        detail["native_drifted"] = len(drifted)
        detail["native_drift_frac"] = round(frac, 4)
        if frac > DRIFT_FAIL_FRAC:
            # Jeremy 2026-10-04: before failing on drift, verify the top-25
            # candidate natives against the live site. If the live site
            # matches, the drift is genuine (source moved) not a pipeline
            # bug, and the check passes as live-verified.
            verified, verify_detail = (False, "live verification skipped")
            if not no_live_verify and source in LIVE_API_URLS:
                verified, verify_detail = verify_top25_live(source, native, combo_name)
            if verified:
                checks.append(_check(f"native_drift:{combo_name}", "pass",
                                     f"{len(drifted)}/{len(shared)} values moved > "
                                     f"{DRIFT_TOL} -- {verify_detail}"))
            else:
                checks.append(_check(f"native_drift:{combo_name}", "fail",
                                     f"{len(drifted)}/{len(shared)} values moved > "
                                     f"{DRIFT_TOL} ({verify_detail})"))
        elif frac > DRIFT_WARN_FRAC:
            checks.append(_check(f"native_drift:{combo_name}", "warn",
                                 f"{len(drifted)}/{len(shared)} values moved"))
        else:
            checks.append(_check(f"native_drift:{combo_name}", "pass",
                                 "native values match fixture"))

        # coverage per position (fixture n_priced when the fixture records it)
        for pos in POSITIONS:
            detail.setdefault("coverage", {})[pos] = {
                "candidate": combo["n"].get(pos, 0),
                "fixture": fx.get("index_total", {}).get(pos, {}).get("n_priced"),
            }
        # zero preservation
        c_zeros = {s for s, v in native.items() if float(v) == 0.0}
        f_zeros = {s for s, v in fx_native.items() if float(v) == 0.0}
        detail["zeros_candidate"] = len(c_zeros)
        detail["zeros_fixture"] = len(f_zeros)
        if c_zeros != f_zeros:
            checks.append(_check(f"zero_preservation:{combo_name}", "warn",
                                 f"zero sets differ: "
                                 f"only-candidate={len(c_zeros - f_zeros)}, "
                                 f"only-fixture={len(f_zeros - c_zeros)}"))
        else:
            checks.append(_check(f"zero_preservation:{combo_name}", "pass",
                                 f"{len(c_zeros)} zeros match"))

        # anchor divergence (informational -- anchors differ by design)
        key_by_slug = combo.get("player_keys", {})
        pos_of = {s: pos_by_key.get(key_by_slug.get(s)) for s in reidx}
        div = {}
        for pos in POSITIONS:
            pairs = [(reidx[s], fx_reidx[s]) for s in reidx
                     if s in fx_reidx and pos_of.get(s) == pos]
            if pairs:
                diffs = [abs(a - b) for a, b in pairs]
                div[pos] = {"n": len(pairs),
                            "mean_abs": round(sum(diffs) / len(diffs), 2),
                            "max_abs": round(max(diffs), 2)}
        detail["anchor_divergence"] = div
        combos_detail[combo_name] = detail

    qb_mappings = sorted({c.get("anchor_mapping") for c in cand["combos"].values()}
                         - {"exact", None})
    disclosure = ("candidate anchors to the fixture ESPN leg; the fixture's existing "
                  "sections were baked against the retired Monday rail. Reindexed "
                  "divergence above is measured, not asserted -- promotion must note "
                  "the anchor change.")
    if qb_mappings:
        disclosure += (" QB-dimension anchor mappings (explicit, not guessed): "
                       + "; ".join(qb_mappings) + ".")
    checks.append(_check("anchor_disclosure", "info", disclosure))

    # coverage check (needs fixture positions; approximate from fixture combo keys)
    if fx_section is not None:
        for combo_name, combo in cand["combos"].items():
            fx = fx_combos.get(combo_name)
            if not fx:
                continue
            fx_reidx = fx.get("reindexed", fx.get("values", {}))
            for pos in POSITIONS:
                # As-published sources use global scaling; per-position counts
                # may not be available. Skip if candidate has no per-pos data.
                if pos not in combo["n"]:
                    continue
                c_n = combo["n"].get(pos, 0)
                f_n = fx.get("index_total", {}).get(pos, {}).get("n_priced")
                if f_n is None:
                    continue  # fixture records no priced count; cannot compare
                if c_n < f_n:
                    verified, verify_detail = (False, "live verification skipped")
                    if not no_live_verify and source in LIVE_API_URLS:
                        fx_priced = {s for s, v in fx_reidx.items()
                                     if v and pos_by_key.get(player_keys.get(s)) == pos}
                        c_keys = combo.get("player_keys", {})
                        c_priced = {s for s, v in combo["native"].items()
                                    if v and pos_by_key.get(c_keys.get(s, player_keys.get(s))) == pos}
                        dropped = sorted(fx_priced - c_priced)
                        verified, verify_detail = verify_coverage_drop_live(
                            source, combo_name, dropped)
                    checks.append(_check(
                        f"coverage:{combo_name}/{pos}", "pass" if verified else "fail",
                        f"candidate priced {c_n} < fixture {f_n} -- {verify_detail}"))
        if not any(c["name"].startswith("coverage:") and c["status"] == "fail"
                   for c in checks):
            checks.append(_check("coverage", "pass", "no priced-count regressions"))

    # --- JEG-114: Native change classification and provenance tracking ---
    # Compute candidate native hash for provenance tracking
    candidate_native_hash = _sha256_canonical(
        {c: cand["combos"][c]["native"] for c in cand["combos"]})

    # Classify the change type based on native comparison
    if fx_section is None:
        native_change_classification = "native_new_source"
        native_change_detail = "new source, no fixture baseline for comparison"
    elif candidate_native_hash == fixture_native_sha256:
        # Candidate natives exactly match fixture natives - this is a reindex-only change
        # (or potentially a no-op if reindexed values also match)
        native_change_classification = "reindex_only"
        native_change_detail = "candidate natives identical to fixture natives - reindex only, no native change"
    else:
        # Candidate natives differ from fixture - this is a native-changing update
        native_change_classification = "native_change"
        native_change_detail = "candidate natives differ from fixture natives - actual native update"

    checks.append(_check("native_change_classification", "pass", native_change_detail))

    # Record provenance information for JEG-114
    # This enables promotion to verify review was created BEFORE any fixture edits
    review_created_at = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")

    verdict = "hold" if any(c["status"] == "fail" for c in checks) else "ready"

    report = {
        "schema": SCHEMA,
        "source_key": source,
        "asof": cand.get("asof"),
        "verdict": verdict,
        "checks": checks,
        "combos": combos_detail,
        "review_rows": cand.get("review_rows", []),
        "triaged": triaged,
        "reindexed_source_file": str(reindexed_path),
        "reindexed_sha256": _sha256_file(reindexed_path),
        # JEG-114: Provenance tracking for native change detection
        "fixture_native_before_sha256": fixture_native_sha256,  # Fixture natives when review was created
        "fixture_native_sha256": fixture_native_sha256,  # Alias: promote checks this key
        "candidate_native_sha256": candidate_native_hash,  # Candidate's native values
        "review_created_at": review_created_at,  # When review was generated
        "native_change_classification": native_change_classification,  # native_change | reindex_only | native_new_source
        "note": ("'ready' means the candidate MAY be promoted by a human. "
                 "This script never writes under data/."),
    }
    return report


def main(argv=None):
    ap = argparse.ArgumentParser(description="Review a reindexed candidate section.")
    ap.add_argument("reindexed", help="reindexed section JSON")
    ap.add_argument("--triage", default=None,
                    help="JSON mapping slug -> triage note for review rows")
    ap.add_argument("--out", default=None,
                    help="output path (default output/comparison-review/<source>-<date>-review.json)")
    ap.add_argument("--no-live-verify", action="store_true",
                    help="skip the top-25 live verification on native_drift "
                         "fail (for CI/offline runs; drift fails hard)")
    args = ap.parse_args(argv)

    report = review_candidate(args.reindexed, args.triage,
                              no_live_verify=args.no_live_verify)
    out = Path(args.out) if args.out else (
        REPO / "output" / "comparison-review"
        / f"{report['source_key']}-{date.today().isoformat()}-review.json")
    if out.resolve().is_relative_to((REPO / "data").resolve()):
        raise SystemExit("refusing to write under data/")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=1) + "\n")
    print(f"review -> {out}")
    print(f"verdict: {report['verdict']}")
    for c in report["checks"]:
        if c["status"] != "pass":
            print(f"  {c['status'].upper()}: {c['name']} -- {c['detail']}")
    return 0 if report["verdict"] == "ready" else 2


if __name__ == "__main__":
    sys.exit(main())
