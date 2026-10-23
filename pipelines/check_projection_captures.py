#!/usr/bin/env python3
"""Fail loudly when a content week's projection capture is missing (JEG-944).

For every content week from pc.FIRST_REQUIRED_WEEK (7) to the current one, each
source must hold the horizons it offers in public.source_projection_captures, with
at least the row floor (see pipelines/lib/projection_capture.py):
  espn week-ahead rows, cbs ros + week rows, razzball ros rows.
Exit 1 with one line per gap. The current week gets a grace period until
Wednesday 12:00 UTC (the weekly pulls run Tuesday to Wednesday); past weeks never do.

Reads through PostgREST with one-row probes, never the table. Usage:
  python3 pipelines/check_projection_captures.py [--season 2026] [--now ISO]
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines" / "lib"))
sys.path.insert(0, str(ROOT / "pipelines"))
import projection_capture as pc  # noqa: E402
from nfl_week import content_week  # noqa: E402


def in_grace(now: datetime) -> bool:
    """True from Tuesday 00:00 (the content-week flip) to Wednesday 12:00 UTC."""
    wd = now.weekday()  # Tuesday = 1
    return wd == 1 or (wd == 2 and now.hour < 12)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--season", type=int, default=2026)
    ap.add_argument("--now", help="ISO time, tests only")
    a = ap.parse_args(argv)
    now = datetime.fromisoformat(a.now) if a.now else datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    current = content_week(now.date())
    try:
        import sbclient  # noqa: PLC0415
    except ImportError:
        import gh_sbclient as sbclient  # noqa: PLC0415
    counts = pc.fetch_capture_counts(sbclient, a.season,
                                     range(pc.FIRST_REQUIRED_WEEK, current + 1))
    problems = pc.missing_captures(counts, current_week=current, grace_current=in_grace(now))
    if problems:
        print(f"PROJECTION CAPTURE MISSING (season {a.season}, content week {current}):",
              file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        return 1
    print(f"projection captures complete for content weeks {pc.FIRST_REQUIRED_WEEK}-{current}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
