#!/usr/bin/env python3
"""Surgical FantasyCalc weekly refresh (repo-side runner).

The FantasyCalc snapshot lives in the goal workspace
(lottery/data/sources_cache/fantasycalc_*.json + fantasycalc_snapshot.json)
and is refreshed by build_sources_dashboard.py --refresh-fc. The full
dashboard build also re-pulls the pinned USA Today/CBS/FP articles and
rebuilds every rail, so on plain refresh Wednesdays this runner does ONLY
the FantasyCalc API loop, reusing the goal script's own pull/save
functions and its exact cache payload shapes (read-only import -- goal
code is never modified).

Fail-closed: all 24 combos must pull cleanly with sane row counts before
anything is written; otherwise the old cache is left untouched and the
manifest is NOT re-stamped (a fresh stamp on stale content would be
dishonest, and the watchdog would go green on a lie).

Usage:
  refresh_fantasycalc.py [--week-label "Week 3"] [--dry-run]

The week label defaults to the watchdog's nfl_week() ("Week N").
"""
import argparse
import os
import sys
from datetime import datetime, timezone

REPO = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO, "ops", "watchdog"))
GOAL_BIN = os.path.expanduser(
    "~/workspace/goals/football-signal-database-and-app/lottery/bin")
sys.path.insert(0, GOAL_BIN)

from _common import nfl_week  # noqa: E402
import build_sources_dashboard as bsd  # noqa: E402  (read-only use)

MIN_ROWS = 100  # the live representative combo holds ~210 rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--week-label", default=None)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    week_label = args.week_label or ("Week %d" % nfl_week())

    combos = [(s, t, q) for s in bsd.SCORINGS
              for t in bsd.TEAM_COUNTS for q in bsd.QB_COUNTS]
    fetched_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    pulled = {}
    for scoring, teams, qbs in combos:
        key = "%s_%d_qb%d" % (scoring, teams, qbs)
        try:
            rows = bsd.pull_fantasycalc(scoring, teams, qbs)
        except Exception as e:  # noqa: BLE001 -- per-combo failure is fatal here
            print("FATAL: %s pull failed: %s -- cache untouched, manifest not "
                  "re-stamped" % (key, e), flush=True)
            sys.exit(1)
        if not rows or len(rows) < MIN_ROWS:
            print("FATAL: %s returned %d rows (< %d) -- cache untouched, "
                  "manifest not re-stamped" % (key, len(rows or []), MIN_ROWS),
                  flush=True)
            sys.exit(1)
        pulled[key] = rows
        print("pulled %s: %d rows" % (key, len(rows)), flush=True)

    if args.dry_run:
        print("dry-run ok: %d combos pulled, nothing written" % len(pulled))
        return

    # Same payload shape as build_sources_dashboard.py --refresh-fc.
    for key, rows in pulled.items():
        bsd.save_cache("fantasycalc_%s" % key,
                       {"fetched_at": fetched_at, "rows": rows,
                        "snapshot": {"week": week_label,
                                     "cadence": "weekly snapshot"}})
    bsd.save_cache("fantasycalc_snapshot",
                   {"week": week_label, "fetched_at": fetched_at,
                    "cadence": "weekly snapshot",
                    "combos": sorted(pulled),
                    "note": "Weekly snapshot tied to the NFL week, not a live read."})
    print("wrote %d combo caches + snapshot manifest (week %s)" % (
        len(pulled), week_label), flush=True)


if __name__ == "__main__":
    main()
