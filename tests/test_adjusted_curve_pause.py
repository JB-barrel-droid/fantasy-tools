"""Fixture-transition Option B: paused adjusted curves (staged 2026-09-22).

The four *_adjusted curves are PAUSED while their source has no live
adjustment cells in adjustment-inputs.json. espn ("ESPN adjusted") is the
live bottom-up leg and is never paused.

The pause predicate is a pure function tested behaviorally through the Node
harness; the DOM wiring (toggles, defaults, lock fallbacks) is asserted
statically against curve-widget.js, the same pattern test_static_export.py
uses for DOM-dependent code.
"""
import json
import subprocess
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
WIDGET = REPO / "app" / "trade-value-chart" / "assets" / "curve-widget.js"
HARNESS = Path(__file__).resolve().parent / "two_tier_harness.js"
INPUTS_ASSET = REPO / "app" / "trade-value-chart" / "assets" / "adjustment-inputs.json"
FIXTURE = REPO / "data" / "fixtures" / "current" / "comparison-sources-data.json"

PAUSED_KEYS = ["fantasycalc_adjusted", "usatoday_adjusted",
               "fantasypros_adjusted", "cbs_adjusted"]
EMPTY_INPUTS = {"version": "trade-value-adjustment-inputs-v1", "sources": {}}


def run_pause(cases):
    proc = subprocess.run(["node", str(HARNESS), "pause"],
                          input=json.dumps({"cases": cases}),
                          capture_output=True, text=True, timeout=120)
    if proc.returncode != 0:
        raise AssertionError(f"harness pause failed: {proc.stderr[:2000]}")
    return json.loads(proc.stdout)


class TestPausePredicate(unittest.TestCase):
    def test_adjusted_curves_paused_with_empty_inputs(self):
        got = run_pause([{"key": k, "inputs": EMPTY_INPUTS} for k in PAUSED_KEYS])
        self.assertEqual(got, [True] * 4)

    def test_stage2_live_asset_unpauses_all_four(self):
        # Stage 2 (2026-09-22): the live asset carries validated cells for
        # every source, so every *_adjusted curve returns to the toggle
        # list with NO widget code change. The pause mechanism itself is
        # unchanged: any source whose cells array empties pauses again
        # (see test_empty_cells_array_stays_paused).
        asset = json.loads(INPUTS_ASSET.read_text(encoding="utf-8"))
        self.assertEqual(asset["status"], "live")
        for key in PAUSED_KEYS:
            raw = key[:-len("_adjusted")] if key != "cbs_adjusted" else "cbs"
            self.assertTrue(asset["sources"][raw]["cells"],
                            f"{key} has no live cells")
        got = run_pause([{"key": k, "inputs": asset} for k in PAUSED_KEYS])
        self.assertEqual(got, [False] * 4)

    def test_espn_never_paused(self):
        asset = json.loads(INPUTS_ASSET.read_text(encoding="utf-8"))
        for inputs in (EMPTY_INPUTS, asset, None):
            got = run_pause([{"key": "espn", "inputs": inputs}])
            self.assertEqual(got, [False], f"espn paused with {inputs!r}")

    def test_raw_and_vorp_keys_never_paused(self):
        got = run_pause([{"key": k, "inputs": EMPTY_INPUTS}
                         for k in ("fantasycalc", "usatoday", "fantasypros",
                                   "cbs", "espn_vorp")])
        self.assertEqual(got, [False] * 5)

    def test_auto_return_when_cells_land(self):
        cells = {"sources": {
            "fantasycalc": {"cells": [{"position": "QB", "tier": "starter",
                                       "alpha": 0.0, "beta": 1.0}]},
            "cbs": {"cells": [{"position": "RB", "tier": "bench",
                               "alpha": 1.0, "beta": 0.9}]},
        }}
        got = run_pause([{"key": "fantasycalc_adjusted", "inputs": cells},
                         {"key": "cbs_adjusted", "inputs": cells},
                         {"key": "usatoday_adjusted", "inputs": cells}])
        # fantasycalc + cbs un-pause (cbs_adjusted reads sources.cbs);
        # usatoday stays paused. No code change, no re-bake.
        self.assertEqual(got, [False, False, True])

    def test_empty_cells_array_stays_paused(self):
        got = run_pause([{"key": "fantasycalc_adjusted",
                          "inputs": {"sources": {"fantasycalc": {"cells": []}}}}])
        self.assertEqual(got, [True])

    def test_missing_inputs_fail_closed_to_paused(self):
        for inputs in (None, {}, {"sources": None}, {"nope": 1}):
            got = run_pause([{"key": k, "inputs": inputs}
                             for k in PAUSED_KEYS])
            self.assertEqual(got, [True] * 4, f"not fail-closed for {inputs!r}")


def run_defaultset(cases):
    proc = subprocess.run(["node", str(HARNESS), "defaultset"],
                          input=json.dumps({"cases": cases}),
                          capture_output=True, text=True, timeout=120)
    if proc.returncode != 0:
        raise AssertionError(f"harness defaultset failed: {proc.stderr[:2000]}")
    return json.loads(proc.stdout)


