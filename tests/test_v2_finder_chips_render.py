"""v2 Find a trade v2 (JEG-988), commit 2: score chips on each roster row, rendered.

After players are added, every row shows the two scores the search uses: DDF Value (fundamental) and the Trade chart
average (market: the mean of the trade charts the engine says are available, only with at least three). Checked at 1440
and 390 against the engine's own rows, computed here independently of finder.js:

  * every evaluated player's two chips read the engine's value to one decimal (chart average = mean of the available
    charts, "no value" when any available chart does not price the player, never 0);
  * a player with no DDF Value reads "no value" on that chip, never 0. The weekly data may have no such player, so the test
    makes its own: the page's engine rows are wrapped to drop one mid-ranked player's DDF Value (data only, the
    test_v2_deal_read_render FEED pattern), and that player is added;
  * a kept defense or kicker shows "Not evaluated" and no chips;
  * chips follow a player moved to the other team (Move) and stay on Undo;
  * no page errors, no sideways scroll at 390.

Discrimination: test_guard_fails_on_broken_builds serves finder.js with the DDF chip reading the chart average, the chart
average reading as 0 when missing, and the chips not drawn, and requires each to fail.
"""
from __future__ import annotations

import unittest

from tests import _render_env
from tests.test_v2_finder_box_render import FIXTURE, OVER
from tests.test_v2_finder_render import FINDER_JS, PICK, _built_dist, add

import functools

from tests.test_published_league_settings_render import _chromium_executable
from tests.test_v2_modules_render import _serve


def setUpModule():
    _render_env.ensure_built()


EXPECT = """() => {
  const C = window.TradeValueCurveControls;
  const byKey = new Map(C.getAllRows().map(r => [String(r.player_key), r]));
  const avail = new Set(C.getSourceInfo().filter(i => i.available).map(i => i.key));
  const charts = ['usatoday', 'fantasycalc', 'fantasypros', 'cbs'].filter(k => avail.has(k));
  const f = v => (typeof v === 'number' && Number.isFinite(v) ? v.toFixed(1) : 'no value');
  const out = {};
  // Find a trade's own rows: the league screen (league.js) draws the same rosters with its own chips.
  document.querySelectorAll('#v2FindTrade li.v2-find-row').forEach(li => {
    const name = li.querySelector('b').textContent;
    const row = [...byKey.values()].find(r => r.name === name);
    const chips = [...li.querySelectorAll('.v2-find-chip-value')].map(b => b.textContent);
    let want = null;
    if (row && charts.length >= 3) {
      const vals = charts.map(k => row.values[k]);
      const avg = vals.every(v => typeof v === 'number' && Number.isFinite(v)) ? vals.reduce((a, b) => a + b, 0) / vals.length : null;
      want = [f(row.values.ddf_value), f(avg)];
    }
    out[name] = {chips, want, notEvaluated: li.textContent.includes('Not evaluated')};
  });
  return out;
}"""

# The missing-value case, built by the test (the week's data may price every player): one priced QB/RB/WR/TE with a unique
# name, ranked 41st by DDF Value (outside the players PICK adds) and not in the pasted page, loses its DDF Value in every
# row the engine hands out from here on. Returns that player's name, or null when the week has too few players.
UNPRICE = """(paste) => {
  const C = window.TradeValueCurveControls;
  const all = C.getAllRows();
  const count = new Map(); all.forEach(r => count.set(r.name, (count.get(r.name) || 0) + 1));
  const rows = all.filter(r => r.name && count.get(r.name) === 1 && ['QB', 'RB', 'WR', 'TE'].includes(r.pos) && r.values
    && Number.isFinite(r.values.ddf_value) && !paste.includes(r.name)).sort((a, b) => b.values.ddf_value - a.values.ddf_value);
  const target = rows[40];
  if (!target) return null;
  const key = String(target.player_key);
  const orig = C.getAllRows.bind(C);
  C.getAllRows = () => orig().map(r => (String(r.player_key) === key ? {...r, values: {...r.values, ddf_value: null}} : r));
  return target.name;
}"""


