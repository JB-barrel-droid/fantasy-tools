"""Chart views measured against Jeremy's invariants (views-audit, 2026-10-08).

Jeremy, 2026-10-08:
  * Indexed: "the positions and bench/starter have different weights but the
    total pies are the same."
  * VORP vs waivers: "the differences in deconstructed values of each player
    on the same exact scale."
  * Adjusted values: "the differences in value of each player, when their
    positional and bench/starter weights have been normalized."

Every total on one basis: the players a source and the ESPN anchor both price
(QB/RB/WR/TE). Read live from the real page (window.TradeValueCurveHarness.
sourceMaps) at the 3 scorings x 8/10/12/14 teams, a custom roster, and bench
shares of 30% and 5%, in all three tabs, plus the page's own
TradeValueCurveDiagnostics.viewInvariants (informational).

GATED (wrong-number guards for what already holds; Jeremy 2026-10-08: no
math changes before the coordinated review):
  * Indexed: CBS ROS, Razzball, every *_adjusted series and every raw
    value-above-waivers series total exactly the anchor's total;
  * VORP vs waivers: the raw ESPN / CBS ROS / Razzball series total exactly
    the anchor's total;
  * the page's viewInvariants agrees with this independent recomputation.
MEASURED, NOT GATED (docs/math-review-agenda.md "From views-audit"): the four
published charts in every tab (Indexed totals 0.66-1.82x the anchor's on
Week 5; VORP vs waivers 0.71-1.00x; Adjusted group totals proportional to the
DDF weights at derived settings, level 0.79-0.96x, not at the saved setup).

Discrimination (test_guard_fails_on_broken_engines): broken engines -- CBS
ROS / Razzball without their total factor, the raw series without theirs --
must fail.

"""
from __future__ import annotations

import json
import unittest

from tests.test_published_league_settings_engine import (
    POSITIONS, browser_players,
)
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
  const maps = window.TradeValueCurveHarness.sourceMaps();
  const d = window.TradeValueCurveDiagnostics || {};
  const out = {maps: {}, viewInvariants: d.viewInvariants || null, viewMode: d.viewMode};
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


def shared_totals(values, anchor, pos_of):
    keys = [k for k in values if pos_of.get(k) in POSITIONS and k in anchor]
    return len(keys), sum(max(0.0, values[k]) for k in keys), sum(max(0.0, anchor[k]) for k in keys)


GATED_INDEXED = ("cbsros", "razzball", "fantasycalc_adjusted", "usatoday_adjusted",
                 "fantasypros_adjusted", "cbs_adjusted") + RAW_VORP


def verify(swept):
    """(problems, measured): gated invariants recomputed from the plotted maps;
    `measured` holds every source's numbers, gated or not."""
    pos_of = browser_players()
    problems, measured = [], {}
    problems += [f"page error: {e[:200]}" for e in swept.get("_errors", [])]
    for label, views in swept.items():
        if label.startswith("_"):
            continue
        parts = label.split("/")
        for view, res in views.items():
            maps = {k: {int(pk): v for pk, v in m.items()} for k, m in res["maps"].items()}
            anchor = maps["espn"]
            vi = res["viewInvariants"]
            if not vi or vi.get("gatedHold") is not True:
                problems.append(f"{label} [{view} tab]: page viewInvariants gated rows do not hold")

            def ratio(values):
                n, total, target = shared_totals(values, anchor, pos_of)
                return n, (total / target if target else float("nan"))

            def gate(name, values):
                n, r = ratio(values)
                measured[(label, view, name)] = round(r, 6)
                if n < MIN_SHARED or abs(r - 1) > REL_TOL:
                    problems.append(f"{label} {view} {name}: shared total ratio {r:.6f} (n={n})")

            if view == "indexed":
                for key in GATED_INDEXED:
                    if maps.get(key):
                        gate(key, maps[key])
                for key in PUBLISHED:
                    if maps.get(key):
                        measured[(label, view, key)] = round(ratio(maps[key])[1], 6)
                        page = vi["indexed"]["sources"].get(key, {})
                        if abs(page.get("ratio", 0) - measured[(label, view, key)]) > 1e-5:
                            problems.append(f"{label} indexed {key}: page ratio {page.get('ratio')} "
                                            f"!= recomputed {measured[(label, view, key)]}")
            elif view == "vorp":
                for key in RAW_VORP:
                    if maps.get(key):
                        gate(key, maps[key])
                for key in PUBLISHED:
                    if maps.get(key):
                        measured[(label, view, key)] = round(ratio(maps[key])[1], 6)
            elif view == "adj":
                for key in PUBLISHED:
                    row = vi["adjusted"]["sources"].get(key)
                    if row:
                        measured[(label, view, key)] = (row["spread"], row["level"], row["mode"])
    return problems, measured


