"""Trade player rows must not clip their meta text (JEG-827).

At 320, 375 and 768 px the "WR · SEA · Starter" line sat beside the name in a
nowrap/ellipsis box and was cut to "W" or "R...". It must wrap under the name.

Discrimination: test_guard_fails_on_old_css serves the CSS with the fix reverted.
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
WIDTHS = (320, 375, 414, 768)
NEW = "display: inline; white-space: normal; min-width: 0; }"
OLD = "display: inline; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; min-width: 0; }"


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


PROBE = """() => [...document.querySelectorAll('#v2Compare .v2-trade-players li')].map(li => {
  const d = li.querySelector('div'), m = d.querySelector('.v2-meta');
  const r = m.getBoundingClientRect(), p = li.getBoundingClientRect();
  return {text: m.textContent.trim(), clipped: m.scrollWidth - m.clientWidth, outside: r.right - p.right,
          ellipsis: getComputedStyle(m).textOverflow === 'ellipsis', over: document.documentElement.scrollWidth - innerWidth};
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
            # JEG-1190: Compare opens empty; the sample trade gives the rows to measure.
            page.click("#v2CTryExample")
            page.wait_for_timeout(400)
            out[width] = page.evaluate(PROBE)
            page.close()
        browser.close()
    return out


def _errors(result) -> list[str]:
    errors = []
    for width, rows in result.items():
        if not rows:
            errors.append(f"{width}: no trade rows rendered")
        for row in rows:
            if row["clipped"] > 0 or row["ellipsis"] or row["outside"] > 0:
                errors.append(f"{width}: meta clipped for {row['text']!r}")
    return errors


class TradeRowsTest(unittest.TestCase):
    def test_meta_not_clipped(self):
        self.assertEqual(_errors(_run()), [])

    def test_guard_fails_on_old_css(self):
        css = CSS.read_text(encoding="utf-8")
        self.assertIn(NEW, css, "stale mutation anchor")
        self.assertTrue(_errors(_run(css.replace(NEW, OLD))), "old CSS was not caught")


if __name__ == "__main__":
    unittest.main()
