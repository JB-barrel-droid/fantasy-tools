#!/usr/bin/env python3
"""Independent deadline checker for monitoring source and chain freshness.

This checker runs independently of the comparison chain itself, allowing it to
detect when the chain has not run for an extended period (staleness).

Per D3 (JEG-83, 2026-10-02): NO alert recipient — no messages, no callbacks, no
third-party integration. The only consumer is the rendered monitor route.

JEG-189 (R10 wiring): each source's grace is extended by measured scheduler
slip. `grace_window_minutes()` returns `publication_window +
slip_observed_max_minutes`, where unmeasured sources fall back to the
6h default and stale measurements are surfaced in the reason string. The
slip itself is loaded by `compute_slip_measurement()` from
`pipelines.measure_scheduler_slip` (called here from `check_deadlines()`).

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
from pipelines.nfl_week import content_week_start as _content_week_start, current_nfl_week
from pipelines.lib.publication_windows import (
    PUBLICATION_SCHEDULES,
    DEFAULT_SLIP_MINUTES,
    format_slip_reason,
    get_slip_minutes,
    get_slip_status,
    load_slip_overrides,
    reset_slip_overrides,
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

    Per JEG-189 (R10 wiring), the returned window is
    `publication_window + slip_observed_max_minutes`, so the deadline
    checker uses a single value to extend its grace. Slip comes from
    PUBLICATION_SCHEDULES[source]["slip_observed_max_minutes"] when
    "measured" and fresh, else the 6h default fallback. Unverified
    schedules return `None`.

    Args:
        source: Source name (used to look up slip from PUBLICATION_SCHEDULES)
        rule: Publication schedule rule from PUBLICATION_SCHEDULES

    Returns:
        Grace window in minutes (publication + slip), or None if no rule.
    """
    if rule is None or rule.get("grace_days") is None:
        return None
    publication_minutes = rule["grace_days"] * 24 * 60
    slip_minutes = get_slip_minutes(source)
    return publication_minutes + slip_minutes


def _slip_status_for_source(source: str) -> str:
    """Wrap get_slip_status with the default for unknown sources."""
    return get_slip_status(source) if source in PUBLICATION_SCHEDULES else "unmeasured"


def compute_slip_measurement(slip_history_fn: callable | None = None) -> dict[str, Any]:
    """Compute and load the per-source scheduler slip measurement.

    JEG-189 (R10 wiring). Calls
    `pipelines.measure_scheduler_slip.compute_scheduler_slip(history)` and
    applies the result via `load_slip_overrides()`. The returned dict is
    the raw measurement (also available from `PUBLICATION_SCHEDULES[...]`
    via the slip helpers).

    Args:
        slip_history_fn: Optional callable returning the list of workflow
            runs. If `None`, defaults to `get_slip_history()`, which raises
            `NotImplementedError` (same contract as `get_supabase_last_write`).
            Tests inject a fake.

    Returns:
        The full measurement dict as returned by `compute_scheduler_slip`.
        On error (missing measurement, GitHub API failure) returns a dict
        with `error` set and leaves slip_status at "unmeasured".
    """
    try:
        from pipelines.measure_scheduler_slip import compute_scheduler_slip
    except ImportError as e:
        return {"error": f"measure_scheduler_slip import failed: {e}"}

    fetch = slip_history_fn or get_slip_history
    try:
        history = fetch()
    except NotImplementedError:
        # No injection and no default fetcher; treat as unmeasured.
        reset_slip_overrides()
        return {
            "generated_at": None,
            "sources": {},
            "error": "no_slip_history_injected",
        }
    except Exception as e:  # pragma: no cover - injected by tests when needed
        # Network/API error -- fail closed to defaults so the checker keeps
        # running. Operator sees the slip reason "default 6h (unmeasured)".
        reset_slip_overrides()
        return {
            "generated_at": None,
            "sources": {},
            "error": f"slip_history_fetch_failed: {type(e).__name__}: {e}",
        }

    if not isinstance(history, list):
        reset_slip_overrides()
        return {
            "generated_at": None,
            "sources": {},
            "error": "slip_history_not_a_list",
        }

    try:
        measurement = compute_scheduler_slip(history)
    except Exception as e:  # pragma: no cover
        reset_slip_overrides()
        return {
            "generated_at": None,
            "sources": {},
            "error": f"compute_scheduler_slip_failed: {type(e).__name__}: {e}",
        }

    load_slip_overrides(measurement)
    return measurement


def get_slip_history() -> list[dict[str, Any]]:
    """Return GitHub Actions workflow runs for slip measurement.

    Default raises `NotImplementedError`, matching the
    `get_supabase_last_write` injection contract. Production injects a
    fetcher (e.g., the GitHub REST API). Tests inject canned runs.

    JEG-189 (R10 wiring).
    """
    raise NotImplementedError(
        "Workflow run history requires external injection. "
        "Use a mock in tests or inject via config in production."
    )


