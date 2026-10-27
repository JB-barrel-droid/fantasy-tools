"""Phone layout guard for a Major mobile defect (JEG-810).

The the Targets positional-weight table pins the Group column (not the
Players count), shows Signal on first view, cues the sideways scroll, and keeps
the scroll inside its own box (the page never scrolls sideways).

Discrimination: test_guard_fails_on_old_css serves the CSS with each fix removed
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


WEIGHT = """async () => {
  const wrap = document.querySelector('#v2WeightTable').parentElement;
  const wr = wrap.getBoundingClientRect();
  const first = () => document.querySelector('#v2WeightTable tbody tr[data-group] td.player').getBoundingClientRect();
  const sig = document.querySelector('#v2WeightTable tbody tr[data-group] td.w-signal');
  const sr = sig.getBoundingClientRect();
  const res = {scrolls: wrap.scrollWidth > wrap.clientWidth, signalVisible: sr.right <= wr.right + 1 && sr.width > 0,
    pinnedHead: getComputedStyle(document.querySelector('#v2WeightTable th.player')).position,
    cue: /gradient/.test(getComputedStyle(wrap).backgroundImage)};
  wrap.scrollLeft = 200; await new Promise(r => setTimeout(r, 100));
  res.labelAfterScroll = Math.abs(first().left - wr.left) < 2 && first().width > 0;
  res.over = document.documentElement.scrollWidth - document.documentElement.clientWidth;
  return res;
}"""


def _run(css=None) -> dict:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise _render_env.unavailable("playwright is not installed")
    exe = _render_env.chromium_executable()
    if exe is None and _render_env.required() is False:
        raise _render_env.unavailable("no browser")
    out = {"weight": None}
    with _served() as base, sync_playwright() as p:
        browser = p.chromium.launch(executable_path=exe, args=_render_env.HERMETIC_ARGS)
        for width in (375,):
            page = browser.new_page(viewport={"width": width, "height": 812})
            page.add_init_script(_render_env.pin_data_week_script())
            if css is not None:
                page.route("**/v2/v2.css*", lambda route: route.fulfill(status=200, content_type="text/css", body=css))
            page.goto(base + "#trade-targets", wait_until="networkidle")
            page.wait_for_timeout(1200)
            out["weight"] = page.evaluate(WEIGHT)
            page.close()
        browser.close()
    return out


def _weight_errors(w) -> list[str]:
    errors = []
    if not w["scrolls"]:
        errors.append("weight table does not scroll inside its box at 375")
    if not w["signalVisible"]:
        errors.append("Signal column not visible on first view")
    if w["pinnedHead"] != "sticky":
        errors.append("Group header is not pinned")
    if not w["labelAfterScroll"]:
        errors.append("Group label gone after sideways scroll")
    if not w["cue"]:
        errors.append("no scroll cue")
    if w["over"] > 0:
        errors.append(f"page scrolls sideways by {w['over']}")
    return errors


class PhoneLayoutTest(unittest.TestCase):
    def test_weight_table_pins_group(self):
        r = _run()
        self.assertEqual(_weight_errors(r["weight"]), [])

    def test_guard_fails_on_old_css(self):
        css = CSS.read_text(encoding="utf-8")
        weight_fix = re.search(r"/\* JEG-810 \(phone\).*?\n\}\n", css, re.S)
        self.assertTrue(weight_fix, "stale mutation anchor")
        old = css.replace(weight_fix.group(0), "")
        r = _run(old)
        self.assertTrue(_weight_errors(r["weight"]), "old weight CSS was not caught")


if __name__ == "__main__":
    unittest.main()
