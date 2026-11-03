"""JEG-1395: explanation arithmetic agrees with the unchanged chart engine."""
from __future__ import annotations

import builtins
import contextlib
import json
import os
import re
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from pipelines import build_values_explainer as builder
from tests import _render_env

ROOT = Path(__file__).resolve().parents[1]


class ExplainerExportTest(unittest.TestCase):
    def test_raw_surplus_and_weighted_groups_are_distinct_exports(self):
        result = builder.trim_pipeline({"sources": {"espn": {
            "surplusTotal": 870.21, "totalVorp": 544.74,
            "vorpFactor": 2352 / 870.21,
        }}})["sources"]["espn"]
        self.assertEqual(result["surplusTotal"], 870.21)
        self.assertEqual(result["totalVorp"], 544.74)
        self.assertAlmostEqual(result["vorpFactor"] * result["surplusTotal"], 2352)


class ExplainerArithmeticRenderTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            from playwright.sync_api import Error as PlaywrightError, sync_playwright
        except ImportError as exc:
            raise _render_env.unavailable(f"Playwright is not available: {exc}") from exc

        resources = contextlib.ExitStack()
        cls.addClassCleanup(resources.close)
        try:
            cls.pw = resources.enter_context(sync_playwright())
            cls.browser = cls.pw.chromium.launch(args=_render_env.HERMETIC_ARGS,
                                                executable_path=_render_env.chromium_executable())
        except (PlaywrightError, OSError) as exc:
            raise _render_env.unavailable(f"Chromium is not available: {exc}") from exc
        resources.callback(cls.browser.close)
        # Probe dependencies before building. Build/bundle errors must remain
        # errors even when rendering is optional, with both resources cleaned up.
        _render_env.ensure_built()
        cls.html = (ROOT / "dist/value-logic/index.html").read_text()
        cls.data = json.loads(re.search(r'const D = (.*);\n\(function', cls.html).group(1))

    def page(self, html=None):
        page = self.browser.new_page()
        page.route("**/*", lambda route: route.abort())
        page.set_content(html or self.html, wait_until="domcontentloaded")
        self.addCleanup(page.close)
        return page

    def test_every_rendered_player_and_version_matches_engine(self):
        page = self.page()
        result = builder.check_rendered_page(page, self.data)
        self.assertEqual(result["off"], {})
        self.assertEqual(result["checked"], len(self.data["players"]) * 3)
        self.assertGreater(result["checked"], 100)
        # Regression sentinel: the reported example must use the chart inputs.
        walker = next(p for p in self.data["players"].values() if p["n"] == "Kenneth Walker III")
        self.assertEqual(set(walker["sources"]["blended"]),
                         set(self.data["compositeByVersion"]["blended"]["series"]))
        self.assertNotIn("espn", walker["sources"]["blended"])

    def test_membership_table_uses_each_versions_engine_series(self):
        page = self.page()
        page.locator('#srcNav [data-k="ddf"]').click()
        for version, info in self.data["compositeByVersion"].items():
            cell = page.locator(f'[data-membership="{version}"]')
            keys = cell.locator('[data-source]').evaluate_all("els => els.map(el => el.dataset.source)")
            self.assertEqual(keys, info["series"])

    def test_source_divisions_use_raw_surplus_and_label_weighted_total(self):
        page = self.page()
        for source in ("fantasycalc", "espn"):
            page.locator(f'#srcNav [data-k="{source}"]').click()
            s = self.data["vp"]["sources"][source]
            formula = page.locator('[data-vorp-division]').inner_text()
            if len(self.data["vp"].get("allocationMix") or []) > 1:
                # JEG-1335 averages factors, not reciprocals of averaged totals.
                self.assertIn("weighted mean(2,352 ÷ raw positive surplus per allocation)", formula)
                self.assertIn("dividing by the averaged surplus above would give a different number",
                              page.locator('#srcBody').inner_text())
            else:
                denominator = float(formula.split("÷")[1].replace(",", ""))
                self.assertAlmostEqual(denominator, s["surplusTotal"], delta=0.51)
            self.assertIn("expected-start-weighted group total", page.locator('#srcBody').inner_text())
            self.assertNotEqual(s["surplusTotal"], s["totalVorp"])

    def test_single_allocation_displays_its_raw_surplus_divisor(self):
        data = json.loads(json.dumps(self.data))
        data["vp"]["allocationMix"] = None
        blob = json.dumps(data).replace("</", "<\\/")
        html = (ROOT / "app/values-explainer/template.html").read_text().replace("/*__VALUES_DATA__*/null", blob)
        page = self.page(html)
        for source in ("fantasycalc", "espn"):
            page.locator(f'#srcNav [data-k="{source}"]').click()
            formula = page.locator('[data-vorp-division]').inner_text()
            denominator = float(formula.split("÷")[1].replace(",", ""))
            self.assertAlmostEqual(denominator, data["vp"]["sources"][source]["surplusTotal"], delta=0.51)

    def test_build_check_reads_the_displayed_divisor(self):
        page = self.page()
        page.evaluate("""() => { const host = document.getElementById('traceBody');
          const descriptor = Object.getOwnPropertyDescriptor(Element.prototype, 'innerHTML');
          Object.defineProperty(host, 'innerHTML', {set(html) {
            descriptor.set.call(this, html);
            this.querySelector('[data-ddf-version="blended"] [data-aggregate-divisor]').textContent = '÷ 7 =';
          }, get() { return descriptor.get.call(this); }}); }""")
        self.assertTrue(builder.check_rendered_page(page, self.data)["off"])

    def test_build_check_rejects_the_original_seven_source_trace(self):
        page = self.page()
        # Reproduce the old UI bug: all included sources enter each player's mean.
        page.evaluate("""() => { for (const [pk, p] of Object.entries(D.players))
          p.sources.blended = D.vp.included.filter(k => D.src[k]?.[pk]); }""")
        result = builder.check_rendered_page(page, self.data)
        self.assertTrue(result["off"], result)

    def test_build_check_reads_the_displayed_final_number(self):
        page = self.page()
        page.evaluate("""() => { const host = document.getElementById('traceBody');
          const descriptor = Object.getOwnPropertyDescriptor(Element.prototype, 'innerHTML');
          Object.defineProperty(host, 'innerHTML', {set(html) {
            descriptor.set.call(this, html);
            this.querySelector('[data-ddf-version="blended"] [data-aggregate-value] .v').textContent = '999';
          }, get() { return descriptor.get.call(this); }}); }""")
        result = builder.check_rendered_page(page, self.data)
        self.assertTrue(result["off"], result)


