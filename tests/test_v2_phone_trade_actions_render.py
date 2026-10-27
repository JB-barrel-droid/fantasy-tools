"""Trade actions (Swap sides, Clear trade, Use this example) look like buttons (JEG-827).

They had no border and a transparent fill, so they read as plain text.

Discrimination: test_guard_fails_on_old_css serves the CSS with the fix removed.
"""
from __future__ import annotations

import contextlib
import functools
import http.server
import re
import socketserver
import threading
import unittest
from pathlib import Path

from tests import _render_env

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
CSS = ROOT / "app" / "v2" / "v2.css"
WIDTHS = (320, 375, 768)
FIX = re.compile(r"\n/\* JEG-827: the trade actions look like buttons.*?\n#v2Compare #v2CSwap[^\n]*\n", re.S)


def setUpModule():
    _render_env.ensure_built()


@contextlib.contextmanager
def _served():
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass
    with socketserver.ThreadingTCPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=str(DIST))) as server:
        server.daemon_threads = True
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            yield f"http://127.0.0.1:{server.server_address[1]}/v2/"
        finally:
            server.shutdown()


PROBE = """() => ['v2CSwap', 'v2CClear', 'v2CUseExample'].map(id => {
  const e = document.getElementById(id);
  e.hidden = false;
  const c = getComputedStyle(e), b = e.getBoundingClientRect();
  return {id, border: parseFloat(c.borderTopWidth), fill: c.backgroundColor, h: b.height};
})"""


def _run(css=None) -> dict:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise _render_env.unavailable("playwright is not installed")
    exe = _render_env.chromium_executable()
    if exe is None and _render_env.required() is False:
        raise _render_env.unavailable("no browser")
    out = {}
    with _served() as base, sync_playwright() as p:
        browser = p.chromium.launch(executable_path=exe, args=_render_env.HERMETIC_ARGS)
        for width in WIDTHS:
            page = browser.new_page(viewport={"width": width, "height": 812})
            page.add_init_script(_render_env.pin_data_week_script())
            if css is not None:
                page.route("**/v2/v2.css*", lambda route: route.fulfill(status=200, content_type="text/css", body=css))
            page.goto(base + "#compare-trade", wait_until="networkidle")
            page.wait_for_timeout(1200)
            out[width] = page.evaluate(PROBE)
            page.close()
        browser.close()
    return out


def _errors(result) -> list[str]:
    errors = []
    for width, items in result.items():
        for i in items:
            transparent = i["fill"] in ("rgba(0, 0, 0, 0)", "transparent")
            if i["border"] < 1 or transparent or i["h"] < 44:
                errors.append(f"{width}: {i['id']} reads as text (border {i['border']}, fill {i['fill']}, h {i['h']:.0f})")
    return errors


class TradeActionsTest(unittest.TestCase):
    def test_actions_are_buttons(self):
        self.assertEqual(_errors(_run()), [])

    def test_guard_fails_on_old_css(self):
        css = CSS.read_text(encoding="utf-8")
        self.assertTrue(FIX.search(css), "stale mutation anchor")
        self.assertTrue(_errors(_run(FIX.sub("\n", css))), "old CSS was not caught")


if __name__ == "__main__":
    unittest.main()
