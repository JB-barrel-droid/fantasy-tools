"""JEG-1230: the shared trade readout on the built page, with real engine rows, drawn by the existing lineup table."""
from __future__ import annotations

import unittest

from tests._league_render import browser_on_build, fixture, open_page

BUILD = """([fx]) => {
  const C = window.TradeValueCurveControls, F = window.TradeValueFinder, R = window.TradeValueReadout;
  const all = new Map(C.getAllRows().map(r => [String(r.player_key), r]));
  const team = t => ({rows: t.players.map(p => all.get(p.key)).filter(Boolean), entries: t.players.map(p => ({key: p.key, name: p.name, pos: p.pos}))});
  const mine = team(fx.teams[0]), theirs = team(fx.teams[1]);
  const priced = (rows, pos) => rows.find(r => r.pos === pos && Number.isFinite(r.values?.[F.OUR_KEY]));
  const give = [priced(mine.rows, 'RB')], receive = [priced(theirs.rows, 'WR')];
  const info = C.getSourceInfo ? C.getSourceInfo() : [];
  const charts = F.CHART_KEYS.filter(k => info.some(i => i.key === k && i.available));
  const shape = C.getRosterShape();
  const out = R.build({shape, ourKey: F.OUR_KEY, chartKeys: charts, sourceInfo: info, mine, theirs,
    give: give.map(r => r.player_key), receive: receive.map(r => r.player_key)});
  const direct = F.rosterImpact(mine.rows, give, receive, shape, F.OUR_KEY);
  const host = document.createElement('section');
  host.id = 'jeg1230Harness';
  host.setAttribute('aria-label', 'Readout harness');
  [['mine', 'Your team'], ['theirs', 'Their team']].forEach(([who, label]) => R.VIEWS.forEach(v =>
    host.appendChild(R.renderSide(out, who, v.id, `${label}: best starting lineup in ${v.label}`))));
  // Inside the visible league page (the body's other children are the hidden legacy engine).
  const card = document.getElementById('v2LgCard');
  card.parentElement.insertBefore(host, card);
  return {ready: out.ready, same: out.sides.mine.ddf.starterDelta === direct.starterDelta && out.sides.mine.ddf.benchDelta === direct.benchDelta,
    statuses: Object.fromEntries(Object.entries(out.views).map(([id, v]) => [id, v.status])),
    notEvaluated: out.sides.mine.ddf.notEvaluated.length + out.sides.theirs.ddf.notEvaluated.length};
}"""


# JEG-1260: the Mac's empty-TE 2-for-1 in synthetic rows, one outgoing player with no DDF Value. Visible words only.
SYNTHETIC = """([missingTwo]) => {
  const F = window.TradeValueFinder, R = window.TradeValueReadout, L = window.TradeValueLineupComparison;
  const row = (key, pos, v) => ({player_key: key, name: key, pos, values: pos === 'K' || pos === 'DEF' ? {} : Object.fromEntries(
    [[F.OUR_KEY, v]].concat(F.CHART_KEYS.map(k => [k, v === null ? null : v * 1.02])))});
  const team = list => list.map(([k, pos, v]) => row(k, pos, v === undefined ? null : v));
  const mine = team([['eQB1','QB',21],['eQB2','QB',8],['eRB1','RB',20],['eRB2','RB',15],['eRB3','RB',9],['eRB4','RB',null],['eRB5','RB',3],
    ['eWR1','WR',19],['eWR2','WR',16],['eWR3','WR',12],['eWR4','WR',7],['eWR5','WR',4],['eWR6','WR',missingTwo ? null : 2],['eK','K'],['eDEF','DEF']]);
  const theirs = team([['oQB1','QB',20],['oQB2','QB',7],['oRB1','RB',22],['oRB2','RB',13],['oRB3','RB',8],['oRB4','RB',5],['oRB5','RB',2],
    ['oWR1','WR',18],['oWR2','WR',14],['oWR3','WR',9],['oWR4','WR',6],['oWR5','WR',3],['oTE1','TE',12],['oTE2','TE',4],['oK','K'],['oDEF','DEF']]);
  const shape = {QB: 1, RB: 2, WR: 2, TE: 1, FLEX: 1, SUPERFLEX: 0, K: 1, DST: 1, BENCH: 7};
  const out = R.build({shape, ourKey: F.OUR_KEY, chartKeys: F.CHART_KEYS.slice(), mine: {rows: mine}, theirs: {rows: theirs},
    give: ['eRB4', 'eWR5'], receive: ['oTE1']});
  const host = document.createElement('section');
  host.id = 'jeg1260Harness';
  [['mine', 'Your team'], ['theirs', 'Their team']].forEach(([who, label]) =>
    host.appendChild(R.renderSide(out, who, 'ddf', `${label}: best starting lineup in DDF Value`)));
  const card = document.getElementById('v2LgCard');
  card.parentElement.insertBefore(host, card);
  const rows = L.buildRows(out.sides.mine.ddf.impact.before, out.sides.mine.ddf.impact.after, shape).bench.length;
  return {rows, physicalAfter: out.roster.mine.after.bench};
}"""


