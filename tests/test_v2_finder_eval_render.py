"""v2 Find a trade v2 (JEG-988), commit 3: roster balance and the evaluation sentences, rendered.

Two real roster pages (the Yahoo and ESPN team fixtures) go into the boxes at 1440 and 390 wide. Checked against the
engine's own allocation and rows, computed here independently of finder.js:

  * a partial roster shows no judgement, only when it will appear; a full one shows two sentences ("Based on
    fundamentals, your roster is ..." and "Based on market pricing, ..." and "their roster" on the other side) and the
    position table, whose counts and over / under words equal the independent computation in both views;
  * the kept kicker and defense are named "present, not evaluated" and never counted as depth;
  * after Find trades the same sentences stand in the team summary above the results, also when no trade is found;
  * no page errors, no sideways scroll at 390.

Discrimination: test_guard_fails_on_broken_builds serves finder.js with the market view reading DDF Value, the
over / under words swapped, and the roster evaluation left out of the summary, and requires each to fail.
"""
from __future__ import annotations

import functools
import unittest
from pathlib import Path

from tests import _render_env
from tests.test_published_league_settings_render import _chromium_executable
from tests.test_v2_finder_box_render import FIXTURE, OVER
from tests.test_v2_finder_render import FINDER_JS, PICK, _built_dist, add
from tests.test_v2_modules_render import _serve

ESPN = FIXTURE.with_name("espn-team.txt")


def setUpModule():
    _render_env.ensure_built()


# What the table must say, from the engine: players per position with a usable value in each view against the expected range.
WANT = """(side) => {
  const C = window.TradeValueCurveControls;
  const teams = C.getState().teams;
  const alloc = Object.fromEntries(C.getAdjustmentWeights().allocation.map(a => [a.pos, a]));
  const avail = new Set(C.getSourceInfo().filter(i => i.available).map(i => i.key));
  const charts = ['usatoday', 'fantasycalc', 'fantasypros', 'cbs'].filter(k => avail.has(k));
  const byName = new Map(C.getAllRows().map(r => [r.name, r]));
  const names = [...document.querySelectorAll(`#v2Find${side}Players li.v2-find-row b`)].map(b => b.textContent).filter(n => byName.has(n));
  const rows = names.map(n => byName.get(n));
  const usable = v => typeof v === 'number' && Number.isFinite(v) && v >= 0.05;
  const avg = r => { const vals = charts.map(k => r.values[k]); return vals.every(v => typeof v === 'number' && Number.isFinite(v)) ? vals.reduce((a, b) => a + b, 0) / vals.length : null; };
  const out = {};
  for (const pos of ['QB', 'RB', 'WR', 'TE']) {
    const x = alloc[pos].rostered / teams, lo = Math.floor(x + 1e-9), hi = Math.ceil(x - 1e-9);
    const mine = rows.filter(r => r.pos === pos);
    const word = n => (n < lo ? 'underweight' : n > hi + 1 ? 'overweight' : 'ok');
    const f = mine.filter(r => usable(r.values.ddf_value)).length, m = mine.filter(r => usable(avg(r))).length;
    out[pos] = {range: lo === hi ? String(lo) : `${lo}-${hi}`, fund: `${f} ${word(f)}`, market: `${m} ${word(m)}`};
  }
  return out;
}"""
TABLE = """(side) => [...document.querySelectorAll(`#v2Find${side}Eval tbody tr`)].map(tr => [...tr.children].map(c => c.textContent))"""


