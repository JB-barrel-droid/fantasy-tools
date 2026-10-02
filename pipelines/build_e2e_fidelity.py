#!/usr/bin/env python3
"""JEG-77: Build e2e-fidelity.json — end-to-end source fidelity for the dashboard.

Thin builder that IMPORTS check_freshness and check_fidelity from
pipelines/check_source_fidelity (no duplication — one implementation, imported)
and produces a dashboard-friendly JSON payload.

The payload shape:
  {
    "generated_at": <ISO8601 UTC>,
    "max_age_days": <float>,
    "sources": {
      <source_key>: {
        "label": <human label>,
        "fetched_at": <ISO or "">,
        "content_vintage": <str or "">,
        "freshness": { "status": "ok|warn|bad|unk", "failures": [...] },
        "fidelity": { "status": "ok|warn|bad|unk", "failures": [...] },
        "n_failures": <int>,
        "status": "ok|warn|bad|unk"
      },
      ...
    },
    "summary": { "n_sources": ..., "n_failures": ..., "status": "ok|warn|bad" }
  }

This is what the dashboard card renders. Per-source failures carry the exact
shape produced by the imported check_source_fidelity.check_freshness /
check_fidelity functions — same source, same messages, just re-shaped for
display.

Usage:
    python3 pipelines/build_e2e_fidelity.py [--out PATH] [--fixture PATH]
        --out PATH:      output JSON path (default: dist/modules/e2e-fidelity.json)
        --fixture PATH:  fixture JSON (default: data/fixtures/current/comparison-sources-data.json)
        --max-age-days:  snapshot age threshold passed through to check_freshness
Exit 0 always; this builder is consumed by the dashboard, not used as a gate.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# Import the JEG-77a implementation. The dashboard card must show what
# check_source_fidelity reports — same code path, no parallel logic.
REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "pipelines"))
import check_source_fidelity as csf  # noqa: E402

DEFAULT_FIXTURE = REPO / "data" / "fixtures" / "current" / "comparison-sources-data.json"
DEFAULT_OUTPUT = REPO / "dist" / "modules" / "e2e-fidelity.json"

# Human-readable labels mirror check_source_fidelity's SOURCES order.
SRC_LABEL = {
    "fantasycalc": "FantasyCalc",
    "usatoday": "USA Today",
    "fantasypros": "FantasyPros",
    "cbs": "CBS",
}


def _status_for_failures(failures: list[dict]) -> str:
    """Map a list of failure dicts to a coarse dashboard status.

    - Any 'fidelity_flip' → "bad" (data correctness defect)
    - freshness_stale / freshness_parse_error → "warn" (midweek update concern)
    - freshness_unknown → "unk" (cannot determine)
    - no failures → "ok"
    """
    if not failures:
        return "ok"
    types = {f.get("type", "") for f in failures}
    if "fidelity_flip" in types:
        return "bad"
    if "freshness_stale" in types or "freshness_parse_error" in types:
        return "warn"
    if "freshness_unknown" in types:
        return "unk"
    # Defensive fallback: any failure is at least warn.
    return "warn"


def build(fixture_path: Path, max_age_days: float) -> dict:
    """Produce the e2e-fidelity payload by calling the imported checks.

    Raises FileNotFoundError if the fixture is missing — the builder refuses
    to fabricate a payload from an empty fixture (fail-closed).
    """
    if not fixture_path.exists():
        raise FileNotFoundError(f"fixture not found: {fixture_path}")
    fixture = json.loads(fixture_path.read_text())

    payload: dict = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "max_age_days": max_age_days,
        "sources": {},
        "summary": {"n_sources": 0, "n_failures": 0, "status": "ok"},
    }

    n_failures = 0
    worst = "ok"
    worst_rank = {"ok": 0, "unk": 1, "warn": 2, "bad": 3}

    for src in csf.SOURCES:
        src_data = fixture.get("sources", {}).get(src, {})

        # Freshness + fidelity: imported directly from check_source_fidelity.
        # No parallel logic. If a source is missing from the fixture, the
        # imported checks return [] for fidelity and either skip freshness
        # (unknown) or report freshness_unknown — we mirror that contract.
        if not src_data:
            freshness_failures: list[dict] = [{
                "source": src,
                "type": "freshness_unknown",
                "message": f"{src}: source missing from fixture, cannot verify",
            }]
            fidelity_failures: list[dict] = []
        else:
            freshness_failures = csf.check_freshness(src, fixture, max_age_days)
            fidelity_failures = csf.check_fidelity(src, fixture)

        fres_status = _status_for_failures(freshness_failures)
        fid_status = _status_for_failures(fidelity_failures)
        src_n_failures = len(freshness_failures) + len(fidelity_failures)

        # Worst-of-freshness-and-fidelity drives the source pill color.
        if worst_rank[fid_status] > worst_rank[fres_status]:
            src_status = fid_status
        else:
            src_status = fres_status

        payload["sources"][src] = {
            "label": SRC_LABEL.get(src, src),
            "fetched_at": src_data.get("fetched_at", "") if src_data else "",
            "content_vintage": src_data.get("content_vintage", "") if src_data else "",
            "freshness": {
                "status": fres_status,
                "failures": freshness_failures,
            },
            "fidelity": {
                "status": fid_status,
                "failures": fidelity_failures,
            },
            "n_failures": src_n_failures,
            "status": src_status,
        }
        n_failures += src_n_failures
        if worst_rank[src_status] > worst_rank[worst]:
            worst = src_status

    payload["summary"] = {
        "n_sources": len(payload["sources"]),
        "n_failures": n_failures,
        "status": worst,
    }
    return payload


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Build e2e-fidelity.json (JEG-77)")
    ap.add_argument("--out", default=str(DEFAULT_OUTPUT),
                    help="output JSON path (default: dist/modules/e2e-fidelity.json)")
    ap.add_argument("--fixture", default=str(DEFAULT_FIXTURE),
                    help="fixture JSON path (default: data/fixtures/current/comparison-sources-data.json)")
    ap.add_argument("--max-age-days", type=float, default=2.0,
                    help="snapshot age threshold passed to check_freshness (default: 2.0)")
    args = ap.parse_args(argv)

    out_path = Path(args.out)
    fixture_path = Path(args.fixture)
    payload = build(fixture_path, args.max_age_days)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2))
    print(f"wrote {out_path} — {payload['summary']['n_failures']} failure(s) "
          f"across {payload['summary']['n_sources']} source(s), "
          f"status={payload['summary']['status']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())