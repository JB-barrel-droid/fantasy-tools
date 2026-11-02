"""JEG-1389: the "Use league rosters" switch redraws every player line, and a flip prices like a reload.

The USO rosters from tests/fixtures/league_levels/uso.json on the built page. Each team's player lines show DDF Value
chips. Flipping the switch changes every number (the standard bench, or the league's own rosters at the DDF level), so
the lines have to be drawn again: before the fix they kept the other level's values until the roster itself changed.

Checks under Standard, Half PPR and PPR, for every player line and team total:
  - switched off, a line shows the standard bench (getAllRows), and the same values after a reload with the switch off;
  - switched on, a line shows the DDF level (getLeagueLevel), and the on and off lines differ for some players.
  - placing starter-level JSN in an ordinary BN slot does not change his market prices or source roles.
"""
from __future__ import annotations

import unittest

from tests import _render_env
from tests._league_render import browser_on_build, open_page
from tests.test_jeg1249_league_site_render import PASTED, SEED, settle, uso
from tests.test_jeg1389_link_settings_reload_render import SCORINGS, USO_QUERY

# Each team's player lines as drawn ({team id: [[key, chip text], ...]}), and what the engine prices them at, at the
# standard bench and at the DDF level (same shape, one decimal like the chip).
LINES = """() => { const W = window.TradeValueWorkspace, C = window.TradeValueCurveControls, ws = W.store.get();
  const fmt = v => Number.isFinite(v) ? v.toFixed(1) : 'no value';
  const std = new Map(C.getAllRows().map(r => [String(r.player_key), r]));
  const out = {drawn: {}, standard: {}, ddf: {}, totals: {}, standardTotals: {}, ddfTotals: {}};
  let ddf = null;
  try {
    // The league page's own rostered and reserve keys (league.js leagueCheck), then the engine's DDF level for them.
    const check = window.ValueModel.leagueCompleteness({teamsExpected: C.getState().teams, now: Date.now(), startingSlotsPerTeam: 0,
      teams: ws.teams.map(t => ({id: t.id, unresolved: 0, loadedAt: Date.now(),
        players: t.entries.filter(e => !['K', 'DEF', 'DST'].includes(e.pos)).map(e => ({key: e.key, slot: e.slot}))}))});
    const got = C.getLeagueLevel({rostered: check.rostered, reserve: check.reserve, level: 'ddf'});
    ddf = got ? new Map(got.rows.map(r => [String(r.player_key), r])) : null;
  } catch (error) { ddf = null; }
  ws.teams.forEach(t => {
    const body = document.getElementById(`v2LgBody-${t.id}`);
    const rows = body ? [...body.querySelectorAll('.v2-lg-row')] : [];
    out.drawn[t.id] = rows.map((row, i) => { const chip = row.querySelector('.v2-find-chip[data-kind="ddf"] .v2-find-chip-value');
      return [t.entries[i] && t.entries[i].key, chip ? chip.textContent : null]; }).filter(([, text]) => text !== null);
    out.standard[t.id] = out.drawn[t.id].map(([k]) => [k, std.get(k) ? fmt(std.get(k).values.ddf_value) : null]);
    out.ddf[t.id] = out.drawn[t.id].map(([k]) => [k, ddf && ddf.get(k) ? fmt(ddf.get(k).values.ddf_value) : null]);
    const cell = document.querySelector(`tr[data-team-id="${t.id}"] [data-cell="rosterF"]`);
    const sum = byKey => fmt(t.entries.reduce((s, e) => s + (byKey?.get(e.key)?.values.ddf_value || 0), 0));
    out.totals[t.id] = cell ? cell.textContent : null;
    out.standardTotals[t.id] = sum(std);
    out.ddfTotals[t.id] = sum(ddf);
  });
  return out; }"""

# Jeremy: "When a starter level player is on your bench, the market still values them as a starter."
# Move JSN between an ordinary WR slot and BN without changing ownership, reserve status, or inputs.
SLOT_PRICES = """() => {
  const C = window.TradeValueCurveControls, ws = window.TradeValueWorkspace.store.get();
  const rostered = ws.teams.flatMap(t => t.entries.filter(e => ['QB', 'RB', 'WR', 'TE'].includes(e.pos)).map(e => e.key));
  const setting = {league_rostered: rostered, league_reserve: [], bench_level: 'market'};
  const market = C.getLeagueLevel({rostered, reserve: [], level: 'market'});
  const run = window.TradeValueCurveHarness.runPipelineWith({setting});
  return {standard: C.getAllRows().find(r => String(r.player_key) === '3247').values,
    market: market.rows.find(r => String(r.player_key) === '3247').values,
    roles: Object.values(run.sources).map(s => s.players['3247']?.role).filter(Boolean)};
}"""

