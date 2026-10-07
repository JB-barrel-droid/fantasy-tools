"""Current-NFL-week detection for the weekly chain.

current_week() = date-based week for the 2026 season (Wednesday-through-
Tuesday weeks, Week 1 = 2026-09-09 .. 2026-09-15), matching
matchup/bin/nfl_week.py. This is authoritative; the games-table status
is too stale to drive week rollover (Week 1 games stayed 'scheduled'
days after they were played).
"""
from datetime import date, datetime
from zoneinfo import ZoneInfo

SEASON_OPEN = date(2026, 9, 9)  # Wednesday, Week 1 day one
MAX_WEEK = 18


def current_week(season: int = 2026) -> int:
    # Date-based is authoritative. The season anchor is 2026-specific;
    # bump SEASON_OPEN each season.
    if season != 2026:
        # Fall back to DB-based detection for other seasons
        import os
        import sys
        sys.path.insert(0, os.path.expanduser("~/workspace/skills/supabase-football-signal/bin"))
        import sbclient  # noqa: E402
        rows = sbclient.get(
            "games",
            f"?season=eq.{season}&status=neq.final&select=week&order=week.asc&limit=1",
        )
        if not rows:
            raise RuntimeError(f"no unfinished weeks found for season {season}")
        return rows[0]["week"]
    d = datetime.now(ZoneInfo("America/Chicago")).date()
    delta = (d - SEASON_OPEN).days
    week = delta // 7 + 1
    return max(1, min(MAX_WEEK, week))


if __name__ == "__main__":
    print(current_week())
