"""JEG-1539: old v2 links that carry rosters become redesign league links (legacy-routes.js translate()).

The v2 assistant links (chat site_url: #find-trade / #compare-trade / #trade-targets with mine=, theirs=, target=) and
the league finder's share link (#find-league?workspace=<teams>&wm=<mine>) used to open a classic view with those
rosters. v2 is retired, so the front door turns them into a #s= league link on the page that does the job:
1. #find-trade?mine=&theirs=&scoring=&teams= -> find.html, two teams (yours first), the link's settings.
2. #trade-targets?target=&mine= -> values.html Buy / Sell with your team and the target.
3. #find-league?workspace=<name:keys|...>&wm=1 -> find.html with every team by name and wm as your team; from /v2/ too.
4. No page errors; plain routes are tested in tests/test_legacy_routes.py.
"""
from __future__ import annotations

import json
import re
import unittest
from urllib.parse import urlparse

from tests import _render_env
from tests._dist_server import DIST, serve

try:
    from playwright.sync_api import Error as PlaywrightError, sync_playwright
except ImportError:  # pragma: no cover
    sync_playwright = None

CLEAR = "try { if (!sessionStorage.getItem('__t')) { sessionStorage.clear(); localStorage.clear(); sessionStorage.setItem('__t','1'); } } catch (e) {}"


def b36(n: int) -> str:
    digits = "0123456789abcdefghijklmnopqrstuvwxyz"
    out = ""
    while True:
        n, r = divmod(n, 36)
        out = digits[r] + out
        if not n:
            return out


@unittest.skipUnless(sync_playwright and (DIST / "legacy-routes.js").exists(), "needs make sync and Playwright")
class LegacyLeagueLinks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        rows = json.loads((DIST / "players-table-1.json").read_text(encoding="utf-8"))
        cls.p = [dict(zip(("n", "pos", "team", "key"), r.split("|"))) for r in rows[:6]]
        cls._serve = serve(DIST)
        cls.base = cls._serve.__enter__()
        cls._pw = sync_playwright().start()
        try:
            cls.browser = cls._pw.chromium.launch(args=_render_env.HERMETIC_ARGS, executable_path=_render_env.chromium_executable(cls._pw))
        except PlaywrightError as exc:
            cls._pw.stop(); cls._serve.__exit__(None, None, None)
            raise _render_env.unavailable(f"Chromium not available: {exc}") from exc

    @classmethod
    def tearDownClass(cls):
        cls.browser.close(); cls._pw.stop(); cls._serve.__exit__(None, None, None)

    def land(self, path, page_re):
        ctx = self.browser.new_context()
        self.addCleanup(ctx.close)
        page = ctx.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.add_init_script(CLEAR)
        page.goto(self.base + path, wait_until="load", timeout=60000)
        page.wait_for_url(re.compile(page_re), timeout=30000)
        page.wait_for_function("() => sessionStorage.getItem('ddf:league')", timeout=30000)
        league = page.evaluate("() => JSON.parse(sessionStorage.getItem('ddf:league'))")
        self.assertEqual(errors, [], path)
        return page, league

    def test_find_trade_rosters(self):
        a, b, c = self.p[:3]
        page, lg = self.land(f"/#find-trade?mine={a['key']},{b['key']}&theirs={c['key']}&scoring=standard&teams=10&roster=QB1.RB2.WR2.TE1.FLEX1.SF1.BN6", r"/find\.html#s=")
        self.assertEqual([len(t["players"]) for t in lg["teams"]], [2, 1])
        self.assertEqual(lg["me"], 0)
        self.assertEqual(lg["settings"], {"scoring": "standard", "teams": 10, "superflex": True, "slots": [1, 2, 2, 1, 1, 6]})

    def test_link_settings_apply_for_the_visit_only(self):
        """Review of PR #1345: a link's league applies on the page but never overwrites the reader's saved settings."""
        a, b, c = self.p[:3]
        page, lg = self.land(f"/#find-trade?mine={a['key']},{b['key']}&theirs={c['key']}&scoring=standard&teams=10", r"/find\.html#s=")
        page.wait_for_function("() => window.DDF && DDF.league && DDF.engine.controls() && DDF.league.current()", timeout=90000)
        page.wait_for_timeout(1500)
        got = page.evaluate("() => [DDF.engine.settings().scoring, DDF.engine.settings().teams, localStorage.getItem('ddf.v2.league-settings')]")
        self.assertEqual(got, ["standard", 10, None])

    def test_chat_league_prices_every_page_in_the_tab(self):
        """Review of PR #1345: after a chat league arrives, Values in the same tab prices that league (visit only)."""
        a, b, c = self.p[:3]
        page, lg = self.land(f"/#find-trade?mine={a['key']},{b['key']}&theirs={c['key']}&scoring=standard&teams=10", r"/find\.html#s=")
        page.goto(self.base + "/values.html", wait_until="load", timeout=60000)
        page.wait_for_function("() => window.DDF && DDF.engine && DDF.engine.controls()", timeout=90000)
        got = page.evaluate("() => [DDF.engine.settings().scoring, DDF.engine.settings().teams, localStorage.getItem('ddf.v2.league-settings')]")
        self.assertEqual(got, ["standard", 10, None])

    def test_plain_route_league_settings(self):
        """#risers-fallers?scoring=&teams=&roster= (chat site_url, no rosters): values.html prices that league for the visit."""
        ctx = self.browser.new_context()
        self.addCleanup(ctx.close)
        page = ctx.new_page()
        page.add_init_script(CLEAR)
        page.goto(self.base + "/#risers-fallers?scoring=standard&teams=10&roster=QB1.RB2.WR3.TE1.FLEX1.SF1.BN6", wait_until="load", timeout=60000)
        page.wait_for_url(re.compile(r"/values\.html#\?scoring=standard"), timeout=30000)
        page.wait_for_function("() => window.DDF && DDF.engine && DDF.engine.controls()", timeout=90000)
        got = page.evaluate("() => { const s = DDF.engine.settings(); return [s.scoring, s.teams, s.roster.SUPERFLEX, s.roster.WR, localStorage.getItem('ddf.v2.league-settings')]; }")
        self.assertEqual(got, ["standard", 10, 1, 3, None])

    def test_trade_targets_target(self):
        a, c = self.p[0], self.p[3]
        page, lg = self.land(f"/#trade-targets?target={c['key']}&mine={a['key']}&scoring=half_ppr&teams=12", r"/values\.html#s=.*&buy-sell")
        self.assertEqual(lg["view"], "values")
        self.assertEqual(len(lg["teams"]), 1)

    def test_league_share_link(self):
        ws = f"Alpha:{','.join(b36(int(p['key'])) for p in self.p[:3])}|Beta:{','.join(b36(int(p['key'])) for p in self.p[3:])}"
        for prefix in ("/", "/v2/"):
            page, lg = self.land(f"{prefix}#find-league?workspace={ws}&wm=1&scoring=ppr&teams=12", r"/find\.html#s=")
            self.assertNotIn("/v2/", urlparse(page.url).path)
            self.assertEqual([t["name"] for t in lg["teams"]], ["Alpha", "Beta"])
            self.assertEqual([len(t["players"]) for t in lg["teams"]], [3, 3])
            self.assertEqual(lg["me"], 1)


if __name__ == "__main__":
    unittest.main()
