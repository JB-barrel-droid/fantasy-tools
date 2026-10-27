"""JEG-1178 (part of JEG-1176): the week selector in the v2 context row, rendered at 0, 43, 57 and 100 percent coverage.

While sources move from week N to week N+1 each serves its own week. The page shows one week view:
the default is the newer week once MORE than half of the league's sources serve it (JEG-1177 defaultWeek),
a missing source is named and left out (no carry-forward), the reader's pick is kept for the session and
rides in share links as `wk=`, and the selector goes away once every source has the newer week.

The committed data has every source on week 7. Each scenario serves a history index that puts the lagging
sources back on week 6 (the engine drops a source whose served week is before the view's week; the BE sentinel,
tests/test_week_history.py WeekTransitionSentinelTest, pins the value math of a real transition). Coverage is
sources on week 7 of the 7 that feed DDF Value at Full PPR / 12: 0, 3 (43%), 4 (57%) and 7 (100%).

Both clocks are pinned (window.TRADE_VALUE_TODAY and window.TRADE_VALUE_NOW), never the real one. Phone (390) and
desktop (1366x768) are both checked; on desktop Compare's trade boxes and verdict must stay on the first screen
as far as they do with no selector at all.
"""
from __future__ import annotations

import contextlib
import functools
import http.server
import json
import shutil
import socketserver
import sys
import tempfile
import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
sys.path.insert(0, str(ROOT / "pipelines"))
import build_v2_page  # noqa: E402
from tests import _render_env  # noqa: E402
from tests.test_week_history import _fixture_today  # noqa: E402

SOURCES = ("espn", "cbsros", "razzball", "fantasycalc", "usatoday", "fantasypros", "cbs")
NEWER, OLDER = 7, 6
# lagging sources (served week 6), expected default week, and whether a selector shows
SCENARIOS = {
    "0%": {"lagging": SOURCES, "on_newer": 0},
    "43%": {"lagging": ("espn", "cbsros", "razzball", "cbs"), "on_newer": 3},
    "57%": {"lagging": ("espn", "razzball", "cbs"), "on_newer": 4},
    "100%": {"lagging": (), "on_newer": 7},
}
NAMES = {"espn": "ESPN", "cbsros": "CBS rest of season", "razzball": "Razzball", "cbs": "CBS Sports"}
THURSDAY = "2026-10-22"  # Thursday of content week 7
BEFORE_NOON = f"{THURSDAY}T16:00:00Z"   # 11:00 CDT
AT_NOON = f"{THURSDAY}T17:00:00Z"       # 12:00 CDT exactly: not yet after noon
AFTER_NOON = f"{THURSDAY}T18:00:00Z"    # 13:00 CDT


def setUpModule():
    _render_env.ensure_built()


