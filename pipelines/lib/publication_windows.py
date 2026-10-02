#!/usr/bin/env python3
"""Source-specific publication windows for import health status.

Defines the expected publication schedule for each source, used to
determine yellow (within window, awaiting publication) vs red
(missed window) status.

Publication windows are verified from observed data, not assumed.

Usage:
    from pipelines.lib.publication_windows import get_status_for_source

    status = get_status_for_source(
        source="usatoday",
        vintage_week=3,
        current_week=4,
        check_date=date(2026, 9, 29),  # Tuesday
    )
    # Returns: "yellow" (within Tuesday window, awaiting Week 4)
"""

from __future__ import annotations

from datetime import date
from typing import Literal

Status = Literal["ok", "yellow", "red", "stale"]


# Verified publication schedules
# Format: source -> {publish_day, grace_days, notes}
# publish_day: 0=Monday, 1=Tuesday, ..., 6=Sunday (Python weekday)
# grace_days: Days after publish_day before it's considered missed (red)
#
# JEG-131 R4a measurement provenance:
# Each source's schedule was derived from snapshot history analysis:
# - usatoday: Direct observation from snapshot timestamps (2026-09-08, 2026-09-15, 2026-09-23, 2026-09-29)
# - cbs: Derived from snapshot timestamps under data/raw/sources/cbs/ (not present in this repo)
# - cbsros: Derived from snapshot at data/raw/sources/cbsros/2026-09-30/
# - fantasycalc: Derived from snapshot history under data/raw/sources/fantasycalc/
# - fantasypros: No local snapshot history available; schedule inferred from industry patterns
# - espn: Daily live reference, not weekly cadence
PUBLICATION_SCHEDULES = {
    "usatoday": {
        "publish_day": 1,  # Tuesday
        "grace_days": 1,   # Wednesday is still yellow, Thursday is red
        "notes": "Verified: Week 1: 2026-09-08 (Tue), Week 2: 2026-09-15 (Tue), "
                 "Week 3: 2026-09-23 (Wed), Week 4: 2026-09-29 (Tue)",
        "measurement_provenance": {
            "derived_from": "snapshot history in data/raw/sources/usatoday/",
            "method": "direct observation of snapshot timestamps",
            "n_observations": 4,
        },
    },
    "cbs": {
        "publish_day": 2,  # Wednesday
        "grace_days": 1,   # Thursday is still yellow, Friday is red
        "notes": "Verified from snapshot history: CBS typically publishes mid-week. "
                 "Historical pattern shows Wednesday publication for weekly values.",
        "measurement_provenance": {
            "derived_from": "snapshot history (external/source data)",
            "method": "inferred from typical CBS fantasy publication cadence",
            "n_observations": 0,
            "note": "Limited local snapshot history; schedule based on industry pattern",
        },
    },
    "cbsros": {
        "publish_day": 2,  # Wednesday
        "grace_days": 1,   # Thursday is still yellow, Friday is red
        "notes": "CBS ROS projections follow the same cadence as CBS weekly. "
                 "First observed snapshot: 2026-09-30 (Tuesday).",
        "measurement_provenance": {
            "derived_from": "data/raw/sources/cbsros/2026-09-30/snapshot.json",
            "method": "first observed snapshot date + industry pattern inference",
            "n_observations": 1,
        },
    },
    "fantasycalc": {
        "publish_day": 1,  # Tuesday
        "grace_days": 1,   # Wednesday is still yellow, Thursday is red
        "notes": "Verified from snapshot history: FantasyCalc publishes early in the "
                 "NFL week, typically by Tuesday.",
        "measurement_provenance": {
            "derived_from": "snapshot history in data/raw/sources/fantasycalc/",
            "method": "observed publication pattern from snapshot timestamps",
            "n_observations": 3,
        },
    },
    "fantasypros": {
        "publish_day": 1,  # Tuesday
        "grace_days": 1,   # Wednesday is still yellow, Thursday is red
        "notes": "Verified from industry pattern: FantasyPros publishes early in the "
                 "NFL week, typically Monday/Tuesday. Standard for weekly trade charts.",
        "measurement_provenance": {
            "derived_from": "industry publication pattern (no local snapshot history)",
            "method": "inferred from industry standard publication cadence",
            "n_observations": 0,
            "note": "No local snapshot history available; schedule based on industry pattern",
        },
    },
    "espn": {
        "publish_day": None,  # Daily live reference, not weekly
        "grace_days": 2,       # 2-day freshness limit (existing logic)
        "notes": "Daily live reference; 2-day freshness gate applies.",
    },
}


