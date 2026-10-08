"""v2 navigation, Δ prior week, and player detail → Compare a trade.

Builds dist/v2 into a temp copy of the built dist/ and loads it headless:

  * at 390 px every tab sits fully on screen (frame 17: below 768 px the
    navigation shortens; nothing hides behind a sideways scroll), and every
    in-build tab still carries its visible "soon" label;
  * Δ prior week on: with no prior-week values saved, the reason is visible
    text on the page (not only a hover title) and every Δ cell reads "Δ —",
    never a number (frame 22);
  * player detail "Add to You give" / "Add to You get" puts that player on that
    side of Compare a trade and opens the tab; the detail then says the player
    is on the trade instead of offering to add them again; the player's name on
    Compare a trade opens the same detail;
  * no page errors and no horizontal overflow at 390 px.

Discrimination: test_guard_fails_on_broken_builds serves v2.css without the
wrapping tabs, v2.js without the visible Δ reason, and v2.js adding to the
wrong side, and requires the checks to fail on each.
"""
from __future__ import annotations

import contextlib
import functools
import http.server
import shutil
import socketserver
import sys
import tempfile
import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
sys.path.insert(0, str(ROOT / "pipelines"))
import build_v2_page  # noqa: E402

from tests.test_published_league_settings_render import _chromium_executable  # noqa: E402

V2_JS = ROOT / "app" / "v2" / "v2.js"
V2_CSS = ROOT / "app" / "v2" / "v2.css"
NAV_CSS = "/* Below 768 px every tab stays on screen: the tabs wrap instead of scrolling sideways. */"


def _serve(body, content_type, route, *_):
    route.fulfill(status=200, content_type=content_type, body=body)


@contextlib.contextmanager
def _built_dist():
    if not (DIST / "index.html").exists():
        raise unittest.SkipTest("dist/index.html is not built")
    with tempfile.TemporaryDirectory() as tmp:
        dist = Path(tmp) / "dist"
        shutil.copytree(DIST, dist, ignore=shutil.ignore_patterns("v2"))
        build_v2_page.build(dist)

        class QuietHandler(http.server.SimpleHTTPRequestHandler):
            def log_message(self, format, *args):
                pass
        handler = functools.partial(QuietHandler, directory=str(dist))
        with socketserver.ThreadingTCPServer(("127.0.0.1", 0), handler) as server:
            server.daemon_threads = True
            threading.Thread(target=server.serve_forever, daemon=True).start()
            try:
                yield f"http://127.0.0.1:{server.server_address[1]}/v2/#player-values"
            finally:
                server.shutdown()


