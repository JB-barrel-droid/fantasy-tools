"""Phone header at first paint (JEG-887).

Round-3 product review (2026-10-22): at 375 x 812 the "Data Driven Football" wordmark was reported above the
viewport on first paint and the header showed only "Week 7 · 1 source held". Measured on the built page, the
freshness button (content-width flex basis) wrapped onto its own row below 400 px, so the header was 166 px with
a blank dark band under the wordmark and the page started 52 px lower.

Loads the built page headless at 320, 360, 375, 390 and 412 px wide (812 tall), fresh, at #trade-targets and
#compare-trade, and requires at scrollY 0: the wordmark fully inside the viewport and inside the painted header,
and (360 px and up) the header no taller than two rows. JEG-1119 (Jeremy's scope, 2026-10-26) moved the freshness
button out of the header into the context row, so on a phone it must sit on the league summary's line there, short
label and all. Since JEG-1134 that line is the row's summary button (#v2ContextSummary).
Discrimination: test_guard_fails_on_broken_builds serves v2.css with the wordmark pushed 41 px up (the reported
-31 px top) and with the phone rules broken (the freshness button back on its own row; the full text instead of "Week 7"), and requires failures.
"""
from __future__ import annotations

import unittest

from tests import _render_env
from tests.test_published_league_settings_render import _chromium_executable
from tests.test_v2_deal_read_render import _served, V2_JS

V2_CSS = V2_JS.with_name("v2.css")
WIDTHS = (320, 360, 375, 390, 412)
TABS = ("#trade-targets", "#compare-trade")
TWO_ROWS_MAX = 120  # wordmark row (44 + 10 padding) + tab row (52) + gap
MEASURE = """() => {
  const r = s => { const b = document.querySelector(s).getBoundingClientRect(); return {top: b.top, bottom: b.bottom, left: b.left, right: b.right}; };
  // JEG-1134: below 768 px the league summary is the context row's summary line (the league block opens under it).
  const league = document.getElementById('v2ContextSummary')?.offsetParent ? '#v2ContextSummary' : '.v2-ctx-league';
  return {scrollY: window.scrollY, brand: r('.v2-brand'), nav: r('.v2-nav'), fresh: r('#v2Freshness'), league: r(league)};
}"""


def run_checks(css_patch=None) -> list[str]:
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        raise _render_env.unavailable(f"Playwright is not available: {exc}") from exc
    css = V2_CSS.read_text(encoding="utf-8")
    if css_patch:
        assert css_patch[0] in css, f"css patch anchor missing: {css_patch[0]!r}"
        css = css.replace(css_patch[0], css_patch[1])
    errors: list[str] = []
    with _served() as base, sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(args=_render_env.HERMETIC_ARGS, executable_path=_chromium_executable(playwright))
        except PlaywrightError as exc:
            raise _render_env.unavailable(f"Chromium is not available: {exc}") from exc
        try:
            for width in WIDTHS:
                for tab in TABS:
                    page = browser.new_page(viewport={"width": width, "height": 812}, is_mobile=True, has_touch=True)
                    page.route(lambda u: not u.startswith("http://127.0.0.1"), lambda route: route.abort())
                    if css_patch:
                        page.route("**/v2/v2.css*", lambda route, *_: route.fulfill(status=200, content_type="text/css", body=css))
                    page.goto(base + tab, wait_until="networkidle")
                    page.wait_for_function("() => window.TradeValueV2 && [...document.querySelectorAll('main.v2-main')].some(m => !m.hidden)", timeout=60000)
                    page.wait_for_timeout(300)
                    m = page.evaluate(MEASURE)
                    tag = f"[{width}px {tab}]"
                    brand, nav, fresh, league = m["brand"], m["nav"], m["fresh"], m["league"]
                    if m["scrollY"] != 0:
                        errors.append(f"{tag} page is scrolled on load: scrollY {m['scrollY']}")
                    if brand["top"] < 0 or brand["left"] < 0 or brand["right"] > width:
                        errors.append(f"{tag} wordmark outside the viewport: {brand}")
                    if brand["top"] < nav["top"] or brand["bottom"] > nav["bottom"]:
                        errors.append(f"{tag} wordmark outside the painted header: brand {brand} nav {nav}")
                    if width >= 360:
                        mid = lambda b: (b["top"] + b["bottom"]) / 2  # noqa: E731
                        if abs(mid(fresh) - mid(league)) > 2 or fresh["right"] > width:
                            errors.append(f"{tag} freshness button is not on the league summary's line: league {league}, freshness {fresh}")
                        if nav["bottom"] - nav["top"] > TWO_ROWS_MAX:
                            errors.append(f"{tag} header is taller than two rows: {nav['bottom'] - nav['top']:.0f}px")
                    page.close()
        finally:
            browser.close()
    return errors


PATCHES = {
    "wordmark pushed above the viewport": (".v2-brand { min-height: 44px; display: inline-flex; align-items: center; }",
                                           ".v2-brand { min-height: 44px; display: inline-flex; align-items: center; margin-top: -41px; }"),
    "freshness button back on its own row": (".v2-context .v2-ctx-freshness { order: 1; flex: 0 1 auto; min-width: 0;",
                                             ".v2-context .v2-ctx-freshness { order: 1; flex: 1 0 100%; min-width: 0;"),
    "full freshness text on a phone": ("  .v2-context .v2-freshness #v2FreshnessLabel { display: none; }",
                                       "  .v2-context .v2-freshness #v2FreshnessLabel { display: inline; white-space: nowrap; flex-shrink: 0; min-width: max-content; }"),
}


class PhoneHeaderRenderTest(unittest.TestCase):
    def test_wordmark_on_first_paint(self):
        _render_env.ensure_built()
        self.assertEqual(run_checks(), [])

    def test_guard_fails_on_broken_builds(self):
        _render_env.ensure_built()
        for name, patch in PATCHES.items():
            with self.subTest(patch=name):
                self.assertNotEqual(run_checks(css_patch=patch), [], f"checks did not catch: {name}")


if __name__ == "__main__":
    unittest.main()
