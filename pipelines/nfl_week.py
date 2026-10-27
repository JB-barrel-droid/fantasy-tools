#!/usr/bin/env python3
"""The one NFL calendar for the 2026 season. Two week concepts, defined once.

CONTENT WEEK (Tuesday flip) -- `content_week(day)`
    The week the trade-chart publishers and projection sources are on. They
    post their "Week N" charts on Monday night / Tuesday, after the Monday
    night game, so content week N runs Tuesday..Monday:
        Week 1: Tue 2026-09-08 .. Mon 2026-09-14
        Week 2: Tue 2026-09-15 .. Mon 2026-09-21  (and so on)
    Use it for EVERYTHING that labels data: savers' week grain, ingests,
    import health, the rebuild chain, history, VORP grains, freshness.
    SQL copy: public.nfl_content_week (supabase/migrations/
    jeg432_source_freshness.sql). JS copy: product-data.js contentWeekForDay.
    Both are pinned to this function by tests.

GAME WEEK (Thursday flip) -- `game_week(day)`
    The week whose games are being played: game week N runs Thursday..
    Wednesday from Thursday 2026-09-10. (The 2026 opener, NE@SEA, was on
    Wednesday 2026-09-09; weeks 2+ open Thursday: DET@BUF Thu 09-17. Schedule
    checked 2026-09-21 against sportsnet.ca / nbc.com / si.com.) Use it ONLY where
    games themselves matter (e.g. "which week's games are left"), never to
    label a source's content. On Tuesday and Wednesday it is one week behind
    the content week; labelling a save with it files new content under the
    previous week (GAP-WEEK-CALENDARS, GAP-INGEST-THU-WEEK).

CLOCK (JEG-1177): every "today" is the New York calendar day
    (America/New_York), because the content week turns over after Monday
    Night Football, Eastern time. `today_ny()` is the one reader of the wall
    clock; tests and replays inject a fixed instant with `set_clock(...)` or
    the DDF_NOW environment variable (ISO timestamp). The page's copy is
    product-data.js todayIsoDay (America/New_York, window.TRADE_VALUE_TODAY
    override). A UTC date flips the week 4-5 hours early (Monday evening in
    Chicago), which is why value_reference.py and three CLIs read the wrong
    week each Monday night before this.

Usage:
    python3 pipelines/nfl_week.py          # prints the content week
    python3 pipelines/nfl_week.py --game   # prints the game week
"""

from __future__ import annotations

import os
import sys
from datetime import date, datetime, timedelta, timezone
from typing import Callable
from zoneinfo import ZoneInfo

SEASON = 2026
CONTENT_WEEK_1_START = date(2026, 9, 8)   # Tuesday before the Week 1 kickoff
GAME_WEEK_1_START = date(2026, 9, 10)     # Thursday, Week 1 kickoff
REGULAR_SEASON_WEEKS = 18
LAST_GAME_WEEK = 22                        # through the Super Bowl
NEW_YORK = ZoneInfo("America/New_York")

_clock: Callable[[], datetime] | None = None


def set_clock(clock: Callable[[], datetime] | datetime | None) -> None:
    """Inject the wall clock (a callable returning an aware datetime, a fixed
    datetime, or None to restore the real clock)."""
    global _clock
    if isinstance(clock, datetime):
        fixed = clock
        _clock = lambda: fixed  # noqa: E731
    else:
        _clock = clock


def now_utc() -> datetime:
    """The current instant: the injected clock, else DDF_NOW, else the system clock."""
    if _clock is not None:
        moment = _clock()
    elif os.environ.get("DDF_NOW"):
        try:
            from lib.timestamps import parse_iso_timestamp
        except ImportError:  # imported as pipelines.nfl_week
            from pipelines.lib.timestamps import parse_iso_timestamp
        moment = parse_iso_timestamp(os.environ["DDF_NOW"])
    else:
        moment = datetime.now(timezone.utc)
    if moment.tzinfo is None:
        raise ValueError("the clock must return an aware datetime")
    return moment.astimezone(timezone.utc)


def today_ny(now: datetime | None = None) -> date:
    """The New York calendar day of `now` (default: the clock above)."""
    moment = now or now_utc()
    if moment.tzinfo is None:
        raise ValueError("today_ny needs an aware datetime")
    return moment.astimezone(NEW_YORK).date()


def content_week(day: date | None = None) -> int:
    """Content week (Tuesday flip) for a date; 1 before the season, capped at 18.
    No date: today in New York (today_ny)."""
    day = day or today_ny()
    days_since = (day - CONTENT_WEEK_1_START).days
    if days_since < 0:
        return 1
    return min(days_since // 7 + 1, REGULAR_SEASON_WEEKS)


def content_week_or_none(day: date) -> int | None:
    """Content week of a date, or None before content week 1 (no week yet)."""
    if day < CONTENT_WEEK_1_START:
        return None
    return content_week(day)


def content_week_start(week: int) -> date:
    """The Tuesday content week `week` opens."""
    return CONTENT_WEEK_1_START + timedelta(weeks=week - 1)


def game_week(day: date | None = None) -> int:
    """Game week (Thursday flip) for a date; 1 before kickoff, capped at 22."""
    day = day or today_ny()
    week = (day - GAME_WEEK_1_START).days // 7 + 1
    return max(1, min(LAST_GAME_WEEK, week))


def week_of_label(value) -> int | None:
    """'Week 5' -> 5; anything else -> None."""
    import re
    m = re.match(r"^\s*week\s*(\d+)\s*$", str(value or ""), re.I)
    return int(m.group(1)) if m else None


def week_of_date(value) -> int | None:
    """Content week of an ISO date/timestamp string, or None."""
    try:
        return content_week_or_none(date.fromisoformat(str(value or "")[:10]))
    except ValueError:
        return None


def section_content_week(section) -> int | None:
    """Content week of a fixture source section: the week its values belong
    to (what the page labels it), never the chain week. Same order as the
    page's product-data.js sourceVintage: the "Week N" label
    (week_designated), a "Week N" content_vintage, then the importer's
    provenance week, then the first dated field (content_vintage, vintage,
    espn_snapshot, lineage.raw_vintage, fetched_at) on the content calendar.
    None when nothing dates the section."""
    if not isinstance(section, dict):
        return None
    for value in (section.get("week_designated"), section.get("content_vintage")):
        week = week_of_label(value)
        if week:
            return week
    prov = section.get("source_provenance") if isinstance(section.get("source_provenance"), dict) else {}
    prov_week = prov.get("week_designated")
    if isinstance(prov_week, int) and not isinstance(prov_week, bool) and prov_week > 0:
        return prov_week
    lineage = section.get("lineage") if isinstance(section.get("lineage"), dict) else {}
    for value in (section.get("content_vintage") or prov.get("content_vintage"), section.get("vintage"),
                  section.get("espn_snapshot"), lineage.get("raw_vintage"), section.get("fetched_at")):
        week = week_of_date(value)
        if week:
            return week
    return None


def current_nfl_week(today: date | None = None) -> int:
    """Back-compatible name for content_week (the chain's week)."""
    return content_week(today)


if __name__ == "__main__":
    print(game_week() if "--game" in sys.argv[1:] else content_week())
