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

The week label defaults to the content week (pipelines/nfl_week.py, Tuesday flip; "Week N").

JEG-87: codify the week honestly per docs/week-coding-rules.md.
FantasyCalc's API (/values/current) carries no week in the URL and has
no week-labeled page title, so the week is asserted from --week-label
(fail-closed if unparseable) and recorded as `week` + `week_evidence`
with week_url=None / week_titles=[] on every cache payload, so
downstream consumers can see the evidence is request-asserted.
"""
import argparse
import os
import re
import sys
from datetime import datetime, timezone

REPO = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO, "ops", "watchdog"))
GOAL_BIN = os.path.expanduser(
    "~/workspace/goals/football-signal-database-and-app/lottery/bin")
sys.path.insert(0, GOAL_BIN)

from _common import content_week  # noqa: E402
import build_sources_dashboard as bsd  # noqa: E402  (read-only use)

MIN_ROWS = 100  # the live representative combo holds ~210 rows

# FantasyCalc scoring -> ppr= param. This MUST mirror
# build_sources_dashboard.pull_fantasycalc's own mapping
# ({"standard": 0, "half": 0.5, "full": 1}) so the URL recorded as
# evidence is byte-identical to the URL actually fetched.
FANTASYCALC_PPR = {"standard": 0, "half": 0.5, "full": 1}


def _week_number_from_label(week_label):
    """Parse the integer week out of a label like 'Week 4' or 'Week 4 foo'.

    Returns None if no week number is parseable, so the validator can
    treat an unparseable label the same as a missing one (fail closed).
    """
    m = re.search(r"\bweek\s+(\d+)\b", str(week_label or ""), re.I)
    return int(m.group(1)) if m else None


def fantasycalc_url(scoring, teams, qbs):
    """Rebuild the exact FantasyCalc API URL pull_fantasycalc fetches.

    Pattern:
      https://api.fantasycalc.com/values/current?isDynasty=false
        &numQbs={qbs}&numTeams={teams}&ppr={ppr}

    This is the URL recorded as evidence (Rule 3). It is byte-identical
    to the URL bsd.pull_fantasycalc requests -- no week param is added:
    the live endpoint is /values/current and ignores unknown params, so
    appending &week=N would record a URL that was never fetched.

    Honest limitation (reviewer correction 2026-10-02): FantasyCalc's API
    carries no week in the URL and there is no week-labeled page title to
    scrape -- /values/current returns current values. The week is
    asserted from --week-label (fail-closed if unparseable) and recorded
    with week_url=None / week_titles=[] so downstream consumers can see
    this is request-asserted evidence, weaker than page-extracted.
    """
    ppr = FANTASYCALC_PPR[scoring]
    return ("https://api.fantasycalc.com/values/current"
            "?isDynasty=false&numQbs=%d&numTeams=%d&ppr=%s"
            % (qbs, teams, ppr))


def extract_week_from_url(url):
    """Extract week number from a FantasyCalc URL.

    Pattern: .../values/current?...&week=N or ?week=N
    Returns None if no week param is present.
    """
    if not url:
        return None
    m = re.search(r"[?&]week=(\d+)", url)
    return int(m.group(1)) if m else None


def extract_week_from_title(title):
    """Extract week number from a FantasyCalc page title.

    Pattern: "Week N <anything>" or "<anything> Week N"
    Returns None if no week is present.
    """
    if not title:
        return None
    m = re.search(r"\bweek\s+(\d+)\b", str(title), re.I)
    return int(m.group(1)) if m else None


def validate_week_consistency(url, page_title_text, requested_week):
    """Validate URL week == title week == requested week (fail closed).

    Jeremy 2026-10-02 (docs/week-coding-rules.md): "We need to codify
    elements of the page such as the headline to the dataset, so that we
    do not have these errors, along with rules on how weeks get coded to
    datasets." A dataset without a validated week is worse than no
    dataset.

    Raises RuntimeError on any mismatch or when no evidence is available.
    Returns {week, week_url, week_titles, week_requested} on success.
    """
    url_week = extract_week_from_url(url)
    title_week = extract_week_from_title(page_title_text)
    req_week = requested_week

    weeks_seen = {w for w in (url_week, title_week, req_week)
                  if w is not None}
    if len(weeks_seen) > 1:
        raise RuntimeError(
            "FantasyCalc week evidence disagrees: url=%s title=%s "
            "requested=%s (url=%s). Refusing to label dataset."
            % (url_week, title_week, req_week, url))

    validated = req_week if req_week is not None else (
        url_week if url_week is not None else title_week)
    if validated is None:
        raise RuntimeError(
            "FantasyCalc: could not determine week from URL, page title, "
            "or request (url=%s). Refusing to label dataset without "
            "week evidence." % url)

    return {
        "week": validated,
        "week_url": url_week,
        "week_titles": [title_week] if title_week is not None else [],
        "week_requested": req_week,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--week-label", default=None)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    week_label = args.week_label or ("Week %d" % content_week())

    # JEG-87: codify the week, honestly. FantasyCalc's API (/values/current)
    # carries no week in the URL and exposes no week-labeled page title,
    # so the week is asserted from --week-label and recorded with
    # week_url=None / week_titles=[] (request-asserted evidence, weaker
    # than page-extracted -- see fantasycalc_url docstring). Refuse to
    # start the API loop if the requested label is unparseable or empty:
    # a dataset without a validated week is worse than no dataset
    # (Rule 2 fail-closed).
    requested_week = _week_number_from_label(week_label)
    if requested_week is None:
        print("FATAL: --week-label %r is not parseable as 'Week N'; "
              "refusing to pull" % week_label, flush=True)
        sys.exit(1)

    # Representative combo URL (the validator only needs one -- all
    # combos share the same week). This is the exact URL
    # bsd.pull_fantasycalc fetches for that combo.
    rep_scoring, rep_teams, rep_qbs = (
        bsd.SCORINGS[0], bsd.TEAM_COUNTS[0], bsd.QB_COUNTS[0])
    canonical_url = fantasycalc_url(rep_scoring, rep_teams, rep_qbs)
    try:
        week_evidence = validate_week_consistency(
            canonical_url, None, requested_week)
    except RuntimeError as e:
        print("FATAL: %s -- cache untouched, manifest not re-stamped"
              % e, flush=True)
        sys.exit(1)
    print("week validated: %d (url=%s, titles=%s, requested=%s) [basis: "
          "request-asserted; API exposes no week-labeled page]" % (
        week_evidence["week"], week_evidence["week_url"],
        week_evidence["week_titles"], week_evidence["week_requested"]),
        flush=True)

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

    # Same payload shape as build_sources_dashboard.py --refresh-fc, plus
    # the JEG-87 week evidence so downstream consumers (fixture builders,
    # validators) can check `week` and `week_evidence` before using the
    # data (Rules 3 + 4). `url` is the exact API URL fetched for the
    # combo; there is no page title (API pull, not a page scrape).
    for scoring, teams, qbs in combos:
        key = "%s_%d_qb%d" % (scoring, teams, qbs)
        rows = pulled[key]
        bsd.save_cache("fantasycalc_%s" % key,
                       {"fetched_at": fetched_at, "rows": rows,
                        "url": fantasycalc_url(scoring, teams, qbs),
                        "week": week_evidence["week"],
                        "week_evidence": week_evidence,
                        "snapshot": {"week": week_label,
                                     "cadence": "weekly snapshot"}})
    bsd.save_cache("fantasycalc_snapshot",
                   {"week": week_label, "fetched_at": fetched_at,
                    "cadence": "weekly snapshot",
                    "url": canonical_url,
                    "week_evidence": week_evidence,
                    "combos": sorted(pulled),
                    "note": "Weekly snapshot tied to the NFL week, not a live read. "
                            "Week is request-asserted (--week-label): the FantasyCalc "
                            "API (/values/current) exposes no week-labeled page."})
    print("wrote %d combo caches + snapshot manifest (week %s)" % (
        len(pulled), week_label), flush=True)


if __name__ == "__main__":
    main()
