"""v2 across devices: touch targets, tablet navigation, dark-mode contrast.

Builds dist/v2 into a temp copy of the built dist/ and loads Player values
headless at 390 (phone), 820 (tablet) and 1440 (desktop), then checks:

  * frame 17 "every action has a 44 × 44 px hit area": each visible button,
    link and select is at least 43 px wide and a tap 21 px above and below its
    centre still lands on it (or on the label that wraps it);
  * every tab is fully on screen at every width (tablet included);
  * no horizontal overflow;
  * dark mode: a hovered table row keeps a dark background under light text,
    and the status toast's text contrasts with its background.

Discrimination: test_guard_fails_on_broken_builds serves v2.css without the
tablet navigation rule, with 40 px chart zoom buttons, and with the
light hover colour back in dark mode, and requires the checks to fail on each.
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
from tests import _render_env  # noqa: E402


def setUpModule():
    # Build app/ and dist/ from the committed fixtures first, so the
    # test never reads a stale committed build (GAP-APP-ASSETS-LAG).
    _render_env.ensure_built()


V2_CSS = ROOT / "app" / "v2" / "v2.css"
TABLET_NAV = "@media (min-width: 768px) and (max-width: 1023px) {\n  .v2-nav-inner"

TARGETS = """() => { const bad = [];
  document.querySelectorAll('.v2-app button, .v2-app a, .v2-app select').forEach(n => {
    const b = n.getBoundingClientRect();
    // Only controls fully on screen can be probed.
    if (!b.width || n.closest('[hidden]') || b.top - 1 < 0 || b.bottom + 1 > innerHeight) return;
    const cx = b.left + b.width / 2, cy = b.top + b.height / 2;
    const owner = n.closest('label') || n;
    const ok = [-21, 21].every(dy => { const e = document.elementFromPoint(cx, cy + dy); return e && (owner === e || owner.contains(e)); });
    if (!ok || b.width < 43) bad.push(`${n.tagName} "${(n.textContent || '').trim().slice(0, 24)}" ${Math.round(b.width)}x${Math.round(b.height)}`);
  });
  return {bad, tabs: [...document.querySelectorAll('.v2-tab')].filter(t => t.getBoundingClientRect().right > innerWidth + 0.5)
    .map(t => t.textContent), overflow: document.documentElement.scrollWidth - innerWidth};
}"""

LUM = """(color) => { const m = color.match(/[\\d.]+/g).map(Number);
  const c = m.slice(0, 3).map(v => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; });
  return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]; }"""


def _serve(body, route, *_):
    route.fulfill(status=200, content_type="text/css", body=body)


@contextlib.contextmanager
def _built_dist():
    if not (DIST / "index.html").exists():
        raise _render_env.unavailable("dist/index.html is not built")
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
                yield f"http://127.0.0.1:{server.server_address[1]}/v2/#player-values"
            finally:
                server.shutdown()


def contrast(l1, l2):
    hi, lo = max(l1, l2), min(l1, l2)
    return (hi + 0.05) / (lo + 0.05)


def run_checks(v2_css=None) -> list[str]:
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        raise _render_env.unavailable(f"Playwright is not available: {exc}") from exc
    errors = []
    with _built_dist() as url, sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(args=_render_env.HERMETIC_ARGS, executable_path=_chromium_executable(playwright))
        except PlaywrightError as exc:
            raise _render_env.unavailable(f"Chromium is not available: {exc}") from exc
        try:
            for width, height, scheme in ((390, 844, "light"), (820, 1180, "light"), (1440, 900, "light"), (1440, 900, "dark")):
                page = browser.new_page(viewport={"width": width, "height": height}, color_scheme=scheme)
                page_errors = []
                page.on("pageerror", lambda e: page_errors.append(str(e)))
                page.route(lambda u: not u.startswith("http://127.0.0.1"), lambda route: route.abort())
                if v2_css is not None:
                    page.route("**/v2/v2.css*", functools.partial(_serve, v2_css))
                page.goto(url, wait_until="networkidle")
                page.wait_for_function("() => window.TradeValueV2 && document.querySelector('#v2Table tbody tr')", timeout=30000)
                tag = f"{width}px {scheme}"
                if scheme == "light":
                    r = page.evaluate(TARGETS)
                    errors += [f"{tag}: hit area under 44 px: {b}" for b in r["bad"]]
                    errors += [f"{tag}: tab off screen: {t}" for t in r["tabs"]]
                    if r["overflow"] > 0:
                        errors.append(f"{tag}: horizontal overflow {r['overflow']}px")
                else:
                    page.hover("#v2Table tbody tr:nth-child(3) td.player")
                    colors = page.evaluate("""() => { const td = document.querySelector('#v2Table tbody tr:nth-child(3) td.player');
                      const s = getComputedStyle(td); const st = document.getElementById('v2Status'); st.hidden = false; st.textContent = 'x';
                      const ss = getComputedStyle(st); return [s.backgroundColor, s.color, ss.backgroundColor, ss.color]; }""")
                    lums = [page.evaluate(f"({LUM})({c!r})".replace("({c!r})", f"('{c}')")) for c in colors]
                    if contrast(lums[0], lums[1]) < 4.5:
                        errors.append(f"{tag}: hovered row text contrast {contrast(lums[0], lums[1]):.1f} ({colors[0]} / {colors[1]})")
                    if contrast(lums[2], lums[3]) < 4.5:
                        errors.append(f"{tag}: status toast contrast {contrast(lums[2], lums[3]):.1f} ({colors[2]} / {colors[3]})")
                if page_errors:
                    errors.append(f"{tag}: page errors {page_errors}")
                page.close()
        finally:
            browser.close()
    return errors


class UxRenderTest(unittest.TestCase):
    def test_targets_tabs_and_dark_mode(self):
        self.assertEqual(run_checks(), [])

    def test_guard_fails_on_broken_builds(self):
        css = V2_CSS.read_text(encoding="utf-8")
        broken = {
            "no tablet navigation": css.replace(TABLET_NAV, "@media (min-width: 9999px) {\n  .v2-nav-inner", 1),
            # JEG-475 removed the rank-window buttons; the zoom buttons inside the plot carry the 44 px rule now.
            "40 px zoom buttons": css.replace(".v2-zoom button { width: 44px; height: 44px;", ".v2-zoom button { width: 40px; height: 40px;", 1),
            "light hover in dark mode": css + "\n.v2-table tbody tr:hover td { background: #F7FAF9; }\n",
        }
        for name, body in broken.items():
            with self.subTest(mutation=name):
                self.assertNotEqual(body, css, f"mutation anchor for {name!r} is stale")
                self.assertNotEqual(run_checks(body), [], f"render checks did not catch: {name}")


if __name__ == "__main__":
    unittest.main()
