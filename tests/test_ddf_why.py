"""JEG-1561: the "Why" panel for a trade (app/next/ddf-why.js, window.DDFWhy) on find.html offer cards.

What we guard:
- Table-driven trades on hand-made rows where DDF Value and the Analyst charts differ (Natural fit with both teams
  gaining, Natural fit with their side inside tradeFit's tolerance, a need fill, 2-for-1 consolidation, FLEX
  re-slotting, an unpriced player, no fit): every number DDFWhy.explain reports (starter change by position, FLEX
  moves, starter / weighted bench / net change for both teams) equals an independent call of
  TradeValueFinder.lineupValue and tradeFit in the same browser; needs and surpluses equal tradeFit's depth readout
  (towardAt / awayAt / depth); "Natural fit" = tradeFit natural AND need received / surplus given for both teams; the
  headline never claims their side gains when their net is under the 0.05 floor; each case carries its reasons.
- Drift: the same checks fail when ddf-why.js is served with one number nudged.
- The % slot shows DDFOpportunity.rosterImprovementPct's shown / label verbatim, and hides when it is absent or null.
- Not judged (no chart average for an Analyst charts valuation): explain returns null.
- DDFWhy.text never says "DDF" or a team name.
- find.html with the seeded league at 1440x900 and 390x844: every judged offer card has a Why button (44px tall on
  390), it opens with the keyboard, shows the headline, the 3-row table, 1-3 reasons, the chart link, and the starter
  change in its numbers toggle equals the card's own (find-engine) value; copy rules hold.
"""
from __future__ import annotations

import re
import unittest

from tests import _render_env
from tests._dist_server import DIST, serve
from tests.test_find_engine_parity import APPLY, READY
from tests.test_team_engine_parity import seed_script, seeded_league

SETUP = r"""() => {
  // ddf, the three analyst charts [cbs, usatoday, fantasypros] (their mean is the Analyst charts value), projections = ddf
  const R = (key, name, pos, d, c) => ({player_key: key, name, pos, team: 'X', values: d === null ? {} :
    {ddf_value: d, ddf_value_charts: d, ddf_value_projections: d, cbs: c[0], usatoday: c[1], fantasypros: c[2], fantasycalc: d}});
  const mine = [R('m1','Mike Quinn','QB',30,[28,30,32]), R('m2','Mark Rush','RB',12,[10,12,14]), R('m3','Max Run','RB',9,[8,9,10]), R('m4','Mel Back','RB',4,[3,4,5]),
    R('m5','Matt Wide','WR',40,[36,40,44]), R('m6','Mo Wide','WR',38,[35,38,41]), R('m7','Milo Wide','WR',30,[26,30,34]), R('m8','Marv Wide','WR',22,[8,14,20]),
    R('m9','Mack Wide','WR',18,[15,18,21]), R('m10','Moss Wide','WR',15,[13,15,17]), R('m11','Mint Wide','WR',12,[10,12,14]), R('m12','Mule Wide','WR',8,[6,8,10]),
    R('m13','Moe End','TE',15,[13,15,17])];
  const theirs = [R('t1','Tom Quill','QB',28,[26,28,30]), R('t2','Ty Run','RB',40,[38,40,42]), R('t3','Tad Run','RB',36,[34,36,38]), R('t4','Tim Run','RB',31,[29,31,33]),
    R('t5','Tab Run','RB',28,[26,30,34]), R('t6','Toby Run','RB',20,[18,20,22]), R('t7','Troy Run','RB',15,[13,15,17]), R('t8','Tate Run','RB',10,[9,10,11]),
    R('t9','Tug Run','RB',5,[4,5,6]), R('t10','Ted Wide','WR',10,[9,10,11]), R('t11','Tod Wide','WR',9,[8,9,10]), R('t12','Tuck Wide','WR',3,[2,3,4]),
    R('t13','Tyr End','TE',14,[12,14,16]), R('t14','Tex Pick','RB',null)];
  const by = k => mine.concat(theirs).find(r => r.player_key === k);
  // Pinned so the cases do not move with the engine's settings: 12-team expected depth, one bench weight.
  const expected = {QB: {lo: 1, hi: 2}, RB: {lo: 5, hi: 5}, WR: {lo: 5, hi: 6}, TE: {lo: 1, hi: 2}};
  const shape = {QB: 1, RB: 2, WR: 2, TE: 1, FLEX: 1, SUPERFLEX: 0, BENCH: 7};
  const ctx = Object.assign({}, DDF.find.context(), {shape, expected, weights: {overall: 0.15}, analyst: ['cbs', 'usatoday', 'fantasypros'], ourKey: 'ddf_value', marketKey: 'chart_avg'});
  window.__why = {mine, theirs, by, ctx};
  return true;
}"""

