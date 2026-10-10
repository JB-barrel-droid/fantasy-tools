"""Chart views measured against Jeremy's invariants (views-audit/2, JEG-508).

Jeremy, 2026-10-08:
  * Indexed: "the positions and bench/starter have different weights but the
    total pies are the same."
  * VORP vs waivers: "the differences in deconstructed values of each player
    on the same exact scale."
  * Adjusted values: "the differences in value of each player, when their
    positional and bench/starter weights have been normalized."

JEG-508 (docs/methodology.md "Value Pipeline", VP-5 / VP-6.4) makes all three
exact for every source, with no anchor: the fixed league pie is
28 x teams x starting slots (OC-1), and
  * VORP vs waivers: every source's values (charts and the projections'
    *_vorp series) total the pie;
  * Adjusted values: every source's values total the pie (less any budget a
    source cannot fund, which the page reports);
  * Indexed: each chart's values over the players it lists total their
    blended DDF Value.
Recomputed here from the plotted maps (window.TradeValueCurveHarness.
sourceMaps), the rows and the page's pipeline result, at the 3 scorings x
8/10/12/14 teams, a custom roster and bench shares of 30% and 5%, in all three
tabs; the page's own viewInvariants must agree (gatedHold).

Before JEG-508 the basis was the ESPN anchor's shared total and the published
charts were measured, not gated; that model is retired (VP-10).

Discrimination (test_guard_fails_on_broken_engines): a VORP vs waivers series
left unscaled (raw value above waivers) and an Adjusted value that pays the
starter slice at the bench rate must fail.
"""
from __future__ import annotations

import json
import unittest

from tests.test_published_league_settings_render import APP, _server
from tests import _render_env  # noqa: E402


def setUpModule():
    # Build app/ and dist/ from the committed fixtures first, so the
    # test never reads a stale committed build (GAP-APP-ASSETS-LAG).
    _render_env.ensure_built()


PUBLISHED = ("cbs", "fantasypros", "usatoday", "fantasycalc")
RAW_VORP = ("espn_vorp", "cbsros_vorp", "razzball_vorp")
CUSTOM_ROSTER = {"RB": 3, "FLEX": 2, "BENCH": 8}
MIN_SHARED = 40
REL_TOL = 1e-6
VALUE_TOL = 1e-9
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

# (scoring, teams, roster overrides or None, bench share in PERCENT -- the
# TradeValueCurveControls.setBenchShare unit -- or None)
SETTINGS = [(s, t, None, None) for s in ("standard", "half_ppr", "ppr") for t in (8, 10, 12, 14)]
SETTINGS += [("ppr", 12, CUSTOM_ROSTER, None), ("ppr", 12, None, 30), ("half_ppr", 10, None, 5)]

READ = """() => {
  const H = window.TradeValueCurveHarness;
  const maps = H.sourceMaps();
  const d = window.TradeValueCurveDiagnostics || {};
  const result = H.pipeline();
  const listed = {};
  Object.entries(result.sources).forEach(([k, src]) => {
    listed[k] = Object.entries(src.players).filter(([, p]) => !p.estimated).map(([pk]) => Number(pk));
  });
  const ddf = {};
  window.TradeValueCurveControls.getAllRows().forEach(r => { ddf[r.player_key] = r.values.ddf_value; });
  const out = {maps: {}, viewInvariants: d.viewInvariants || null, viewMode: d.viewMode, pie: result.pie,
    listed, ddf, unpaid: Object.fromEntries(Object.entries(result.sources).map(([k, src]) =>
      [k, (src.unfundedGroups || []).reduce((t, g) => t + g.amount, 0)]))};
  maps.forEach((m, k) => { out.maps[k] = Object.fromEntries([...m.entries()]); });
  return out;
}"""
def _chromium(playwright):
    import os
    import shutil
    from pathlib import Path
    for candidate in (os.environ.get("CHROMIUM_PATH"), playwright.chromium.executable_path,
                      CHROME, shutil.which("chromium")):
        if candidate and Path(candidate).exists():
            return candidate
    return None


def _serve(body):
    def handler(route):
        route.fulfill(status=200, content_type="text/javascript", body=body)
    return handler


def _label(scoring, teams, roster, share):
    return f"{scoring}/{teams}" + ("/custom" if roster else "") + (f"/bench{share}pct" if share is not None else "")


def _sweep(settings, overrides=None, views=("indexed", "vorp", "adj")):
    """{label: {view: READ result}} for each setting."""
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        raise _render_env.unavailable(f"Playwright is not available: {exc}") from exc
    out, errors = {}, []
    with _server() as url, sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(args=_render_env.HERMETIC_ARGS, executable_path=_chromium(playwright))
        except PlaywrightError as exc:
            raise _render_env.unavailable(f"Chromium is not available: {exc}") from exc
        try:
            for scoring, teams, roster, share in settings:
                page = browser.new_page()
                page.on("pageerror", lambda e: errors.append(str(e)))
                for pattern, body in (overrides or {}).items():
                    page.route(pattern, _serve(body))
                page.goto(url, wait_until="networkidle")
                try:
                    page.wait_for_function("() => window.TradeValueCurveHarness && window.TradeValueCurveDiagnostics",
                                           timeout=30000)
                except PlaywrightError:
                    status = page.evaluate("() => document.querySelector('#curve-status')?.textContent || ''")
                    errors.append(f"{_label(scoring, teams, roster, share)}: chart never finished ({status[:160]})")
                    page.close()
                    continue
                page.evaluate("([s, t]) => { const c = window.TradeValueCurveControls; c.setScoring(s); c.setTeams(t); }",
                              [scoring, teams])
                for key, value in (roster or {}).items():
                    page.evaluate("""([k, v]) => { const i = document.querySelector(`[data-roster-key="${k}"]`);
                                      i.value = v; i.dispatchEvent(new Event('change')); }""", [key, value])
                if share is not None:
                    page.evaluate("(s) => window.TradeValueCurveControls.setBenchShare(s)", share)
                label = _label(scoring, teams, roster, share)
                out[label] = {}
                for view in views:
                    page.locator(f'#viewModeTabs [data-view-mode="{view}"]').click()
                    out[label][view] = page.evaluate(READ)
                page.close()
        finally:
            browser.close()
    out["_errors"] = errors
    return out