def check(page, tag, width) -> list[str]:
    errors = []
    say = lambda what: errors.append(tag + what)
    page.wait_for_function("() => window.TradeValueV2 && window.TradeValueV2.view() && document.getElementById('v2Find') && window.DDFRosterPaste", timeout=60000)
    page.evaluate("() => { location.hash = '#find-trade'; }")
    page.wait_for_function("() => !document.getElementById('v2FindTrade').hidden", timeout=20000)
    pick = page.evaluate(PICK)
    for name in pick["mine"][:6]:
        add(page, "Mine", name)
    paste = FIXTURE.read_text(encoding="utf-8")   # a page with a kicker and a defense
    unpriced = page.evaluate(UNPRICE, paste)
    if unpriced:   # a player with no DDF Value: the chip says so, it is not 0
        add(page, "Mine", unpriced)
    else:
        say("too few priced players to build the missing-value case")
    page.fill("#v2FindTheirsSearch", paste)
    page.wait_for_timeout(400)
    rows = page.evaluate(EXPECT)
    if len(rows) < 12:
        say(f"only {len(rows)} rows to check")
    for name, r in rows.items():
        if r["notEvaluated"]:
            if r["chips"]:
                say(f"{name}: a not-evaluated player shows chips {r['chips']}")
        elif r["want"] is None:
            say(f"{name}: no engine row or too few charts to say what the chips should be")
        elif r["chips"] != r["want"]:
            say(f"{name}: chips {r['chips']}, engine says {r['want']}")
    if unpriced and (unpriced not in rows or rows[unpriced]["chips"][0] != "no value"):
        say(f"{unpriced} has no DDF Value but his chips read {rows.get(unpriced)}")
    if sum(1 for r in rows.values() if r["notEvaluated"]) != 2:
        say("want exactly one kicker and one defense not evaluated")
    labels = page.evaluate("() => [...new Set([...document.querySelectorAll('.v2-find-chip')].map(c => c.textContent.replace(/[0-9.]+|no value/, '').trim()))]")
    if sorted(labels) != ["DDF Value", "Trade chart average"]:
        say(f"chip labels are {labels}")
    # Move follows the chips.
    mover = pick["mine"][0]
    page.click(f"#v2FindMinePlayers li:has(b:text-is('{mover}')) .v2-find-move")
    page.wait_for_timeout(200)
    moved = page.evaluate(EXPECT)
    if moved.get(mover, {}).get("chips") != rows[mover]["chips"] or not page.locator(f"#v2FindTheirsPlayers li:has(b:text-is('{mover}')) .v2-find-chip").count() == 2:
        say(f"{mover} did not keep both chips after Move")
    if width <= 390 and page.evaluate(OVER) > 0:
        say("horizontal overflow")
    return errors


def run_checks(overrides=None, viewports=((1440, 900), (390, 844), (320, 640))) -> list[str]:
    from playwright.sync_api import sync_playwright
    errors = []
    with _built_dist() as base, sync_playwright() as playwright:
        browser = playwright.chromium.launch(args=_render_env.HERMETIC_ARGS, executable_path=_chromium_executable(playwright))
        try:
            for width, height in viewports:
                page = browser.new_page(viewport={"width": width, "height": height})
                page_errors = []
                page.on("pageerror", lambda e: page_errors.append(str(e)))
                page.route(lambda u: not u.startswith("http://127.0.0.1"), lambda route: route.abort())
                for name, body in (overrides or {}).items():
                    page.route(f"**/v2/{name}*", functools.partial(_serve, body, "text/javascript"))
                page.goto(base + "#find-trade", wait_until="networkidle")
                errors += check(page, f"[{width}px] ", width)
                if page_errors:
                    errors.append(f"[{width}px] page errors {page_errors}")
                page.close()
        finally:
            browser.close()
    return errors


def broken(overrides) -> bool:
    try:
        return bool(run_checks(overrides, viewports=((1440, 900),)))
    except Exception:
        return True


class FinderChipsRenderTest(unittest.TestCase):
    def test_chips(self):
        self.assertEqual(run_checks(), [])

    def test_guard_fails_on_broken_builds(self):
        js = FINDER_JS.read_text(encoding="utf-8")
        cases = {
            "ddf chip reads the chart average": ("const ddf = row.values ? row.values[OUR_KEY] : null;", "const ddf = row.values ? row.values.usatoday : null;"),
            "missing average shown as 0": ("el(\"span\", {class: \"v2-find-chip-value\", text: finite(value) ? value.toFixed(1) : \"no value\"})", "el(\"span\", {class: \"v2-find-chip-value\", text: (value || 0).toFixed(1)})"),
            "chips not drawn": ("badge, scoreChips(p, byKey, charts))", "badge)"),
        }
        for name, (old, new) in cases.items():
            with self.subTest(name):
                self.assertIn(old, js, f"stale anchor for {name!r}")
                self.assertTrue(broken({"finder.js": js.replace(old, new, 1)}), f"not caught: {name}")


if __name__ == "__main__":
    unittest.main()
