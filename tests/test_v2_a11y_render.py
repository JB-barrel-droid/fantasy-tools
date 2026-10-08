"""v2 contrast, skip link and focus containment, rendered (UX pass 2, frame 17).

Builds dist/v2 into a temp copy of the built dist/ and loads every tab
headless in light and dark at 1440 and 390:

  * every visible text node meets WCAG AA contrast against its nearest opaque
    background (4.5:1, or 3:1 for large text), and every publisher symbol
    (● ■ ▲ ◆ ▼ ▽ ✚) meets 3:1 (non-text contrast), so colour plus symbol stays
    readable in dark mode too;
  * "Skip to content" (first in the tab order) moves focus to the visible tab's
    main region without changing the hash route;
  * with player detail or a settings panel open, Tab and Shift+Tab stay inside
    it (both are aria-modal);
  * no page errors.

Discrimination: test_guard_fails_on_broken_builds serves v2.js without the
dark publisher palette and without the focus containment, and v2.css with the
light tint text colour reverted, and requires each to fail.
"""
from __future__ import annotations

import contextlib
import functools
import http.server
import shutil
import socketserver
import sys
import tempfile
import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
sys.path.insert(0, str(ROOT / "pipelines"))
import build_v2_page  # noqa: E402

from tests.test_published_league_settings_render import _chromium_executable  # noqa: E402

V2_JS = ROOT / "app" / "v2" / "v2.js"
V2_CSS = ROOT / "app" / "v2" / "v2.css"
TABS = ("player-values", "trade-targets", "risers-fallers", "compare-trade", "how-values")

CONTRAST = r"""() => {
  const parse = c => { const m = c.match(/rgba?\(([^)]+)\)/); if (!m) return null; const p = m[1].split(',').map(Number);
    return {r: p[0], g: p[1], b: p[2], a: p.length > 3 ? p[3] : 1}; };
  const lum = c => { const f = v => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); };
    return 0.2126 * f(c.r) + 0.7152 * f(c.g) + 0.0722 * f(c.b); };
  const bgOf = el => { for (let n = el; n && n.nodeType === 1; n = n.parentElement) {
    const c = parse(getComputedStyle(n).backgroundColor); if (c && c.a > 0.5) return c; } return {r: 255, g: 255, b: 255, a: 1}; };
  const out = [];
  const seen = new Set();
  const walker = document.createTreeWalker(document.querySelector('.v2-app'), NodeFilter.SHOW_TEXT);
  while (walker.nextNode()) {
    const t = walker.currentNode;
    const text = t.textContent.trim();
    if (!text) continue;
    const el = t.parentElement;
    if (seen.has(el)) continue;
    seen.add(el);
    const box = el.getBoundingClientRect();
    if (!box.width || !box.height || box.bottom < 0) continue;
    const cs = getComputedStyle(el);
    if (cs.visibility === 'hidden' || el.closest('[hidden]') || Number(cs.opacity) === 0) continue;
    const fg = parse(cs.color);
    if (!fg) continue;
    const a = lum(fg), b = lum(bgOf(el));
    const ratio = (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
    const size = parseFloat(cs.fontSize);
    const symbol = /^[●■▲◆▼▽✚•]$/.test(text);
    const need = symbol ? 3 : (size >= 24 || (size >= 18.66 && Number(cs.fontWeight) >= 700)) ? 3 : 4.5;
    if (ratio < need - 0.005) out.push(`${text.slice(0, 24)} ${ratio.toFixed(2)}<${need}`);
  }
  return out;
}"""


def _serve(body, content_type, route, *_):
    route.fulfill(status=200, content_type=content_type, body=body)


@contextlib.contextmanager
def _built_dist():
    if not (DIST / "index.html").exists():
        raise unittest.SkipTest("dist/index.html is not built")
    with tempfile.TemporaryDirectory() as tmp:
        dist = Path(tmp) / "dist"
        shutil.copytree(DIST, dist, ignore=shutil.ignore_patterns("v2"))
        build_v2_page.build(dist)

        class QuietHandler(http.server.SimpleHTTPRequestHandler):
            def log_message(self, format, *args):
                pass
        handler = functools.partial(QuietHandler, directory=str(dist))
        with socketserver.ThreadingTCPServer(("127.0.0.1", 0), handler) as server:
            server.daemon_threads = True
            threading.Thread(target=server.serve_forever, daemon=True).start()
            try:
                yield f"http://127.0.0.1:{server.server_address[1]}/v2/"
            finally:
                server.shutdown()