# name: (give, receive, reasons that must be there, natural expected)
CASES = {
    "natural, both gain": (["m9"], ["t5"], {"need", "partner"}, True),
    "natural, their side within tolerance": (["m11"], ["t5"], {"need", "partner"}, True),
    "need 1-for-1": (["m7"], ["t4"], {"need"}, None),
    "consolidation 2-for-1": (["m10", "m12"], ["t4"], {"spots"}, None),
    "flex re-slot": (["m7", "m8"], ["t2", "t3", "t4"], {"flex"}, None),
    "unpriced player": (["m4"], ["t14"], {"unvalued"}, False),
    "no fit": (["m5"], ["t12"], {"loss"}, False),
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
    return {pos, flex, starter: +(a.starterValue - b.starterValue).toFixed(6)};
  };
  const posOf = rows => POS.filter(p => rows.some(x => x.pos === p));
  const need = (t, rec) => t.ready ? POS.filter(p => rec.includes(p) && t.towardAt.includes(p)) : [];
  const spare = (t, giv) => t.ready ? POS.filter(p => giv.includes(p) && t.depth[p] && !t.awayAt.includes(p) && t.depth[p].statusAfter !== 'under') : [];
  const needs = {you: need(fit.us, posOf(Rv)), them: need(fit.them, posOf(G)), youSurplus: spare(fit.us, posOf(G)), themSurplus: spare(fit.them, posOf(Rv))};
  return {you: side(M, G, Rv, 'ddf_value'), them: side(T, Rv, G, 'chart_avg'), needs,
    fitUs: [+fit.us.starterDelta.toFixed(6), +fit.us.benchDelta.toFixed(6), +fit.us.net.toFixed(6)],
    fitThem: [+fit.them.starterDelta.toFixed(6), +fit.them.benchDelta.toFixed(6), +fit.them.net.toFixed(6)],
    themNet: fit.them.net, themTau: fit.them.tau, label: fit.label,
    natural: fit.label === 'natural' && needs.you.length > 0 && needs.youSurplus.length > 0 && needs.them.length > 0 && needs.themSurplus.length > 0};
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


def case_errors(page) -> list[str]:
    """Every table-driven case against the independent finder read; a list of mismatches (empty = all match)."""
    errors = []
    page.evaluate(SETUP)
    for name, (give, receive, must, natural) in CASES.items():
        want, got = page.evaluate(ORACLE, [give, receive]), page.evaluate(EXPLAIN, [give, receive])
        for k in ("you", "them"):
            if got[k] != want[k]:
                errors.append(f"{name}: {k} why={got[k]} finder={want[k]}")
        for k in ("fitUs", "fitThem", "natural", "needs"):
            if got[k] != want[k]:
                errors.append(f"{name}: {k} why={got[k]} finder={want[k]}")
        if natural is not None and want["natural"] != natural:
            errors.append(f"{name}: case expects natural={natural}, finder says {want['natural']} (label {want['label']})")
        if not must <= set(got["kinds"]):
            errors.append(f"{name}: reasons {got['kinds']} miss {sorted(must - set(got['kinds']))}")
        if not 1 <= got["n"] <= 3:
            errors.append(f"{name}: {got['n']} reasons")
        # Finding 1: never imply their side gains under the floor.
        gains = "their roster gets better" in got["headline"]
        if got["headline"] != "This does not make your team better." and gains != (want["themNet"] >= 0.05):
            errors.append(f"{name}: headline {got['headline']!r} vs their net {want['themNet']:.3f}")
        if got["headline"] != "This does not make your team better." and -want["themTau"] <= want["themNet"] < 0.05 and "about even, within how much the sources disagree" not in got["headline"]:
            errors.append(f"{name}: inside tolerance but headline {got['headline']!r}")
        if got["pct"] is not None or "data-pct" in got["html"]:
            errors.append(f"{name}: % shown without DDFOpportunity")
        if got["text"].count("\n- ") != got["n"]:
            errors.append(f"{name}: text reasons {got['text']!r}")
        hits = [b for b in BANNED if re.search(b, got["text"])]
        if hits:
            errors.append(f"{name}: banned words in text {hits}")
        if name == "natural, their side within tolerance" and not (want["themNet"] < 0.05):
            errors.append(f"{name}: their net {want['themNet']:.3f} is not under the floor (case drifted)")
        if name == "unpriced player" and (got["top"][:1] != ["unvalued"] or got["table"]["get"][0]["role"] != "no value yet"):
            errors.append(f"{name}: unpriced player not disclosed first: {got['top']} {got['table']['get']}")
        if name == "no fit" and (got["headline"] != "This does not make your team better." or "need" in got["kinds"]):
            errors.append(f"{name}: {got['headline']!r} {got['kinds']}")
        if name == "consolidation 2-for-1" and not any("opens a roster spot" in t for t in got["texts"]):
            errors.append(f"{name}: no roster spot reason {got['texts']}")
    return errors


