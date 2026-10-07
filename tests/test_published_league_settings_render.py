"""Rendered live parity for published charts across league settings (JEG-334, JEG-332 step 3).

Loads the real chart page headless and reads the plotted published-source
maps (window.TradeValueCurveHarness.sourceMaps) for every scoring x team
count, plus one non-default roster:

  * 12 teams, standard roster: every published source (CBS, FantasyPros,
    USA Today, FantasyCalc) plots exactly its SAVED values;
  * 8/10/14 teams and the custom roster: every source is available (no longer
    "unavailable") and plots exactly the reference derivation from
    tests/test_published_league_settings_engine.expected_derived;
  * the fixed-pie guard stays green in every combination.

Discrimination: the same checks run against two broken builds served in
place of the real assets -- one that derives even at the saved setup (USA
Today / FantasyCalc 12-team values move) and one with the derivation unwired
(8/10/14 teams back to unavailable) -- and must fail on both.
"""
from __future__ import annotations

import contextlib
import functools
import http.server
import json
import shutil
import socketserver
import threading
import unittest
from pathlib import Path

from tests.test_published_league_settings_engine import (
    FIXTURE, SAVED_SHAPE, SCORINGS, browser_players, compare_maps, expected_derived,
)

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app" / "trade-value-chart"
PUBLISHED = ("cbs", "fantasypros", "usatoday", "fantasycalc")
CUSTOM_ROSTER = {"RB": 3, "FLEX": 2, "BENCH": 8}


def _chromium_executable(playwright):
    candidates = [Path(playwright.chromium.executable_path)]
    chromium = shutil.which("chromium")
    if chromium:
        candidates.append(Path(chromium))
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return None


@contextlib.contextmanager
def _server():
    class QuietHandler(http.server.SimpleHTTPRequestHandler):
        def log_message(self, format, *args):
            pass
    handler = functools.partial(QuietHandler, directory=str(APP))
    with socketserver.ThreadingTCPServer(("127.0.0.1", 0), handler) as server:
        server.daemon_threads = True
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            yield f"http://127.0.0.1:{server.server_address[1]}/"
        finally:
            server.shutdown()


READ_MAPS = """(keys) => {
  const maps = window.TradeValueCurveHarness.sourceMaps();
  const d = window.TradeValueCurveDiagnostics || {};
  const out = {fixedPie: d.fixedPieIndexed, savedSetup: d.savedSetup, maps: {}};
  keys.forEach(k => { out.maps[k] = Object.fromEntries([...(maps.get(k) || new Map()).entries()]); });
  return out;
}"""


def collect(overrides=None):
    """Return {(scoring, teams, roster_label): {fixedPie, maps}} from the page."""
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        raise unittest.SkipTest(f"Playwright is not available: {exc}") from exc
    out = {}
    with _server() as url, sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(executable_path=_chromium_executable(playwright))
        except PlaywrightError as exc:
            raise unittest.SkipTest(f"Chromium is not available: {exc}") from exc
        try:
            page = browser.new_page()
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            def _serve(body):
                def handler(route):
                    route.fulfill(status=200, content_type="text/javascript", body=body)
                return handler
            for pattern, body in (overrides or {}).items():
                page.route(pattern, _serve(body))
            page.goto(url, wait_until="networkidle")
            page.wait_for_function("() => window.TradeValueCurveHarness && window.TradeValueCurveDiagnostics",
                                   timeout=20000)
            for scoring in SCORINGS:
                for teams in (8, 10, 12, 14):
                    page.evaluate("([s, t]) => { const c = window.TradeValueCurveControls; "
                                  "try { c.setScoring(s); c.setTeams(t); } catch (e) {} }", [scoring, teams])
                    out[(scoring, teams, "std")] = page.evaluate(READ_MAPS, list(PUBLISHED))
            page.evaluate("() => { try { window.TradeValueCurveControls.setScoring('ppr'); "
                          "window.TradeValueCurveControls.setTeams(12); } catch (e) {} }")
            for key, value in CUSTOM_ROSTER.items():
                page.evaluate("""([k, v]) => { const i = document.querySelector(`[data-roster-key="${k}"]`);
                                  i.value = v; i.dispatchEvent(new Event('change')); }""", [key, value])
            out[("ppr", 12, "custom")] = page.evaluate(READ_MAPS, list(PUBLISHED))
            for key, value in SAVED_SHAPE.items():
                page.evaluate("""([k, v]) => { const i = document.querySelector(`[data-roster-key="${k}"]`);
                                  i.value = v; i.dispatchEvent(new Event('change')); }""", [key, value])
            # vorp_views are saved at the 12-team standard setup only and are not
            # derived: at 8 teams the published sources must sit out that view.
            page.locator('#viewModeTabs [data-view-mode="vorp"]').click()
            for teams in (8, 12):
                page.evaluate(f"() => {{ try {{ window.TradeValueCurveControls.setTeams({teams}); }} catch (e) {{}} }}")
                out[f"_vorp_view_{teams}"] = page.evaluate(READ_MAPS, list(PUBLISHED))
            page.locator('#viewModeTabs [data-view-mode="indexed"]').click()
            out["_errors"] = errors
        finally:
            browser.close()
    return out