def _widget():
    return (APP / "assets" / "curve-widget.js").read_text(encoding="utf-8")


class ViewInvariants(unittest.TestCase):
    def test_every_view_holds_its_invariant(self):
        swept = _sweep(SETTINGS)
        problems, measured = verify(swept)
        gated = sum(1 for k in measured if k[2] in GATED_INDEXED)
        print(f"\n[views-audit] settings={len(SETTINGS)} gated checks={gated} problems={len(problems)}")
        for key in PUBLISHED:
            for view in ("indexed", "vorp"):
                vals = [v for k, v in measured.items() if k[1] == view and k[2] == key]
                if vals:
                    print(f"  measured {view:7s} {key:12s} shared-total ratio {min(vals):.3f}-{max(vals):.3f}")
            adj = [v for k, v in measured.items() if k[1] == "adj" and k[2] == key]
            if adj:
                print(f"  measured adj     {key:12s} group spread {min(a[0] for a in adj):.3f}-{max(a[0] for a in adj):.3f}"
                      f" level {min(a[1] for a in adj):.3f}-{max(a[1] for a in adj):.3f}")
        self.assertGreaterEqual(gated, len(SETTINGS) * len(GATED_INDEXED))
        self.assertEqual(problems, [], "\n".join(problems[:25]))

    def test_guard_fails_on_broken_engines(self):
        widget = _widget()
        # Off by 0.05% -- about 1 point on a ~2,200 pie, inside the page's own
        # fixedPieIndexed tolerance (2 points), so only this gate sees it.
        broken = {
            "projection-total-off": widget.replace(
                "    if (PROJECTION_TOTAL_ONLY_KEYS.has(key)) {\n      return ValueModel.scaleToSharedTotal({\n        values,\n        anchor: anchorMap,",
                "    if (PROJECTION_TOTAL_ONLY_KEYS.has(key)) {\n      return ValueModel.scaleToSharedTotal({\n        values,\n        anchor: new Map([...anchorMap].map(([k, v]) => [k, v * 1.0005])),"),
            "raw-series-off": widget.replace(
                "      sourceMaps.set(vorpKey, ValueModel.scaleToSharedTotal({\n        values: buildVorpMap(vorpKey),\n        anchor: anchorMap,",
                "      sourceMaps.set(vorpKey, ValueModel.scaleToSharedTotal({\n        values: buildVorpMap(vorpKey),\n        anchor: new Map([...anchorMap].map(([k, v]) => [k, v * 1.0005])),"),
        }
        settings = [("ppr", 12, None, None), ("standard", 10, None, None)]
        for name, body in broken.items():
            self.assertNotEqual(body, widget, f"mutation anchor for {name} moved")
            problems, _ = verify(_sweep(settings, {"**/assets/curve-widget.js*": body}))
            print(f"\n[views-audit negative test] {name}: {len(problems)} problems, e.g. {problems[:1]}")
            self.assertGreater(len(problems), 0, f"broken engine {name} was NOT caught")


if __name__ == "__main__":
    unittest.main()
