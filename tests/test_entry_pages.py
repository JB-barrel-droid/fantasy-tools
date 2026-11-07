"""JEG-1538: entry pages (connect.html, setup.html) at the root, the link codec and the routes into them.

Build checks (no browser):
- connect.html and setup.html are root pages; connect.html carries the engine; their files are published.
- The AI prompts send no-tools users to connect.html, not the MCP guide at connect/.
Rendered checks (dist/, Chromium):
1. A real paste (Yahoo markdown fixture) fills "Here's what we read from your paste" from the parse, keeps the league in
   sessionStorage ddf:pasted and enables Next; no static sample summary is left.
2. A paste we cannot read shows the status line and the edit-names box; Next stays disabled.
3. setup.html lists the pasted teams; confirming one stores `me` and writes the league to the live store
   ddf.v2.workspaces with that team as myTeamId (storage bridge); with nothing kept it says no rosters were added.
4. Link codec: the LINK-FORMAT.md section 6 and 6.1 vectors decode on the live page to the documented states, and an
   encodeToken -> decodeBlock round trip keeps teams, me, overrides and basis.
5. Routes: a #s= token on a v2 route lands on connect.html whole; /next/connect.html and /next/setup.html forward to the
   root keeping query and hash; a chat link for a view that is not live yet opens its live route with the league kept.
6. League ID help follows the provider toggle and its screenshots load; the iPhone tip shows for an iPhone browser only.
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from tests import _render_env
from tests._dist_server import serve

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
FIXTURES = ROOT / "tests" / "fixtures" / "entry_paste"
IPHONE_UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) "
             "Version/18.0 Mobile/15E148 Safari/604.1")
ENGINE_READY = "() => window.DDF && DDF.engine && DDF.engine.controls && DDF.engine.controls() && DDF.leaguePaste"
STATIC_SAMPLE = "Found 12 teams and 164 players"

# LINK-FORMAT.md section 6 (Chrome bytes) and 6.1 (with reader context).
VECTOR_6 = ("LAECAwEBBgMBf_AwHclLCoAgFAXQrcRt6sSavSVEmzC7qPRFxAixtUed6SnIEK2QAy8IrKddoJDMtPKPFM1MSIELmRC03TMwcgu38c14ZELBMX2joXCa"
            "mHZGSF_rCw+Pa")
VECTOR_61 = ("LAECAwEBBgMBf_AwXY7BTgMxDER_BQ1XK9qlLBX5hIo7h6oHb2p2I9qkSkxKVYVvR4k4IV9GM_Y831FgR0LxcoWFW8V9gpBF1Yclw94h35q4q0vMXn0"
             "M7-KXVbuVlZNKgt2P1OdAmCW4tTnmlSazpY15psGMh1orQXk-SUdq4qO0jsUXgcXj089Okpz9jdeHt1gEhEW0JSMIF04aGmlTCbFISv4o_YcJdjsQ_h3b"
             "l8FMlTBz9n3tHBsOOX4l17r_hMUHB-V8c3xyqPUX+xb")
VECTOR_6_STATE = {"v": 1, "view": "check", "settings": {"scoring": "half_ppr", "teams": 12, "superflex": False, "slots": [1, 2, 3, 1, 1, 6]},
                  "table": 1, "trade": {"give": [5, "Jeremiyah Love"], "get": [12], "partner": 3}}


class EntryBuildTest(unittest.TestCase):

    def test_entry_pages_are_root_pages(self):
        import sys
        sys.path.insert(0, str(ROOT / "pipelines"))
        import build_root_pages as brp
        for page in ("connect.html", "setup.html"):
            self.assertIn(page, brp.ROOT_PAGES)
            self.assertEqual(brp.rewrite_links(f'"{page}#paste"'), f'"{page}#paste"')
        self.assertIn("connect.html", brp.ENGINE_PAGES)
        for name in ("rosterparse.js", "league-paste.js", "connect-entry.js", "setup-entry.js", "img/league-id", "assets/howto/slides"):
            self.assertIn(name, brp.ROOT_FILES)
            self.assertTrue((ROOT / "app" / "next" / name).exists(), name)

    def test_prompts_point_no_tools_users_at_connect_html(self):
        for page in ("connect.html", "values.html", "index.html", "find.html", "ai.html"):
            text = (ROOT / "app" / "next" / page).read_text(encoding="utf-8")
            self.assertNotIn("fantasy-tools/connect/", text, page)
            self.assertIn("fantasy-tools/connect.html", text, page)

    def test_connect_has_no_static_sample(self):
        text = (ROOT / "app" / "next" / "connect.html").read_text(encoding="utf-8")
        self.assertNotIn(STATIC_SAMPLE, text)
        self.assertNotIn("<td>Josh Allen</td><td>QB</td><td>QB</td>", text)   # the old manual-entry sample roster
        setup = (ROOT / "app" / "next" / "setup.html").read_text(encoding="utf-8")
        self.assertNotIn('value="Team 02"', setup)


def setUpModule():
    _render_env.ensure_built()


def _pw():
    try:
        from playwright.sync_api import sync_playwright, Error as PlaywrightError
    except Exception as exc:
        raise _render_env.unavailable(f"Playwright not available: {exc}") from exc
    return sync_playwright, PlaywrightError


class EntryPagesRenderTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        sync_playwright, cls.PlaywrightError = _pw()
        cls._serve = serve()
        cls.base = cls._serve.__enter__()
        cls._pwcm = sync_playwright()
        cls.pw = cls._pwcm.__enter__()
        try:
            cls.browser = cls.pw.chromium.launch(args=_render_env.HERMETIC_ARGS, executable_path=_render_env.chromium_executable())
        except cls.PlaywrightError as exc:
            cls._pwcm.__exit__(None, None, None)
            cls._serve.__exit__(None, None, None)
            raise _render_env.unavailable(f"Chromium not available: {exc}") from exc

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls._pwcm.__exit__(None, None, None)
        cls._serve.__exit__(None, None, None)

    def page(self, **ctx):
        context = self.browser.new_context(viewport=ctx.pop("viewport", {"width": 1440, "height": 900}), **ctx)
        self.addCleanup(context.close)
        page = context.new_page()
        page.route(lambda u: not (u.startswith("http://127.0.0.1") or u.startswith("http://localhost")), lambda r: r.abort())
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.errors = errors
        return page

    def connect(self, page):
        page.goto(f"{self.base}/connect.html", wait_until="networkidle", timeout=60000)
        page.wait_for_function(ENGINE_READY, timeout=60000)

    def paste(self, page, text):
        page.fill("#rosters", text)
        page.click("#recognize-button")

    def test_real_paste_fills_recognition_card(self):
        page = self.page()
        self.connect(page)
        self.assertTrue(page.get_attribute("#connect-next", "aria-disabled"), "Next starts disabled")
        self.paste(page, (FIXTURES / "02-yahoo-markdown.txt").read_text(encoding="utf-8"))
        page.wait_for_selector("#recognized:not([hidden])", timeout=20000)
        summary = page.text_content("#recognition-summary")
        self.assertTrue(summary.startswith("Found 3 teams and "), summary)
        self.assertNotIn(STATIC_SAMPLE, page.content())
        teams = page.eval_on_selector_all(".recognition-team > summary", "els => els.map(e => e.textContent)")
        self.assertEqual([t.split(" · ")[0] for t in teams], ["Fourth Down Club", "Hail Marys", "Kingdom of Caleb"])
        kept = page.evaluate("JSON.parse(sessionStorage.getItem('ddf:pasted'))")
        self.assertEqual(kept["source"], "paste")
        self.assertIn("Drake Maye", [p["name"] for p in kept["teams"][0]["players"]])
        self.assertIsNone(page.get_attribute("#connect-next", "aria-disabled"), "Next enabled after a read")
        self.assertEqual(page.errors, [])

    def test_unreadable_paste_offers_edit_names(self):
        page = self.page()
        self.connect(page)
        self.paste(page, "Alpha Squad\nfoo bar\nBeta Crew\nbaz qux")
        page.wait_for_selector("#edit-names:not([hidden])", timeout=20000)
        self.assertIn("could not find any teams in that paste", page.text_content("#entry-status"))
        self.assertTrue(page.is_hidden("#recognized"))
        self.assertEqual(page.get_attribute("#connect-next", "aria-disabled"), "true")
        page.fill("#rosters", "zzz\nGG!\nJosh Allen\nBijan Robinson\nTT!\nJordan Love\nSaquon Barkley\n")
        page.click("#recognize-button")
        page.wait_for_selector("#recognized:not([hidden])", timeout=20000)
        page.click("#edit-team-names")
        page.fill("#edit-names-input", "GG!\nTT!")
        page.click("#edit-names-go")
        page.wait_for_function("() => JSON.parse(sessionStorage.getItem('ddf:pasted')).teams[0].name === 'GG!'", timeout=10000)
        kept = page.evaluate("JSON.parse(sessionStorage.getItem('ddf:pasted')).teams.map(t => [t.name, t.players.length])")
        self.assertEqual(kept, [["GG!", 2], ["TT!", 2]])

    def test_setup_lists_pasted_teams_and_bridges_the_league(self):
        page = self.page(viewport={"width": 390, "height": 844})
        self.connect(page)
        self.paste(page, (FIXTURES / "01-yahoo-iphone.txt").read_text(encoding="utf-8"))
        page.wait_for_selector("#recognized:not([hidden])", timeout=20000)
        page.click("#connect-next")
        page.wait_for_url("**/setup.html", timeout=20000)
        names = page.eval_on_selector_all("input[name=team]", "els => els.map(e => e.value)")
        self.assertEqual(names, ["Fourth Down Club", "Hail Marys", "Bijan Mustard Robinson", "Ricky and the Bobbys"])
        self.assertEqual(page.get_attribute("#continue-btn", "aria-disabled"), "true")
        page.click("label.setup-option >> nth=1")
        self.assertIsNone(page.get_attribute("#continue-btn", "aria-disabled"))
        self.assertEqual(page.evaluate("JSON.parse(sessionStorage.getItem('ddf:pasted')).me"), 1)
        ws = page.evaluate("JSON.parse(localStorage.getItem('ddf.v2.workspaces'))")
        self.assertEqual(ws["v"], 1)
        live = ws["workspaces"][0]
        self.assertEqual(ws["activeId"], live["id"])
        self.assertEqual([t["name"] for t in live["teams"]], names)
        self.assertEqual([t["name"] for t in live["teams"] if t["id"] == live["myTeamId"]], ["Hail Marys"])
        self.assertEqual([e["name"] for e in live["teams"][0]["entries"]], ["Drake Maye", "Ollie Gordon II", "Sione Vaki"])
        self.assertTrue(page.is_hidden("#bridge-ask"))
        # confirming another team updates the same live league in place (same ids)
        ids = [t["id"] for t in live["teams"]]
        page.click("label.setup-option >> nth=2")
        again = page.evaluate("JSON.parse(localStorage.getItem('ddf.v2.workspaces')).workspaces[0]")
        self.assertEqual([t["id"] for t in again["teams"]], ids)
        self.assertEqual(again["id"], live["id"])
        self.assertEqual(again["myTeamId"], ids[2])
        page.evaluate("sessionStorage.clear()")
        page.reload(wait_until="networkidle")
        self.assertTrue(page.is_visible("#setup-empty"))
        self.assertEqual(page.eval_on_selector_all("input[name=team]", "els => els.length"), 0)

    def test_bridge_asks_before_replacing_a_saved_league(self):
        page = self.page()
        saved = {"v": 1, "activeId": "lg-old", "workspaces": [{"id": "lg-old", "name": "Old league", "settings": {"teams": 10},
                 "teams": [{"id": "t1", "name": "Old A", "entries": []}, {"id": "t2", "name": "Old B", "entries": []}], "myTeamId": "t1"}]}
        page.add_init_script("if (!localStorage.getItem('ddf.v2.workspaces')) localStorage.setItem('ddf.v2.workspaces', %s);" % json.dumps(json.dumps(saved)))
        self.connect(page)
        self.paste(page, (FIXTURES / "03-espn.txt").read_text(encoding="utf-8"))
        page.wait_for_selector("#recognized:not([hidden])", timeout=20000)
        page.click("#connect-next")
        page.wait_for_url("**/setup.html", timeout=20000)
        page.click("label.setup-option >> nth=0")
        self.assertTrue(page.is_visible("#bridge-ask"))
        self.assertEqual(page.evaluate("JSON.parse(localStorage.getItem('ddf.v2.workspaces'))"), saved, "untouched before the reader says so")
        page.click("#bridge-replace")
        ws = page.evaluate("JSON.parse(localStorage.getItem('ddf.v2.workspaces'))")["workspaces"][0]
        self.assertNotEqual(ws["id"], "lg-old")
        self.assertIsNone(ws["settings"])
        self.assertEqual([t["name"] for t in ws["teams"]], ["Gridiron Gurus", "Taco Tuesday", "Mahomes Alone"])

    def test_link_after_paste_replaces_the_pasted_league(self):
        page = self.page()
        self.connect(page)
        self.paste(page, (FIXTURES / "03-espn.txt").read_text(encoding="utf-8"))
        page.wait_for_selector("#recognized:not([hidden])", timeout=20000)
        self.assertIsNotNone(page.evaluate("sessionStorage.getItem('ddf:pasted')"))
        state = {"v": 1, "view": "team", "settings": {"scoring": "ppr", "teams": 10, "superflex": False, "slots": [1, 2, 2, 1, 1, 6]},
                 "teams": [{"name": "Link A", "players": ["Josh Allen"]}, {"name": "Link B", "players": ["Jordan Love"]}]}
        page.evaluate("s => DDF.link.decodeBlock(JSON.stringify(s))", state)
        self.assertIsNone(page.evaluate("sessionStorage.getItem('ddf:pasted')"))
        page.goto(f"{self.base}/setup.html", wait_until="networkidle")
        self.assertEqual(page.eval_on_selector_all("input[name=team]", "els => els.map(e => e.value)"), ["Link A", "Link B"])

    def test_link_codec_vectors_and_round_trip(self):
        page = self.page()
        self.connect(page)
        page.wait_for_function("() => DDF.link && DDF.link.table(1)", timeout=20000)
        got6 = page.evaluate("t => DDF.link.decodeBlock(t)", VECTOR_6)
        got6.pop("overrides", None)
        self.assertEqual(got6, VECTOR_6_STATE)
        got61 = page.evaluate("t => DDF.link.decodeBlock(t)", VECTOR_61)
        self.assertEqual(got61["trade"], VECTOR_6_STATE["trade"])
        self.assertEqual(got61["overrides"], {"5": 70, "Jeremiyah Love": 60.5})
        self.assertEqual(got61["basis"], {"mode": "source", "source": "fantasycalc"})
        self.assertEqual(got61["settings"]["extras"]["positionWeights"], {"starter": [1, 1, 1, 1], "bench": [1.9, 5.7, 3.4, 0.1]})
        state = {"v": 1, "view": "team", "settings": {"scoring": "ppr", "teams": 10, "superflex": True, "slots": [1, 2, 2, 1, 1, 6]},
                 "table": 1, "me": 1, "teams": [{"name": "A", "players": [0, 1, "Somebody New"]}, {"name": "B", "players": [2, 3]}],
                 "overrides": {"0": 75.5}, "basis": {"mode": "custom", "weights": {"cbs": 1, "fantasycalc": 2}}}
        back = page.evaluate("s => DDF.link.encodeToken(s).then(t => DDF.link.decodeBlock(t))", state)
        for key in ("view", "settings", "me", "teams", "overrides", "basis"):
            self.assertEqual(back[key], state[key], key)

    def test_routes_into_entry_pages(self):
        page = self.page()
        page.goto(f"{self.base}/index.html#s=abc", wait_until="networkidle", timeout=60000)
        self.assertTrue(page.url.endswith("/connect.html#s=abc"), page.url)
        self.assertTrue(page.is_visible("#paste-link"), "a broken token shows the paste-your-block notice")
        page.goto(f"{self.base}/next/connect.html?x=1#paste", wait_until="networkidle")
        self.assertTrue(page.url.endswith("/connect.html?x=1#paste") and "/next/" not in page.url, page.url)
        page.goto(f"{self.base}/next/setup.html", wait_until="networkidle")
        self.assertTrue(page.url.endswith("/setup.html") and "/next/" not in page.url, page.url)
        # a chat link for Build a Trade (view check, live since JEG-1537): build.html with the token and its overrides
        page.goto(f"{self.base}/index.html#s={VECTOR_61}", wait_until="networkidle", timeout=60000)
        page.wait_for_function("() => /build\\.html#s=/.test(location.href)", timeout=20000)
        league = json.loads(page.evaluate("sessionStorage.getItem('ddf:league')"))
        self.assertEqual(league["trade"], VECTOR_6_STATE["trade"])
        page.wait_for_function("() => DDF.engine && DDF.engine.controls && DDF.engine.controls()", timeout=60000)
        page.wait_for_function("() => DDF.engine.overrides.count() > 0", timeout=20000)
        self.assertEqual(page.evaluate("DDF.engine.overrides.count()"), 2, "the link's two overrides apply")
        # a team view (team.html live since JEG-1539): team.html with the token, never a token glued after a v2 hash route
        token = page.evaluate("""() => DDF.link.encodeToken({v: 1, view: 'team', settings: {scoring: 'ppr', teams: 10, superflex: false,
            slots: [1, 2, 2, 1, 1, 6]}, teams: [{name: 'A', players: ['Josh Allen']}, {name: 'B', players: ['Jordan Love']}],
            overrides: {'Josh Allen': 80}})""")
        page.goto(f"{self.base}/index.html#s={token}", wait_until="networkidle", timeout=60000)
        page.wait_for_function("() => /team\\.html#s=/.test(location.href)", timeout=20000)
        page.wait_for_function("() => DDF.engine && DDF.engine.controls && DDF.engine.controls() && DDF.engine.overrides.count() > 0", timeout=60000)
        self.assertEqual(page.evaluate("DDF.engine.overrides.count()"), 1)

    def test_league_id_help_and_device_tip(self):
        page = self.page()
        self.connect(page)
        self.assertTrue(page.is_hidden("#phone-tip"), "desktop: no iPhone tip by default")
        page.click('[data-provider="yahoo"]')
        page.click("#id-help > summary")
        self.assertTrue(page.is_visible('[data-idhelp="yahoo"]'))
        self.assertTrue(page.is_hidden('[data-idhelp="espn"]'))
        page.wait_for_function("() => [...document.querySelectorAll('[data-idhelp=yahoo] img')].every(i => i.complete && i.naturalWidth > 0)", timeout=10000)
        page.click('#entry .dv-toggle.to-phone')
        self.assertTrue(page.is_visible("#phone-tip"))
        phone = self.page(viewport={"width": 390, "height": 844}, user_agent=IPHONE_UA, is_mobile=True, has_touch=True)
        self.connect(phone)
        self.assertEqual(phone.evaluate("document.documentElement.getAttribute('data-device')"), "phone")
        self.assertTrue(phone.is_visible("#phone-tip"))
        self.assertEqual(phone.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth"), 0)


if __name__ == "__main__":
    unittest.main()
