"""GAP-ESPN-BELOW-LEG: a projected player below a leg's pricing line is 0.0, not —.

Jeremy (2026-10-07): a player ESPN projects above 0 but below its waiver line is
worth 0.0 on our value, like the injured/out case (GAP-025), so a chart that
still pays for him is a sell target with gap = chart value. The same rule holds
for the CBS ROS and Razzball legs. Players with no row in the source stay —.

"Below the leg" is checked here independently of the code under test: from the
engine's raw source maps (TradeValueCurveHarness.sourceMaps, which this rule
must not touch) and the page's own #players-data projections, a player missing
from a leg is expected at 0 only when his per-game projection is at or below
the lowest projection the leg prices at his position. Above that line, or at a
position the leg prices no one (CBS ROS quarterbacks at 8 teams), he must stay
missing: zeroing there would invent a value.

Headless against a temp copy of the built dist/ (dist/v2 rebuilt from app/v2):
  * every combo of 12-team and 8-team PPR: getRows() matches the expectation
    for espn / cbsros / razzball on every row;
  * Darren Waller (12-team PPR): engine ESPN 0.0, and on v2 Trade targets
    (ESPN as our value) a sell row with ours 0.0 and gap = chart value for
    every compared chart that pays for him;
  * CBS ROS quarterbacks at 8 teams stay missing.
Discrimination: test_guard_fails_on_broken_builds serves the origin/main rule
(below-leg players missing), a rule that zeroes every projected player missing
from a leg (no floor).

The main comparison table is not checked: its ESPN column reads the built
fixture leg, which already carries 0 for these players (299 zeros at the
default setting), so the rule is not needed there.
"""
from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

from tests.test_published_league_settings_render import _chromium_executable  # noqa: E402
from tests.test_v2_targets_render import DIST, _built_dist  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
WIDGET_JS = ROOT / "app" / "trade-value-chart" / "assets" / "curve-widget.js"
LEGS = {"espn": "espn_ppg", "cbsros": "cbsros_ppg", "razzball": "rz_ppg"}
CHARTS = ("usatoday", "fantasycalc", "fantasypros", "cbs")
PROBE = "Darren Waller"
SETTINGS = (("ppr", 12), ("ppr", 8))

WIDGET_RULE = "if (ppg !== null && Number.isFinite(floor) && ppg <= floor) return 0;"


def players():
    html = (DIST / "index.html").read_text(encoding="utf-8")
    match = re.search(r'<script id="players-data" type="application/json">(.*?)</script>', html, re.S)
    return {p["player_key"]: p for p in json.loads(match.group(1))["players"]}


def expected(rows, maps, field_scoring, by_key):
    """{(player_key, leg): expected value or None} for players missing from a leg."""
    out = {}
    for leg, field in LEGS.items():
        legmap = {int(k): v for k, v in maps.get(leg, {}).items()}
        if not legmap:
            continue
        floors = {}
        for key in legmap:
            p = by_key.get(key) or {}
            ppg = (p.get(field) or {}).get(field_scoring)
            if isinstance(ppg, (int, float)):
                floors[p["pos"]] = min(floors.get(p["pos"], float("inf")), ppg)
        for row in rows:
            key = row["player_key"]
            if key in legmap:
                out[(key, leg)] = legmap[key]
                continue
            p = by_key.get(key) or {}
            ppg = (p.get(field) or {}).get(field_scoring)
            if leg == "espn" and row.get("espnProjectsZero"):
                out[(key, leg)] = 0  # GAP-025, covered by test_espn_zero_badge_render
            elif isinstance(ppg, (int, float)) and p.get("pos") in floors and ppg <= floors[p["pos"]]:
                out[(key, leg)] = 0
            else:
                out[(key, leg)] = None
    return out


def collect(overrides=None):
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        raise unittest.SkipTest(f"Playwright is not available: {exc}") from exc
    out = {"settings": {}}
    with _built_dist() as v2_url, sync_playwright() as playwright:
        base = v2_url.split("/v2/")[0]
        try:
            browser = playwright.chromium.launch(executable_path=_chromium_executable(playwright))
        except PlaywrightError as exc:
            raise unittest.SkipTest(f"Chromium is not available: {exc}") from exc
        try:
            def open_page(url):
                page = browser.new_page(viewport={"width": 1440, "height": 1000})
                errors = []
                page.on("pageerror", lambda e: errors.append(str(e)))
                page.route(lambda u: not u.startswith("http://127.0.0.1"), lambda route: route.abort())
                for pattern, body in (overrides or {}).items():
                    page.route(pattern, (lambda b: lambda route: route.fulfill(
                        status=200, content_type="text/javascript", body=b))(body))
                page.goto(url, wait_until="networkidle")
                page.wait_for_function("() => window.TradeValueCurveControls && window.TradeValueCurveHarness"
                                       " && window.TradeValueCurveControls.getRows().length > 0", timeout=30000)
                return page, errors

            page, errors = open_page(f"{base}/index.html")
            for scoring, teams in SETTINGS:
                page.evaluate("([s, t]) => { const c = window.TradeValueCurveControls; c.setScoring(s); c.setTeams(t); }",
                              [scoring, teams])
                out["settings"][f"{scoring}_{teams}"] = page.evaluate("""() => {
                  const maps = {};
                  window.TradeValueCurveHarness.sourceMaps().forEach((v, k) => {
                    if (['espn', 'cbsros', 'razzball'].includes(k)) maps[k] = Object.fromEntries(v);
                  });
                  return {maps, rows: window.TradeValueCurveControls.getRows().map(r => ({
                    player_key: r.player_key, name: r.name, espnProjectsZero: r.espnProjectsZero,
                    values: {espn: r.values.espn, cbsros: r.values.cbsros, razzball: r.values.razzball,
                             usatoday: r.values.usatoday, fantasycalc: r.values.fantasycalc,
                             fantasypros: r.values.fantasypros, cbs: r.values.cbs}}))};
                }""")
            page.evaluate("() => { const c = window.TradeValueCurveControls; c.setScoring('ppr'); c.setTeams(12); }")
            out["main_errors"] = list(errors)
            page.close()

            page, errors = open_page(f"{base}/v2/")
            page.evaluate("() => { location.hash = '#trade-targets'; }")
            page.wait_for_function("() => window.TradeValueV2 && window.TradeValueV2.targets()", timeout=30000)
            page.click("#v2Targets [data-side=sell]")
            out["targets"] = page.evaluate("""(name) => {
              const t = window.TradeValueV2.targets();
              const hit = t.sell.find(p => p.row.name === name);
              return {ours: t.ours, used: t.used, probe: hit ? {ours: hit.ours,
                cells: Object.fromEntries(Object.entries(hit.cells).map(([c, v]) => [c, {value: v.value, gap: v.gap}]))} : null};
            }""", PROBE)
            page.fill("#v2TSearch", PROBE)
            page.wait_for_timeout(400)
            out["targets_row"] = page.evaluate("""() => {
              const tr = document.querySelector('#v2TTable tbody tr');
              return tr ? {ours: tr.querySelector('[data-ours]').textContent} : null;
            }""")
            out["v2_errors"] = list(errors)
            page.close()
        finally:
            browser.close()
    return out


