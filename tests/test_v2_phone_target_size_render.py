"""Chart legend toggles and the rank-brush fill must clear 24 x 24 CSS px (JEG-903).

WCAG 2.5.8 Target Size (Minimum). The live a11y audit (2026-10-22) measured the
legend toggles at 22 px and the rank-brush fill at 16 px. The Targets card value
spans are 44 x 44 on touch (JEG-947) and must stay that way.

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
WIDTHS = (375, 1440)

NEW = """.v2-legend .v2-legend-item { min-height: 24px; }
/* The track band grows with the fill, so the two stay the same height in the 44 px track. */
.v2-brush-track::before { top: 10px; height: 24px; }
.v2-brush-fill { top: 10px; height: 24px; }"""
OLD = """.v2-legend .v2-legend-item { min-height: 22px; }
.v2-brush-track::before { top: 14px; height: 16px; }
.v2-brush-fill { top: 14px; height: 16px; }"""


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
  const legend = [...document.querySelectorAll('#v2Legend .v2-legend-item')]
    .map(el => Math.round(el.getBoundingClientRect().height));
  const fill = document.getElementById('v2BrushFill').getBoundingClientRect();
  return {legend, fillW: Math.round(fill.width), fillH: Math.round(fill.height)};
}"""

CARDS = """() => [...document.querySelectorAll('#v2TCards .val.has-math')]
  .map(el => el.getBoundingClientRect())
  .filter(b => b.width > 0 && b.height > 0)
  .map(b => Math.round(b.height))"""


def _run(css=None) -> dict:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise _render_env.unavailable("playwright is not installed")
    exe = _render_env.chromium_executable()
    if exe is None and _render_env.required() is False:
        raise _render_env.unavailable("no browser")
    out = {"legend": {}, "cards": {}}
    with _served() as base, sync_playwright() as p:
        browser = p.chromium.launch(executable_path=exe, args=_render_env.HERMETIC_ARGS)
        for width in WIDTHS:
            page = browser.new_page(viewport={"width": width, "height": 812})
            if css is not None:
                page.route("**/v2/v2.css*", lambda route: route.fulfill(status=200, content_type="text/css", body=css))
            page.goto(base + "#player-values", wait_until="networkidle")
            page.wait_for_timeout(1500)
            out["legend"][width] = page.evaluate(PROBE)
            page.goto(base + "#trade-targets", wait_until="networkidle")
            page.wait_for_timeout(1500)
            out["cards"][width] = page.evaluate(CARDS)
            page.close()
        browser.close()
    return out


def _errors(result) -> list[str]:
    errors = []
    for width, probe in result["legend"].items():
        if not probe["legend"]:
            errors.append(f"{width}: no legend items rendered")
        for height in probe["legend"]:
            if height < 24:
                errors.append(f"{width}: legend item {height}px tall, under the 24px minimum")
        if probe["fillH"] < 24 or probe["fillW"] < 24:
            errors.append(f"{width}: rank-brush fill {probe['fillW']}x{probe['fillH']}px, under the 24px minimum")
    for width, heights in result["cards"].items():
        # The target cards are the phone layout; on a wide screen the same values sit in the table.
        for height in heights:
            if height < 24:
                errors.append(f"{width}: card value span {height}px tall, under the 24px minimum")
    return errors


class TargetSizeTest(unittest.TestCase):
    def test_targets_clear_24px(self):
        self.assertEqual(_errors(_run()), [])

    def test_guard_fails_on_old_css(self):
        css = CSS.read_text(encoding="utf-8")
        self.assertIn(NEW, css, "stale mutation anchor")
        self.assertTrue(_errors(_run(css.replace(NEW, OLD))), "old CSS was not caught")


if __name__ == "__main__":
    unittest.main()
