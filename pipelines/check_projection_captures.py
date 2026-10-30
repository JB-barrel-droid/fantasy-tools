#!/usr/bin/env python3
"""Fail loudly when a content week's projection capture is missing (JEG-944).

Jeremy 2026-10-23: a full copy per source after the Tuesday flip (phase midweek) AND a
Sunday pre-kickoff copy (phase sunday). For every content week from 7 (Sunday copy from
8), each source must hold the horizons it offers in public.source_projection_captures,
at least the row floor (pipelines/lib/projection_capture.py):
  espn week-ahead rows, cbs ros + week rows, razzball ros rows.
A midweek copy is due from Wednesday 12:00 UTC of its week, a Sunday copy from the
following Monday 12:00 UTC, or with --pre-kickoff from that Sunday 16:00 UTC (JEG-1377). Exit 1 with one line per gap; a missing Sunday copy fails
loudly here, in espn-weekly-store.yml, which feeds no published value. The CBS and Razzball
savers never fail on a capture fault.

Reads through PostgREST with one-row probes, never the table. Usage:
  python3 pipelines/check_projection_captures.py [--season 2026] [--pre-kickoff] [--now ISO]
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
from timestamps import parse_iso_timestamp  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--season", type=int, default=2026)
    ap.add_argument("--pre-kickoff", action="store_true",
                    help="the current week's Sunday copy is due from Sunday 16:00 UTC (JEG-1377)")
    ap.add_argument("--now", help="ISO time, tests only")
    a = ap.parse_args(argv)
    now = parse_iso_timestamp(a.now) if a.now else datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    cells = pc.required_cells(now, sunday_due=pc.SUNDAY_DUE_PRE_KICKOFF if a.pre_kickoff else pc.SUNDAY_DUE)
    try:
        import sbclient  # noqa: PLC0415
    except ImportError:
        import gh_sbclient as sbclient  # noqa: PLC0415
    counts = pc.fetch_capture_counts(sbclient, a.season, cells)
    problems = pc.missing_captures(counts, cells)
    if problems:
        print(f"PROJECTION CAPTURE MISSING (season {a.season}):",
              file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        return 1
    print(f"projection captures complete: {len(cells)} (week, phase) cells checked")
    return 0


if __name__ == "__main__":
    sys.exit(main())
