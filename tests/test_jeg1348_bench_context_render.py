"""Render the prepared JEG-1348 integration without editing the owned v2.js.

The checked-in patch is applied to temporary source copies, then served as
overrides. This is evidence for the pending integration, not a claim it is live.
"""
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from tests import _render_env
from tests._dist_server import serve

ROOT = Path(__file__).resolve().parents[1]
PATCH = ROOT / "docs/claude-log/2026-11-03-jeg1348-integration.patch"


def integration_overrides(integrated=True):
    with tempfile.TemporaryDirectory() as temporary:
        tmp = Path(temporary)
        for name in ("app/v2/v2.js", "pipelines/build_v2_page.py"):
            dest = tmp / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes((ROOT / name).read_bytes())
        check = subprocess.run(["git", "apply", "--check", str(PATCH)], cwd=tmp, capture_output=True)
        if check.returncode:
            # After the coordinator integrates, reverse only in temporary
            # copies so the same regression and negative control still work.
            subprocess.run(["git", "apply", "--reverse", str(PATCH)], cwd=tmp, check=True, capture_output=True)
        if integrated:
            subprocess.run(["git", "apply", str(PATCH)], cwd=tmp, check=True, capture_output=True)
        # Run the patched builder with the real root: both script registration
        # and the v2 call site come from the exact handoff patch.
        namespace = {"__file__": str(ROOT / "pipelines/build_v2_page.py"), "__name__": "jeg1348_builder"}
        exec(compile((tmp / "pipelines/build_v2_page.py").read_text(), "jeg1348_builder", "exec"), namespace)
        output = tmp / "dist"
        namespace["build"](dist=output)
        return {"index.html": (output / "index.html").read_bytes(),
                "v2/v2.js": (tmp / "app/v2/v2.js").read_bytes(),
                **({f"v2/{name}": (output / "v2" / name).read_bytes()
                    for name in ("bench-breakout-evidence.js", "bench-context.js")} if integrated else {})}


def setUpModule():
    _render_env.ensure_built()


class BenchContextRenderTest(unittest.TestCase):
    def run_browser(self, callback, overrides=None, width=1280):
        from playwright.sync_api import sync_playwright
        overrides = integration_overrides() if overrides is None else overrides
        with serve(overrides=overrides) as base, sync_playwright() as pw:
            browser = pw.chromium.launch(executable_path=_render_env.chromium_executable(pw),
                                         args=_render_env.HERMETIC_ARGS)
            try:
                page = browser.new_page(viewport={"width": width, "height": 900})
                if "index.html" in overrides:
                    # _dist_server's overrides normally serve JS/JSON only.
                    page.route("**/index.html", lambda route: route.fulfill(
                        body=overrides["index.html"], content_type="text/html"))
                page.add_init_script(_render_env.pin_data_week_script())
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.goto(base + "/index.html")
                page.wait_for_function("() => window.TradeValueCurveControls?.isReady()", timeout=120000)
                callback(page)
                self.assertEqual(errors, [])
            finally:
                browser.close()

    def open_weights(self, page, settings):
        page.keyboard.press("Escape")
        page.evaluate("settings => window.TradeValueCurveControls.setLineupSettings(settings, false)", settings)
        _render_env.open_phone_context(page)
        page.click("#v2ContextMore")
        page.click("#v2Weights")

    def test_prepared_panel_uses_measured_window_and_fixed_counted_history(self):
        def check(page):
            historical = None
            for week, weeks, byes in ((8, 9, 18), (14, 3, 0), (17, 0, 0), (18, 0, 0)):
                self.open_weights(page, {"contentWeek": week, "optimizeFor": "season"})
                text = page.locator("[data-bench-context]").inner_text()
                self.assertIn(f"Measured: {weeks} weeks left", text)
                self.assertIn(f"{byes} of 32 teams have a bye in this window", text)
                if week == 8:
                    self.assertIn("weeks 9–17", text)
                if weeks == 0:
                    self.assertNotIn("(weeks", text)
                page.locator("[data-bench-historical] summary").click()
                current = page.locator("[data-bench-historical]").inner_text()
                self.assertIn("Historical breakout odds", current)
                self.assertIn("2015–2025 · 12-team cohorts", current)
                self.assertIn("0.0% (0/132)", current)
                self.assertIn("27.3% (36/132)", current)
                self.assertIn("not a forecast", current)
                self.assertEqual(page.locator("[data-bench-historical] tbody tr").count(), 4)
                historical = current if historical is None else historical
                self.assertEqual(current, historical, "fixed historical evidence must not decay with content week")
            self.open_weights(page, {"contentWeek": 8, "optimizeFor": "playoffs", "playoffWeeks": [15, 16], "benchShareOverride": .1})
            self.assertIn("Measured: 2 weeks left (weeks 15–16) · 0 of 32", page.locator("[data-bench-context]").inner_text())
            self.assertIn("your override", page.locator("[data-bench-readout]").inner_text())
            page.locator("[data-bench-override-reset]").click()
            self.assertIn("Measured: 2 weeks left", page.locator("[data-bench-context]").inner_text())
        self.run_browser(check)

    def test_phone_expanded_evidence_fits_panel(self):
        def check(page):
            self.open_weights(page, {"contentWeek": 8, "optimizeFor": "season"})
            self.assertGreaterEqual(page.locator("[data-bench-historical] summary").bounding_box()["height"], 44)
            page.locator("[data-bench-historical] summary").click()
            bounds = page.locator("[data-bench-historical]").evaluate("el => ({width:el.clientWidth, scroll:el.scrollWidth})")
            self.assertLessEqual(bounds["scroll"], bounds["width"] + 1, bounds)
            self.assertTrue(page.locator("[data-bench-context]").is_visible())
        self.run_browser(check, width=390)

    def test_without_integration_the_new_readout_is_absent(self):
        # Negative control: source page without the held patch must not pass
        # the positive panel-presence assertion.
        def check(page):
            self.open_weights(page, {"contentWeek": 8, "optimizeFor": "season"})
            with self.assertRaises(AssertionError):
                self.assertEqual(page.locator("[data-bench-context]").count(), 1)
        self.run_browser(check, overrides=integration_overrides(integrated=False))
