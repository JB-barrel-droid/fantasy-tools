#!/usr/bin/env python3
"""NEW FantasyPros trade-value-chart pull (repo replacement, stage 2).

Sits alongside ops/watchdog/pull_usatoday.py and pull_cbs.py — the only
existing repo puller that touches a FantasyPros article is the goal-workspace
lottery/bin/pull_fantasypros_chart.py (outside this repo). The CSVs in
weekly_vegas/data/fantasypros/ are its output.

JEG-86 / Jeremy 2026-10-02 directive: "We need to codify elements of the page
such as the headline to the dataset, so that we do not have these errors,
along with rules on how weeks get coded to datasets." The week on the dataset
must come from the page itself (URL slug + headline/H1), not from the request.

Usage:
  pull_fantasypros.py [--week N] [--write] [--url URL]

--write stores ops/watchdog/pulls/fantasypros-<date>.json (repo-local,
provisional — NOT wired into any live path). Default is a dry run that
prints the discovered URL, headline week, and table counts.
"""
import argparse
import json
import os
import re
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import fetch, nfl_week, REPO

# Auto-discovery: FantasyPros trade-value-chart article slug embeds the week.
# Candidate template (newest week first); discovery walks week N, N-1, N-2
# and returns the first whose page carries a parseable H1/title AND that
# headline's week matches the URL's week. Discovery never silently reuses
# a stale pinned URL.
SECTION_SLUG = ("https://www.fantasypros.com/2026/09/"
                "fantasy-football-trade-value-chart-week-%d-2026/")


class DiscoveryFailed(RuntimeError):
    pass


def candidate_urls(week=None):
    week = week or nfl_week()
    return [SECTION_SLUG % w for w in (week, week - 1, week - 2) if w >= 1]


def discover_url(week=None, fetch_fn=fetch):
    """First week-N slug (newest first) whose page is live AND whose page
    headline week matches the slug week. Raises DiscoveryFailed when none
    resolve — never silently reuses a stale pinned URL.

    We require URL week == title week here too (not just on the parsed
    payload) so a slug mismatch is caught at discovery, not after parsing.
    """
    week = week or nfl_week()
    tried = []
    for w in (week, week - 1, week - 2):
        if w < 1:
            continue
        url = SECTION_SLUG % w
        st, html = fetch_fn(url)
        tried.append((url, st))
        if st != 200 or not html:
            continue
        title = _extract_title_text(html)
        if title is None:
            continue
        title_week = extract_week_from_title(title)
        url_week = extract_week_from_url(url)
        if title_week is None or url_week is None:
            continue
        if title_week != url_week:
            # Slug said week-A, headline said week-B: treat as a stale page
            # (same class of miss as the 2026-10-02 USA Today incident).
            continue
        return url
    raise DiscoveryFailed(
        "no FantasyPros trade chart page found (tried: %s)"
        % [(u.rsplit("/", 2)[-2][:60], s) for u, s in tried])


def _extract_title_text(html):
    """Return the trimmed <title>...</title> text, or the <h1>...</h1> text
    if <title> is absent. Returns None if neither is found.

    Page-title is the more durable evidence: the article publishes with
    "Week N" in the <title> even when the H1 is more verbose. Falls back
    to H1 so a CMS rewrite that drops the <title> still leaves us
    fail-closed evidence instead of silently accepting a non-week page.
    """
    m = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
    if m:
        t = re.sub(r"<[^>]+>", "", m.group(1)).strip()
        if t:
            return t
    m = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.I | re.S)
    if m:
        t = re.sub(r"<[^>]+>", "", m.group(1)).strip()
        if t:
            return t
    return None


def extract_week_from_url(url: str) -> int | None:
    """Extract week number from the FantasyPros article URL slug.

    URL pattern: .../fantasy-football-trade-value-chart-week-N-2026/
    Returns None if no week found.
    """
    m = re.search(r"trade-value-chart-week-(\d+)-", url)
    return int(m.group(1)) if m else None


