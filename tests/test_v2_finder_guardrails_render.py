"""JEG-1184: guardrail controls are usable by keyboard and persist across a visit."""
from __future__ import annotations

import unittest

from tests import _render_env
from tests.test_published_league_settings_render import _chromium_executable
from tests.test_v2_finder_render import _built_dist


def setUpModule():
    _render_env.ensure_built()


class FinderGuardrailsRenderTest(unittest.TestCase):
    def test_controls_validation_save_reset_and_keyboard(self):
        from playwright.sync_api import sync_playwright

        with _built_dist() as base, sync_playwright() as playwright:
            browser = playwright.chromium.launch(args=_render_env.HERMETIC_ARGS,
                                                 executable_path=_chromium_executable(playwright))
            try:
                page = browser.new_page(viewport={"width": 390, "height": 800})
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.goto(base + "#find-trade")
                page.locator("#v2FindProtectRB").wait_for(timeout=60000)
                page.locator("#v2FindProtectRB").focus()
                page.keyboard.press("Space")
                self.assertTrue(page.locator("#v2FindProtectRB").is_checked())
                page.locator(".v2-find-advanced summary").focus()
                page.keyboard.press("Enter")
                self.assertTrue(page.locator(".v2-find-advanced").evaluate("e => e.open"))
                page.locator("#v2FindMinMine").fill("0")
                page.locator("#v2FindMinMine").press("Tab")
                self.assertEqual(page.locator("#v2FindMinMine").input_value(), "0")
                page.locator("#v2FindMinEdge").fill("101")
                page.locator("#v2FindMinEdge").press("Tab")
                self.assertEqual(page.locator("#v2FindMinEdge").input_value(), "0")
                self.assertIn("0 to 100", page.locator("#v2FindAdvancedStatus").inner_text())
                page.evaluate("window.TradeValueWorkspace.store.flush()")
                page.reload()
                page.locator("#v2FindProtectRB").wait_for(timeout=60000)
                self.assertTrue(page.locator("#v2FindProtectRB").is_checked())
                page.locator(".v2-find-advanced summary").click()
                self.assertEqual(page.locator("#v2FindMinMine").input_value(), "0")
                page.locator("#v2FindResetSettings").click()
                self.assertFalse(page.locator("#v2FindProtectRB").is_checked())
                self.assertEqual(page.locator("#v2FindMinMine").input_value(), "")
                self.assertTrue(page.locator("#v2FindKeepMine").is_checked())
                hash_value = page.evaluate("""() => {
                  const rows = window.TradeValueCurveControls.getAllRows().filter(r => Number.isFinite(r.values?.ddf_value));
                  return window.TradeValueFinder.encodeFinderHash({mine: [String(rows[0].player_key)],
                    theirs: [String(rows[1].player_key)], keepMine: false,
                    guardrails: {protectedPositions: ['WR'], minDdfEdge: 2, minUserLineupGain: 0}});
                }""")
                page.goto(base + hash_value)
                page.locator("#v2FindProtectWR").wait_for(timeout=60000)
                self.assertTrue(page.locator("#v2FindProtectWR").is_checked())
                self.assertFalse(page.locator("#v2FindKeepMine").is_checked())
                page.locator(".v2-find-advanced summary").click()
                self.assertEqual(page.locator("#v2FindMinMine").input_value(), "0")
                self.assertLessEqual(page.evaluate("document.documentElement.scrollWidth"), 390)
                self.assertEqual(errors, [])
            finally:
                browser.close()


if __name__ == "__main__":
    unittest.main()
