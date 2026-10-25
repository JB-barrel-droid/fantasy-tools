"""GAP-ESPN-BELOW-LEG: a projected player is never "—" on a projection leg.

Jeremy (2026-10-07): a player ESPN projects above 0 but below its waiver line is
worth 0.0 on our value, not "—", so a chart that still pays for him is a sell
target with gap = chart value. The same holds for the CBS ROS and Razzball legs.
Players with no projection in the source stay "—".

JEG-608 (2026-10-12): the rule is kept, the mechanism changed. It used to be a
display patch (buildLegFloors / rowValue zeroed a missing player projected at
or below the lowest priced projection at his position). JEG-508 (#491) made
every projected player a priced native (currentNatives), so a below-line player
is priced at 0 by the pipeline and is never missing; the patch was deleted.
The test no longer reads the engine's own maps for its expectation. It checks
from the page's #players-data projections, independent of the code:
  * every combo of 12-team and 8-team PPR: for espn / cbsros / razzball, a
    player with a per-game projection at the scoring shows a number (>= 0), a
    player without one shows nothing (ESPN-0 "ineligible" players show 0);
  * Darren Waller (12-team PPR): engine ESPN 0.0, and on v2 Trade targets
    (ESPN as our value) ours 0.0 and gap = chart value for every compared
    chart that pays for him; he is a sell row exactly when the consensus rule
    holds (JEG-677: 2+ charts, median above 0, most charts paying for him).
Discrimination: test_guard_fails_on_broken_builds serves a build that drops
low-projection players from the legs' natives (the old "missing below the
line" state), and one that drops every CBS ROS quarterback.

The main comparison table is not checked: its ESPN column reads the built
fixture leg, which already carries 0 for these players.
"""
from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

from tests.test_published_league_settings_render import _chromium_executable  # noqa: E402
from tests.test_v2_targets_render import DIST, _built_dist  # noqa: E402
from tests import _render_env  # noqa: E402


def setUpModule():
    # Build app/ and dist/ from the committed fixtures first, so the
    # test never reads a stale committed build (GAP-APP-ASSETS-LAG).
    _render_env.ensure_built()


ROOT = Path(__file__).resolve().parents[1]
WIDGET_JS = ROOT / "app" / "trade-value-chart" / "assets" / "curve-widget.js"
LEGS = {"espn": "espn_ppg", "cbsros": "cbsros_ppg", "razzball": "rz_ppg"}
CHARTS = ("usatoday", "fantasycalc", "fantasypros", "cbs")
PROBE = "Darren Waller"
SETTINGS = (("ppr", 12), ("ppr", 8))

WIDGET_RULE = "if (ppg !== null && Number.isFinite(floor) && ppg <= floor) return 0;"
# Mutations of the pipeline's natives (currentNatives in curve-widget.js).
NATIVE_RULE = "if (Number.isFinite(ppg)) values.set(playerKey, ppg);"


def players():
    html = (DIST / "index.html").read_text(encoding="utf-8")
    match = re.search(r'<script id="players-data" type="application/json">(.*?)</script>', html, re.S)
    return {p["player_key"]: p for p in json.loads(match.group(1))["players"]}


def expected(rows, field_scoring, by_key):
    """{(player_key, leg): True if the leg must show a number, else False},
    from the page's own projections (never from the engine's maps)."""
    out = {}
    for row in rows:
        p = by_key.get(row["player_key"]) or {}
        for leg, field in LEGS.items():
            ppg = (p.get(field) or {}).get(field_scoring)
            projected = isinstance(ppg, (int, float))
            out[(row["player_key"], leg)] = projected or (leg == "espn" and bool(row.get("espnProjectsZero")))
    return out


