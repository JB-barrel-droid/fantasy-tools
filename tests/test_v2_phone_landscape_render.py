"""Landscape phone guard (JEG-824).

At 812x375 the Values toolbar (108 px) and table foot stuck to the screen and hid the
table header, leaving a ~4 row window. In short viewports the toolbar and foot must not
stick, the table header must be the element at its own position, and the table scroller
must take most of the screen. Tall viewports keep the sticky toolbar.

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
FIX = re.compile(r"\n/\* JEG-824:.*?\n\}\n", re.S)


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
  const wrap = document.querySelector('#v2Main .v2-table-wrap');
  window.scrollTo({top: wrap.getBoundingClientRect().top + scrollY - 8, behavior: 'instant'});
  await new Promise(r => setTimeout(r, 300));
  const th = document.querySelector('.v2-vtable .v2-head-row th.player') || document.querySelector('.v2-vtable thead th');
  const b = th.getBoundingClientRect();
  const hit = document.elementFromPoint(b.left + b.width / 2, b.top + b.height / 2);
  return {
    toolbar: getComputedStyle(document.querySelector('#v2Main .v2-toolbar')).position,
    foot: getComputedStyle(document.querySelector('#v2Main .v2-table-foot')).position,
    wrapH: wrap.getBoundingClientRect().height,
    headVisible: b.top >= 0 && b.bottom <= innerHeight && !!hit && th.contains(hit),
  };
}"""


def _run(width, height, css=None) -> dict:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise _render_env.unavailable("playwright is not installed")
    exe = _render_env.chromium_executable()
    if exe is None and _render_env.required() is False:
        raise _render_env.unavailable("no browser")
    with _served() as base, sync_playwright() as p:
        browser = p.chromium.launch(executable_path=exe, args=_render_env.HERMETIC_ARGS)
        page = browser.new_page(viewport={"width": width, "height": height})
        page.add_init_script(_render_env.pin_data_week_script())
        if css is not None:
            page.route("**/v2/v2.css*", lambda route: route.fulfill(status=200, content_type="text/css", body=css))
        page.goto(base + "#player-values", wait_until="networkidle")
        page.wait_for_timeout(1200)
        out = page.evaluate(PROBE)
        browser.close()
    return out


def _landscape_errors(r) -> list[str]:
    errors = []
    if r["toolbar"] == "sticky":
        errors.append("toolbar sticky in landscape")
    if r["foot"] == "sticky":
        errors.append("table foot sticky in landscape")
    if not r["headVisible"]:
        errors.append("table header hidden")
    if r["wrapH"] < 250:
        errors.append(f"table window only {r['wrapH']:.0f}px")
    return errors


class LandscapeTest(unittest.TestCase):
    def test_landscape_table_usable(self):
        for size in ((812, 375), (896, 414)):
            self.assertEqual(_landscape_errors(_run(*size)), [], size)

    def test_tall_viewport_keeps_sticky_toolbar(self):
        self.assertEqual(_run(1024, 768)["toolbar"], "sticky")

    def test_guard_fails_on_old_css(self):
        css = CSS.read_text(encoding="utf-8")
        self.assertTrue(FIX.search(css), "stale mutation anchor")
        self.assertTrue(_landscape_errors(_run(812, 375, FIX.sub("\n", css))), "old CSS was not caught")


if __name__ == "__main__":
    unittest.main()
