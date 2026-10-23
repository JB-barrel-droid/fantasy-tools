"""JEG-873: the real tabs sit on one row at every phone width down to 360 px; at 320 px the row may wrap but never overflow.

Live (build tv-20261022-2012-1795eb2) "Values auditing" had no short phone label, so at 320 px the row wrapped
(tab tops 114 / 162) while 360 px and up fit. JEG-852 (#809) then added Find a trade, the seventh tab (lead decision,
"final nav is 7 tabs"); with seven tabs the 320 px row wraps even with the short label, and
tests/test_v2_phone_nav_overflow_render.py (JEG-818) already allows that wrap. So the one-row pin now starts at 360 px. Below 360 px v2.css gives that tab the label "Audit" (the label #809
Find a trade also uses, at every phone width).

At 320, 360, 375, 390 and 412 px: seven tabs, one row from 360 px up (two rows at most at 320), every tab at least 44 px wide and tall, no sideways page scroll, and the
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
TABS = 7  # JEG-852 (#809)
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


def measure(css: str | None = None, strip_short_label: bool = False) -> dict:
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
                if strip_short_label:
                    page.evaluate("() => document.querySelector('.v2-tab[data-view=audit]').removeAttribute('data-short')")
                out[width] = page.evaluate(NAV)
                page.close()
        finally:
            browser.close()
    return out


def errors_in(result: dict) -> list[str]:
    errors = []
    for width, r in result.items():
        if r["count"] != TABS:
            errors.append(f"{width}: {r['count']} tabs, want {TABS}")
        if r["rows"] > (1 if width >= 360 else 2):
            errors.append(f"{width}: tabs on {r['rows']} rows, want {'one' if width >= 360 else 'at most two'}")
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
    def test_seven_tabs_on_one_row_down_to_360(self):
        self.assertEqual(errors_in(measure()), [])

    def test_guard_fails_without_the_short_label(self):
        # Two things now give the Values auditing tab its short phone label: data-short="Audit" (JEG-852, #809, shown at
        # every phone width) and the JEG-873 rule below 360 px. Either alone is enough, so the break removes both.
        css = CSS.read_text(encoding="utf-8")
        rule = re.search(r"\n  /\* JEG-873:.*?\n  \.v2-tab\[data-view=\"audit\"\]::before \{ content: \"Audit\"; \}\n", css, re.S)
        self.assertTrue(rule, "stale mutation anchor")
        errors = errors_in(measure(css.replace(rule.group(0), "\n"), strip_short_label=True))
        self.assertTrue(any(e.startswith("320: Values auditing reads") for e in errors), f"the missing short label was not caught at 320px: {errors}")
        # Each half alone must NOT fail (they are redundant on purpose), so the guard cannot be passing for another reason.
        self.assertEqual(errors_in(measure(strip_short_label=True)), [], "the 320px CSS rule alone should still give the label")

if __name__ == "__main__":
    unittest.main()
