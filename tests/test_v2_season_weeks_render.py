"""JEG-527 / GL-24: season week inputs in Edit league.

Loads dist/v2 headless and checks that:

  * Edit league shows the week the values are for, the last regular-season
    week, the playoff weeks and Optimize for, at the defaults (build week,
    14, 15-17, Whole season);
  * changing them reaches (live, no Apply: JEG-1020) the engine (getLeagueWeeks,
    getOptimizeFor, getContentWeek) and moves the bench-share window;
  * Reset defaults in the panel returns them;
  * a shared trade link carries a non-default setting and a fresh page
    opened on it has the same setting, while a default link stays short.

The engine's numbers for these settings are pinned against the Python
reference in test_bench_share_readout_matches_reference.

Discrimination: test_guard_fails_on_broken_builds serves v2.js with the live change
ignoring the weeks and with the link ignoring them, and requires failure.
"""
from __future__ import annotations

import functools
import unittest

from tests import _render_env
from tests.test_v2_share_render import V2_JS, _built_dist, _serve
from tests.test_published_league_settings_render import _chromium_executable


def setUpModule():
    _render_env.ensure_built()


STATE = """() => { const C = window.TradeValueCurveControls; const r = C.getBenchShareReadout();
  return {weeks: C.getLeagueWeeks(), optimize: C.getOptimizeFor(), week: C.getContentWeek(),
          build: C.getBuildContentWeek(), window: r && r.window, hash: location.hash}; }"""


def click(page, label):
    page.click(f'[aria-label="{label}"]')


def run_checks(v2_js=None) -> list[str]:
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        raise _render_env.unavailable(f"Playwright is not available: {exc}") from exc
    errors = []
    with _built_dist() as base, sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(args=_render_env.HERMETIC_ARGS, executable_path=_chromium_executable(playwright))
        except PlaywrightError as exc:
            raise _render_env.unavailable(f"Chromium is not available: {exc}") from exc

        def open_page(url):
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            page.errors = []
            page.on("pageerror", lambda e: page.errors.append(str(e)))
            page.route(lambda u: not u.startswith("http://127.0.0.1"), lambda route: route.abort())
            if v2_js is not None:
                page.route("**/v2/v2.js*", functools.partial(_serve, v2_js))
            page.goto(url, wait_until="networkidle")
            page.wait_for_function("() => window.TradeValueV2 && window.TradeValueV2.compare()", timeout=30000)
            page.wait_for_timeout(200)
            return page

        try:
            page = open_page(base + "#compare-trade")
            first = page.evaluate(STATE)
            build = first["build"]
            if first["weeks"] != {"regularSeasonEnd": 14, "playoffWeeks": [15, 17]} or first["optimize"] != "season" or first["week"] != build:
                errors.append(f"defaults wrong: {first}")
            page.click("#v2EditLeague")
            for ident in ("v2StepContentWeek", "v2StepRegularEnd", "v2StepPlayoffLo", "v2StepPlayoffHi"):
                if page.query_selector(f"#{ident}") is None:
                    errors.append(f"Edit league has no #{ident}")
            # JEG-834: the stepper names the data week (JEG-806 wording), not "the week the values are for".
            label = page.text_content("#v2StepContentWeek")
            if label != "Data through week":
                errors.append(f"Edit league week stepper reads {label!r}, want 'Data through week'")
            click(page, "Earlier Last regular-season week")
            click(page, "Earlier Last playoff week")
            click(page, f"Earlier {label}")
            page.click('.v2-pseg[aria-label="Optimize for"] button[data-value="regular"]')
            page.click('[data-done="league"]')   # JEG-1020: no Apply; Done flushes the pending change and closes
            page.wait_for_timeout(300)
            got = page.evaluate(STATE)
            if got["weeks"] != {"regularSeasonEnd": 13, "playoffWeeks": [15, 16]}:
                errors.append(f"weeks not applied: {got['weeks']}")
            if got["optimize"] != "regular":
                errors.append(f"optimize not applied: {got['optimize']}")
            if got["week"] != build - 1:
                errors.append(f"content week {got['week']} != {build - 1}")
            if got["window"] != [build, 13]:
                errors.append(f"window {got['window']} != {[build, 13]}")
            # Reset defaults inside the panel returns to the build's week, 14, 15-17, Whole season.
            page.click("#v2EditLeague")
            page.click("[data-league-reset]")
            page.click('[data-done="league"]')
            page.wait_for_timeout(300)
            back = page.evaluate(STATE)
            if (back["weeks"], back["optimize"], back["week"]) != (first["weeks"], "season", build):
                errors.append(f"reset did not return the defaults: {back}")
            # Links: a default link stays short; a changed setting is carried and opens the same.
            page.evaluate("() => { const C = window.TradeValueCurveControls; C.setOptimizeFor('playoffs'); C.setContentWeek(%d); }" % max(1, build - 2))
            for field, results, query in (("#v2GiveSearch", "#v2GiveResults", "Gibbs"), ("#v2GetSearch", "#v2GetResults", "Chase")):
                page.fill(field, query)
                page.click(f"{results} button >> nth=0")
            page.wait_for_timeout(300)
            hashed = page.evaluate("() => location.hash")
            if "optimize=playoffs" not in hashed or f"week={max(1, build - 2)}" not in hashed:
                errors.append(f"link does not carry the weeks: {hashed!r}")
            if "regend=" in hashed or "playoffs=" in hashed.replace("optimize=playoffs", ""):
                errors.append(f"link carries default weeks: {hashed!r}")
            shared = open_page(base + hashed)
            same = shared.evaluate(STATE)
            if (same["optimize"], same["week"], same["weeks"]) != ("playoffs", max(1, build - 2), first["weeks"]):
                errors.append(f"link did not set the weeks: {same}")
            for p in (page, shared):
                if p.errors:
                    errors.append(f"page errors {p.errors}")
                p.close()
        finally:
            browser.close()
    return errors


class SeasonWeeksRenderTest(unittest.TestCase):
    def test_season_weeks_in_edit_league(self):
        self.assertEqual(run_checks(), [])

    def test_guard_fails_on_broken_builds(self):
        js = V2_JS.read_text(encoding="utf-8")
        broken = {
            "live change ignores weeks": js.replace("if (draft.weeks) error = applySeasonWeeks(draft.weeks);", "", 1),
            "old week label": js.replace("\"Data through week\", \"content\"", "\"Week the values are for\", \"content\"", 1),
            "link ignores weeks": js.replace("const error = applySeasonWeeks(weeksChange);", "const error = '';", 1),
        }
        for name, body in broken.items():
            with self.subTest(mutation=name):
                self.assertNotEqual(body, js, f"mutation anchor for {name!r} is stale")
                self.assertNotEqual(run_checks(body), [], f"render checks did not catch: {name}")


if __name__ == "__main__":
    unittest.main()
