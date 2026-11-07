"""JEG-1537: old Compare a trade links reach Build a Trade with their state; links into it from swapped pages.

1. /#compare-trade?give=<keys>&get=<keys>&scoring=&teams=&roster= (the live share format; since JEG-1539 the front
   door's legacy-routes.js forwards it) lands on build.html with those players, the link's league for this visit only, and the address rewritten to
   ?give=<names>&get=<names>.
2. The same link from /v2/ lands on the root build.html; name tokens (n:Name) resolve.
3. A link's basis and overrides (basis=, ov=) apply for the visit (ddf-engine.js) and are not saved.
4. JEG-1539: a Compare link carrying a whole league state (mine=, theirs=) no longer stays on the retired classic view:
   it lands on build.html as a league link (#s=, the rosters as the league) with give/get as names.
5. (removed at JEG-1539: in-page jumps inside the classic page; v2 no longer runs on the site)
6. /next/build.html redirects to the root page; check.html/trade.html links point at build.html.
7. The Values page's Build a Trade links use build.html?give=<name> (no #compare-trade left on swapped pages).
"""
from __future__ import annotations

import re
import unittest
from urllib.parse import parse_qs, urlparse

from tests import _render_env
from tests._dist_server import DIST, serve

LIVE = "() => document.body.classList.contains('build-live')"
KEYS_JS = """() => window.DDF.engine.ready.then(() => DDF.engine.players().filter(p => p.ddf !== null)
  .sort((a, b) => b.ddf - a.ddf).slice(0, 6).map(p => ({key: p.key, n: p.n})))"""
CLEAR = "(function(){ try { localStorage.clear(); sessionStorage.clear(); } catch (e) {} })()"


def setUpModule():
    _render_env.ensure_built()


