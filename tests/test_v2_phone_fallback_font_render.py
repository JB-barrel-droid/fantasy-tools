"""No sideways scroll at 390 px in a wide fallback face (JEG-675).

The page asks for Inter. A host without Inter (GitHub's Ubuntu runner, a
visitor's phone) falls back to a wider face, and the phone layout must still
fit. The render suites passed on a machine with Inter installed and failed in CI
on the same code (nav row 6 to 15 px over on every tab, the Player values table
head 33 px over), so this test forces DejaVu Sans, the widest common fallback,
on every element and requires scrollWidth == clientWidth on each tab.

Discrimination: test_guard_fails_on_old_css serves v2.css with the 13 px tab
row and the non-shrinking table title and requires the overflow to be found.
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
TABS = ("#manifesto", "#player-values", "#trade-targets", "#risers-fallers", "#compare-trade", "#how-values", "#research")
WIDE = ("document.addEventListener('DOMContentLoaded',()=>{const s=document.createElement('style');"
        "s.textContent=\"*{font-family:'DejaVu Sans',sans-serif !important}\";document.head.appendChild(s)})")
OLD_RULES = (
    ("padding: 8px 2px; min-width: 44px; flex: 1 1 auto; justify-content: center; font-size: 12px;",
     "padding: 8px 2px; min-width: 44px; flex: 1 1 auto; justify-content: center; font-size: 13px;"),
    ("@media (max-width: 767px) { .v2-table-head h2 { flex: 0 1 auto; min-width: 0; } }", ""),
)


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


def _overflows(css=None) -> dict:
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
        # Without DejaVu Sans the forced face falls back to the host default and nothing
        # is wide, so both tests would be vacuous (a Mac has no DejaVu: JEG-718).
        has_face = probe.evaluate("""() => { const c = document.createElement('canvas').getContext('2d'); const t = 'Wide fallback face WMwmi 0123';
            c.font = "40px monospace"; const a = c.measureText(t).width; c.font = "40px 'DejaVu Sans', monospace"; return c.measureText(t).width !== a; }""")
        probe.close()
        if not has_face:
            browser.close()
            raise _render_env.unavailable("DejaVu Sans is not installed, so the wide fallback face cannot be forced")
        for tab in TABS:
            page = browser.new_page(viewport={"width": 390, "height": 844})
            page.add_init_script(WIDE)
            if css is not None:
                page.route("**/v2/v2.css*", lambda route: route.fulfill(status=200, content_type="text/css", body=css))
            page.goto(base + tab, wait_until="networkidle")
            page.wait_for_timeout(1500)
            over = page.evaluate("() => document.documentElement.scrollWidth - document.documentElement.clientWidth")
            if over > 0:
                out[tab] = over
            page.close()
        browser.close()
    return out


class PhoneFallbackFontTest(unittest.TestCase):
    def test_every_tab_fits_390_in_a_wide_fallback_face(self):
        self.assertEqual(_overflows(), {})

    def test_guard_fails_on_old_css(self):
        css = (ROOT / "app" / "v2" / "v2.css").read_text(encoding="utf-8")
        for new, old in OLD_RULES:
            self.assertEqual(css.count(new), 1, f"stale mutation anchor: {new[:60]!r}")
            css = css.replace(new, old)
        found = _overflows(css)
        self.assertIn("#manifesto", found)
        self.assertIn("#player-values", found)


if __name__ == "__main__":
    unittest.main()
