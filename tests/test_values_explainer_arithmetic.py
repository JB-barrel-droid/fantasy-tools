"""JEG-1395: explanation arithmetic agrees with the unchanged chart engine."""
from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

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
        _render_env.ensure_built()
        from playwright.sync_api import sync_playwright
        cls.pw = sync_playwright().start()
        cls.browser = cls.pw.chromium.launch(args=_render_env.HERMETIC_ARGS,
                                            executable_path=_render_env.chromium_executable())
        cls.html = (ROOT / "dist/value-logic/index.html").read_text()
        cls.data = json.loads(re.search(r'const D = (.*);\n\(function', cls.html).group(1))

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()

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


if __name__ == "__main__":
    unittest.main()
