"""v2 shareable trade links and page metadata.

Builds dist/v2 into a temp copy of the built dist/ and loads it headless:

  * build a trade on Compare a trade through the search boxes; the address
    becomes #compare-trade?give=<keys>&get=<keys>;
  * opening that address in a fresh page shows the same players on the same
    sides and the same per-source rows (same give / get / net text);
  * a link with an unknown or repeated key does not crash: the unknown player is
    listed, every row it touches shows —, and a repeated key appears once;
  * the built page declares color-scheme "light dark" (v2 has a dark theme;
    v1's "light" left form controls light inside it).

Discrimination: test_guard_fails_on_broken_builds serves v2.js without
reading the hash and without writing it, and requires the checks to fail.
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
from tests import _render_env  # noqa: E402


def setUpModule():
    # Build app/ and dist/ from the committed fixtures first, so the
    # test never reads a stale committed build (GAP-APP-ASSETS-LAG).
    _render_env.ensure_built()


V2_JS = ROOT / "app" / "v2" / "v2.js"

READ = """() => ({hash: location.hash,
  give: [...document.querySelectorAll('#v2GivePlayers li[data-player-key]')].map(li => li.dataset.playerKey),
  get: [...document.querySelectorAll('#v2GetPlayers li[data-player-key]')].map(li => li.dataset.playerKey),
  rows: [...document.querySelectorAll('#v2CTable tbody tr')].map(tr => tr.dataset.source + ' ' + tr.textContent),
  scheme: document.querySelector('meta[name=color-scheme]')?.content})"""


def _serve(body, route, *_):
    route.fulfill(status=200, content_type="text/javascript", body=body)


@contextlib.contextmanager
def _built_dist():
    if not (DIST / "index.html").exists():
        raise _render_env.unavailable("dist/index.html is not built")
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
                yield f"http://127.0.0.1:{server.server_address[1]}/v2/"
            finally:
                server.shutdown()


def run_checks(v2_js=None) -> list[str]:
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        raise _render_env.unavailable(f"Playwright is not available: {exc}") from exc
    errors = []
    with _built_dist() as base, sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(args=_render_env.HERMETIC_ARGS, executable_path=_chromium_executable(playwright))
        except PlaywrightError as exc:
            raise _render_env.unavailable(f"Chromium is not available: {exc}") from exc

        def open_page(url):
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            page.errors = []
            page.on("pageerror", lambda e: page.errors.append(str(e)))
            page.route(lambda u: not u.startswith("http://127.0.0.1"), lambda route: route.abort())
            if v2_js is not None:
                page.route("**/v2/v2.js*", functools.partial(_serve, v2_js))
            page.goto(url, wait_until="networkidle")
            page.wait_for_function("() => window.TradeValueV2 && window.TradeValueV2.compare()", timeout=30000)
            page.wait_for_timeout(200)
            return page

        try:
            page = open_page(base + "#compare-trade")
            for field, results, query in (("#v2GiveSearch", "#v2GiveResults", "Gibbs"), ("#v2GiveSearch", "#v2GiveResults", "Nacua"),
                                          ("#v2GetSearch", "#v2GetResults", "Chase")):
                page.fill(field, query)
                page.click(f"{results} button >> nth=0")
            first = page.evaluate(READ)
            if first["scheme"] != "light dark":
                errors.append(f"color-scheme meta is {first['scheme']!r}, expected 'light dark'")
            want = f"#compare-trade?give={','.join(first['give'])}&get={','.join(first['get'])}"
            if first["hash"] != want:
                errors.append(f"address {first['hash']!r} != {want!r}")
            shared = open_page(base + want)
            second = shared.evaluate(READ)
            if (second["give"], second["get"]) != (first["give"], first["get"]):
                errors.append(f"shared link opened {second['give']} / {second['get']}, built {first['give']} / {first['get']}")
            if not first["rows"] or second["rows"] != first["rows"]:
                errors.append("shared link rows differ from the built trade's rows")
            odd = open_page(base + f"#compare-trade?give={first['give'][0]},{first['give'][0]},999999999&get={first['get'][0]}")
            third = odd.evaluate(READ)
            if third["give"] != [first["give"][0], "999999999"]:
                errors.append(f"repeated / unknown keys: give side {third['give']}")
            if not third["rows"] or any("—" not in r for r in third["rows"]):
                errors.append("an unknown player must turn every row into —")
            for p in (page, shared, odd):
                if p.errors:
                    errors.append(f"page errors {p.errors}")
                p.close()
        finally:
            browser.close()
    return errors


class ShareRenderTest(unittest.TestCase):
    def test_shared_trade_link(self):
        self.assertEqual(run_checks(), [])

    def test_guard_fails_on_broken_builds(self):
        js = V2_JS.read_text(encoding="utf-8")
        broken = {
            "hash not read": js.replace("    bind();\n    readTradeHash();\n", "    bind();\n", 1),
            "hash not written": js.replace("    if (location.hash !== want) history.replaceState(null, \"\", want);", "", 1),
        }
        for name, body in broken.items():
            with self.subTest(mutation=name):
                self.assertNotEqual(body, js, f"mutation anchor for {name!r} is stale")
                self.assertNotEqual(run_checks(body), [], f"render checks did not catch: {name}")


if __name__ == "__main__":
    unittest.main()
