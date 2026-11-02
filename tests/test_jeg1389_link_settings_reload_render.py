"""JEG-1389 (Jeremy's pick A, 2026-10-30): a league share link's settings survive a reload.

The USO league (tests/fixtures/league_levels/uso.json) shared as a #find-league link that carries USO's settings: half
PPR, 12 teams, QB1 RB2 WR3 TE1 FLEX1, 5 bench. Opening the link applies them (league.js applyImported, through
TradeValueV2.applyLinkLeague). Before the fix they were not saved, so a reload priced the league at the site's defaults
(PPR, 2 WR, 7 bench): Kyren Williams 45.9 at the standard bench instead of 55.8.

Checks under Standard, Half PPR and PPR, after opening the link and again after a reload:
  - the engine holds USO's scoring, team count and roster;
  - all six reported players keep their standard-bench values; with CBS explicitly shown (the local server holds
    CBS), Kyren is not priced at the default settings' value, read on the same inputs before the link was opened.
The numbers move with each input refresh (55.8 / 45.9 on the inputs of 2026-10-30 at c7c8800b, 54.3 at USO's settings
after the next comparison rebuild), so the test compares settings on one set of inputs instead of pinning a number.
"""
from __future__ import annotations

import unittest

from tests import _render_env
from tests._league_render import browser_on_build, open_page
from tests.test_jeg1249_league_site_render import settle, uso

KYREN = "1063"
USO_QUERY = "scoring=half_ppr&teams=12&roster=QB1.RB2.WR3.TE1.FLEX1.SF0.BN5"
SCORINGS = ("standard", "half_ppr", "ppr")
SENTINELS = ("3247", "1063", "869", "164", "4485", "2575")

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
  const live = H.runPipelineWith({hidden: []});
  return {scoring: st.scoring, teams: st.teams, roster: {QB: shape.QB, RB: shape.RB, WR: shape.WR, TE: shape.TE, FLEX: shape.FLEX, BENCH: shape.BENCH},
    teamsLoaded: window.TradeValueWorkspace.store.get().teams.length,
    sentinels: Object.fromEntries(['3247', '1063', '869', '164', '4485', '2575'].map(k => [k, live.rows[k]?.ddfByVersion.blended.value ?? null])),
    kyren: row ? Number(row.values.ddf_value.toFixed(1)) : null,
    kyrenHarness: ddf(H.runPipelineWith()), kyrenLive: ddf(live)}; }"""

USO = {"scoring": "half_ppr", "teams": 12, "roster": {"QB": 1, "RB": 2, "WR": 3, "TE": 1, "FLEX": 1, "BENCH": 5}}


def setUpModule():
    _render_env.ensure_built()


class LinkSettingsReloadTest(unittest.TestCase):
    def setUp(self):
        self.fx = uso()
        self.problems = []

    def check_uso(self, got, when, scoring="half_ppr"):
        expected = {**USO, "scoring": scoring}
        self.assertEqual({k: got[k] for k in expected}, expected, f"{when}: the engine does not hold USO's settings "
                         f"(Kyren Williams {got['kyren']} drawn, {got['kyrenLive']} with CBS shown)")

    def test_share_link_settings_survive_reload(self):
        for scoring in SCORINGS:
            with self.subTest(scoring=scoring):
                self.check_scoring(scoring)

    def check_scoring(self, scoring):
        # Each scoring gets a fresh browser; saved settings cannot leak between cases.
        with browser_on_build() as (browser, base):
            page = open_page(browser, base, errors=self.problems, tag="[jeg1389-link] ")
            settle(page)
            fresh = page.evaluate(READ, KYREN)   # nothing saved yet: the site's defaults
            self.assertNotEqual({k: fresh[k] for k in USO}, USO, "the defaults already are USO's settings; the check proves nothing")
            query = USO_QUERY.replace("half_ppr", scoring)
            hash_ = page.evaluate(LINK, [self.fx["league"]["teams"], self.fx["mine"], query])
            self.assertTrue(hash_.startswith("#find-league?"), hash_[:40])

            # A fresh load of the link (a hash-only goto would stay on the same document).
            page.goto("about:blank")
            page.goto(base + hash_, wait_until="networkidle")
            page.wait_for_function("() => window.TradeValueLeague && window.TradeValueLeague.ui.ready", timeout=60000)
            page.wait_for_function("() => window.TradeValueWorkspace.store.get().teams.length > 0", timeout=60000)
            settle(page)
            opened = page.evaluate(READ, KYREN)
            self.check_uso(opened, "after opening the link", scoring)
            self.assertGreater(opened["teamsLoaded"], 0)
            # Check the drawn values separately from the explicitly CBS-visible diagnostic run.
            self.assertEqual(opened["kyrenHarness"], opened["kyren"], "the harness does not price Kyren Williams as the page does")

            page.wait_for_timeout(1500)
            page.reload(wait_until="networkidle")
            page.wait_for_function("() => window.TradeValueLeague && window.TradeValueLeague.ui.ready", timeout=60000)
            settle(page)
            reloaded = page.evaluate(READ, KYREN)
            print(f"\n{scoring}, JSN/Kyren/Allen/Jones/Goedert/Hockenson with CBS shown: "
                  f"defaults {[round(fresh['sentinels'][k], 1) for k in SENTINELS]}, "
                  f"link {[round(opened['sentinels'][k], 1) for k in SENTINELS]}, "
                  f"reload {[round(reloaded['sentinels'][k], 1) for k in SENTINELS]}")
            self.check_uso(reloaded, "after a reload", scoring)
            self.assertEqual(reloaded["sentinels"], opened["sentinels"], "a reload changes the six approved players' values")
            self.assertEqual(reloaded["teamsLoaded"], 12)
            self.assertEqual(reloaded["kyren"], opened["kyren"], "a reload prices Kyren Williams differently from the link")
            self.assertEqual(reloaded["kyrenLive"], opened["kyrenLive"], "with CBS shown, a reload prices Kyren Williams differently from the link")
            self.assertNotEqual(reloaded["kyrenLive"], fresh["kyrenLive"], "with CBS shown, a reload prices Kyren Williams at the default settings")
            print(f"\nKyren Williams with CBS shown: defaults {fresh['kyrenLive']}, link {opened['kyrenLive']}, reload {reloaded['kyrenLive']}")
        self.assertEqual(self.problems, [])


if __name__ == "__main__":
    unittest.main()