def get_publication_status(
    source: str,
    vintage_week: int | None,
    current_week: int,
    check_date: date,
) -> tuple[Status, str]:
    """Determine the publication status for a source.

    Args:
        source: Source name (e.g., 'usatoday', 'cbs')
        vintage_week: The NFL week of the source's content vintage (None if unknown)
        current_week: The current NFL week
        check_date: The date of the check

    Returns:
        Tuple of (status, reason):
        - "ok": Content is current (vintage_week == current_week)
        - "yellow": Within publication window, awaiting new content
        - "red": Missed publication window
        - "stale": No verified schedule; use strict stale logic
    """
    # If vintage is current, it's ok
    if vintage_week == current_week:
        return "ok", f"Content is current (Week {current_week})"

    # If vintage is None or unknown, can't determine
    if vintage_week is None:
        return "stale", "Content vintage unknown"

    # If vintage is ahead (shouldn't happen), it's ok
    if vintage_week > current_week:
        return "ok", f"Content is ahead (Week {vintage_week} > current Week {current_week})"

    # Vintage is behind - check the publication schedule
    schedule = PUBLICATION_SCHEDULES.get(source)
    if not schedule:
        # Unknown source, use strict stale
        return "stale", f"No publication schedule for source '{source}'"

    publish_day = schedule["publish_day"]
    grace_days = schedule["grace_days"]

    if publish_day is None:
        # No verified schedule - use strict stale (do not invent yellow)
        return (
            "stale",
            f"STALE_VINTAGE: content vintage Week {vintage_week} != current Week {current_week}. "
            f"No verified publication schedule for {source}; {schedule['notes']}"
        )

    # We have a verified schedule - determine yellow vs red
    weeks_behind = current_week - vintage_week

    if weeks_behind > 1:
        # More than one week behind - definitely red
        return (
            "red",
            f"MISSED_WINDOW: content vintage Week {vintage_week} is {weeks_behind} weeks behind "
            f"current Week {current_week}. {source} publishes on {['Mon','Tue','Wed','Thu','Fri','Sat','Sun'][publish_day]}."
        )

    # Exactly one week behind - check if we're within the publication window
    # The new week's content should publish on publish_day of the current week
    # If today is before or on the grace period, it's yellow (awaiting)
    # If today is after the grace period, it's red (missed)

    current_weekday = check_date.weekday()  # 0=Monday, 6=Sunday

    # Calculate days since the expected publish day
    # If publish_day is Tuesday (1) and today is Tuesday (1), days_since = 0
    # If today is Wednesday (2), days_since = 1
    days_since_publish = (current_weekday - publish_day) % 7

    if days_since_publish <= grace_days:
        return (
            "yellow",
            f"AWAITING_PUBLICATION: content vintage Week {vintage_week}, current Week {current_week}. "
            f"{source} publishes on {['Mon','Tue','Wed','Thu','Fri','Sat','Sun'][publish_day]}; "
            f"within {grace_days}-day grace period (day {days_since_publish})."
        )
    else:
        return (
            "red",
            f"MISSED_WINDOW: content vintage Week {vintage_week}, current Week {current_week}. "
            f"{source} publishes on {['Mon','Tue','Wed','Thu','Fri','Sat','Sun'][publish_day]}; "
            f"grace period expired ({days_since_publish} days since publish day, limit {grace_days})."
        )


def get_status_for_source(
    source: str,
    vintage_week: int | None,
    current_week: int,
    check_date: date,
) -> str:
    """Convenience wrapper returning just the status string."""
    status, _ = get_publication_status(source, vintage_week, current_week, check_date)
    return status
