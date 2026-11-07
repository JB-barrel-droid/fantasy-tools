"""JEG-1557: mobile visual defects on the swapped site, the connect.html rework and the caveats note.

Each mobile test names the defect the live-site sweep (390 and 360 wide) found and fails without its fix:
1. Entry header (connect, setup, settings): pinned ~135px tall and the three steps wrapped with an orphan separator.
2. Sticky action bar: first-load reason in error orange, and a bar taller than it needs to be.
3. Info icon: stretched into a 44px-tall oval by the global summary tap-target rule.
4. Footer sitemap links 28px tall; header Menu button 36px on learn/build.
5. Text under 12px (eyebrows and range labels).
6. Explore: the Back button wrapped to "Bac / k" in the bottom bar.
7. connect.html: league ID box messages, one numbering for steps, phone toggle tap target, success card scrolled into
   view and wording, unreadable-paste wording.
Caveats note (Jeremy 2026-11-07): shown on the team assessment and Trade & Waiver Recommendations pages at 1440 and 390,
detail collapsed and expands; one line on the recognition card in the entry flow.
"""
from __future__ import annotations

import unittest
from pathlib import Path

from tests import _render_env
from tests._dist_server import serve

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "entry_paste"
ENGINE_READY = "() => window.DDF && DDF.engine && DDF.engine.controls && DDF.engine.controls() && DDF.leaguePaste"
STATE = {"v": 1, "view": "team", "settings": {"scoring": "ppr", "teams": 10, "superflex": False, "slots": [1, 2, 2, 1, 1, 6]}, "me": 0,
         "teams": [{"name": "Link A", "players": ["Josh Allen", "Bijan Robinson", "Puka Nacua"]},
                   {"name": "Link B", "players": ["Jordan Love", "Jahmyr Gibbs", "Ja'Marr Chase"]}]}


def setUpModule():
    _render_env.ensure_built()