class DDFWhyTest(unittest.TestCase):
    def setUp(self):
        try:
            from playwright.sync_api import sync_playwright
        except Exception as exc:  # noqa: BLE001
            raise _render_env.unavailable(f"Playwright not available: {exc}") from exc
        if not (DIST / "find.html").exists() or not (DIST / "ddf-why.js").exists():
            raise _render_env.unavailable("dist/find.html or dist/ddf-why.js is not built")
        self.sync_playwright = sync_playwright

    def _cases(self, overrides=None):
        with serve(DIST, overrides) as base, self.sync_playwright() as pw:
            browser = _launch(pw)
            try:
                page, errors = _find_page(browser, base, 1440, 900, _league())
                found = case_errors(page)
                extra = page.evaluate(r"""() => {
                  const {mine, theirs, by, ctx} = window.__why, t = {mine, theirs, give: [by('m9')], receive: [by('t5')]};
                  window.DDFOpportunity = {rosterImprovementPct: (tr, side) => side === 'sender'
                    ? {side, pct: 4.2, shown: '+4.2%', label: 'a fair ask'} : {side, pct: -1.1, shown: '-1.1%', label: 'a fair ask'}};
                  const on = DDFWhy.explain(t, ctx).pct;
                  window.DDFOpportunity = {rosterImprovementPct: (tr, side) => ({side, pct: null, shown: null, label: null})};
                  const off = DDFWhy.explain(t, ctx).pct;
                  delete window.DDFOpportunity;
                  const unjudged = DDFWhy.explain(t, Object.assign({}, ctx, {analyst: null}));
                  return {on: on && on.text, off, unjudged};
                }""")
                return found, extra, errors
            finally:
                browser.close()

    def test_cases_match_finder(self):
        found, extra, errors = self._cases()
        self.assertEqual(found, [], "\n".join(found))
        self.assertEqual(extra, {"on": "Your roster +4.2%. Theirs -1.1%, a fair ask.", "off": None, "unjudged": None})
        self.assertEqual(errors, [])

    def test_guard_fails_on_drift(self):
        src = (DIST / "ddf-why.js").read_text()
        needle = "posDelta[p] = at(a) - at(b);"
        self.assertIn(needle, src)
        found, _, _ = self._cases({"ddf-why.js": src.replace(needle, "posDelta[p] = at(a) - at(b) + 0.01;").encode()})
        self.assertTrue(any(": you why=" in e or ": them why=" in e for e in found), f"drift not caught: {found[:3]}")

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
                    judged = page.locator('[data-offer]:not([data-you=""])').count()   # an unjudged card (no fit) has no Why
                    self.assertGreater(judged, 0, f"{w}: no judged offer cards")
                    self.assertEqual(page.locator("[data-offer] details[data-why] > summary").count(), judged)
                    cards = page.locator('[data-offer]:not([data-you=""])')
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
