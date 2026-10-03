#!/usr/bin/env python3
"""Record a workflow run's started_at and cron_at in comparison-chain-status.json.

JEG-137 (R10). Each scheduled workflow runs this step near the end of its job
to record when it actually started (`started_at`, GitHub Actions run start) and
the intended fire time (`cron_at`, the cron expression evaluated to its most
recent fire opportunity before started_at). For workflow_dispatch triggers,
`cron_at` is null.

The script is idempotent: it merges its record into the `workflow_runs` section
of comparison-chain-status.json, overwriting the matching workflow entry rather
than appending duplicates. A missing file is created.

Args:
    --workflow   Workflow display name (matches WORKFLOW_SOURCE_MAP keys)
    --started-at ISO timestamp of run start (usually `date -u +%FT%TZ`)
    --cron       Cron expression (e.g., "30 11 * * *"), or "" for dispatch
    --run-id     GitHub Actions run ID
    --status     Final status ("success" or "failure")
    --output     Path to comparison-chain-status.json (default: output/comparison-chain-status.json)
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path


def compute_cron_at(cron: str, started_at: datetime) -> str | None:
    """Compute the most recent fire opportunity for `cron` before `started_at`.

    Returns ISO string, or None for empty/dispatch cron expressions.
    Only numeric single-position cron is supported; complex schedules
    return None (we do not fabricate).
    """
    if not cron:
        return None
    parts = cron.split()
    if len(parts) != 5:
        return None
    try:
        minute = int(parts[0])
        hour = int(parts[1])
    except ValueError:
        return None
    if parts[2] != "*" or parts[3] != "*":
        return None
    dow_raw = parts[4]
    day_of_week = None
    if dow_raw != "*":
        try:
            day_of_week = int(dow_raw)
        except ValueError:
            return None

    # Start from the reference day at the scheduled hour/minute, UTC.
    intended = started_at.replace(
        hour=hour, minute=minute, second=0, microsecond=0
    )

    if day_of_week is not None:
        # cron Sun=0..Sat=6; Python Mon=0..Sun=6 -> convert
        py_dow = (day_of_week + 6) % 7
        days_back = (intended.weekday() - py_dow) % 7
        intended = intended - timedelta(days=days_back)
        if intended > started_at:
            intended = intended - timedelta(days=7)
    else:
        # Daily: if intended is in the future, walk back a day
        if intended > started_at:
            intended = intended - timedelta(days=1)

    return intended.isoformat()


def parse_iso(value: str) -> datetime:
    """Parse an ISO datetime, tolerating the Z suffix."""
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Record a workflow run's started_at and cron_at in comparison-chain-status.json"
    )
    parser.add_argument("--workflow", required=True,
                        help="Workflow display name")
    parser.add_argument("--started-at", required=True,
                        help="ISO timestamp of run start")
    parser.add_argument("--cron", default="",
                        help="Cron expression (or '' for workflow_dispatch)")
    parser.add_argument("--run-id", required=True,
                        help="GitHub Actions run ID")
    parser.add_argument("--status", default="success",
                        choices=["success", "failure", "unknown"],
                        help="Final job status")
    parser.add_argument("--output",
                        default="output/comparison-chain-status.json",
                        help="Path to comparison-chain-status.json")
    args = parser.parse_args()

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if output_path.exists():
        with open(output_path, "r") as f:
            data = json.load(f)
    else:
        data = {}

    started_at = parse_iso(args.started_at)
    if started_at.tzinfo is None:
        started_at = started_at.replace(tzinfo=timezone.utc)

    cron_at = compute_cron_at(args.cron, started_at)
    slip_minutes = None
    if cron_at is not None:
        cron_dt = parse_iso(cron_at)
        delta = started_at - cron_dt
        slip_minutes = max(0, int(delta.total_seconds() / 60))

    runs = data.setdefault("workflow_runs", {})
    runs[args.workflow] = {
        "workflow_name": args.workflow,
        "run_id": int(args.run_id),
        "started_at": started_at.isoformat(),
        "cron": args.cron or None,
        "cron_at": cron_at,
        "status": args.status,
        "slip_minutes": slip_minutes,
    }
    # Top-level mirrors the most recent scheduled run for the chain reader.
    if args.workflow == "Rebuild comparison chain":
        data["started_at"] = started_at.isoformat()
        data["cron_at"] = cron_at

    with open(output_path, "w") as f:
        json.dump(data, f, indent=2, sort_keys=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())