#!/usr/bin/env python3
"""Merge a candidate comparison section into a candidate comparison artifact.

Reads the CURRENT comparison fixture plus a candidate section file and writes
``output/comparison-sources-data-candidate.json``: a deep copy of the fixture
with the candidate section installed under ``sources{}``, marked as a candidate
(never live). Also writes ``output/comparison-candidate-report.json`` comparing
the candidate's native values against the current baseline for the same section
key, when one exists.

Fail-closed rules:
- output and report paths must never resolve under data/ (especially
  data/fixtures/current/); anything inside data/ is refused;
- the live fixture is only read, never written;
- missing values are never zero-filled: every candidate native value must
  trace to a numeric source-reference row (verified, not assumed).
"""

from __future__ import annotations

import argparse
import copy
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_COMPARISON = ROOT / "data" / "fixtures" / "current" / "comparison-sources-data.json"
DEFAULT_OUTPUT = ROOT / "output" / "comparison-sources-data-candidate.json"
DEFAULT_REPORT = ROOT / "output" / "comparison-candidate-report.json"
INPUT_SCHEMA = "trade-value-comparison-section-candidate-v1"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SystemExit(f"Expected JSON object in {path}")
    return payload


def require_output_path(path: Path) -> Path:
    """Fail closed when the path resolves under data/ (never touch the fixture tree)."""
    resolved = path.resolve()
    data_root = (ROOT / "data").resolve()
    if resolved == data_root or data_root in resolved.parents:
        raise SystemExit(f"Refusing to write inside data/: {path}")
    return resolved


def verify_no_zero_fill(section: dict[str, Any]) -> dict[str, Any]:
    """Every native value must trace to a placed reference row.

    The section builder only places numeric reference rows, so any None in
    ``native`` (or a placed/review count mismatch) is a defect, not data.
    """
    summary = section.get("summary", {})
    placed = summary.get("placed_count", 0)
    counted = sum(len(combo.get("native", {})) for combo in section.get("combos", {}).values())
    problems = []
    for combo_key, combo in section.get("combos", {}).items():
        for name, value in combo.get("native", {}).items():
            if value is None:
                problems.append(f"{combo_key}:{name} is null in native")
            elif not isinstance(value, (int, float)) or isinstance(value, bool):
                problems.append(f"{combo_key}:{name} is non-numeric in native")
    if placed != counted:
        problems.append(f"placed_count={placed} does not match native entries={counted}")
    return {"status": "pass" if not problems else "fail", "problems": problems}


def compare_combos(
    candidate_combos: dict[str, Any],
    current_section: dict[str, Any] | None,
) -> dict[str, Any]:
    if current_section is None:
        return {"baseline": "none (new section key)", "combos": {}}
    current_combos = current_section.get("combos", {})
    report: dict[str, Any] = {"baseline": "current fixture section", "combos": {}}
    for combo_key, candidate_combo in candidate_combos.items():
        candidate_native = candidate_combo.get("native", {})
        current_combo = current_combos.get(combo_key, {})
        current_native = current_combo.get("native", {})
        overlap = sorted(set(candidate_native) & set(current_native))
        deltas = [
            (name, candidate_native[name] - current_native[name]) for name in overlap
        ]
        abs_deltas = sorted(((name, abs(delta)) for name, delta in deltas), key=lambda item: -item[1])
        report["combos"][combo_key] = {
            "current_combo_present": bool(current_combo),
            "n_overlap": len(overlap),
            "n_candidate_only": len(set(candidate_native) - set(current_native)),
            "n_current_only": len(set(current_native) - set(candidate_native)),
            "max_abs_delta": round(abs_deltas[0][1], 4) if abs_deltas else None,
            "mean_abs_delta": round(sum(item[1] for item in abs_deltas) / len(abs_deltas), 4) if abs_deltas else None,
            "largest_deltas": [
                {"name": name, "candidate": candidate_native[name], "current": current_native[name],
                 "delta": round(candidate_native[name] - current_native[name], 4)}
                for name, _ in abs_deltas[:10]
            ],
        }
    return report


def merge_candidate(candidate_path: Path, comparison_path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    candidate = load_json(candidate_path)
    if candidate.get("schema") != INPUT_SCHEMA:
        raise SystemExit(f"{candidate_path} is not a {INPUT_SCHEMA} file")
    section_key = candidate.get("section_key")
    if not section_key:
        raise SystemExit(f"{candidate_path} is missing section_key")
    combos = candidate.get("combos")
    if not isinstance(combos, dict) or not combos:
        raise SystemExit(f"{candidate_path} must contain combos{{}}")

    zero_fill = verify_no_zero_fill(candidate)
    if zero_fill["status"] != "pass":
        raise SystemExit(f"Zero-fill check failed: {'; '.join(zero_fill['problems'])}")

    fixture = load_json(comparison_path)
    sources = fixture.get("sources")
    if not isinstance(sources, dict):
        raise SystemExit(f"{comparison_path} must contain sources{{}}")

    merged = copy.deepcopy(fixture)
    merged["sources"][section_key] = candidate
    merged["built_at"] = utc_now()
    validation = merged.get("source_validation")
    if isinstance(validation, dict):
        validation[section_key] = "candidate"
    merged["candidate"] = {
        "section_key": section_key,
        "candidate_input": str(candidate_path),
        "baseline_fixture": str(comparison_path),
        "reindex_status": candidate.get("reindex_status", "pending"),
        "note": "Candidate artifact for review only. Not published; the live fixture is untouched.",
    }

    report = {
        "schema": "trade-value-comparison-candidate-report-v1",
        "generated_at": utc_now(),
        "candidate_input": str(candidate_path),
        "baseline_fixture": str(comparison_path),
        "section_key": section_key,
        "reindex_status": candidate.get("reindex_status", "pending"),
        "zero_fill_check": zero_fill,
        "candidate_summary": candidate.get("summary", {}),
        "candidate_review_count": len(candidate.get("review_rows", [])),
        "combo_comparison": compare_combos(combos, sources.get(section_key)),
    }
    return merged, report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, required=True, help="candidate section file")
    parser.add_argument("--comparison", type=Path, default=DEFAULT_COMPARISON,
                        help="current comparison fixture (read-only baseline)")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()

    output = require_output_path(args.output)
    report_path = require_output_path(args.report)

    merged, report = merge_candidate(args.candidate, args.comparison)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(merged, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    section_key = report["section_key"]
    compared = report["combo_comparison"]
    print(
        f"Merged candidate section '{section_key}' ({compared['baseline']}). "
        f"Wrote {output} and {report_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
