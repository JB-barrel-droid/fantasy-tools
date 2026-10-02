#!/usr/bin/env python3
"""NEW CBS trade-value-chart pull (repo replacement, stage 2).

Does NOT touch the goal-workspace pull (pull_cbs() inside
build_sources_dashboard.py) — that keeps running untouched until the repo
pipeline replaces it.

Auto-discovery: Dave Richard's weekly chart slug embeds the week number,
so we try week-N slug candidates newest-first and validate the
TableBuilder markup on each (the same markup the parser requires).

Usage:
  pull_cbs.py [--week N] [--write] [--url URL]
"""
import argparse
import json
import os
import re
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import fetch, nfl_week, REPO

SLUG = ("https://sportsfly.cbsistatic.com/fantasy/football/news/"
        "dave-richards-week-%d-trade-chart-and-rest-of-season-"
        "fantasy-football-rankings-help-you-win-now/")
TABLE_MARK = 'class="TableBuilder"'
TABLE_RE = re.compile(
    r"<h2>\s*(.*?)\s*</h2>\s*<table class=\"TableBuilder\">(.*?)</table>", re.S)


class DiscoveryFailed(RuntimeError):
    pass


def extract_week_from_url(url: str) -> int | None:
    """Extract week number from the CBS article URL slug.

    URL pattern: .../dave-richards-week-N-trade-chart-...
    Returns None if no week found.
    """
    m = re.search(r"dave-richards-week-(\d+)-", url)
    return int(m.group(1)) if m else None


def extract_week_from_title(title: str) -> int | None:
    """Extract week number from a headline / page title.

    Pattern: "Week N ..." (anywhere in the string, case-insensitive).
    Returns None if no week found.
    """
    m = re.search(r"\bweek\s+(\d+)\b", title, re.I)
    return int(m.group(1)) if m else None


def extract_page_headline(html: str) -> str | None:
    """Find the page headline / title from a CBS article HTML body.

    Tries <meta property="og:title">, then <title>, then the first <h1>.
    Returns the cleaned string or None if none are present.

    CBS's H2 table titles are position-only ("Quarterbacks", "Running backs"),
    so the week lives in the page headline — not the table titles.
    """
    for pattern in (
        r"<meta[^>]*property=[\"']og:title[\"'][^>]*content=[\"']([^\"']+)[\"']",
        r"<title[^>]*>(.*?)</title>",
        r"<h1[^>]*>(.*?)</h1>",
    ):
        m = re.search(pattern, html, re.S | re.I)
        if m:
            text = re.sub(r"<.*?>", "", m.group(1)).strip()
            if text:
                return text
    return None


def validate_week_consistency(url: str, headline: str | None,
                              requested_week: int | None) -> dict:
    """Validate that URL, page headline, and requested week all agree.

    Jeremy 2026-10-02: "We need to codify elements of the page such as the
    headline to the dataset, so that we do not have these errors, along with
    rules on how weeks get coded to datasets."

    Fail-closed: raises RuntimeError on any mismatch. Returns a dict with
    the validated week and the evidence (week_url, week_headline).
    """
    url_week = extract_week_from_url(url)
    headline_week = extract_week_from_title(headline) if headline else None

    if url_week is not None and headline_week is not None and url_week != headline_week:
        raise RuntimeError(
            "CBS URL week (%d) != page headline week (%d) "
            "(url=%s, headline=%r). Refusing to label dataset."
            % (url_week, headline_week, url, headline))

    validated = headline_week if headline_week is not None else url_week
    if requested_week is not None and validated is not None and requested_week != validated:
        raise RuntimeError(
            "CBS requested week (%d) != page week (%d) (url=%s, headline=%r). "
            "Page content does not match request; refusing to label dataset."
            % (requested_week, validated, url, headline))

    if validated is None:
        raise RuntimeError(
            "CBS: could not determine week from URL or page headline "
            "(url=%s, headline=%r). Refusing to label dataset without "
            "week evidence." % (url, headline))

    return {
        "week": validated,
        "week_url": url_week,
        "week_headline": headline_week,
        "week_requested": requested_week,
    }


