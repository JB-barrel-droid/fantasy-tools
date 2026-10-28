#!/usr/bin/env python3
"""The week-transition rule (JEG-1176 / JEG-1177), Python twin of
value-model.js `weekState` / `defaultWeek`. Both are pinned to the shared
vectors in tests/fixtures/week_state_vectors.json by tests/test_week_state.py,
so the two cannot drift.

Sources publish week N+1 at different times. Each source carries its own
served week. For one league setting, pass the sources that feed DDF Value
there (eligible, not hidden by a red hold or a divergence exclusion), each
with the week it serves:

* newest = the highest served week; previous = newest - 1.
* default week = newest when MORE than half of those sources serve it,
  else previous (exactly half stays on previous). Jeremy, 2026-10-27
  (JEG-1176): "Fewer than 50% of sources have published N+1 -> default to
  week N. More than 50% have published N+1 -> default to week N+1."
* A source with no known week counts in the total and has not published the
  newest week.
* No carry-forward (Jeremy, 2026-10-27): the newest week's view lists only
  the sources serving it; the previous week's view lists the sources that
  serve previous or newest (a source that moved on is read from its saved
  previous week). Everyone else is a missing source of that view. The engine
  narrows the previous view further when a moved source has no saved week.
"""
from __future__ import annotations

from typing import Iterable


def _entries(entries: Iterable) -> list[tuple[str, int | None]]:
    out, seen = [], set()
    for item in entries or []:
        if isinstance(item, dict):
            source, week = item.get("source"), item.get("week")
        else:
            source, week = item
        if not source or source in seen:
            continue
        seen.add(source)
        ok = isinstance(week, int) and not isinstance(week, bool)
        out.append((str(source), week if ok else None))
    return out


def week_state(entries: Iterable) -> dict:
    """{newest, previous, default_week, transition, weeks, on_newest, total,
    views: {"<week>": {sources, missing_sources}}} for one league setting."""
    rows = _entries(entries)
    weeks = [w for _, w in rows if w is not None]
    if not weeks:
        return {"newest": None, "previous": None, "default_week": None, "transition": False,
                "weeks": [], "on_newest": 0, "total": len(rows), "views": {}}
    newest = max(weeks)
    previous = newest - 1
    on_newest = sorted(s for s, w in rows if w == newest)
    total = len(rows)
    transition = len(on_newest) < total
    default = newest if 2 * len(on_newest) > total else previous
    everyone = sorted(s for s, _ in rows)
    views = {str(newest): {"sources": on_newest,
                           "missing_sources": [s for s in everyone if s not in on_newest]}}
    if transition:
        prev_sources = sorted(s for s, w in rows if w in (previous, newest))
        views[str(previous)] = {"sources": prev_sources,
                                "missing_sources": [s for s in everyone if s not in prev_sources]}
    return {"newest": newest, "previous": previous, "default_week": default, "transition": transition,
            "weeks": [newest, previous] if transition else [newest], "on_newest": len(on_newest),
            "total": total, "views": views}


def default_week(entries: Iterable) -> int | None:
    """The week a reader sees first at this setting (week_state's default_week)."""
    return week_state(entries)["default_week"]


# ---------------------------------------------------------------------------
# Published week state (comparison-sources-data.json `week_state`, the chain
# status `source_weeks`). JEG-1178 (selector), JEG-1179 (MCP/get-values) and
# JEG-1180 (stale flag/health) read these instead of re-deriving weeks.
# ---------------------------------------------------------------------------

PUBLISHED_AT_FIELDS = ("published_at", "content_vintage", "vintage", "espn_snapshot", "lineage.raw_vintage",
                       "fetched_at")
WEEK_STATE_TEAMS = (8, 10, 12, 14)


def published_at(section) -> str | None:
    """When a source's served content was published: the first dated field of
    PUBLISHED_AT_FIELDS (the publisher's own date first, our pull time last)."""
    import re
    if not isinstance(section, dict):
        return None
    lineage = section.get("lineage") if isinstance(section.get("lineage"), dict) else {}
    for field in PUBLISHED_AT_FIELDS:
        value = lineage.get("raw_vintage") if field == "lineage.raw_vintage" else section.get(field)
        if isinstance(value, str) and re.match(r"^\d{4}-\d{2}-\d{2}", value):
            return value
    return None


def source_weeks(fixture: dict, index: dict | None) -> dict:
    """{source: {served_week, label_week, published_at, basis}} for every
    fixture section. served_week is the history index's (content matched by
    fingerprint); without it, the section's own content week (label)."""
    from nfl_week import section_content_week
    served = (index or {}).get("served") or {}
    same_build = not ((index or {}).get("fixture_built_at") and fixture.get("built_at")
                      and index["fixture_built_at"] != fixture["built_at"])
    out = {}
    for key, section in sorted((fixture.get("sources") or {}).items()):
        if not isinstance(section, dict):
            continue
        rec = served.get(key) if same_build else None
        label = section_content_week(section)
        if isinstance(rec, dict) and isinstance(rec.get("week"), int):
            week, basis = rec["week"], "history_index"
        else:
            week, basis = label, "section_label"
        out[key] = {"served_week": week, "label_week": label, "published_at": published_at(section),
                    "basis": basis}
    return out


