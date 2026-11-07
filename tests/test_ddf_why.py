"""JEG-1561: the "Why" panel for a trade (app/next/ddf-why.js, window.DDFWhy) on find.html offer cards.

What we guard:
- Table-driven trades on hand-made rows (1-for-1 need fit, 2-for-1 consolidation, FLEX re-slotting, an unpriced player,
  no fit): every number DDFWhy.explain reports (starter change by position, slot moves, starter / weighted bench / net
  change for both teams) equals an independent call of TradeValueFinder.lineupValue and tradeFit in the same browser,
  "Natural fit" is tradeFit's natural label AND need lining up both ways, and each case carries the reasons it must.
- The % slot shows DDFOpportunity.rosterImprovementPct's shown / label verbatim, and hides when it is absent or null.
- DDFWhy.text never says "DDF" or a team name.
- find.html with the seeded league at 1440x900 and 390x844: every offer card has a Why button (44px tall on 390), it
  opens with the keyboard, shows the headline, the 3-row table, 1-3 reasons, the chart link, and the starter change
  in its numbers toggle equals the card's own (find-engine) value; copy rules hold.
"""
from __future__ import annotations

import re
import unittest

from tests import _render_env
from tests._dist_server import DIST, serve
from tests.test_find_engine_parity import APPLY, READY
from tests.test_team_engine_parity import seed_script, seeded_league

SETUP = r"""() => {
  const V = v => ({ddf_value: v, ddf_value_charts: v, ddf_value_projections: v, cbs: v, usatoday: v, fantasypros: v, fantasycalc: v});
  const R = (key, name, pos, v) => ({player_key: key, name, pos, team: 'X', values: v === null ? {} : V(v)});
  const mine = [R('m1', 'Mike Quinn', 'QB', 30), R('m2', 'Mark Rush', 'RB', 12), R('m3', 'Max Run', 'RB', 9), R('m4', 'Matt Wide', 'WR', 40),
    R('m5', 'Mo Wide', 'WR', 38), R('m6', 'Milo Wide', 'WR', 30), R('m7', 'Marv Wide', 'WR', 22), R('m8', 'Moe End', 'TE', 15),
    R('m9', 'Mel Back', 'RB', 4), R('m10', 'Mitch Pass', 'QB', 6)];
  const theirs = [R('t1', 'Tom Quill', 'QB', 28), R('t2', 'Ty Run', 'RB', 40), R('t3', 'Tad Run', 'RB', 36), R('t4', 'Tim Run', 'RB', 31),
    R('t5', 'Ted Wide', 'WR', 14), R('t6', 'Tod Wide', 'WR', 10), R('t7', 'Tyr End', 'TE', 14), R('t8', 'Tab Back', 'RB', 5),
    R('t9', 'Tuck Wide', 'WR', 3), R('t10', 'Tex Pick', 'RB', null)];
  const by = k => mine.concat(theirs).find(r => r.player_key === k);
  const ctx = Object.assign({}, DDF.find.context(), {shape: {QB: 1, RB: 2, WR: 2, TE: 1, FLEX: 1, SUPERFLEX: 0, BENCH: 6}, ourKey: 'ddf_value', marketKey: 'chart_avg'});
  window.__why = {mine, theirs, by, ctx};
  return true;
}"""

CASES = {
    "need 1-for-1": (["m6"], ["t4"], {"need", "partner"}),
    "consolidation 2-for-1": (["m7", "m9"], ["t3"], {"spots"}),
    "flex re-slot": (["m6", "m7"], ["t3", "t4"], {"flex"}),
    "unpriced player": (["m9"], ["t10"], {"unvalued"}),
    "no fit": (["m4"], ["t9"], {"loss"}),
}

