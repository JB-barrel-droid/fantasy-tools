"""JEG-1535 follow-up: an override of 0 is a real override, never "no override".

The Values editor read the stored entry by truthiness, so a saved 0 showed as "= DDF", the button said "Set
override", Reset was disabled and the field reopened at DDF Value, while the store, the engine and the old v2
Overrides tab all held 0. This drives the page's own controls through set 0 -> reopen -> update -> reset and checks
the editor, the live store (ddf-v2-value-overrides, keyed by player_key), the engine row (the page prices the player
at 0) and the old v2 tab reading the same store.
"""
from __future__ import annotations

import json
import unittest

from tests import _render_env
from tests._dist_server import serve

KEY = "2227"
NAME = "Jahmyr Gibbs"
LIVE = "() => document.body.classList.contains('values-live') && !!window.DDF && !!DDF.engine.player('2227')"
STATE = """() => {
  const rec = DDF.engine.player('2227');
  const row = [...document.querySelectorAll('#rows tr')].find(t => t.textContent.includes('Jahmyr Gibbs'));
  return {
    store: JSON.parse(localStorage.getItem('ddf-v2-value-overrides') || 'null'),
    entry: DDF.engine.overrides.get('2227'),
    engineDdf: TradeValueCurveControls.getAllRows().find(r => r.player_key === 2227).values.ddf_value,
    pageDdf: rec.ddf, pageOv: rec.ov,
    cur: document.getElementById('ov-cur').textContent.trim(),
    button: document.getElementById('ov-apply').textContent.trim(),
    resetDisabled: document.getElementById('ov-reset').disabled,
    field: document.getElementById('ov-num').value,
    count: document.getElementById('ov-n').textContent.trim(),
    chartRowOverride: !!(row && row.classList.contains('ov-row')),
  };
}"""


# Navigation waits for DOMContentLoaded, then for the page's own readiness (engine built, modules loaded): the
# engine pages are 1.3 MB and keep fetching, so 'networkidle' can outlast the timeout on a loaded CI runner
# (deploy run 42403384425 timed out there at Page.goto).


def setUpModule():
    _render_env.ensure_built()


