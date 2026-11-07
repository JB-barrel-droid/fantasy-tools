"""JEG-1560 addition (Jeremy 2026-11-07): the chart count on offer cards reads "N/M public trade charts" and links to
Build a Trade for that trade, scrolled to its charts (build.html?give=<name>&get=<name>#trade-charts, JEG-1559's anchor).

What we guard on find.html with the seeded league, at 1440x900 and 390x844:
- every offer card's chart link text is "<rivalOk>/<charts> public trade charts" (the old "N/M charts" label is gone);
- its href is the card's own Build a Trade href plus #trade-charts, and that href is build.html with one give / get
  parameter per player name of the card (an independent rebuild from the card's player keys and the engine rows);
- its aria-label says "See the N of M public trade charts for this trade";
- on 390 the link is at least 44px tall.
The anchor scroll itself is checked once JEG-1559 (#trade-charts on build.html) is on main; until then only the href.
"""
from __future__ import annotations

import re
import unittest
from urllib.parse import parse_qsl, urlsplit

from tests import _render_env
from tests._dist_server import DIST, serve
from tests.test_find_engine_parity import APPLY, READY
from tests.test_team_engine_parity import seed_script, seeded_league

READ = r"""() => [...document.querySelectorAll('[data-offer]')].map(card => {
  const a = card.querySelector('a[data-charts]'), b = card.querySelector('a[data-build]');
  const names = keys => keys.split(',').filter(Boolean).map(k => DDF.engine.player(k).n);
  return {text: a ? a.textContent.trim() : null, href: a ? a.getAttribute('href') : null, aria: a ? a.getAttribute('aria-label') : null,
    build: b.getAttribute('href'), height: a ? a.getBoundingClientRect().height : 0, give: names(card.dataset.give), get: names(card.dataset.receive),
    old: /\d+\/\d+ charts\b/.test(card.textContent)};
})"""


def league():
    lg = seeded_league()
    del lg["teams"][lg["me"]]["players"][1:3]
    return lg


class FindChartLinksTest(unittest.TestCase):
    def test_chart_count_links_to_build_charts(self):
        try:
            from playwright.sync_api import sync_playwright
        except Exception as exc:  # noqa: BLE001
            raise _render_env.unavailable(f"Playwright not available: {exc}") from exc
        if not (DIST / "find.html").exists():
            raise _render_env.unavailable("dist/find.html is not built")
        with serve(DIST) as base, sync_playwright() as pw:
            try:
                browser = pw.chromium.launch(args=_render_env.HERMETIC_ARGS, executable_path=_render_env.chromium_executable())
            except Exception as exc:  # noqa: BLE001
                raise _render_env.unavailable(f"Chromium not available: {exc}") from exc
            try:
                for w, h in ((1440, 900), (390, 844)):
                    page = browser.new_page(viewport={"width": w, "height": h})
                    errors = []
                    page.on("pageerror", lambda e: errors.append(str(e)))
                    page.route(lambda u: not u.startswith(base), lambda r: r.abort())
                    page.add_init_script(seed_script(league()))
                    page.goto(f"{base}/find.html", wait_until="domcontentloaded", timeout=60000)
                    page.evaluate(APPLY, ["ppr", 12, False])
                    page.wait_for_timeout(300)
                    page.wait_for_function(READY, timeout=120000)
                    cards = page.evaluate(READ)
                    self.assertTrue(cards, f"{w}: no offer cards for the seeded league")
                    for c in cards:
                        m = re.fullmatch(r"(\d+)/(\d+) public trade charts", c["text"] or "")
                        self.assertIsNotNone(m, f"{w}: label {c['text']!r}")
                        self.assertFalse(c["old"], f"{w}: old 'N/M charts' label still on a card")
                        self.assertEqual(c["aria"], f"See the {m[1]} of {m[2]} public trade charts for this trade")
                        self.assertEqual(c["href"], c["build"] + "#trade-charts")
                        url = urlsplit(c["href"])
                        self.assertEqual((url.path, url.fragment), ("build.html", "trade-charts"))
                        q = parse_qsl(url.query)
                        self.assertEqual([v for k, v in q if k == "give"], c["give"])
                        self.assertEqual([v for k, v in q if k == "get"], c["get"])
                        if w == 390:
                            self.assertGreaterEqual(round(c["height"], 1), 44, f"390: chart link {c['height']}px tall")
                    self.assertEqual(errors, [])
                    page.close()
            finally:
                browser.close()


if __name__ == "__main__":
    unittest.main()
