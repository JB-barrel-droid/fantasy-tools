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
  document.body.prepend(host);
  return {ready: out.ready, same: out.sides.mine.ddf.starterDelta === direct.starterDelta && out.sides.mine.ddf.benchDelta === direct.benchDelta,
    statuses: Object.fromEntries(Object.entries(out.views).map(([id, v]) => [id, v.status])),
    notEvaluated: out.sides.mine.ddf.notEvaluated.length + out.sides.theirs.ddf.notEvaluated.length};
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


if __name__ == "__main__":
    unittest.main()
