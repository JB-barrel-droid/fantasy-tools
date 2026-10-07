#!/usr/bin/env python3
"""Snapshot public.monitoring_summary() into modules/monitoring-summary.json.

The served monitor's "is everything working" banner reads this file. The RPC
derives its answer from monitoring.check_observations through the evaluator
(monitoring.check_heartbeats), so the banner reflects what pipelines actually
recorded, not what a generated artifact claims.

Fail-closed: when Supabase cannot be reached or answers with something that is
not a summary, the file is still written, with overall="red" and the reason, so
the page can never show green on a failed read. The page also compares
`generated_at` to the browser clock and turns red when the snapshot is stale.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / "output" / "monitoring-summary.json"
SCHEMA = "ddf-monitoring-summary-v1"


def failed_snapshot(reason, now):
    return {
        "schema": SCHEMA,
        "generated_at": now.isoformat(),
        "overall": "red",
        "headline": f"Monitor read failed: {reason}",
        "read_error": reason,
        "counts": {"total": 0, "green": 0, "yellow": 0, "red": 0, "dispatch_failed": 0},
        "checks": [],
        "cron_jobs": [],
    }


def validate(payload):
    """Return a reason string when payload is not a usable summary, else None."""
    if not isinstance(payload, dict):
        return "summary is not an object"
    if payload.get("schema") != SCHEMA:
        return f"unexpected schema {payload.get('schema')!r}"
    if payload.get("overall") not in ("green", "yellow", "red"):
        return f"unknown overall {payload.get('overall')!r}"
    if not isinstance(payload.get("checks"), list) or not payload["checks"]:
        return "no checks in summary"
    if not payload.get("generated_at"):
        return "no generated_at"
    return None


def build(fetch, now=None):
    now = now or datetime.now(timezone.utc)
    try:
        payload = fetch()
    except Exception as exc:  # noqa: BLE001 - fail-closed, reported in the file
        return failed_snapshot(f"{type(exc).__name__}: {str(exc)[:200]}", now)
    bad = validate(payload)
    if bad:
        return failed_snapshot(bad, now)
    return payload


def _rpc():
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import gh_sbclient as sbclient  # noqa: PLC0415
    return sbclient.rpc("monitoring_summary", {})


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args(argv)
    snap = build(_rpc)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(snap, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    c = snap.get("counts", {})
    print(f"monitoring summary: {snap['overall']} - {snap['headline']} "
          f"(green={c.get('green')} yellow={c.get('yellow')} red={c.get('red')})")
    # A red or yellow system is information, not a build failure; only an
    # unreadable monitor fails this step (the file is still written).
    return 1 if snap.get("read_error") else 0


if __name__ == "__main__":
    raise SystemExit(main())
