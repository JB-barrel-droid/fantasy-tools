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
import urllib.request
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import fetch, nfl_week, today_ct, REPO

SECTION_SLUG = "trade-value-chart-week-%d-ros-rankings"
# NOTE (2026-10-02): USA Today changed the article slug between week 3 and
# week 4 -- "fantasy-football-trade-value-chart-week-N-ros-rankings" became
# "fantasy-trade-value-chart-week-N-ros-rankings". Matching on the common
# "trade-value-chart-week-N-ros-rankings" substring covers both, so a slug
# rename can never again make discovery silently miss the current article
# while the sitemap still lists last week's (which then fails closed as a
# "stale article"). extract_week_from_url already matches both patterns.
# NOTE (2026-10-07): the week-5 article slug is
# "fantasy-trade-value-charts-week-5-ros-rankings" -- "chart" became "charts".
# The singular-only match silently missed it (and fell back to the stale
# week-4 article), so the slug match accepts both forms.
SLUG_RE = r"trade-value-charts?-week-%d-ros-rankings"
SITEMAP_INDEX = "https://www.usatoday.com/web-sitemap-index.xml"
SITEMAP_MONTH = "https://www.gannett-cdn.com/sitemaps/USAT/web/web-sitemap-%04d-%02d.xml"
TABLE_MARK = "gnt_ar_b_tbl"


class DiscoveryFailed(RuntimeError):
    """No article for the week (quiet "not published yet" skip in the
    ingest wrapper)."""
    quiet = True