def published_week_state(fixture_path, history_root, players_path=None) -> dict:
    """The week state the build publishes: per-source weeks and, per league
    setting ("<scoring>_<teams>", standard roster), value_reference's week
    view (default week, weeks, per-week sources / missing_sources)."""
    import json
    from pathlib import Path
    import value_reference as R
    fixture_path = Path(fixture_path)
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    hist = R.History(Path(history_root))
    inp = R.Inputs.load(fixture_path, players_path or R.PLAYERS)
    settings = {}
    for scoring in R.SCORINGS:
        for teams in WEEK_STATE_TEAMS:
            view = R.Setting(inp, scoring, teams, hist=hist).week_view()
            settings[f"{scoring}_{teams}"] = None if view is None else {
                k: view[k] for k in ("default_week", "newest", "previous", "transition", "weeks",
                                     "on_newest", "total", "views")}
    return {"schema": 1,
            "rule": "default week = N+1 when more than half of a setting's DDF Value sources serve it, else N "
                    "(Jeremy, 2026-10-27, JEG-1176); each week's view uses only that week's data",
            "sources": source_weeks(fixture, hist.index),
            "settings": settings}


# ---------------------------------------------------------------------------
# Stale flag (JEG-1180). Jeremy, 2026-10-27 (JEG-1176, open question 3):
# "Stale cutoff? Decided: Thursday 12:00 CT. A source still on N after that
# is flagged stale (a warning, not a failure)."
#
# Each source is judged by its OWN served week, against the content-week
# calendar (nfl_week, New York day, injectable clock):
#   current  served week >= this content week
#   lagging  behind, before Thursday 12:00 CT of the week after its served
#            week (normal Tuesday through Thursday morning)
#   stale    behind, at or after that cutoff (a source two weeks behind is
#            always stale: its cutoff passed last week)
#   unknown  no served week
# Stale is a warning. Nothing here fails the chain, changes a hold or
# changes which sources a week's view uses.
# ---------------------------------------------------------------------------

STALE_CUTOFF_WEEKDAY_OFFSET = 2          # Tuesday + 2 days = Thursday
STALE_CUTOFF_HOUR = 12                   # 12:00 ...
STALE_CUTOFF_TZ = "America/Chicago"      # ... Central time
STALE_RULE = ("a source still serving week N after Thursday 12:00 CT of week N+1 is stale "
              "(Jeremy, 2026-10-27, JEG-1176); a warning only, never a chain failure")


def stale_after(week: int):
    """The instant (aware datetime, Central time) after which a source still
    serving the week before `week` is stale: Thursday 12:00 CT of content
    week `week`."""
    from datetime import datetime, time, timedelta
    from zoneinfo import ZoneInfo
    from nfl_week import content_week_start
    day = content_week_start(week) + timedelta(days=STALE_CUTOFF_WEEKDAY_OFFSET)
    return datetime.combine(day, time(STALE_CUTOFF_HOUR), tzinfo=ZoneInfo(STALE_CUTOFF_TZ))


def source_week_status(served_week, now=None) -> dict:
    """{served_week, expected_week, weeks_behind, state, stale, stale_after}
    for one source at `now` (an aware datetime; default nfl_week's clock).
    expected_week is the content week of the New York day of `now`."""
    import nfl_week
    now = now or nfl_week.now_utc()
    expected = nfl_week.content_week(nfl_week.today_ny(now))
    ok = isinstance(served_week, int) and not isinstance(served_week, bool)
    if not ok:
        return {"served_week": None, "expected_week": expected, "weeks_behind": None,
                "state": "unknown", "stale": False, "stale_after": None}
    behind = max(expected - served_week, 0)
    if behind == 0:
        state, cutoff = "current", None
    else:
        cutoff = stale_after(served_week + 1)
        state = "stale" if now >= cutoff else "lagging"
    return {"served_week": served_week, "expected_week": expected, "weeks_behind": behind,
            "state": state, "stale": state == "stale",
            "stale_after": cutoff.isoformat() if cutoff else None}


def annotate_source_weeks(weeks: dict, now=None) -> dict:
    """source_weeks() entries with each source's status (source_week_status)
    merged in. Judged at one instant, so every source sees the same clock."""
    import nfl_week
    now = now or nfl_week.now_utc()
    out = {}
    for source, entry in sorted((weeks or {}).items()):
        entry = dict(entry) if isinstance(entry, dict) else {}
        out[source] = {**entry, **source_week_status(entry.get("served_week"), now)}
    return out


def sources_in_state(annotated: dict, state: str) -> list[str]:
    """Sorted source names whose annotated state is `state`."""
    return sorted(s for s, e in (annotated or {}).items() if isinstance(e, dict) and e.get("state") == state)
