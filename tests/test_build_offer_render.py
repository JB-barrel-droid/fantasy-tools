"""JEG-1559: the offer message section on build.html, rendered at 1440 and 390.

For a near-even 1-for-1, a lopsided trade in your favor, a 2-for-1 in a seeded league and a shop-a-player offer:
the option buttons are exactly DDFOffer.options() for the page's own offer input (ids and order), one is pressed and
it is the preselected one, the message box holds that option's text, a click on another option replaces the text,
Copy message reports success, the message never names the site or a team, and the page has no horizontal overflow.
Also the #trade-charts anchor: a trade link with it lands on the charts below the sticky header; without it, no scroll.
The shape rules themselves are table-tested in tests/node/build_offer_check.cjs.
"""
from __future__ import annotations

import unittest

from tests import _render_env
from tests._dist_server import DIST, serve

LIVE = "() => document.body.classList.contains('build-live')"
KEYS_JS = """() => window.DDF.engine.ready.then(() => DDF.engine.players().filter(p => p.ddf !== null && p.cbs !== null && p.usat !== null && p.fp !== null)
  .sort((a, b) => b.ddf - a.ddf).slice(0, 40).map(p => ({key: p.key, n: p.n, pos: p.pos, an: (p.cbs + p.usat + p.fp) / 3})))"""
SEED_JS = """(keys) => {
  try { localStorage.clear(); sessionStorage.clear(); } catch (e) {}
  if (!keys) return;
  const team = (id, name, list) => ({id, name, entries: list.map(k => ({key: k}))});
  localStorage.setItem('ddf.v2.workspaces', JSON.stringify({v: 1, activeId: 'w', workspaces: [{id: 'w', name: 'Offer League', myTeamId: 'a',
    teams: [team('a', 'Team Alpha', keys.filter((k, i) => i % 2 === 0)), team('b', 'Team Bravo', keys.filter((k, i) => i % 2 === 1))]}]}));
}"""
READ_JS = """() => {
  const want = DDFOffer.options(DDFBuild.offerInput());
  const buttons = [...document.querySelectorAll('#styles [data-style]')];
  const pressed = buttons.filter(b => b.getAttribute('aria-pressed') === 'true').map(b => b.dataset.style);
  return {wantIds: want.options.map(o => o.id), pre: want.preselect, texts: Object.fromEntries(want.options.map(o => [o.id, o.text])),
    ids: buttons.map(b => b.dataset.style), pressed, message: document.getElementById('message').value,
    summary: document.getElementById('offer-shape').textContent,
    why: !!document.querySelector('#build-why details.why'), partner: (DDFBuild.offerInput().partner || {}).band || null,
    overflow: Math.max(document.body.scrollWidth, document.documentElement.scrollWidth) > innerWidth + 1};
}"""


def setUpModule():
    _render_env.ensure_built()


class BuildOfferRenderTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            from playwright.sync_api import sync_playwright, Error as PlaywrightError
        except Exception as exc:
            raise _render_env.unavailable(f"Playwright not available: {exc}") from exc
        cls._serve = serve(DIST)
        cls.base = cls._serve.__enter__()
        cls._pw = sync_playwright().start()
        try:
            cls.browser = cls._pw.chromium.launch(args=_render_env.HERMETIC_ARGS, executable_path=_render_env.chromium_executable(cls._pw))
        except PlaywrightError as exc:
            cls._pw.stop(); cls._serve.__exit__(None, None, None)
            raise _render_env.unavailable(f"Chromium not available: {exc}") from exc
        page = cls.browser.new_page()
        page.add_init_script(f"({SEED_JS})(null)")
        page.goto(f"{cls.base}/build.html", wait_until="load", timeout=60000)
        cls.players = page.evaluate(KEYS_JS)
        page.close()

    @classmethod
    def tearDownClass(cls):
        cls.browser.close(); cls._pw.stop(); cls._serve.__exit__(None, None, None)

    def check(self, path, width, seed=None, expect_ids=None):
        ctx = self.browser.new_context(viewport={"width": width, "height": 900})
        ctx.grant_permissions(["clipboard-read", "clipboard-write"])
        page = ctx.new_page()
        self.addCleanup(ctx.close)
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.add_init_script(f"({SEED_JS})({seed!r})".replace("'", '"') if seed else f"({SEED_JS})(null)")
        page.goto(f"{self.base}{path}", wait_until="load", timeout=60000)
        page.wait_for_function(LIVE, timeout=60000)
        page.wait_for_selector("#styles [data-style]", timeout=20000)
        snap = page.evaluate(READ_JS)
        label = f"{path} @{width}"
        self.assertEqual(snap["ids"], snap["wantIds"], label)
        if expect_ids is not None:
            self.assertEqual(snap["ids"], expect_ids, label)
        self.assertEqual(snap["pressed"], [snap["pre"]], label)
        self.assertEqual(snap["message"], snap["texts"][snap["pre"]], label)
        self.assertTrue(snap["summary"], label)
        if seed:
            self.assertTrue(snap["why"], f"{label}: no Why panel in My league")
            self.assertIn(snap["partner"], ("better", "unchanged", "slightly_worse", "clearly_worse", "unsized"), label)
        self.assertFalse(snap["overflow"], f"{label}: horizontal overflow")
        for text in snap["texts"].values():
            self.assertNotRegex(text, r"DDF|Data Driven|Team Alpha|Team Bravo", label)
        others = [i for i in snap["ids"] if i != snap["pre"]]
        if others:
            page.click(f'#styles [data-style="{others[0]}"]')
            after = page.evaluate(READ_JS)
            self.assertEqual(after["pressed"], [others[0]], label)
            self.assertEqual(after["message"], snap["texts"][others[0]], label)
        page.click("#copy")
        page.wait_for_function("() => /copied/i.test(document.getElementById('copy-status').textContent)", timeout=5000)
        self.assertEqual(errors, [], label)
        return snap

    def test_offer_shapes_at_both_widths(self):
        p = self.players
        # Near even 1-for-1 and a trade the charts favor you in, by Analyst charts value.
        by_an = sorted(p, key=lambda x: x["an"])
        hi, lo = by_an[-1], by_an[0]
        near = min(((a, b) for a in p for b in p if a["key"] != b["key"]), key=lambda ab: abs(ab[0]["an"] - ab[1]["an"]))
        keys = [x["key"] for x in p[:32]]
        mine, theirs = keys[0::2], keys[1::2]
        for width in (1440, 390):
            snap = self.check(f"/build.html?give={near[0]['key']}&get={near[1]['key']}", width)
            self.assertIn("Analyst charts: near even", snap["summary"])
            snap = self.check(f"/build.html?give={lo['key']}&get={hi['key']}", width)
            self.assertIn("ask", snap["ids"]); self.assertEqual(snap["pre"], "ask")
            snap = self.check(f"/build.html?mode=league&give={mine[3]}&give={mine[6]}&get={theirs[2]}", width, seed=keys)
            self.assertIn("2-for-1 (you consolidate)", snap["summary"])
            # JEG-1558 / JEG-1561 modules on the page: the partner's roster % band reaches the offer, the Why panel shows.
            self.assertRegex(snap["summary"], r"(Their roster gets about [0-9.]+% (better|worse)|Their roster is about the same \([0-9.]+%\)|Not enough priced players)", snap["summary"])
            self.assertIn("consolidate", snap["ids"])
            self.check(f"/build.html?give={p[0]['key']}", width, expect_ids=["shop"])


    def test_trade_charts_anchor(self):
        """build.html?give=..&get=..#trade-charts lands on the charts below the sticky header; no anchor, no scroll."""
        a, b = self.players[0]["key"], self.players[5]["key"]
        for width in (1440, 390):
            for anchor in ("#trade-charts", ""):
                ctx = self.browser.new_context(viewport={"width": width, "height": 800})
                self.addCleanup(ctx.close)
                page = ctx.new_page()
                page.add_init_script(f"({SEED_JS})(null)")
                page.goto(f"{self.base}/build.html?give={a}&get={b}{anchor}", wait_until="load", timeout=60000)
                page.wait_for_function(LIVE, timeout=60000)
                page.wait_for_timeout(600)
                pos = page.evaluate("""() => { const el = document.getElementById('trade-charts'), h = document.querySelector('header');
                  return {top: el.getBoundingClientRect().top, header: h.getBoundingClientRect().bottom, y: scrollY, vh: innerHeight}; }""")
                label = f"{width} {anchor or 'no anchor'}"
                if anchor:
                    self.assertGreater(pos["y"], 0, label)
                    self.assertGreaterEqual(pos["top"], pos["header"] - 1, f"{label}: hidden under the header {pos}")
                    self.assertLess(pos["top"], pos["header"] + 120, f"{label}: not scrolled to the charts {pos}")
                else:
                    self.assertEqual(pos["y"], 0, label)


    def test_pasted_league_hides_the_add_league_card(self):
        """A league pasted on connect/setup (sessionStorage ddf:pasted only) counts: no "Add your league" card, the
        trade checks (lineup effect) show. With no league the card shows. Both widths."""
        p = self.players[:24]
        mine, theirs = p[0::2], p[1::2]
        pasted = {"v": 1, "me": 0, "teams": [{"name": "Paste One", "players": [{"name": x["n"], "key": x["key"], "pos": x["pos"]} for x in mine]},
                                             {"name": "Paste Two", "players": [{"name": x["n"], "key": x["key"], "pos": x["pos"]} for x in theirs]}]}
        import json
        seed = "(function(){ try { localStorage.clear(); sessionStorage.clear(); sessionStorage.setItem('ddf:pasted', %s); } catch (e) {} })()" % json.dumps(json.dumps(pasted))
        card = "() => { const c = document.querySelector('.lock-card[data-kind=trade][data-only=any-noleague]'); return {card: !!c && !c.hidden && c.offsetParent !== null, checks: !document.querySelector('.trade-checks').hidden && document.getElementById('checks').children.length > 0, mode: DDFBuild.state().mode}; }"
        for width in (1440, 390):
            for with_league in (True, False):
                ctx = self.browser.new_context(viewport={"width": width, "height": 900})
                self.addCleanup(ctx.close)
                page = ctx.new_page()
                page.add_init_script(seed if with_league else f"({SEED_JS})(null)")
                page.goto(f"{self.base}/build.html?give={mine[2]['key']}&give={mine[4]['key']}&get={theirs[1]['key']}&get={theirs[3]['key']}", wait_until="load", timeout=60000)
                page.wait_for_function(LIVE, timeout=60000)
                page.wait_for_timeout(500)
                got = page.evaluate(card)
                label = f"{width} {'pasted league' if with_league else 'no league'}"
                if with_league:
                    self.assertEqual((got["card"], got["mode"]), (False, "league"), label)
                    self.assertTrue(got["checks"], f"{label}: the lineup effect (trade checks) is missing")
                else:
                    self.assertEqual((got["card"], got["mode"]), (True, "any"), label)


    def test_chart_picker_and_reader_choices(self):
        """The value option's chart is the one the picker shows; an explicit None removes the value option and stays
        None; the reader's own option pick and edited text survive a re-render (an engine rebuild)."""
        p = self.players
        ctx = self.browser.new_context(viewport={"width": 1440, "height": 900})
        self.addCleanup(ctx.close)
        page = ctx.new_page()
        page.add_init_script(f"({SEED_JS})(null)")
        # Find a trade the best chart supports: you send the higher Analyst charts value.
        by_an = sorted(p, key=lambda x: -x["an"])
        page.goto(f"{self.base}/build.html?give={by_an[0]['key']}&get={by_an[8]['key']}", wait_until="load", timeout=60000)
        page.wait_for_function(LIVE, timeout=60000)
        page.wait_for_selector("#styles [data-style]")
        st = page.evaluate("() => ({pre: DDFBuild.offer().preselect, chart: document.getElementById('ref-chart').value, msg: document.getElementById('message').value})")
        self.assertEqual(st["pre"], "value", st)
        self.assertTrue(st["chart"], "the picker shows the chart the message cites")
        name = page.evaluate("() => document.querySelector('#ref-chart option:checked').textContent.split(':')[0].replace('Best for your pitch · ', '')")
        self.assertIn(name.split(' (')[0], st["msg"])
        page.select_option("#ref-chart", "")
        page.wait_for_timeout(200)
        after = page.evaluate("() => ({ids: [...document.querySelectorAll('#styles [data-style]')].map(b => b.dataset.style), chart: document.getElementById('ref-chart').value, msg: document.getElementById('message').value})")
        self.assertEqual(after["chart"], "", after)
        self.assertNotIn("value", after["ids"], after)
        self.assertNotRegex(after["msg"], r"trade chart|live market values", after)
        # Reader's pick and edits survive a re-render.
        page.click('#styles [data-style="opener"]')
        page.fill("#message", "My own words")
        page.evaluate("() => DDF.engine.applyVisit({})")   # an engine rebuild re-renders the page
        page.wait_for_timeout(200)
        kept = page.evaluate("() => ({style: DDFBuild.state().style, msg: document.getElementById('message').value})")
        self.assertEqual(kept, {"style": "opener", "msg": "My own words"})

    def test_pasted_league_any_players_mode_has_no_card(self):
        p = self.players[:24]
        mine, theirs = p[0::2], p[1::2]
        import json
        pasted = {"v": 1, "me": 0, "teams": [{"name": "Paste One", "players": [{"name": x["n"], "key": x["key"], "pos": x["pos"]} for x in mine]},
                                             {"name": "Paste Two", "players": [{"name": x["n"], "key": x["key"], "pos": x["pos"]} for x in theirs]}]}
        seed = "(function(){ try { localStorage.clear(); sessionStorage.clear(); sessionStorage.setItem('ddf:pasted', %s); } catch (e) {} })()" % json.dumps(json.dumps(pasted))
        for width in (1440, 390):
            ctx = self.browser.new_context(viewport={"width": width, "height": 900})
            self.addCleanup(ctx.close)
            page = ctx.new_page()
            page.add_init_script(seed)
            page.goto(f"{self.base}/build.html?mode=any&give={mine[2]['key']}&get={theirs[1]['key']}", wait_until="load", timeout=60000)
            page.wait_for_function(LIVE, timeout=60000)
            shown = page.evaluate("() => { const c = document.querySelector('.lock-card[data-kind=trade][data-only=any-noleague]'); return [DDFBuild.state().mode, !!c && !c.hidden]; }")
            self.assertEqual(shown, ["any", False], width)


if __name__ == "__main__":
    unittest.main()
