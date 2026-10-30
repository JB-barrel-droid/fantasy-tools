"""JEG-1184: guardrail controls are usable by keyboard and persist across a visit (JEG-1237: they fold with the rosters after Find)."""
from __future__ import annotations

import unittest

from tests import _render_env
from tests.test_published_league_settings_render import _chromium_executable
from tests.test_v2_finder_render import _built_dist
from tests.test_v2_finder_render import PICK


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
                picked = page.evaluate(PICK)
                page.evaluate("""names => {
                  const byName = new Map(window.TradeValueCurveControls.getAllRows().map(r => [r.name, r]));
                  const entries = list => list.map(name => ({key: String(byName.get(name).player_key), name, pos: byName.get(name).pos}));
                  window.TradeValueFinder.ui.setSides(entries(names.mine), entries(names.theirs));
                }""", picked)
                page.locator("#v2FindSize").select_option("3")
                page.locator("#v2FindGo").click()
                page.locator("#v2FindList > li").first.wait_for(timeout=60000)
                self.assertEqual(page.locator("#v2FindList .v2-find-notes.is-warn").count(), 0)
                self.assertNotIn("It breaks your protected positions or Advanced minimums.",
                                 page.locator("#v2FindList").inner_text())
                page.locator(".v2-find-advanced summary").click()
                page.locator("#v2FindMinMine").fill("100")
                page.locator("#v2FindMinMine").press("Tab")
                page.locator("#v2FindGo").click()
                self.assertIn("left out by your protected positions or Advanced minimums",
                              page.locator("#v2FindOut").inner_text())
                self.assertEqual(page.locator("#v2FindList > li").count(), 0)
                page.locator("#v2FindResetSettings").click()
                page.locator(".v2-find-advanced summary").click()
                self.assertEqual(page.locator("#v2FindSize option[value='1']").inner_text(), "1-for-1 only")
                page.locator("#v2FindSize").select_option("1")
                # JEG-1237: after Find the protected-position and bench-backup settings fold with the rosters; the
                # folded summary reads them back and Edit rosters opens them again.
                self.assertTrue(page.locator("#v2FindGuardrails").is_hidden())
                self.assertIn("Trade settings: no protected positions", page.locator("#v2FindGuardrailSummary").inner_text())
                page.locator("#v2FindEdit").click()
                self.assertTrue(page.locator("#v2FindGuardrails").is_visible())
                page.locator("#v2FindBackupsRBUp").focus()
                page.keyboard.press("Enter")
                self.assertEqual(page.locator("#v2FindBackupsRB").inner_text(), "1")
                self.assertFalse(page.locator("#v2FindBackupsRBDown").is_disabled())
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
                self.assertEqual(page.locator("#v2FindSize").input_value(), "1")
                self.assertEqual(page.locator("#v2FindBackupsRB").inner_text(), "1")
                page.locator(".v2-find-advanced summary").click()
                self.assertEqual(page.locator("#v2FindMinMine").input_value(), "0")
                page.locator("#v2FindResetSettings").click()
                self.assertFalse(page.locator("#v2FindProtectRB").is_checked())
                self.assertEqual(page.locator("#v2FindSize").input_value(), "2")
                self.assertEqual(page.locator("#v2FindBackupsRB").inner_text(), "0")
                self.assertTrue(page.locator("#v2FindBackupsRBDown").is_disabled())
                self.assertEqual(page.locator("#v2FindMinMine").input_value(), "")
                self.assertTrue(page.locator("#v2FindKeepMine").is_checked())
                hash_value = page.evaluate("""() => {
                  const rows = window.TradeValueCurveControls.getAllRows().filter(r => Number.isFinite(r.values?.ddf_value));
                  return window.TradeValueFinder.encodeFinderHash({mine: [String(rows[0].player_key)], maxSize: 1,
                    theirs: [String(rows[1].player_key)], keepMine: false,
                    guardrails: {protectedPositions: ['WR'], minBackups: {TE: 2}, minDdfEdge: 2, minUserLineupGain: 0}});
                }""")
                page.goto(base + hash_value)
                page.locator("#v2FindProtectWR").wait_for(timeout=60000)
                self.assertTrue(page.locator("#v2FindProtectWR").is_checked())
                self.assertEqual(page.locator("#v2FindSize").input_value(), "1")
                self.assertEqual(page.locator("#v2FindBackupsTE").inner_text(), "2")
                self.assertFalse(page.locator("#v2FindKeepMine").is_checked())
                page.locator(".v2-find-advanced summary").click()
                self.assertEqual(page.locator("#v2FindMinMine").input_value(), "0")
                # JEG-1237: Find folds the linked settings and the summary reads them back.
                page.locator("#v2FindGo").click()
                self.assertTrue(page.locator("#v2FindGuardrails").is_hidden())
                self.assertEqual(page.locator("#v2FindGuardrailSummary").inner_text(),
                                 "Trade settings: protecting WR; minimum bench backups TE 2")
                page.locator("#v2FindEdit").click()
                self.assertTrue(page.locator("#v2FindBackupsTE").is_visible())
                self.assertLessEqual(page.evaluate("document.documentElement.scrollWidth"), 390)
                self.assertEqual(errors, [])
            finally:
                browser.close()


if __name__ == "__main__":
    unittest.main()
