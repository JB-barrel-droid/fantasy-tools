"""JEG-1216: the shared lineup table works in the league panel at desktop and phone width."""
from __future__ import annotations

import unittest

from tests._league_render import browser_on_build, open_page, seed, wait_opps


class LineupComparisonRenderTest(unittest.TestCase):
    def test_expandable_bench_and_phone_accessibility(self):
        with browser_on_build() as (browser, base):
            for width in (1366, 390):
                with self.subTest(width=width):
                    errors = []
                    page = open_page(browser, base, width=width, height=844, errors=errors)
                    seed(page, "20team")
                    wait_opps(page, timeout=90000)
                    page.locator("[data-pick-for]:visible").first.click()
                    page.wait_for_selector("#v2LgOppPanel")
                    wrapper = page.locator('#v2LgOppPanel [data-side="Your team"] .v2-lineup-comparison-wrap').first
                    table = wrapper.locator("table")
                    toggle = wrapper.locator("button.v2-lineup-bench-toggle")
                    bench = wrapper.locator("tbody.v2-lineup-bench-rows")
                    self.assertEqual(toggle.get_attribute("aria-expanded"), "false")
                    self.assertEqual(bench.get_attribute("id"), toggle.get_attribute("aria-controls"))
                    self.assertTrue(bench.is_hidden())
                    self.assertGreater(table.locator('tbody tr[data-slot="RB"]').count(), 0)
                    toggle.focus()
                    page.keyboard.press("Enter")
                    self.assertEqual(toggle.get_attribute("aria-expanded"), "true")
                    self.assertTrue(bench.is_visible())
                    page.keyboard.press("Enter")
                    self.assertEqual(toggle.get_attribute("aria-expanded"), "false")
                    self.assertTrue(bench.is_hidden())
                    self.assertEqual(errors, [])
                    if width == 390:
                        self.assertLessEqual(page.evaluate("document.documentElement.scrollWidth"), 400)
                    page.close()


if __name__ == "__main__":
    unittest.main()