def verify(collected):
    fixture = json.loads(FIXTURE.read_text())
    pos_of = browser_players()
    problems = []
    for setting, got in collected.items():
        if setting == "_errors":
            problems.extend(f"page error: {e[:200]}" for e in got)
            continue
        if setting == "_vorp_view_8":
            shown = [s for s in PUBLISHED if got["maps"][s]]
            if shown:
                problems.append(f"VORP view at 8 teams shows saved 12-team views for {shown}")
            continue
        if setting == "_vorp_view_12":
            if not any(got["maps"][s] for s in PUBLISHED):
                problems.append("VORP view at the saved setup shows no published source")
            continue
        scoring, teams, label = setting
        shape = SAVED_SHAPE if label == "std" else {**SAVED_SHAPE, **CUSTOM_ROSTER}
        if got["fixedPie"] is not True:
            problems.append(f"{setting}: fixedPieIndexed {got['fixedPie']}")
        for source in PUBLISHED:
            values = {int(k): v for k, v in got["maps"][source].items()}
            if not values:
                problems.append(f"{setting} {source}: unavailable (empty map)")
                continue
            expected = expected_derived(source, scoring, teams, shape, fixture, pos_of)
            diffs, _ = compare_maps(expected, values)
            if diffs:
                problems.append(f"{setting} {source}: {diffs[:2]}")
    return problems


class PublishedLeagueSettingsRender(unittest.TestCase):
    def test_live_page_plots_saved_and_derived_values(self):
        collected = collect()
        problems = verify(collected)
        settings = [k for k in collected if not (isinstance(k, str) and k.startswith("_"))]
        n = sum(len(collected[k]["maps"][s]) for k in settings for s in PUBLISHED)
        print(f"\n[JEG-334 live parity] settings={len(settings)} values_compared={n} "
              f"problems={len(problems)}")
        self.assertEqual(problems, [], "\n".join(problems[:20]))

    def test_guard_fails_on_broken_builds(self):
        model = (APP / "assets" / "value-model.js").read_text()
        widget = (APP / "assets" / "curve-widget.js").read_text()
        always_derive = model.replace("if (Number(teams) !== SAVED_SETUP_TEAMS) return false;",
                                      "return false;")
        unwired = widget.replace(
            "if (AS_PUBLISHED_KEYS.has(key) && !onSavedSetup()) return derivedPublishedSourceMap(key);", "")
        ungated_views = widget.replace("if (viewKey && !onSavedSetup()) return new Map();", "")
        self.assertNotEqual(always_derive, model)
        self.assertNotEqual(unwired, widget)
        self.assertNotEqual(ungated_views, widget)
        for name, overrides in (("always-derive", {"**/assets/value-model.js*": always_derive}),
                                ("unwired", {"**/assets/curve-widget.js*": unwired}),
                                ("ungated-vorp-views", {"**/assets/curve-widget.js*": ungated_views})):
            problems = verify(collect(overrides))
            print(f"\n[JEG-334 negative test] {name}: {len(problems)} problems, e.g. {problems[:1]}")
            self.assertGreater(len(problems), 0, f"broken build {name} was NOT caught")


if __name__ == "__main__":
    unittest.main()