def collect(overrides=None):
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        raise _render_env.unavailable(f"Playwright is not available: {exc}") from exc
    out = {"settings": {}}
    with _built_dist() as v2_url, sync_playwright() as playwright:
        base = v2_url.split("/v2/")[0]
        try:
            browser = playwright.chromium.launch(args=_render_env.HERMETIC_ARGS, executable_path=_chromium_executable(playwright))
        except PlaywrightError as exc:
            raise _render_env.unavailable(f"Chromium is not available: {exc}") from exc
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

            page, errors = open_page(f"{base}/classic/")
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
            # JEG-677: DDF Value is the default Our value; this check is about ESPN, so pick it.
            page.select_option("#v2TOurs", "espn")
            page.click("#v2Targets [data-side=sell]")
            out["targets"] = page.evaluate("""(name) => {
              const t = window.TradeValueV2.targets();
              const hit = t.players.find(p => p.row.name === name);
              return {ours: t.ours, used: t.used, listed: Boolean(t.sell.find(p => p.row.name === name)),
                belowSellFloor: t.belowSellFloor, leftOut: t.leftOut, probe: hit ? {ours: hit.ours,
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


def consensus_listed(values) -> bool:
    """JEG-677 Check 1 for a player whose our value is 0 (ESPN 0): 2+ priced charts, a consensus (median) above 0,
    and a strict majority of the charts paying above 0. A chart at its waiver line counts as pricing him at 0."""
    priced = sorted(v for v in values if isinstance(v, (int, float)))
    if len(priced) < 2:
        return False
    mid = len(priced) // 2
    consensus = priced[mid] if len(priced) % 2 else (priced[mid - 1] + priced[mid]) / 2
    return consensus > 0 and sum(1 for v in priced if v > 0) * 2 > len(priced)


def check(out) -> list[str]:
    errors = []
    by_key = players()
    for setting, data in out["settings"].items():
        scoring = setting.rsplit("_", 1)[0]
        want = expected(data["rows"], scoring, by_key)
        rows = {r["player_key"]: r for r in data["rows"]}
        bad = []
        for (key, leg), shown in want.items():
            value = rows[key]["values"][leg]
            if shown != (isinstance(value, (int, float)) and value >= 0):
                bad.append((rows[key]["name"], leg, value, "number" if shown else "nothing"))
        if bad:
            errors.append(f"{setting}: {len(bad)} cells differ from the projection rule, e.g. {bad[:3]} (name, leg, got, want)")
        if not any(want.values()):
            errors.append(f"{setting}: no projected player in the data (nothing to test)")
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
        errors.append(f"Trade targets: {PROBE} (paid {paid}) is not compared at all")
    else:
        used_values = [hit["cells"][c]["value"] for c in out["targets"]["used"] if c in hit["cells"]]
        # JEG-820 (Sell floor, ours >= 5) and JEG-842 (an ESPN-0 "out" player is never recommended) superseded
        # the JEG-677 listing: he still passes the market consensus (so the exclusion is exercised), is never
        # in the Sell list, and the page counts him among the players it left out.
        if not consensus_listed(used_values):
            errors.append(f"Trade targets: {PROBE} does not pass the market consensus on {used_values} (the exclusion went untested)")
        if out["targets"]["listed"]:
            errors.append(f"Trade targets: {PROBE} (ours 0, ESPN out) is in the Sell list: below the Sell floor and never recommended")
        if (out["targets"].get("belowSellFloor") or 0) + (out["targets"].get("leftOut") or 0) < 1:
            errors.append("Trade targets: the page does not count the ESPN-0 player it leaves out")
        if hit["ours"] != 0:
            errors.append(f"Trade targets: {PROBE} ours {hit['ours']!r}, expected 0")
        for chart, value in paid.items():
            if hit["cells"].get(chart, {}).get("gap") != value:
                errors.append(f"Trade targets: {PROBE} {chart} gap {hit['cells'].get(chart)}, expected {value}")
        if out["targets_row"]:
            errors.append(f"Trade targets: {PROBE} is rendered in the Sell table: {out['targets_row']}")
    if out["main_errors"] or out["v2_errors"]:
        errors.append(f"page errors: {out['main_errors'] + out['v2_errors']}")
    return errors


class BelowLegZeroRenderTest(unittest.TestCase):
    def test_below_leg_players_are_zero_missing_stay_missing(self):
        out = collect()
        self.assertEqual(check(out), [])

    def test_guard_fails_on_broken_builds(self):
        widget = WIDGET_JS.read_text(encoding="utf-8")
        self.assertEqual(widget.count(NATIVE_RULE), 1, "mutation anchor is stale")
        mutations = {
            # The pre-JEG-508 state: a player projected below the line is missing.
            "below-line players missing": widget.replace(
                NATIVE_RULE, "if (Number.isFinite(ppg) && ppg > 3) values.set(playerKey, ppg);", 1),
            # A leg that prices no quarterbacks (the old CBS ROS 8-team state).
            "CBS ROS prices no QB": widget.replace(
                NATIVE_RULE, 'if (Number.isFinite(ppg) && !(key === "cbsros" && player.pos === "QB")) '
                             "values.set(playerKey, ppg);", 1),
        }
        overrides = {name: {"**/assets/curve-widget.js*": body} for name, body in mutations.items()}
        # JEG-820/JEG-842: Trade targets before the Sell floor and the out-player exclusion listed ESPN-0 players.
        targets_js = (ROOT / "app" / "v2" / "targets.js").read_text(encoding="utf-8")
        self.assertIn("const SELL_FLOOR = 5;", targets_js, "mutation anchor for the Sell floor is stale")
        self.assertIn('if (row.espnProjectsZero) return "out";', targets_js, "mutation anchor for the out rule is stale")
        overrides["Trade targets list the ESPN-0 player"] = {"**/targets.js*": targets_js.replace(
            "const SELL_FLOOR = 5;", "const SELL_FLOOR = 0;", 1).replace('if (row.espnProjectsZero) return "out";', "", 1)}
        # Control: the unmodified widget through the same override path passes.
        self.assertEqual(check(collect({"**/assets/curve-widget.js*": widget})), [],
                         "unmodified widget fails the render checks")
        for name, override in overrides.items():
            with self.subTest(mutation=name):
                self.assertNotEqual(check(collect(override)), [], f"render checks did not catch: {name}")


if __name__ == "__main__":
    unittest.main()