class ZeroOverrideTest(unittest.TestCase):
    def _launch(self, pw):
        from playwright.sync_api import Error as PlaywrightError
        try:
            return pw.chromium.launch(args=_render_env.HERMETIC_ARGS, executable_path=_render_env.chromium_executable())
        except PlaywrightError as exc:
            raise _render_env.unavailable(f"Chromium not available: {exc}") from exc

    def _open(self, page, base):
        page.goto(f"{base}/values.html#overrides?player=Jahmyr+Gibbs", wait_until="domcontentloaded", timeout=90000)
        page.wait_for_function(LIVE, timeout=60000)
        page.wait_for_timeout(500)

    def _set(self, page, value):
        page.fill("#ov-num", str(value))
        page.dispatch_event("#ov-num", "input")
        page.click("#ov-apply")
        page.wait_for_timeout(500)

    def test_zero_override_round_trip(self):
        try:
            from playwright.sync_api import sync_playwright
        except Exception as exc:
            raise _render_env.unavailable(f"Playwright not available: {exc}") from exc
        with serve() as base, sync_playwright() as pw:
            browser = self._launch(pw)
            try:
                ctx = browser.new_context(viewport={"width": 1440, "height": 900})
                ctx.route(lambda u: not u.startswith("http://127.0.0.1"), lambda r: r.abort())
                page = ctx.new_page()
                errors = []
                page.on("pageerror", lambda e: errors.append(str(e)))
                self._open(page, base)
                pipeline = page.evaluate("() => DDF.engine.player('2227').base")
                self.assertGreater(pipeline, 1, "fixture player must have a DDF Value above 0")

                # set 0
                self._set(page, 0)
                s = page.evaluate(STATE)
                self.assertEqual(s["store"]["values"], {KEY: 0}, "0 is saved in the live store")
                self.assertEqual(s["entry"], 0)
                self.assertEqual(s["engineDdf"], 0, "the engine prices the player at the override")
                self.assertEqual(s["pageDdf"], 0, "parity: the page record equals the engine row")
                self.assertTrue(s["pageOv"])
                self.assertEqual(s["cur"], "0.0", "editor shows your value 0.0, not '= DDF'")
                self.assertEqual(s["button"], "Update override")
                self.assertFalse(s["resetDisabled"], "Reset to DDF is available for a 0 override")
                self.assertEqual(s["count"], "1")

                # reopen (new page in the same context: localStorage persists)
                page.close()
                page = ctx.new_page()
                page.on("pageerror", lambda e: errors.append(str(e)))
                self._open(page, base)
                s = page.evaluate(STATE)
                self.assertEqual(s["entry"], 0)
                self.assertEqual(s["cur"], "0.0")
                self.assertEqual(s["button"], "Update override")
                self.assertFalse(s["resetDisabled"])
                self.assertEqual(float(s["field"]), 0.0, "the field reopens at the saved 0, not at DDF Value")
                self.assertEqual(s["engineDdf"], 0)
                page.click("#tab-chart")
                page.click('.segmented [data-count="All"]')
                page.wait_for_timeout(300)
                self.assertTrue(page.evaluate(STATE)["chartRowOverride"], "the Chart table marks the 0 override")
                page.click("#tab-ov")

                # update to another value
                self._set(page, 12.5)
                s = page.evaluate(STATE)
                self.assertEqual(s["store"]["values"], {KEY: 12.5})
                self.assertAlmostEqual(s["engineDdf"], 12.5)
                self.assertEqual(s["cur"], "12.5")

                # back to 0, then reset
                self._set(page, 0)
                self.assertEqual(page.evaluate(STATE)["store"]["values"], {KEY: 0})
                page.click("#ov-reset")
                page.wait_for_timeout(500)
                s = page.evaluate(STATE)
                self.assertEqual(s["store"]["values"], {}, "reset removes the 0 override")
                self.assertIsNone(s["entry"])
                self.assertAlmostEqual(s["engineDdf"], pipeline, places=6)
                self.assertEqual(s["cur"], "= DDF")
                self.assertTrue(s["resetDisabled"])
                self.assertEqual(errors, [])
            finally:
                browser.close()

    def test_old_v2_tab_reads_a_zero_saved_on_values(self):
        try:
            from playwright.sync_api import sync_playwright
        except Exception as exc:
            raise _render_env.unavailable(f"Playwright not available: {exc}") from exc
        record = json.dumps({"v": 2, "basis": {"mode": "default"}, "values": {KEY: 0}, "names": {KEY: NAME}})
        with serve() as base, sync_playwright() as pw:
            browser = self._launch(pw)
            try:
                ctx = browser.new_context(viewport={"width": 1440, "height": 900})
                ctx.route(lambda u: not u.startswith("http://127.0.0.1"), lambda r: r.abort())
                page = ctx.new_page()
                page.goto(f"{base}/values.html", wait_until="domcontentloaded", timeout=90000)
                page.evaluate(f"() => localStorage.setItem('ddf-v2-value-overrides', {json.dumps(record)})")
                # JEG-1539: the v2 shell is build-only; the harness serves it at /v2-app.html with every view.
                page.goto(f"{base}/v2-app.html#value-overrides", wait_until="domcontentloaded", timeout=90000)
                page.wait_for_function("() => window.DDFOverrides && window.TradeValueCurveControls && TradeValueCurveControls.isReady()", timeout=90000)
                page.wait_for_timeout(1500)
                got = page.evaluate("() => ({all: DDFOverrides.all(), ddf: TradeValueCurveControls.getAllRows().find(r => r.player_key === 2227).values.ddf_value})")
                self.assertEqual(got["all"], {KEY: 0})
                self.assertEqual(got["ddf"], 0)
            finally:
                browser.close()


if __name__ == "__main__":
    unittest.main()