@contextlib.contextmanager
def served_dist(overrides: dict):
    """The built dist (with v2) on a local server; `overrides` maps a path to replacement text."""
    if not (DIST / "index.html").exists():
        raise _render_env.unavailable("dist/index.html is not built")
    with tempfile.TemporaryDirectory() as tmp:
        dist = Path(tmp) / "dist"
        shutil.copytree(DIST, dist, ignore=shutil.ignore_patterns("v2"))
        build_v2_page.build(dist)

        class Handler(http.server.SimpleHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                path = self.path.split("?")[0].lstrip("/")
                body = overrides.get(path)
                if body is None:
                    return super().do_GET()
                data = body.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        handler = functools.partial(Handler, directory=str(dist))
        with socketserver.ThreadingTCPServer(("127.0.0.1", 0), handler) as server:
            server.daemon_threads = True
            threading.Thread(target=server.serve_forever, daemon=True).start()
            try:
                yield f"http://127.0.0.1:{server.server_address[1]}/v2/", dist
            finally:
                server.shutdown()


def transition_index(lagging) -> str:
    index = json.loads((DIST / "assets" / "history" / "index.json").read_text(encoding="utf-8"))
    for source in lagging:
        index["served"][source] = {**index["served"][source], "week": OLDER, "label_week": OLDER}
    return json.dumps(index)


READY = "() => window.TradeValueV2 && window.TradeValueV2.view && window.TradeValueV2.view()"
PROBE = """() => {
  const v2 = window.TradeValueV2, c = window.TradeValueCurveControls;
  const q = id => document.getElementById(id);
  const box = el => { if (!el || el.hidden || !el.offsetParent) return null; const r = el.getBoundingClientRect(); return {top: r.top, bottom: r.bottom, left: r.left, right: r.right}; };
  const ddf = c.getCompositeValues('ddf_value');
  return {
    pick: v2.weekPick(),
    selectVisible: Boolean(box(q('v2WeekPick'))),
    options: [...q('v2WeekSelect').options].map(o => o.textContent),
    selected: q('v2WeekSelect').value,
    selectBox: box(q('v2WeekSelect')),
    note: q('v2WeekNote').textContent,
    noteVisible: Boolean(box(q('v2WeekNoteBar'))),
    stale: Boolean(q('v2WeekNote').querySelector('.v2-weeknote-stale')),
    priced: Object.keys((ddf && ddf.current) || {}).length,
    overflow: document.documentElement.scrollWidth - window.innerWidth,
    engineWeek: c.getWeekState().week,
    link: v2.leagueQuery(),
  };
}"""
COMPARE_FIT = """() => {
  const q = id => document.getElementById(id);
  const r = el => el.getBoundingClientRect();
  return {verdictTop: r(q('v2CVerdict')).top, verdictBottom: r(q('v2CVerdict')).bottom, inner: window.innerHeight,
    contextBottom: r(document.getElementById('v2Context')).bottom,
    noteBottom: document.getElementById('v2WeekNoteBar').hidden ? 0 : r(document.getElementById('v2WeekNoteBar')).bottom};
}"""


def open_page(browser, url, width, height, today=None, now=None, errors=None):
    page = browser.new_page(viewport={"width": width, "height": height})
    if errors is not None:
        page.on("pageerror", lambda e: errors.append(str(e)))
    page.add_init_script(f"window.TRADE_VALUE_TODAY = {json.dumps(today or _fixture_today())};"
                         f"window.TRADE_VALUE_NOW = {json.dumps(now or BEFORE_NOON)};")
    page.route(lambda u: not u.startswith("http://127.0.0.1"), lambda route: route.abort())
    page.goto(url, wait_until="networkidle", timeout=120000)
    page.wait_for_function(READY, timeout=60000)
    page.wait_for_timeout(200)
    return page


def launch(playwright):
    from playwright.sync_api import Error as PlaywrightError
    try:
        return playwright.chromium.launch(args=_render_env.HERMETIC_ARGS,
                                          executable_path=_render_env.chromium_executable(playwright))
    except PlaywrightError as exc:
        raise _render_env.unavailable(f"Chromium is not available: {exc}") from exc


def sync_playwright():
    try:
        from playwright.sync_api import sync_playwright as sp
    except Exception as exc:
        raise _render_env.unavailable(f"Playwright is not available: {exc}") from exc
    return sp()


def check_scenario(browser, base, label, spec, width, height, errors, now=None):
    tag = f"{label} @{width}"
    page_errors = []
    page = open_page(browser, base, width, height, now=now, errors=page_errors)
    s = page.evaluate(PROBE)
    lagging = set(spec["lagging"])
    newer_default = 2 * spec["on_newer"] > 7
    transition = 0 < spec["on_newer"] < 7
    if page_errors:
        errors.append(f"{tag}: page errors {page_errors[:2]}")
    if s["overflow"] > 0:
        errors.append(f"{tag}: page scrolls sideways by {s['overflow']}px")
    if s["selectVisible"] is not transition:
        errors.append(f"{tag}: selector visible {s['selectVisible']}, expected {transition}")
    if s["priced"] < 50:
        errors.append(f"{tag}: DDF Value priced only {s['priced']} players (blank values)")
    if spec["on_newer"] == 0:
        # Nothing has published the newer week: no choice to offer, but the page says so and shows the older week.
        if f"Week {NEWER} is not published by any of the 7 sources" not in s["note"] or s["engineWeek"] != OLDER:
            errors.append(f"{tag}: want the older week plus a not-published note, got week {s['engineWeek']} {s['note']!r}")
    elif transition:
        want_default = NEWER if newer_default else OLDER
        if s["engineWeek"] != want_default or s["selected"] != str(want_default):
            errors.append(f"{tag}: default week {s['engineWeek']} / select {s['selected']}, expected {want_default}")
        want_options = [f"Week {NEWER} ({spec['on_newer']} of 7 sources)", f"Week {OLDER} (7 of 7 sources)"]
        if s["options"] != want_options:
            errors.append(f"{tag}: options {s['options']}, expected {want_options}")
        if "wk=" in s["link"]:
            errors.append(f"{tag}: the default week is in the link: {s['link']!r}")
        # The newer week names every source it lacks and says they are left out, not carried forward.
        page.select_option("#v2WeekSelect", str(NEWER))
        page.wait_for_timeout(300)
        newer = page.evaluate(PROBE)
        for source in lagging:
            if NAMES[source] not in newer["note"]:
                errors.append(f"{tag}: Week {NEWER} note does not name {NAMES[source]}: {newer['note']!r}")
        if "not yet published" not in newer["note"] or "not carried over" not in newer["note"]:
            errors.append(f"{tag}: Week {NEWER} note: {newer['note']!r}")
        if newer["priced"] < 50:
            errors.append(f"{tag}: Week {NEWER} view priced only {newer['priced']} players (blank values)")
        # The older week has every source and shows no missing-source note.
        page.select_option("#v2WeekSelect", str(OLDER))
        page.wait_for_timeout(300)
        older = page.evaluate(PROBE)
        if older["engineWeek"] != OLDER or older["priced"] < 50:
            errors.append(f"{tag}: Week {OLDER} view: week {older['engineWeek']}, priced {older['priced']}")
        if any(NAMES[s_] in older["note"] and "not yet published" in older["note"] for s_ in lagging):
            errors.append(f"{tag}: Week {OLDER} view names missing sources: {older['note']!r}")
    else:
        if s["engineWeek"] != NEWER or (spec["on_newer"] == 7 and s["noteVisible"]):
            errors.append(f"{tag}: at full coverage want Week {NEWER} and no note, got week {s['engineWeek']} note {s['note']!r}")
    page.close()


def run_checks() -> list[str]:
    errors: list[str] = []
    with sync_playwright() as playwright:
        browser = launch(playwright)
        try:
            for label, spec in SCENARIOS.items():
                overrides = {"assets/history/index.json": transition_index(spec["lagging"])}
                with served_dist(overrides) as (base, _dist):
                    for width, height in ((390, 844), (1366, 768)):
                        check_scenario(browser, base, label, spec, width, height, errors)
        finally:
            browser.close()
    return errors


def stale_checks() -> list[str]:
    """Sources still on week 6 get the stale badge only after Thursday 12:00 CT of week 7."""
    errors: list[str] = []
    spec = SCENARIOS["57%"]
    with sync_playwright() as playwright:
        browser = launch(playwright)
        try:
            overrides = {"assets/history/index.json": transition_index(spec["lagging"])}
            with served_dist(overrides) as (base, _dist):
                for now, want in ((BEFORE_NOON, False), (AT_NOON, False), (AFTER_NOON, True)):
                    page = open_page(browser, base, 1366, 768, now=now)
                    s = page.evaluate(PROBE)
                    if s["stale"] is not want:
                        errors.append(f"{now}: stale badge {s['stale']}, expected {want}: {s['note']!r}")
                    if want and not all(NAMES[k] in s["note"] for k in spec["lagging"]):
                        errors.append(f"{now}: stale note does not name every lagging source: {s['note']!r}")
                    page.close()
        finally:
            browser.close()
    return errors


def compare_fit_checks() -> list[str]:
    """Desktop 1366x768: Compare's give / receive boxes and verdict must not sit lower with the selector than without."""
    errors: list[str] = []
    seen = {}
    with sync_playwright() as playwright:
        browser = launch(playwright)
        try:
            for label in ("100%", "57%", "0%"):
                spec = SCENARIOS[label]
                overrides = {"assets/history/index.json": transition_index(spec["lagging"])}
                with served_dist(overrides) as (base, _dist):
                    page = open_page(browser, base + "#compare-trade", 1366, 768)
                    page.wait_for_function("() => window.TradeValueV2.compare && window.TradeValueV2.compare()", timeout=30000)
                    page.click("#v2CUseExample")
                    page.wait_for_timeout(500)
                    seen[label] = page.evaluate(COMPARE_FIT)
                    page.close()
        finally:
            browser.close()
    base_fit = seen["100%"]
    for label in ("57%", "0%"):
        fit = seen[label]
        # The give / receive boxes and the verdict end inside the 768px screen with the selector and its note.
        if fit["verdictBottom"] > fit["inner"]:
            errors.append(f"{label}: Compare's verdict no longer fits the 768px screen ({fit['verdictBottom']:.0f} > {fit['inner']}); "
                          f"without the selector it ends at {base_fit['verdictBottom']:.0f}")
    if base_fit["verdictBottom"] > base_fit["inner"]:
        errors.append(f"even without the selector Compare's verdict ends at {base_fit['verdictBottom']:.0f} of {base_fit['inner']}")
    return errors


def link_round_trip() -> list[str]:
    """A picked week goes into the share link (wk=), survives opening the link in a fresh page, and is remembered
    for the session; a fresh session opened without wk= shows the default week."""
    errors: list[str] = []
    spec = SCENARIOS["57%"]   # default Week 7; the reader picks Week 6
    with sync_playwright() as playwright:
        browser = launch(playwright)
        try:
            overrides = {"assets/history/index.json": transition_index(spec["lagging"])}
            with served_dist(overrides) as (base, _dist):
                page = open_page(browser, base + "#compare-trade", 1366, 768)
                page.click("#v2CUseExample")
                page.select_option("#v2WeekSelect", str(OLDER))
                page.wait_for_timeout(500)
                link = page.evaluate("() => location.href")
                if f"wk={OLDER}" not in link:
                    errors.append(f"the share link has no wk={OLDER}: {link!r}")
                copied = page.evaluate("() => window.TradeValueV2.leagueQuery()")
                if f"wk={OLDER}" not in copied:
                    errors.append(f"leagueQuery has no wk={OLDER}: {copied!r}")
                # Session memory: a reload in the same tab keeps the pick.
                page.goto(base + "#values", wait_until="networkidle")
                page.wait_for_function(READY, timeout=60000)
                page.wait_for_timeout(300)
                if page.evaluate(PROBE)["engineWeek"] != OLDER:
                    errors.append("a reload in the same session lost the picked week")
                page.close()
                # A fresh tab opening the link (no session memory) lands on the sender's week.
                fresh = browser.new_context(viewport={"width": 1366, "height": 768}).new_page()
                fresh.add_init_script(f"window.TRADE_VALUE_TODAY = {json.dumps(_fixture_today())};"
                                      f"window.TRADE_VALUE_NOW = {json.dumps(BEFORE_NOON)};")
                fresh.route(lambda u: not u.startswith("http://127.0.0.1"), lambda route: route.abort())
                fresh.goto(link, wait_until="networkidle", timeout=120000)
                fresh.wait_for_function(READY, timeout=60000)
                fresh.wait_for_timeout(500)
                got = fresh.evaluate(PROBE)
                if got["engineWeek"] != OLDER or got["selected"] != str(OLDER):
                    errors.append(f"the link opened on Week {got['engineWeek']} (select {got['selected']}), expected {OLDER}")
                if f"wk={OLDER}" not in fresh.evaluate("() => location.hash"):
                    errors.append("the opened link's address lost wk=")
                if got["priced"] < 50:
                    errors.append(f"the opened link priced only {got['priced']} players")
                # Picking the default week again takes wk= back out of the link.
                fresh.select_option("#v2WeekSelect", str(NEWER))
                fresh.wait_for_timeout(500)
                if "wk=" in fresh.evaluate("() => location.hash"):
                    errors.append("the default week is still in the link after picking it again")
                fresh.close()
                # A link naming a week outside the transition falls back to the default instead of failing.
                bad = open_page(browser, base + "#compare-trade?give=1&get=2&scoring=ppr&wk=99", 1366, 768)
                if bad.evaluate(PROBE)["engineWeek"] != NEWER:
                    errors.append("a link with an unknown wk= did not fall back to the default week")
                bad.close()
        finally:
            browser.close()
    return errors


class WeekSelectorRenderTest(unittest.TestCase):
    def test_coverage_scenarios_phone_and_desktop(self):
        self.assertEqual(run_checks(), [])

    def test_stale_badge_after_thursday_noon_central(self):
        self.assertEqual(stale_checks(), [])

    def test_compare_still_fits_with_the_selector(self):
        self.assertEqual(compare_fit_checks(), [])

    def test_wk_share_link_round_trip(self):
        self.assertEqual(link_round_trip(), [])


if __name__ == "__main__":
    unittest.main()