def check(out) -> list[str]:
    errors = []
    by_key = players()
    for setting, data in out["settings"].items():
        scoring = setting.rsplit("_", 1)[0]
        want = expected(data["rows"], data["maps"], scoring, by_key)
        rows = {r["player_key"]: r for r in data["rows"]}
        bad = [(rows[k]["name"], leg, rows[k]["values"][leg], v) for (k, leg), v in want.items()
               if rows[k]["values"][leg] != v]
        if bad:
            errors.append(f"{setting}: {len(bad)} cells differ from the below-leg rule, e.g. {bad[:3]} (name, leg, got, want)")
        zeros = sum(1 for (k, leg), v in want.items() if v == 0 and k not in {int(x) for x in data["maps"].get(leg, {})}
                    and not (leg == "espn" and rows[k].get("espnProjectsZero")))
        if not zeros:
            errors.append(f"{setting}: no below-leg player in the data (nothing to test)")
    eight = out["settings"].get("ppr_8")
    if eight:
        qbs = [r for r in eight["rows"] if (by_key.get(r["player_key"]) or {}).get("pos") == "QB"
               and isinstance(((by_key.get(r["player_key"]) or {}).get("cbsros_ppg") or {}).get("ppr"), (int, float))]
        if not any(int(k) in {q["player_key"] for q in qbs} for k in eight["maps"].get("cbsros", {})):
            zeroed = [q["name"] for q in qbs if q["values"]["cbsros"] is not None]
            if zeroed:
                errors.append(f"ppr_8: CBS ROS prices no QB, yet QBs show a CBS ROS value: {zeroed[:3]}")
    probe = next((r for r in out["settings"]["ppr_12"]["rows"] if r["name"] == PROBE), None)
    if not probe:
        errors.append(f"{PROBE} is not an engine row at 12-team PPR")
        return errors
    if probe["values"]["espn"] != 0:
        errors.append(f"{PROBE}: engine ESPN {probe['values']['espn']!r}, expected 0")
    paid = {c: probe["values"][c] for c in CHARTS
            if isinstance(probe["values"][c], (int, float)) and probe["values"][c] > 0 and c in out["targets"]["used"]}
    if not paid:
        errors.append(f"{PROBE}: no compared chart pays for him (nothing to test)")
    hit = out["targets"]["probe"]
    if not hit:
        errors.append(f"Trade targets: {PROBE} (paid {paid}) is not in the sell list")
    else:
        if hit["ours"] != 0:
            errors.append(f"Trade targets: {PROBE} ours {hit['ours']!r}, expected 0")
        for chart, value in paid.items():
            if hit["cells"].get(chart, {}).get("gap") != value:
                errors.append(f"Trade targets: {PROBE} {chart} gap {hit['cells'].get(chart)}, expected {value}")
        if (out["targets_row"] or {}).get("ours") != "0.0":
            errors.append(f"Trade targets: rendered row for {PROBE} shows {out['targets_row']}")
    if out["main_errors"] or out["v2_errors"]:
        errors.append(f"page errors: {out['main_errors'] + out['v2_errors']}")
    return errors


class BelowLegZeroRenderTest(unittest.TestCase):
    def test_below_leg_players_are_zero_missing_stay_missing(self):
        out = collect()
        self.assertEqual(check(out), [])

    def test_guard_fails_on_broken_builds(self):
        widget = WIDGET_JS.read_text(encoding="utf-8")
        mutations = {
            # origin/main before this change: below-leg players are missing.
            "below-leg missing in the engine": {"**/assets/curve-widget.js*": widget.replace(WIDGET_RULE, "", 1)},
            # Zero every projected player missing from a leg, floor ignored.
            "no floor (zero any projected player)": {"**/assets/curve-widget.js*": widget.replace(
                WIDGET_RULE, "if (ppg !== null) return 0;", 1)},
        }
        for name, overrides in mutations.items():
            with self.subTest(mutation=name):
                body = next(iter(overrides.values()))
                self.assertNotEqual(body, widget, f"mutation anchor for {name!r} is stale")
                self.assertNotEqual(check(collect(overrides)), [], f"render checks did not catch: {name}")


if __name__ == "__main__":
    unittest.main()
