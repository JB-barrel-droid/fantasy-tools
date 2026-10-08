#!/usr/bin/env python3
"""NEW CBS trade-value-chart pull (repo replacement, stage 2).

Does NOT touch the goal-workspace pull (pull_cbs() inside
build_sources_dashboard.py) -- that keeps running untouched until the repo
pipeline replaces it.

Discovery (rewritten 2026-10-08, GAP-CBS-DISCOVERY-SLUG): Dave Richard's
slug changes from week to week (week 1 "fantasy-football-2026-week-1-trade-
chart-...", week 3 "trade-chart-fantasy-football-buy-sell-week-3-dave-
richard", week 4 "dave-richards-week-4-trade-chart-...", week 5 "dave-
richards-2026-week-5-trade-chart"). Guessing one slug template found the
Week 4 article for Week 5, so Week 5 was never ingested. Discovery now reads
CBS's own listings (author page, fantasy football hub, fantasy news sitemap),
takes every trade-chart link, and accepts a page only when its headline says
the requested week and its TableBuilder tables parse. A small LLM may
nominate a link when that finds nothing (article_discovery.llm_pick); its
pick goes through the same page checks.

Usage:
  pull_cbs.py [--week N] [--write] [--url URL]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import content_week, fetch, REPO
import article_discovery as ad

CBS = "https://www.cbssports.com"
# Listing pages, most specific first. Each is an independent path: one
# failing (layout change, 404) does not stop discovery.
LISTINGS = (
    ("author page", CBS + "/writers/dave-richard/", "html"),
    ("fantasy football hub", CBS + "/fantasy/football/", "html"),
    ("fantasy news sitemap", CBS + "/news-fantasy-sitemap.xml", "sitemap"),
)
# Known slug shapes, tried as direct guesses after the listings' links.
SLUG_GUESSES = (
    CBS + "/fantasy/football/news/dave-richards-2026-week-%d-trade-chart/",
    CBS + "/fantasy/football/news/dave-richards-week-%d-trade-chart-and-rest-of-"
          "season-fantasy-football-rankings-help-you-win-now/",
)
# The week-4-era template, kept only for importers (tests/test_source_probe.py
# on feat/refresh-cadence asserts it is www, not the 60-day sportsfly CDN).
# Discovery does not rely on it.
SLUG = SLUG_GUESSES[1]
NEWS_PATH = "/fantasy/football/news/"
TABLE_MARK = 'class="TableBuilder"'
TABLE_RE = re.compile(
    r"<h2>\s*(.*?)\s*</h2>\s*<table class=\"TableBuilder\">(.*?)</table>", re.S)
_CHART_SLUG_RE = re.compile(r"trade-(?:value-)?charts?", re.I)
_CHART_TEXT_RE = re.compile(r"trade (?:value )?charts?", re.I)


class DiscoveryFailed(RuntimeError):
    """No page for the requested week passed the checks. `quiet` (the
    ingest's "not published yet" skip) only when at least one listing was
    read; when none could be read, discovery could not look at all."""

    def __init__(self, msg, quiet=True, newest_week=None):
        super().__init__(msg)
        self.quiet = quiet
        self.newest_week = newest_week


def extract_week_from_url(url: str) -> int | None:
    """Week number in the article URL slug ("...-week-N-..."), or None.

    Any slug shape (the 2026 slugs differ every week); the page headline
    stays the authority (validate_week_consistency). Non-CBS URLs -> None.
    """
    if not re.match(r"https?://[^/]*(cbssports\.com|cbsistatic\.com)/", url or ""):
        return None
    return ad.week_in_slug(url)


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
        # og:title with double-quoted content (may contain apostrophes,
        # e.g. "Dave Richard's Week 4 Trade Chart ..."), then single-quoted.
        r'<meta[^>]*property=["\']og:title["\'][^>]*content="([^"]+)"',
        r"<meta[^>]*property=[\"']og:title[\"'][^>]*content='([^']+)'",
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


def is_chart_link(url, text):
    """A CBS fantasy football news link that names a trade (value) chart in
    its slug or its link text / headline."""
    if NEWS_PATH not in url:
        return False
    slug = url.split(NEWS_PATH, 1)[1]
    return bool(_CHART_SLUG_RE.search(slug) or _CHART_TEXT_RE.search(text or ""))


def parse_tables(html):
    """The article's position tables: [{title, headers, rows}]."""
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
    return tables


def check_article(url, week, fetch_fn=fetch):
    """None when `url` is the week-`week` trade chart (live page, headline
    names a trade chart for exactly that week, >= 4 TableBuilder tables
    parse, slug week agrees if it has one); else the reason it is not."""
    st, html = fetch_fn(url)
    if st != 200 or not html:
        return "status=%r" % (st,)
    if TABLE_MARK not in html:
        return "no TableBuilder tables"
    headline = extract_page_headline(html)
    if not headline or not _CHART_TEXT_RE.search(headline):
        return "headline is not a trade chart: %r" % (headline,)
    try:
        info = validate_week_consistency(url, headline, week)
    except RuntimeError as e:
        return str(e)
    if info["week_headline"] != week:
        return "headline has no week: %r" % (headline,)
    if len(parse_tables(html)) < 4:
        return "fewer than 4 position tables"
    return None


def _read_listings(fetch_fn, listings=LISTINGS):
    links, read, failed = [], [], []
    for label, url, kind in listings:
        st, body = fetch_fn(url)
        if st != 200 or not body:
            failed.append("%s status=%r" % (label, st))
            continue
        got = (ad.sitemap_entries(body) if kind == "sitemap"
               else ad.links_from_html(body, url))
        got = [(u, t) for u, t in got if NEWS_PATH in u]
        read.append("%s (%d football news links)" % (label, len(got)))
        links.extend(got)
    return links, read, failed


def discover_url(week=None, fetch_fn=fetch, llm_fn=None, listings=LISTINGS):
    """URL of Dave Richard's Week-`week` trade chart, verified on the page.

    1. Every trade-chart link on CBS's listings (author page, fantasy hub,
       fantasy news sitemap) plus the known slug shapes, links advertising
       week N first; links advertising another week are never tried.
    2. If none passes check_article, the LLM fallback (llm_fn, default
       article_discovery.llm_pick: a no-op without ANTHROPIC_API_KEY)
       nominates one listing link, which must pass check_article too.

    Raises DiscoveryFailed: quiet (not published yet) when listings were
    read but nothing passed; loud (quiet=False) when no listing could be read.
    Never falls back to an older week.
    """
    week = week or content_week()
    links, read, failed = _read_listings(fetch_fn, listings)
    guesses = [(g % week, "") for g in SLUG_GUESSES]
    ranked, newest_older = ad.rank_candidates(links + guesses, week, is_chart_link)
    tried = {}
    for url in ranked:
        why = check_article(url, week, fetch_fn)
        tried[ad.url_key(url)] = why
        if why is None:
            print("[cbs] discovered week %d chart: %s" % (week, url), flush=True)
            return url

    if read:
        pool = [(u, t) for u, t in links if ad.url_key(u) not in tried]
        pick = (llm_fn or (lambda w, ls: ad.llm_pick("CBS Sports (Dave Richard)", w, ls)))(week, pool)
        if pick:
            why = check_article(pick, week, fetch_fn)
            print("[cbs] LLM fallback nominated %s: %s" % (
                pick, "accepted" if why is None else "rejected (%s)" % why), flush=True)
            if why is None:
                return pick
            tried[ad.url_key(pick)] = "LLM pick: " + why

    detail = "listings read: %s; unreadable: %s; candidates tried: %s" % (
        read or "none", failed or "none",
        ["%s -> %s" % (k.rsplit("/", 1)[-1][:50], v) for k, v in tried.items()] or "none")
    if not read:
        raise DiscoveryFailed("CBS discovery could not read any listing (%s)" % detail,
                              quiet=False)
    raise DiscoveryFailed(
        "no CBS week %d trade chart found (newest older week seen: %s; %s)"
        % (week, newest_older, detail), quiet=True, newest_week=newest_older)


def page_week(url, fetch_fn=fetch):
    """Week of the article at `url`: its slug week, or (slug without a
    week) its headline week. For the ingest's exact-week gate."""
    w = extract_week_from_url(url)
    if w is not None or not re.match(r"https?://[^/]*cbssports\.com/", url or ""):
        return w
    st, html = fetch_fn(url)
    return extract_week_from_title(extract_page_headline(html or "") or "")


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
    tables = parse_tables(html)
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
