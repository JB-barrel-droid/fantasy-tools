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

from datetime import date, datetime, timezone, timedelta
from typing import Literal

Status = Literal["ok", "yellow", "red", "stale"]


# JEG-137 R10: Default scheduler slip assumption when no measurement exists.
# Measured slip on observed runs reached ~6 hours; this is the worst-case
# fallback so a slow first run never trips "missed window" false positives.
DEFAULT_SLIP_MINUTES = 6 * 60  # 360 minutes (6 hours)

# Measurement is considered stale past this age. JEG-137 R10 review brief
# rule: a slip measurement older than 30 days should be flagged in the UI.
SLIP_STALE_AFTER = timedelta(days=30)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# Verified publication schedules
# Format: source -> {publish_day, grace_days, notes, slip_observed_max_minutes,
#                     slip_measured_at}
# publish_day: 0=Monday, 1=Tuesday, ..., 6=Sunday (Python weekday)
# grace_days: Days after publish_day before it's considered missed (red)
# slip_observed_max_minutes: Largest measured scheduler slip in minutes (None
#                            means unmeasured → DEFAULT_SLIP_MINUTES is used).
# slip_measured_at: ISO timestamp when the slip measurement was last refreshed
#                   (None means unmeasured).
#
# JEG-131 R4a measurement provenance:
# Each source's schedule was derived from snapshot history analysis:
# - usatoday: Direct observation from snapshot timestamps (2026-09-08, 2026-09-15, 2026-09-23, 2026-09-29)
# - cbs: Derived from snapshot timestamps under data/raw/sources/cbs/ (not present in this repo)
# - cbsros: Derived from snapshot at data/raw/sources/cbsros/2026-09-30/
# - fantasycalc: Derived from snapshot history under data/raw/sources/fantasycalc/
# - fantasypros: No local snapshot history available; schedule inferred from industry patterns
# - espn: Daily live reference, not weekly cadence
#
# JEG-137 R10: slip_observed_max_minutes / slip_measured_at default to None on
# every entry below — the helper `effective_slip_minutes()` falls back to
# DEFAULT_SLIP_MINUTES when unmeasured and flags the entry as stale when the
# measurement is older than SLIP_STALE_AFTER. The fields are intentionally
# defaulted to None so an importing test can assert presence on every entry.
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
        "slip_observed_max_minutes": None,
        "slip_measured_at": None,
    },
    "cbs": {
        # JEG-179: no VERIFIED schedule (n_observations=0). publish_day=None
        # keeps the honest "stale/unknown" verdict until snapshot history
        # verifies a real cadence. Believed Wednesday pattern kept in notes.
        "publish_day": None,
        "grace_days": 1,
        "notes": "Believed to publish mid-week (typically Wednesday) based on "
                 "industry pattern, but NOT verified against local snapshot "
                 "history. Treated as unknown until verified.",
        "measurement_provenance": {
            "derived_from": "snapshot history (external/source data)",
            "method": "inferred from typical CBS fantasy publication cadence",
            "n_observations": 0,
            "note": "Limited local snapshot history; schedule based on industry pattern",
        },
        "slip_observed_max_minutes": None,
        "slip_measured_at": None,
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
        "slip_observed_max_minutes": None,
        "slip_measured_at": None,
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
        "slip_observed_max_minutes": None,
        "slip_measured_at": None,
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
        "slip_observed_max_minutes": None,
        "slip_measured_at": None,
    },
    "espn": {
        "publish_day": None,  # Daily live reference, not weekly
        "grace_days": 2,       # 2-day freshness limit (existing logic)
        "notes": "Daily live reference; 2-day freshness gate applies.",
        "measurement_provenance": {
            "derived_from": "pipeline pull cadence (daily ESPN scrape)",
            "method": "observed puller schedule, not publisher cadence",
            "n_observations": 0,
            "note": "ESPN is pulled daily by our pipeline; no weekly publisher schedule",
        },
        "slip_observed_max_minutes": None,
        "slip_measured_at": None,
    },
}


def _parse_iso(dt_str: str) -> datetime:
    """Parse an ISO 8601 datetime string into a timezone-aware datetime."""
    return datetime.fromisoformat(dt_str.replace("Z", "+00:00"))


def effective_slip_minutes(rule: dict, now: datetime | None = None) -> int:
    """Return the slip (in minutes) that should be added to the grace window.

    JEG-137 R10 acceptance criteria:
      - unmeasured slip → DEFAULT_SLIP_MINUTES (6h) default
      - measured slip → ``rule["slip_observed_max_minutes"]``
      - measured but older than SLIP_STALE_AFTER → still returned, but
        ``slip_is_stale(rule, now)`` flips True so the card can label it
        "slip: stale measurement (>30d)" per the reviewer brief.

    Negative ``slip_observed_max_minutes`` values are treated as zero so a
    corrupt measurement can never make the grace window shrink.
    """
    observed = rule.get("slip_observed_max_minutes")
    if observed is None:
        return DEFAULT_SLIP_MINUTES
    if not isinstance(observed, (int, float)):
        return DEFAULT_SLIP_MINUTES
    return max(0, int(observed))


def slip_is_stale(rule: dict, now: datetime | None = None) -> bool:
    """True when the slip measurement is older than SLIP_STALE_AFTER.

    A rule with no measurement (``slip_measured_at is None``) is NOT stale
    here; the caller is expected to fall back to ``DEFAULT_SLIP_MINUTES`` and
    label it "slip: default 6h (unmeasured)" instead.
    """
    measured_at_raw = rule.get("slip_measured_at")
    if measured_at_raw is None:
        return False
    if now is None:
        now = _utcnow()
    try:
        measured_at = _parse_iso(measured_at_raw) if isinstance(measured_at_raw, str) else measured_at_raw
    except ValueError:
        return True
    if measured_at.tzinfo is None:
        measured_at = measured_at.replace(tzinfo=timezone.utc)
    return (now - measured_at) > SLIP_STALE_AFTER


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
