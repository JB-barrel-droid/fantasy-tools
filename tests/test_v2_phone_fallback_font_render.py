"""No sideways scroll at 390 px in a wide fallback face (JEG-675).

The page asks for Inter. A host without Inter (GitHub's Ubuntu runner, a
visitor's phone) falls back to a wider face, and the phone layout must still
fit. The render suites passed on a machine with Inter installed and failed in CI
on the same code (nav row 6 to 15 px over on every tab, the Player values table
head 33 px over), so this test forces DejaVu Sans, the widest common fallback,
on every element and requires scrollWidth == clientWidth on each tab.

Discrimination: test_guard_fails_on_old_nav_rules and test_guard_fails_on_old_table_head_rule serve v2.css with the 13 px tab
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
TABS = ("#writing/manifesto", "#player-values", "#trade-targets", "#risers-fallers", "#compare-trade", "#find-trade", "#writing/how-values", "#writing/research", "#values-auditing")
WIDE = ("document.addEventListener('DOMContentLoaded',()=>{const s=document.createElement('style');"
        "s.textContent=\"*{font-family:'DejaVu Sans',sans-serif !important}\";document.head.appendChild(s)})")
OLD_RULES = (
    ("padding: 8px 2px; min-width: 44px; flex: 1 1 auto; justify-content: center; font-size: 12px;",
     "padding: 8px 2px; min-width: 44px; flex: 1 1 auto; justify-content: center; font-size: 13px;"),
    # JEG-829: the tab row now also wraps from 360 px in a wide face; the old state has neither the wrap nor the 12 px type.
    ("@media (min-width: 360px) and (max-width: 767px) { .v2-tabs { flex-wrap: wrap; row-gap: 4px; } }", ""),
    ("@media (max-width: 767px) { .v2-table-head { flex-wrap: wrap; } .v2-table-head h2, .v2-table-head .v2-meta { flex: 1 1 100%; min-width: 0; } }", ""),
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


def _overflows(css=None, tabs=TABS, extra_tabs=0) -> dict:
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
        for tab in tabs:
            page = browser.new_page(viewport={"width": 390, "height": 844})
            page.add_init_script(WIDE)
            if css is not None:
                page.route("**/v2/v2.css*", lambda route: route.fulfill(status=200, content_type="text/css", body=css))
            page.goto(base + tab, wait_until="networkidle")
            page.wait_for_timeout(1500)
            for index in range(extra_tabs):
                # Stand-in tabs: the row is held at more tabs than the nav has, so the nav rules can be proven on their own.
                page.evaluate("""(i) => { const nav = document.querySelector('.v2-tabs'); const t = nav.lastElementChild.cloneNode(true);
                  t.dataset.view = 'standin-' + i; t.dataset.short = 'Tab'; t.classList.remove('is-active'); t.removeAttribute('aria-current');
                  nav.appendChild(t); }""", index)
            page.wait_for_timeout(200)
            over = page.evaluate("() => document.documentElement.scrollWidth - document.documentElement.clientWidth")
            if over > 0:
                out[tab] = over
            page.close()
        browser.close()
    return out


class PhoneFallbackFontTest(unittest.TestCase):
    def test_every_tab_fits_390_in_a_wide_fallback_face(self):
        self.assertEqual(_overflows(), {})

    def test_guard_fails_on_old_table_head_rule(self):
        # The Player values table head must not widen the page (33 px over in JEG-675). Only this rule is reverted.
        css = (ROOT / "app" / "v2" / "v2.css").read_text(encoding="utf-8")
        new, old = OLD_RULES[2]
        self.assertEqual(css.count(new), 1, f"stale mutation anchor: {new[:60]!r}")
        self.assertIn("#player-values", _overflows(css.replace(new, old), tabs=("#player-values",)))

    def test_guard_fails_on_old_nav_rules(self):
        # JEG-880: the nav rules (12 px tab type, wrap from 360 px) are proven on their own, on a route whose table head
        # cannot overflow. Seven short tabs now fit even with the old rules, so the row is held at eight with one stand-in
        # tab. Current rules must hold the eight (a wrapped row, no sideways scroll); the old rules must not.
        css = (ROOT / "app" / "v2" / "v2.css").read_text(encoding="utf-8")
        old_css = css
        for new, old in OLD_RULES[:2]:
            self.assertEqual(css.count(new), 1, f"stale mutation anchor: {new[:60]!r}")
            old_css = old_css.replace(new, old)
        route = ("#trade-targets",)
        self.assertEqual(_overflows(tabs=route, extra_tabs=1), {}, "current nav rules must hold eight tabs")
        self.assertIn("#trade-targets", _overflows(old_css, tabs=route, extra_tabs=1), "old nav rules were not caught")
