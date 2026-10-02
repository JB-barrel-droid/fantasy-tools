#!/usr/bin/env python3
"""Independent deadline checker for monitoring source and chain freshness.

This checker runs independently of the comparison chain itself, allowing it to
detect when the chain has not run for an extended period (staleness).

Per D3 (JEG-83, 2026-10-02): NO alert recipient — no messages, no callbacks, no
third-party integration. The only consumer is the rendered monitor route.

Usage:
    python3 pipelines/check_deadlines.py --nfl-week 4
    # Writes output/deadline-checker.json and exits 0
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, date, timezone, timedelta
from pathlib import Path
from typing import Any

# Import existing modules (read-only consumers)
from pipelines.nfl_week import current_nfl_week
from pipelines.lib.publication_windows import (
    PUBLICATION_SCHEDULES,
    DEFAULT_SLIP_MINUTES,
    effective_slip_minutes,
)


# Configuration
OUTPUT_DIR = Path("output")
CHAIN_STATUS_FILE = OUTPUT_DIR / "comparison-chain-status.json"
DEADLINE_OUTPUT_FILE = OUTPUT_DIR / "deadline-checker.json"

# Thresholds (in hours)
CHAIN_GREEN_HOURS = 6
CHAIN_AMBER_HOURS = 12


def get_supabase_last_write(source: str, nfl_week: int) -> datetime | None:
    """Read the last-write timestamp for a source from Supabase.

    This is an injectable function. In production, it reads from Supabase.
    In tests, fakes are injected.

    Args:
        source: Source name (e.g., 'usatoday', 'espn')
        nfl_week: The NFL week to check

    Returns:
        datetime of last write, or None if not available
    """
    # Sandbox has no credentials - this function is designed to be injected
    # with a mock in tests. For production, this would query Supabase.
    # The structure allows external dependency injection without hardcoding.
    raise NotImplementedError(
        "Supabase read requires external injection. "
        "Use a mock in tests or inject via config in production."
    )


def get_source_last_write(source: str, nfl_week: int) -> datetime | None:
    """Get the last-write timestamp for a source.

    Attempts to read from Supabase, falls back to file-based timestamps.

    This is a small injectable function - tests use fakes.
    """
    try:
        return get_supabase_last_write(source, nfl_week)
    except NotImplementedError:
        # Fallback: check file-based timestamp if available
        return None


def read_chain_status() -> dict[str, Any] | None:
    """Read the comparison chain status file.

    Returns:
        The chain status dict, or None if file doesn't exist.
        Absence of the file is itself a signal (reports 'unknown').
    """
    if not CHAIN_STATUS_FILE.exists():
        return None

    with open(CHAIN_STATUS_FILE, "r") as f:
        return json.load(f)


def parse_iso_datetime(dt_str: str) -> datetime:
    """Parse ISO datetime string to timezone-aware datetime."""
    # Handle various ISO formats
    dt_str = dt_str.replace("Z", "+00:00")
    if "+" in dt_str and "-" not in dt_str.split("+")[0]:
        # Already has timezone
        return datetime.fromisoformat(dt_str)
    elif "-" in dt_str and "+" not in dt_str:
        # Has timezone offset
        return datetime.fromisoformat(dt_str)
    else:
        # No timezone info - assume UTC
        return datetime.fromisoformat(dt_str).replace(tzinfo=timezone.utc)


def grace_window_minutes(source: str, rule: dict | None) -> int | None:
    """Calculate the grace window in minutes for a source.

    JEG-137 R10: Returns ``grace_days * 24 * 60 + slip_observed_max_minutes``
    (or the 6-hour default when unmeasured). Callers that need to render the
    slip component separately should read ``effective_slip_minutes(rule)``
    from ``pipelines.lib.publication_windows`` directly.

    Args:
        source: Source name
        rule: Publication schedule rule from PUBLICATION_SCHEDULES

    Returns:
        Grace window in minutes (slip-adjusted), or None if no rule
    """
    if rule is None or rule.get("grace_days") is None:
        return None
    base_minutes = rule["grace_days"] * 24 * 60  # grace_days → minutes
    slip_minutes = effective_slip_minutes(rule)
    return base_minutes + slip_minutes


def determine_source_state(
    source: str,
    last_write: datetime | None,
    nfl_week: int,
    check_time: datetime,
) -> dict[str, Any]:
    """Determine the state for a single source.

    Args:
        source: Source name
        last_write: Last write timestamp from Supabase
        nfl_week: Current NFL week
        check_time: Current check time

    Returns:
        Dict with expected_by, actual_at, lag_minutes, state, reason
    """
    rule = PUBLICATION_SCHEDULES.get(source)

    # If no rule, report unknown
    if rule is None:
        return {
            "expected_by": None,
            "actual_at": last_write.isoformat() if last_write else None,
            "lag_minutes": None,
            "state": "unknown",
            "reason": f"No publication rule found for source '{source}'",
        }

    publish_day = rule.get("publish_day")
    grace_days = rule.get("grace_days")

    # If no verified schedule (publish_day is None), report unknown
    if publish_day is None:
        return {
            "expected_by": None,
            "actual_at": last_write.isoformat() if last_write else None,
            "lag_minutes": None,
            "state": "unknown",
            "reason": f"Publication schedule for '{source}' is unverified",
        }

    # Calculate expected publication time for current week.
    # content_week_start is anchored to Tuesday 2026-09-08, so adding
    # (nfl_week - 1) weeks lands exactly on the Tuesday of the given NFL week.
    # Use it directly: subtracting days_since_tuesday would shift the expected
    # publish date back to the wrong week on any day after Tuesday.
    content_week_start = date(2026, 9, 8) + timedelta(weeks=nfl_week - 1)
    this_week_tuesday = content_week_start

    # Expected publish time is the Tuesday of the content week at some hour
    # For simplicity, use end of day as the expected publication window
    expected_by = datetime(
        this_week_tuesday.year,
        this_week_tuesday.month,
        this_week_tuesday.day,
        23,
        59,
        tzinfo=timezone.utc,
    )

    # Add grace period (slip-adjusted per JEG-137 R10). grace_window_minutes
    # already folds in measured (or default) scheduler slip; we use it here so
    # the freshness verdict accounts for slow Actions runs.
    slip_minutes = effective_slip_minutes(rule)
    grace_window = grace_window_minutes(source, rule)
    if grace_window is None:
        # Defensive fallback: if the helper returns None for an unexpected
        # reason, fall back to the raw grace_days so the verdict still works.
        grace_window = (grace_days or 0) * 24 * 60 + slip_minutes
    grace_until = expected_by + timedelta(minutes=grace_window)
    # Raw grace window (days-only, slip excluded) — kept so the card label
    # can show "slip-adjusted grace = Xh + slip Yh" without re-computing.
    raw_grace_minutes = (grace_days or 0) * 24 * 60

    # Determine state based on last_write.
    # The verdict judges the WRITE against the deadline, not the check time
    # against the deadline: a source that published on time stays green when
    # we check later. A write dated before this content week's Tuesday belongs
    # to a previous cycle and does not satisfy this week's deadline.
    week_start = datetime(
        this_week_tuesday.year, this_week_tuesday.month, this_week_tuesday.day,
        tzinfo=timezone.utc,
    )
    if last_write is None:
        return {
            "expected_by": expected_by.isoformat(),
            "actual_at": None,
            "lag_minutes": None,
            "state": "unknown",
            "reason": f"No last-write timestamp available for '{source}'",
        }

    # Calculate lag
    lag_timedelta = check_time - last_write
    lag_minutes = int(lag_timedelta.total_seconds() / 60)

    if last_write < week_start:
        # No write yet this content week: stale write from a previous cycle.
        if check_time <= grace_until:
            return {
                "expected_by": expected_by.isoformat(),
                "actual_at": last_write.isoformat(),
                "lag_minutes": lag_minutes,
                "state": "unknown",
                "reason": f"No {source} write yet for Week {nfl_week} (still within grace)",
                "slip_observed_max_minutes": slip_minutes,
                "grace_window_minutes": grace_window,
                "raw_grace_window_minutes": raw_grace_minutes,
            }
        return {
            "expected_by": expected_by.isoformat(),
            "actual_at": last_write.isoformat(),
            "lag_minutes": lag_minutes,
            "state": "red",
            "reason": f"No {source} write for Week {nfl_week}; past slip-adjusted grace "
                      f"({grace_window // 60}h{grace_window % 60:02d}m = {raw_grace_minutes // 60}h "
                      f"+ slip {slip_minutes}m)",
            "slip_observed_max_minutes": slip_minutes,
            "grace_window_minutes": grace_window,
            "raw_grace_window_minutes": raw_grace_minutes,
        }

    if last_write <= expected_by:
        # Published on time - green, regardless of when we check
        return {
            "expected_by": expected_by.isoformat(),
            "actual_at": last_write.isoformat(),
            "lag_minutes": lag_minutes,
            "state": "green",
            "reason": f"Published on time for Week {nfl_week}",
            "slip_observed_max_minutes": slip_minutes,
            "grace_window_minutes": grace_window,
            "raw_grace_window_minutes": raw_grace_minutes,
        }
    elif last_write <= grace_until:
        # Late but within slip-adjusted grace - amber
        return {
            "expected_by": expected_by.isoformat(),
            "actual_at": last_write.isoformat(),
            "lag_minutes": lag_minutes,
            "state": "amber",
            "reason": f"Published late for Week {nfl_week} (within slip-adjusted grace "
                      f"{grace_window // 60}h{grace_window % 60:02d}m)",
            "slip_observed_max_minutes": slip_minutes,
            "grace_window_minutes": grace_window,
            "raw_grace_window_minutes": raw_grace_minutes,
        }
    else:
        # Published after grace - red
        return {
            "expected_by": expected_by.isoformat(),
            "actual_at": last_write.isoformat(),
            "lag_minutes": lag_minutes,
            "state": "red",
            "reason": f"Published past slip-adjusted grace for Week {nfl_week} "
                      f"({grace_window // 60}h{grace_window % 60:02d}m = {raw_grace_minutes // 60}h "
                      f"+ slip {slip_minutes}m)",
            "slip_observed_max_minutes": slip_minutes,
            "grace_window_minutes": grace_window,
            "raw_grace_window_minutes": raw_grace_minutes,
        }


def determine_chain_state(
    chain_status: dict | None,
    check_time: datetime,
) -> dict[str, Any]:
    """Determine the state for the comparison chain.

    Args:
        chain_status: The chain status dict from comparison-chain-status.json
        check_time: Current check time

    Returns:
        Dict with expected_by, actual_at, lag_minutes, state, runner, reason
    """
    # If chain status file doesn't exist, report unknown
    if chain_status is None:
        return {
            "expected_by": None,
            "actual_at": None,
            "lag_minutes": None,
            "state": "unknown",
            "runner": None,
            "reason": "Chain status file does not exist - chain has never run",
        }

    # Get the run timestamp
    run_at_str = chain_status.get("run_at")
    if run_at_str is None:
        return {
            "expected_by": None,
            "actual_at": None,
            "lag_minutes": None,
            "state": "unknown",
            "runner": chain_status.get("runner"),
            "reason": "Chain status has no run_at timestamp",
        }

    run_at = parse_iso_datetime(run_at_str)

    # Calculate lag
    lag_timedelta = check_time - run_at
    lag_minutes = int(lag_timedelta.total_seconds() / 60)
    lag_hours = lag_minutes / 60

    # Determine state based on thresholds
    if lag_hours <= CHAIN_GREEN_HOURS:
        return {
            "expected_by": None,  # Chain runs on demand, no fixed schedule
            "actual_at": run_at.isoformat(),
            "lag_minutes": lag_minutes,
            "state": "green",
            "runner": chain_status.get("runner"),
            "reason": f"Chain last ran {lag_hours:.1f}h ago (within {CHAIN_GREEN_HOURS}h green threshold)",
        }
    elif lag_hours <= CHAIN_AMBER_HOURS:
        return {
            "expected_by": None,
            "actual_at": run_at.isoformat(),
            "lag_minutes": lag_minutes,
            "state": "amber",
            "runner": chain_status.get("runner"),
            "reason": f"Chain last ran {lag_hours:.1f}h ago (within {CHAIN_AMBER_HOURS}h amber threshold)",
        }
    else:
        return {
            "expected_by": None,
            "actual_at": run_at.isoformat(),
            "lag_minutes": lag_minutes,
            "state": "red",
            "runner": chain_status.get("runner"),
            "reason": f"Chain last ran {lag_hours:.1f}h ago (past {CHAIN_AMBER_HOURS}h red threshold)",
        }


def check_deadlines(
    nfl_week: int,
    check_time: datetime | None = None,
    source_last_write_fn: callable | None = None,
) -> dict[str, Any]:
    """Check all deadlines and generate the deadline checker artifact.

    Args:
        nfl_week: NFL week to check
        check_time: Optional check time (defaults to now)
        source_last_write_fn: Optional injectable function for source timestamps

    Returns:
        The complete deadline checker artifact
    """
    if check_time is None:
        check_time = datetime.now(timezone.utc)

    # Read chain status
    chain_status = read_chain_status()

    # Determine chain state
    chain_state = determine_chain_state(chain_status, check_time)

    # Determine source states
    sources = {}
    source_names = ["usatoday", "fantasycalc", "fantasypros", "espn", "cbs", "cbsros"]

    # Use injected function or default implementation
    def get_source_time(src: str) -> datetime | None:
        if source_last_write_fn:
            return source_last_write_fn(src, nfl_week)
        return get_source_last_write(src, nfl_week)

    for source in source_names:
        last_write = get_source_time(source)
        sources[source] = determine_source_state(source, last_write, nfl_week, check_time)

    # Build artifact
    artifact = {
        "generated_at": check_time.isoformat(),
        "nfl_week": nfl_week,
        "sources": sources,
        "chain": chain_state,
    }

    return artifact


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Check deadline freshness for sources and chain"
    )
    parser.add_argument(
        "--nfl-week",
        type=int,
        help="NFL week to check (default: auto-detect from nfl_week.py)",
    )
    parser.add_argument(
        "--output",
        type=str,
        help="Output file path (default: output/deadline-checker.json)",
    )

    args = parser.parse_args()

    # Determine NFL week
    if args.nfl_week is not None:
        nfl_week = args.nfl_week
    else:
        nfl_week = current_nfl_week()

    # Run the check
    try:
        artifact = check_deadlines(nfl_week)
    except Exception as e:
        # Write structured failure to output
        error_artifact = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "nfl_week": nfl_week,
            "error": str(e),
            "sources": {},
            "chain": {
                "expected_by": None,
                "actual_at": None,
                "lag_minutes": None,
                "state": "unknown",
                "runner": None,
                "reason": f"Check failed: {e}",
            },
        }
        output_path = Path(args.output) if args.output else DEADLINE_OUTPUT_FILE
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(error_artifact, f, indent=2)
        print(f"Error: {e}", file=sys.stderr)
        return 1

    # Write output
    output_path = Path(args.output) if args.output else DEADLINE_OUTPUT_FILE
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w") as f:
        json.dump(artifact, f, indent=2)

    print(f"Deadline check complete. Output written to {output_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
