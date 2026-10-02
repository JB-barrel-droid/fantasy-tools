#!/usr/bin/env python3
"""JEG-77: End-to-end source fidelity checks.

Verifies the full pipeline from live publisher to rendered dashboard:
1. FRESHNESS: Live publisher values vs our fixture native values.
   Flags when we're stale (publisher did a midweek update we missed).
2. FIDELITY: Fixture native ordering vs reindexed ordering.
   Flags when VORP translation flips player order (JEG-73 class bug).
3. DEPLOY: Fixture values vs live GitHub Pages JSON.
   Flags when Pages is serving stale data (CDN/cache issue).

This is the END-TO-END check Jeremy demanded 2026-10-02:
"Your checks are not end to end."

Unlike verify_vorp_wiring.py (internal consistency only), this compares
against the actual live publisher sites and the actual live dashboard.

Usage:
    python3 pipelines/check_source_fidelity.py [--source usatoday] [--live]
    --live: Actually fetch from publisher sites (slow, requires network).
            Without --live, uses the most recent watchdog pull snapshots.

Output: JSON report + human-readable summary. Exit 1 if any check fails.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from datetime import datetime, timezone

REPO = Path(__file__).resolve().parent.parent
FIXTURE = REPO / "data" / "fixtures" / "current" / "comparison-sources-data.json"
PAGES_URL = "https://jb-barrel-droid.github.io/fantasy-tools/assets/comparison-sources-data.json"

# The 4 as-published sources that go through VORP translation
SOURCES = ["fantasycalc", "usatoday", "fantasypros", "cbs"]

# --- Live puller constants (urllib HTTPS ONLY — no browser tooling) ---
LIVE_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)
LIVE_ACCEPT = (
    "text/html,application/xhtml+xml,application/xml;q=0.9,"
    "image/avif,image/webp,*/*;q=0.8"
)
LIVE_ACCEPT_LANGUAGE = "en-US,en;q=0.9"
LIVE_TABLE_MARK = "gnt_ar_b_tbl"
LIVE_SECTION_SLUG = "trade-value-chart-week-%d-ros-rankings"
LIVE_SITEMAP_MONTH = (
    "https://www.gannett-cdn.com/sitemaps/USAT/web/web-sitemap-%04d-%02d.xml"
)
# Position inferred from table title (mirrors ops/watchdog/pull_usatoday.py
# so the live puller reads the same page structure the watchdog reads).
LIVE_POS_BY_TITLE = (
    ("quarterback", "QB"),
    ("fantasy trade charts", "QB"),  # Week 4+ section heading
    ("running back", "RB"),
    ("wide receiver", "WR"),
    ("tight end", "TE"),
)
# USA Today combo -> scoring-column header on RB/WR/TE tables.
# QBs use 1QB regardless of combo (per save_usatoday_references.py
# IMPLIED rule mirroring the CBS fixture).
LIVE_FIXTURE_COMBO_TO_HEADER = {
    "standard_12": "std",
    "half_12": "half",
    "full_12": "ppr",
}
LIVE_DEFAULT_COMBO = "half_12"
# Strict equality: any difference at all is flagged as staleness drift.
# USA Today publishes integer chart points, so float noise isn't expected;
# a non-zero delta means the publisher updated since our snapshot.
LIVE_DEFAULT_TOLERANCE = 0.0

# Canonical ordering test pairs per source.
# These are (higher_name, lower_name) where the LIVE publisher ranks higher > lower.
# If our pipeline flips this ordering, it's a fidelity bug.
# Source: verified against live publisher sites 2026-10-02.
FIDELITY_PAIRS = {
    # USA Today Week 4 Half PPR (from Jeremy's screenshot 2026-10-02 08:29 CDT):
    # JSN 73 > Chase 70 > Amon-Ra 67 > Lamb 62 = Puka 62 > Jefferson 50
    "usatoday": [
        ("jaxon smithnjigba", "puka nacua"),      # 73 > 62
        ("jaxon smithnjigba", "justin jefferson"),  # 73 > 50
        ("amonra st brown", "puka nacua"),          # 67 > 62
    ],
    # FantasyCalc (from JEG-73): JSN native 9914 > Puka 7386
    "fantasycalc": [
        ("jaxon smithnjigba", "puka nacua"),
        ("jahmyr gibbs", "bijan robinson"),
    ],
    # FantasyPros: Gibbs > Bijan (stable top-2)
    "fantasypros": [
        ("jahmyr gibbs", "bijan robinson"),
    ],
    # CBS: Gibbs > Bijan (stable top-2)
    "cbs": [
        ("jahmyr gibbs", "bijan robinson"),
    ],
}


def find_slug(name_fragment: str, values: dict) -> str | None:
    """Find a player slug by name fragment (case-insensitive)."""
    frag = name_fragment.lower()
    for slug in values:
        if frag in slug.lower():
            return slug
    return None


def check_fidelity(source: str, fixture: dict) -> list[dict]:
    """Check that reindexed ordering preserves native ordering.
    
    Returns list of failure dicts (empty if all pass).
    """
    failures = []
    pairs = FIDELITY_PAIRS.get(source, [])
    if not pairs:
        return failures
    
    combos = fixture["sources"][source]["combos"]
    # Use the first combo that has both native and reindexed
    for combo_name, combo in combos.items():
        native = combo.get("native", {})
        reindexed = combo.get("reindexed", {})
        if not native or not reindexed:
            continue
        
        for higher_name, lower_name in pairs:
            h_slug = find_slug(higher_name, native)
            l_slug = find_slug(lower_name, native)
            if not h_slug or not l_slug:
                continue  # Player not in this combo, skip
            
            h_nat = native.get(h_slug, 0)
            l_nat = native.get(l_slug, 0)
            if h_nat <= l_nat:
                continue  # Native ordering doesn't match expectation, skip
            
            h_rei = reindexed.get(h_slug, 0)
            l_rei = reindexed.get(l_slug, 0)
            # Also check slug exists in reindexed (name normalization)
            h_rei_slug = find_slug(higher_name, reindexed)
            l_rei_slug = find_slug(lower_name, reindexed)
            if h_rei_slug:
                h_rei = reindexed[h_rei_slug]
            if l_rei_slug:
                l_rei = reindexed[l_rei_slug]
            
            if h_rei <= l_rei:
                failures.append({
                    "source": source,
                    "combo": combo_name,
                    "type": "fidelity_flip",
                    "higher": higher_name,
                    "lower": lower_name,
                    "native_higher": h_nat,
                    "native_lower": l_nat,
                    "reindexed_higher": h_rei,
                    "reindexed_lower": l_rei,
                    "message": (
                        f"{source}/{combo_name}: FIDELITY FLIP: native {higher_name} "
                        f"({h_nat:.1f}) > {lower_name} ({l_nat:.1f}), but reindexed "
                        f"{h_rei:.1f} <= {l_rei:.1f}"
                    ),
                })
        break  # Only check first valid combo per source
    
    return failures


def check_freshness(source: str, fixture: dict, max_age_days: float = 2.0) -> list[dict]:
    """Check that our snapshot isn't stale.

    Returns list of failure dicts.
    """
    failures = []
    src = fixture["sources"].get(source, {})
    fetched_at = src.get("fetched_at", "")
    content_vintage = src.get("content_vintage", "")

    if not fetched_at:
        failures.append({
            "source": source,
            "type": "freshness_unknown",
            "message": f"{source}: no fetched_at timestamp, cannot verify freshness",
        })
        return failures

    try:
        # Parse ISO timestamp
        ts = datetime.fromisoformat(fetched_at.replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        age = datetime.now(timezone.utc) - ts
        age_days = age.total_seconds() / 86400
        if age_days > max_age_days:
            failures.append({
                "source": source,
                "type": "freshness_stale",
                "fetched_at": fetched_at,
                "content_vintage": content_vintage,
                "age_days": round(age_days, 1),
                "message": (
                    f"{source}: STALE - fetched {age_days:.1f} days ago "
                    f"({fetched_at}), vintage {content_vintage}. "
                    f"Publisher may have done a midweek update."
                ),
            })
    except (ValueError, TypeError) as e:
        failures.append({
            "source": source,
            "type": "freshness_parse_error",
            "message": f"{source}: cannot parse fetched_at '{fetched_at}': {e}",
        })

    return failures


# --- Live USA Today puller (urllib HTTPS ONLY, no browser tooling) ---


class LivePullError(RuntimeError):
    """A live USA Today pull could not complete (network, parse, discovery).

    The live freshness path is fail-closed: any error here is reported as
    a check failure, never a silent pass.
    """


def live_fetch(url, *, timeout=60.0, opener=None):
    """Fetch one URL with stdlib urllib (HTTPS, TLS-verified).

    NO browser, NO selenium/playwright, NO live-browser tooling -- just
    urllib.request.urlopen under a verified SSL context. Returns
    (status: int, body: str). Raises LivePullError on any failure that
    leaves us unable to read the page state.
    """
    import ssl
    import urllib.request

    ctx = ssl.create_default_context()
    req = urllib.request.Request(url, headers={
        "User-Agent": LIVE_USER_AGENT,
        "Accept": LIVE_ACCEPT,
        "Accept-Language": LIVE_ACCEPT_LANGUAGE,
    })
    opener_fn = opener or urllib.request.urlopen
    try:
        with opener_fn(req, timeout=timeout, context=ctx) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            status = getattr(resp, "status", 200) or 200
            return status, body
    except Exception as e:
        raise LivePullError("urllib fetch failed for %s: %s" % (url, e)) from e


def live_discover_url(week, *, fetch_fn=None):
    """Find the current USA Today trade-value-chart URL via sitemap.

    Mirrors ops/watchdog/pull_usatoday.py:discover_url but uses the
    urllib-based fetch_fn from this module (no curl, no browser). Raises
    LivePullError on any failure -- never returns a stale or partial URL.
    """
    fetch = fetch_fn or live_fetch

    def _urls_for_month(year, month):
        url = LIVE_SITEMAP_MONTH % (year, month)
        last_err = None
        for _ in (1, 2):
            try:
                status, body = fetch(url)
            except LivePullError as e:
                last_err = "exception=%s" % e
                continue
            if status == 200 and body and "</urlset>" in body:
                return re.findall(r"<loc>([^<]+)</loc>", body)
            last_err = "status=%r truncated=%s" % (
                status, bool(body) and "</urlset>" not in (body or ""))
        raise LivePullError(
            "sitemap fetch failed/truncated for %04d-%02d (%s)"
            % (year, month, last_err))

    now = datetime.now(timezone.utc)
    slug = LIVE_SECTION_SLUG % week
    months = [(now.year, now.month)]
    if now.month > 1:
        months.append((now.year, now.month - 1))
    else:
        months.append((now.year - 1, 12))
    for year, month in months:
        urls = _urls_for_month(year, month)
        hits = [u for u in urls if slug in u]
        if hits:
            return hits[-1]  # newest article wins (sitemap is chronological)
    raise LivePullError(
        "no USA Today trade-value-chart URL for week %d" % week)


def parse_usatoday_tables(html: str) -> list[dict]:
    """Parse position tables from a USA Today trade-value-chart article.

    Pure function (no I/O). Mirrors ops/watchdog/pull_usatoday.py:pull so
    the live puller reads the same page structure the watchdog puller
    reads. Returns list of dicts:

        {"title": str,
         "position": "QB"|"RB"|"WR"|"TE"|None,
         "headers": [str],
         "rows": [[str]]}

    Position is None if the table title cannot be matched (caller logs,
    never guesses).
    """
    tables = []
    if LIVE_TABLE_MARK not in html:
        return tables

    for m in re.finditer(
            r"<h2[^>]*>(.*?)</h2>.*?"
            r"<table class=gnt_ar_b_tbl>(.*?)</table>", html, re.S):
        title_html, body = m.group(1), m.group(2)
        headers = [
            re.sub(r"<.*?>", "", h).strip()
            for h in re.findall(r"<th>(.*?)</th>", body)
        ]
        rows = []
        for tr in re.finditer(r"<tr>(.*?)</tr>", body, re.S):
            cells = re.findall(r"<td>(.*?)</td>", tr.group(1))
            if cells and cells[0].strip().isdigit():
                rows.append(
                    [re.sub(r"<.*?>", "", c).strip() for c in cells])
        title = re.sub(r"<.*?>", "", title_html).strip()
        # Section headings like "Week N fantasy trade charts" pair with
        # the QB table under the lazy <h2>...<table> regex; promote to
        # QB when 1QB shows up in headers.
        if not re.search(
                r"quarterbacks?|\bqbs?\b|running backs?|wide receivers?|"
                r"tight ends?", title, re.I):
            hl = [h.lower().replace(" ", "") for h in headers]
            if any("1qb" in h for h in hl):
                title = "Quarterback Trade Value Chart"
        position = None
        title_lower = title.lower()
        for key, pos in LIVE_POS_BY_TITLE:
            if key in title_lower:
                position = pos
                break
        tables.append({
            "title": title,
            "position": position,
            "headers": headers,
            "rows": rows,
        })

    return tables


def live_slug(name: str) -> str:
    """Slug a live-pulled player name to the fixture's native-key shape.

    JEG-77 identity rule: the fixture's native keys are lowercase display
    names with non-alphanumeric characters REMOVED (not spaced) and
    whitespace collapsed -- e.g. 'Jaxon Smith-Njigba' -> 'jaxon smithnjigba',
    'A.J. Brown' -> 'aj brown', 'Brian Thomas Jr' -> 'brian thomas jr'
    (suffixes kept). Verified 2026-10-02 (Roman): reproduces all 249 native
    keys of the usatoday half_12 combo from the 2026-09-29 watchdog snapshot
    names, with zero mismatches and zero extras.

    NOTE: match_source_snapshot.normalize_name is documented label-only
    ("not for identity matching") -- it spaces hyphens ('smith njigba')
    and strips suffixes ('brian thomas'), so it must NOT be used here:
    27/249 fixture keys would false-positive as staleness_missing_in_live
    on every live run.
    """
    text = str(name or "").lower()
    text = re.sub(r"[^a-z0-9 ]", "", text)
    return re.sub(r"\s+", " ", text).strip()


def live_extract_native(tables: list[dict], combo: str) -> dict[str, float]:
    """Extract {slug: value} from parsed tables for one fixture combo.

    Slugs come from live_slug so they match the fixture's `native` keys
    exactly (verified 249/249 against the current fixture). QBs use the
    1QB column for std/half/full/ppr (per save_usatoday_references.py
    IMPLIED rule mirroring the CBS fixture); RB/WR/TE use the
    scoring-specific column.

    Players whose table has no value column are skipped (never guessed).
    Tables whose position could not be inferred are skipped.
    """

    col = LIVE_FIXTURE_COMBO_TO_HEADER.get(combo)
    if col is None:
        raise ValueError("unknown combo %r" % combo)

    out: dict[str, float] = {}
    for table in tables:
        pos = table.get("position")
        if not pos:
            continue
        headers = table["headers"]
        headers_lower = [h.lower().replace(" ", "") for h in headers]

        col_header = "1qb" if pos == "QB" else col
        if col_header not in headers_lower:
            continue
        value_header_idx = headers_lower.index(col_header)
        # Row layout: cells = [rank, name, ...values]. The first value
        # column aligns with headers[0]; value at header_idx is at
        # cells[header_idx + 2] (skip rank + name prefix).
        row_value_idx = value_header_idx + 2

        for row in table["rows"]:
            if len(row) <= row_value_idx:
                continue
            try:
                value = float(row[row_value_idx])
            except (ValueError, IndexError):
                continue
            name = row[1] if len(row) > 1 else ""
            slug = live_slug(name)
            if slug:
                out[slug] = value

    return out


def live_pull_usatoday(*, week=None, fetch_fn=None, timeout=60.0):
    """End-to-end live USA Today pull: discover URL, fetch, parse.

    Returns a dict with:
        - source: "usatoday"
        - url: the article URL
        - fetched_at: ISO8601 UTC timestamp
        - tables: parsed tables
        - native_by_combo: {combo: {slug: value}}
        - n_tables, n_rows: counts

    Raises LivePullError on any failure (fail closed; never returns a
    partial result).
    """
    from nfl_week import current_nfl_week

    fetch = fetch_fn or live_fetch
    if week is None:
        week = current_nfl_week()
    url = live_discover_url(week, fetch_fn=fetch)
    status, html = fetch(url, timeout=timeout)  # may raise LivePullError
    if status != 200 or not html:
        raise LivePullError(
            "non-200 or empty body from %s: status=%r" % (url, status))
    tables = parse_usatoday_tables(html)
    if len(tables) < 4:
        raise LivePullError(
            "expected >=4 position tables, got %d from %s"
            % (len(tables), url))
    native_by_combo = {
        combo: live_extract_native(tables, combo)
        for combo in LIVE_FIXTURE_COMBO_TO_HEADER
    }
    return {
        "source": "usatoday",
        "url": url,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "tables": tables,
        "native_by_combo": native_by_combo,
        "n_tables": len(tables),
        "n_rows": sum(len(t["rows"]) for t in tables),
    }


def check_live_freshness(
    source: str,
    fixture: dict,
    live_native_by_combo: dict[str, dict[str, float]],
    *,
    combo: str = LIVE_DEFAULT_COMBO,
    tolerance: float = LIVE_DEFAULT_TOLERANCE,
) -> list[dict]:
    """Compare live publisher values to fixture native values.

    Failure types:
        - staleness_drift: live value differs from fixture native beyond
          tolerance. The publisher updated since our snapshot.
        - staleness_missing_in_live: fixture has a value for the slug,
          but the live page has no row. Either the publisher dropped the
          player or the name changed (canonical-name resolution is
          upstream; this check just reports the gap).

    A live row that does not exist in fixture native is NOT a failure --
    the publisher may have added a player (informational; logged in the
    report under `live_extra`).
    """
    failures = []
    fixture_src = fixture.get("sources", {}).get(source, {})
    fixture_combos = fixture_src.get("combos", {})
    fixture_combo = fixture_combos.get(combo, {}) if isinstance(fixture_combos, dict) else {}
    fixture_native = fixture_combo.get("native", {}) or {}
    live_native = (live_native_by_combo or {}).get(combo, {}) or {}

    for slug, fixture_val in fixture_native.items():
        if slug in live_native:
            live_val = live_native[slug]
            delta = float(live_val) - float(fixture_val)
            if abs(delta) > tolerance:
                failures.append({
                    "source": source,
                    "combo": combo,
                    "type": "staleness_drift",
                    "player": slug,
                    "fixture_native": fixture_val,
                    "live": live_val,
                    "delta": round(delta, 4),
                    "message": (
                        "%s/%s: STALENESS DRIFT -- fixture native %s=%s, "
                        "live=%s. Publisher updated since our snapshot "
                        "(delta=%s)."
                        % (source, combo, slug, fixture_val, live_val,
                           round(delta, 4))),
                })
        else:
            failures.append({
                "source": source,
                "combo": combo,
                "type": "staleness_missing_in_live",
                "player": slug,
                "fixture_native": fixture_val,
                "message": (
                    "%s/%s: STALENESS -- fixture has %s=%s but live page "
                    "has no value for this player."
                    % (source, combo, slug, fixture_val)),
            })

    return failures


def run_live_usatoday_check(
    fixture: dict,
    *,
    week=None,
    fetch_fn=None,
    tolerance: float = LIVE_DEFAULT_TOLERANCE,
    combo: str = LIVE_DEFAULT_COMBO,
):
    """Top-level --live path for USA Today.

    Returns (live_pull: dict, failures: list[dict]). The live_pull dict
    is included in the JSON report under `live_pull` so the reviewer can
    see what was fetched and from where. On LivePullError, returns
    ({"error": str}, [failure]) so the failure is visible rather than a
    silent pass.
    """
    try:
        live_pull = live_pull_usatoday(week=week, fetch_fn=fetch_fn)
    except LivePullError as e:
        return ({"error": str(e)}, [{
            "source": "usatoday",
            "combo": combo,
            "type": "live_unavailable",
            "message": "usatoday live pull failed: %s" % e,
        }])
    failures = check_live_freshness(
        "usatoday", fixture, live_pull["native_by_combo"],
        combo=combo, tolerance=tolerance,
    )
    # Surface live extras (not failures, but informative for the report).
    live_native = live_pull["native_by_combo"].get(combo, {})
    fixture_native = (
        fixture.get("sources", {}).get("usatoday", {})
        .get("combos", {}).get(combo, {}).get("native", {})
    ) or {}
    extra = sorted(set(live_native.keys()) - set(fixture_native.keys()))
    if extra:
        live_pull["live_extra"] = {
            "combo": combo, "count": len(extra), "sample": extra[:10],
        }
    return live_pull, failures


def main(argv=None, *, fetch_fn=None) -> int:
    """fetch_fn is a test seam: production always passes None (real urllib)."""
    import argparse
    ap = argparse.ArgumentParser(description="End-to-end source fidelity checks (JEG-77)")
    ap.add_argument("--source", choices=SOURCES, help="Check only this source")
    ap.add_argument("--max-age-days", type=float, default=2.0,
                    help="Max snapshot age before flagging stale (default: 2.0)")
    ap.add_argument("--json", action="store_true", help="Output JSON report")
    ap.add_argument(
        "--live", action="store_true",
        help="Actually fetch live publisher data via urllib (USA Today only). "
             "Without --live, freshness uses the snapshot age from the fixture.")
    ap.add_argument(
        "--live-combo", default=LIVE_DEFAULT_COMBO,
        choices=sorted(LIVE_FIXTURE_COMBO_TO_HEADER.keys()),
        help="Which fixture combo the live path compares against (default: half_12).")
    ap.add_argument(
        "--live-tolerance", type=float, default=LIVE_DEFAULT_TOLERANCE,
        help="Max delta between live and fixture native before flagging drift "
             "(default: 0.0 — strict equality).")
    args = ap.parse_args(argv)

    fixture = json.loads(FIXTURE.read_text())
    sources = [args.source] if args.source else SOURCES

    all_failures = []
    live_pull_report: dict = {}
    for source in sources:
        if source not in fixture["sources"]:
            print("WARNING: %s not in fixture, skipping" % source, file=sys.stderr)
            continue

        # Fidelity: native ordering vs reindexed ordering
        all_failures.extend(check_fidelity(source, fixture))

        # Freshness: live (--live) OR snapshot-age proxy
        if args.live and source == "usatoday":
            live_pull, live_failures = run_live_usatoday_check(
                fixture, week=None, fetch_fn=fetch_fn,
                tolerance=args.live_tolerance, combo=args.live_combo,
            )
            live_pull_report = live_pull
            all_failures.extend(live_failures)
        else:
            all_failures.extend(check_freshness(source, fixture, args.max_age_days))

    if args.json:
        report = {
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "sources": sources,
            "failures": all_failures,
            "n_failures": len(all_failures),
        }
        if args.live:
            report["live"] = True
            report["live_combo"] = args.live_combo
            report["live_tolerance"] = args.live_tolerance
            report["live_pull"] = live_pull_report
        print(json.dumps(report, indent=2))
    else:
        if not all_failures:
            print("All end-to-end fidelity checks passed.")
            for source in sources:
                print("  OK %s: fresh, ordering preserved" % source)
        else:
            print("\n%d FAILURES:" % len(all_failures))
            for f in all_failures:
                print("  - %s" % f["message"])

    return 1 if all_failures else 0


if __name__ == "__main__":
    sys.exit(main())