class BuildSwapRoutesTest(unittest.TestCase):
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
        page.add_init_script(CLEAR)
        page.goto(f"{cls.base}/build.html", wait_until="load", timeout=60000)
        cls.players = page.evaluate(KEYS_JS)
        page.close()

    @classmethod
    def tearDownClass(cls):
        cls.browser.close(); cls._pw.stop(); cls._serve.__exit__(None, None, None)

    def open(self, path, wait_live=True):
        page = self.browser.new_page(viewport={"width": 1440, "height": 900})
        self.errors = []
        page.on("pageerror", lambda e: self.errors.append(str(e)))
        page.add_init_script(CLEAR)
        page.goto(f"{self.base}{path}", wait_until="load", timeout=60000)
        if wait_live:
            page.wait_for_function(LIVE, timeout=60000)
        self.addCleanup(page.close)
        return page

    def state(self, page):
        return page.evaluate("""() => ({give: DDFBuild.picked('give'), get: DDFBuild.picked('get'),
          settings: document.getElementById('settings-line').textContent, note: document.getElementById('prefill-note').textContent,
          saved: localStorage.getItem('ddf.v2.league-settings'), savedOv: localStorage.getItem('ddf-v2-value-overrides')})""")

    def test_compare_link_lands_with_players_and_league(self):
        a, b, c = self.players[:3]
        page = self.open(f"/index.html#compare-trade?give={a['key']},{b['key']}&get={c['key']}&scoring=standard&teams=10&roster=QB1.RB2.WR3.TE1.FLEX1.SF1.BN6")
        url = urlparse(page.url)
        self.assertTrue(url.path.endswith("/build.html"), page.url)
        q = parse_qs(url.query)
        self.assertEqual(q.get("give"), [a["n"], b["n"]])
        self.assertEqual(q.get("get"), [c["n"]])
        s = self.state(page)
        self.assertEqual(s["give"], [a["key"], b["key"]])
        self.assertEqual(s["get"], [c["key"]])
        self.assertIn("Standard · 10 teams · Superflex", s["settings"])
        self.assertIsNone(s["saved"], "the link's league must apply for the visit only")
        self.assertEqual(self.errors, [])

    def test_v2_path_and_name_tokens(self):
        a, b = self.players[3:5]
        page = self.open(f"/v2/index.html#compare-trade?give={a['key']}&get=n:{b['n'].replace(' ', '%20')}")
        self.assertRegex(urlparse(page.url).path, r"/build\.html$")
        self.assertNotIn("/v2/", urlparse(page.url).path)
        s = self.state(page)
        self.assertEqual((s["give"], s["get"]), ([a["key"]], [b["key"]]))

    def test_value_context_applies_for_the_visit(self):
        a, b = self.players[:2]
        page = self.open(f"/index.html#compare-trade?give={a['key']}&get={b['key']}&ov={a['key']}:12.5")
        got = page.evaluate(f"() => DDFBuild.rec('{a['key']}').ddf")
        self.assertAlmostEqual(got, 12.5, places=6)
        self.assertIsNone(self.state(page)["savedOv"])

    def test_full_state_link_becomes_a_league_link(self):
        """JEG-1539: mine=/theirs= links (ddf-assist.js, chat site_url) open Build a Trade with those rosters as the league."""
        a, b, c = self.players[:3]
        page = self.open(f"/index.html#compare-trade?give={a['key']}&get={c['key']}&mine={a['key']},{b['key']}&theirs={c['key']}&scoring=ppr&teams=10", wait_live=False)
        page.wait_for_url(re.compile(r"build\.html"), timeout=30000)
        url = urlparse(page.url)
        self.assertTrue(url.fragment.startswith("s="), page.url)
        self.assertEqual(parse_qs(url.query).get("give"), [a["n"]])
        page.wait_for_function("() => sessionStorage.getItem('ddf:league')", timeout=30000)
        league = page.evaluate("() => JSON.parse(sessionStorage.getItem('ddf:league'))")
        self.assertEqual([len(t["players"]) for t in league["teams"]], [2, 1])
        self.assertEqual((league["me"], league["settings"]["scoring"], league["settings"]["teams"]), (0, "ppr", 10))
        self.assertEqual(self.errors, [])

    def test_advanced_and_weeks_match_the_classic_view(self):
        """The link's advanced settings and season weeks reach build.html: the same DDF Value as the classic view."""
        a, b = self.players[:2]
        for extra in ("&bso=0.300&inj=all&conf=1.5", "&regend=12&playoffs=13-15&optimize=playoffs"):
            link = f"#compare-trade?give={a['key']}&get={b['key']}&scoring=half_ppr&teams=12&roster=QB1.RB2.WR3.TE1.FLEX1.SF0.BN6{extra}"
            classic = self.open(f"/v2-app.html{link}", wait_live=False)   # the build-only v2 shell keeps the classic view
            classic.wait_for_function("() => window.TradeValueCurveControls && TradeValueCurveControls.isReady && TradeValueCurveControls.isReady()", timeout=60000)
            classic.wait_for_timeout(2500)
            want = classic.evaluate(f"() => TradeValueCurveControls.getAllRows().find(r => String(r.player_key) === '{a['key']}').values.ddf_value")
            page = self.open(f"/index.html{link}")
            got = page.evaluate(f"() => DDFBuild.rec('{a['key']}').ddf")
            self.assertAlmostEqual(got, want, places=6, msg=extra)
            self.assertIsNone(self.state(page)["saved"], extra)

    def test_next_stub_and_page_links(self):
        page = self.open("/next/build.html?mode=any", wait_live=True)
        self.assertRegex(urlparse(page.url).path, r"/fantasy-tools/build\.html$|^/build\.html$")
        html = (DIST / "build.html").read_text(encoding="utf-8")
        self.assertFalse("#compare-trade" in html, "build.html links to the old Compare route")
        self.assertFalse('href="next/' in html, "build.html links into /next/")
        self.assertFalse("data-posweights" in html, "position weights stay hidden until JEG-1540 (D7)")
        for name in ("values-buysell.js", "values-chart.js", "values-overrides.js", "ddf-engine.js", "values.html", "learn.html"):
            self.assertFalse("#compare-trade" in (DIST / name).read_text(encoding="utf-8"), f"{name} links to the old Compare route")
        self.assertIn("var BUILD_PAGE = 'build.html';", (DIST / "ddf-engine.js").read_text(encoding="utf-8"))

    def test_values_build_link_uses_names(self):
        a, b = self.players[:2]
        page = self.open("/values.html", wait_live=False)
        page.wait_for_function("() => window.DDF && DDF.engine && DDF.engine.controls()", timeout=60000)
        href = page.evaluate(f"() => DDF.engine.buildHref({{give: [DDF.engine.player('{a['key']}')], get: [DDF.engine.player('{b['key']}')]}})")
        q = parse_qs(urlparse(href).query)
        self.assertTrue(href.startswith("build.html?"), href)
        self.assertEqual((q["give"], q["get"]), ([a["n"]], [b["n"]]))


if __name__ == "__main__":
    unittest.main()
