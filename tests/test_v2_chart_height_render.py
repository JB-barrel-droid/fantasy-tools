"""v2 Player values: chart height by screen size and the taller / shorter toggle (JEG-477).

Jeremy, 2026-10-19: the chart is taller by default on larger screens (scales with the viewport) plus an
expand / contract toggle; the laptop layout (JEG-470 fold) stays as it was.

Checks the built page headless:
  * 1440 x 900 and 1366 x 768 keep the JEG-470 plot height (42vh, floor 280 px);
  * 1920 x 1080 plots at least 520 px (the laptop rule would give 454) and 2560 x 1440 is taller still;
  * #v2ChartSize toggles the plot taller (aria-pressed, label, drawn SVG follows) and back to the default.

Discrimination: test_guard_fails_on_broken_builds serves v2.css / v2.js without the large-screen rule, without the
toggle's height rule and with the toggle never contracting, and requires failures.
"""
from __future__ import annotations

import functools
import unittest

from playwright.sync_api import Error as PlaywrightError  # noqa: F401  (skip below if missing)

from tests import _render_env  # noqa: E402
from tests.test_published_league_settings_render import _chromium_executable  # noqa: E402
from tests.test_v2_expand_render import V2_CSS, V2_JS, _built_dist, _serve  # noqa: E402

def setUpModule():
    _render_env.ensure_built()


PLOT = "() => { const r = document.getElementById('v2Plot').getBoundingClientRect(); const s = document.querySelector('#v2Chart svg'); return {plot: r.height, svg: s ? s.getBoundingClientRect().height : 0}; }"


def run_checks(overrides=None, viewports=((1440, 900), (1366, 768), (1920, 1080), (2560, 1440))) -> list[str]:
    from playwright.sync_api import sync_playwright
    errors, plot = [], {}
    with _built_dist() as base, sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(args=_render_env.HERMETIC_ARGS, executable_path=_chromium_executable(playwright))
        except PlaywrightError as exc:
            raise _render_env.unavailable(f"Chromium is not available: {exc}") from exc
        try:
            for width, height in viewports:
                tag = f"[{width}x{height}] "
                page = browser.new_page(viewport={"width": width, "height": height})
                page_errors = []
                page.on("pageerror", lambda e: page_errors.append(str(e)))
                page.route(lambda u: not u.startswith("http://127.0.0.1"), lambda route: route.abort())
                for name, (body, ctype) in (overrides or {}).items():
                    page.route(f"**/v2/{name}*", functools.partial(_serve, body, ctype))
                page.goto(base + "#player-values", wait_until="networkidle")
                page.wait_for_function("() => window.TradeValueV2 && window.TradeValueV2.chart()", timeout=60000)
                page.wait_for_timeout(400)
                base_h = page.evaluate(PLOT)
                plot[width] = base_h["plot"]
                if width <= 1440:
                    want = max(280, min(height - 490, 0.42 * height))
                    if abs(base_h["plot"] - want) > 1:
                        errors.append(f"{tag}laptop plot {base_h['plot']:.0f}px, want {want:.0f}px (JEG-470 fold)")
                elif width == 1920 and base_h["plot"] < 520:
                    errors.append(f"{tag}plot only {base_h['plot']:.0f}px, want at least 520px")
                if width == 1440:
                    page.click("#v2ChartSize")
                    page.wait_for_timeout(400)
                    tall = page.evaluate(PLOT)
                    if page.get_attribute("#v2ChartSize", "aria-pressed") != "true":
                        errors.append(f"{tag}toggle not pressed after click")
                    if tall["plot"] < base_h["plot"] + 100:
                        errors.append(f"{tag}toggle did not make the plot taller: {base_h['plot']:.0f} -> {tall['plot']:.0f}")
                    if tall["svg"] < base_h["svg"] + 80:
                        errors.append(f"{tag}chart svg did not redraw taller: {base_h['svg']:.0f} -> {tall['svg']:.0f}")
                    page.click("#v2ChartSize")
                    page.wait_for_timeout(400)
                    back = page.evaluate(PLOT)
                    if abs(back["plot"] - base_h["plot"]) > 1 or page.get_attribute("#v2ChartSize", "aria-pressed") != "false":
                        errors.append(f"{tag}toggle did not contract back: {back['plot']:.0f} vs {base_h['plot']:.0f}")
                if page_errors:
                    errors.append(f"{tag}page errors {page_errors}")
                page.close()
            if 1920 in plot and 2560 in plot and plot[2560] <= plot[1920]:
                errors.append(f"plot does not scale with the viewport: 1920 {plot[1920]:.0f}, 2560 {plot[2560]:.0f}")
        finally:
            browser.close()
    return errors


class ChartHeightRenderTest(unittest.TestCase):
    def test_height_by_screen_and_toggle(self):
        self.assertEqual(run_checks(), [])

    def test_guard_fails_on_broken_builds(self):
        js, css = V2_JS.read_text(encoding="utf-8"), V2_CSS.read_text(encoding="utf-8")
        broken = {
            "no large-screen rule": {"v2.css": css.replace("@media (min-width: 1680px) and (min-height: 960px)", "@media (min-width: 99999px)", 1)},
            "toggle sets no height": {"v2.css": css.replace('#v2Main[data-chart-size="tall"] {', '#v2Main[data-chart-size="never"] {', 1)},
            "toggle never contracts": {"v2.js": js.replace('const tall = $("v2Main").dataset.chartSize !== "tall";', "const tall = true;", 1)},
            "laptop fold changed": {"v2.css": css.replace("--v2-chart-h: clamp(280px, calc(100vh - 490px), 42vh);", "--v2-chart-h: clamp(420px, 60vh, 700px);", 1)},
        }
        sources = {"v2.css": css, "v2.js": js}
        for name, files in broken.items():
            with self.subTest(mutation=name):
                for file, body in files.items():
                    self.assertNotEqual(body, sources[file], f"mutation anchor for {name!r} is stale")
                overrides = {f: (b, "text/css" if f.endswith("css") else "text/javascript") for f, b in files.items()}
                self.assertNotEqual(run_checks(overrides, viewports=((1440, 900), (1920, 1080))), [], f"not caught: {name}")


if __name__ == "__main__":
    unittest.main()
