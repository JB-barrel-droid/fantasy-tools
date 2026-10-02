#!/usr/bin/env python3
"""Measure scheduler slip for GitHub Actions workflows.

This tool parses GitHub Actions workflow run history and computes the delay
between intended cron schedule and actual execution start time. The measured
slip is used to extend acquisition grace periods without letting delayed
collection make old publisher content appear fresh.

Usage:
    python3 pipelines/measure_scheduler_slip.py --history <json> --output <json>

Input (--history): JSON array of workflow run objects with:
  - workflow_id: int
  - workflow_name: str
  - run_started_at: str (ISO 8601)
  - run_id: int
  - event: str (schedule, workflow_dispatch, etc.)
  - status: str (completed, etc.)
  - conclusion: str (success, failure, etc., nullable)

Output (--output): JSON object with:
  - generated_at: str (ISO 8601)
  - workflows: dict mapping workflow name to slip measurement
  - sources: dict mapping source name to slip measurement (if workflow maps to source)
  - measurement_details: dict with observation interval, sample counts

Acceptance criteria:
1. Computes nonnegative started_at minus intended cron_at for scheduled runs only
2. Excludes manual/push runs and missing/ambiguous scheduling evidence
3. Fresh valid measurement uses bounded-history maximum; stale uses 360-minute fallback
4. Exactly 30d is not stale; test the boundary
5. Deadline = publication deadline + base grace + slip exactly once
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, date, timezone, timedelta
from pathlib import Path
from typing import Any

# Configuration
DEFAULT_FALLBACK_SLIP_MINUTES = 360  # 6 hours
STALE_THRESHOLD_DAYS = 30
MAX_HISTORY_RUNS = 10  # Use last N runs for measurement

# Workflow to source mapping (workflow name -> data source)
WORKFLOW_SOURCE_MAP = {
    "ESPN scrape to Supabase": "espn",
    "CBS ROS scrape to Supabase": "cbsros",
    "FantasyCalc drift check and refresh": "fantasycalc",
    "Source vintage check": None,  # Dispatch trigger, not scheduled data
    "Rebuild comparison chain": None,  # workflow_dispatch only
}

# Cron schedules in UTC (workflow name -> cron expression)
# These are the intended execution times in UTC
WORKFLOW_CRON_SCHEDULES = {
    "ESPN scrape to Supabase": "30 11 * * *",  # Daily 11:30 UTC = 06:30 CT
    "CBS ROS scrape to Supabase": "0 11 * * 3",  # Wednesday 11:00 UTC = 06:00 CT
    "FantasyCalc drift check and refresh": "45 11 * * *",  # Daily 11:45 UTC = 06:45 CT
    "Source vintage check": "0 * * * *",  # Hourly
}


def parse_cron_expression(cron: str) -> dict | None:
    """Parse a cron expression into schedule components.

    Args:
        cron: Cron expression (e.g., "30 11 * * *" or "0 11 * * 3")

    Returns:
        Dict with minute, hour, day_of_week (None if "*" or unsupported),
        or None if unparseable. Only numeric single values and "*" are
        supported; anything else returns None (ambiguous, not fabricated).
    """
    parts = cron.split()
    if len(parts) != 5:
        return None
    try:
        minute = int(parts[0])
        hour = int(parts[1])
    except ValueError:
        return None
    # Day-of-week: "*" means daily; numeric 0-6 (Sun=0) constrains the weekday
    dow_raw = parts[4]
    day_of_week = None
    if dow_raw != "*":
        try:
            day_of_week = int(dow_raw)
        except ValueError:
            return None  # ranges/lists/names unsupported -> ambiguous
    # Day-of-month and month must be "*" for this simple parser
    if parts[2] != "*" or parts[3] != "*":
        return None
    return {"minute": minute, "hour": hour, "day_of_week": day_of_week}


def get_intended_cron_time(cron: str, reference_time: datetime) -> datetime | None:
    """Calculate the intended cron execution time nearest to reference_time.

    Args:
        cron: Cron expression
        reference_time: The actual run started_at time

    Returns:
        The intended cron execution time, or None if ambiguous/unknown
    """
    sched = parse_cron_expression(cron)
    if not sched:
        return None

    # Start from the reference day at the scheduled time
    intended = reference_time.replace(
        hour=sched["hour"],
        minute=sched["minute"],
        second=0,
        microsecond=0
    )

    if sched["day_of_week"] is not None:
        # Weekly cron: walk back to the most recent matching weekday.
        # Python weekday(): Mon=0..Sun=6; cron: Sun=0..Sat=6.
        cron_dow = sched["day_of_week"]
        py_dow = (cron_dow + 6) % 7  # convert cron Sun=0 to Python Mon=0
        days_back = (intended.weekday() - py_dow) % 7
        intended = intended - timedelta(days=days_back)
        # If still in the future (same weekday but later time), go back a week
        if intended > reference_time:
            intended = intended - timedelta(days=7)
    else:
        # Daily cron: if the intended time is in the future, use yesterday
        if intended > reference_time:
            intended = intended - timedelta(days=1)

    return intended


def parse_iso_datetime(dt_str: str) -> datetime:
    """Parse ISO datetime string to timezone-aware datetime."""
    dt_str = dt_str.replace("Z", "+00:00")
    return datetime.fromisoformat(dt_str)


def is_scheduled_run(event: str) -> bool:
    """Check if a run was triggered by a schedule."""
    return event == "schedule"


def calculate_slip_minutes(
    run_started_at: datetime,
    intended_cron_at: datetime | None
) -> int | None:
    """Calculate slip in minutes between actual start and intended cron time.

    Args:
        run_started_at: Actual workflow run start time
        intended_cron_at: Intended cron execution time

    Returns:
        Slip in minutes (nonnegative), or None if cannot calculate
    """
    if intended_cron_at is None:
        return None

    slip = run_started_at - intended_cron_at
    slip_minutes = int(slip.total_seconds() / 60)

    # Return nonnegative slip (some runs may start slightly before cron)
    return max(0, slip_minutes)


def is_stale(measurement_time: datetime, check_time: datetime) -> bool:
    """Check if a measurement is stale (>30 days old).

    Args:
        measurement_time: When the measurement was taken
        check_time: Current check time

    Returns:
        True if measurement is stale (>30 days)
    """
    age = check_time - measurement_time
    return age.days > STALE_THRESHOLD_DAYS


def is_within_grace(
    deadline: datetime,
    check_time: datetime,
    base_grace_minutes: int,
    slip_minutes: int
) -> tuple[bool, str]:
    """Determine if a source is within grace period.

    Args:
        deadline: Publication deadline + base grace
        check_time: Current check time
        base_grace_minutes: Base grace period in minutes
        slip_minutes: Measured scheduler slip in minutes

    Returns:
        Tuple of (is_within_grace, reason)
    """
    effective_deadline = deadline + timedelta(minutes=slip_minutes)

    if check_time <= effective_deadline:
        return True, f"Within grace (deadline + {slip_minutes}min slip)"
    else:
        overdue_minutes = int((check_time - effective_deadline).total_seconds() / 60)
        return False, f"Past grace by {overdue_minutes}min"


def process_workflow_runs(
    workflow_runs: list[dict[str, Any]],
    workflow_name: str,
    max_runs: int = MAX_HISTORY_RUNS
) -> dict[str, Any]:
    """Process workflow runs and compute slip measurement.

    Args:
        workflow_runs: List of workflow run objects
        workflow_name: Name of the workflow
        max_runs: Maximum number of recent runs to consider

    Returns:
        Dict with slip measurement and details
    """
    cron = WORKFLOW_CRON_SCHEDULES.get(workflow_name)
    source = WORKFLOW_SOURCE_MAP.get(workflow_name)

    # Filter to scheduled runs only
    scheduled_runs = [
        r for r in workflow_runs
        if is_scheduled_run(r.get("event", ""))
    ]

    # Sort by started_at descending (most recent first)
    scheduled_runs.sort(
        key=lambda r: r.get("run_started_at", ""),
        reverse=True
    )

    # Take most recent runs
    recent_runs = scheduled_runs[:max_runs]

    if not recent_runs:
        return {
            "workflow_name": workflow_name,
            "source": source,
            "cron": cron,
            "slip_minutes": None,
            "slip_reason": "no_scheduled_runs",
            "n_observations": 0,
            "is_stale": True,
            "fallback_used": DEFAULT_FALLBACK_SLIP_MINUTES,
            "runs": [],
        }

    # Calculate slip for each run
    slip_measurements = []
    runs_detail = []

    for run in recent_runs:
        run_started_str = run.get("run_started_at")
        if not run_started_str:
            continue

        try:
            run_started_at = parse_iso_datetime(run_started_str)
        except (ValueError, TypeError):
            continue

        intended_cron_at = get_intended_cron_time(cron, run_started_at) if cron else None
        slip = calculate_slip_minutes(run_started_at, intended_cron_at)

        if slip is not None:
            slip_measurements.append(slip)

        runs_detail.append({
            "run_id": run.get("run_id"),
            "event": run.get("event"),
            "run_started_at": run_started_str,
            "intended_cron_at": intended_cron_at.isoformat() if intended_cron_at else None,
            "slip_minutes": slip,
        })

    # Determine measurement status
    if not slip_measurements:
        return {
            "workflow_name": workflow_name,
            "source": source,
            "cron": cron,
            "slip_minutes": None,
            "slip_reason": "no_valid_measurements",
            "n_observations": 0,
            "is_stale": True,
            "fallback_used": DEFAULT_FALLBACK_SLIP_MINUTES,
            "runs": runs_detail,
        }

    # Use maximum slip from recent runs (worst case within grace window)
    max_slip = max(slip_measurements)

    # Check if measurement is stale (oldest measurement > 30 days)
    oldest_measurement_time = parse_iso_datetime(recent_runs[-1].get("run_started_at", ""))
    check_time = datetime.now(timezone.utc)
    stale = is_stale(oldest_measurement_time, check_time)

    return {
        "workflow_name": workflow_name,
        "source": source,
        "cron": cron,
        "slip_minutes": max_slip if not stale else None,
        "slip_reason": "valid" if not stale else "stale_measurement",
        "n_observations": len(slip_measurements),
        "is_stale": stale,
        "fallback_used": DEFAULT_FALLBACK_SLIP_MINUTES if stale else None,
        "observation_interval": {
            "newest": recent_runs[0].get("run_started_at"),
            "oldest": recent_runs[-1].get("run_started_at"),
        },
        "runs": runs_detail,
    }


def compute_scheduler_slip(
    history: list[dict[str, Any]],
    check_time: datetime | None = None
) -> dict[str, Any]:
    """Compute scheduler slip for all workflows.

    Args:
        history: List of workflow run objects from GitHub Actions API
        check_time: Optional check time (defaults to now)

    Returns:
        Dict with slip measurements for each workflow and source
    """
    if check_time is None:
        check_time = datetime.now(timezone.utc)

    # Group runs by workflow
    workflow_runs_map: dict[str, list[dict[str, Any]]] = {}

    for run in history:
        workflow_name = run.get("workflow_name", "")
        if not workflow_name:
            continue

        if workflow_name not in workflow_runs_map:
            workflow_runs_map[workflow_name] = []

        workflow_runs_map[workflow_name].append(run)

    # Process each workflow
    workflow_measurements = {}
    source_measurements = {}

    for workflow_name, runs in workflow_runs_map.items():
        measurement = process_workflow_runs(runs, workflow_name)
        workflow_measurements[workflow_name] = measurement

        # Also map to source if applicable
        if measurement.get("source"):
            source_measurements[measurement["source"]] = {
                "slip_minutes": measurement["slip_minutes"],
                "slip_reason": measurement["slip_reason"],
                "is_stale": measurement["is_stale"],
                "fallback_used": measurement.get("fallback_used"),
                "n_observations": measurement["n_observations"],
                "workflow": workflow_name,
            }

    return {
        "generated_at": check_time.isoformat(),
        "workflows": workflow_measurements,
        "sources": source_measurements,
        "measurement_details": {
            "check_time": check_time.isoformat(),
            "max_history_runs": MAX_HISTORY_RUNS,
            "stale_threshold_days": STALE_THRESHOLD_DAYS,
            "default_fallback_minutes": DEFAULT_FALLBACK_SLIP_MINUTES,
        },
    }


def calculate_effective_deadline(
    publication_deadline: datetime,
    base_grace_minutes: int,
    slip_minutes: int | None,
    is_stale: bool
) -> tuple[datetime, str]:
    """Calculate effective deadline including slip.

    Args:
        publication_deadline: Approved publication deadline
        base_grace_minutes: Base grace period in minutes
        slip_minutes: Measured slip in minutes, or None
        is_stale: Whether slip measurement is stale

    Returns:
        Tuple of (effective_deadline, reason)
    """
    # Apply slip exactly once
    if slip_minutes is not None and not is_stale:
        effective = publication_deadline + timedelta(minutes=base_grace_minutes + slip_minutes)
        reason = f"deadline + base_grace({base_grace_minutes}min) + slip({slip_minutes}min)"
    else:
        # Use fallback
        effective = publication_deadline + timedelta(
            minutes=base_grace_minutes + DEFAULT_FALLBACK_SLIP_MINUTES
        )
        fallback_reason = "stale" if is_stale else "no_measurement"
        reason = f"deadline + base_grace({base_grace_minutes}min) + fallback({DEFAULT_FALLBACK_SLIP_MINUTES}min) [{fallback_reason}]"

    return effective, reason


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Measure scheduler slip for GitHub Actions workflows"
    )
    parser.add_argument(
        "--history",
        type=str,
        required=True,
        help="Path to JSON file containing workflow run history",
    )
    parser.add_argument(
        "--output",
        type=str,
        required=True,
        help="Path to output JSON file",
    )

    args = parser.parse_args()

    # Read history
    history_path = Path(args.history)
    if not history_path.exists():
        print(f"Error: History file not found: {args.history}", file=sys.stderr)
        return 1

    try:
        with open(history_path, "r") as f:
            history = json.load(f)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in history file: {e}", file=sys.stderr)
        return 1

    if not isinstance(history, list):
        print("Error: History must be a JSON array of workflow runs", file=sys.stderr)
        return 1

    # Compute slip
    result = compute_scheduler_slip(history)

    # Write output
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w") as f:
        json.dump(result, f, indent=2)

    print(f"Scheduler slip measurement complete. Output written to {output_path}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