def trapped(page, opener) -> list[str]:
    """Open a dialog, Tab / Shift+Tab around it, and report focus that left it."""
    page.click(opener)
    page.wait_for_timeout(150)
    box = "#v2Drawer" if opener.startswith("#v2Table") else "#v2Popover"
    escaped = []
    for key in ["Tab"] * 40 + ["Shift+Tab"] * 40:
        page.keyboard.press(key)
        if not page.evaluate(f"() => document.querySelector('{box}').contains(document.activeElement)"):
            escaped.append(key)
            break
    page.keyboard.press("Escape")
    return [f"focus left {box} on {escaped[0]}"] if escaped else []


def run_checks(v2_js=None, v2_css=None, schemes=("light", "dark"), widths=(1440, 390), tabs=TABS) -> list[str]:
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        raise unittest.SkipTest(f"Playwright is not available: {exc}") from exc
    errors = []
    with _built_dist() as base, sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(executable_path=_chromium_executable(playwright))
        except PlaywrightError as exc:
            raise unittest.SkipTest(f"Chromium is not available: {exc}") from exc
        try:
            for scheme in schemes:
                for width in widths:
                    page = browser.new_page(viewport={"width": width, "height": 900}, color_scheme=scheme)
                    page_errors = []
                    page.on("pageerror", lambda e: page_errors.append(str(e)))
                    page.route(lambda u: not u.startswith("http://127.0.0.1"), lambda route: route.abort())
                    if v2_js is not None:
                        page.route("**/v2/v2.js*", functools.partial(_serve, v2_js, "text/javascript"))
                    if v2_css is not None:
                        page.route("**/v2/v2.css*", functools.partial(_serve, v2_css, "text/css"))
                    page.goto(base + "#player-values", wait_until="networkidle")
                    page.wait_for_function("() => window.TradeValueV2 && document.querySelector('#v2Table tbody tr')", timeout=40000)
                    tag = f"[{scheme} {width}px] "
                    for tab in tabs:
                        page.evaluate(f"() => {{ location.hash = '#{tab}'; }}")
                        page.wait_for_timeout(1500 if tab == "risers-fallers" else 400)
                        errors += [f"{tag}{tab}: low contrast {e}" for e in page.evaluate(CONTRAST)]
                    if scheme == "light" and width == 1440:
                        page.evaluate("() => { location.hash = '#compare-trade'; }")
                        page.wait_for_timeout(300)
                        page.keyboard.press("Tab")
                        first = page.evaluate("() => document.activeElement.id")
                        page.keyboard.press("Enter")
                        after = page.evaluate("() => ({id: document.activeElement.id, hash: location.hash})")
                        if first != "v2Skip" or after["id"] != "v2Compare" or not after["hash"].startswith("#compare-trade"):
                            errors.append(f"{tag}skip link: first tab stop {first!r}, then focus {after}")
                        page.evaluate("() => { location.hash = '#player-values'; }")
                        page.wait_for_timeout(400)
                        errors += [tag + e for e in trapped(page, "#v2Table tbody tr")]
                        errors += [tag + e for e in trapped(page, "#v2EditLeague")]
                    if page_errors:
                        errors.append(f"{tag}page errors {page_errors}")
                    page.close()
        finally:
            browser.close()
    return errors


class A11yRenderTest(unittest.TestCase):
    def test_contrast_skip_and_focus(self):
        self.assertEqual(run_checks(), [])

    def test_guard_fails_on_broken_builds(self):
        js = V2_JS.read_text(encoding="utf-8")
        css = V2_CSS.read_text(encoding="utf-8")
        broken = {
            "no dark publisher palette": ({"v2_js": js.replace(
                "const pubColor = publisher => (isDark() && DARK_COLORS[publisher]) ||",
                "const pubColor = publisher =>", 1)}, {"schemes": ("dark",), "widths": (1440,), "tabs": ("how-values",)}),
            "focus escapes dialogs": ({"v2_js": js.replace('      if (event.key === "Tab") {', '      if (false) {', 1)},
                                      {"schemes": ("light",), "widths": (1440,), "tabs": ()}),
            "tint text reverted": ({"v2_css": css.replace("  --v2-action-strong: #066B4C;", "  --v2-action-strong: #087F5B;", 1)},
                                   {"schemes": ("light",), "widths": (1440,), "tabs": ("player-values",)}),
        }
        for name, (kwargs, scope) in broken.items():
            with self.subTest(mutation=name):
                body = next(iter(kwargs.values()))
                self.assertNotIn(body, (js, css), f"mutation anchor for {name!r} is stale")
                self.assertNotEqual(run_checks(**kwargs, **scope), [], f"render checks did not catch: {name}")


if __name__ == "__main__":
    unittest.main()
