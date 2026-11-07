"""JEG-1560 C: a pasted league (sessionStorage ddf:pasted, no saved workspace) counts as a league on every page.

values.html Buy / Sell read DDF.engine.league() (saved workspace only), so it showed "Add your league to see..." with a
pasted league loaded. It now reads DDF.league. What we guard, with the seeded league of tests.test_team_engine_parity:
- pasted league: no "Add your league" card on values.html (Buy / Sell), partners.html or team.html, and Buy / Sell
  shows the Sell card (my team is known);
- no league: the card shows on all three, linking to connect.html.
"""
from __future__ import annotations

import unittest

from tests import _render_env
from tests._dist_server import DIST, serve
from tests.test_team_engine_parity import seed_script, seeded_league

PAGES = {
    "values.html#buy-sell": "() => ({card: !document.getElementById('bs-nolg').hidden, link: document.querySelector('#bs-nolg a').getAttribute('href'), sell: !document.getElementById('bs-sell-card').hidden})",
    "partners.html": "() => ({card: !document.getElementById('no-league').hidden, link: (document.querySelector('#no-league a') || {getAttribute: () => null}).getAttribute('href')})",
    "team.html": "() => ({card: !document.getElementById('no-league').hidden, link: document.querySelector('#no-league a').getAttribute('href')})",
}


class LeagueCardPastedTest(unittest.TestCase):
    def test_add_league_card_follows_pasted_league(self):
        try:
            from playwright.sync_api import sync_playwright
        except Exception as exc:  # noqa: BLE001
            raise _render_env.unavailable(f"Playwright not available: {exc}") from exc
        if not all((DIST / p.split("#")[0]).exists() for p in PAGES):
            raise _render_env.unavailable("dist pages are not built")
        with serve(DIST) as base, sync_playwright() as pw:
            try:
                browser = pw.chromium.launch(args=_render_env.HERMETIC_ARGS, executable_path=_render_env.chromium_executable())
            except Exception as exc:  # noqa: BLE001
                raise _render_env.unavailable(f"Chromium not available: {exc}") from exc
            try:
                for league in (seeded_league(), None):
                    for path, read in PAGES.items():
                        page = browser.new_page(viewport={"width": 1440, "height": 900})
                        errors = []
                        page.on("pageerror", lambda e: errors.append(str(e)))
                        page.route(lambda u: not u.startswith(base), lambda r: r.abort())
                        page.add_init_script(seed_script(league))
                        page.goto(f"{base}/{path}", wait_until="networkidle", timeout=60000)
                        page.wait_for_function("() => window.DDF && DDF.league && DDF.league.ready", timeout=30000)
                        page.evaluate("() => DDF.league.ready")
                        page.wait_for_timeout(500)
                        got = page.evaluate(read)
                        label = f"{path} ({'pasted league' if league else 'no league'})"
                        self.assertEqual(got["card"], league is None, f"{label}: Add your league card shown={got['card']}")
                        if league is None:
                            self.assertEqual(got["link"], "connect.html", label)
                        if path.startswith("values") and league:
                            self.assertTrue(got["sell"], f"{label}: Sell card hidden with my team known")
                        self.assertEqual(errors, [], label)
                        page.close()
            finally:
                browser.close()


if __name__ == "__main__":
    unittest.main()
