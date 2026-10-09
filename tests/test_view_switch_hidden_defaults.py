"""A default curve the user hid must survive a view switch (2026-10-09).

Deploy run 37884767247 failed make validate: on the v2 front door every view
switch threw "Curve regression guard failed: defaultGroupedSources". v2 hides
ESPN and the *_adjusted curves through the engine's own source toggles (the
user-deselected set); setViewMode() parked the Indexed selection but cleared
that set, so the guard, which checks the parked Indexed selection, read every
hidden default as a vanished one. The fix parks the hidden set with the
selection and restores it on return.

Headless on the built dist/: the engine page (hide ESPN with its toggle, then
VORP vs waivers -> Adjusted values -> Indexed, with a league change in
between) and the v2 front door (switch views). No page error, the guard
holds, and the user's choice is kept on return.
"""
from __future__ import annotations

import unittest

from tests._dist_server import DIST, serve
from tests import _render_env  # noqa: E402


def setUpModule():
    _render_env.ensure_built()


SWITCH = """async (hide) => {
  const c = window.TradeValueCurveControls;
  const view = v => document.querySelector(`#viewModeTabs [data-view-mode=${v}]`).click();
  const out = {steps: []};
  if (hide) document.querySelector(`#sourceToggles input[data-source="${hide}"]`).click();
  out.activeBefore = c.getActiveSources();
  const steps = [['vorp', () => view('vorp')], ['teams 10', () => c.setTeams(10)], ['adj', () => view('adj')],
    ['indexed', () => view('indexed')], ['teams 12', () => c.setTeams(12)]];
  const settle = () => new Promise(resolve => setTimeout(resolve, 200));
  for (const [tag, step] of steps) {
    step();
    await settle();
    out.steps.push([tag, window.TradeValueCurveDiagnostics.defaultGroupedSources]);
  }
  out.activeAfter = c.getActiveSources();
  return out;
}"""


def run(path: str, hide: str | None):
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
                errors = []
                page.on("pageerror", lambda exc: errors.append(str(exc)))
                page.goto(base + path, wait_until="networkidle")
                page.wait_for_function(
                    "() => window.TradeValueCurveControls && window.TradeValueCurveControls.isReady()", timeout=60000)
                page.wait_for_timeout(300)
                out = page.evaluate(SWITCH, hide)
                page.wait_for_timeout(500)
                out["pageErrors"] = errors
                return out
        finally:
            browser.close()


class ViewSwitchHiddenDefaultsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not (DIST / "index.html").exists():
            raise _render_env.unavailable("dist/ not built (run make sync)")

    def test_engine_page_hidden_default_survives_view_switches(self):
        out = run("/classic/", "espn")
        self.assertEqual(out["pageErrors"], [])
        self.assertNotIn("espn", out["activeBefore"])
        self.assertTrue(all(ok for _tag, ok in out["steps"]), out["steps"])
        self.assertEqual(out["activeAfter"], out["activeBefore"], "the Indexed selection was not restored")

    def test_v2_front_door_view_switches_do_not_throw(self):
        out = run("/", None)
        self.assertEqual(out["pageErrors"], [])
        self.assertTrue(all(ok for _tag, ok in out["steps"]), out["steps"])
        self.assertEqual(out["activeAfter"], out["activeBefore"])


if __name__ == "__main__":
    unittest.main()