MOVE_JSN = """slot => {
  const W = window.TradeValueWorkspace;
  W.store.update(ws => {
    const team = ws.teams.find(t => t.entries.some(e => e.key === '3247'));
    return W.ops.setEntries(ws, team.id, team.entries.map(e => e.key === '3247' ? {...e, slot} : e));
  }, 'entries');
  return W.store.get().teams.flatMap(t => t.entries).find(e => e.key === '3247').slot;
}"""


def setUpModule():
    _render_env.ensure_built()


class SwitchRedrawTest(unittest.TestCase):
    def setUp(self):
        self.fx = uso()
        self.problems = []

    def read(self, page):
        return page.evaluate(LINES)

    def test_switch_redraws_lines_and_matches_reload(self):
        for scoring in SCORINGS:
            with self.subTest(scoring=scoring):
                self.check_scoring(scoring)

    def check_scoring(self, scoring):
        with browser_on_build() as (browser, base):
            page = open_page(browser, base, errors=self.problems, tag="[jeg1389] ")
            page.evaluate("query => window.TradeValueV2.applyLinkLeague(new URLSearchParams(query), {save: true})",
                          USO_QUERY.replace("half_ppr", scoring))
            settle(page)
            page.evaluate(SEED, [self.fx["league"]["teams"], self.fx["mine"], PASTED, {}, {}])
            settle(page)
            self.assertTrue(page.evaluate("() => document.getElementById('v2LgUseLeague').checked"), "league rosters not on")
            on = self.read(page)
            drawn = sum(len(v) for v in on["drawn"].values())
            self.assertGreater(drawn, 100, "too few player lines drawn to check")
            # The DDF level is the league page's DDF Value (league.js levels.rows take DDF Value from the ddf run).
            self.assertEqual(on["drawn"], on["ddf"], "switched on, the lines do not show the DDF level")
            self.assertEqual(on["totals"], on["ddfTotals"], "team totals do not show the DDF level")

            page.click("#v2LgUseLeague")
            settle(page)
            off = self.read(page)
            self.assertEqual(off["drawn"], off["standard"], "switched off, the lines still show the league level")
            self.assertEqual(off["totals"], off["standardTotals"], "team totals do not show the standard bench")
            moved = [k for t in on["drawn"] for (k, a), (_, b) in zip(on["drawn"][t], off["drawn"][t]) if a != b]
            self.assertGreater(len(moved), 10, "the two levels drew the same lines; the check proves nothing")

            page.wait_for_timeout(1500)
            page.reload(wait_until="networkidle")
            page.wait_for_function("() => window.TradeValueLeague && window.TradeValueLeague.ui.ready", timeout=60000)
            settle(page)
            reloaded = self.read(page)
            self.assertEqual(reloaded["drawn"], off["drawn"], "a reload with the switch off draws other values than the flip")
            self.assertEqual(reloaded["totals"], off["totals"], "a reload changes team totals with the switch off")
            self.assertFalse(page.locator("#v2LgUseLeague").is_checked(), "the saved off choice was lost")

            page.click("#v2LgUseLeague")
            settle(page)
            back = self.read(page)
            self.assertEqual(back["drawn"], back["ddf"], "switched back on after a reload, the lines do not show the DDF level")
            self.assertEqual(back["drawn"], on["drawn"], "switched on after a reload, the lines differ from the first load")
            self.assertEqual(back["totals"], on["totals"], "a reload changes team totals with the switch on")
            self.assertEqual(page.evaluate(MOVE_JSN, "WR"), "WR")
            settle(page)
            starter = page.evaluate(SLOT_PRICES)
            self.assertIn("starter", starter["roles"], "JSN is not starter-level in any source; the ruling check proves nothing")
            self.assertEqual(page.evaluate(MOVE_JSN, "BN"), "BN")
            settle(page)
            benched = page.evaluate(SLOT_PRICES)
            self.assertEqual(benched, starter, "an ordinary bench slot changed a starter-level player's market price or role")
            print(f"\n{scoring}, team totals: on {list(on['totals'].values())}, "
                  f"off {list(off['totals'].values())}, reload {list(reloaded['totals'].values())}")
        self.assertEqual(self.problems, [])


if __name__ == "__main__":
    unittest.main()
