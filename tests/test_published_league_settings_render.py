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

The other two chart views ("VORP vs waivers", "Adjusted values") are checked
live in tests/test_published_views_render.py (JEG332-VORP-VIEWS); until
2026-10-07 this file pinned their old sit-out-at-non-saved-settings gating.

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
from tests import _render_env  # noqa: E402


def setUpModule():
    # Build app/ and dist/ from the committed fixtures first, so the
    # test never reads a stale committed build (GAP-APP-ASSETS-LAG).
    _render_env.ensure_built()


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app" / "trade-value-chart"
PUBLISHED = ("cbs", "fantasypros", "usatoday", "fantasycalc")
CUSTOM_ROSTER = {"RB": 3, "FLEX": 2, "BENCH": 8}


def _chromium_executable(playwright):
    return _render_env.chromium_executable(playwright)


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
        raise _render_env.unavailable(f"Playwright is not available: {exc}") from exc
    out = {}
    with _server() as url, sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(args=_render_env.HERMETIC_ARGS, executable_path=_chromium_executable(playwright))
        except PlaywrightError as exc:
            raise _render_env.unavailable(f"Chromium is not available: {exc}") from exc
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
            out["_errors"] = errors
        finally:
            browser.close()
    return out


def verify(collected):
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    pos_of = browser_players()
    problems = []
    for setting, got in collected.items():
        if setting == "_errors":
            problems.extend(f"page error: {e[:200]}" for e in got)
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
        model = (APP / "assets" / "value-model.js").read_text(encoding="utf-8")
        widget = (APP / "assets" / "curve-widget.js").read_text(encoding="utf-8")
        # "never-derive": every setting treated as the saved one, so 8/10/14 teams
        # and custom rosters plot the saved 12-team values. (Until #386 this was
        # "always-derive" -- deriving at the saved setup too -- which no longer
        # differs from the saved values once those ARE the current translation,
        # so it stopped being a broken state.)
        never_derive = model.replace("if (Number(teams) !== SAVED_SETUP_TEAMS) return false;",
                                     "return true;")
        unwired = widget.replace(
            "if (AS_PUBLISHED_KEYS.has(key) && !onSavedSetup()) return derivedPublishedSourceMap(key);", "")
        self.assertNotEqual(never_derive, model)
        self.assertNotEqual(unwired, widget)
        for name, overrides in (("never-derive", {"**/assets/value-model.js*": never_derive}),
                                ("unwired", {"**/assets/curve-widget.js*": unwired})):
            problems = verify(collect(overrides))
            print(f"\n[JEG-334 negative test] {name}: {len(problems)} problems, e.g. {problems[:1]}")
            self.assertGreater(len(problems), 0, f"broken build {name} was NOT caught")


if __name__ == "__main__":
    unittest.main()
