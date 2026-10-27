"""Phone layouts hold in a wide fallback face at 320, 375 and 414 px (JEG-829).

tests/test_v2_phone_layout_render.py and test_v2_phone_weight_render.py passed on a Mac with Inter and
failed on the Linux runner ("375: page scrolls sideways by 6", "Signal column not visible on first
view"), because the runner falls back to DejaVu Sans. Real Android and Windows hosts fall back to
similarly wide faces. This test forces the widest installed of DejaVu Sans / Verdana on every element
and requires: no sideways page scroll on any tab, and the Targets weight table's Signal column fully
visible on first view at 375 and 414.

Discrimination: test_guard_fails_on_old_css serves the CSS with the JEG-829 block removed.
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
TABS = ("player-values", "trade-targets", "risers-fallers", "compare-trade", "find-trade", "writing/how-values", "writing/research", "values-auditing", "writing/manifesto")
WIDTHS = (320, 375, 414)
FAMILIES = ("DejaVu Sans", "Verdana")
FIX = re.compile(r"\n/\* JEG-829: a host without Inter.*?\n\}\n@media \(min-width: 360px\)[^\n]*\n", re.S)


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


HAS_FACE = """(family) => { const c = document.createElement('canvas').getContext('2d'); const t = 'Wide fallback face WMwmi 0123';
  c.font = "40px monospace"; const a = c.measureText(t).width; c.font = `40px '${family}', monospace`; return c.measureText(t).width !== a; }"""
PROBE = """() => {
  const sig = document.querySelector('#v2WeightTable tbody tr[data-group] td.w-signal');
  let signalCut = null;
  if (sig) {
    const wrap = document.querySelector('#v2WeightTable').parentElement.getBoundingClientRect();
    signalCut = sig.getBoundingClientRect().right - wrap.right;
  }
  return {over: document.documentElement.scrollWidth - document.documentElement.clientWidth, signalCut};
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
        probe = browser.new_page()
        probe.add_init_script(_render_env.pin_data_week_script())
        family = next((f for f in FAMILIES if probe.evaluate(HAS_FACE, f)), None)
        probe.close()
        if family is None:
            browser.close()
            raise _render_env.unavailable("neither DejaVu Sans nor Verdana is installed")
        init = ("document.addEventListener('DOMContentLoaded',()=>{const s=document.createElement('style');"
                f"s.textContent=\"*{{font-family:'{family}',sans-serif !important}}\";document.head.appendChild(s)}})")
        for width in WIDTHS:
            for tab in TABS:
                page = browser.new_page(viewport={"width": width, "height": 812})
                page.add_init_script(_render_env.pin_data_week_script())
                page.add_init_script(init)
                if css is not None:
                    page.route("**/v2/v2.css*", lambda route: route.fulfill(status=200, content_type="text/css", body=css))
                page.goto(base + "#" + tab, wait_until="networkidle")
                page.wait_for_timeout(800)
                out[(width, tab)] = page.evaluate(PROBE)
                page.close()
        browser.close()
    return out


def _errors(result) -> list[str]:
    errors = []
    for (width, tab), r in result.items():
        if r["over"] > 0:
            errors.append(f"{width} {tab}: page scrolls sideways by {r['over']}")
        if tab == "trade-targets" and width >= 375:
            if r["signalCut"] is None or r["signalCut"] > 1:
                errors.append(f"{width}: Signal column not visible on first view ({r['signalCut']})")
    return errors


class WideFontTest(unittest.TestCase):
    def test_phone_layouts_fit_in_wide_face(self):
        self.assertEqual(_errors(_run()), [])

    def test_guard_fails_on_old_css(self):
        css = CSS.read_text(encoding="utf-8")
        self.assertTrue(FIX.search(css), "stale mutation anchor")
        self.assertTrue(_errors(_run(FIX.sub("\n", css))), "old CSS was not caught")


if __name__ == "__main__":
    unittest.main()