class TestDefaultActiveSet(unittest.TestCase):
    """The default active set restores un-paused adjusted curves.

    Banner copy promises the four adjusted source projects are "shown by
    default" once cells are live; this makes the copy true. Named defect:
    defaults stuck at ["espn"] after auto-un-pause, so the banner overclaims
    while the curves render enabled-yet-unchecked.
    """

    def test_live_asset_defaults_include_all_five(self):
        asset = json.loads(INPUTS_ASSET.read_text(encoding="utf-8"))
        self.assertEqual(asset["status"], "live")
        got = run_defaultset([{"inputs": asset}])
        self.assertEqual(got, [["espn", "fantasycalc_adjusted",
                                "usatoday_adjusted", "fantasypros_adjusted",
                                "cbs_adjusted"]])

    def test_empty_inputs_default_to_espn_only(self):
        got = run_defaultset([{"inputs": EMPTY_INPUTS}])
        self.assertEqual(got, [["espn"]])

    def test_missing_inputs_fail_closed_to_espn_only(self):
        for inputs in (None, {}, {"sources": None}, {"nope": 1}):
            got = run_defaultset([{"inputs": inputs}])
            self.assertEqual(got, [["espn"]], f"not fail-closed for {inputs!r}")

    def test_partial_cells_restore_only_live_sources(self):
        cells = {"sources": {
            "fantasycalc": {"cells": [{"position": "QB", "tier": "starter",
                                       "alpha": 0.0, "beta": 1.0}]},
            "cbs": {"cells": [{"position": "RB", "tier": "bench",
                               "alpha": 1.0, "beta": 0.9}]},
        }}
        got = run_defaultset([{"inputs": cells}])
        self.assertEqual(got, [["espn", "fantasycalc_adjusted", "cbs_adjusted"]])

    def test_empty_cells_array_does_not_restore(self):
        # Negative test of the named defect's quieter cousin: a source whose
        # cells array emptied must NOT come back into the default set.
        got = run_defaultset([{"inputs": {"sources": {
            "fantasycalc": {"cells": []}}}}])
        self.assertEqual(got, [["espn"]])
    @classmethod
    def setUpClass(cls):
        cls.text = WIDGET.read_text(encoding="utf-8")

class TestPauseWiring(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = WIDGET.read_text(encoding="utf-8")

    def test_default_active_set_is_espn_only(self):
        self.assertIn('DEFAULT_INDEXED_SOURCES = ["espn"]', self.text)
        self.assertNotIn(
            'DEFAULT_INDEXED_SOURCES = ["espn", "fantasycalc_adjusted"',
            self.text)

    def test_default_lock_order_is_espn(self):
        self.assertIn('let lockOrder = "espn"', self.text)
        self.assertNotIn('let lockOrder = "fantasycalc_adjusted"', self.text)

    def test_lock_fallbacks_are_pause_aware(self):
        self.assertIn("!isAdjustedCurvePaused(\"fantasycalc_adjusted\")"
                      " && sourceAvailable(\"fantasycalc_adjusted\")", self.text)
        self.assertIn("!isAdjustedCurvePaused(lockOrder)", self.text)

    def test_active_sources_exclude_paused(self):
        self.assertIn("!isAdjustedCurvePaused(key)", self.text)

    def test_toggle_greys_paused_with_explanation(self):
        self.assertIn("const paused = isAdjustedCurvePaused(key)", self.text)
        self.assertIn("waiting on fresh adjustment inputs", self.text)
        self.assertIn("paused · waiting on fresh adjustment inputs", self.text)

    def test_validated_status_names_pause(self):
        self.assertIn("are paused while they wait on fresh adjustment inputs",
                      self.text)

    def test_baked_fixture_sections_not_deleted(self):
        # Option B is a display change only: the baked *_adjusted sections
        # stay in the fixture for the fallback render path.
        fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
        sources = fixture["sources"]
        for key in ("fantasycalc_adjusted", "usatoday_adjusted",
                    "fantasypros_adjusted"):
            self.assertIn(key, sources, f"{key} removed from fixture")
        self.assertIn("buildCbsAdjustedMap", self.text)

    def test_pause_predicate_is_pure_and_exposed(self):
        self.assertIn("function adjustedCurvePaused(key, inputs)", self.text)
        self.assertIn("globalThis.TradeValueCurvePause", self.text)

    def test_init_restores_live_curves_to_default_active_set(self):
        # Named defect: defaults stuck at ["espn"] after auto-un-pause while
        # the banner promises the four adjusted projects are shown by
        # default. init() must recompute the default active set from the
        # loaded inputs on fresh load.
        self.assertIn(
            "activeSources = new Set(defaultIndexedSourceKeys(adjustmentInputs))",
            self.text)
        self.assertIn("function defaultIndexedSourceKeys(inputs)", self.text)
        self.assertIn("defaultIndexedSourceKeys", self.text)

    def test_regression_guard_checks_computed_default_set(self):
        self.assertIn(
            "defaultIndexedSourceKeys(adjustmentInputs).every(key => activeSources.has(key))",
            self.text)


if __name__ == "__main__":
    unittest.main()