def check(page, tag, width) -> list[str]:
    errors = []
    say = lambda what: errors.append(tag + what)
    page.wait_for_function("() => window.TradeValueV2 && window.TradeValueV2.view() && document.getElementById('v2Find') && window.DDFRosterPaste", timeout=60000)
    page.evaluate("() => { location.hash = '#find-trade'; }")
    page.wait_for_function("() => !document.getElementById('v2FindTrade').hidden", timeout=20000)
    pick = page.evaluate(PICK)
    for name in pick["mine"][:3]:
        add(page, "Mine", name)
    partial = page.text_content("#v2FindMineEval") or ""
    if "Roster balance shows once" not in partial or "Based on" in partial:
        say(f"a three-player roster reads {partial!r}")
    page.fill("#v2FindMineSearch", FIXTURE.read_text(encoding="utf-8"))
    page.fill("#v2FindTheirsSearch", ESPN.read_text(encoding="utf-8"))
    page.wait_for_timeout(500)
    for side, who in (("Mine", "your"), ("Theirs", "their")):
        lines = page.evaluate("(s) => [...document.querySelectorAll(`#v2Find${s}Eval .v2-find-eval-line`)].map(p => p.textContent)", side)
        if len(lines) != 2 or not lines[0].startswith(f"Based on fundamentals, {who} roster is ") or not lines[1].startswith(f"Based on market pricing, {who} roster is "):
            say(f"{side}: the evaluation lines are {lines}")
        if lines and "starting lineup is worth" not in lines[0]:
            say(f"{side}: no lineup value in the sentence: {lines[0][:120]}")
        want = page.evaluate(WANT, side)
        table = page.evaluate(TABLE, side)
        for pos, expect, fund, market in table:
            w = want[pos]
            if (expect, fund, market) != (w["range"], w["fund"], w["market"]):
                say(f"{side} {pos}: table says {expect} / {fund} / {market}, engine says {w}")
        if len(table) != 4:
            say(f"{side}: {len(table)} table rows")
        # The words in the sentences agree with the table.
        for i, view_idx in ((0, 2), (1, 3)):
            for pos, *cells in table:
                status = cells[view_idx - 1].split()[1]
                sentence = lines[i] if len(lines) == 2 else ""
                said = {"underweight": f"underweight at", "overweight": "overweight at"}
                if status in said:
                    chunk = sentence.split(said[status])[1] if said[status] in sentence else ""
                    if f"{pos} (" not in chunk:
                        say(f"{side} {pos}: the table says {status} but the sentence does not name it: {sentence[:160]}")
        text = page.text_content(f"#v2Find{side}Eval")
        if "present, not evaluated" not in text:
            say(f"{side}: the kicker and defense are not named as not evaluated")
    # After Find: the summary carries the evaluation.
    page.click("#v2FindGo")
    page.wait_for_timeout(600)
    summary = page.text_content("#v2FindTeams") or ""
    for need in ("Based on fundamentals, your roster is", "Based on market pricing, their roster is", "Based on fundamentals, their roster is"):
        if need not in summary:
            say(f"the team summary lacks {need!r}")
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


class FinderEvalRenderTest(unittest.TestCase):
    def test_evaluation(self):
        self.assertEqual(run_checks(), [])

    def test_guard_fails_on_broken_builds(self):
        js = FINDER_JS.read_text(encoding="utf-8")
        cases = {
            "market view reads DDF Value": ('{id: "market", word: "market pricing", unit: "trade chart average", key: MARKET_KEY, rows: marketRows}',
                                            '{id: "market", word: "market pricing", unit: "trade chart average", key: OUR_KEY, rows}'),
            "over and under swapped": ('const status = have < e.lo ? "under" : have > e.hi + 1 ? "over" : "ok";', 'const status = have < e.lo ? "over" : have > e.hi + 1 ? "under" : "ok";'),
            "summary without the evaluation": ("const evaluation = evaluationNode(who, true);", "const evaluation = el(\"div\", {hidden: \"\"}); evaluation.hidden = true;"),
        }
        for name, (old, new) in cases.items():
            with self.subTest(name):
                self.assertIn(old, js, f"stale anchor for {name!r}")
                self.assertTrue(broken({"finder.js": js.replace(old, new, 1)}), f"not caught: {name}")


if __name__ == "__main__":
    unittest.main()
