"""Rendered live parity for the "VORP vs waivers" and "Adjusted values" views
of the published charts at any league setting (JEG332-VORP-VIEWS).

Loads the real chart page headless, switches to each view, and reads the
plotted published-source maps (window.TradeValueCurveHarness.sourceMaps) plus
the live ESPN anchor at several scoring x team count settings and one custom
roster:

  * at the saved views' own setup (their scoring, 12 teams, standard roster)
    FantasyCalc / FantasyPros / USA Today plot exactly their SAVED
    `vorp_views` (resolved through the fixture's player_keys) -- not the
    Indexed values, which is what the views silently showed from JEG-363 until
    2026-10-07 because the lookup table was missing from the snapshot;
  * everywhere else -- including 12 teams in Standard / Half PPR, which used to
    show the full-PPR views -- every published chart (CBS included) plots
    exactly the reference derivation
    (tests/test_published_views_engine.expected_views) with group budgets
    measured off the live anchor by an independent port of ValueModel.roleMap;
  * no page errors, fixed-pie guard green.

Discrimination: test_guard_fails_on_broken_builds serves four broken widgets.
"""
from __future__ import annotations

import json
import unittest

from tests.test_published_league_settings_engine import (
    FIXTURE, INDEX, POSITIONS, SAVED_SHAPE, browser_inputs, browser_players,
)
from tests.test_published_league_settings_render import APP, _chromium_executable, _server
from tests.test_published_views_engine import expected_views

import re
from tests import _render_env  # noqa: E402


def setUpModule():
    # Build app/ and dist/ from the committed fixtures first, so the
    # test never reads a stale committed build (GAP-APP-ASSETS-LAG).
    _render_env.ensure_built()


PUBLISHED = ("cbs", "fantasypros", "usatoday", "fantasycalc")
SAVED_VIEW_SOURCES = ("fantasypros", "usatoday", "fantasycalc")
VIEWS = {"vorp": "vorp", "adj": "adj_values"}
CUSTOM_ROSTER = {"RB": 3, "FLEX": 2, "BENCH": 8}
STD_SETTINGS = [("ppr", 12), ("standard", 12), ("half_ppr", 12), ("ppr", 8), ("standard", 14), ("half_ppr", 10)]
TOL = 1e-9

READ = """(keys) => {
  const maps = window.TradeValueCurveHarness.sourceMaps();
  const d = window.TradeValueCurveDiagnostics || {};
  const out = {fixedPie: d.fixedPieIndexed, viewMode: d.viewMode, publishedView: d.publishedView, maps: {}};
  keys.forEach(k => { out.maps[k] = Object.fromEntries([...(maps.get(k) || new Map()).entries()]); });
  return out;
}"""


def player_names():
    html = INDEX.read_text(encoding="utf-8")
    m = re.search(r'<script id="players-data" type="application/json">(.*?)</script>', html, re.S)
    return {p["player_key"]: str(p.get("name") or "") for p in json.loads(m.group(1))["players"]
            if isinstance(p.get("player_key"), int)}


def role_map(values, pos_of, names, teams, shape):
    """Independent port of ValueModel.roleMap: dedicated slots by value, then
    superflex slots (any position, JEG332-SUPERFLEX-FLEX option A), then flex
    (RB/WR/TE), then bench, by value."""
    rows = [(k, v) for k, v in values.items() if pos_of.get(k) in POSITIONS and v > 0]
    rows.sort(key=lambda r: (-r[1], names.get(r[0], ""), r[0]))
    roles = {}
    for pos in POSITIONS:
        for k, _ in [r for r in rows if pos_of[r[0]] == pos][:teams * shape.get(pos, 0)]:
            roles[k] = "starter"
    for k, _ in [r for r in rows if r[0] not in roles][:teams * int(shape.get("SUPERFLEX", 0))]:
        roles[k] = "starter"
    elig = ("RB", "WR", "TE")
    for k, _ in [r for r in rows if pos_of[r[0]] in elig and r[0] not in roles][:teams * shape.get("FLEX", 0)]:
        roles[k] = "starter"
    for k, _ in [r for r in rows if r[0] not in roles][:teams * shape.get("BENCH", 0)]:
        roles[k] = "bench"
    return roles


def anchor_budgets(anchor, keys, pos_of, names, teams, shape):
    roles = role_map(anchor, pos_of, names, teams, shape)
    keyset = set(keys)
    out = {p: {"starter": 0.0, "bench": 0.0} for p in POSITIONS}
    for k, v in anchor.items():
        role = roles.get(k)
        if k in keyset and role in ("starter", "bench") and pos_of.get(k) in POSITIONS:
            out[pos_of[k]][role] += max(0.0, v)
    return out


def saved_view(fixture, source, view_key, pos_of):
    pk = fixture["player_keys"]
    out = {}
    for name, value in fixture["sources"][source]["vorp_views"]["views"][view_key].items():
        key = pk.get(str(name).strip().lower())
        if isinstance(key, int) and key in pos_of and value is not None:
            out[key] = max(0.0, float(value))
    return out


