"""JEG-484: a slow first load must not silently drop the adjusted series.

product-data.js used to fetch assets/adjustment-inputs.json with a 4s timeout
and fail open (.catch(() => null)). On a slow load the timeout fired, every
*_adjusted series paused and DDF Value fell from 7 inputs to 3, with only a
console.warn to show for it.

Headless on the built dist/:
1. The adjustment-inputs response is delayed past the old 4s timeout: the
   adjusted series still load, DDF Value keeps all 7 inputs.
2. The adjustment-inputs request fails every time: it is retried (3 attempts),
   then getLoadStatus() reports the failure. Since JEG-497 (Jeremy 2026-10-09)
   the DDF Value reads each chart's Adjusted values, not the fitted *_adjusted
   series, so a failed adjustment load no longer removes any DDF input; the
   rows' *_adjusted nulls carry "Adjustment data failed to load"
   (tests/test_row_missing_reasons.py).
"""
from __future__ import annotations

import time
import unittest

from tests._dist_server import DIST, serve
from tests import _render_env  # noqa: E402


def setUpModule():
    _render_env.ensure_built()


ADJUSTED = ["fantasycalc_adjusted", "usatoday_adjusted", "fantasypros_adjusted", "cbs_adjusted"]
# JEG-508 (VP-11): the DDF inputs are source keys; a chart input is the chart.
ALL_INPUTS = ["espn", "cbsros", "razzball", "fantasycalc", "usatoday", "fantasypros", "cbs"]
ADJUSTMENTS_GLOB = "**/assets/adjustment-inputs.json*"


def expected_inputs(out) -> list[str]:
    """Every DDF input except those the built fixture holds (validationHold: a JEG-479 value check or
    JEG-520 fidelity hold). A held source is left out of DDF Value by design, so a hold never stops
    the site. This test is about the adjustment load: on 2026-10-10 a fidelity hold on ESPN failed it,
    and the chain could not publish the rebuild that would have released the hold."""
    held = {e["key"] for e in out["composite"]["excluded"] if str(e.get("reason") or "").startswith("held:")}
    return sorted(set(ALL_INPUTS) - held)

STATE = """() => {
  const c = window.TradeValueCurveControls;
  const pd = window.TradeValueProductData;
  return {
    adjustmentsLoaded: pd.getProviderInfo().adjustmentsLoaded,
    loadStatus: c.getLoadStatus ? c.getLoadStatus() : null,
    composite: c.getCompositeInputs(),
  };
}"""


def run(route_handler):
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise _render_env.unavailable(f"Playwright is not available: {exc}") from exc
    with sync_playwright() as p:
        exe = _render_env.chromium_executable(p)
        if exe is None:
            raise _render_env.unavailable("no Chromium available")
        browser = p.chromium.launch(args=_render_env.HERMETIC_ARGS, executable_path=exe)
        try:
            with serve(DIST) as base:
                page = browser.new_page(viewport={"width": 1280, "height": 900})
                calls = []

                def handler(route):
                    calls.append(time.monotonic())
                    route_handler(route)

                page.route(ADJUSTMENTS_GLOB, handler)
                page.goto(base + "/", wait_until="domcontentloaded")
                page.wait_for_function(
                    "() => window.TradeValueCurveControls && window.TradeValueCurveControls.isReady()",
                    timeout=90000)
                page.wait_for_timeout(300)
                result = page.evaluate(STATE)
                result["requests"] = len(calls)
                return result
        finally:
            browser.close()


def _slow(route):
    time.sleep(5.5)  # past the old FETCH_TIMEOUT_MS = 4000
    route.continue_()


def _broken(route):
    route.abort("failed")


class AssetLoadRetryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not (DIST / "index.html").exists():
            raise _render_env.unavailable("dist/ not built (run make sync)")

    def test_slow_adjustment_inputs_still_load(self):
        out = run(_slow)
        self.assertTrue(out["adjustmentsLoaded"], "adjustment inputs dropped on a slow load")
        self.assertEqual(sorted(out["composite"]["inputs"]), expected_inputs(out),
                         f"DDF Value lost inputs on a slow load: excluded={out['composite']['excluded']}")
        self.assertIsNotNone(out["loadStatus"], "TradeValueCurveControls.getLoadStatus missing")
        status = out["loadStatus"]["assets"]["adjustments"]
        self.assertTrue(status["ok"])
        self.assertIsNone(status["error"])
        self.assertTrue(out["loadStatus"]["adjustmentsLoaded"])
        self.assertTrue(out["loadStatus"]["assets"]["detail"]["ok"])

    def test_failed_adjustment_inputs_are_reported(self):
        out = run(_broken)
        self.assertIsNotNone(out["loadStatus"], "TradeValueCurveControls.getLoadStatus missing")
        status = out["loadStatus"]["assets"]["adjustments"]
        self.assertFalse(status["ok"])
        self.assertTrue(status["error"])
        self.assertEqual(status["attempts"], 3)
        self.assertEqual(out["requests"], 3, "the adjustment inputs were not retried")
        self.assertFalse(out["loadStatus"]["adjustmentsLoaded"])
        # JEG-497: the DDF inputs do not depend on the adjustment data.
        reasons = {e["key"]: e["reason"] for e in out["composite"]["excluded"]}
        self.assertNotIn("Adjustment data failed to load", reasons.values(), reasons)
        self.assertEqual(sorted(out["composite"]["inputs"]), expected_inputs(out), reasons)


if __name__ == "__main__":
    unittest.main()
