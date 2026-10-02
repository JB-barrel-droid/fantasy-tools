#!/usr/bin/env python3
"""Source-specific publication windows for import health status.

Defines the expected publication schedule for each source, used to
determine yellow (within window, awaiting publication) vs red
(missed window) status.

Publication windows are verified from observed data, not assumed.

Per-source slip (JEG-189, R10 wiring): each entry carries
`slip_observed_max_minutes`, `slip_measured_at`, and `slip_status` so
the deadline checker can extend the grace window by measured scheduler
slip. Slip values default to `None`/`"unmeasured"`; the deadline
checker loads them from `pipelines.measure_scheduler_slip.compute_scheduler_slip`
via `load_slip_overrides()`. Unmeasured sources use the 6-hour default
fallback; stale measurements (>30d) are flagged in the reason string.

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

from datetime import date, datetime, timedelta, timezone
from typing import Any, Literal

Status = Literal["ok", "yellow", "red", "stale"]

# JEG-189 (R10 wiring): the default scheduler slip for sources without a
# measured value. Matches DEFAULT_FALLBACK_SLIP_MINUTES in
# pipelines/measure_scheduler_slip.py; duplicated here so the deadline
# checker never imports the measurement module just to pick the fallback.
DEFAULT_SLIP_MINUTES = 360  # 6 hours

# A slip measurement older than this is considered stale and surfaced as
# "slip: stale measurement (>30d)" rather than used to extend grace.
# Matches STALE_THRESHOLD_DAYS in pipelines/measure_scheduler_slip.py.
SLIP_STALE_AFTER = timedelta(days=30)


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
#
# JEG-189 R10 wiring additions (per-source scheduler slip):
# - slip_observed_max_minutes: int | None -- max slip from recent scheduled runs
# - slip_measured_at: str | None -- ISO timestamp of the measurement (when loaded)
# - slip_status: str -- "unmeasured" (default), "measured" (fresh), or "stale" (>30d old)
PUBLICATION_SCHEDULES: dict[str, dict[str, Any]] = {
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
        "slip_status": "unmeasured",
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
        "slip_status": "unmeasured",
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
        "slip_status": "unmeasured",
    },
    "fantasycalc": {
        # JEG-187: publish_day=None per the R4 verified-not-assumed contract.
        # Local snapshot history under data/raw/sources/fantasycalc/ (gitignored)
        # does not contain a corroborated weekly cadence; the section-4 audit
        # listed FantasyCalc as an "undefined" freshness limit. Believed Tuesday
        # pattern kept in notes; treated as unknown until snapshot history
        # verifies a real cadence. Same shape as the JEG-179 CBS fix.
        "publish_day": None,
        "grace_days": 1,
        "notes": "Believed to publish early in the NFL week (typically by Tuesday) "
                 "based on industry pattern, but NOT verified against local "
                 "snapshot history. Treated as unknown until verified.",
        "measurement_provenance": {
            "derived_from": "snapshot history in data/raw/sources/fantasycalc/ (gitignored)",
            "method": "industry-pattern inference; no corroborated weekly cadence on disk",
            "n_observations": 0,
            "note": (
                "JEG-187 R4 contract: freshness for an unverified schedule must "
                "report stale, not red. Snapshot history exists locally but does "
                "not establish a publish cadence on its own."
            ),
        },
        "slip_observed_max_minutes": None,
        "slip_measured_at": None,
        "slip_status": "unmeasured",
    },
    "fantasypros": {
        # JEG-187: publish_day=None per the R4 verified-not-assumed contract.
        # n_observations=0 in the JEG-131 measurement provenance; section-4 audit
        # listed FantasyPros as an "undefined" freshness limit. The pre-JEG-131
        # commit had publish_day=None; JEG-131 overwrote it with publish_day=1
        # based on industry pattern. JEG-179 (CBS) re-established the strict
        # rule for n_observations=0; this applies the same rule to FantasyPros.
        "publish_day": None,
        "grace_days": 1,
        "notes": "Believed to publish early in the NFL week (typically Monday/Tuesday) "
                 "based on industry pattern, but NOT verified against local "
                 "snapshot history. Treated as unknown until verified.",
        "measurement_provenance": {
            "derived_from": "industry publication pattern (no local snapshot history)",
            "method": "inferred from industry standard publication cadence",
            "n_observations": 0,
            "note": (
                "JEG-187 R4 contract: freshness for an unverified schedule must "
                "report stale, not red. Same shape as the JEG-179 CBS fix."
            ),
        },
        "slip_observed_max_minutes": None,
        "slip_measured_at": None,
        "slip_status": "unmeasured",
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
        "slip_status": "unmeasured",
    },
}


# JEG-189 (R10 wiring): workflow -> source mapping for the slip loader.
# Mirrors pipelines/measure_scheduler_slip.WORKFLOW_SOURCE_MAP. The
# deadline checker calls load_slip_overrides() with the measurement dict
# from compute_scheduler_slip(); entries that map to a None source (e.g.,
# dispatch-only workflows) are ignored. Sources not listed here (usatoday,
# cbs, fantasypros) have no scheduled workflow to measure and therefore
# stay "unmeasured" -- the deadline checker falls back to the 6h default.
WORKFLOW_SOURCE_MAP = {
    "ESPN scrape to Supabase": "espn",
    "CBS ROS scrape to Supabase": "cbsros",
    "FantasyCalc drift check and refresh": "fantasycalc",
    "Source vintage check": None,
    "Rebuild comparison chain": None,
}


def effective_slip_minutes(rule: dict[str, Any] | None) -> int:
    """Return the effective scheduler slip in minutes for a rule dict.

    - If the rule has `slip_observed_max_minutes` set, return that value
      (clamped to >= 0).
    - Otherwise, return `DEFAULT_SLIP_MINUTES` (the 6-hour fallback).

    Stale measurements are NOT used to extend grace; the rule's
    `slip_status` field reflects that and is surfaced separately by
    `format_slip_reason()`. This function intentionally returns the
    fallback for stale rules so the math stays defined.

    JEG-189 (R10 wiring).
    """
    if rule is None:
        return DEFAULT_SLIP_MINUTES
    measured = rule.get("slip_observed_max_minutes")
    if measured is None:
        return DEFAULT_SLIP_MINUTES
    return max(0, int(measured))


def slip_is_stale(rule: dict[str, Any] | None, now: datetime | None = None) -> bool:
    """Return True iff a rule's slip measurement is older than SLIP_STALE_AFTER.

    A rule with no `slip_measured_at` is treated as fresh=False (the rule
    is "unmeasured", not "stale") -- so callers that want to distinguish
    must also inspect the field. This function answers only "would this
    measurement be considered stale right now?".

    JEG-189 (R10 wiring).
    """
    if rule is None:
        return False
    measured_at_raw = rule.get("slip_measured_at")
    if not measured_at_raw:
        return False
    try:
        measured_at = datetime.fromisoformat(str(measured_at_raw).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return False
    if now is None:
        now = datetime.now(timezone.utc)
    if measured_at.tzinfo is None:
        measured_at = measured_at.replace(tzinfo=timezone.utc)
    return (now - measured_at) > SLIP_STALE_AFTER


def get_slip_minutes(source: str) -> int:
    """Source-name wrapper around `effective_slip_minutes`.

    JEG-189 (R10 wiring).
    """
    return effective_slip_minutes(PUBLICATION_SCHEDULES.get(source))


def get_slip_status(source: str) -> str:
    """Return the slip status string for a source.

    One of: "measured", "stale", "unmeasured". Used by the deadline
    checker to build the slip reason string.

    JEG-189 (R10 wiring).
    """
    rule = PUBLICATION_SCHEDULES.get(source)
    if rule is None:
        return "unmeasured"
    return rule.get("slip_status", "unmeasured")


def format_slip_reason(source: str) -> str:
    """Return the human-readable slip reason for a source's deadline state.

    Examples (matching the brief's verbatim strings):
        "slip: 12m measured"
        "slip: default 6h (unmeasured)"
        "slip: stale measurement (>30d)"

    JEG-189 (R10 wiring).
    """
    rule = PUBLICATION_SCHEDULES.get(source)
    status = get_slip_status(source)
    if status == "measured":
        measured = rule.get("slip_observed_max_minutes") if rule else None
        if measured is None:
            return "slip: measured (unknown minutes)"
        return f"slip: {int(measured)}m measured"
    if status == "stale":
        return "slip: stale measurement (>30d)"
    return f"slip: default {DEFAULT_SLIP_MINUTES // 60}h (unmeasured)"


def reset_slip_overrides() -> None:
    """Reset every source's slip fields to the initial defaults.

    Used by tests to ensure a clean slate between cases, and called by
    `check_deadlines()` before applying a fresh measurement so a stale
    load never leaks across runs.

    JEG-189 (R10 wiring).
    """
    for entry in PUBLICATION_SCHEDULES.values():
        entry["slip_observed_max_minutes"] = None
        entry["slip_measured_at"] = None
        entry["slip_status"] = "unmeasured"


def load_slip_overrides(slip_measurement: dict[str, Any]) -> dict[str, str]:
    """Apply a slip-measurement dict to PUBLICATION_SCHEDULES.

    Args:
        slip_measurement: Output of
            `pipelines.measure_scheduler_slip.compute_scheduler_slip()`.
            Recognised shape:
                {
                  "generated_at": ISO str,
                  "sources": {
                     "<source>": {
                       "slip_minutes": int | None,
                       "slip_reason": "valid" | "stale_measurement" | "no_scheduled_runs" | ...,
                       "is_stale": bool,
                       ...
                     },
                     ...
                  }
                }

    Returns:
        Dict mapping source name -> resulting slip_status for inspection
        (used by tests to verify which entries were updated).

    Behaviour:
        - For each source listed in `slip_measurement["sources"]`:
          - `is_stale == True` or `slip_minutes is None`:
              status = "stale", slip_observed_max_minutes = None
          - else: status = "measured", slip_observed_max_minutes = slip_minutes
        - For each source in PUBLICATION_SCHEDULES not in the measurement:
          status stays "unmeasured" (the default); call reset_slip_overrides()
          first if you want to drop a previously-loaded measurement.

    JEG-189 (R10 wiring).
    """
    reset_slip_overrides()
    sources = (slip_measurement or {}).get("sources", {}) or {}
    generated_at = (slip_measurement or {}).get("generated_at")
    statuses: dict[str, str] = {}
    for source, payload in sources.items():
        if source not in PUBLICATION_SCHEDULES:
            # A measurement for a source we don't track; ignore it.
            continue
        rule = PUBLICATION_SCHEDULES[source]
        is_stale = bool(payload.get("is_stale"))
        slip_minutes = payload.get("slip_minutes")
        if is_stale or slip_minutes is None:
            rule["slip_status"] = "stale"
            rule["slip_observed_max_minutes"] = None
            rule["slip_measured_at"] = generated_at
        else:
            rule["slip_status"] = "measured"
            rule["slip_observed_max_minutes"] = int(slip_minutes)
            rule["slip_measured_at"] = generated_at
        statuses[source] = rule["slip_status"]
    return statuses


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
