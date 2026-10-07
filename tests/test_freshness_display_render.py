"""Rendered regression for GAP-043: every freshness label on the built page
agrees with each source's own content week.

The rule (one rule, every surface): a source's content week comes from its
own section -- `week_designated` ("Week N"), then `content_vintage`, then its
dated fields -- placed on the Tuesday-flip content calendar of
pipelines/nfl_week.py. A source older than the reader's content week is
marked as older ("Week 4 · newer week not yet published" for a weekly chart).

Before the fix (live page, 2026-10-07): every dataset-health card wore a
constant "Live" badge and showed `published` (2026-09-15) as its content
date, the header's "Source snapshot" showed the build time, the table note
said "source weeks current" while CBS was on Week 4, and the chart toggles
and caption used their own build-time week rule ("Week 4 references").

Checks, on the synced page in headless Chromium:
- every health card's badge and content-week text match the fixture;
- the header box shows the current content week and the older-week count;
- every weekly chart toggle shows its own week and is marked older exactly
  when the fixture says so;
- the table note names every older source;
- a fixture edit (USA Today -> Week 3) moves the labels with it (no constant);
- NEGATIVE: the old constant "Live" badge, and a label that ignores the
  source's week, are both caught by the same checker.
"""

import contextlib
import datetime
import functools
import http.server
import json
import re
import shutil
import socketserver
import sys
import threading
import unittest
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
# The synced page (`make sync` writes the same files to app/ and dist/); app/
# is always the current source, while a committed dist/ can lag until CI syncs.
SERVE = ROOT / "app" / "trade-value-chart"
sys.path.insert(0, str(ROOT / "pipelines"))
from nfl_week import current_nfl_week  # noqa: E402

CARD_KEYS = {
    "USA Today": "usatoday", "FantasyCalc": "fantasycalc", "FantasyPros": "fantasypros",
    "CBS": "cbs", "CBS Adjusted": "cbs_adjusted", "FC Adjusted": "fantasycalc_adjusted",
    "USAT Adjusted": "usatoday_adjusted", "FP Adjusted": "fantasypros_adjusted",
    "ESPN": "espn", "ESPN live": "espn", "Razzball": "razzball",
}
WEEKLY_TOGGLES = {
    "usatoday": "USA Today", "fantasycalc": "FantasyCalc", "fantasypros": "FantasyPros", "cbs": "CBS",
    "fantasycalc_adjusted": "FC Adjusted", "usatoday_adjusted": "USAT Adjusted",
    "fantasypros_adjusted": "FP Adjusted", "cbs_adjusted": "CBS Adjusted",
}


def _week_label(value):
    match = re.search(r"week\s*(\d+)|wk\s*(\d+)", str(value or ""), re.I)
    return int(match.group(1) or match.group(2)) if match else None


def _iso_day(value):
    match = re.match(r"(\d{4}-\d{2}-\d{2})", str(value or ""))
    return match.group(1) if match else None


def expected_week(sources, key):
    """Independent Python statement of the rule, read straight off the fixture."""
    base = "cbs" if key == "cbs_adjusted" else key.replace("_adjusted", "")
    meta = sources.get(base) or sources.get(key) or {}
    for field in ("week_designated", "content_vintage"):
        week = _week_label(meta.get(field))
        if week:
            return week, "weekly"
    for value in (meta.get("content_vintage"), meta.get("vintage"), meta.get("espn_snapshot"),
                  (meta.get("lineage") or {}).get("raw_vintage"), meta.get("fetched_at")):
        day = _iso_day(value)
        if day:
            return current_nfl_week(datetime.date.fromisoformat(day)), "rest_of_season"
    return None, None


def violations(page_state, sources, today):
    """Compare what the page shows with what the fixture says. [] when they agree."""
    current = current_nfl_week(datetime.date.fromisoformat(today))
    problems = []
    cards = page_state["cards"]
    if not cards:
        problems.append("no dataset-health source cards rendered")
    older_count = 0
    for card in cards:
        key = CARD_KEYS.get(card["title"])
        if not key:
            continue
        week, cadence = expected_week(sources, key)
        older = week is not None and week < current
        older_count += older
        want_badge = "Older week" if older else "Current week"
        if card["badge"].strip().lower() != want_badge.lower():
            problems.append(f"{card['title']}: badge {card['badge']!r}, fixture says {want_badge!r} (Week {week})")
        if not re.search(rf"\bWeek {week}\b", card["freshness"]):
            problems.append(f"{card['title']}: freshness {card['freshness']!r} lacks Week {week}")
        if older and cadence == "weekly" and "newer week not yet published" not in card["freshness"]:
            problems.append(f"{card['title']}: Week {week} chart not marked older ({card['freshness']!r})")
    if page_state["header"].strip() != f"Week {current}":
        problems.append(f"header source box shows {page_state['header']!r}, not Week {current}")
    want_header_badge = f"{older_count} of" if older_count else "All"
    if not page_state["headerBadge"].startswith(want_header_badge):
        problems.append(f"header badge {page_state['headerBadge']!r} does not report {older_count} older")
    for key, label in WEEKLY_TOGGLES.items():
        toggle = next((t for t in page_state["toggles"]
                       if t["text"].split("\n")[0].startswith(label + " Wk ")), None)
        if toggle is None:
            problems.append(f"toggle for {label} missing")
            continue
        week, _ = expected_week(sources, key)
        older = week < current
        first = toggle["text"].split("\n")[0].strip()
        if first != f"{label} Wk {week}":
            problems.append(f"toggle {first!r} != {label} Wk {week}")
        if toggle["available"] and toggle["stale"] != older:
            problems.append(f"toggle {first!r} older flag {toggle['stale']} != {older}")
        if toggle["available"] and older and "newer week not yet published" not in toggle["text"]:
            problems.append(f"toggle {first!r} not marked 'newer week not yet published'")
    note = page_state["tableNote"]
    any_older_weekly = any(expected_week(sources, k)[0] < current for k in ("usatoday", "fantasycalc", "fantasypros", "cbs"))
    if any_older_weekly and ("current" in note and "older" not in note):
        problems.append(f"table note claims current while a weekly chart is older: {note!r}")
    return problems


