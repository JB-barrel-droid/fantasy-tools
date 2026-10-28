"""Phone layout guard for a Major mobile defect (JEG-809).

JEG-809: the Values "All selected values" card head must wrap at 320-767 px
(title takes the row, buttons below), not squeeze the title to 2 px.

Discrimination: test_guard_fails_on_old_css serves the CSS with the fix removed
and requires the check to fail.
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
WIDTHS = (320, 375, 414, 768, 1440)


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


HEAD = """() => {
  const r = s => document.querySelector(s).getBoundingClientRect();
  const h = r('#v2TableTitle'), m = r('#v2TableMeta'), c = r('#v2Columns'), e = r('#v2ExpandTable');
  const hit = (a, b) => a.left < b.right - 1 && b.left < a.right - 1 && a.top < b.bottom - 1 && b.top < a.bottom - 1;
  return {titleW: h.width, titleH: h.height, metaH: m.height, overlap: hit(h, c) || hit(h, e) || hit(m, c) || hit(m, e) || hit(c, e),
          over: document.documentElement.scrollWidth - document.documentElement.clientWidth};
}"""


def _run(css=None) -> dict:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise _render_env.unavailable("playwright is not installed")
    exe = _render_env.chromium_executable()
    if exe is None and _render_env.required() is False:
        raise _render_env.unavailable("no browser")
    out = {"head": {}}
    with _served() as base, sync_playwright() as p:
        browser = p.chromium.launch(executable_path=exe, args=_render_env.HERMETIC_ARGS)
        for width in WIDTHS:
            page = browser.new_page(viewport={"width": width, "height": 812})
            page.add_init_script(_render_env.pin_data_week_script())
            if css is not None:
                page.route("**/v2/v2.css*", lambda route: route.fulfill(status=200, content_type="text/css", body=css))
            page.goto(base + "#player-values", wait_until="networkidle")
            page.wait_for_timeout(1200)
            out["head"][width] = page.evaluate(HEAD)
            page.close()
        browser.close()
    return out


def _head_errors(result) -> list[str]:
    errors = []
    for width, h in result["head"].items():
        if h["over"] > 0 and width >= 375:  # 320: the 7-tab nav row overflows on its own (not this card)
            errors.append(f"{width}: page scrolls sideways by {h['over']}")
        if h["overlap"]:
            errors.append(f"{width}: head parts overlap")
        if width < 768 and (h["titleW"] < 120 or h["titleH"] > 60):
            errors.append(f"{width}: title squeezed ({h['titleW']:.0f}x{h['titleH']:.0f})")
    return errors


class PhoneLayoutTest(unittest.TestCase):
    def test_head_wraps(self):
        r = _run()
        self.assertEqual(_head_errors(r), [])

    def test_guard_fails_on_old_css(self):
        css = CSS.read_text(encoding="utf-8")
        head_fix = re.search(r"@media \(max-width: 767px\) \{ \.v2-table-head \{ flex-wrap: wrap; \}[^\n]*\n", css)
        self.assertTrue(head_fix, "stale mutation anchors")
        old = css.replace(head_fix.group(0), "@media (max-width: 767px) { .v2-table-head h2 { flex: 0 1 auto; min-width: 0; } }\n")
        r = _run(old)
        self.assertTrue(_head_errors(r), "old head CSS was not caught")


if __name__ == "__main__":
    unittest.main()
