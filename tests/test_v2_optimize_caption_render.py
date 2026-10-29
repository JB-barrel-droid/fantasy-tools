"""JEG-1119: Optimize for playoffs is hidden (known not working).

Checks that the Optimize for control (segmented buttons and caption) is NOT
present in Edit league, at 1440, 390 and 320 wide.

When the feature is ready to ship, restore the original checks and re-enable
it in v2.js.
"""
from __future__ import annotations

import functools
import unittest

from tests import _render_env
from tests.test_v2_share_render import _built_dist, _serve
from tests.test_published_league_settings_render import _chromium_executable


def setUpModule():
    _render_env.ensure_built()


PROBE = """() => {
  const cap = document.getElementById('v2OptimizeNotReviewed');
  const seg = document.querySelector('.v2-pseg button[data-value="playoffs"]');
  return { capPresent: !!cap, segPresent: !!seg };
}"""


def run_checks() -> list[str]:
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        raise _render_env.unavailable(f"Playwright is not available: {exc}") from exc
    errors = []
    with _built_dist() as base, sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(args=_render_env.HERMETIC_ARGS, executable_path=_chromium_executable(playwright))
        except PlaywrightError as exc:
            raise _render_env.unavailable(f"Chromium is not available: {exc}") from exc
        try:
            for width, height in ((1440, 1000), (390, 800), (320, 700)):
                page = browser.new_page(viewport={"width": width, "height": height})
                page.errors = []
                page.on("pageerror", lambda e: page.errors.append(str(e)))
                page.route(lambda u: not u.startswith("http://127.0.0.1"), lambda route: route.abort())
                page.goto(base + "#compare-trade", wait_until="networkidle")
                page.wait_for_function("() => window.TradeValueV2 && window.TradeValueV2.compare()", timeout=30000)
                _render_env.open_phone_context(page)  # JEG-1134: on a phone the context row opens first
                page.click("#v2EditLeague")
                page.wait_for_timeout(300)
                s = page.evaluate(PROBE)
                tag = f"@{width}"
                if s["capPresent"]:
                    errors.append(f"{tag} v2OptimizeNotReviewed element should not be in DOM (feature is hidden)")
                if s["segPresent"]:
                    errors.append(f"{tag} Playoffs segmented button should not be in DOM (feature is hidden)")
                if page.errors:
                    errors.append(f"{tag} page errors {page.errors}")
                page.close()
        finally:
            browser.close()
    return errors


class OptimizeCaptionRenderTest(unittest.TestCase):
    def test_optimize_playoffs_hidden(self):
        self.assertEqual(run_checks(), [])


if __name__ == "__main__":
    unittest.main()
