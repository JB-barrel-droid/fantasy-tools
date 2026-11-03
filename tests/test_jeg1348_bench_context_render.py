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
CASES = json.loads((ROOT / "tests/fixtures/jeg1348_bench_context.json").read_text())
READY = "() => window.TradeValueCurveControls?.isReady() && window.TradeValueV2?.view()"


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
    def assert_historical_matrix(self, page):
        # Independent oracle: read every rendered cell against the research
        # matrix, rather than the display asset or the formatter under test.
        matrix = json.loads((ROOT / CASES["historical_source"]).read_text())
        evidence = {row["id"]: row for row in matrix["rows"] if row["id"].startswith("O3.")}
        table = page.locator("[data-bench-historical] table")
        self.assertEqual(table.locator("thead th").all_text_contents(), ["Position", "Backup #1", "Backup #2", "Backup #3"])
        self.assertEqual(table.locator("th[scope=col]").count(), 4)
        self.assertEqual(table.locator("th[scope=row]").count(), 4)
        for i, position in enumerate(("QB", "RB", "WR", "TE")):
            row = table.locator("tbody tr").nth(i)
            self.assertEqual(row.locator("th").inner_text(), position)
            expected = []
            for depth in (1, 2, 3):
                source = evidence[f"O3.{position}.d{depth}"]
                expected.append(f"{source['values']['rate'] * 100:.1f}% ({source['values']['breakouts']}/{source['n']})")
            self.assertEqual(row.locator("td").all_text_contents(), expected)

    def test_fixture_windows_and_all_historical_cells(self):
        def check(page):
            for case in CASES["cases"]:
                with self.subTest(case=case["name"]):
                    self.open_weights(page, case["settings"])
                    readout = page.evaluate("() => TradeValueCurveControls.getBenchShareReadout()")
                    self.assertEqual(readout["window"], case["window"])
                    self.assertEqual((readout["weeksLeft"], readout["byesLeft"]), (case["weeks"], case["byes"]))
                    text = page.locator("[data-bench-context]").inner_text()
                    noun = "week" if case["weeks"] == 1 else "weeks"
                    self.assertIn(f"Measured: {case['weeks']} {noun} left", text)
                    self.assertIn(f"{case['byes']} of 32 teams have a bye in this window", text)
                    page.locator("[data-bench-historical] summary").click()
                    self.assert_historical_matrix(page)
            # The historical table must keep the original cohort even for a
            # different current scoring and team count.
            page.keyboard.press("Escape")
            page.evaluate("() => { TradeValueCurveControls.setTeams(8); TradeValueCurveControls.setScoring('standard'); }")
            self.open_weights(page, CASES["cases"][0]["settings"])
            page.locator("[data-bench-historical] summary").click()
            self.assertIn("12-team cohorts", page.locator("[data-bench-historical] caption").inner_text())
            self.assertIn("Half-PPR", page.locator("[data-bench-historical]").inner_text())
            self.assert_historical_matrix(page)
        self.run_browser(check)

    def test_visible_objective_control_and_reload_keep_context(self):
        def check(page):
            page.evaluate("settings => TradeValueCurveControls.setLineupSettings(settings, false)", CASES["cases"][0]["settings"])
            page.click("#v2EditLeague")
            page.click('#v2Popover [aria-label="Optimize for"] [data-value="regular"]')
            page.wait_for_function("() => TradeValueCurveControls.getOptimizeFor() === 'regular'")
            page.click('[data-done="league"]')
            page.click("#v2ContextMore")
            page.click("#v2Weights")
            expected = "Measured: 6 weeks left (weeks 9–14) · 18 of 32 teams have a bye in this window"
            self.assertEqual(page.locator("[data-bench-context]").inner_text(), expected)
            page.reload()
            page.wait_for_function(READY)
            page.click("#v2ContextMore")
            page.click("#v2Weights")
            self.assertEqual(page.locator("[data-bench-context]").inner_text(), expected)
            summary = page.locator("[data-bench-historical] summary")
            summary.focus()
            summary.press("Enter")
            self.assertTrue(page.locator("[data-bench-historical]").evaluate("el => el.open"))
            self.assertTrue(summary.evaluate("el => el === document.activeElement"))
            self.assert_historical_matrix(page)
            summary.press("Space")
            self.assertFalse(page.locator("[data-bench-historical]").evaluate("el => el.open"))
            summary.press("Escape")
            self.assertFalse(page.locator("[data-bench-context]").is_visible())
            self.assertTrue(page.locator("#v2ContextMore").evaluate("el => el === document.activeElement"))
        self.run_browser(check)

    def test_missing_historical_asset_keeps_measured_context(self):
        overrides = integration_overrides()
        overrides["v2/bench-breakout-evidence.js"] = b"window.TradeValueBenchEvidence = null;"
        def check(page):
            self.open_weights(page, CASES["cases"][0]["settings"])
            self.assertIn("Measured: 9 weeks left", page.locator("[data-bench-context]").inner_text())
            page.locator("[data-bench-historical] summary").click()
            self.assertIn("Historical breakout odds unavailable", page.locator("[data-bench-historical]").inner_text())
            self.assertEqual(page.locator("[data-bench-historical] table").count(), 0)
        self.run_browser(check, overrides=overrides)

    def test_missing_bye_map_stays_unavailable_instead_of_zero(self):
        overrides = integration_overrides()
        config = json.loads((ROOT / CASES["bye_source"]).read_text())
        config.pop("byes")
        overrides["assets/lineup-parameters.json"] = json.dumps(config).encode()
        def check(page):
            self.open_weights(page, CASES["cases"][0]["settings"])
            text = page.locator("[data-bench-context]").inner_text()
            self.assertIn("9 weeks left", text)
            self.assertIn("byes left unavailable", text)
            self.assertNotIn("0 of", text)
            page.locator("[data-bench-historical] summary").click()
            self.assert_historical_matrix(page)
        self.run_browser(check, overrides=overrides)

    def run_browser(self, callback, overrides=None, width=1280, directory=None):
        from playwright.sync_api import sync_playwright
        overrides = integration_overrides() if overrides is None else overrides
        with serve(directory=directory or ROOT / "dist", overrides=overrides) as base, sync_playwright() as pw:
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
                page.wait_for_function(READY, timeout=120000)
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

    def test_exported_review_is_self_contained_and_sources_stay_unchanged(self):
        from tools.preview_bench_context import export_review
        protected = [ROOT / path for path in ("app/v2/v2.js", "pipelines/build_v2_page.py")]
        before = [path.read_bytes() for path in protected]
        with tempfile.TemporaryDirectory() as temporary:
            destination = export_review(Path(temporary) / "review")
            manifest = json.loads((destination / "jeg1348-review.json").read_text())
            self.assertIn("held integration", manifest["purpose"])
            def check(page):
                self.open_weights(page, CASES["cases"][0]["settings"])
                page.locator("[data-bench-historical] summary").click()
                self.assert_historical_matrix(page)
                self.assertIn("9 weeks left", page.locator("[data-bench-context]").inner_text())
                bounds = page.locator("[data-bench-historical]").evaluate("el => ({width:el.clientWidth, scroll:el.scrollWidth, left:el.getBoundingClientRect().left, right:el.getBoundingClientRect().right, viewport:innerWidth})")
                self.assertLessEqual(bounds["scroll"], bounds["width"] + 1, bounds)
                self.assertGreaterEqual(bounds["left"], 0, bounds)
                self.assertLessEqual(bounds["right"], bounds["viewport"] + 1, bounds)
            self.run_browser(check, overrides={}, width=320, directory=destination)
        self.assertEqual([path.read_bytes() for path in protected], before)

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
