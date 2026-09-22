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

Writes (under output/ only):
  output/comparison-review/<source>-<asof>-review.json
  (schema: trade-value-comparison-review-v1)
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCHEMA = "trade-value-comparison-review-v1"
POSITIONS = ("QB", "RB", "WR", "TE")
DRIFT_TOL = 0.05       # per-value tolerance for "same" native
DRIFT_WARN_FRAC = 0.0  # any drift warns
DRIFT_FAIL_FRAC = 0.05  # >5% of values drifted fails
FACTOR_LO, FACTOR_HI = 0.2, 5.0


def _load_json(path):
    with open(path) as fh:
        return json.load(fh)


def _check(name, status, detail=""):
    return {"name": name, "status": status, "detail": detail}


def review_candidate(reindexed_path, triage_path=None, fixture_path=None,
                     players_path=None):
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

    # --- pie factor sanity (no fixture needed) ---
    sane, bad = True, []
    for combo_name, combo in cand["combos"].items():
        for pos in POSITIONS:
            it = combo["index_total"].get(pos, {})
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
    else:
        fx_combos = fx_section.get("combos", {})

    # --- combos match ---
    if fx_section is not None:
        missing = [c for c in fx_combos if c not in cand["combos"]]
        extra = [c for c in cand["combos"] if c not in fx_combos]
        if missing:
            checks.append(_check("combos_match", "fail", f"missing combos: {missing}"))
        elif extra:
            checks.append(_check("combos_match", "warn", f"new combos: {extra}"))
        else:
            checks.append(_check("combos_match", "pass",
                                 f"{len(fx_combos)} combos match"))

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
            checks.append(_check(f"native_drift:{combo_name}", "fail",
                                 f"{len(drifted)}/{len(shared)} values moved > {DRIFT_TOL}"))
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

    checks.append(_check(
        "anchor_disclosure", "info",
        "candidate anchors to the fixture ESPN leg; the fixture's existing "
        "sections were baked against the retired Monday rail. Reindexed "
        "divergence above is measured, not asserted -- promotion must note "
        "the anchor change."))

    # coverage check (needs fixture positions; approximate from fixture combo keys)
    if fx_section is not None:
        for combo_name, combo in cand["combos"].items():
            fx = fx_combos.get(combo_name)
            if not fx:
                continue
            fx_reidx = fx.get("reindexed", fx.get("values", {}))
            for pos in POSITIONS:
                c_n = combo["n"].get(pos, 0)
                f_n = fx.get("index_total", {}).get(pos, {}).get("n_priced")
                if f_n is None:
                    continue  # fixture records no priced count; cannot compare
                if c_n < f_n:
                    checks.append(_check(f"coverage:{combo_name}/{pos}", "fail",
                                         f"candidate priced {c_n} < fixture {f_n}"))
        if not any(c["name"].startswith("coverage:") and c["status"] == "fail"
                   for c in checks):
            checks.append(_check("coverage", "pass", "no priced-count regressions"))

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
    args = ap.parse_args(argv)

    report = review_candidate(args.reindexed, args.triage)
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