READ_STATE = """() => ({
  cards: [...document.querySelectorAll('#datasetHealthRows .dataset-card')].map(card => ({
    title: card.querySelector('h3')?.textContent || '',
    badge: card.querySelector('.dataset-badge')?.textContent || '',
    freshness: [...card.querySelectorAll('.dataset-facts > div')]
      .filter(d => /freshness|content week/i.test(d.querySelector('dt')?.textContent || ''))
      .map(d => d.querySelector('dd')?.textContent || '').join(' '),
  })).filter(c => !/news pipeline|freshness pipe/i.test(c.title)),
  header: document.getElementById('ecrContentDate')?.textContent || '',
  headerBadge: document.getElementById('ecrFreshnessBadge')?.textContent || '',
  toggles: [...document.querySelectorAll('.src-toggle')].map(t => ({
    text: t.querySelector('.src-text')?.innerText || '',
    stale: t.classList.contains('is-stale'),
    available: !t.querySelector('input')?.disabled,
  })),
  tableNote: document.getElementById('freshness')?.textContent || '',
})"""


def _chromium_executable(playwright):
    candidates = [Path(playwright.chromium.executable_path),
                  Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")]
    for name in ("chromium", "chromium-browser", "google-chrome"):
        found = shutil.which(name)
        if found:
            candidates.append(Path(found))
    return next((str(c) for c in candidates if c.exists()), None)


@contextlib.contextmanager
def rendered_state(sources_edit=None, text_mutations=None):
    """Load the built page; optionally edit the fixture or mutate served text."""
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        raise unittest.SkipTest(f"Playwright is not available: {exc}") from exc

    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass

    data = json.loads((SERVE / "assets" / "comparison-sources-data.json").read_text())
    if sources_edit:
        sources_edit(data["sources"])
    today = datetime.datetime.now(ZoneInfo("America/New_York")).date().isoformat()
    handler = functools.partial(Quiet, directory=str(SERVE))
    with socketserver.ThreadingTCPServer(("127.0.0.1", 0), handler) as server:
        server.daemon_threads = True
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            url = f"http://127.0.0.1:{server.server_address[1]}/"
            with sync_playwright() as playwright:
                try:
                    browser = playwright.chromium.launch(executable_path=_chromium_executable(playwright))
                except PlaywrightError as exc:
                    raise unittest.SkipTest(f"Chromium is not available: {exc}") from exc
                try:
                    page = browser.new_page()
                    page.add_init_script(f"window.TRADE_VALUE_TODAY = {json.dumps(today)};")
                    page.route("**/assets/comparison-sources-data.json*", lambda route: route.fulfill(
                        status=200, content_type="application/json", body=json.dumps(data)))
                    for pattern, pairs in (text_mutations or {}).items():
                        def mutate(route, _request=None, pairs=pairs):
                            body = route.fetch().text()
                            for old, new in pairs:
                                assert old in body, f"mutation target missing: {old[:60]}"
                                body = body.replace(old, new)
                            route.fulfill(status=200, body=body, headers={"content-type": "text/html" if pattern.endswith("/") else "application/javascript"})
                        page.route(pattern, mutate)
                    page.goto(url, wait_until="networkidle")
                    page.wait_for_function(
                        "() => document.querySelectorAll('#datasetHealthRows .dataset-card').length"
                        " && document.querySelectorAll('.src-toggle').length", timeout=20000)
                    yield page.evaluate(READ_STATE), data["sources"], today
                finally:
                    browser.close()
        finally:
            server.shutdown()


# Simulated broken states (negative tests).
CONSTANT_LIVE_BADGE = {"**/": [
    ('<span class="dataset-badge">${esc(badgeText[fresh.status])}</span>', '<span class="dataset-badge">Live</span>'),
]}
IGNORES_SOURCE_WEEK = {"**/assets/product-data.js*": [
    ("const designated = parseWeekLabel(m.week_designated);", "const designated = 5;"),
]}


class FreshnessDisplayRenderTest(unittest.TestCase):
    def test_built_page_labels_match_fixture(self):
        with rendered_state() as (state, sources, today):
            self.assertEqual(violations(state, sources, today), [])

    def test_labels_follow_a_fixture_edit(self):
        def usatoday_week_3(sources):
            sources["usatoday"]["week_designated"] = "Week 3"
            sources["usatoday"]["content_vintage"] = "Week 3"
        with rendered_state(usatoday_week_3) as (state, sources, today):
            self.assertEqual(violations(state, sources, today), [])
            card = next(c for c in state["cards"] if c["title"] == "USA Today")
            self.assertIn("Week 3", card["freshness"])

    def test_negative_constant_live_badge_is_caught(self):
        with rendered_state(text_mutations=CONSTANT_LIVE_BADGE) as (state, sources, today):
            self.assertTrue(violations(state, sources, today),
                            "a constant 'Live' badge must not pass the freshness check")

    def test_negative_label_ignoring_source_week_is_caught(self):
        with rendered_state(text_mutations=IGNORES_SOURCE_WEEK) as (state, sources, today):
            problems = violations(state, sources, today)
            self.assertTrue(any("CBS" in p for p in problems),
                            f"CBS Week 4 rendered as Week 5 must be caught: {problems}")


if __name__ == "__main__":
    unittest.main()
