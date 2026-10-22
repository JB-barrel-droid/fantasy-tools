"""No tab may scroll sideways at 320 px, and the Values "Rank by" field stays inside the screen (JEG-827).

The Values toolbar's "Rank by" label and series picker ran 2-3 px past a 320 px screen.

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
HASHES = ("player-values", "trade-targets", "risers-fallers", "compare-trade", "writing/how-values", "writing/research", "values-auditing", "writing/manifesto")
FIX = re.compile(r"\n/\* JEG-827: the Values \"Rank by\".*?\n\}\n", re.S)


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
  const f = document.querySelector('#v2Main .v2-field-rank');
  const r = f && f.getBoundingClientRect();
  return {over: document.documentElement.scrollWidth - innerWidth, rankRight: r ? r.right : null};
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
        page = browser.new_page(viewport={"width": 320, "height": 800})
        if css is not None:
            page.route("**/v2/v2.css*", lambda route: route.fulfill(status=200, content_type="text/css", body=css))
        for h in HASHES:
            page.goto(base + "#" + h, wait_until="networkidle")
            page.wait_for_timeout(900)
            out[h] = page.evaluate(PROBE)
        browser.close()
    return out


def _errors(result) -> list[str]:
    errors = [f"{h}: scrolls sideways by {r['over']}" for h, r in result.items() if r["over"] > 0]
    right = result["player-values"]["rankRight"]
    if right is None or right > 320:
        errors.append(f"player-values: Rank by field ends at {right}")
    return errors


class RankOverflowTest(unittest.TestCase):
    def test_no_overflow_at_320(self):
        self.assertEqual(_errors(_run()), [])

    def test_guard_fails_on_old_css(self):
        css = CSS.read_text(encoding="utf-8")
        self.assertTrue(FIX.search(css), "stale mutation anchor")
        self.assertTrue(_errors(_run(FIX.sub("\n", css))), "old CSS was not caught")


if __name__ == "__main__":
    unittest.main()
