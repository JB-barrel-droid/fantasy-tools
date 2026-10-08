"""GAP-025: players ESPN projects at 0 carry a badge and an ESPN value of 0.0.

Jeremy's decisions (2026-10-07): show each publisher's value as published and
add a badge saying ESPN projects 0 for the player (injured/out); and ("Yes, use
0") our ESPN value for such a player is 0.0, not missing, so a chart that still
pays for him is an ordinary sell target with gap = chart value. A player ESPN
has no row for is missing, not 0: no badge, and his ESPN value stays — .

Expected sets come from the built page's own #players-data island, read here in
Python, not from the code under test:

  * ESPN 0: espn_status "ineligible" (ESPN lists the player with a zero
    projection), or an ESPN row whose per-game projection is 0 in every scoring;
  * no ESPN row: espn_status "absent".

Headless against a temp copy of the built dist/ (with dist/v2 rebuilt from
app/v2), for a real ESPN-0 player a published chart still pays for, and a real
no-ESPN-row player, it checks:

  * engine rows (getRows): every ESPN-0 row has espn = espn_vorp = 0, every
    no-ESPN-row player has espn = null;
  * main page: the comparison table row (badge, ESPN column 0.0 or —) and the
    chart tooltip;
  * /v2/: the Player values table row and the player drawer; Trade targets
    (sell side, ESPN as our value) lists every ESPN-0 player a compared chart
    pays for, with our value 0.0 and each chart's gap equal to its value, and
    never lists a no-ESPN-row player; the retired separate ESPN-0 list is gone;
  * the badge has a text label and a symbol, not color alone.

Discrimination: test_guard_fails_on_broken_builds serves an engine without the
0.0 rule (the previous behaviour: ESPN-0 = missing), one without the badge flag,
and one that reads "no ESPN row" as 0, and requires the checks to fail on each.
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
PRODUCT_DATA_JS = ROOT / "app" / "trade-value-chart" / "assets" / "product-data.js"
CURVE_WIDGET_JS = ROOT / "app" / "trade-value-chart" / "assets" / "curve-widget.js"
CHARTS = ("usatoday", "fantasycalc", "fantasypros", "cbs")
LABEL = "ESPN: 0 (out)"
SYMBOL = "⊘"


def expected_sets():
    html = (DIST / "index.html").read_text(encoding="utf-8")
    match = re.search(r'<script id="players-data" type="application/json">(.*?)</script>', html, re.S)
    players = json.loads(match.group(1))["players"]
    zero, absent = set(), set()
    for player in players:
        status = player.get("espn_status")
        ppg = player.get("espn_ppg")
        if status == "absent":
            absent.add(player["player_key"])
        elif status == "ineligible" or (isinstance(ppg, dict) and ppg and all(v == 0 for v in ppg.values())):
            zero.add(player["player_key"])
    return zero, absent


FIND_TOOLTIP = """async (key) => {
  const rows = window.TradeValueCurveControls.getRows();
  const rank = rows.findIndex(r => r.player_key === key) + 1;
  if (!rank) return null;
  const canvas = document.getElementById('chart');
  canvas.focus();
  const press = k => canvas.dispatchEvent(new KeyboardEvent('keydown', {key: k, bubbles: true}));
  press('Home');
  for (let i = 1; i < rank; i++) press('ArrowRight');
  const tip = document.getElementById('tip');
  return {name: tip.querySelector('strong')?.textContent || '', badge: tip.querySelector('[data-espn-zero]')?.textContent || null};
}"""

def badge_ok(text):
    return bool(text) and LABEL in text and SYMBOL in text


def collect(overrides=None):
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        raise _render_env.unavailable(f"Playwright is not available: {exc}") from exc
    zero, absent = expected_sets()
    out = {"zero_expected": sorted(zero), "absent_expected": sorted(absent)}
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
                def serve(body):
                    return lambda route: route.fulfill(status=200, content_type="text/javascript", body=body)
                for pattern, body in (overrides or {}).items():
                    page.route(pattern, serve(body))
                page.goto(url, wait_until="networkidle")
                page.wait_for_function("() => window.TradeValueCurveControls && window.TradeValueCurveControls.getRows().length > 0", timeout=30000)
                return page, errors

            # ---- main page ----
            page, errors = open_page(f"{base}/classic/")
            rows = page.evaluate("() => window.TradeValueCurveControls.getRows()")
            by_key = {r["player_key"]: r for r in rows}
            paid = [r for r in rows if r["player_key"] in zero
                    and any(isinstance(r["values"].get(c), (int, float)) and r["values"][c] > 0 for c in CHARTS)]
            absent_rows = [r for r in rows if r["player_key"] in absent]
            out["paid"] = [{"key": r["player_key"], "name": r["name"],
                            "charts": {c: r["values"].get(c) for c in CHARTS if isinstance(r["values"].get(c), (int, float)) and r["values"][c] > 0}}
                           for r in paid]
            out["engine_values"] = {str(r["player_key"]): {"espn": r["values"].get("espn"), "espn_vorp": r["values"].get("espn_vorp")}
                                    for r in rows if r["player_key"] in zero or r["player_key"] in absent}
            out["engine_flag"] = {"zero": sorted(r["player_key"] for r in rows if r.get("espnProjectsZero")),
                                  "rows_zero": sorted(k for k in by_key if k in zero),
                                  "rows_absent": sorted(r["player_key"] for r in absent_rows)}
            probe_zero = paid[0] if paid else None
            probe_absent = absent_rows[0] if absent_rows else None
            out["probe"] = {"zero": probe_zero and probe_zero["name"], "absent": probe_absent and probe_absent["name"]}

            def main_table_badge(row):
                page.fill("#playerSearch", row["name"])
                return page.evaluate("""(key) => {
                  const tr = document.querySelector(`#tableWrap tr.row-main[data-player-key="${key}"]`);
                  if (!tr) return {present: false, badge: null};
                  return {present: true, badge: tr.querySelector('[data-espn-zero]')?.textContent || null,
                          espn: tr.querySelector('td[data-label="ESPN adjusted"]')?.textContent ?? null};
                }""", row["player_key"])

            main = {}
            for label, row in (("zero", probe_zero), ("absent", probe_absent)):
                if row:
                    main[label] = {"table": main_table_badge(row),
                                   "tooltip": page.evaluate(FIND_TOOLTIP, row["player_key"])}
            # every badge in the full comparison table must belong to an ESPN-0 player
            page.fill("#playerSearch", "")
            out["main_table_badged"] = page.evaluate("""() => [...document.querySelectorAll('#tableWrap tr.row-main')]
              .filter(tr => tr.querySelector('[data-espn-zero]')).map(tr => Number(tr.dataset.playerKey))""")
            out["main"] = main
            out["main_errors"] = list(errors)
            page.close()

            # ---- v2: Player values ----
            # /v2/ lands on Trade targets (Jeremy, 2026-10-08) and renders only
            # the active view, so the Player values table needs its own hash.
            page, errors = open_page(f"{base}/v2/#player-values")
            page.wait_for_function("() => document.querySelector('#v2Table tbody tr')", timeout=30000)
            v2 = {}
            for label, row in (("zero", probe_zero), ("absent", probe_absent)):
                if not row:
                    continue
                page.fill("#v2Search", row["name"])
                page.wait_for_timeout(400)
                cell = page.evaluate("""(name) => {
                  const tr = [...document.querySelectorAll('#v2Table tbody tr')].find(tr => tr.querySelector('td.player')?.childNodes[0]?.textContent === name);
                  if (!tr) return null;
                  return {badge: tr.querySelector('[data-espn-zero]')?.textContent || null};
                }""", row["name"])
                drawer = None
                if cell is not None:
                    page.evaluate("""(name) => [...document.querySelectorAll('#v2Table tbody tr')]
                      .find(tr => tr.querySelector('td.player')?.childNodes[0]?.textContent === name).click()""", row["name"])
                    drawer = page.evaluate("""() => ({note: document.querySelector('#v2Drawer .v2-espn-zero-note')?.textContent || null})""")
                    page.evaluate("() => document.querySelector('#v2Drawer .close').click()")
                v2[label] = {"table": cell, "drawer": drawer}
            out["v2"] = v2
            # ---- v2: Trade targets ----
            page.fill("#v2Search", "")
            page.evaluate("() => { location.hash = '#trade-targets'; }")
            page.wait_for_function("() => window.TradeValueV2 && window.TradeValueV2.targets()", timeout=30000)
            page.click("#v2Targets [data-side=sell]")
            page.wait_for_function("() => document.getElementById('v2TOurs').value === 'espn'")
            out["targets"] = page.evaluate("""() => {
              const t = window.TradeValueV2.targets();
              return {used: t.used, ours: t.ours, retiredList: Boolean(document.getElementById('v2TEspnZero')),
                sell: t.sell.map(p => ({key: p.row.player_key, ours: p.ours,
                  cells: Object.fromEntries(Object.entries(p.cells).map(([c, v]) => [c, {value: v.value, gap: v.gap}]))}))};
            }""")
            # The probe's rendered row in the sell table.
            if probe_zero:
                page.fill("#v2TSearch", probe_zero["name"])
                page.wait_for_timeout(400)
                out["targets_row"] = page.evaluate("""(key) => {
                  const tr = document.querySelector(`#v2TTable tbody tr[data-player-key="${key}"]`);
                  if (!tr) return null;
                  return {ours: tr.querySelector('[data-ours]').textContent,
                    badge: tr.querySelector('[data-espn-zero]')?.textContent || null,
                    gaps: Object.fromEntries([...tr.querySelectorAll('td[data-chart]')].map(td => [td.dataset.chart, td.querySelector('.gap')?.textContent ?? null]))};
                }""", probe_zero["player_key"])
            out["v2_errors"] = list(errors)
            page.close()
        finally:
            browser.close()
    return out




def check(out) -> list[str]:
    errors = []
    zero, absent = set(out["zero_expected"]), set(out["absent_expected"])
    if not out["paid"]:
        errors.append("no ESPN-0 player with a positive published chart value in the current data (nothing to test)")
    if out["probe"]["absent"] is None:
        errors.append("no player without an ESPN row is in the engine rows (nothing to test)")
    flag = out["engine_flag"]
    if flag["zero"] != flag["rows_zero"]:
        errors.append(f"engine espnProjectsZero {len(flag['zero'])} rows != expected ESPN-0 rows {len(flag['rows_zero'])}")
    if set(flag["zero"]) & absent:
        errors.append("a player with no ESPN row is flagged as ESPN 0")
    main = out["main"]
    if "zero" in main:
        if not main["zero"]["table"]["present"] or not badge_ok(main["zero"]["table"]["badge"]):
            errors.append(f"main table: no badge for {out['probe']['zero']}: {main['zero']['table']}")
        tip = main["zero"]["tooltip"]
        if not tip or tip["name"].split(". ", 1)[-1] != out["probe"]["zero"] or not badge_ok(tip["badge"]):
            errors.append(f"main chart tooltip: no badge for {out['probe']['zero']}: {tip}")
    if "absent" in main:
        if not main["absent"]["table"]["present"]:
            errors.append(f"main table: {out['probe']['absent']} not found")
        if main["absent"]["table"]["badge"]:
            errors.append(f"main table: no-ESPN-row player {out['probe']['absent']} labeled ESPN 0")
        if (main["absent"]["tooltip"] or {}).get("badge"):
            errors.append(f"main chart tooltip: no-ESPN-row player {out['probe']['absent']} labeled ESPN 0")
    stray = [k for k in out["main_table_badged"] if k not in zero]
    if stray:
        errors.append(f"main table badges players ESPN does not project at 0: {stray[:5]}")
    v2 = out["v2"]
    if "zero" in v2:
        cell = v2["zero"]["table"]
        if not cell or not badge_ok(cell["badge"]):
            errors.append(f"v2 table: no badge for {out['probe']['zero']}: {cell}")
        if not v2["zero"]["drawer"] or not badge_ok(v2["zero"]["drawer"]["note"]):
            errors.append(f"v2 drawer: no ESPN-0 note for {out['probe']['zero']}")
    if "absent" in v2:
        cell = v2["absent"]["table"]
        if cell is None:
            errors.append(f"v2 table: {out['probe']['absent']} not found")
        elif cell["badge"]:
            errors.append(f"v2 table: no-ESPN-row player {out['probe']['absent']} labeled ESPN 0")
        if v2["absent"]["drawer"] and v2["absent"]["drawer"]["note"]:
            errors.append("v2 drawer: no-ESPN-row player has the ESPN-0 note")
    values = out["engine_values"]
    wrong_zero = [k for k in zero if str(k) in values
                  and (values[str(k)]["espn"] != 0 or values[str(k)]["espn_vorp"] != 0)]
    if wrong_zero:
        errors.append(f"engine: {len(wrong_zero)} ESPN-0 rows without an ESPN value of 0.0, e.g. "
                      f"{wrong_zero[0]}: {values[str(wrong_zero[0])]}")
    wrong_absent = [k for k in absent if str(k) in values and values[str(k)]["espn"] is not None]
    if wrong_absent:
        errors.append(f"engine: no-ESPN-row players with an ESPN value: {wrong_absent[:5]}")
    if "zero" in main and main["zero"]["table"].get("espn") != "0.0":
        errors.append(f"main table: ESPN column for {out['probe']['zero']} shows {main['zero']['table'].get('espn')!r}, expected 0.0")
    if "absent" in main and main["absent"]["table"].get("espn") not in ("—", None):
        errors.append(f"main table: ESPN column for no-ESPN-row {out['probe']['absent']} shows {main['absent']['table'].get('espn')!r}, expected —")
    t = out["targets"]
    used = set(t["used"])
    if t["retiredList"]:
        errors.append("Trade targets: the separate ESPN-0 list should be retired (they are in the sell list)")
    sell = {item["key"]: item for item in t["sell"]}
    for p in out["paid"]:
        paid_used = {c: v for c, v in p["charts"].items() if c in used}
        if not paid_used:
            continue
        item = sell.get(p["key"])
        if not item:
            errors.append(f"Trade targets: {p['name']} (ESPN 0, paid {paid_used}) is not in the sell list")
            continue
        if item["ours"] != 0:
            errors.append(f"Trade targets: {p['name']} our value {item['ours']!r}, expected 0")
        for chart, value in paid_used.items():
            cell = item["cells"].get(chart) or {}
            if cell.get("gap") != value:
                errors.append(f"Trade targets: {p['name']} {chart} gap {cell.get('gap')!r}, expected chart value {value!r}")
    for key in sell:
        if key in absent:
            errors.append(f"Trade targets: no-ESPN-row player {key} is in the sell list")
    row = out.get("targets_row")
    if out["paid"] and any(set(p["charts"]) & used for p in out["paid"][:1]):
        if not row:
            errors.append(f"Trade targets: {out['probe']['zero']} not rendered in the sell table")
        else:
            if row["ours"] != "0.0" or not badge_ok(row["badge"]):
                errors.append(f"Trade targets: {out['probe']['zero']} row shows ours {row['ours']!r}, badge {row['badge']!r}")
            for chart, value in out["paid"][0]["charts"].items():
                if chart in used and row["gaps"].get(chart) != f"+{value:.1f}":
                    errors.append(f"Trade targets: {out['probe']['zero']} {chart} gap {row['gaps'].get(chart)!r}, expected +{value:.1f}")
    if out["main_errors"] or out["v2_errors"]:
        errors.append(f"page errors: {out['main_errors'] + out['v2_errors']}")
    return errors


class EspnZeroBadgeRenderTest(unittest.TestCase):
    def test_espn_zero_is_badged_and_valued_zero_missing_is_not(self):
        out = collect()
        self.assertEqual(check(out), [], json.dumps({k: out[k] for k in ("probe", "paid")}))

    def test_guard_fails_on_broken_builds(self):
        source = PRODUCT_DATA_JS.read_text(encoding="utf-8")
        widget = CURVE_WIDGET_JS.read_text(encoding="utf-8")
        # The engine before "Yes, use 0": an ESPN-0 player is missing (—).
        # (GAP-MAIN-TABLE-ESPN-DRIFT, 2026-10-08: the main table renders the
        # engine's rows and has no copy of the rule to mutate separately; this
        # one mutation reaches the chart, the main table and /v2/.)
        no_zero_widget = widget.replace(
            "if (ESPN_ZERO_VALUE_KEYS.has(key) && player.espnProjectsZero) return 0;", "", 1)
        self.assertNotEqual(no_zero_widget, widget, "mutation anchor for the engine 0.0 rule is stale")
        for name, overrides in {
            "ESPN-0 missing in the engine": {"**/assets/curve-widget.js*": no_zero_widget},
        }.items():
            with self.subTest(mutation=name):
                self.assertNotEqual(check(collect(overrides)), [], f"render checks did not catch: {name}")
        broken = {
            # The flag the page had before GAP-025: none.
            "no ESPN-0 flag": source.replace("espn_projects_zero: espnProjectsZero(player),",
                                             "espn_projects_zero: false,", 1),
            # "No ESPN row" read as "ESPN projects 0".
            "missing labeled as 0": source.replace('if (player?.espn_status === "absent") return false;',
                                                   'if (player?.espn_status === "absent") return true;', 1),
        }
        for name, body in broken.items():
            with self.subTest(mutation=name):
                self.assertNotEqual(body, source, f"mutation anchor for {name!r} is stale")
                self.assertNotEqual(check(collect({"**/assets/product-data.js*": body})), [],
                                    f"render checks did not catch: {name}")


if __name__ == "__main__":
    unittest.main()