def collect(overrides=None):
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
            keys = list(PUBLISHED) + ["espn"]
            for mode in VIEWS:
                page.locator(f'#viewModeTabs [data-view-mode="{mode}"]').click()
                for scoring, teams in STD_SETTINGS:
                    page.evaluate("([s, t]) => { const c = window.TradeValueCurveControls; "
                                  "try { c.setScoring(s); c.setTeams(t); } catch (e) {} }", [scoring, teams])
                    out[(mode, scoring, teams, "std")] = page.evaluate(READ, keys)
            # Custom roster at full PPR / 12 teams, Adjusted view still active.
            page.evaluate("() => { try { window.TradeValueCurveControls.setScoring('ppr'); "
                          "window.TradeValueCurveControls.setTeams(12); } catch (e) {} }")
            for key, value in CUSTOM_ROSTER.items():
                page.evaluate("""([k, v]) => { const i = document.querySelector(`[data-roster-key="${k}"]`);
                                  i.value = v; i.dispatchEvent(new Event('change')); }""", [key, value])
            out[("adj", "ppr", 12, "custom")] = page.evaluate(READ, keys)
            page.locator('#viewModeTabs [data-view-mode="vorp"]').click()
            out[("vorp", "ppr", 12, "custom")] = page.evaluate(READ, keys)
            page.locator('#viewModeTabs [data-view-mode="indexed"]').click()
            out["_errors"] = errors
        finally:
            browser.close()
    return out


def verify(collected):
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    pos_of = browser_players()
    names = player_names()
    problems = []
    for setting, got in collected.items():
        if setting == "_errors":
            problems.extend(f"page error: {e[:200]}" for e in got)
            continue
        mode, scoring, teams, label = setting
        shape = SAVED_SHAPE if label == "std" else {**SAVED_SHAPE, **CUSTOM_ROSTER}
        view_key = VIEWS[mode]
        if got.get("viewMode") != mode:
            problems.append(f"{setting}: viewMode {got.get('viewMode')}")
        if got["fixedPie"] is not True:
            problems.append(f"{setting}: fixedPieIndexed {got['fixedPie']}")
        maps = {s: {int(k): v for k, v in got["maps"][s].items()} for s in PUBLISHED}
        anchor = {int(k): v for k, v in got["maps"]["espn"].items()}
        saved_setup = (scoring == "ppr" and teams == 12 and label == "std")
        inputs = {}
        for source in PUBLISHED:
            native, saved, _ = browser_inputs(fixture, pos_of, source, scoring)
            keys = [k for k, _ in saved]
            inputs[source] = (native, keys, anchor_budgets(anchor, keys, pos_of, names, teams, shape))
        exp = expected_views(inputs, teams, shape, pos_of)
        for source in PUBLISHED:
            values = maps[source]
            if not values:
                problems.append(f"{setting} {source}: unavailable (empty map)")
                continue
            if saved_setup and source in SAVED_VIEW_SOURCES:
                want, kind = saved_view(fixture, source, view_key, pos_of), "saved"
            else:
                want, kind = exp[source]["vorp" if mode == "vorp" else "adj"], "derived"
            if set(want) != set(values):
                problems.append(f"{setting} {source} ({kind}): player sets differ "
                                f"missing={sorted(set(want) - set(values))[:3]} extra={sorted(set(values) - set(want))[:3]}")
                continue
            bad = [(k, want[k], values[k]) for k in want if abs(want[k] - values[k]) > TOL]
            if bad:
                problems.append(f"{setting} {source} ({kind}): {len(bad)} values differ, e.g. {bad[:2]}")
    return problems


class PublishedViewsRender(unittest.TestCase):
    def test_live_views_plot_saved_and_derived_values(self):
        collected = collect()
        problems = verify(collected)
        settings = [k for k in collected if k != "_errors"]
        n = sum(len(collected[k]["maps"][s]) for k in settings for s in PUBLISHED)
        print(f"\n[JEG332-VORP-VIEWS live parity] settings={len(settings)} values_compared={n} "
              f"problems={len(problems)}")
        self.assertEqual(problems, [], "\n".join(problems[:20]))

    def test_guard_fails_on_broken_builds(self):
        widget = (APP / "assets" / "curve-widget.js").read_text(encoding="utf-8")
        broken = {
            # the JEG-363 regression: lookup table read from the snapshot
            # (empty), so the saved views never resolve
            "saved-views-unresolved": (
                "const keysById = window.TradeValueProductData?.getPlayerKeysBySourceId?.() || new Map();",
                "const keysById = new Map(Object.entries(data.player_keys || {}));"),
            # the pre-2026-10-07 scoring blind spot: Standard / Half PPR at 12
            # teams show the full-PPR saved views
            "scoring-unchecked": (
                "return VIEW_SCORING[String(vorpViews.scoring || \"\").toLowerCase()] === scoring\n      && Number(vorpViews.teams) === teams;",
                "return Number(vorpViews.teams) === teams;"),
            # views not derived: published charts sit out at non-saved settings
            # (anchored on the leading newline: the math inspector added an
            # indented `const batch = derivedViewBatch();` of its own, 2026-10-08)
            "not-derived": (
                "\n    const batch = derivedViewBatch();\n",
                "\n    if (true) return new Map();\n    const batch = derivedViewBatch();\n"),
            # views show the Indexed values in disguise
            "indexed-in-disguise": (
                "      if (viewKey) return publishedViewMap(key, viewKey);",
                "      if (viewKey) return buildPublishedSourceMap(key);"),
        }
        for name, (old, new) in broken.items():
            self.assertEqual(widget.count(old), 1, f"mutation anchor for {name} moved")
            problems = verify(collect({"**/assets/curve-widget.js*": widget.replace(old, new)}))
            print(f"\n[JEG332-VORP-VIEWS live negative test] {name}: {len(problems)} problems, e.g. {problems[:1]}")
            self.assertGreater(len(problems), 0, f"broken build {name} was NOT caught")


if __name__ == "__main__":
    unittest.main()
