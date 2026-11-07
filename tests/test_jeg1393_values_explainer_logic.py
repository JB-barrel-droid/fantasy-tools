"""JEG-1393 round 1, lane A: the Full value logic explainer's presentation of
DDF Value membership, hidden sources and the value-above-waivers factor.

Builder helpers are tested on synthetic engine bundles; template rules are
checked on the source. The rendered page is checked by `make values-explainer`
plus the render checks in the JEG-1393 handback.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))

import build_values_explainer as bve  # noqa: E402

TEMPLATE = (ROOT / "app" / "values-explainer" / "template.html").read_text(encoding="utf-8")


def bundle(**extra):
    sources = {"espn": {"vorpFactor": 0.5 * (10 / 4) + 0.5 * (10 / 5)},
               "cbs": {"vorpFactor": 10 / 8}}
    raw = {
        "inspection": {
            "valuePipeline": {"sources": sources},
            "rows": {
                "1": {"ddfByVersion": {"blended": {"sources": ["cbs"]}, "projections": {"sources": ["cbsros"]}}},
                "2": {"ddfByVersion": {"blended": {"sources": ["cbs", "usatoday"]}}},
            },
        },
        "diagnostics": {"excluded": [
            {"key": "espn", "reason": "held: fidelity: scrape_validity", "holdLevel": "red", "hidden": True},
            {"key": "usatoday", "reason": "held: lagging", "holdLevel": "amber"},
            {"key": "espn", "reason": "duplicate", "hidden": True},
        ]},
        "extra": {
            "compositeByVersion": {
                "ddf_value_projections": {"inputs": ["espn", "cbsros", "razzball"], "series": ["cbsros"]},
            },
            "vorpRuns": [
                {"weight": 0.5, "sources": {"espn": [4.0, 10 / 4], "cbs": [8.0, 10 / 8]}},
                {"weight": 0.5, "sources": {"espn": [5.0, 10 / 5], "cbs": [8.0, 10 / 8]}},
            ],
        },
    }
    raw.update(extra)
    return raw


class BuilderHelpersTest(unittest.TestCase):
    def test_hidden_lists_red_holds_once_and_skips_amber(self):
        self.assertEqual(bve.hidden_sources(bundle()),
                         [{"key": "espn", "reason": "held: fidelity: scrape_validity", "level": "red"}])

    def test_version_sources_reads_inputs_series_and_used(self):
        vs = bve.version_sources(bundle())
        self.assertEqual(vs["projections"], {"inputs": ["espn", "cbsros", "razzball"], "series": ["cbsros"],
                                             "used": ["cbsros"]})
        self.assertEqual(vs["blended"]["used"], ["cbs", "usatoday"])
        self.assertIsNone(vs["charts"]["series"])

    def test_vorp_runs_kept_only_when_they_reproduce_the_factor(self):
        runs = bve.vorp_runs(bundle())
        self.assertEqual(sorted(runs), ["cbs", "espn"])
        # The blended factor is the weighted mean of pie / raw surplus per run,
        # not pie / the averaged surplus (10 / 4.5 = 2.222 != 2.25).
        espn = runs["espn"]
        self.assertAlmostEqual(sum(w * f for w, _, f in espn), 2.25)
        self.assertNotAlmostEqual(10 / (0.5 * 4 + 0.5 * 5), 2.25)
        broken = bundle()
        broken["inspection"]["valuePipeline"]["sources"]["espn"]["vorpFactor"] = 9.0
        self.assertNotIn("espn", bve.vorp_runs(broken))

    def test_single_allocation_has_no_runs(self):
        raw = bundle()
        raw["extra"]["vorpRuns"] = None
        self.assertEqual(bve.vorp_runs(raw), {})

    def test_trim_keeps_the_raw_surplus_total(self):
        src = {"surplusTotal": 889.6, "totalVorp": 568.4, "family": "projection"}
        row = bve.trim_pipeline({"sources": {"espn": src}}, full=False)["sources"]["espn"]
        self.assertEqual((row["surplusTotal"], row["totalVorp"]), (889.6, 568.4))


class TemplateRulesTest(unittest.TestCase):
    def test_ddf_value_is_the_trade_charts(self):
        self.assertIn("DDF Value = mean(Adjusted value of each included, non-hidden trade chart that prices the player)",
                      TEMPLATE)
        self.assertIn("DDF Value = mean(Adjusted over included, non-hidden trade charts that price the player)", TEMPLATE)
        self.assertNotIn("non-hidden source that prices the player", TEMPLATE)
        # The trace averages each version's own sources, not every counted source.
        self.assertIn('chain("blended", "ddf_value")', TEMPLATE)
        self.assertNotIn("if (COUNTED.includes(src) && av !== null", TEMPLATE)

    def test_hidden_is_read_per_version(self):
        self.assertIn("D.hidden", TEMPLATE)
        self.assertIn("heldIn(v)", TEMPLATE)

    def test_no_false_single_division_for_the_display_factor(self):
        self.assertNotIn("(${fmt(PIE, 0)} ÷ ${fmtN(s.totalVorp)})", TEMPLATE)
        self.assertIn("Expected-start-weighted parts total", TEMPLATE)

    def test_order_claim_is_qualified(self):
        self.assertNotIn("while keeping its own player order", TEMPLATE)
        self.assertIn("Indexed keeps the published order.", TEMPLATE)

    def test_fill_in_comes_before_the_waiver_line(self):
        self.assertLess(TEMPLATE.index('["Fill in what a chart doesn\'t list"'),
                        TEMPLATE.index('["Native to value above waivers, per source"'))
        self.assertIn("an estimate can set a chart's waiver line", TEMPLATE)

    def test_wording_rules(self):
        self.assertNotIn("Player pool", TEMPLATE)
        self.assertIn("chart's own curve", TEMPLATE)


if __name__ == "__main__":
    unittest.main()
