#!/usr/bin/env python3
"""Freshness SLA check for the weekly dashboard load (JEG-396).

Read-only: queries api.weekly_dashboard_status and compares the published
(season, week) against the expected NFL week. Never touches the Muse
runtime state; safe to run from GitHub Actions or locally.

Exit codes: 0 = all clear, 1 = breach (message on stdout, ::error::/::warning::
annotations when running under GitHub Actions).

Staleness rules (see runbooks/weekly-dashboard-freshness.md):
- CRITICAL: no current run; published week != expected week (from Wednesday);
  newest run older than 8 days (loader dead).
- WARNING: signal_count == 0 on the current run; bundle_built_at older than 8 days.

Trade-chart sources (JEG-1180): each source in the chain status
(`source_weeks` in output/comparison-chain-status.json, or $DDF_CHAIN_STATUS)
is judged by its OWN served week with the shared rule in
pipelines/week_state.py: lagging is normal Tuesday through Thursday morning;
still on week N after Thursday 12:00 CT of week N+1 is stale. Stale prints a
warning annotation and never changes the exit code. See
docs/week-transition-runbook.md.
"""
import datetime as dt
import os
import sys

SKILL_BIN = os.path.expanduser("~/workspace/skills/supabase-football-signal/bin")
if os.path.isdir(SKILL_BIN):
    sys.path.insert(0, SKILL_BIN)
sys.path.insert(0, "/opt/hatch/skills/skill-creator/bin")
import sbclient  # noqa: E402

# The calendar is pipelines/nfl_week.py (one week rule). This dashboard is
# labelled by GAME week (Thursday flip): the week whose games it covers.
# BUMP the season there every August (runbook).
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "pipelines"))
import nfl_week  # noqa: E402
import week_state  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHAIN_STATUS = os.path.join(REPO, "output", "comparison-chain-status.json")

SEASON = nfl_week.SEASON
RUN_MAX_AGE_DAYS = 8
BUNDLE_MAX_AGE_DAYS = 8


def annotate(level, msg):
    if os.environ.get("GITHUB_ACTIONS") == "true":
        print(f"::{level}::{msg}")
    print(f"{level.upper()}: {msg}")


def expected_week(today):
    """Expected published NFL week for `today` (UTC date).

    Weeks are labeled by the Sunday ending the week. Monday/Tuesday tolerate
    the prior week (Monday-night games may just have concluded); from
    Wednesday the current week must be published.
    """
    raw = nfl_week.game_week(today)
    if today.weekday() in (0, 1):  # Mon, Tue
        return {raw - 1, raw}
    return {raw}


def source_week_report(now, path=None):
    """[(source, status)] for every source in the chain status, each judged
    by its own served week at `now` (week_state.source_week_status). An
    absent or unreadable status file yields []: this report never fails."""
    import json
    path = path or os.environ.get("DDF_CHAIN_STATUS") or CHAIN_STATUS
    try:
        with open(path, encoding="utf-8") as fh:
            weeks = json.load(fh).get("source_weeks") or {}
    except (OSError, ValueError, AttributeError):
        return []
    if not isinstance(weeks, dict):
        return []
    annotated = week_state.annotate_source_weeks(weeks, now)
    return [(source, annotated[source]) for source in sorted(annotated)]


def report_source_weeks(now, path=None):
    """Print each source's served week and state; stale sources get a
    warning annotation. Returns the stale source names. Never a breach."""
    stale = []
    for source, st in source_week_report(now, path):
        line = (f"source {source}: serves Week {st['served_week']} "
                f"(calendar Week {st['expected_week']}) -> {st['state']}")
        if st["state"] == "stale":
            stale.append(source)
            annotate("warning", f"{line}; still behind after Thursday 12:00 CT "
                                f"({st['stale_after']}). Warning only (docs/week-transition-runbook.md)")
        else:
            print(f"INFO: {line}")
    return stale


def main():
    breaches = []
    warnings = []
    try:
        rows = sbclient.get("weekly_dashboard_status", "?select=*", schema="api")
    except Exception as e:
        annotate("error", f"freshness check could not read api.weekly_dashboard_status: {e}")
        return 1
    if len(rows) != 1:
        annotate("error", f"status view returned {len(rows)} rows, expected exactly 1")
        return 1
    s = rows[0]
    # One New York calendar (JEG-1177): the UTC date ran a day ahead each
    # evening Eastern. The instant is read here so tests freeze it.
    now = dt.datetime.now(dt.timezone.utc)
    today = nfl_week.today_ny(now)
    # JEG-1180: per-source week states, warning only (exit code unchanged).
    report_source_weeks(now)

    if not s.get("has_current"):
        breaches.append("no current weekly run (has_current=false)")
    else:
        pub = (s.get("season"), s.get("week"))
        exp = expected_week(today)
        if pub[1] not in exp or pub[0] != SEASON:
            breaches.append(
                f"published season/week {pub[0]}/{pub[1]} not in expected {sorted(exp)} "
                f"for {today} (season {SEASON})"
            )
        if (s.get("signal_count") or 0) == 0:
            warnings.append("current run has 0 signals")
        try:
            run_age = today - dt.datetime.fromisoformat(s["run_created_at"]).date()
            if run_age.days > RUN_MAX_AGE_DAYS:
                breaches.append(f"newest run is {run_age.days}d old (>{RUN_MAX_AGE_DAYS}d) — loader may be dead")
        except (TypeError, ValueError):
            breaches.append("run_created_at missing/unparseable on status view")
        try:
            bundle_age = today - dt.datetime.fromisoformat(s["bundle_built_at"]).date()
            if bundle_age.days > BUNDLE_MAX_AGE_DAYS:
                warnings.append(f"bundle_built_at is {bundle_age.days}d old (>{BUNDLE_MAX_AGE_DAYS}d) — stale bundle")
        except (TypeError, ValueError):
            warnings.append("bundle_built_at missing/unparseable on status view")

    # current_run_count > 1 means the atomic-promotion invariant broke.
    if (s.get("current_run_count") or 0) > 1:
        breaches.append(f"current_run_count={s['current_run_count']} — multiple current runs!")

    for w in warnings:
        annotate("warning", w)
    for b in breaches:
        annotate("error", b)
    if not breaches and not warnings:
        print(f"OK: season {s.get('season')} week {s.get('week')} current, "
              f"{s.get('signal_count')} signals, published {s.get('run_created_at')}")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