class TradeReadoutRenderTest(unittest.TestCase):
    def test_readout_renders_with_lineup_table_keyboard_and_phone(self):
        fx = fixture("20team")
        with browser_on_build() as (browser, base):
            for width in (1366, 390):
                with self.subTest(width=width):
                    errors = []
                    page = open_page(browser, base, width=width, height=844, errors=errors)
                    result = page.evaluate(BUILD, [fx])
                    self.assertTrue(result["ready"])
                    self.assertTrue(result["same"], "readout must equal finder.rosterImpact on the same rows")
                    self.assertEqual(result["statuses"]["ddf"], "available")
                    host = page.locator("#jeg1230Harness")
                    self.assertTrue(host.is_visible(), "the harness must sit in the visible page")
                    for status, view in ((result["statuses"][v], v) for v in ("ddf", "market", "projections")):
                        node = host.locator(f'.v2-readout-view[data-view="{view}"]').first
                        if status == "available":
                            self.assertEqual(node.locator("table.v2-lineup-comparison").count(), 1)
                        else:
                            self.assertEqual(node.locator("table").count(), 0, "an unavailable view shows a reason, not a table")
                            self.assertIn(":", node.inner_text())
                    wrapper = host.locator('.v2-readout-view[data-view="ddf"] .v2-lineup-comparison-wrap').first
                    toggle = wrapper.locator("button.v2-lineup-bench-toggle")
                    bench = wrapper.locator("tbody.v2-lineup-bench-rows")
                    self.assertEqual(toggle.get_attribute("aria-expanded"), "false")
                    self.assertEqual(bench.get_attribute("id"), toggle.get_attribute("aria-controls"))
                    self.assertTrue(bench.is_hidden())
                    toggle.focus()
                    page.keyboard.press("Enter")
                    self.assertEqual(toggle.get_attribute("aria-expanded"), "true")
                    self.assertTrue(bench.is_visible())
                    page.keyboard.press("Space")
                    self.assertEqual(toggle.get_attribute("aria-expanded"), "false")
                    self.assertEqual(wrapper.locator("caption").first.inner_text().startswith("Your team: best starting lineup in DDF Value"), True)
                    if result["notEvaluated"]:
                        self.assertIn("Kickers and defenses are not evaluated", host.inner_text())
                    overflow = page.evaluate("() => document.documentElement.scrollWidth - window.innerWidth")
                    self.assertLessEqual(overflow, 1, "the readout must not widen the page")
                    self.assertEqual(errors, [])
                    page.context.close()


    def test_roster_bench_and_missing_counts_are_the_visible_words(self):
        with browser_on_build() as (browser, base):
            for width in (1366, 390):
                for missing_two in (False, True):
                    with self.subTest(width=width, missing_two=missing_two):
                        errors = []
                        page = open_page(browser, base, width=width, height=844, errors=errors)
                        result = page.evaluate(SYNTHETIC, [missing_two])
                        views = page.locator("#jeg1260Harness .v2-readout-view")
                        mine, theirs = views.nth(0), views.nth(1)
                        self.assertTrue(mine.is_visible())
                        text = mine.inner_text()
                        self.assertIn("Roster: 15 → 14 players (−1).", text)
                        self.assertIn("Bench: 7 → 5 of 7 spots used (−2).", text)
                        self.assertNotIn("Over the bench limit", text)
                        self.assertIn("DDF replacement depth (bench players with a usable value):", text)
                        if missing_two:
                            self.assertIn("2 players have no DDF Value and are left out of this lineup.", text)
                        else:
                            self.assertIn("1 player has no DDF Value and is left out of this lineup.", text,
                                          "the outgoing unpriced player is counted once")
                            self.assertNotIn("2 players have no DDF Value", text)
                        their_text = theirs.inner_text()
                        self.assertIn("Roster: 16 → 17 players (+1).", their_text)
                        self.assertIn("Bench: 7 → 8 of 7 spots used (+1).", their_text)
                        self.assertIn("Over the bench limit by 1 after the trade; no player is dropped automatically.", their_text)
                        toggle = mine.locator("button.v2-lineup-bench-toggle")
                        rows = result["rows"]
                        self.assertNotEqual(rows, result["physicalAfter"], "this case separates display rows from the After bench")
                        self.assertEqual(toggle.inner_text(), f"Show {rows} bench rows")
                        toggle.focus()
                        page.keyboard.press("Enter")
                        self.assertEqual(toggle.inner_text(), f"Hide {rows} bench rows")
                        self.assertEqual(toggle.get_attribute("aria-expanded"), "true")
                        overflow = page.evaluate("() => document.documentElement.scrollWidth - window.innerWidth")
                        self.assertLessEqual(overflow, 1)
                        self.assertEqual(errors, [])
                        page.context.close()


if __name__ == "__main__":
    unittest.main()
