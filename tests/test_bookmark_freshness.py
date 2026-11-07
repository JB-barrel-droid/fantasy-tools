"""JEG-1564: bookmark prompts, page titles, league names, roster input date and freshness (dist/, Chromium).

1. Freshness bands from DDF.leagueMeta.FRESHNESS at every boundary (0/1/2/3/4/6/7/8 days); the age is in plain words.
2. The banner on a workspace page per band; dismissing a band hides it for the session, a later stronger band still shows.
3. Title scheme "League – Team – Week N – Data Driven Football"; "My league" when unnamed.
4. Bookmark prompt after a big input: shows once per change, a dismissed prompt stays dismissed, a new change asks again.
5. Header chip: the league name fitted to the room (short, long, very long, emoji), no header overflow at 390 and 1440,
   full name in aria-label and the menu, "Your league" when unnamed.
6. Link codec: name and enteredAt round-trip; old links without them decode; a bad value is dropped by the reader and
   rejected by the writer. The Bookmark link carries a pasted league's teams, team, name and date.
7. Setup: "We found" on the recognition card and the name suggested (not saved) until the reader confirms a team.
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from tests import _render_env
from tests._dist_server import serve

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "entry_paste"
ENGINE_READY = "() => window.DDF && DDF.engine && DDF.engine.controls && DDF.engine.controls() && DDF.leagueMeta"
VECTOR_6 = ("LAECAwEBBgMBf_AwHclLCoAgFAXQrcRt6sSavSVEmzC7qPRFxAixtUed6SnIEK2QAy8IrKddoJDMtPKPFM1MSIELmRC03TMwcgu38c14ZELBMX2joXCa"
            "mHZGSF_rCw+Pa")


def seed_script(days: int | None, name: str | None = "USO Season XVIII", me: int = 1) -> str:
    """sessionStorage ddf:pasted with a 3-team league entered `days` ago (local calendar days)."""
    rec = {"v": 1, "source": "paste", "site": "yahoo", "me": me, "name": name,
           "teams": [{"name": "Fourth Down Club", "players": [{"name": "Josh Allen", "key": "869", "pos": "QB", "team": "BUF", "id": None}], "unmatched": []},
                     {"name": "Hail Marys", "players": [{"name": "Jahmyr Gibbs", "key": "2227", "pos": "RB", "team": "DET", "id": 0}], "unmatched": []},
                     {"name": "Kingdom of Caleb", "players": [{"name": "Puka Nacua", "key": "1370", "pos": "WR", "team": "LA", "id": 3}], "unmatched": []}]}
    if name is None:
        rec.pop("name")
    date_js = "null" if days is None else f"(() => {{ const d = new Date(); d.setDate(d.getDate() - {days}); return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0'); }})()"
    return ("(() => { if (sessionStorage.getItem('ddf:seeded')) return; const r = " + json.dumps(rec) + "; const at = " + date_js
            + "; if (at) r.enteredAt = at; sessionStorage.setItem('ddf:pasted', JSON.stringify(r)); sessionStorage.setItem('ddf:seeded', '1'); })()")


def setUpModule():
    _render_env.ensure_built()


class BookmarkFreshnessTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        try:
            from playwright.sync_api import sync_playwright, Error as PlaywrightError
        except Exception as exc:
            raise _render_env.unavailable(f"Playwright not available: {exc}") from exc
        cls._serve = serve()
        cls.base = cls._serve.__enter__()
        cls._pwcm = sync_playwright()
        cls.pw = cls._pwcm.__enter__()
        try:
            cls.browser = cls.pw.chromium.launch(args=_render_env.HERMETIC_ARGS, executable_path=_render_env.chromium_executable())
        except PlaywrightError as exc:
            cls._pwcm.__exit__(None, None, None)
            cls._serve.__exit__(None, None, None)
            raise _render_env.unavailable(f"Chromium not available: {exc}") from exc

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls._pwcm.__exit__(None, None, None)
        cls._serve.__exit__(None, None, None)

    def page(self, width=1440, seed=None):
        context = self.browser.new_context(viewport={"width": width, "height": 900})
        self.addCleanup(context.close)
        page = context.new_page()
        page.route(lambda u: not (u.startswith("http://127.0.0.1") or u.startswith("http://localhost")), lambda r: r.abort())
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.errors = errors
        if seed:
            page.add_init_script(seed)
        return page

    def team(self, page):
        page.goto(f"{self.base}/team.html", wait_until="networkidle", timeout=60000)
        page.wait_for_function(ENGINE_READY, timeout=60000)
        page.wait_for_function("() => document.documentElement.getAttribute('data-league') === 'loaded'", timeout=20000)
        page.evaluate("DDF.leagueMeta.refresh()")

    def test_bands_at_every_boundary(self):
        page = self.page()
        page.goto(f"{self.base}/values.html", wait_until="networkidle", timeout=60000)
        page.wait_for_function("() => window.DDF && DDF.leagueMeta", timeout=20000)
        got = page.evaluate("""() => { const M = DDF.leagueMeta, now = new Date(2026, 10, 9, 0, 30);
            return [0, 1, 2, 3, 4, 6, 7, 8].map(n => { const d = new Date(2026, 10, 9 - n);
              const iso = d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');
              const days = M.ageDays(iso, now); return [days, M.band(days), M.ageWords(days)]; }); }""")
        self.assertEqual([g[1] for g in got], ["fresh", "fresh", "note", "note", "prompt", "prompt", "stale", "stale"])
        self.assertEqual([g[0] for g in got], [0, 1, 2, 3, 4, 6, 7, 8])
        self.assertEqual([g[2] for g in got], ["today", "yesterday", "2 days ago", "3 days ago", "4 days ago", "6 days ago", "7 days ago", "8 days ago"])
        msgs = page.evaluate("() => ['note', 'prompt', 'stale'].map(b => DDF.leagueMeta.message(b, 5))")
        for m in msgs:
            self.assertIn("Roster entered 5 days ago", m)
        self.assertIn("may be off", msgs[2])
        cfg = page.evaluate("() => DDF.leagueMeta.FRESHNESS.bands.map(b => [b.id, b.maxDays === Infinity ? null : b.maxDays])")
        self.assertEqual(cfg, [["fresh", 1], ["note", 3], ["prompt", 6], ["stale", None]])

    def test_banner_per_band_and_dismissal(self):
        for days, band in ((1, None), (3, "note"), (5, "prompt"), (8, "stale")):
            with self.subTest(days=days):
                page = self.page(seed=seed_script(days))
                self.team(page)
                if band is None:
                    self.assertEqual(page.locator("#ddf-fresh").count(), 0)
                    continue
                page.wait_for_selector("#ddf-fresh", timeout=10000)
                self.assertEqual(page.get_attribute("#ddf-fresh", "data-band"), band)
                self.assertIn(f"Roster entered {days} days ago", page.text_content("#ddf-fresh"))
                self.assertEqual(page.locator("#ddf-fresh .ddf-fresh-go").count(), 0 if band == "note" else 1)
                self.assertEqual(page.errors, [])
        # dismiss the prompt band: gone after reload; a stronger band (7 days) still shows in the same session
        page = self.page(seed=seed_script(5))
        self.team(page)
        page.wait_for_selector("#ddf-fresh")
        page.click("#ddf-fresh .ddf-fresh-x")
        page.reload(wait_until="networkidle")
        page.wait_for_function(ENGINE_READY, timeout=60000)
        page.evaluate("DDF.leagueMeta.refresh()")
        self.assertEqual(page.locator("#ddf-fresh").count(), 0)
        page.evaluate("""() => { const r = JSON.parse(sessionStorage.getItem('ddf:pasted')); const d = new Date(); d.setDate(d.getDate() - 7);
            r.enteredAt = d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');
            sessionStorage.setItem('ddf:pasted', JSON.stringify(r)); DDF.leagueMeta.refresh(); }""")
        page.wait_for_selector("#ddf-fresh", timeout=5000)
        self.assertEqual(page.get_attribute("#ddf-fresh", "data-band"), "stale")
        page.click(".ddf-chip")
        self.assertEqual(page.text_content(".ddf-cm-age"), "Roster entered 7 days ago")

    def test_title_scheme(self):
        page = self.page(seed=seed_script(0))
        self.team(page)
        week = page.evaluate("DDF.engine.meta().week")
        want = "USO Season XVIII – Hail Marys – " + (f"Week {week} – " if week is not None else "") + "Data Driven Football"
        page.wait_for_function("t => document.title === t", arg=want, timeout=10000)
        unnamed = self.page(seed=seed_script(0, name=None))
        self.team(unnamed)
        unnamed.wait_for_function("() => document.title.startsWith('My league – Hail Marys')", timeout=10000)

    def test_bookmark_prompt_once_per_change(self):
        page = self.page(seed=seed_script(0))
        self.team(page)
        page.wait_for_selector(".ddf-bm", state="visible", timeout=20000)
        page.evaluate("DDF.leagueMeta.want('rosters', 'A')")
        page.wait_for_function("() => { const h = document.querySelector('.ddf-bm-hint'); return h && !h.hidden && h.getAttribute('data-reason') === 'rosters'; }", timeout=5000)
        self.assertEqual(page.text_content(".ddf-bm-ht"), "Rosters added. Bookmark this page to come back to your league.")
        page.click(".ddf-bm-hint .ddf-bm-x")
        page.reload(wait_until="networkidle")
        page.wait_for_function(ENGINE_READY, timeout=60000)
        page.wait_for_selector(".ddf-bm", state="visible", timeout=20000)
        page.wait_for_timeout(1500)
        self.assertNotEqual(page.evaluate("(document.querySelector('.ddf-bm-hint') || {}).getAttribute && document.querySelector('.ddf-bm-hint').getAttribute('data-reason')"), "rosters")
        page.evaluate("DDF.leagueMeta.want('team', 'B')")
        page.wait_for_function("() => { const h = document.querySelector('.ddf-bm-hint'); return h && !h.hidden && h.getAttribute('data-reason') === 'team'; }", timeout=5000)

    def test_link_overrides_do_not_ask_for_a_bookmark(self):
        page = self.page()
        page.goto(f"{self.base}/values.html", wait_until="networkidle", timeout=60000)
        page.wait_for_function("() => DDF.link && DDF.link.table(1)", timeout=20000)
        token = page.evaluate("""() => DDF.link.encodeToken({v: 1, view: 'team', settings: {scoring: 'ppr', teams: 10, superflex: false,
            slots: [1, 2, 2, 1, 1, 6]}, teams: [{name: 'A', players: ['Josh Allen']}, {name: 'B', players: ['Jordan Love']}], me: 0,
            overrides: {'Josh Allen': 80, 'Jordan Love': 70, 'Puka Nacua': 60, 'Jahmyr Gibbs': 90}})""")
        fresh = self.page()
        fresh.goto(f"{self.base}/values.html", wait_until="networkidle", timeout=60000)   # the session's override baseline is 0
        fresh.wait_for_function("() => sessionStorage.getItem('ddf:bmovbase') !== null", timeout=20000)
        fresh.goto(f"{self.base}/team.html#s={token}", wait_until="networkidle", timeout=60000)
        fresh.wait_for_function(ENGINE_READY, timeout=60000)
        fresh.wait_for_selector(".ddf-bm", state="visible", timeout=20000)
        fresh.wait_for_timeout(2000)
        self.assertEqual(fresh.evaluate("DDF.overrides.count()"), 4, "the link's overrides applied")
        want = fresh.evaluate("JSON.parse(sessionStorage.getItem('ddf:bmwant') || 'null')")
        self.assertFalse(want and want["reason"] == "overrides", want)
        self.assertNotEqual(fresh.evaluate("(document.querySelector('.ddf-bm-hint') || document.body).getAttribute('data-reason')"), "overrides")

    def test_league_id_stays_on_the_device(self):
        seed = seed_script(0).replace('"site": "yahoo",', '"site": "yahoo", "leagueId": "848938",')
        page = self.page(seed=seed)
        self.team(page)
        page.wait_for_selector(".ddf-bm", state="visible", timeout=20000)
        self.assertNotIn("848938", page.title())
        page.click(".ddf-bm")
        page.wait_for_function("() => /#s=/.test(location.href)", timeout=10000)
        linked = page.evaluate("() => DDF.link.decodeBlock(location.href)")
        self.assertNotIn("848938", json.dumps(linked))
        self.assertNotIn("leagueId", linked)

    def test_chip_names_fit(self):
        names = [("Gurus", "Gurus"), ("USO Season XVIII", None), ("The Extremely Long Name Report With Bill And Friends", None), ("Gridiron 🏈 Kings", None)]
        for width in (390, 1440):
            for full, exact in names:
                with self.subTest(width=width, name=full):
                    page = self.page(width=width, seed=seed_script(0, name=full))
                    self.team(page)
                    page.wait_for_selector("header .ddf-chip .ddf-chip-t", timeout=10000)
                    shown = page.text_content("header .ddf-chip .ddf-chip-t")
                    if exact:
                        self.assertEqual(shown, exact)
                    self.assertTrue(full.startswith(shown.rstrip("…").split(" ")[0]), shown)
                    cap = 120 if width < 768 else 200
                    self.assertLessEqual(page.evaluate("document.querySelector('header .ddf-chip .ddf-chip-t').getBoundingClientRect().width"), cap + 2)
                    self.assertIn(full, page.get_attribute("header .ddf-chip", "aria-label"))
                    self.assertEqual(page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth"), 0)
                    self.assertLessEqual(page.evaluate("(() => { const h = document.querySelector('header .ddf-chip').closest('.header-inner') || document.querySelector('header'); return h.scrollWidth - h.clientWidth; })()"), 1)
                    page.click("header .ddf-chip")
                    self.assertTrue(page.text_content(".ddf-cm-src").startswith(full))
        cands = self.page()
        cands.goto(f"{self.base}/values.html", wait_until="networkidle")
        got = cands.evaluate("() => DDF.leagueMeta.chipCandidates('USO Season XVIII')")
        self.assertEqual(got[:2], ["USO Season XVIII", "USO S. XVIII"])
        plain = self.page(seed=seed_script(0, name=None))
        self.team(plain)
        self.assertEqual(plain.text_content("header .ddf-chip .ddf-chip-t"), "Your league")

    def test_codec_round_trip_and_bookmark_link(self):
        page = self.page(seed=seed_script(2))
        self.team(page)
        page.wait_for_function("() => DDF.link && DDF.link.table(1)", timeout=20000)
        state = {"v": 1, "view": "team", "settings": {"scoring": "ppr", "teams": 10, "superflex": False, "slots": [1, 2, 2, 1, 1, 6]},
                 "teams": [{"name": "A", "players": ["Josh Allen"]}, {"name": "B", "players": ["Jordan Love"]}], "me": 0,
                 "name": "USO Season XVIII", "enteredAt": "2026-11-02"}
        back = page.evaluate("s => DDF.link.encodeToken(s).then(t => DDF.link.decodeBlock(t))", state)
        self.assertEqual(back["name"], "USO Season XVIII")
        self.assertEqual(back["enteredAt"], "2026-11-02")
        old = page.evaluate("t => DDF.link.decodeBlock(t)", VECTOR_6)
        self.assertNotIn("error", old)
        self.assertNotIn("name", old)
        bad = dict(state, enteredAt="2026-02-30")
        self.assertEqual(page.evaluate("s => DDF.link.encodeToken(s).then(() => 'ok', e => e.message)", bad), "format")
        dropped = page.evaluate("s => DDF.link.decodeBlock(JSON.stringify(s))", dict(state, name="x" * 41, enteredAt="11/02/2026"))
        self.assertNotIn("name", dropped)
        self.assertNotIn("enteredAt", dropped)
        self.assertEqual(dropped["teams"], state["teams"])
        # the Bookmark link of a pasted league carries its teams, team, name and date (re-seed: decodeBlock replaced it)
        page2 = self.page(seed=seed_script(2))
        self.team(page2)
        page2.wait_for_selector(".ddf-bm", state="visible", timeout=20000)
        page2.click(".ddf-bm")
        page2.wait_for_function("() => /#s=/.test(location.href)", timeout=10000)
        linked = page2.evaluate("() => DDF.link.decodeBlock(location.href)")
        self.assertEqual([t["name"] for t in linked["teams"]], ["Fourth Down Club", "Hail Marys", "Kingdom of Caleb"])
        self.assertEqual(linked["me"], 1)
        self.assertEqual(linked["name"], "USO Season XVIII")
        self.assertRegex(linked["enteredAt"], r"^\d{4}-\d{2}-\d{2}$")

    def test_setup_suggests_the_found_name(self):
        page = self.page(width=390)
        page.goto(f"{self.base}/connect.html", wait_until="networkidle", timeout=60000)
        page.wait_for_function(ENGINE_READY, timeout=60000)
        page.fill("#rosters", (FIXTURES / "02-yahoo-markdown.txt").read_text(encoding="utf-8"))
        page.click("#recognize-button")
        page.wait_for_selector("#recognition-league:not([hidden])", timeout=20000)
        self.assertIn("We found: Sample League", page.text_content("#recognition-league"))
        kept = page.evaluate("JSON.parse(sessionStorage.getItem('ddf:pasted'))")
        self.assertEqual(kept["suggestedName"], "Sample League")
        self.assertNotIn("name", kept)
        page.click("#connect-next")
        page.wait_for_url("**/setup.html", timeout=20000)
        self.assertEqual(page.input_value("#league-name"), "Sample League")
        self.assertIsNone(page.evaluate("JSON.parse(sessionStorage.getItem('ddf:pasted')).name || null"), "not saved before confirming")
        page.click("label.setup-option >> nth=0")
        self.assertIsNone(page.evaluate("JSON.parse(sessionStorage.getItem('ddf:pasted')).name || null"), "an untouched suggestion is not saved on team confirm")
        self.assertEqual(page.evaluate("JSON.parse(localStorage.getItem('ddf.v2.workspaces')).workspaces[0].name"), "My league")
        page.fill("#league-name", "Sunday League")
        page.press("#league-name", "Tab")
        self.assertEqual(page.evaluate("JSON.parse(sessionStorage.getItem('ddf:pasted')).name"), "Sunday League")
        self.assertEqual(page.evaluate("JSON.parse(localStorage.getItem('ddf.v2.workspaces')).workspaces[0].name"), "Sunday League")
        self.assertEqual(page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth"), 0)


if __name__ == "__main__":
    unittest.main()
