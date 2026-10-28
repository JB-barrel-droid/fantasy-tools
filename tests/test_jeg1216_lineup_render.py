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
                    visible = page.evaluate("""() => [...document.querySelectorAll('#v2LgOppsTable tr.v2-lg-opp')].map(tr => {
                      const row = window.TradeValueLeague.ui.result.rows.find(r => r.id === tr.dataset.oppId);
                      return {gain: row?.fit?.us?.starterDelta, priced: row?.give.concat(row.receive).every(p => Number.isFinite(p.values?.ddf_value)),
                        text: tr.querySelector('[data-cell="ours"]')?.textContent || ''};
                    })""")
                    gains = [row for row in visible if row["priced"] and row["gain"] and row["gain"] > 0.05]
                    self.assertTrue(gains, "fixture needs a visible genuine starter gain")
                    self.assertTrue(all("starters gain +" in row["text"] and "starters hold" not in row["text"] for row in gains), gains)
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
                    missing = page.evaluate("""() => {
                      const F = window.TradeValueFinder, L = window.TradeValueLineupComparison;
                      const before = F.lineupValue([], {RB: 1}, 'ddf_value');
                      const after = F.lineupValue([{player_key: 'missing', name: 'Unpriced RB', pos: 'RB', values: {ddf_value: null}}], {RB: 1}, 'ddf_value');
                      const view = L.renderTable({before, after}, {RB: 1}, 'ddf_value', 'Missing value check');
                      view.querySelector('button').click();
                      return [...view.querySelectorAll('tbody.v2-lineup-bench-rows tr')].map(row => row.textContent);
                    }""")
                    self.assertEqual(len(missing), 1)
                    self.assertIn("Unpriced RB no value", missing[0])
                    self.assertTrue(missing[0].endswith("—"), missing)
                    if width == 390:
                        self.assertLessEqual(page.evaluate("document.documentElement.scrollWidth"), 400)
                    page.close()


if __name__ == "__main__":
    unittest.main()
