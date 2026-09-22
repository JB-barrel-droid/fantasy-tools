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
    failure or markup mismatch (fail closed)."""
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
            if cells and cells[0].strip().isdigit():
                rows.append(cells)
        tables.append({"title": title, "headers": headers, "rows": rows})
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
        outp = os.path.join(outdir, "cbs-%s.json" % date.today().isoformat())
        with open(outp, "w") as f:
            json.dump({"url": url, "fetched_at": date.today().isoformat(),
                       "tables": tables}, f)
        print("wrote", outp)


if __name__ == "__main__":
    main()
