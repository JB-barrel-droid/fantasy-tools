"""Customize "Select all / Select none" buttons are 44 px tall on phones (JEG-827).

Discrimination: test_guard_fails_on_old_css serves the CSS with the old 32 px height.
"""
from __future__ import annotations

import contextlib
import functools
import http.server
import socketserver
import threading
import unittest
from pathlib import Path

from tests import _render_env

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
CSS = ROOT / "app" / "v2" / "v2.css"
WIDTHS = (320, 375, 414)
NEW = ".v2-app .v2-call { min-height: 44px;"
OLD = ".v2-app .v2-call { min-height: 32px;"


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


PROBE = """async () => {
  document.querySelector('#v2EditSources').click();
  await new Promise(r => setTimeout(r, 500));
  return [...document.querySelectorAll('.v2-call')].map(e => {
    const b = e.getBoundingClientRect();
    return {text: e.textContent, h: b.height, w: b.width};
  });
}"""


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
            if css is not None:
                page.route("**/v2/v2.css*", lambda route: route.fulfill(status=200, content_type="text/css", body=css))
            page.goto(base + "#player-values", wait_until="networkidle")
            page.wait_for_timeout(1200)
            out[width] = page.evaluate(PROBE)
            page.close()
        browser.close()
    return out


def _errors(result) -> list[str]:
    errors = []
    for width, items in result.items():
        if not items:
            errors.append(f"{width}: no Select all/none buttons")
        errors += [f"{width}: {i['text']!r} is {i['h']:.0f}x{i['w']:.0f}" for i in items if i["h"] < 44 or i["w"] < 44]
    return errors


class CustomizeTargetsTest(unittest.TestCase):
    def test_select_buttons_44px(self):
        self.assertEqual(_errors(_run()), [])

    def test_guard_fails_on_old_css(self):
        css = CSS.read_text(encoding="utf-8")
        self.assertIn(NEW, css, "stale mutation anchor")
        self.assertTrue(_errors(_run(css.replace(NEW, OLD))), "old CSS was not caught")


if __name__ == "__main__":
    unittest.main()
