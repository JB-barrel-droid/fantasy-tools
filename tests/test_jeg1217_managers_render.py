"""JEG-1217: the Managers card on Find a trade captures profiles and exclusions, saves them, and changes no trade numbers.

Runs on the built page (tests/_league_render.py). Desktop and phone width.
"""
from __future__ import annotations

import json
import unittest

from tests._league_render import browser_on_build, open_page, seed, wait_opps

OPP_ROWS = """() => (window.TradeValueLeague.ui.result ? window.TradeValueLeague.ui.result.rows : []).map(r => r.id + ':' + r.give.map(p => p.player_key).join(',') + '>' + r.receive.map(p => p.player_key).join(','))"""


class ManagersCardRenderTest(unittest.TestCase):
    def test_capture_exclusion_reload_and_no_value_change(self):
        with browser_on_build() as (browser, base):
            for width in (1366, 390):
                with self.subTest(width=width):
                    errors = []
                    context = browser.new_context(viewport={"width": width, "height": 844}, accept_downloads=True)
                    page = open_page(browser, base, width=width, height=844, errors=errors, context=context)
                    seed(page, "4team")
                    wait_opps(page, timeout=90000)
                    before = page.evaluate(OPP_ROWS)
                    card = page.locator("#v2LgManagers")
                    card.wait_for(state="visible")
                    # Sits between Team summary and Trade opportunities.
                    order = page.evaluate("() => [...document.querySelectorAll('#v2LgSummary, #v2LgManagers, #v2LgOpps')].map(n => n.id)")
                    self.assertEqual(order, ["v2LgSummary", "v2LgManagers", "v2LgOpps"])
                    ids = page.evaluate("() => { const ws = window.TradeValueWorkspace.store.get(); return {mine: ws.myTeamId, all: ws.teams.map(t => t.id)}; }")
                    listed = page.evaluate("() => [...document.querySelectorAll('#v2MgTeams li')].map(li => li.dataset.teamId)")
                    self.assertEqual(listed, [t for t in ids["all"] if t != ids["mine"]], "every team but mine, in league order")
                    first = card.locator("li.v2-mg-team").first
                    team_id = first.get_attribute("data-team-id")
                    self.assertIn("Not described yet", first.locator(".v2-mg-summary").text_content())
                    # Describe: keyboard-reachable disclosure with labelled selects.
                    first.locator("details.v2-mg-describe > summary").click()
                    first.locator("select[id^='v2MgA-draft-']").select_option("strong")
                    first.locator("select[id^='v2MgA-names-']").select_option("some")
                    first.locator("select[id^='v2MgConf-']").select_option("low")
                    summary = first.locator(".v2-mg-summary").text_content()
                    self.assertIn("Mixed", summary)
                    self.assertIn("draft capital (a lot)", summary)
                    self.assertIn("A guess", summary)
                    unlabeled = page.evaluate("() => [...document.querySelectorAll('#v2LgManagers select, #v2LgManagers textarea, #v2LgManagers input[type=checkbox]')].filter(n => !n.labels || !n.labels.length).length")
                    self.assertEqual(unlabeled, 0)
                    # Exclusion.
                    second = card.locator("li.v2-mg-team").nth(1)
                    second_id = second.get_attribute("data-team-id")
                    second.locator("input.v2-mg-excl").check()
                    self.assertIn("Won't trade", second.locator(".v2-mg-summary").text_content())
                    eligible = page.evaluate("() => { const M = window.TradeValueManagerProfiles; return M.eligibleOpponents(M.store.get(), window.TradeValueWorkspace.store.get()).map(r => r.teamId); }")
                    self.assertNotIn(second_id, eligible)
                    self.assertNotIn(ids["mine"], eligible)
                    # No trade numbers moved (stage 1 changes nothing in Trade opportunities).
                    page.wait_for_timeout(500)
                    self.assertEqual(page.evaluate(OPP_ROWS), before)
                    # Saved and reloaded; the league itself is unchanged.
                    page.evaluate("() => { window.TradeValueManagerProfiles.store.flush(); window.TradeValueWorkspace.store.flush(); }")
                    page.reload(wait_until="networkidle")
                    page.wait_for_selector("#v2LgManagers:not([hidden])", timeout=60000)
                    stored = json.loads(page.evaluate("() => localStorage.getItem('ddf.v2.managerProfiles')"))
                    league_id = page.evaluate("() => window.TradeValueWorkspace.store.get().id")
                    self.assertEqual(stored["leagues"][league_id][team_id]["anchors"]["draft"], "strong")
                    self.assertTrue(stored["leagues"][league_id][second_id]["excluded"])
                    self.assertTrue(page.locator(f"#v2LgManagers li[data-team-id='{second_id}'] input.v2-mg-excl").is_checked())
                    saved_league = page.evaluate("() => localStorage.getItem('ddf.v2.workspaces')")
                    self.assertNotIn("anchors", saved_league, "profiles are not written into the saved league")
                    self.assertEqual([t["id"] for t in json.loads(saved_league)["workspaces"][0]["teams"]], ids["all"])
                    # Rename keeps the profile.
                    page.evaluate(f"() => window.TradeValueWorkspace.store.update(w => window.TradeValueWorkspace.ops.renameTeam(w, {json.dumps(team_id)}, 'Renamed Manager'))")
                    row = page.locator(f"#v2LgManagers li[data-team-id='{team_id}']")
                    self.assertEqual(row.locator(".v2-mg-name").text_content(), "Renamed Manager")
                    self.assertIn("Mixed", row.locator(".v2-mg-summary").text_content())
                    if width == 390:
                        self.assertLessEqual(page.evaluate("document.documentElement.scrollWidth"), 400)
                        target = page.evaluate("() => { const r = document.querySelector('#v2LgManagers .v2-mg-excl-label').getBoundingClientRect(); return r.height; }")
                        self.assertGreaterEqual(target, 44)
                    self.assertEqual(errors, [])
                    context.close()


if __name__ == "__main__":
    unittest.main()
