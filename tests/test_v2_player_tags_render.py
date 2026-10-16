"""v2 Start / Hold / Stash / Drop chips and the drawer's lineup share (JEG-571 front end), rendered.

  * Player values rows and Trade targets rows carry a tag chip using only the four tag words;
  * the player drawer shows that player's own "Expected lineup share: N%" (not the old fixed weighting text)
    and a tag chip in its header;
  * no page errors.

Discrimination: test_guard_fails_on_broken_builds serves a v2.js that drops the chips, one that restores the fixed
text, and one that mislabels tags, and requires failures.
"""
from __future__ import annotations

import unittest

from tests import _render_env  # noqa: E402
from tests.test_v2_names_render import V2_JS, _served  # noqa: E402
from tests.test_published_league_settings_render import _chromium_executable  # noqa: E402

WORDS = {"Start", "Hold", "Stash", "Drop"}


def run_checks(js_patch=None) -> list[str]:
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        raise _render_env.unavailable(f"Playwright is not available: {exc}") from exc
    js = V2_JS.read_text(encoding="utf-8")
    if js_patch:
        old, new = js_patch
        assert old in js, f"patch anchor missing: {old!r}"
        js = js.replace(old, new, 1)
    errors: list[str] = []
    with _served() as base, sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(args=_render_env.HERMETIC_ARGS, executable_path=_chromium_executable(playwright))
        except PlaywrightError as exc:
            raise _render_env.unavailable(f"Chromium is not available: {exc}") from exc
        page_errors: list[str] = []
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            page.on("pageerror", lambda e: page_errors.append(str(e)))
            page.route(lambda u: not u.startswith("http://127.0.0.1"), lambda route: route.abort())
            if js_patch:
                page.route("**/v2/v2.js*", lambda route, *_: route.fulfill(status=200, content_type="text/javascript", body=js))
            page.goto(base + "#player-values", wait_until="networkidle")
            page.wait_for_function("() => window.TradeValueV2 && window.TradeValueV2.view()", timeout=60000)
            page.wait_for_timeout(500)
            chips = page.evaluate("() => [...document.querySelectorAll('#v2Main .v2-table .v2-tag')].map(c => c.textContent.trim())")
            if not chips:
                errors.append("[values] no tag chips on Player values")
            elif not set(chips) <= WORDS:
                errors.append(f"[values] unknown tag words {set(chips) - WORDS}")
            elif "Start" not in chips:
                errors.append(f"[values] no Start chip: {chips[:10]}")
            page.click("#v2Main .v2-table tbody tr:first-child")
            page.wait_for_selector("#v2Drawer:not([hidden])", timeout=10000)
            drawer = page.inner_text("#v2Drawer")
            if "utilization weighting" in drawer:
                errors.append("[drawer] the fixed utilization weighting text is still shown")
            if "Expected lineup share:" not in drawer:
                errors.append("[drawer] no 'Expected lineup share' line")
            if not page.query_selector("#v2Drawer .v2-tag"):
                errors.append("[drawer] no tag chip in the drawer header")
            page.keyboard.press("Escape")
            page.evaluate("() => { location.hash = '#trade-targets'; }")
            page.wait_for_timeout(1500)
            if not page.query_selector("#v2Main .v2-tag"):
                errors.append("[targets] no tag chips on Trade targets")
            if page_errors:
                errors.append(f"page errors {page_errors}")
        finally:
            browser.close()
    return errors


JS_PATCHES = {
    "chips dropped": ("    const tag = playerTagOf(row);\n    if (!tag) return null;", "    const tag = null;\n    if (!tag) return null;"),
    "fixed text restored": ("base.textContent = lineupShareText(row) ||", 'base.textContent = "Starter / bench utilization weighting" ||'),
    "mislabelled": ("chip.textContent = tag;", 'chip.textContent = "Buy";'),
}


class PlayerTagsRenderTest(unittest.TestCase):
    def test_tags(self):
        self.assertEqual(run_checks(), [])

    def test_guard_fails_on_broken_builds(self):
        for name, patch in JS_PATCHES.items():
            with self.subTest(patch=name):
                try:
                    errors = run_checks(js_patch=patch)
                except Exception as exc:
                    if "unavailable" in type(exc).__name__.lower() or type(exc).__name__ == "SkipTest":
                        raise
                    errors = [f"walk-through stopped: {type(exc).__name__}"]
                self.assertNotEqual(errors, [], f"checks did not catch: {name}")


if __name__ == "__main__":
    unittest.main()
