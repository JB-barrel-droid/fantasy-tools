"""No sideways scroll at 390 px in a wide fallback face (JEG-675).

The page asks for Inter. A host without Inter (GitHub's Ubuntu runner, a
visitor's phone) falls back to a wider face, and the phone layout must still
fit. The render suites passed on a machine with Inter installed and failed in CI
on the same code (nav row 6 to 15 px over on every tab, before the hamburger menu replaced it, the Player values table
head 33 px over), so this test forces DejaVu Sans, the widest common fallback,
on every element and requires scrollWidth == clientWidth on each tab.

Discrimination: test_guard_fails_on_old_nav_rules and test_guard_fails_on_old_table_head_rule serve v2.css with a 600 px hamburger menu
basis and the non-shrinking table title and requires the overflow to be found.
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
# JEG-953: the phone nav is the hamburger menu. These are the table-head rule (JEG-675) and the menu's own sizing rule;
# the menu is proven open, in the wide face, holding one stand-in item beyond the seven.
OLD_RULES = (
    ("flex: 1 0 100%; display: none; flex-direction: column;", "flex: 1 0 600px; display: none; flex-direction: column;"),
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


def _overflows(css=None, tabs=TABS, extra_tabs=0, open_menu=False) -> dict:
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
            page.add_init_script(_render_env.pin_data_week_script())
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
            if open_menu:
                page.click('#v2NavToggle')
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
        new, old = OLD_RULES[1]
        self.assertEqual(css.count(new), 1, f"stale mutation anchor: {new[:60]!r}")
        self.assertIn("#player-values", _overflows(css.replace(new, old), tabs=("#player-values",)))

    def test_guard_fails_on_old_nav_rules(self):
        # JEG-953: the phone nav is the hamburger menu. Open, with one stand-in item beyond the seven, in the wide face,
        # it must stay inside the viewport; a menu sized 600 px wide (the broken state) must be caught. Route chosen
        # so the table head cannot overflow.
        css = (ROOT / "app" / "v2" / "v2.css").read_text(encoding="utf-8")
        new, old = OLD_RULES[0]
        self.assertEqual(css.count(new), 1, f"stale mutation anchor: {new[:60]!r}")
        route = ("#trade-targets",)
        self.assertEqual(_overflows(tabs=route, extra_tabs=1, open_menu=True), {}, "current nav rules must hold the open menu")
        self.assertIn("#trade-targets", _overflows(css.replace(new, old), tabs=route, extra_tabs=1, open_menu=True), "old nav rules were not caught")
        # The button itself must exist at 390 (a hidden hamburger would leave the phone with no nav).
        hidden = css + "\n.v2-nav .v2-nav-toggle { display: none !important; }\n"
        with self.assertRaises(Exception):
            _overflows(hidden, tabs=route, open_menu=True)
