"""JEG-873: the six real tabs sit on one row at every phone width down to 320 px.

Live (build tv-20261022-2012-1795eb2) "Values auditing" had no short phone label, so at 320 px the row wrapped
(tab tops 114 / 162) while 360 px and up fit. The phone label is "Audit" (the label #809 Find a trade also uses).

At 320, 360, 375, 390 and 412 px: one row, every tab at least 44 px wide and tall, no sideways page scroll.
test_guard_fails_on_long_label puts the long label back on the tab and requires the 320 px row to wrap.
(tests/test_v2_phone_nav_overflow_render.py holds the seven-tab case, where wrapping is allowed.)
"""
from __future__ import annotations

import unittest

from tests import _render_env
from tests.test_published_league_settings_render import _chromium_executable
from tests.test_v2_nav_render import _built_dist

WIDTHS = (320, 360, 375, 390, 412)
SHORT = "Audit"

NAV = """() => {
  const vw = document.documentElement.clientWidth;
  const tabs = [...document.querySelectorAll('.v2-tabs .v2-tab')].map(t => { const r = t.getBoundingClientRect();
    return {short: t.dataset.short, top: Math.round(r.top), width: r.width, height: r.height, right: r.right}; });
  return {rows: new Set(tabs.map(t => t.top)).size, count: tabs.length, over: document.documentElement.scrollWidth - vw,
    small: tabs.filter(t => t.width < 43.5 || t.height < 43.5).map(t => t.short), offscreen: tabs.filter(t => t.right > vw + 0.5).map(t => t.short),
    shorts: tabs.map(t => t.short)};
}"""


def setUpModule():
    _render_env.ensure_built()


def measure(long_label=False) -> dict:
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
                page.goto(url.replace("#player-values", "#trade-targets"), wait_until="networkidle")
                page.wait_for_function("() => window.TradeValueV2", timeout=40000)
                if long_label:
                    page.evaluate("() => { document.querySelector('.v2-tab[data-view=audit]').dataset.short = 'Values auditing'; }")
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
            errors.append(f"{width}: {r['count']} tabs, want 6 ({r['shorts']})")
        if r["rows"] != 1:
            errors.append(f"{width}: tabs on {r['rows']} rows, want one")
        if r["over"] > 0:
            errors.append(f"{width}: page scrolls sideways by {r['over']}px")
        if r["offscreen"]:
            errors.append(f"{width}: tabs past the right edge: {r['offscreen']}")
        if r["small"]:
            errors.append(f"{width}: tabs under 44px: {r['small']}")
        if SHORT not in r["shorts"]:
            errors.append(f"{width}: Values auditing has no '{SHORT}' phone label: {r['shorts']}")
    return errors


class Nav320RenderTest(unittest.TestCase):
    def test_six_tabs_on_one_row_down_to_320(self):
        self.assertEqual(errors_in(measure()), [])

    def test_guard_fails_on_long_label(self):
        errors = errors_in(measure(long_label=True))
        self.assertTrue(any(e.startswith("320: tabs on 2 rows") for e in errors), f"the long label did not wrap the 320px row: {errors}")


if __name__ == "__main__":
    unittest.main()
