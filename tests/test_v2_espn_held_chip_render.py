"""JEG-834: while ESPN is held, the ESPN-zero chip reads "held this week", never "ESPN: 0 (out)".

Headless against a temp copy of dist/ with the pinned holds (tests/_holds.py), ESPN open as the control (chip
"ESPN: 0 (out)") and ESPN held as the case (chip "ESPN: held this week"), for a real player ESPN projects at 0.
test_guard_fails_on_broken_build serves a v2.js that ignores the hold and requires the held case to fail.
"""
from __future__ import annotations

import contextlib
import functools
import http.server
import json
import shutil
import socketserver
import tempfile
import threading
import unittest
from pathlib import Path

from tests import _render_env
from tests._holds import pin_holds_in_dist
from tests.test_published_league_settings_render import _chromium_executable
from tests.test_v2_targets_render import DIST, build_v2_page, engine_path

ROOT = Path(__file__).resolve().parents[1]
V2_JS = ROOT / "app" / "v2" / "v2.js"


def setUpModule():
    _render_env.ensure_built()


@contextlib.contextmanager
def _served(espn_held):
    with tempfile.TemporaryDirectory() as tmp:
        dist = Path(tmp) / "dist"
        shutil.copytree(DIST, dist, ignore=shutil.ignore_patterns("v2"))
        pin_holds_in_dist(dist)
        if espn_held:
            path = dist / "assets" / "comparison-sources-data.json"
            doc = json.loads(path.read_text(encoding="utf-8"))
            doc["sources"]["espn"]["validationHold"] = {"reason": "chain hold: review hold", "root": "espn", "stage": "review"}
            path.write_text(json.dumps(doc, separators=(",", ":")), encoding="utf-8")
        build_v2_page.build(dist)

        class Quiet(http.server.SimpleHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def translate_path(self, path):
                return engine_path(path) or super().translate_path(path)
        handler = functools.partial(Quiet, directory=str(dist))
        with socketserver.ThreadingTCPServer(("127.0.0.1", 0), handler) as server:
            server.daemon_threads = True
            threading.Thread(target=server.serve_forever, daemon=True).start()
            try:
                yield f"http://127.0.0.1:{server.server_address[1]}/v2/#player-values"
            finally:
                server.shutdown()


def chip_text(espn_held, v2_js=None):
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        raise _render_env.unavailable(f"Playwright is not available: {exc}") from exc
    with _served(espn_held) as url, sync_playwright() as pw:
        try:
            browser = pw.chromium.launch(args=_render_env.HERMETIC_ARGS, executable_path=_chromium_executable(pw))
        except PlaywrightError as exc:
            raise _render_env.unavailable(f"Chromium is not available: {exc}") from exc
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            page.route(lambda u: not u.startswith("http://127.0.0.1"), lambda route: route.abort())
            if v2_js is not None:
                page.route("**/v2/v2.js*", lambda route: route.fulfill(status=200, content_type="text/javascript", body=v2_js))
            page.goto(url, wait_until="networkidle")
            page.wait_for_function("() => window.TradeValueV2 && document.querySelector('#v2Table tbody tr')", timeout=40000)
            name = page.evaluate("() => (window.TradeValueCurveControls.getRows().find(r => r.espnProjectsZero) || {}).name || null")
            if not name:
                return None, None
            page.fill("#v2Search", name)
            page.wait_for_timeout(500)
            return name, page.evaluate("() => document.querySelector('#v2Table tbody [data-espn-zero]')?.textContent || null")
        finally:
            browser.close()


class EspnHeldChipTest(unittest.TestCase):
    def test_held_espn_reads_held_not_zero(self):
        name, open_chip = chip_text(False)
        self.assertIsNotNone(name, "no ESPN-zero player in the data (nothing to test)")
        self.assertIn("ESPN: 0 (out)", open_chip or "")
        _, held_chip = chip_text(True)
        self.assertIn("held this week", held_chip or "")
        self.assertNotIn("0 (out)", held_chip or "")

    def test_guard_fails_on_broken_build(self):
        v2 = V2_JS.read_text(encoding="utf-8")
        broken = v2.replace("if (heldReason(view && view.infoByKey && view.infoByKey.espn)) {", "if (false) {", 1)
        self.assertNotEqual(broken, v2)
        _, chip = chip_text(True, v2_js=broken)
        self.assertIn("0 (out)", chip or "", "the broken build should still show the zero chip")


if __name__ == "__main__":
    unittest.main()
