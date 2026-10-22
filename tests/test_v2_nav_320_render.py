"""JEG-873: the six real tabs sit on one row at every phone width down to 320 px.

Live (build tv-20261022-2012-1795eb2) "Values auditing" had no short phone label, so at 320 px the row wrapped
(tab tops 114 / 162) while 360 px and up fit. Below 360 px v2.css gives that tab the label "Audit" (the label #809
Find a trade also uses, at every phone width).

At 320, 360, 375, 390 and 412 px: one row, every tab at least 44 px wide and tall, no sideways page scroll, and the
rendered label of the Values auditing tab is "Audit" at 320 px. test_guard_fails_without_the_short_label serves
v2.css without the JEG-873 rule and requires the 320 px row to wrap. (tests/test_v2_phone_nav_overflow_render.py
holds the seven-tab case, where wrapping is allowed.)
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

from tests import _render_env
from tests.test_published_league_settings_render import _chromium_executable
from tests.test_v2_nav_render import _built_dist

ROOT = Path(__file__).resolve().parents[1]
CSS = ROOT / "app" / "v2" / "v2.css"
WIDTHS = (320, 360, 375, 390, 412)
SHORT = "Audit"

NAV = """() => {
  const vw = document.documentElement.clientWidth;
  const tabs = [...document.querySelectorAll('.v2-tabs .v2-tab')].map(t => { const r = t.getBoundingClientRect();
    return {view: t.dataset.view, label: getComputedStyle(t, '::before').content.replace(/^"|"$/g, ''), top: Math.round(r.top),
      width: r.width, height: r.height, right: r.right}; });
  return {rows: new Set(tabs.map(t => t.top)).size, count: tabs.length, over: document.documentElement.scrollWidth - vw,
    small: tabs.filter(t => t.width < 43.5 || t.height < 43.5).map(t => t.label), offscreen: tabs.filter(t => t.right > vw + 0.5).map(t => t.label),
    audit: (tabs.find(t => t.view === 'audit') || {}).label};
}"""


def setUpModule():
    _render_env.ensure_built()


def measure(css: str | None = None) -> dict:
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        raise _render_env.unavailable(f"Playwright is not available: {exc}") from exc
    out = {}
    with _built_dist() as url, sync_playwright() as pw:
        try:
            browser = pw.chromium.launch(args=_render_env.HERMETIC_ARGS, executable_path=_chromium_executable(pw))
        except PlaywrightError as exc:
            raise _render_env.unavailable(f"Chromium is not available: {exc}") from exc
        try:
            for width in WIDTHS:
                page = browser.new_page(viewport={"width": width, "height": 740})
                page.route(lambda u: not u.startswith("http://127.0.0.1"), lambda route: route.abort())
                if css is not None:
                    page.route("**/v2/v2.css*", lambda route: route.fulfill(status=200, content_type="text/css", body=css))
                page.goto(url.replace("#player-values", "#trade-targets"), wait_until="networkidle")
                page.wait_for_function("() => window.TradeValueV2", timeout=40000)
                page.wait_for_timeout(300)
                out[width] = page.evaluate(NAV)
                page.close()
        finally:
            browser.close()
    return out


def errors_in(result: dict) -> list[str]:
    errors = []
    for width, r in result.items():
        if r["count"] != 6:
            errors.append(f"{width}: {r['count']} tabs, want 6")
        if r["rows"] != 1:
            errors.append(f"{width}: tabs on {r['rows']} rows, want one")
        if r["over"] > 0:
            errors.append(f"{width}: page scrolls sideways by {r['over']}px")
        if r["offscreen"]:
            errors.append(f"{width}: tabs past the right edge: {r['offscreen']}")
        if r["small"]:
            errors.append(f"{width}: tabs under 44px: {r['small']}")
        if width < 360 and r["audit"] != SHORT:
            errors.append(f"{width}: Values auditing reads {r['audit']!r}, want {SHORT!r}")
    return errors


class Nav320RenderTest(unittest.TestCase):
    def test_six_tabs_on_one_row_down_to_320(self):
        self.assertEqual(errors_in(measure()), [])

    def test_guard_fails_without_the_short_label(self):
        css = CSS.read_text(encoding="utf-8")
        rule = re.search(r"\n  /\* JEG-873:.*?\n  \.v2-tab\[data-view=\"audit\"\]::before \{ content: \"Audit\"; \}\n", css, re.S)
        self.assertTrue(rule, "stale mutation anchor")
        errors = errors_in(measure(css.replace(rule.group(0), "\n")))
        self.assertTrue(any(e.startswith("320: tabs on 2 rows") for e in errors), f"the long label did not wrap the 320px row: {errors}")


if __name__ == "__main__":
    unittest.main()