def extract_week_from_title(title: str) -> int | None:
    """Extract week number from the article headline / H1 / page title.

    Title pattern: "Week N fantasy football trade value chart" (or any text
    containing "Week N" as a standalone word). e.g. "Week 4 fantasy
    football trade value chart" -> 4. Returns None if no week found.
    """
    m = re.search(r"\bweek\s+(\d+)\b", title, re.I)
    return int(m.group(1)) if m else None


def validate_week_consistency(url: str, title: str,
                              requested_week: int | None) -> dict:
    """Validate that URL week, headline week, and requested week all agree.

    JEG-86 / Jeremy 2026-10-02: the dataset must carry evidence of what week
    it represents, derived from the page headline/title, not just the
    request. Fail-closed: raises RuntimeError on any mismatch. Returns a
    dict with the validated week and the evidence.
    """
    url_week = extract_week_from_url(url)
    title_week = extract_week_from_title(title) if title else None

    if url_week is None:
        raise RuntimeError(
            "FantasyPros URL has no week slug (url=%s). "
            "Refusing to label dataset without week evidence." % url)
    if title_week is None:
        raise RuntimeError(
            "FantasyPros page title contains no 'Week N' (url=%s, "
            "title=%r). Refusing to label dataset without week evidence."
            % (url, (title or "")[:80]))
    if url_week != title_week:
        raise RuntimeError(
            "FantasyPros URL week (%d) != page title week (%d) (url=%s, "
            "title=%r). Page content does not match slug; refusing to label "
            "dataset." % (url_week, title_week, url, (title or "")[:80]))
    if requested_week is not None and url_week != requested_week:
        raise RuntimeError(
            "FantasyPros requested week (%d) != page week (%d) (url=%s). "
            "Page content does not match request; refusing to label dataset."
            % (requested_week, url_week, url))

    return {
        "week": url_week,
        "week_url": url_week,
        "week_titles": [title_week],
        "week_requested": requested_week,
        "title": title,
    }


def pull(url, fetch_fn=fetch):
    """Fetch + extract the page headline (URL slug + <title>/<h1> evidence).

    The FantasyPros chart page embeds its player-by-player values as a
    structured <table>; this stub returns the page-level week evidence
    that JEG-86 demands. The downstream consumer (FantasyPros saver) reads
    the existing fantasypros_trade_chart.csv — JEG-86 is about the week
    label on that dataset, not about re-implementing the table parser
    that already lives in lottery/bin/pull_fantasypros_chart.py.
    """
    st, html = fetch_fn(url)
    if st != 200 or not html:
        raise RuntimeError("fetch failed: status=%r url=%s" % (st, url))
    title = _extract_title_text(html)
    if title is None:
        raise RuntimeError(
            "FantasyPros page has no <title> or <h1> at %s" % url)
    return title


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--week", type=int, default=None)
    ap.add_argument("--url", default=None,
                    help="explicit article URL (manual override; skips discovery)")
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()

    url = args.url or discover_url(args.week)
    print("url:", url, flush=True)
    title = pull(url)
    print("title:", title, flush=True)

    # JEG-86 / Jeremy 2026-10-02: codify the week from page elements.
    # The dataset must carry evidence of what week it represents,
    # derived from the page headline/title, not just the request.
    week_info = validate_week_consistency(url, title, args.week)
    print("week validated: %d (url=%d, titles=%s, requested=%s)" % (
        week_info["week"], week_info["week_url"],
        week_info["week_titles"], week_info["week_requested"]), flush=True)

    if args.write:
        outdir = os.path.join(REPO, "ops", "watchdog", "pulls")
        os.makedirs(outdir, exist_ok=True)
        outp = os.path.join(outdir, "fantasypros-%s.json" % date.today().isoformat())
        with open(outp, "w") as f:
            json.dump({"url": url, "fetched_at": date.today().isoformat(),
                       "week": week_info["week"],
                       "week_evidence": week_info,
                       "title": title}, f)
        print("wrote", outp)


if __name__ == "__main__":
    main()