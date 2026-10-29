"""Combined JEG-1214/1216/1184 browser flow on the release candidate."""
from __future__ import annotations

import unittest

from tests import _render_env
from tests.test_v2_finder_render import _built_dist


def setUpModule():
    _render_env.ensure_built()


class InteractiveTradesReleaseRenderTest(unittest.TestCase):
    def test_compare_lineups_and_finder_settings(self):
        from playwright.sync_api import sync_playwright

        with _built_dist() as base, sync_playwright() as playwright:
            browser = playwright.chromium.launch(args=_render_env.HERMETIC_ARGS,
                                                 executable_path=_render_env.chromium_executable(playwright))
            try:
                page = browser.new_page(viewport={"width": 1100, "height": 900})
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.goto(base + "#compare-trade", wait_until="networkidle")
                page.locator("#v2CConstruction").wait_for(state="attached", timeout=60000)
                keys = page.evaluate("""() => {
                  const rows = window.TradeValueCurveControls.getAllRows()
                    .filter(r => ['RB', 'WR', 'TE'].includes(r.pos) && Number.isFinite(r.values.ddf_value))
                    .sort((a, b) => b.values.ddf_value - a.values.ddf_value).slice(0, 24);
                  if (rows.length !== 24) throw Error('need 24 priced roster players');
                  const entry = r => ({key: String(r.player_key), name: r.name, pos: r.pos});
                  const W = window.TradeValueWorkspace;
                  let ws = W.ops.addTeam(W.newWorkspace(), 'Mine', {entries: rows.slice(0, 12).map(entry), mine: true});
                  ws = W.ops.addTeam(ws, 'Theirs', {entries: rows.slice(12).map(entry)});
                  W.store.replace(ws, 'release-test');
                  return {mine: rows.slice(0, 12).map(r => String(r.player_key)),
                    theirs: rows.slice(12).map(r => String(r.player_key))};
                }""")
                mine_id = page.locator("#v2CMyTeam").input_value()
                their_id = page.locator("#v2CTheirTeam").input_value()
                page.locator("#v2CEditRosters").click()
                mine = page.locator("#v2CRosterLists section").first
                theirs = page.locator("#v2CRosterLists section").last
                mine.locator("button").nth(0).click()
                mine.locator("button").nth(1).click()
                theirs.locator("button").nth(0).click()
                self.assertEqual(page.locator("#v2CConstruction").get_attribute("data-ready"), "true")
                self.assertEqual(page.locator("#v2CConstruction table.v2-lineup-comparison").count(), 2)
                self.assertGreater(page.locator("#v2CConstruction tr[data-changed='false']").count(), 0)
                self.assertIn("Opens 1 roster/bench spot", page.locator("#v2CConstruction").inner_text())
                toggle = page.locator("#v2CConstruction .v2-lineup-bench-toggle").first
                toggle.click()
                self.assertEqual(toggle.get_attribute("aria-expanded"), "true")
                self.assertGreater(page.locator("#v2CConstruction .v2-lineup-bench-rows").first.locator("tr").count(), 0)
                page.locator("#v2CEditRosters").click()  # Keep a baseline trade.
                page.locator("#v2CEditRosters").click()
                page.locator("#v2CSwap").click()
                page.locator("#v2CCancelRosterEdit").click()
                self.assertEqual(page.locator("#v2CMyTeam").input_value(), mine_id)
                self.assertEqual(page.locator("#v2CTheirTeam").input_value(), their_id)
                self.assertEqual(page.locator("#v2CConstruction").get_attribute("data-ready"), "true")
                self.assertEqual(page.locator("#v2GivePlayers li[data-player-key]").count(), 2)
                page.locator("#v2CEditRosters").click()
                page.evaluate("""ids => { location.hash = `#compare-trade?give=${ids[0]}&get=${ids[1]}`; }""",
                              [keys["mine"][2], keys["theirs"][1]])
                page.wait_for_timeout(300)
                self.assertEqual(page.locator("#v2CCancelRosterEdit").count(), 0)
                self.assertEqual(page.locator("#v2GivePlayers li[data-player-key]").first.get_attribute("data-player-key"), keys["mine"][2])
                page.locator("#v2CEditRosters").click()
                page.evaluate("""ids => window.DDFAssist.applyLink(`give=${ids[0]}&get=${ids[1]}`)""",
                              [keys["mine"][3], keys["theirs"][2]])
                self.assertEqual(page.locator("#v2CCancelRosterEdit").count(), 0)
                self.assertEqual(page.locator("#v2GivePlayers li[data-player-key]").first.get_attribute("data-player-key"), keys["mine"][3])

                page.evaluate("() => { location.hash = '#find-trade'; }")
                page.locator("#v2FindProtectRB").wait_for(timeout=60000)
                self.assertFalse(page.locator("#v2FindProtectRB").is_checked())
                self.assertTrue(page.locator("#v2FindKeepMine").is_checked())
                self.assertEqual(page.locator("#v2FindMinMine").input_value(), "")
                parity = page.evaluate("""keys => {
                  const F = window.TradeValueFinder;
                  const byKey = new Map(window.TradeValueCurveControls.getAllRows().map(r => [String(r.player_key), r]));
                  const mine = keys.mine.slice(0, 4).map(k => byKey.get(k));
                  const theirs = keys.theirs.slice(0, 4).map(k => byKey.get(k));
                  const opts = {maxSize: 1, chartKeys: F.CHART_KEYS, limit: 10};
                  const signature = result => result.trades.map(t =>
                    [t.give.map(r => r.player_key), t.receive.map(r => r.player_key), t.edge]);
                  return {plain: signature(F.findTrades(mine, theirs, opts)),
                    inactive: signature(F.findTrades(mine, theirs, {...opts, guardrails:
                      {protectedPositions: [], minDdfEdge: 0, minUserLineupGain: null, minTheirLineupGain: null}}))};
                }""", keys)
                self.assertEqual(parity["plain"], parity["inactive"], "default recommendations moved")
                page.locator("#v2FindProtectRB").check()
                page.locator(".v2-find-advanced summary").click()
                page.locator("#v2FindMinEdge").fill("2")
                page.locator("#v2FindMinEdge").press("Tab")
                page.evaluate("window.TradeValueWorkspace.store.flush()")
                page.reload(wait_until="networkidle")
                page.locator("#v2FindProtectRB").wait_for(timeout=60000)
                self.assertTrue(page.locator("#v2FindProtectRB").is_checked())
                page.locator(".v2-find-advanced summary").click()
                self.assertEqual(page.locator("#v2FindMinEdge").input_value(), "2")
                linked = page.evaluate("""keys => window.TradeValueFinder.encodeFinderHash({
                  mine: [keys.mine[0]], theirs: [keys.theirs[0]], guardrails:
                  {protectedPositions: ['WR'], minDdfEdge: 3, minUserLineupGain: 0}})""", keys)
                page.goto(base + linked, wait_until="networkidle")
                page.locator("#v2FindProtectWR").wait_for(timeout=60000)
                self.assertTrue(page.locator("#v2FindProtectWR").is_checked())
                self.assertFalse(page.locator("#v2FindProtectRB").is_checked())
                page.locator(".v2-find-advanced summary").click()
                self.assertEqual(page.locator("#v2FindMinEdge").input_value(), "3")
                self.assertEqual(page.locator("#v2FindMinMine").input_value(), "0")
                self.assertEqual(errors, [])
            finally:
                browser.close()