class ExplainerHarnessSetupTest(unittest.TestCase):
    """Dependency controls run without installing or launching a browser."""

    def run_setup(self, required, *, missing_package=False, missing_browser=False,
                  build_error=None, bundle_error=None):
        class DependencyError(Exception):
            pass

        events = []
        browser = Mock()
        browser.close.side_effect = lambda: events.append("browser closed")
        driver = Mock()
        driver.stop.side_effect = lambda: events.append("driver stopped")
        driver.chromium.launch.return_value = browser
        if missing_browser:
            driver.chromium.launch.side_effect = DependencyError("Chromium executable missing")
        manager = Mock()
        manager.__enter__ = Mock(return_value=driver)
        manager.__exit__ = Mock(side_effect=lambda *a: events.append("driver stopped"))
        manager.start.return_value = driver  # also exercise the pre-fix setup
        api = SimpleNamespace(Error=DependencyError, sync_playwright=Mock(return_value=manager))
        original_import = builtins.__import__

        def dependency_import(name, *args, **kwargs):
            if name == "playwright.sync_api":
                if missing_package:
                    raise ModuleNotFoundError("Playwright missing", name="playwright")
                return api
            return original_import(name, *args, **kwargs)

        class Harness(ExplainerArithmeticRenderTest):
            def runTest(self):
                pass

        result = unittest.TestResult()
        with patch.dict(os.environ, {"RENDER_TESTS_REQUIRED": required}), \
             patch("builtins.__import__", side_effect=dependency_import), \
             patch.object(_render_env, "chromium_executable", return_value="fake-chromium"), \
             patch.object(_render_env, "ensure_built", side_effect=build_error) as build, \
             patch.object(Path, "read_text", return_value='const D = {};\n(function',
                          side_effect=bundle_error):
            unittest.TestSuite([Harness("runTest")]).run(result)
        return result, events, build

    def assert_unavailable(self, result, required):
        self.assertEqual(result.failures, [])
        if required == "0":
            self.assertEqual(result.errors, [])
            self.assertEqual(len(result.skipped), 1)
        else:
            self.assertEqual(result.skipped, [])
            self.assertEqual(len(result.errors), 1)
            self.assertIn("RENDER_TESTS_REQUIRED=1", result.errors[0][1])

    def test_missing_package_obeys_optional_and_required_policy(self):
        for required in ("0", "1"):
            with self.subTest(required=required):
                result, events, build = self.run_setup(required, missing_package=True)
                self.assert_unavailable(result, required)
                self.assertEqual(events, [])
                build.assert_not_called()

    def test_missing_browser_obeys_policy_and_stops_driver(self):
        for required in ("0", "1"):
            with self.subTest(required=required):
                result, events, build = self.run_setup(required, missing_browser=True)
                self.assert_unavailable(result, required)
                self.assertEqual(events, ["driver stopped"])
                build.assert_not_called()

    def test_real_build_errors_never_skip_and_close_resources(self):
        for required in ("0", "1"):
            for error in (RuntimeError("genuine build regression"),
                          ValueError("invalid engine bundle")):
                with self.subTest(required=required, error=type(error).__name__):
                    result, events, build = self.run_setup(required, build_error=error)
                    self.assertEqual(result.skipped, [])
                    self.assertEqual(len(result.errors), 1)
                    self.assertIn(str(error), result.errors[0][1])
                    self.assertEqual(events, ["browser closed", "driver stopped"])
                    build.assert_called_once_with()

    def test_bundle_read_errors_close_resources_without_skipping(self):
        for required in ("0", "1"):
            with self.subTest(required=required):
                result, events, _ = self.run_setup(required, bundle_error=FileNotFoundError("missing build"))
                self.assertEqual(result.skipped, [])
                self.assertEqual(len(result.errors), 1)
                self.assertIn("missing build", result.errors[0][1])
                self.assertEqual(events, ["browser closed", "driver stopped"])

    def test_success_closes_browser_before_driver(self):
        result, events, build = self.run_setup("1")
        self.assertTrue(result.wasSuccessful(), result.errors)
        self.assertEqual(result.testsRun, 1)
        self.assertEqual(events, ["browser closed", "driver stopped"])
        build.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
