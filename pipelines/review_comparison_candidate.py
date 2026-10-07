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


def fetch_live_rows(source, combo_name=None):
    """Live API rows for ``source``/``combo_name`` as {norm_name: (value, pos)}.

    ``pos`` is the publisher's position label upper-cased, or None when the
    row carries none. Returns (rows, error). Fail closed: any fetch/parse
    problem returns (None, reason), never an empty "verified" set.
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
        player = p.get("player") or {}
        name = player.get("name")
        val = p.get("value")
        if name and val is not None:
            pos = player.get("position")
            live[norm_player_name(name)] = (float(val),
                                            str(pos).upper() if pos else None)
    if not live:
        return None, "live API returned no players"
    return live, None


def fetch_live_values(source, combo_name=None):
    """Live API values for ``source``/``combo_name`` as {norm_name: value}."""
    rows, err = fetch_live_rows(source, combo_name)
    if rows is None:
        return None, err
    return {k: v for k, (v, _pos) in rows.items()}, None


def verify_coverage_drop_live(source, combo_name, dropped_slugs, pos=None,
                              depth=None):
    """Jeremy 2026-10-05 (extends the 2026-10-04 drift rule to coverage):
    a priced-count drop is a genuine source change -- not a pipeline loss --
    only when EVERY player the fixture priced and the candidate lost is also
    absent (or unpriced) in the live source for the same combo. One dropped
    player still listed live means the pipeline lost them: stay on hold.

    JEG-436 follow-up (2026-10-07): the live list is read at REVIEW time, a
    day or more after the bake was pulled, and FantasyCalc's list churns its
    tail daily (fcwk5 pulled 2026-10-06 14:20Z without Pat Freiermuth; the
    2026-10-07 live list had him back as its 27th and last TE at 20, and had
    dropped Oronde Gadsden, who IS in the bake). A dropped player the live
    list ranks BELOW the candidate's depth at the position (live position
    rank > ``depth``, the candidate's priced count there) cannot be told
    apart from that churn, so he is not called a pipeline loss here; the
    caller then applies the tail-churn rule, which still holds on identity
    loss, non-tail players and players listed-but-unpriced. A dropped player
    the live list ranks WITHIN the candidate's depth -- or whose live
    position is unknown, or when ``pos``/``depth`` are not given -- is still
    a contradiction: fail closed.

    Returns (verified, detail). ``detail`` contains "still priced live" only
    for a genuine contradiction (the caller keys on it).
    """
    if not dropped_slugs:
        return False, "no dropped players identified for the count drop"
    live, err = fetch_live_rows(source, combo_name)
    if live is None:
        return False, err
    still_live = sorted(s for s in dropped_slugs
                        if live.get(norm_player_name(s), (0.0, None))[0] > 0)
    if not still_live:
        return True, (f"live-verified: all {len(dropped_slugs)} dropped player(s) "
                      f"absent from the live source ({', '.join(sorted(dropped_slugs)[:4])})")
    contradicting, below_depth = [], []
    if pos is not None and depth is not None:
        ranked = sorted(((v, n) for n, (v, p) in live.items()
                         if p == pos and v > 0), reverse=True)
        rank_of = {n: i + 1 for i, (_v, n) in enumerate(ranked)}
        for s in still_live:
            rank = rank_of.get(norm_player_name(s))
            if rank is not None and rank > depth:
                below_depth.append(f"{s} (live {pos}{rank}/{len(ranked)})")
            else:
                contradicting.append(s)
    else:
        contradicting = still_live
    if contradicting:
        return False, (f"{len(contradicting)} dropped player(s) still priced live "
                       f"(e.g. {', '.join(contradicting[:3])}) -- pipeline loss")
    return False, (f"live tail: {len(below_depth)} dropped player(s) listed live only "
                   f"below the candidate's {pos} depth {depth} "
                   f"({', '.join(below_depth[:4])}) -- indistinguishable from "
                   "publisher tail churn between bake and review; tail rule applies")


# JEG-436 (Jeremy 2026-10-07: "Tighten or loosen whichever gates you need").
# A weekly list churns its tail: FantasyCalc's week-5 list dropped Pat
# Freiermuth and Terrance Ferguson and added Mike Gesicki (TE 27 -> 26). When
# the live check cannot confirm the drop (no live API, fetch failure), a SMALL,
# NAMED drop of tail players the publisher no longer lists is a warn, not a
# hold. A live check that finds a dropped player still priced stays a fail.
COVERAGE_CHURN_ABS = 3        # players, per (combo, position)
COVERAGE_CHURN_FRAC = 0.05    # ...or this share of the fixture's priced set
COVERAGE_CHURN_TAIL_FRAC = 0.10  # dropped player's fixture native must be
                                 # below this share of the position's top native


def coverage_drop_is_tail_churn(f_n, c_n, dropped, fx_native, pos_slugs,
                                cand_native, review_ids=frozenset(),
                                key_of=None):
    """Is a priced-count drop small, named, tail-of-list publisher churn?

    Returns (ok, detail). Fails closed unless every condition holds:
      - the dropped players are named (a count drop with no named player
        means the counts disagree with the sets);
      - net drop and players dropped are each <= the cap
        max(COVERAGE_CHURN_ABS, ceil(COVERAGE_CHURN_FRAC * fixture count));
      - every dropped player was in the tail of the fixture's list (fixture
        native < COVERAGE_CHURN_TAIL_FRAC x the position's top fixture native);
      - no dropped player is still in the candidate's natives (listed by the
        source but unpriced = anchor or pipeline loss, not churn);
      - no dropped player (slug or player_key) is in the candidate's review
        rows (an identity / matching loss, not churn).
    """
    import math
    net = f_n - c_n
    if not dropped:
        return False, (f"count fell by {net} but no player left the priced set "
                       "-- counts disagree with the priced sets")
    names = ", ".join(dropped[:8]) + (" ..." if len(dropped) > 8 else "")
    cap = max(COVERAGE_CHURN_ABS, math.ceil(COVERAGE_CHURN_FRAC * f_n))
    if net > cap:
        return False, f"net drop {net} > tolerance {cap} (dropped: {names})"
    if len(dropped) > cap:
        return False, (f"{len(dropped)} players left the priced set > "
                       f"tolerance {cap} (dropped: {names})")
    top = max((float(fx_native.get(s) or 0) for s in pos_slugs), default=0.0)
    not_tail = [s for s in dropped
                if top <= 0 or float(fx_native.get(s) or 0) >= COVERAGE_CHURN_TAIL_FRAC * top]
    if not_tail:
        return False, (f"{len(not_tail)} dropped player(s) were not tail-of-list "
                       f"({', '.join(not_tail[:4])}; native >= "
                       f"{COVERAGE_CHURN_TAIL_FRAC:.0%} of the position top {top:g})")
    still_listed = [s for s in dropped if s in cand_native]
    if still_listed:
        return False, (f"{len(still_listed)} dropped player(s) still listed by the "
                       f"source but unpriced ({', '.join(still_listed[:4])}) -- "
                       "anchor/pipeline loss, not churn")
    key_of = key_of or {}
    in_review = [s for s in dropped
                 if s.lower() in review_ids
                 or (key_of.get(s) is not None and str(key_of.get(s)) in review_ids)]
    if in_review:
        return False, (f"{len(in_review)} dropped player(s) in the candidate's "
                       f"review rows ({', '.join(in_review[:4])}) -- identity loss")
    return True, (f"tail churn tolerated: net -{net}, {len(dropped)} left "
                  f"(tolerance {cap}); no longer listed by the source: {names}")


def _week_num(value):
    m = re.search(r"(\d+)", str(value)) if value not in (None, "") else None
    return int(m.group(1)) if m else None


def newer_vintage(cand, fx_section):
    """Return a description when the candidate is a newer publication than the
    fixture section (higher designated week, or same/unknown week with a later
    content date), else None.

    Week-over-week the publishers re-rank most of their chart, so native drift
    against an older week is measured source movement, not corruption. Drift
    at the same (or an unknown) vintage keeps the hard fail.
    """
    if not fx_section:
        return None
    cw, fw = _week_num(cand.get("week_designated")), _week_num(fx_section.get("week_designated"))
    if cw is not None and fw is not None and cw != fw:
        return f"Week {cw} vs fixture Week {fw}" if cw > fw else None
    cd = str(cand.get("content_vintage") or "")[:10]
    fd = str(fx_section.get("content_vintage") or "")[:10]
    if re.match(r"\d{4}-\d{2}-\d{2}$", cd) and re.match(r"\d{4}-\d{2}-\d{2}$", fd) and cd > fd:
        return f"content {cd} vs fixture {fd}"
    return None


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
        newer = newer_vintage(cand, fx_section)
        if frac > DRIFT_FAIL_FRAC and newer:
            checks.append(_check(f"native_drift:{combo_name}", "warn",
                                 f"{len(drifted)}/{len(shared)} values moved > "
                                 f"{DRIFT_TOL} -- newer publication ({newer}); "
                                 "measured source movement"))
        elif frac > DRIFT_FAIL_FRAC:
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

    # coverage check: priced players per position, candidate vs fixture.
    #
    # JEG-436 (2026-10-07). Two defects made the FantasyCalc week-5 hold
    # undiagnosable ("no dropped players identified for the count drop"):
    #   1. The baseline was the fixture's recorded index_total.n_priced, which
    #      was stale against the fixture's own priced set (full_12_qb1:
    #      recorded WR 78 / TE 28, priced set WR 76 / TE 27).
    #   2. The dropped list kept only fixture players whose REINDEXED value was
    #      truthy. Since the JEG332-STORED-DRIFT re-translation, players at or
    #      below the waiver line are stored at exactly 0.0, so every tail
    #      player -- exactly the players a weekly list churns -- vanished from
    #      the list.
    # The comparison is now set-based: a player is priced when the combo has a
    # reindexed entry for them (0.0 included). A recorded count that disagrees
    # with the priced set is a visible warn, and the set is the baseline.
    if fx_section is not None:
        review_ids = set()
        for row in cand.get("review_rows", []):
            for k in ("slug", "player_key", "canonical_name", "player_name"):
                if row.get(k) is not None:
                    review_ids.add(str(row.get(k)).lower())
            inner = row.get("row") if isinstance(row.get("row"), dict) else {}
            for k in ("player_key", "player_name"):
                if inner.get(k) is not None:
                    review_ids.add(str(inner.get(k)).lower())
        for combo_name, combo in cand["combos"].items():
            fx = fx_combos.get(combo_name)
            if not fx:
                continue
            fx_reidx = fx.get("reindexed", fx.get("values", {}))
            fx_native = fx.get("native", {})
            c_keys = combo.get("player_keys", {})
            for pos in POSITIONS:
                # As-published sources use global scaling; per-position counts
                # may not be available. Skip if candidate has no per-pos data.
                if pos not in combo["n"]:
                    continue
                c_recorded = combo["n"].get(pos, 0)
                f_recorded = fx.get("index_total", {}).get(pos, {}).get("n_priced")
                fx_priced = {s for s in fx_reidx
                             if pos_by_key.get(player_keys.get(s)) == pos}
                c_priced = {s for s in combo.get("reindexed", {})
                            if pos_by_key.get(c_keys.get(s, player_keys.get(s))) == pos}
                # JEG-436 follow-up (2026-10-07): both sides on ONE basis.
                # #392 compared the candidate's RECORDED n (the flex-aware pie
                # bucket count, which by design excludes zero-native players --
                # reindex_comparison_section.py `zero_native`) with the
                # fixture's priced SET (which includes them at 0.0). USA Today
                # full_12/QB: recorded 32, set 35 (Mendoza, Sanders, Tagovailoa
                # at native 0.0) on BOTH sides -> held on "32 < 35" with no
                # player dropped. Sets on both sides when the fixture has one;
                # recorded counts on both sides only when it does not.
                if fx_priced:
                    c_n, f_n = len(c_priced), len(fx_priced)
                else:
                    c_n, f_n = c_recorded, f_recorded
                if f_n is None:
                    continue  # fixture records no priced count; cannot compare
                dropped = sorted(fx_priced - c_priced)
                added = sorted(c_priced - fx_priced)
                cov = combos_detail.setdefault(combo_name, {}).setdefault(
                    "coverage", {}).setdefault(pos, {})
                cov.update({"candidate": c_n, "fixture": f_n,
                            "candidate_recorded_n": c_recorded,
                            "fixture_recorded_n_priced": f_recorded,
                            "dropped": dropped, "added": added})
                # The candidate's own recorded count vs its own priced set: a
                # visible warn (like coverage_baseline), never silent. The
                # flex-aware pie's zero-native exclusion is named so a reader
                # can tell the by-design gap from an unexplained one.
                if c_priced and c_recorded != len(c_priced):
                    c_zero = sum(1 for s in c_priced
                                 if float(combo["native"].get(s) or 0) <= 0)
                    explained = c_recorded == len(c_priced) - c_zero
                    checks.append(_check(
                        f"coverage_count:{combo_name}/{pos}", "warn",
                        f"candidate recorded n {c_recorded} disagrees with its own "
                        f"priced set ({len(c_priced)}; {c_zero} at native 0) -- "
                        + ("explained by the flex-aware pie's zero-native exclusion"
                           if explained else "UNEXPLAINED by zero-native exclusion")
                        + "; compared on the priced set"))
                if fx_priced and f_recorded is not None and f_recorded != len(fx_priced):
                    checks.append(_check(
                        f"coverage_baseline:{combo_name}/{pos}", "warn",
                        f"fixture index_total.n_priced {f_recorded} disagrees with its "
                        f"own priced set ({len(fx_priced)}); compared against the set"))
                if c_n >= f_n:
                    continue
                named = (f"dropped: {', '.join(dropped[:8]) or 'none named'}"
                         f"; added: {', '.join(added[:8]) or 'none'}")
                status, verify_detail = "fail", "live verification skipped"
                live_contradicts = False
                if not no_live_verify and source in LIVE_API_URLS and dropped:
                    verified, verify_detail = verify_coverage_drop_live(
                        source, combo_name, dropped, pos=pos, depth=c_n)
                    if verified:
                        status = "pass"
                    live_contradicts = "still priced live" in verify_detail
                if status != "pass" and not live_contradicts:
                    churn_ok, churn_detail = coverage_drop_is_tail_churn(
                        f_n, c_n, dropped, fx_native, fx_priced, combo["native"],
                        review_ids, {s: c_keys.get(s, player_keys.get(s)) for s in dropped})
                    verify_detail = f"{verify_detail}; {churn_detail}"
                    if churn_ok:
                        status = "warn"
                checks.append(_check(
                    f"coverage:{combo_name}/{pos}", status,
                    f"candidate priced {c_n} < fixture {f_n} ({named}) -- {verify_detail}"))
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