ORACLE = r"""([give, receive]) => {
  const F = window.TradeValueFinder, {mine, theirs, by, ctx} = window.__why;
  const POS = ['QB', 'RB', 'WR', 'TE'];
  const g = give.map(by), r = receive.map(by);
  const w = rows => F.withChartAverage(rows, ctx.analyst);
  const M = w(mine), T = w(theirs), byKey = new Map(M.concat(T).map(x => [x.player_key, x]));
  const G = g.map(x => byKey.get(x.player_key)), Rv = r.map(x => byKey.get(x.player_key));
  const fit = F.tradeFit({mine: {roster: M, leaving: G, arriving: Rv}, theirs: {roster: T, leaving: Rv, arriving: G}},
    {shape: ctx.shape, expected: ctx.expected, weights: ctx.weights, ourKey: 'ddf_value', marketKey: 'chart_avg', chartKeys: ctx.analyst, z: F.FIT_Z});
  const side = (roster, out, inn, key) => {
    const gone = new Set(out.map(x => x.player_key));
    const after = roster.filter(x => !gone.has(x.player_key)).concat(inn);
    const b = F.lineupValue(roster, ctx.shape, key), a = F.lineupValue(after, ctx.shape, key);
    const at = (l, p) => l.starters.filter(x => x.pos === p).reduce((t, x) => t + x.values[key], 0);
    const pos = {}; POS.forEach(p => { pos[p] = +(at(a, p) - at(b, p)).toFixed(6); });
    const flex = {from: (b.slots.FLEX || []).map(x => x.pos).join(), to: (a.slots.FLEX || []).map(x => x.pos).join()};
    const need = []; inn.forEach(x => { if (a.starters.includes(x) && pos[x.pos] >= 0.05 && !need.includes(x.pos)) need.push(x.pos); });
    return {pos, flex, need, starter: +(a.starterValue - b.starterValue).toFixed(6)};
  };
  const you = side(M, G, Rv, 'ddf_value'), them = side(T, Rv, G, 'chart_avg');
  return {you, them, fitUs: [+fit.us.starterDelta.toFixed(6), +fit.us.benchDelta.toFixed(6), +fit.us.net.toFixed(6)],
    fitThem: [+fit.them.starterDelta.toFixed(6), +fit.them.benchDelta.toFixed(6), +fit.them.net.toFixed(6)],
    natural: fit.label === 'natural' && you.need.length > 0 && them.need.length > 0};
}"""

EXPLAIN = r"""([give, receive]) => {
  const {mine, theirs, by, ctx} = window.__why;
  const e = DDFWhy.explain({mine, theirs, give: give.map(by), receive: receive.map(by)}, ctx);
  const s = v => ({pos: Object.fromEntries(Object.entries(v.posDelta).map(([k, x]) => [k, +x.toFixed(6)])),
    flex: {from: (v.slots.FLEX || {from: []}).from.join(), to: (v.slots.FLEX || {to: []}).to.join()}, starter: +v.starterDelta.toFixed(6)});
  const t = DDFWhy.text({mine, theirs, give: give.map(by), receive: receive.map(by)}, ctx);
  return {you: s(e.you), them: s(e.them), needs: e.needs, natural: e.natural, headline: e.headline, table: e.table,
    fitUs: [+e.you.starterDelta.toFixed(6), +e.you.benchDelta.toFixed(6), +e.you.net.toFixed(6)],
    fitThem: [+e.them.starterDelta.toFixed(6), +e.them.benchDelta.toFixed(6), +e.them.net.toFixed(6)],
    kinds: e.allReasons.map(r => r.kind), texts: e.allReasons.map(r => r.text), top: e.reasons.map(r => r.kind), n: e.reasons.length, pct: e.pct, text: t,
    html: DDFWhy.html({mine, theirs, give: give.map(by), receive: receive.map(by)}, ctx, {})};
}"""

BANNED = [r"\bDDF\b", r"player pool", r"(?<!Live )\bMarket\b", r"\bdemo\b", r"\bsample\b", r"\bmock", r"illustrative", r"\bchoose\b", r"\bset up\b"]


def _launch(pw):
    try:
        return pw.chromium.launch(args=_render_env.HERMETIC_ARGS, executable_path=_render_env.chromium_executable())
    except Exception as exc:  # noqa: BLE001
        raise _render_env.unavailable(f"Chromium not available: {exc}") from exc


def _find_page(browser, base, w, h, league):
    page = browser.new_page(viewport={"width": w, "height": h})
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.route(lambda u: not u.startswith(base), lambda r: r.abort())
    page.add_init_script(seed_script(league))
    page.goto(f"{base}/find.html", wait_until="domcontentloaded", timeout=60000)
    page.evaluate(APPLY, ["ppr", 12, False])
    page.wait_for_timeout(300)
    page.wait_for_function(READY, timeout=120000)
    return page, errors


def _league():
    lg = seeded_league()
    del lg["teams"][lg["me"]]["players"][1:3]
    return lg