PROJECTIONS = ("espn", "cbsros", "razzball")


def starting_slots(roster):
    shape = {"QB": 1, "RB": 2, "WR": 3, "TE": 1, "FLEX": 1, **(roster or {})}
    return shape["QB"] + shape["RB"] + shape["WR"] + shape["TE"] + shape["FLEX"]


def verify(swept):
    """(problems, measured): each tab's invariant recomputed from the plotted
    maps, the rows and the page's pipeline result."""
    problems, measured = [], {}
    problems += [f"page error: {e[:200]}" for e in swept.get("_errors", [])]
    for label, views in swept.items():
        if label.startswith("_"):
            continue
        parts = label.split("/")
        teams = int(parts[1])
        roster = CUSTOM_ROSTER if "custom" in parts else None
        pie = 28 * teams * starting_slots(roster)
        for view, res in views.items():
            maps = {k: {int(pk): v for pk, v in m.items()} for k, m in res["maps"].items()}
            vi = res["viewInvariants"]
            if not vi or vi.get("gatedHold") is not True:
                problems.append(f"{label} [{view} tab]: page viewInvariants do not hold")
            if abs(res["pie"] - pie) > 1e-9:
                problems.append(f"{label}: page pie {res['pie']}, want {pie}")

            def total_is_pie(name, values, unpaid=0.0):
                total = sum(values.values())
                measured[(label, view, name)] = round(total, 6)
                if abs(total - (pie - unpaid)) > REL_TOL * pie:
                    problems.append(f"{label} {view} {name}: total {total:.6f}, pie {pie} (unpaid {unpaid})")

            if view == "vorp":
                for key in PUBLISHED + RAW_VORP:
                    if maps.get(key):
                        total_is_pie(key, maps[key])
            elif view == "adj":
                for key in PUBLISHED + PROJECTIONS:
                    if maps.get(key):
                        total_is_pie(key, maps[key], res["unpaid"].get(key, 0.0))
            elif view == "indexed":
                for key in PUBLISHED:
                    values = maps.get(key)
                    if not values:
                        continue
                    shared = [k for k in res["listed"][key]
                              if isinstance(res["ddf"].get(str(k), res["ddf"].get(k)), (int, float))]
                    ddf_total = sum(res["ddf"].get(str(k), res["ddf"].get(k)) for k in shared)
                    idx_total = sum(values[k] for k in shared)
                    measured[(label, view, key)] = round(idx_total, 6)
                    if abs(idx_total - ddf_total) > REL_TOL * max(1.0, ddf_total):
                        problems.append(f"{label} indexed {key}: total {idx_total:.6f} vs DDF {ddf_total:.6f}")
    return problems, measured


def _widget():
    return (APP / "assets" / "curve-widget.js").read_text(encoding="utf-8")


class ViewInvariants(unittest.TestCase):
    def test_every_view_holds_its_invariant(self):
        swept = _sweep(SETTINGS)
        problems, measured = verify(swept)
        print(f"\n[views-audit/2] settings={len(SETTINGS)} checks={len(measured)} problems={len(problems)}")
        self.assertGreaterEqual(len(measured), len(SETTINGS) * (len(PUBLISHED) * 3 + len(RAW_VORP) + len(PROJECTIONS)))
        self.assertEqual(problems, [], "\n".join(problems[:25]))

    def test_guard_fails_on_broken_engines(self):
        from tests.test_published_league_settings_render import APP as _APP
        model = (_APP / "assets" / "value-model.js").read_text(encoding="utf-8")
        broken = {
            # VORP vs waivers left as raw value above waivers (no pie factor).
            "vorp-unscaled": model.replace("r.vorpDisplay = r.vorp * vorpFactor;", "r.vorpDisplay = r.vorp;"),
            # The starter slice paid at the bench rate.
            "starter-at-bench-rate": model.replace(
                '+ rates[vpGroupKey(r.pos, "starter")] * r.starterSlice;',
                '+ rates[vpGroupKey(r.pos, "bench")] * r.starterSlice;'),
        }
        settings = [("ppr", 12, None, None), ("standard", 10, None, None)]
        for name, body in broken.items():
            self.assertNotEqual(body, model, f"mutation anchor for {name} moved")
            problems, _ = verify(_sweep(settings, {"**/assets/value-model.js*": body}))
            print(f"\n[views-audit negative test] {name}: {len(problems)} problems, e.g. {problems[:1]}")
            self.assertGreater(len(problems), 0, f"broken engine {name} was NOT caught")


if __name__ == "__main__":
    unittest.main()