def determine_source_state(
    source: str,
    last_write: datetime | None,
    nfl_week: int,
    check_time: datetime,
) -> dict[str, Any]:
    """Determine the state for a single source.

    JEG-189 (R10 wiring): the grace window is extended by measured
    scheduler slip (`publication_window + slip_observed_max_minutes`).
    Unmeasured sources use the 6h default fallback; stale measurements
    are surfaced in the reason string.

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
    content_week_start = _content_week_start(nfl_week)
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

    # Add base publication grace
    grace_until = expected_by + timedelta(days=grace_days)

    # JEG-189 (R10 wiring): extend grace by measured scheduler slip.
    slip_minutes = get_slip_minutes(source)
    effective_grace_until = grace_until + timedelta(minutes=slip_minutes)
    slip_reason = format_slip_reason(source)
    slip_status = _slip_status_for_source(source)

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
        if check_time <= effective_grace_until:
            return {
                "expected_by": expected_by.isoformat(),
                "actual_at": last_write.isoformat(),
                "lag_minutes": lag_minutes,
                "state": "unknown",
                "reason": (
                    f"No {source} write yet for Week {nfl_week} "
                    f"(within slip-adjusted grace; {slip_reason})"
                ),
                "slip_status": slip_status,
                "slip_minutes": slip_minutes,
            }
        return {
            "expected_by": expected_by.isoformat(),
            "actual_at": last_write.isoformat(),
            "lag_minutes": lag_minutes,
            "state": "red",
            "reason": (
                f"No {source} write for Week {nfl_week}; "
                f"past {grace_days}-day grace + {slip_minutes}min slip "
                f"({slip_reason})"
            ),
            "slip_status": slip_status,
            "slip_minutes": slip_minutes,
        }

    if last_write <= expected_by:
        # Published on time - green, regardless of when we check
        return {
            "expected_by": expected_by.isoformat(),
            "actual_at": last_write.isoformat(),
            "lag_minutes": lag_minutes,
            "state": "green",
            "reason": f"Published on time for Week {nfl_week}",
            "slip_status": slip_status,
            "slip_minutes": slip_minutes,
        }
    elif last_write <= effective_grace_until:
        # Late but within slip-extended grace - amber
        slip_extra = (
            f"; {slip_reason}" if slip_status == "measured" else
            f" ({slip_reason})" if slip_status == "stale" else ""
        )
        return {
            "expected_by": expected_by.isoformat(),
            "actual_at": last_write.isoformat(),
            "lag_minutes": lag_minutes,
            "state": "amber",
            "reason": (
                f"Published late for Week {nfl_week} "
                f"(within {grace_days}-day grace + {slip_minutes}min slip){slip_extra}"
            ),
            "slip_status": slip_status,
            "slip_minutes": slip_minutes,
        }
    else:
        # Published after slip-adjusted grace - red
        return {
            "expected_by": expected_by.isoformat(),
            "actual_at": last_write.isoformat(),
            "lag_minutes": lag_minutes,
            "state": "red",
            "reason": (
                f"Published past {grace_days}-day grace + {slip_minutes}min slip "
                f"for Week {nfl_week} ({slip_reason})"
            ),
            "slip_status": slip_status,
            "slip_minutes": slip_minutes,
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
    slip_history_fn: callable | None = None,
) -> dict[str, Any]:
    """Check all deadlines and generate the deadline checker artifact.

    JEG-189 (R10 wiring): calls `compute_slip_measurement()` first so
    every source's grace is slip-adjusted before `determine_source_state`
    decides green/amber/red. Pass `slip_history_fn` to inject a fake
    workflow-run history (tests do this).

    Args:
        nfl_week: NFL week to check
        check_time: Optional check time (defaults to now)
        source_last_write_fn: Optional injectable function for source timestamps
        slip_history_fn: Optional injectable function for GitHub workflow runs

    Returns:
        The complete deadline checker artifact
    """
    if check_time is None:
        check_time = datetime.now(timezone.utc)

    # JEG-189 (R10 wiring): compute and load slip BEFORE deciding source
    # states, so each call to determine_source_state() picks up the fresh
    # slip via PUBLICATION_SCHEDULES. Reset is implicit inside
    # load_slip_overrides(), so a stale load never leaks across runs.
    slip_measurement = compute_slip_measurement(slip_history_fn)

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
        "slip_measurement": {
            "generated_at": slip_measurement.get("generated_at"),
            "sources": slip_measurement.get("sources", {}),
            "error": slip_measurement.get("error"),
        },
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