class _RenderBase(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        try:
            from playwright.sync_api import sync_playwright, Error
        except Exception as exc:
            raise _render_env.unavailable(f"Playwright not available: {exc}") from exc
        cls.PlaywrightError = Error
        cls._serve = serve()
        cls.base = cls._serve.__enter__()
        cls._pwcm = sync_playwright()
        cls.pw = cls._pwcm.__enter__()
        try:
            cls.browser = cls.pw.chromium.launch(args=_render_env.HERMETIC_ARGS, executable_path=_render_env.chromium_executable())
        except Error as exc:
            cls._pwcm.__exit__(None, None, None)
            cls._serve.__exit__(None, None, None)
            raise _render_env.unavailable(f"Chromium not available: {exc}") from exc

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls._pwcm.__exit__(None, None, None)
        cls._serve.__exit__(None, None, None)

    def page(self, width=390, height=844, **ctx):
        if width < 761:
            ctx.setdefault("is_mobile", True)
            ctx.setdefault("has_touch", True)
        context = self.browser.new_context(viewport={"width": width, "height": height}, **ctx)
        self.addCleanup(context.close)
        page = context.new_page()
        page.route(lambda u: not (u.startswith("http://127.0.0.1") or u.startswith("http://localhost")), lambda r: r.abort())
        return page

    def go(self, page, name, engine=False):
        page.goto(f"{self.base}/{name}", wait_until="networkidle", timeout=60000)
        if engine:
            page.wait_for_function(ENGINE_READY, timeout=60000)
        page.wait_for_timeout(400)

    def with_league(self, page):
        self.go(page, "connect.html", engine=True)
        page.wait_for_function("() => DDF.link && DDF.link.table(1)", timeout=20000)
        page.evaluate("s => DDF.link.decodeBlock(JSON.stringify(s))", STATE)


class MobileConnectTest(_RenderBase):

    # ---- 1 ----
    def test_entry_header_is_not_pinned_and_steps_share_one_row(self):
        for width in (390, 360):
            for name in ("connect.html", "setup.html", "settings.html"):
                with self.subTest(width=width, page=name):
                    page = self.page(width)
                    self.go(page, name)
                    self.assertNotEqual(page.eval_on_selector("header.entry-head", "e => getComputedStyle(e).position"), "sticky")
                    tops = page.eval_on_selector_all(".entry-head .entry-steps > li", "els => els.map(e => Math.round(e.getBoundingClientRect().top))")
                    self.assertEqual(len(set(tops)), 1, f"steps wrapped onto several rows: {tops}")
                    self.assertLessEqual(page.eval_on_selector(".entry-head .entry-steps", "e => e.scrollWidth - e.clientWidth"), 0)

    # ---- 2 ----
    def test_action_bar_reason_is_calm_and_compact(self):
        page = self.page(390)
        self.go(page, "connect.html", engine=True)
        page.wait_for_selector(".ddf-actionbar.is-ready")
        sum_ = page.locator(".ddf-actionbar__sum")
        self.assertEqual(sum_.text_content().strip(), "Paste your rosters to continue.")
        self.assertNotEqual(sum_.evaluate("e => getComputedStyle(e).color"), "rgb(168, 62, 18)", "first-load hint must not read as an error")
        self.assertLessEqual(page.eval_on_selector(".ddf-actionbar", "e => e.getBoundingClientRect().height"), 92)

    def test_settings_intro_names_the_real_defaults(self):
        page = self.page(390)
        self.go(page, "settings.html")
        self.assertNotIn("We filled in what we could read", page.inner_text("main"))
        self.assertIn("We started with common settings (PPR, 12 teams, 1 QB, 2 RB, 2 WR, 1 TE, 1 FLEX, 7 bench), or the ones from your chat link or your last visit. Confirm each one.", page.inner_text("main"))
        self.assertEqual(page.eval_on_selector("#scoring", "e => e.value.toLowerCase()"), "ppr")
        self.assertEqual([page.input_value(f"#lineup-{k}") for k in ("qb", "rb", "wr", "te", "flex", "bench")], ["1", "2", "2", "1", "1", "7"])

    def test_setup_shows_one_next_button_and_it_enables_after_a_team_is_picked(self):
        for width in (1440, 390, 360):
            with self.subTest(width=width):
                page = self.page(width, 900 if width > 760 else 800)
                self.go(page, "connect.html", engine=True)
                page.fill("#rosters", (FIXTURES / "02-yahoo-markdown.txt").read_text(encoding="utf-8"))
                page.click("#recognize-button")
                page.wait_for_selector("#recognized:not([hidden])", timeout=20000)
                self.go(page, "setup.html")
                count = "() => [...document.querySelectorAll('a.button.primary, button.primary')].filter(e => e.textContent.includes('Next') && e.getBoundingClientRect().width > 0).length"
                self.assertEqual(page.evaluate(count), 1, "only the sticky bar's Next shows")
                nxt = page.locator(".ddf-actionbar__next")
                self.assertEqual(nxt.get_attribute("aria-disabled"), "true")
                self.assertIn("Confirm your team first", page.inner_text(".ddf-actionbar__sum"))
                page.locator("input[name=team]").first.check(force=True)
                page.wait_for_timeout(300)
                self.assertEqual(nxt.get_attribute("aria-disabled"), "false")
                self.assertTrue(page.inner_text(".ddf-actionbar__sum").startswith("Team: "))
                self.assertEqual(page.evaluate(count), 1)

    # ---- 3 ----
    def test_info_icon_stays_a_circle(self):
        page = self.page(390)
        self.go(page, "settings.html")
        sizes = page.eval_on_selector_all(".info summary", "els => els.map(e => { const r = e.getBoundingClientRect(); return [r.width, r.height]; })")
        self.assertTrue(sizes, "settings.html has info icons")
        for w, h in sizes:
            self.assertAlmostEqual(w, h, delta=1, msg=f"oval {w}x{h}")
            self.assertLessEqual(h, 24)

    # ---- 4 ----
    def test_footer_links_and_menu_button_meet_44px(self):
        page = self.page(390)
        self.go(page, "learn.html")
        heights = page.eval_on_selector_all(".sitemap a", "els => els.map(e => e.getBoundingClientRect().height)")
        self.assertTrue(heights)
        self.assertGreaterEqual(min(heights), 44)
        self.assertGreaterEqual(page.eval_on_selector("header .morewrap > button", "e => e.getBoundingClientRect().height"), 44)

    # ---- 5 ----
    def test_no_visible_text_under_12px_on_index_values_and_footer(self):
        js = """() => { const bad = []; const w = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT); let n;
          while (n = w.nextNode()) { const p = n.parentElement; if (!n.textContent.trim() || !p || ['SCRIPT','STYLE'].includes(p.tagName)) continue;
            const r = p.getBoundingClientRect(); const s = getComputedStyle(p);
            if (r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && parseFloat(s.fontSize) < 12) bad.push(p.tagName + '.' + p.className + ' ' + s.fontSize); }
          return bad; }"""
        for name in ("index.html", "values.html", "learn.html"):
            with self.subTest(page=name):
                page = self.page(390)
                self.go(page, name)
                self.assertEqual(page.evaluate(js), [])

    # ---- 6 ----
    def test_explore_back_button_does_not_wrap(self):
        page = self.page(360)
        self.go(page, "explore.html")
        box = page.eval_on_selector(".xbar .button", "e => { const r = e.getBoundingClientRect(); return [r.width, r.height]; }")
        self.assertLessEqual(box[1], 50, f"Back wrapped: {box}")

    # ---- 7 ----
    def test_connect_league_id_box_and_steps_wording(self):
        page = self.page(390, user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1")
        self.go(page, "connect.html", engine=True)
        text = page.inner_text("main")
        self.assertNotIn("League numbers only work on Sleeper", text)
        self.assertNotIn("Step 1 of 3", text, "how-to slides must not reuse the page's step numbers")
        self.assertIn("Already copied your rosters? Jump to the paste box.", text)
        self.assertEqual(page.get_attribute("#league-ref", "placeholder"), "A league link or ID, such as 123456")
        page.click("#get-link")
        self.assertEqual(page.text_content("#link-result"), "Paste a link or league ID first.")
        page.fill("#league-ref", "no id here")
        page.click("#get-link")
        self.assertIn("could not find a league ID", page.text_content("#link-result"))
        page.click("[data-provider=espn]")
        page.fill("#league-ref", "https://fantasy.espn.com/football/league?leagueId=123456")
        page.click("#get-link")
        self.assertEqual(page.get_attribute("#link-result a.button", "href"), "https://fantasy.espn.com/football/league/rosters?leagueId=123456")
        page.click("[data-provider=yahoo]")
        page.click("#tutorial > summary")
        toggle = page.locator("[data-walkthrough=yahoo] .dv-toggle:visible").first
        self.assertGreaterEqual(toggle.bounding_box()["height"], 44)

    def test_connect_success_card_is_scrolled_into_view_and_worded_plainly(self):
        page = self.page(390)
        self.go(page, "connect.html", engine=True)
        page.fill("#rosters", (FIXTURES / "02-yahoo-markdown.txt").read_text(encoding="utf-8"))
        page.evaluate("() => document.getElementById('rosters').dispatchEvent(new Event('paste', {bubbles: true}))")  # how phones enter rosters: paste, no submit
        page.wait_for_selector("#recognized:not([hidden])", timeout=20000)
        page.wait_for_timeout(500)
        self.assertTrue(page.text_content("#recognition-summary").startswith("Found 3 teams and "), page.text_content("#recognition-summary"))
        top = page.eval_on_selector("#recognized", "e => e.getBoundingClientRect().top")
        self.assertTrue(0 <= top < 400, f"success card off screen (top={top})")
        self.assertEqual(page.text_content("#entry-status").strip(), "Check the list below, then confirm your team.")

    def test_connect_unreadable_paste_wording(self):
        page = self.page(390)
        self.go(page, "connect.html", engine=True)
        page.fill("#rosters", "hello this is not a roster page at all\nnothing to see")
        page.click("#recognize-button")
        page.wait_for_selector("#edit-names:not([hidden])", timeout=20000)
        self.assertIn("We could not find any teams in that paste", page.text_content("#entry-status"))
        self.assertEqual(page.get_attribute("#edit-names-input", "placeholder"), "One team name per line")

    # ---- caveats ----
    def test_caveats_note_on_team_and_recommendations_pages(self):
        for width in (1440, 390):
            for name in ("team.html", "find.html", "partners.html"):
                with self.subTest(width=width, page=name):
                    page = self.page(width, 900 if width > 760 else 844)
                    self.with_league(page)
                    self.go(page, name, engine=False)
                    note = page.locator(".ddf-caveats").first
                    note.wait_for(state="visible", timeout=20000)
                    self.assertIn("not advice", note.inner_text())
                    self.assertIn("Check them against your league before you act" if name == "team.html" else "Check each one against your league before you act", note.inner_text())
                    more = note.locator("details")
                    self.assertFalse(more.evaluate("e => e.open"), "detail starts collapsed")
                    self.assertGreaterEqual(note.locator("summary").bounding_box()["height"], 44)
                    note.locator("summary").click()
                    self.assertTrue(more.evaluate("e => e.open"))
                    body = note.inner_text()
                    for phrase in ("Snapshot week", "Value above waivers", "Estimated chart values", "Your league settings", "Pasted rosters", "Not advice"):
                        self.assertIn(phrase, body)
                    self.assertNotIn("Player pool", body)
                    self.assertIn("News since then is not in them", body)
                    self.assertEqual(page.evaluate("document.documentElement.scrollWidth - innerWidth"), 0)

    def test_entry_flow_shows_one_line_note_when_the_league_loads(self):
        page = self.page(390)
        self.go(page, "connect.html", engine=True)
        page.fill("#rosters", (FIXTURES / "02-yahoo-markdown.txt").read_text(encoding="utf-8"))
        page.click("#recognize-button")
        page.wait_for_selector("#recognized:not([hidden]) .ddf-caveats--entry", timeout=20000)
        note = page.locator("#recognized .ddf-caveats--entry")
        self.assertIn("as of your paste", note.inner_text())
        self.assertEqual(note.locator("details").count(), 0)


TOUCH_PAGES = ("index.html", "values.html", "learn.html", "build.html", "connect.html", "setup.html", "team.html", "explore.html",
               "partners.html", "find.html", "waivers.html", "settings.html", "ai.html")
INTERACTIVE = ("a[href],button,input:not([type=hidden]),select,textarea,summary,[role=button],[role=tab],[role=link],"
               "[tabindex]:not([tabindex='-1'])")
INTENDED_TOUCH_ACTIONS = ("manipulation", "pan-y pinch-zoom")


class TouchBehaviorTest(_RenderBase):
    """Jeremy 2026-11-07: taps must not double-tap-zoom, fields must not trigger iOS focus zoom, nothing overflows."""

    def test_stylesheet_rule_and_no_zoom_lock(self):
        css = (ROOT / "app" / "next" / "styles.css").read_text(encoding="utf-8")
        self.assertRegex(css, r"a\[href\],button,input,select,textarea,summary,label[^{]*\{touch-action:manipulation!important\}")
        self.assertIn("#vchart{touch-action:pan-y pinch-zoom!important}", css)
        for html in sorted((ROOT / "app" / "next").glob("*.html")):
            meta = html.read_text(encoding="utf-8")
            self.assertNotIn("user-scalable", meta, html.name)
            self.assertNotIn("maximum-scale", meta, html.name)

    def test_touch_action_fields_and_overflow_on_every_page(self):
        js = """(sel) => { const bad = [], small = [];
          document.querySelectorAll(sel).forEach(e => { const r = e.getBoundingClientRect(); const s = getComputedStyle(e);
            if (!(r.width > 0 && r.height > 0) || s.visibility === 'hidden') return;
            const d = e.tagName.toLowerCase() + (e.id ? '#' + e.id : '') + '.' + String(e.className && e.className.baseVal !== undefined ? e.className.baseVal : e.className).trim().split(/\\s+/)[0];
            if (!%s.includes(s.touchAction)) bad.push(d + ' ' + s.touchAction);
            if (['INPUT','TEXTAREA','SELECT'].includes(e.tagName) && !['checkbox','radio','range','file','button','submit'].includes(e.type) && parseFloat(s.fontSize) < 16) small.push(d + ' ' + s.fontSize); });
          return {bad, small, over: document.documentElement.scrollWidth - innerWidth}; }""" % list(INTENDED_TOUCH_ACTIONS)
        for width in (390, 360):
            for name in TOUCH_PAGES:
                with self.subTest(width=width, page=name):
                    page = self.page(width, 800)
                    self.go(page, name)
                    got = page.evaluate(js, INTERACTIVE)
                    self.assertEqual(got["bad"], [], "interactive elements without touch-action: manipulation")
                    self.assertEqual(got["small"], [], "fields under 16px trigger iOS focus zoom")
                    self.assertLessEqual(got["over"], 0, "horizontal overflow")

    def test_chart_pans_vertically_and_pinches_and_menus_do_not_chain_scroll(self):
        page = self.page(390)
        self.go(page, "values.html")
        self.assertEqual(page.eval_on_selector("#vchart", "e => getComputedStyle(e).touchAction"), "pan-y pinch-zoom")
        self.assertEqual(page.eval_on_selector(".table-wrap, #rows", "e => getComputedStyle(e.closest('.table-wrap') || e).overscrollBehaviorX"), "contain")


if __name__ == "__main__":
    unittest.main()
