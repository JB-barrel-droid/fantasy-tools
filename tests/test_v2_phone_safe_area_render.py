"""The page must respect the device safe areas (JEG-956).

The v2 page ships with viewport-fit=cover, so the browser draws it under the
notch, the home indicator and the landscape cutouts. The four insets are read
once as custom properties and every edge that can sit under a cutout adds its
own inset to the padding it already has.

The browser cannot fake a safe area, so the test sets the four custom properties
itself (the same values a notched phone reports) and measures what moved: the
nav bar's content, the page's side and bottom padding, the player drawer's four
sides and the fixed toast. Nothing may overflow sideways.

Discrimination: test_guard_fails_on_old_css serves the CSS with the fix removed
and requires the check to fail.
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
# A phone and a tablet: the page's own gutters differ (16 px on a phone, 24 px for
# the nav and 48 px for the page on a tablet), so both are checked.
WIDTHS = (375, 1100)
GUTTER = {375: {"nav": 16, "main": 16}, 1100: {"nav": 24, "main": 48}}
SAFE = {"top": 47, "right": 44, "bottom": 34, "left": 44}

NEW = (".v2-nav { padding-top: var(--v2-safe-top); padding-left: var(--v2-safe-left); "
       "padding-right: var(--v2-safe-right); }")
OLD = ".v2-nav { padding-top: 0px; padding-left: 0px; padding-right: 0px; }"

SAFE_CSS = ":root {\n" + "".join(
    f"  --v2-safe-{name}: {value}px !important;\n" for name, value in SAFE.items()) + "}\n"


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
  const px = el => Math.round(parseFloat(getComputedStyle(el).paddingLeft) || 0);
  const pad = (el, side) => Math.round(parseFloat(getComputedStyle(el)[side]) || 0);
  const nav = document.querySelector('.v2-nav');
  const inner = document.querySelector('.v2-nav-inner');
  const main = document.querySelector('#v2Main');
  const toast = document.querySelector('.v2-status');
  // Where the nav bar's content starts: the bar's own inset plus its gutter.
  const navContentLeft = Math.round(inner.getBoundingClientRect().left + px(inner));
  return {
    navTop: pad(nav, 'paddingTop'),
    navLeft: navContentLeft,
    mainLeft: px(main),
    mainBottom: pad(main, 'paddingBottom'),
    toastBottom: Math.round(parseFloat(getComputedStyle(toast).bottom) || 0),
    over: document.documentElement.scrollWidth - document.documentElement.clientWidth,
  };
}"""

