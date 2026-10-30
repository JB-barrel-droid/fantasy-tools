"""JEG-1389 (Jeremy's pick A, 2026-10-30): a league share link's settings survive a reload.

The USO league (tests/fixtures/league_levels/uso.json) shared as a #find-league link that carries USO's settings: half
PPR, 12 teams, QB1 RB2 WR3 TE1 FLEX1, 5 bench. Opening the link applies them (league.js applyImported, through
TradeValueV2.applyLinkLeague). Before the fix they were not saved, so a reload priced the league at the site's defaults
(PPR, 2 WR, 7 bench): Kyren Williams 45.9 at the standard bench instead of 55.8.

Checks, after opening the link and again after a reload:
  - the engine holds USO's scoring, team count and roster;
  - the standard bench prices Kyren Williams the same both times, and with CBS shown (as on live, the local server holds
    CBS) he reads 55.8, not the default-settings 45.9.
"""
from __future__ import annotations

import unittest

from tests import _render_env
from tests._league_render import browser_on_build, open_page
from tests.test_jeg1249_league_site_render import settle, uso

KYREN = "1063"
USO_QUERY = "scoring=half_ppr&teams=12&roster=QB1.RB2.WR3.TE1.FLEX1.SF0.BN5"

# The USO teams as a share link with USO's settings (the league page's own Copy link encoder).
LINK = """([teams, mine, query]) => {
  const W = window.TradeValueWorkspace, C = window.TradeValueCurveControls;
  const byKey = new Map(C.getAllRows().map(r => [String(r.player_key), r]));
  let ws = W.newWorkspace({name: 'USO'});
  teams.forEach(t => {
    const entries = t.players.filter(p => p.key).map(p => { const row = byKey.get(p.key); return {key: p.key, name: row ? row.name : p.name, pos: p.pos, slot: p.slot}; });
    ws = W.ops.addTeam(ws, 'Team ' + t.id, {entries});
  });
  const m = teams.findIndex(t => t.id === mine);
  if (m >= 0) ws = W.ops.setMyTeam(ws, ws.teams[m].id);
  return W.shareHash(ws, query).hash; }"""

# What the engine is set to, and Kyren Williams at the standard bench: as drawn locally, and with CBS shown.
READ = """(key) => { const C = window.TradeValueCurveControls, st = C.getState(), shape = C.getRosterShape();
  const row = C.getAllRows().find(r => String(r.player_key) === key);
  const H = window.TradeValueCurveHarness;
  const ddf = run => { const r = run.rows && run.rows[key]; const v = r && r.ddfByVersion.blended.value; return Number.isFinite(v) ? Number(v.toFixed(1)) : null; };
  return {scoring: st.scoring, teams: st.teams, roster: {QB: shape.QB, RB: shape.RB, WR: shape.WR, TE: shape.TE, FLEX: shape.FLEX, BENCH: shape.BENCH},
    teamsLoaded: window.TradeValueWorkspace.store.get().teams.length,
    kyren: row ? Number(row.values.ddf_value.toFixed(1)) : null,
    kyrenHarness: ddf(H.runPipelineWith()), kyrenLive: ddf(H.runPipelineWith({hidden: []}))}; }"""

USO = {"scoring": "half_ppr", "teams": 12, "roster": {"QB": 1, "RB": 2, "WR": 3, "TE": 1, "FLEX": 1, "BENCH": 5}}


def setUpModule():
    _render_env.ensure_built()


class LinkSettingsReloadTest(unittest.TestCase):
    def setUp(self):
        self.fx = uso()
        self.problems = []

    def check_uso(self, got, when):
        self.assertEqual({k: got[k] for k in USO}, USO, f"{when}: the engine does not hold USO's settings "
                         f"(Kyren Williams {got['kyren']} drawn, {got['kyrenLive']} with CBS shown)")

    def test_share_link_settings_survive_reload(self):
        with browser_on_build() as (browser, base):
            page = open_page(browser, base, errors=self.problems, tag="[jeg1389-link] ")
            settle(page)
            hash_ = page.evaluate(LINK, [self.fx["league"]["teams"], self.fx["mine"], USO_QUERY])
            self.assertTrue(hash_.startswith("#find-league?"), hash_[:40])

            # A fresh load of the link (a hash-only goto would stay on the same document).
            page.goto("about:blank")
            page.goto(base + hash_, wait_until="networkidle")
            page.wait_for_function("() => window.TradeValueLeague && window.TradeValueLeague.ui.ready", timeout=60000)
            page.wait_for_function("() => window.TradeValueWorkspace.store.get().teams.length > 0", timeout=60000)
            settle(page)
            opened = page.evaluate(READ, KYREN)
            self.check_uso(opened, "after opening the link")
            self.assertGreater(opened["teamsLoaded"], 0)
            # The harness run with the page's own hidden set is what the page draws, so its CBS-shown run is live's number.
            self.assertEqual(opened["kyrenHarness"], opened["kyren"], "the harness does not price Kyren Williams as the page does")

            page.wait_for_timeout(1500)
            page.reload(wait_until="networkidle")
            page.wait_for_function("() => window.TradeValueLeague && window.TradeValueLeague.ui.ready", timeout=60000)
            settle(page)
            reloaded = page.evaluate(READ, KYREN)
            self.check_uso(reloaded, "after a reload")
            self.assertEqual(reloaded["kyren"], opened["kyren"], "a reload prices Kyren Williams differently from the link")
            self.assertEqual(reloaded["kyrenLive"], 55.8, "with CBS shown, Kyren Williams does not read USO's 55.8 after a reload")
        self.assertEqual(self.problems, [])


if __name__ == "__main__":
    unittest.main()
