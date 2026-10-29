"""JEG-1231: opponent inclusion checkboxes on the built league page.

Leaving a team out removes its offers and nothing else: the remaining rows keep their values, fits and order, the star,
rosters and names do not change, the choice is saved with the league, and Clear all says why nothing is found.
"""
from __future__ import annotations

import unittest

from tests._league_render import browser_on_build, open_page, seed, wait_opps

ROWS = """() => window.TradeValueLeague.ui.result.rows.map(r => JSON.stringify({...r, rank: undefined}))"""
WORKSPACE = """() => { const ws = window.TradeValueWorkspace.store.get();
  return JSON.stringify({star: ws.myTeamId, teams: ws.teams.map(t => [t.id, t.name, t.entries.map(e => e.key)])}); }"""


class LeagueInclusionRenderTest(unittest.TestCase):
    def test_leaving_out_a_team(self):
        with browser_on_build() as (browser, base):
            for width in (1366, 390):
                with self.subTest(width=width):
                    errors = []
                    page = open_page(browser, base, width=width, height=844, errors=errors)
                    seed(page, "4team")
                    wait_opps(page)
                    self.assertTrue(page.locator("#v2LgOppsInclusion").is_visible())
                    boxes = page.locator("#v2LgOppsInclusion input[type=checkbox]")
                    self.assertEqual(boxes.count(), 3, "every other team, never my own")
                    self.assertEqual(page.locator("#v2LgOppsInclusion input:checked").count(), 3, "today's baseline: every opponent searched")
                    full = page.evaluate(ROWS)
                    before = page.evaluate(WORKSPACE)
                    target = page.evaluate("""() => { const r = window.TradeValueLeague.ui.result.rows; return r.length ? r[0].opponentId : null; }""")
                    self.assertIsNotNone(target, "the fixture finds at least one trade")
                    box = page.locator(f"#v2LgOppsInclusion input[data-team-id='{target}']")
                    box.focus()
                    page.keyboard.press("Space")
                    wait_opps(page)
                    self.assertEqual(page.evaluate("() => document.activeElement && document.activeElement.dataset.teamId"), target,
                                     "focus stays on the box after the search runs again")
                    rows = page.evaluate("() => window.TradeValueLeague.ui.result.rows.map(r => r.opponentId)")
                    self.assertNotIn(target, rows, "no offer from a left-out team")
                    shown = page.evaluate("() => [...document.querySelectorAll('[data-opp-id]')].map(n => n.dataset.oppId.split('|')[0])")
                    self.assertNotIn(target, shown)
                    kept = [r for r in full if f'"opponentId":"{target}"' not in r]
                    self.assertEqual(page.evaluate(ROWS), kept, "the other rows keep every value, fit and their order")
                    options = page.evaluate("() => [...document.querySelectorAll('#v2LgFilterOpp option')].map(o => o.value)")
                    self.assertNotIn(target, options)
                    self.assertEqual(page.evaluate(WORKSPACE), before, "star, rosters and names are untouched")
                    saved = page.evaluate("() => window.TradeValueWorkspace.store.get().ui.opponentInclusion")
                    self.assertEqual(saved, {"v": 1, "excluded": [target]})
                    page.click("#v2LgOiNone")
                    wait_opps(page)
                    self.assertIn("No opponent with a roster is included", page.inner_text("#v2LgOppsMsg"))
                    page.click("#v2LgOiAll")
                    wait_opps(page)
                    self.assertEqual(page.evaluate(ROWS), full, "Select all brings back exactly the first result")
                    if width == 390:
                        self.assertLessEqual(page.evaluate("document.documentElement.scrollWidth"), 400)
                    self.assertEqual(errors, [])
                    page.close()


if __name__ == "__main__":
    unittest.main()