def candidate_urls(week=None):
    week = week or nfl_week()
    return [SLUG % w for w in (week, week - 1, week - 2) if w >= 1]


def discover_url(week=None, fetch_fn=fetch):
    """First week-N slug (newest first) whose page carries the TableBuilder
    markup. Raises DiscoveryFailed when none resolve — never silently
    reuses a stale pinned URL."""
    tried = []
    for url in candidate_urls(week):
        st, html = fetch_fn(url)
        tried.append((url, st))
        if st == 200 and html and TABLE_MARK in html:
            return url
    raise DiscoveryFailed(
        "no CBS trade chart page found (tried: %s)"
        % [(u.rsplit("/", 2)[-2][:40], s) for u, s in tried])


def pull(url, fetch_fn=fetch):
    """Fetch + parse the article's position tables. Same table shape as the
    goal-workspace pull_cbs(): [{title, headers, rows}]. Raises on fetch
    failure or markup mismatch (fail closed).

    Returns (tables, headline) so the caller can validate the page headline
    week against the URL slug week (JEG-85)."""
    st, html = fetch_fn(url)
    if st != 200 or not html:
        raise RuntimeError("fetch failed: status=%r url=%s" % (st, url))
    if TABLE_MARK not in html:
        raise RuntimeError("CBS TableBuilder markup not found at %s" % url)
    tables = []
    for m in TABLE_RE.finditer(html):
        title = re.sub(r"<.*?>", "", m.group(1)).strip()
        body = m.group(2)
        headers = [re.sub(r"<.*?>", "", h).strip()
                   for h in re.findall(r"<th.*?>(.*?)</th>", body, re.S)]
        rows = []
        for tr in re.finditer(r"<tr.*?>(.*?)</tr>", body, re.S):
            cells = [re.sub(r"<.*?>", "", c).strip()
                     for c in re.findall(r"<td.*?>(.*?)</td>", tr.group(1), re.S)]
            # CBS tables have no rank column: first cell is the player name.
            # (An isdigit() filter here silently dropped every row.)
            if cells and cells[0].strip():
                rows.append(cells)
        tables.append({"title": title, "headers": headers, "rows": rows})
    if len(tables) < 4:
        raise RuntimeError("expected >=4 position tables, got %d at %s"
                           % (len(tables), url))
    headline = extract_page_headline(html)
    return tables, headline


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--week", type=int, default=None)
    ap.add_argument("--url", default=None,
                    help="explicit article URL (manual override; skips discovery)")
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()

    url = args.url or discover_url(args.week)
    print("url:", url, flush=True)
    tables, headline = pull(url)
    total_rows = sum(len(t["rows"]) for t in tables)
    print("tables: %d, rows: %d" % (len(tables), total_rows), flush=True)
    for t in tables:
        print("  %-28s %d rows" % (t["title"][:28], len(t["rows"])))
    if headline:
        print("headline: %s" % headline, flush=True)

    # JEG-85 / Jeremy 2026-10-02: codify the week from page elements.
    # The dataset must carry evidence of what week it represents,
    # derived from the page headline + URL slug, not just the request.
    week_info = validate_week_consistency(url, headline, args.week)
    print("week validated: %d (url=%s, headline=%s, requested=%s)" % (
        week_info["week"], week_info["week_url"],
        week_info["week_headline"], week_info["week_requested"]), flush=True)

    if args.write:
        outdir = os.path.join(REPO, "ops", "watchdog", "pulls")
        os.makedirs(outdir, exist_ok=True)
        outp = os.path.join(outdir, "cbs-%s.json" % date.today().isoformat())
        with open(outp, "w") as f:
            json.dump({"url": url,
                       "fetched_at": date.today().isoformat(),
                       "week": week_info["week"],
                       "week_evidence": week_info,
                       "tables": tables}, f)
        print("wrote", outp)


if __name__ == "__main__":
    main()
