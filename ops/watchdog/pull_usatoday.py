#!/usr/bin/env python3
"""NEW USA Today trade-value-chart pull (repo replacement, stage 2).

Does NOT touch the goal-workspace pull (pull_usatoday() inside
build_sources_dashboard.py) — that keeps running untouched until the repo
pipeline replaces it.

Auto-discovery: USA Today article IDs are opaque, so the week's article URL
cannot be guessed. Instead we read USA Today's own monthly web sitemap
(robots.txt -> web-sitemap-index.xml -> web-sitemap-YYYY-MM.xml) and grep
for the week's chart slug, like pull_fantasypros_chart.py's candidate_urls
pattern but driven by the sitemap rather than a URL template.

Usage:
  pull_usatoday.py [--week N] [--write] [--url URL]

--write stores ops/watchdog/pulls/usatoday-<date>.json (repo-local,
provisional — NOT wired into any live path). Default is a dry run that
prints the discovered URL and table counts.
"""
import argparse
import json
import os
import re
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import fetch, nfl_week, today_ct, REPO

SECTION_SLUG = "fantasy-football-trade-value-chart-week-%d-ros-rankings"
SITEMAP_INDEX = "https://www.usatoday.com/web-sitemap-index.xml"
SITEMAP_MONTH = "https://www.gannett-cdn.com/sitemaps/USAT/web/web-sitemap-%04d-%02d.xml"
TABLE_MARK = "gnt_ar_b_tbl"
POSITION_TITLE_PATTERNS = (
    r"\bquarterbacks?\b", r"\bqbs?\b",
    r"\brunning backs?\b", r"\brbs?\b",
    r"\bwide receivers?\b", r"\bwrs?\b",
    r"\btight ends?\b", r"\btes?\b",
)


class DiscoveryFailed(RuntimeError):
    pass


def table_title(title, headers):
    """Normalize table title enough for the ingestion validator.

    USA Today's Week 3 page changed the QB heading to the generic
    "Week 3 fantasy trade charts"; the position is still unambiguous from
    QB-only headers. Keep fail-closed behavior for anything not inferable.
    """
    clean = re.sub(r"<.*?>", "", title or "").strip()
    if any(re.search(pattern, clean, re.IGNORECASE) for pattern in POSITION_TITLE_PATTERNS):
        return clean
    header_text = " ".join(re.sub(r"<.*?>", "", h or "").strip() for h in headers)
    if re.search(r"\b1QB\b", header_text, re.IGNORECASE) and re.search(r"\bSFLEX\b", header_text, re.IGNORECASE):
        return f"Quarterback {clean}".strip()
    return clean


def sitemap_urls_for_month(year, month, fetch_fn=fetch):
    """All <loc> URLs in one monthly web sitemap.

    Fail-closed on truncation: a sitemap body that does not end with the
    closing </urlset> tag is a truncated fetch, not a short month. We retry
    once, then raise DiscoveryFailed -- a truncated sitemap can silently
    drop the current week's article while still containing last week's,
    which would make discovery "succeed" on stale data. Never returns a
    partial URL list.
    """
    url = SITEMAP_MONTH % (year, month)
    last_err = None
    for attempt in (1, 2):
        st, body = fetch_fn(url)
        if st == 200 and body and "</urlset>" in body:
            return re.findall(r"<loc>([^<]+)</loc>", body)
        last_err = "status=%r len=%d truncated=%s" % (
            st, len(body or ""),
            bool(body) and "</urlset>" not in body)
    raise DiscoveryFailed(
        "USA Today sitemap fetch failed/truncated for %04d-%02d (%s); "
        "refusing to discover from a partial sitemap" % (year, month, last_err))


def discover_url(week=None, fetch_fn=fetch):
    """Find this week's USA Today trade-value-chart article URL.

    Searches the current and previous month's web sitemaps for the
    week-N slug, newest week first. Raises DiscoveryFailed (fail closed)
    when nothing is found — never silently reuses a stale pinned URL.
    """
    week = week or nfl_week()
    today = today_ct()
    tried = []
    for wk in (week, week - 1):
        if wk < 1:
            continue
        slug = SECTION_SLUG % wk
        for dy, dm in ((today.year, today.month),
                       *([ (today.year, today.month - 1) ] if today.month > 1
                         else [(today.year - 1, 12)])):
            urls = sitemap_urls_for_month(dy, dm, fetch_fn)
            tried.append((dy, dm, len(urls)))
            hits = [u for u in urls if slug in u]
            if hits:
                # Newest article wins (sitemap order is chronological).
                return hits[-1]
    raise DiscoveryFailed(
        "no USA Today trade-value-chart article found for week %d "
        "(tried sitemaps: %s)" % (week, tried))


def pull(url, fetch_fn=fetch):
    """Fetch + parse the article's position tables. Same table shape as the
    goal-workspace pull_usatoday(): [{title, headers, rows}]. Raises on
    fetch failure or markup mismatch (fail closed)."""
    st, html = fetch_fn(url)
    if st != 200 or not html:
        raise RuntimeError("fetch failed: status=%r url=%s" % (st, url))
    if TABLE_MARK not in html:
        raise RuntimeError("USA Today table markup not found at %s" % url)
    tables = []
    for m in re.finditer(
            r"<h2 class=gnt_ar_b_h2>(.*?)</h2>.*?"
            r"<table class=gnt_ar_b_tbl>(.*?)</table>", html, re.S):
        title, body = m.group(1), m.group(2)
        headers = re.findall(r"<th>(.*?)</th>", body)
        rows = []
        for tr in re.finditer(r"<tr>(.*?)</tr>", body, re.S):
            cells = re.findall(r"<td>(.*?)</td>", tr.group(1))
            if cells and cells[0].strip().isdigit():
                rows.append([re.sub(r"<.*?>", "", c).strip() for c in cells])
        clean_headers = [re.sub(r"<.*?>", "", h).strip() for h in headers]
        tables.append({"title": table_title(title, clean_headers),
                       "headers": clean_headers,
                       "rows": rows})
    if len(tables) < 4:
        raise RuntimeError("expected >=4 position tables, got %d at %s"
                           % (len(tables), url))
    return tables


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--week", type=int, default=None)
    ap.add_argument("--url", default=None,
                    help="explicit article URL (manual override; skips discovery)")
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()

    url = args.url or discover_url(args.week)
    print("url:", url, flush=True)
    tables = pull(url)
    total_rows = sum(len(t["rows"]) for t in tables)
    print("tables: %d, rows: %d" % (len(tables), total_rows), flush=True)
    for t in tables:
        print("  %-28s %d rows" % (t["title"][:28], len(t["rows"])))
    if args.write:
        outdir = os.path.join(REPO, "ops", "watchdog", "pulls")
        os.makedirs(outdir, exist_ok=True)
        outp = os.path.join(outdir, "usatoday-%s.json" % date.today().isoformat())
        with open(outp, "w") as f:
            json.dump({"url": url, "fetched_at": date.today().isoformat(),
                       "tables": tables}, f)
        print("wrote", outp)


if __name__ == "__main__":
    main()