DRAWER = """() => {
  const d = document.querySelector('#v2Drawer');
  if (!d || d.hidden) return null;
  const pad = side => Math.round(parseFloat(getComputedStyle(d)[side]) || 0);
  return {top: pad('paddingTop'), right: pad('paddingRight'), bottom: pad('paddingBottom'), left: pad('paddingLeft')};
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
            page = browser.new_page(viewport={"width": width, "height": 812},
                                    is_mobile=width <= 767, has_touch=True)
            if css is not None:
                page.route("**/v2/v2.css*", lambda route: route.fulfill(status=200, content_type="text/css", body=css))
            page.goto(base + "#player-values", wait_until="networkidle")
            page.wait_for_timeout(1500)
            plain = page.evaluate(PROBE)
            page.add_style_tag(content=SAFE_CSS)
            page.wait_for_timeout(300)
            safe = page.evaluate(PROBE)
            page.evaluate("() => { const row = document.querySelector('#v2Table tbody tr'); if (row) row.click(); }")
            page.wait_for_timeout(700)
            drawer = page.evaluate(DRAWER)
            out[width] = {"plain": plain, "safe": safe, "drawer": drawer}
            page.close()
        browser.close()
    return out


def _errors(result) -> list[str]:
    errors = []
    for width, page in result.items():
        plain, safe = page["plain"], page["safe"]
        if plain["navLeft"] != GUTTER[width]["nav"]:
            errors.append(f"{width}: nav gutter is {plain['navLeft']}px, expected {GUTTER[width]['nav']}px")
        if plain["mainLeft"] != GUTTER[width]["main"]:
            errors.append(f"{width}: page gutter is {plain['mainLeft']}px, expected {GUTTER[width]['main']}px")
        if safe["navTop"] - plain["navTop"] != SAFE["top"]:
            errors.append(f"{width}: nav bar moved {safe['navTop'] - plain['navTop']}px, expected {SAFE['top']}px")
        if safe["navLeft"] - plain["navLeft"] != SAFE["left"]:
            errors.append(f"{width}: nav content moved {safe['navLeft'] - plain['navLeft']}px sideways, expected {SAFE['left']}px")
        if safe["mainLeft"] - plain["mainLeft"] != SAFE["left"]:
            errors.append(f"{width}: page content moved {safe['mainLeft'] - plain['mainLeft']}px sideways, expected {SAFE['left']}px")
        if safe["mainBottom"] - plain["mainBottom"] != SAFE["bottom"]:
            errors.append(f"{width}: page bottom moved {safe['mainBottom'] - plain['mainBottom']}px, expected {SAFE['bottom']}px")
        if safe["toastBottom"] - plain["toastBottom"] != SAFE["bottom"]:
            errors.append(f"{width}: toast moved {safe['toastBottom'] - plain['toastBottom']}px up, expected {SAFE['bottom']}px")
        if safe["over"] > 0:
            errors.append(f"{width}: page scrolls sideways by {safe['over']}px with the insets")
        drawer = page["drawer"]
        if not drawer:
            errors.append(f"{width}: the player drawer did not open")
            continue
        for side, value in (("top", SAFE["top"]), ("right", SAFE["right"]),
                            ("bottom", SAFE["bottom"]), ("left", SAFE["left"])):
            if drawer[side] < value:
                errors.append(f"{width}: drawer {side} padding {drawer[side]}px, under the {value}px inset")
    return errors


LANDSCAPE_NEW = ("@media (max-width: 932px) and (max-height: 500px) {\n"
                 "  .v2-topnote-detail { padding-left: calc(16px + var(--v2-safe-left));")
LANDSCAPE_OLD = ("@media (max-width: 932px) and (max-height: 500px) {\n"
                 "  .v2-topnote-retired { padding-left: calc(16px + var(--v2-safe-left));")


def _landscape_note_gutter(css=None) -> int:
    """The season note's detail panel on a landscape phone (812 x 375) keeps the 16 px phone gutter."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise _render_env.unavailable("playwright is not installed")
    exe = _render_env.chromium_executable()
    if exe is None and _render_env.required() is False:
        raise _render_env.unavailable("no browser")
    with _served() as base, sync_playwright() as p:
        browser = p.chromium.launch(executable_path=exe, args=_render_env.HERMETIC_ARGS)
        page = browser.new_page(viewport={"width": 812, "height": 375}, is_mobile=True, has_touch=True)
        if css is not None:
            page.route("**/v2/v2.css*", lambda route: route.fulfill(status=200, content_type="text/css", body=css))
        page.goto(base + "#player-values", wait_until="networkidle")
        gutter = page.evaluate("() => Math.round(parseFloat(getComputedStyle("
                               "document.querySelector('.v2-topnote-detail')).paddingLeft) || 0)")
        browser.close()
    return gutter


class SafeAreaTest(unittest.TestCase):
    def test_landscape_phone_keeps_note_gutter(self):
        self.assertEqual(_landscape_note_gutter(), 16)

    def test_landscape_guard_fails_on_old_css(self):
        css = CSS.read_text(encoding="utf-8")
        self.assertIn(LANDSCAPE_NEW, css, "stale mutation anchor")
        self.assertNotEqual(_landscape_note_gutter(css.replace(LANDSCAPE_NEW, LANDSCAPE_OLD)), 16)

    def test_safe_area_insets_are_respected(self):
        self.assertEqual(_errors(_run()), [])

    def test_guard_fails_on_old_css(self):
        css = CSS.read_text(encoding="utf-8")
        self.assertIn(NEW, css, "stale mutation anchor")
        self.assertTrue(_errors(_run(css.replace(NEW, OLD))), "old CSS was not caught")


if __name__ == "__main__":
    unittest.main()
