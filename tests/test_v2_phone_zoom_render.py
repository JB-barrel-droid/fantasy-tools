"""The chart zoom row must not cover the plot below 1024 px (JEG-827).

The zoom buttons were absolutely placed over the top 44 px of the chart at 320-768 px.
They now sit in their own strip above it.

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
WIDTHS = (320, 375, 414, 768)
FIX = re.compile(r"\n/\* JEG-827: below 1024 px the zoom row.*?max-width: 767px\) \{ \.v2-plot-main \{ height: 308px; \} \}\n", re.S)


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


PROBE = """() => {
  const z = document.querySelector('.v2-zoom').getBoundingClientRect();
  const c = document.querySelector('#v2Chart').getBoundingClientRect();
  return {zoomBottom: z.bottom, chartTop: c.top, chartH: c.height, over: document.documentElement.scrollWidth - innerWidth};
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
            page = browser.new_page(viewport={"width": width, "height": 900})
            page.add_init_script(_render_env.pin_data_week_script())
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
    for width, r in result.items():
        if r["zoomBottom"] > r["chartTop"] + 0.5:
            errors.append(f"{width}: zoom row covers the plot ({r['zoomBottom'] - r['chartTop']:.0f}px)")
        if r["chartH"] < 250:
            errors.append(f"{width}: chart shrank to {r['chartH']:.0f}px")
    return errors


class ZoomRowTest(unittest.TestCase):
    def test_zoom_row_clear_of_plot(self):
        self.assertEqual(_errors(_run()), [])

    def test_guard_fails_on_old_css(self):
        css = CSS.read_text(encoding="utf-8")
        self.assertTrue(FIX.search(css), "stale mutation anchor")
        self.assertTrue(_errors(_run(FIX.sub("\n", css))), "old CSS was not caught")


if __name__ == "__main__":
    unittest.main()
