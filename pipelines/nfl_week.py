#!/usr/bin/env python3
"""Calculate the current NFL week for the 2026 season.

The 2026 NFL season started on Thursday, September 10, 2026.
Each NFL week runs Thursday through Wednesday.

Usage:
    python3 nfl_week.py
    # Output: 4
"""

from datetime import date

# 2026 NFL season Week 1 started Thursday, September 10, 2026
SEASON_START = date(2026, 9, 10)

def current_nfl_week(today=None):
    """Return the NFL content week number for the given date (default: today).
    
    The content week turns over on Tuesday, after the Monday night game.
    This matches when publishers (USA Today, etc.) release the new week's
    rankings.
    
    Week 1 content: Tue Sep 8 - Mon Sep 14, 2026
    Week 2 content: Tue Sep 15 - Mon Sep 21
    Week 3 content: Tue Sep 22 - Mon Sep 28
    Week 4 content: Tue Sep 29 - Mon Oct 5
    etc.
    """
    if today is None:
        today = date.today()
    # Content Week 1 starts Tuesday Sep 8, 2026
    CONTENT_WEEK_1_START = date(2026, 9, 8)
    days_since = (today - CONTENT_WEEK_1_START).days
    if days_since < 0:
        return 1  # Preseason
    week = (days_since // 7) + 1
    # Cap at 18 (regular season weeks)
    return min(max(week, 1), 18)

if __name__ == "__main__":
    print(current_nfl_week())