class DDFWhyTest(unittest.TestCase):
    def setUp(self):
        try:
            from playwright.sync_api import sync_playwright
        except Exception as exc:  # noqa: BLE001
            raise _render_env.unavailable(f"Playwright not available: {exc}") from exc
        if not (DIST / "find.html").exists() or not (DIST / "ddf-why.js").exists():
            raise _render_env.unavailable("dist/find.html or dist/ddf-why.js is not built")
        self.sync_playwright = sync_playwright

    def test_cases_match_finder(self):
        with serve(DIST) as base, self.sync_playwright() as pw:
            browser = _launch(pw)
            try:
                page, errors = _find_page(browser, base, 1440, 900, _league())
                page.evaluate(SETUP)
                for name, (give, receive, must) in CASES.items():
                    want, got = page.evaluate(ORACLE, [give, receive]), page.evaluate(EXPLAIN, [give, receive])
                    for k in ("you", "them"):
                        self.assertEqual(got[k], {x: want[k][x] for x in ("pos", "flex", "starter")}, f"{name}: {k}")
                    for k in ("fitUs", "fitThem", "natural"):
                        self.assertEqual(got[k], want[k], f"{name}: {k}")
                    self.assertEqual(got["needs"], {"you": want["you"]["need"], "them": want["them"]["need"]}, name)
                    self.assertTrue(must <= set(got["kinds"]), f"{name}: reasons {got['kinds']} miss {must - set(got['kinds'])}")
                    self.assertTrue(1 <= got["n"] <= 3, f"{name}: {got['n']} reasons")
                    self.assertIsNone(got["pct"], f"{name}: % shown without DDFOpportunity")
                    self.assertNotIn("data-pct", got["html"])
                    self.assertEqual(got["text"].count("\n- "), got["n"])
                    hits = [b for b in BANNED if re.search(b, got["text"])]
                    self.assertEqual(hits, [], f"{name}: banned words in text {hits}")
                    if name == "unpriced player":
                        self.assertEqual(got["top"][0], "unvalued")
                        self.assertEqual(got["table"]["get"][0]["role"], "no value yet")
                    if name == "no fit":
                        self.assertEqual(got["headline"], "This does not make your team better.")
                        self.assertNotIn("need", got["kinds"])
                        self.assertFalse(got["natural"])
                    if name == "consolidation 2-for-1":
                        self.assertTrue(any("opens a roster spot" in t for t in got["texts"]), got["texts"])
                # The % slot: shown / label verbatim from DDFOpportunity, hidden when pct is null.
                pct = page.evaluate(r"""() => {
                  const {mine, theirs, by, ctx} = window.__why, t = {mine, theirs, give: [by('m6')], receive: [by('t4')]};
                  window.DDFOpportunity = {rosterImprovementPct: (tr, side) => side === 'sender'
                    ? {side, pct: 4.2, shown: '+4.2%', label: 'a fair ask'} : {side, pct: -1.1, shown: '-1.1%', label: 'a fair ask'}};
                  const on = DDFWhy.explain(t, ctx).pct;
                  window.DDFOpportunity = {rosterImprovementPct: (tr, side) => ({side, pct: null, shown: null, label: null})};
                  const off = DDFWhy.explain(t, ctx).pct;
                  delete window.DDFOpportunity;
                  return {on: on && on.text, off};
                }""")
                self.assertEqual(pct, {"on": "Your roster +4.2%. Theirs -1.1%, a fair ask.", "off": None})
                self.assertEqual(errors, [])
            finally:
                browser.close()

    def test_why_button_on_find_cards(self):
        league = _league()
        teams = [t["name"] for t in league["teams"]]
        with serve(DIST) as base, self.sync_playwright() as pw:
            browser = _launch(pw)
            try:
                for w, h in ((1440, 900), (390, 844)):
                    page, errors = _find_page(browser, base, w, h, league)
                    cards = page.locator("[data-offer]")
                    self.assertGreater(cards.count(), 0, f"{w}: no offer cards")
                    self.assertEqual(page.locator("[data-offer] details[data-why] > summary").count(), cards.count())
                    summary = cards.first.locator("details[data-why] > summary")
                    box = summary.bounding_box()
                    self.assertGreaterEqual(box["height"], 44, f"{w}: Why button {box['height']}px")
                    summary.focus()
                    page.keyboard.press("Enter")
                    body = cards.first.locator(".why-body")
                    body.wait_for(state="visible", timeout=5000)
                    self.assertTrue(body.locator(".why-head").inner_text().strip())
                    self.assertEqual([x.strip() for x in body.locator(".why-table th").all_inner_texts()], ["You give up", "You get", "Net"])
                    self.assertTrue(1 <= body.locator(".why-reasons li").count() <= 3)
                    self.assertRegex(body.locator("a[data-charts]").inner_text(), r"^\d+/\d+ public trade charts$")
                    # The numbers toggle's starter change equals the card's (find-engine tradeFit) value.
                    card_you = cards.first.get_attribute("data-you")
                    raw = body.locator(".why-raw tr").nth(1).locator("td").first.text_content().strip()
                    if card_you:
                        shown = lambda n: "0.0" if abs(n) < 0.05 else ("+" if n > 0 else "−") + f"{abs(n):.1f}"
                        self.assertEqual(raw, shown(float(card_you)))
                    text = body.inner_text()
                    hits = [b for b in BANNED if re.search(b, text)] + [t for t in teams if t in text]
                    self.assertEqual(hits, [], f"{w}: banned words or team names in the Why panel: {hits}")
                    overflow = page.evaluate("() => document.documentElement.scrollWidth > document.documentElement.clientWidth + 1")
                    self.assertFalse(overflow, f"{w}: horizontal overflow with Why open")
                    self.assertEqual(errors, [])
                    page.close()
            finally:
                browser.close()


if __name__ == "__main__":
    unittest.main()
