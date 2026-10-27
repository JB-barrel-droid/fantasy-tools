"""JEG-484: a slow or flaky first load must not drop the chart's data.

product-data.js used to fetch its assets with a 4s timeout and fail open. On a
slow load the timeout fired and series paused, with only a console.warn to
show for it. Since JEG-539 (Jeremy 2026-10-12) the fixture
(assets/comparison-sources-data.json) is the only asset: the fit's
adjustment-inputs.json and the *_adjusted sections are retired.

Headless on the built dist/:
1. The fixture response is delayed past the old 4s timeout: it still loads and
   DDF Value keeps all its inputs.
2. The fixture request fails: it is retried and loads, and
   getLoadStatus() reports the attempts.
3. The page no longer requests adjustment-inputs.json at all.
"""
from __future__ import annotations

import time
import unittest

from tests._dist_server import DIST, serve
from tests import _render_env  # noqa: E402


def setUpModule():
    _render_env.ensure_built()


ADJUSTED = ["fantasycalc_adjusted", "usatoday_adjusted", "fantasypros_adjusted", "cbs_adjusted"]
# JEG-804 (VP-6.3): DDF Value = projection sources only (was all 7 pre-JEG-804).
ALL_INPUTS = ["fantasycalc", "usatoday", "fantasypros", "cbs"]   # JEG-1073: DDF Value inputs are the four trade charts
DETAIL_GLOB = "**/assets/comparison-sources-data.json*"
RETIRED_GLOB = "**/assets/adjustment-inputs.json*"


def expected_inputs(out) -> list[str]:
    """Every DDF input except those the engine excluded (held, not yet published,
    missing, etc.). This test is about the asset load: on 2026-10-10 a fidelity
    hold on ESPN failed it, and the chain could not publish the rebuild that
    would have released the hold."""
    excluded = {e["key"] for e in out["composite"]["excluded"]}
    return sorted(set(ALL_INPUTS) - excluded)

STATE = """() => {
  const c = window.TradeValueCurveControls;
  const pd = window.TradeValueProductData;
  return {
    loadStatus: c.getLoadStatus ? c.getLoadStatus() : null,
    composite: c.getCompositeInputs(),
  };
}"""


def run(route_handler, glob=DETAIL_GLOB):
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

                page.route(glob, handler)
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


def _fail_first_two():
    """The page also fetches the fixture inline (index.html), so the first request may not be
    product-data's. Failing two guarantees one of them hits its first attempt."""
    seen = []

    def handler(route):
        seen.append(1)
        if len(seen) <= 2:
            route.abort("failed")
        else:
            route.continue_()
    return handler


class AssetLoadRetryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not (DIST / "index.html").exists():
            raise _render_env.unavailable("dist/ not built (run make sync)")

    def test_slow_fixture_still_loads(self):
        out = run(_slow)
        self.assertEqual(sorted(out["composite"]["inputs"]), expected_inputs(out),
                         f"DDF Value lost inputs on a slow load: excluded={out['composite']['excluded']}")
        self.assertIsNotNone(out["loadStatus"], "TradeValueCurveControls.getLoadStatus missing")
        status = out["loadStatus"]["assets"]["detail"]
        self.assertTrue(status["ok"])
        self.assertIsNone(status["error"])

    def test_failed_fixture_request_is_retried_and_reported(self):
        out = run(_fail_first_two())
        status = out["loadStatus"]["assets"]["detail"]
        self.assertTrue(status["ok"], status)
        self.assertGreaterEqual(status["attempts"], 2, "the failed fixture request was not retried")
        self.assertGreaterEqual(out["requests"], 3)
        self.assertEqual(sorted(out["composite"]["inputs"]), expected_inputs(out))

    def test_adjustment_inputs_are_not_requested(self):
        """JEG-539: fails on the old page, which fetched assets/adjustment-inputs.json."""
        out = run(lambda route: route.continue_(), glob=RETIRED_GLOB)
        self.assertEqual(out["requests"], 0, "the page still requests the retired adjustment-inputs.json")
        self.assertNotIn("adjustments", out["loadStatus"]["assets"])


if __name__ == "__main__":
    unittest.main()
