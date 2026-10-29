#!/usr/bin/env python3
"""Offline eligibility audit for the JEG-952 evidence prerequisite (JEG-1277).

JEG-952 may only be worked after four dated weekly divergence reports. This
audit reads receipts (from extract_receipts.py, or a synthetic contract
fixture) and says, per source, how many distinct weekly reports actually
qualify, and why each other capture does not. It never recommends a
threshold, and it never changes the reporter, its config or resolutions.

A capture (one committed report, one source) counts toward a week only when:

* it is a committed receipt (a git commit and report blob), schema
  source-divergence-v1, with no report error;
* the report date (`generated_at`), the build date (`fixture_built_at`) and
  the report week are present, the thresholds are recorded, and the warning
  count in the summary matches the sources' own statuses;
* every combo has a denominator `n` > 0 and an `outliers` count that agrees
  with `outlier_rate`;
* the served week (the saved week the served inputs fingerprint-match, from
  data/history/index.json at the same build) is known and EQUALS the report
  week. The report's week is the content week; a report whose charts were
  still served as an earlier week is not evidence for its label (JEG-1172);
* the served fingerprint, the source's own content date and its scoring
  basis are recorded.

Repeated captures of one report week count once (the newest qualifying
capture represents the week). A week whose served data repeats a counted
week's fingerprint does not count again. Weeks count together only when the
source's combos, scoring basis and the report thresholds are identical; a mix
is reported and only the largest compatible set counts.

Synthetic receipts (`synthetic: true` on the document or a receipt) exercise
the same rules but NEVER satisfy the real evidence prerequisite.

    python3 tools/research/divergence-evidence-audit/audit.py \
        [--receipts tests/fixtures/divergence-evidence-audit/committed-receipts.json] \
        [--markdown docs/research/divergence-evidence-audit/availability-matrix.md] \
        [--json docs/research/divergence-evidence-audit/availability.json]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
RECEIPTS = REPO / "tests" / "fixtures" / "divergence-evidence-audit" / "committed-receipts.json"
SCHEMA = "divergence-evidence-audit/1"
REPORT_SCHEMA = "source-divergence-v1"
REQUIRED_WEEKS = 4
RATE_TOLERANCE = 0.0005  # the reporter rounds outlier_rate to 3 places
FLAGGED_STATUSES = ("warn", "investigate")
SOURCES = ("usatoday", "fantasycalc", "fantasypros", "cbs", "espn", "cbsros", "razzball")
GROUP = {"usatoday": "trade_charts", "fantasycalc": "trade_charts", "fantasypros": "trade_charts",
         "cbs": "trade_charts", "espn": "projections", "cbsros": "projections", "razzball": "projections"}

# Problems that stop a capture from counting. Notes (label disagreement) do not.
REASON_TEXT = {
    "not_committed_receipt": "not a committed report (no commit or report blob)",
    "unknown_schema": "report schema is not source-divergence-v1",
    "report_error": "report recorded an error",
    "missing_report_date": "report date (generated_at) missing",
    "missing_build_date": "fixture build date missing",
    "missing_report_week": "report week missing",
    "missing_thresholds": "thresholds not recorded",
    "missing_warning_counts": "summary warning list missing",
    "warning_count_mismatch": "summary warning count disagrees with source statuses",
    "source_missing": "source not in report",
    "no_combos": "no scoring combos",
    "missing_status": "source status missing",
    "missing_counts": "denominator or outlier count missing",
    "zero_denominator": "denominator is 0",
    "rate_count_mismatch": "outlier_rate disagrees with outliers / n",
    "served_provenance_missing": "served-week provenance not found for this build",
    "served_provenance_conflict": "the only index for this build has another content week",
    "served_week_unknown": "served inputs match no saved week",
    "served_week_mismatch": "served an earlier/other week than the report week",
    "served_fingerprint_missing": "served fingerprint missing",
    "source_date_missing": "source content date missing",
    "scoring_basis_missing": "scoring basis not recorded",
}


def _int(value):
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def receipt_problems(r: dict) -> list[str]:
    rep = r.get("report") or {}
    out = []
    if not r.get("commit") or not r.get("report_blob"):
        out.append("not_committed_receipt")
    if rep.get("schema") != REPORT_SCHEMA:
        out.append("unknown_schema")
    if rep.get("error") or rep.get("status") == "error":
        out.append("report_error")
    if not rep.get("generated_at"):
        out.append("missing_report_date")
    if not rep.get("fixture_built_at"):
        out.append("missing_build_date")
    if _int(rep.get("week")) is None:
        out.append("missing_report_week")
    if not rep.get("thresholds"):
        out.append("missing_thresholds")
    flagged = rep.get("flagged")
    if flagged is None:
        out.append("missing_warning_counts")
    else:
        counted = sum(1 for v in (r.get("sources") or {}).values() if v.get("status") in FLAGGED_STATUSES)
        if len(flagged) != counted:
            out.append("warning_count_mismatch")
    return out


def capture(r: dict, source: str) -> dict:
    """One source in one receipt: its problems, notes and the facts the matrix shows."""
    rep = r.get("report") or {}
    week = _int(rep.get("week"))
    problems = list(receipt_problems(r))
    notes = []
    src = (r.get("sources") or {}).get(source)
    combos = (src or {}).get("combos") or {}
    if src is None:
        problems.append("source_missing")
    else:
        if not combos:
            problems.append("no_combos")
        if not src.get("status"):
            problems.append("missing_status")
        for c in combos.values():
            n, outliers, rate = _int(c.get("n")), _int(c.get("outliers")), c.get("outlier_rate")
            if n is None or outliers is None or rate is None:
                problems.append("missing_counts")
            elif n == 0:
                problems.append("zero_denominator")
            elif round(outliers / n, 3) != rate and abs(outliers / n - rate) > RATE_TOLERANCE + 1e-9:
                problems.append("rate_count_mismatch")
    served_doc = r.get("served")
    served = ((served_doc or {}).get("sources") or {}).get(source)
    served_week = _int((served or {}).get("week"))
    if served is None:
        problems.append("served_provenance_missing")
    elif week is not None and _int(served_doc.get("content_week")) != week:
        # The reporter takes its week from this index; a different content week means this
        # is not the index it read, so its served weeks say nothing about this report.
        problems.append("served_provenance_conflict")
    else:
        if served_week is None:
            problems.append("served_week_unknown")
        elif week is not None and served_week != week:
            problems.append("served_week_mismatch")
        if not served.get("fingerprint"):
            problems.append("served_fingerprint_missing")
        label = _int(served.get("label_week"))
        if label is not None and served_week is not None and label != served_week:
            notes.append(f"section label says week {label}, served data is week {served_week}")
    meta = ((r.get("source_meta") or {}).get("sources") or {}).get(source) or {}
    if not meta.get("source_date"):
        problems.append("source_date_missing")
    if not meta.get("scoring_basis"):
        problems.append("scoring_basis_missing")
    value_impact = ("summary" if combos and all(c.get("mad") is not None and c.get("by_position")
                                                  and c.get("examples") for c in combos.values())
                    else "missing")
    status_counts = {}
    for c in combos.values():
        status_counts[c.get("status")] = status_counts.get(c.get("status"), 0) + 1
    return {
        "commit": r.get("commit"), "report_week": week, "report_date": rep.get("generated_at"),
        "build_date": rep.get("fixture_built_at"), "served_week": served_week,
        "served_fingerprint": (served or {}).get("fingerprint"), "source_date": meta.get("source_date"),
        "status": (src or {}).get("status"), "combo_status_counts": dict(sorted(status_counts.items(), key=str)),
        "denominators": {k: c.get("n") for k, c in sorted(combos.items())},
        "outliers": {k: c.get("outliers") for k, c in sorted(combos.items())},
        "value_impact": value_impact,
        "recomputable_from": (r.get("source_meta") or {}).get("fixture_commit"),
        "identity": json.dumps([sorted(combos), meta.get("scoring_basis"), rep.get("thresholds")],
                               sort_keys=True),
        "problems": sorted(set(problems)), "notes": notes,
        "synthetic": bool(r.get("synthetic")),
    }


def audit_source(receipts: list[dict], source: str, doc_synthetic: bool) -> dict:
    caps = [capture(r, source) for r in receipts]
    weeks = sorted({c["report_week"] for c in caps if c["report_week"] is not None})
    rows = {}
    for w in weeks:
        of_week = [c for c in caps if c["report_week"] == w]
        good = [c for c in of_week if not c["problems"]]
        reasons = {}
        for c in of_week:
            for p in c["problems"]:
                reasons[p] = reasons.get(p, 0) + 1
        rep = good[-1] if good else None
        rows[w] = {"week": w, "captures": len(of_week), "qualifying_captures": len(good),
                   "representative": rep, "rejections": dict(sorted(reasons.items())),
                   "served_weeks_seen": sorted({c["served_week"] for c in of_week if c["served_week"] is not None}),
                   "counted": False, "why_not": None}
        if rep is None:
            rows[w]["why_not"] = "no qualifying capture"
    missing_week = [c for c in caps if c["report_week"] is None]
    # Repeated served data does not make a new week.
    seen_fp = {}
    for w in weeks:
        rep = rows[w]["representative"]
        if not rep:
            continue
        fp = rep["served_fingerprint"]
        if fp in seen_fp:
            rows[w]["why_not"] = f"served data repeats week {seen_fp[fp]}"
            rows[w]["representative"] = None
            continue
        seen_fp[fp] = w
    # Only one identity (combos + scoring basis + thresholds) counts together.
    by_identity = {}
    for w in weeks:
        rep = rows[w]["representative"]
        if rep:
            by_identity.setdefault(rep["identity"], []).append(w)
    chosen = max(by_identity.values(), key=lambda ws: (len(ws), ws[-1])) if by_identity else []
    for w in weeks:
        if rows[w]["representative"] and w not in chosen:
            rows[w]["why_not"] = "scoring basis, combos or thresholds differ from the counted weeks"
        elif w in chosen:
            rows[w]["counted"] = True
    synthetic = doc_synthetic or any(rows[w]["representative"]["synthetic"] for w in chosen)
    met = len(chosen) >= REQUIRED_WEEKS
    value_levels = sorted({rows[w]["representative"]["value_impact"] for w in chosen})
    return {
        "source": source, "group": GROUP.get(source), "counted_weeks": chosen,
        "counted": len(chosen), "required": REQUIRED_WEEKS,
        "mixed_identity": len(by_identity) > 1,
        "four_weeks_met": met,
        "real_evidence_sufficient": met and not synthetic,
        "synthetic": synthetic,
        "value_impact": value_levels[0] if len(value_levels) == 1 else ("mixed" if value_levels else "none"),
        "captures_without_week": len(missing_week),
        "weeks": [rows[w] for w in weeks],
    }


def audit(doc: dict) -> dict:
    receipts = doc.get("receipts") or []
    doc_synthetic = bool(doc.get("synthetic"))
    present = sorted({s for r in receipts for s in (r.get("sources") or {})}, key=lambda s: (s not in SOURCES, SOURCES.index(s) if s in SOURCES else 0, s))
    sources = {s: audit_source(receipts, s, doc_synthetic) for s in present}
    sufficient = [s for s, v in sources.items() if v["real_evidence_sufficient"]]
    return {
        "schema": SCHEMA, "synthetic": doc_synthetic, "required_weeks": REQUIRED_WEEKS,
        "receipts": len(receipts),
        "report_weeks_seen": sorted({r["report"]["week"] for r in receipts
                                     if _int((r.get("report") or {}).get("week")) is not None}),
        "four_weeks_met": [s for s, v in sources.items() if v["four_weeks_met"]],
        "real_evidence_sufficient": sufficient,
        "all_sources_sufficient": bool(sources) and len(sufficient) == len(sources),
        # Never a threshold recommendation: JEG-952's choice is Jeremy's, and only on sufficient real evidence.
        "threshold_recommendation": None,
        "threshold_review_allowed": bool(sources) and len(sufficient) == len(sources),
        "sources": sources,
    }


def _short(sha):
    return (sha or "")[:8]


def markdown(result: dict, doc: dict) -> str:
    src = doc.get("extracted_from") or {}
    lines = [
        "# Divergence evidence availability matrix (JEG-1277)",
        "",
        "Generated by `tools/research/divergence-evidence-audit/audit.py` from "
        f"`tests/fixtures/divergence-evidence-audit/committed-receipts.json` "
        f"({result['receipts']} committed report versions, ref `{src.get('ref')}` at `{_short(src.get('head'))}`). "
        "Do not edit by hand.",
        "",
        f"Required: {result['required_weeks']} distinct qualifying report weeks per source. "
        f"Report weeks seen: {', '.join(map(str, result['report_weeks_seen']))}.",
        "",
        "| Source | Counted weeks | Four weeks met | Value impact in receipts |",
        "| -- | -- | -- | -- |",
    ]
    for s, v in result["sources"].items():
        lines.append(f"| {s} | {v['counted']} ({', '.join(map(str, v['counted_weeks'])) or 'none'}) | "
                     f"{'yes' if v['four_weeks_met'] else 'no'} | {v['value_impact']} |")
    lines += ["", "## Per report week", "",
              "Cell: counted capture (commit, served week, source date, n full/half/standard) or why not. "
              "Captures = committed versions labelled that week; qualifying = passed every check.", ""]
    weeks = result["report_weeks_seen"]
    lines.append("| Source | " + " | ".join(f"Week {w}" for w in weeks) + " |")
    lines.append("| -- |" + " -- |" * len(weeks))
    for s, v in result["sources"].items():
        cells = []
        by_week = {row["week"]: row for row in v["weeks"]}
        for w in weeks:
            row = by_week.get(w)
            if not row:
                cells.append("no report")
                continue
            head = f"{row['qualifying_captures']}/{row['captures']} qualify"
            rep = row["representative"]
            if row["counted"] and rep:
                n = "/".join(str(rep["denominators"].get(k)) for k in sorted(rep["denominators"]))
                cells.append(f"counted: `{_short(rep['commit'])}`, served wk {rep['served_week']}, "
                             f"source {rep['source_date']}, n {n} ({head})")
            else:
                why = row["why_not"] or "not counted"
                rej = "; ".join(f"{REASON_TEXT.get(k, k)} ×{c}" for k, c in row["rejections"].items())
                served = f"served wk {','.join(map(str, row['served_weeks_seen'])) or '?'}"
                cells.append(f"no: {why} ({head}; {served}{'; ' + rej if rej else ''})")
        lines.append(f"| {s} | " + " | ".join(cells) + " |")
    lines += ["", "Threshold recommendation: none. "
              + ("Every source has four qualifying weeks; a threshold change is still Jeremy's choice on JEG-952."
                 if result["threshold_review_allowed"] else
                 "The evidence prerequisite is not met, so no threshold is recommended."), ""]
    return "\n".join(lines)


def summary_json(result: dict) -> dict:
    """The committed JSON: the verdict and per-week facts, without the full capture dumps."""
    out = {k: v for k, v in result.items() if k != "sources"}
    out["sources"] = {}
    for s, v in result["sources"].items():
        weeks = []
        for row in v["weeks"]:
            rep = row["representative"]
            weeks.append({"week": row["week"], "captures": row["captures"],
                          "qualifying_captures": row["qualifying_captures"], "counted": row["counted"],
                          "why_not": row["why_not"], "rejections": row["rejections"],
                          "served_weeks_seen": row["served_weeks_seen"],
                          "representative": None if not rep else {
                              k: rep[k] for k in ("commit", "report_date", "build_date", "served_week",
                                                  "served_fingerprint", "source_date", "status",
                                                  "combo_status_counts", "denominators", "outliers",
                                                  "value_impact", "recomputable_from", "notes")}})
        out["sources"][s] = {**{k: v[k] for k in v if k != "weeks"}, "weeks": weeks}
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--receipts", type=Path, default=RECEIPTS)
    ap.add_argument("--markdown", type=Path)
    ap.add_argument("--json", type=Path)
    args = ap.parse_args(argv)
    doc = json.loads(args.receipts.read_text(encoding="utf-8"))
    result = audit(doc)
    if args.markdown:
        args.markdown.write_text(markdown(result, doc), encoding="utf-8")
    if args.json:
        args.json.write_text(json.dumps(summary_json(result), indent=1, sort_keys=True) + "\n", encoding="utf-8")
    for s, v in result["sources"].items():
        print(f"{s:<12} counted {v['counted']}/{v['required']} weeks {v['counted_weeks']}"
              f"{' (synthetic)' if v['synthetic'] else ''}", file=sys.stderr)
    print("real evidence sufficient for:", ", ".join(result["real_evidence_sufficient"]) or "none", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