class SitemapUnavailable(DiscoveryFailed):
    """The sitemap itself could not be read (non-200 or truncated body).

    Still a DiscoveryFailed (discovery fails closed, never returns a partial
    list), but NOT quiet: discovery could not look, so the ingest wrapper
    must fail loudly instead of reporting "not published yet"."""
    quiet = False


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
    raise SitemapUnavailable(
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
        slug_re = re.compile(SLUG_RE % wk)
        for dy, dm in ((today.year, today.month),
                       *([ (today.year, today.month - 1) ] if today.month > 1
                         else [(today.year - 1, 12)])):
            urls = sitemap_urls_for_month(dy, dm, fetch_fn)
            tried.append((dy, dm, len(urls)))
            hits = [u for u in urls if slug_re.search(u)]
            if hits:
                # Newest article wins (sitemap order is chronological).
                return hits[-1]
    raise DiscoveryFailed(
        "no USA Today trade-value-chart article found for week %d "
        "(tried sitemaps: %s)" % (week, tried))


def extract_week_from_url(url: str) -> int | None:
    """Extract week number from the USA Today article URL slug.

    URL pattern: .../fantasy-football-trade-value-chart-week-N-ros-rankings/...
    Returns None if no week found.
    """
    m = re.search(r"trade-value-charts?-week-(\d+)-", url)
    return int(m.group(1)) if m else None


def extract_week_from_title(title: str) -> int | None:
    """Extract week number from a table title.

    Title pattern: "Week N <position> trade value chart"
    e.g. "Week 4 wide receiver trade value chart" -> 4
    Returns None if no week found.
    """
    m = re.search(r"\bweek\s+(\d+)\b", title, re.I)
    return int(m.group(1)) if m else None


def validate_week_consistency(url: str, tables: list[dict], requested_week: int | None) -> dict:
    """Validate that URL, table titles, and requested week all agree.

    Jeremy 2026-10-02: "We need to codify elements of the page such as the
    headline to the dataset, so that we do not have these errors, along with
    rules on how weeks get coded to datasets."

    Fail-closed: raises RuntimeError on any mismatch. Returns a dict with
    the validated week and the evidence (url_week, title_weeks).
    """
    url_week = extract_week_from_url(url)
    title_weeks = set()
    for t in tables:
        w = extract_week_from_title(t.get("title", ""))
        if w is not None:
            title_weeks.add(w)

    # All table titles should agree on the week
    if len(title_weeks) > 1:
        raise RuntimeError(
            "USA Today table titles disagree on week: %s (url=%s). "
            "Refusing to label dataset." % (sorted(title_weeks), url))
    title_week = next(iter(title_weeks)) if title_weeks else None

    # URL week and title week should agree
    if url_week is not None and title_week is not None and url_week != title_week:
        raise RuntimeError(
            "USA Today URL week (%d) != table title week (%d) (url=%s). "
            "Refusing to label dataset." % (url_week, title_week, url))

    # Requested week should match what we found
    validated = title_week if title_week is not None else url_week
    if requested_week is not None and validated is not None and requested_week != validated:
        raise RuntimeError(
            "USA Today requested week (%d) != page week (%d) (url=%s). "
            "Page content does not match request; refusing to label dataset."
            % (requested_week, validated, url))

    if validated is None:
        raise RuntimeError(
            "USA Today: could not determine week from URL or table titles "
            "(url=%s). Refusing to label dataset without week evidence." % url)

    return {
        "week": validated,
        "week_url": url_week,
        "week_titles": sorted(title_weeks),
        "week_requested": requested_week,
    }


BLOCK_STATUSES = (401, 402, 403, 429)
RELAY_FUNCTION = "usatoday-fetch"


def fetch_via_relay(url, timeout=90):
    """GET `url` through the Supabase Edge Function `usatoday-fetch`.

    GitHub-hosted runner IPs are walled (402) by usatoday.com; Supabase's
    egress is not (verified 2026-10-07). The relay returns the upstream
    status verbatim, so every downstream check (status, table markup, exact
    week gate) is unchanged. Returns (status, body) or None when the relay
    is not configured / unreachable."""
    base = os.environ.get("SUPABASE_URL", "").rstrip("/")
    key = os.environ.get("SUPABASE_SERVICE_KEY", "")
    if not base or not key:
        return None
    req = urllib.request.Request(
        "%s/functions/v1/%s" % (base, RELAY_FUNCTION),
        data=json.dumps({"url": url}).encode(), method="POST",
        headers={"Content-Type": "application/json",
                 "Authorization": "Bearer " + key, "apikey": key})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            d = json.loads(r.read().decode("utf-8", "replace"))
    except Exception as e:  # noqa: BLE001 - any relay failure = no relay
        print("[usatoday] relay unavailable: %s" % e, file=sys.stderr, flush=True)
        return None
    if not isinstance(d, dict) or "status" not in d:
        return None
    return d["status"], d.get("body") or ""


def fetch_via_firecrawl(url, timeout=90):
    """Optional paid fallback: active only when FIRECRAWL_API_KEY is set.
    Returns (status, rawHtml) or None. UNVERIFIED in CI (no secret yet)."""
    key = os.environ.get("FIRECRAWL_API_KEY", "")
    if not key:
        return None
    req = urllib.request.Request(
        "https://api.firecrawl.dev/v1/scrape",
        data=json.dumps({"url": url, "formats": ["rawHtml"]}).encode(),
        method="POST",
        headers={"Content-Type": "application/json",
                 "Authorization": "Bearer " + key})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            d = json.loads(r.read().decode("utf-8", "replace"))
    except Exception as e:  # noqa: BLE001
        print("[usatoday] firecrawl unavailable: %s" % e, file=sys.stderr, flush=True)
        return None
    html = ((d or {}).get("data") or {}).get("rawHtml")
    return (200, html) if html else None


def fetch_article(url, fetch_fn=fetch):
    """Direct fetch first; on a bot-wall status fall back to the Supabase
    relay, then Firecrawl (only if its secret exists). A fallback's non-200
    never masks the original block: the caller still sees the blocked status
    and raises SOURCE_BLOCKED."""
    st, body = fetch_fn(url)
    if st not in BLOCK_STATUSES:
        return st, body
    for name, fb in (("supabase relay", fetch_via_relay),
                     ("firecrawl", fetch_via_firecrawl)):
        got = fb(url)
        if got and got[0] == 200 and got[1]:
            print("[usatoday] direct fetch blocked (%s); fetched via %s"
                  % (st, name), flush=True)
            return got
    return st, body


def pull(url, fetch_fn=fetch_article):
    """Fetch + parse the article's position tables. Same table shape as the
    goal-workspace pull_usatoday(): [{title, headers, rows}]. Raises on
    fetch failure or markup mismatch (fail closed)."""
    st, html = fetch_fn(url)
    if st in (401, 402, 403, 429):
        # 2026-10-06: usatoday.com answers GitHub-hosted runners with 402
        # "Access Restricted" (bot wall); the gannett-cdn sitemaps still 200.
        raise RuntimeError("SOURCE_BLOCKED: fetch refused: status=%r url=%s"
                           % (st, url))
    if st != 200 or not html:
        raise RuntimeError("fetch failed: status=%r url=%s" % (st, url))
    if TABLE_MARK not in html:
        raise RuntimeError("USA Today table markup not found at %s" % url)
    tables = []
    # H2 markup varies by article: older use <h2 class=gnt_ar_b_h2>,
    # Week 4 uses <h2 class=gnt_ar_b_mt>. Accept any <h2 ...>.
    for m in re.finditer(
            r"<h2[^>]*>(.*?)</h2>.*?"
            r"<table class=gnt_ar_b_tbl>(.*?)</table>", html, re.S):
        title, body = m.group(1), m.group(2)
        headers = re.findall(r"<th>(.*?)</th>", body)
        rows = []
        for tr in re.finditer(r"<tr>(.*?)</tr>", body, re.S):
            cells = re.findall(r"<td>(.*?)</td>", tr.group(1))
            if cells and cells[0].strip().isdigit():
                rows.append([re.sub(r"<.*?>", "", c).strip() for c in cells])
        headers = [re.sub(r"<.*?>", "", h).strip() for h in headers]
        title = _clean_title_position(title, headers)
        tables.append({"title": title, "headers": headers, "rows": rows})
    if len(tables) < 4:
        raise RuntimeError("expected >=4 position tables, got %d at %s"
                           % (len(tables), url))
    return tables


def _clean_title_position(title, headers):
    """Infer the QB table when a generic section heading pairs with it.

    The h2->table regex is lazy from the FIRST h2, so the section header
    ("Week N fantasy trade charts") can pair with the QB table instead of
    its own h2. Only the QB table carries 1QB/6-TD/SFLEX columns, so the
    position is inferred from the header signature when the title names
    no position (seen live 2026-09-29).
    """
    title = re.sub(r"<.*?>", "", title).strip()
    if not re.search(
            r"quarterbacks?|\bqbs?\b|running backs?|wide receivers?|"
            r"tight ends?", title, re.I):
        hl = [h.lower().replace(" ", "") for h in headers]
        if any("1qb" in h for h in hl):
            title = "Quarterback Trade Value Chart"
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
    tables = pull(url)
    total_rows = sum(len(t["rows"]) for t in tables)
    print("tables: %d, rows: %d" % (len(tables), total_rows), flush=True)
    for t in tables:
        print("  %-28s %d rows" % (t["title"][:28], len(t["rows"])))

    # JEG-77 / Jeremy 2026-10-02: codify the week from page elements.
    # The dataset must carry evidence of what week it represents,
    # derived from the page headline/titles, not just the request.
    week_info = validate_week_consistency(url, tables, args.week)
    print("week validated: %d (url=%s, titles=%s, requested=%s)" % (
        week_info["week"], week_info["week_url"],
        week_info["week_titles"], week_info["week_requested"]), flush=True)

    if args.write:
        outdir = os.path.join(REPO, "ops", "watchdog", "pulls")
        os.makedirs(outdir, exist_ok=True)
        outp = os.path.join(outdir, "usatoday-%s.json" % date.today().isoformat())
        with open(outp, "w") as f:
            json.dump({"url": url, "fetched_at": date.today().isoformat(),
                       "week": week_info["week"],
                       "week_evidence": week_info,
                       "tables": tables}, f)
        print("wrote", outp)


if __name__ == "__main__":
    main()
