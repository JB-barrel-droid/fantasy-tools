"""GAP-025: players ESPN projects at 0 carry a visible badge; published values stay.

Jeremy's decision (2026-10-07): show each publisher's value as published and
add a badge saying ESPN projects 0 for the player (injured/out). A player ESPN
has no row for is missing, not 0, and must not get the badge.

Expected sets come from the built page's own #players-data island, read here in
Python, not from the code under test:

  * ESPN 0: espn_status "ineligible" (ESPN lists the player with a zero
    projection), or an ESPN row whose per-game projection is 0 in every scoring;
  * no ESPN row: espn_status "absent".

Headless against a temp copy of the built dist/ (with dist/v2 rebuilt from
app/v2), for a real ESPN-0 player a published chart still pays for, and a real
no-ESPN-row player, it checks:

  * main page: the comparison table row and the chart tooltip;
  * /v2/: the Player values table row and tooltip, the player drawer, and the
    Trade targets "ESPN projects 0, but a chart still pays" list (sell side),
    whose chart values must equal the engine's;
  * the badge has a text label and a symbol, not color alone.

Discrimination: test_guard_fails_on_broken_builds serves the origin/main-era
behaviour (no badge flag) and a variant that labels "no ESPN row" as 0, and
requires the checks to fail on both.
"""
from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

from tests.test_published_league_settings_render import _chromium_executable  # noqa: E402
from tests.test_v2_targets_render import DIST, _built_dist  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
PRODUCT_DATA_JS = ROOT / "app" / "trade-value-chart" / "assets" / "product-data.js"
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
        raise unittest.SkipTest(f"Playwright is not available: {exc}") from exc
    zero, absent = expected_sets()
    out = {"zero_expected": sorted(zero), "absent_expected": sorted(absent)}
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
                def serve(body):
                    return lambda route: route.fulfill(status=200, content_type="text/javascript", body=body)
                for pattern, body in (overrides or {}).items():
                    page.route(pattern, serve(body))
                page.goto(url, wait_until="networkidle")
                page.wait_for_function("() => window.TradeValueCurveControls && window.TradeValueCurveControls.getRows().length > 0", timeout=30000)
                return page, errors

            # ---- main page ----
            page, errors = open_page(f"{base}/index.html")
            rows = page.evaluate("() => window.TradeValueCurveControls.getRows()")
            by_key = {r["player_key"]: r for r in rows}
            paid = [r for r in rows if r["player_key"] in zero
                    and any(isinstance(r["values"].get(c), (int, float)) and r["values"][c] > 0 for c in CHARTS)]
            absent_rows = [r for r in rows if r["player_key"] in absent]
            out["paid"] = [{"key": r["player_key"], "name": r["name"],
                            "charts": {c: r["values"].get(c) for c in CHARTS if isinstance(r["values"].get(c), (int, float)) and r["values"][c] > 0}}
                           for r in paid]
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
                  return {present: true, badge: tr.querySelector('[data-espn-zero]')?.textContent || null};
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
            page, errors = open_page(f"{base}/v2/")
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
            out["targets"] = page.evaluate("""() => {
              const box = document.getElementById('v2TEspnZero');
              const rows = window.TradeValueCurveControls.getRows();
              const engine = Object.fromEntries(rows.map(r => [String(r.player_key), r.values]));
              return {hidden: box ? box.hidden : null, used: window.TradeValueV2.targets().used, engine,
                items: [...document.querySelectorAll('#v2TEspnZeroList li')].map(li => ({
                  key: Number(li.dataset.playerKey), badge: li.querySelector('[data-espn-zero]')?.textContent || null,
                  cells: Object.fromEntries([...li.querySelectorAll('[data-chart]')].map(s => [s.dataset.chart, s.textContent]))})),
                tableBadged: [...document.querySelectorAll('#v2TTable tbody tr')].filter(tr => tr.querySelector('[data-espn-zero]')).map(tr => Number(tr.dataset.playerKey))};
            }""")
            page.click("#v2Targets [data-side=buy]")
            out["targets_buy_hidden"] = page.evaluate("() => document.getElementById('v2TEspnZero')?.hidden")
            out["v2_errors"] = list(errors)
            page.close()
        finally:
            browser.close()
    return out


PUB_NAMES = {"usatoday": "USA Today", "fantasycalc": "FantasyCalc", "fantasypros": "FantasyPros", "cbs": "CBS Sports"}


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
    t = out["targets"]
    used = set(t["used"])
    expected_items = [p for p in out["paid"] if set(p["charts"]) & used]
    got = {item["key"]: item for item in t["items"]}
    if expected_items and (t["hidden"] or not got):
        errors.append("Trade targets: ESPN-0 players a chart still pays for are not listed")
    for p in expected_items:
        item = got.get(p["key"])
        if not item:
            errors.append(f"Trade targets: {p['name']} missing from the ESPN-0 list")
            continue
        if not badge_ok(item["badge"]):
            errors.append(f"Trade targets: {p['name']} listed without the badge")
        for chart, value in p["charts"].items():
            if chart in used and item["cells"].get(chart) != f"{PUB_NAMES[chart]} {value:.1f}":
                errors.append(f"Trade targets: {p['name']} {chart} shows {item['cells'].get(chart)!r}, engine {value:.1f}")
    for key in got:
        if key not in zero:
            errors.append(f"Trade targets: player {key} listed as ESPN 0 but is not")
    if t["tableBadged"] and any(k not in zero for k in t["tableBadged"]):
        errors.append("Trade targets table badges a player ESPN does not project at 0")
    if not out["targets_buy_hidden"]:
        errors.append("Trade targets: the ESPN-0 sell list shows on the buy side")
    if out["main_errors"] or out["v2_errors"]:
        errors.append(f"page errors: {out['main_errors'] + out['v2_errors']}")
    return errors


class EspnZeroBadgeRenderTest(unittest.TestCase):
    def test_badge_on_espn_zero_not_on_missing(self):
        out = collect()
        self.assertEqual(check(out), [], json.dumps({k: out[k] for k in ("probe", "paid")}))

    def test_guard_fails_on_broken_builds(self):
        source = PRODUCT_DATA_JS.read_text(encoding="utf-8")
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