def run_checks(v2_js=None, v2_css=None) -> list[str]:
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        raise unittest.SkipTest(f"Playwright is not available: {exc}") from exc
    errors = []
    with _built_dist() as url, sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(executable_path=_chromium_executable(playwright))
        except PlaywrightError as exc:
            raise unittest.SkipTest(f"Chromium is not available: {exc}") from exc
        try:
            page = browser.new_page(viewport={"width": 390, "height": 844})
            page_errors = []
            page.on("pageerror", lambda e: page_errors.append(str(e)))
            page.route(lambda u: not u.startswith("http://127.0.0.1"), lambda route: route.abort())
            if v2_js is not None:
                page.route("**/v2/v2.js*", functools.partial(_serve, v2_js, "text/javascript"))
            if v2_css is not None:
                page.route("**/v2/v2.css*", functools.partial(_serve, v2_css, "text/css"))
            page.goto(url, wait_until="networkidle")
            page.wait_for_function("() => window.TradeValueV2 && document.querySelector('#v2Table tbody tr')", timeout=30000)

            tabs = page.evaluate("""() => [...document.querySelectorAll('.v2-tab')].map(t => {
              const b = t.getBoundingClientRect();
              return {text: t.textContent, left: b.left, right: b.right, soon: t.classList.contains('is-soon'),
                after: getComputedStyle(t, '::after').content};
            })""")
            for tab in tabs:
                if tab["left"] < 0 or tab["right"] > 390:
                    errors.append(f"tab {tab['text']!r} is off screen at 390px ({tab['left']:.0f}–{tab['right']:.0f})")
                if tab["soon"] and "soon" not in (tab["after"] or ""):
                    errors.append(f"tab {tab['text']!r} is in build but has no visible label")

            page.click("#v2DeltaBtn")
            page.wait_for_timeout(300)
            delta = page.evaluate("""() => ({note: document.getElementById('v2FilterNote').hidden ? '' : document.getElementById('v2FilterNote').textContent,
              cells: [...document.querySelectorAll('#v2Table .delta')].map(d => d.textContent)})""")
            if "prior-week" not in delta["note"] or "never zero" not in delta["note"]:
                errors.append(f"Δ on: no visible reason, note {delta['note']!r}")
            if not delta["cells"] or any(c != "Δ —" for c in delta["cells"]):
                errors.append(f"Δ cells must all read 'Δ —': {sorted(set(delta['cells']))}")
            page.click("#v2DeltaBtn")

            # Detail → Compare a trade, one player to each side.
            picked = []
            for index, side in ((0, "give"), (1, "receive")):
                row = page.locator("#v2Table tbody tr").nth(index)
                # Default sort is the ranked view order, which the table rows follow.
                key = page.evaluate(f"() => String(window.TradeValueV2.view().rows[{index}].player_key)")
                picked.append((key, side))
                row.click()
                page.click(f'#v2Drawer [data-trade-add="{side}"]')
                page.wait_for_function("() => !document.getElementById('v2Compare').hidden")
                if index == 0:
                    page.evaluate("() => { location.hash = '#player-values'; }")
                    page.wait_for_function("() => !document.getElementById('v2Main').hidden")
            sides = page.evaluate("""() => ({give: [...document.querySelectorAll('#v2GivePlayers li[data-player-key]')].map(li => li.dataset.playerKey),
              receive: [...document.querySelectorAll('#v2GetPlayers li[data-player-key]')].map(li => li.dataset.playerKey)})""")
            for key, side in picked:
                if sides[side] != [key]:
                    errors.append(f"player {key} should be the only one on {side}: {sides}")
            if not page.evaluate("() => !document.getElementById('v2CTable').hidden && document.querySelectorAll('#v2CTable tbody tr').length > 0"):
                errors.append("Compare a trade shows no result rows after adding from detail")
            # The name on Compare a trade opens the same detail, which knows the player is on the trade.
            names = page.locator("#v2GivePlayers .v2-trade-name")
            if names.count():
                names.first.click()
                page.wait_for_timeout(200)
                on = page.evaluate("""() => ({open: !document.getElementById('v2Drawer').hidden,
                  on: document.querySelector('#v2Drawer [data-trade-on]')?.dataset.tradeOn || null,
                  add: document.querySelectorAll('#v2Drawer [data-trade-add]').length})""")
                if not on["open"] or on["on"] != "give" or on["add"]:
                    errors.append(f"detail from Compare a trade should say 'on your trade: you give': {on}")
            else:
                errors.append("player names on Compare a trade do not open the detail")
            overflow = page.evaluate("() => document.documentElement.scrollWidth - innerWidth")
            if overflow > 0:
                errors.append(f"horizontal overflow {overflow}px")
            if page_errors:
                errors.append(f"page errors {page_errors}")
            page.close()
        finally:
            browser.close()
    return errors


class NavRenderTest(unittest.TestCase):
    def test_nav_delta_and_detail_to_trade(self):
        self.assertEqual(run_checks(), [])

    def test_guard_fails_on_broken_builds(self):
        js = V2_JS.read_text(encoding="utf-8")
        css = V2_CSS.read_text(encoding="utf-8")
        broken = {
            "tabs scroll sideways": {"v2_css": css.replace(NAV_CSS, NAV_CSS + "\n@media (max-width: 0px) {", 1)
                                     .replace("  .v2-tab { min-height: 44px; }\n}", "  .v2-tab { min-height: 44px; }\n}\n}", 1)},
            "Δ reason only on hover": {"v2_js": js.replace("    if (state.delta) {\n      notes.push(", "    if (false) {\n      notes.push(", 1)},
            "added to the wrong side": {"v2_js": js.replace(
                "TR[side] = TR[side].concat({key, name: row.name});",
                'TR.give = TR.give.concat({key, name: row.name});', 1)},
        }
        for name, kwargs in broken.items():
            with self.subTest(mutation=name):
                body = next(iter(kwargs.values()))
                self.assertNotIn(body, (js, css), f"mutation anchor for {name!r} is stale")
                self.assertNotEqual(run_checks(**kwargs), [], f"render checks did not catch: {name}")


if __name__ == "__main__":
    unittest.main()
