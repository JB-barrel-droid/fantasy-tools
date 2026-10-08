"""v2 settings panels, chart options and navigator (frames 09–12, 20, 21, 24), rendered.

Builds dist/v2 into a temp copy of the built dist/ and loads Player values
headless at 1440 and 390. Every check reads the engine back
(TradeValueCurveControls), so a panel that only looks right fails:

  * Choose your sources (09 / 20): toggling a pair changes nothing until
    Apply; Apply adds exactly that pair to getActiveSources(); Cancel
    discards; an empty draft cannot be applied ("Choose at least one");
    an unavailable pair is disabled; full screen at 390;
  * Your league (12): steppers and segmented buttons are a draft; Apply sets
    getRosterShape() / getState().teams, SUPERFLEX included; a change that
    moves the bench share says so (JEG-444); Reset defaults returns to the
    first-load league;
  * Weights & bench (11): position shares equal getPositionWeights(); Apply
    sets getBenchShare() to the slider's value;
  * Source freshness (10): one row per getSourceInfo() series, with
    "Older" for older-week series and the engine's unavailability;
  * Chart options (21): Bench shows exactly the ranks between the engine's
    getZones() boundaries; unticking Team removes the Team column; custom Y
    bounds set the axis;
  * navigator (24): From / To fields set the chart window; Reset to all
    shows every rank;
  * value range (24): names its basis series; every remaining row's ranking
    value is inside the bounds; minimum above maximum is refused;
  * no page errors, no horizontal overflow at 390.

Discrimination: test_guard_fails_on_broken_builds serves v2.js where a pair
toggle reaches the engine at once, the zone preset is ignored, the Team
column ignores its box, the From / To fields are ignored, and league Apply
does nothing, and requires each to fail.
"""
from __future__ import annotations

import contextlib
import functools
import http.server
import shutil
import socketserver
import sys
import tempfile
import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
sys.path.insert(0, str(ROOT / "pipelines"))
import build_v2_page  # noqa: E402

from tests.test_published_league_settings_render import _chromium_executable  # noqa: E402
from tests import _render_env  # noqa: E402


def setUpModule():
    # Build app/ and dist/ from the committed fixtures first, so the
    # test never reads a stale committed build (GAP-APP-ASSETS-LAG).
    _render_env.ensure_built()


V2_JS = ROOT / "app" / "v2" / "v2.js"
ACTIVE = "() => window.TradeValueCurveControls.getActiveSources()"


def _serve(body, route, *_):
    route.fulfill(status=200, content_type="text/javascript", body=body)


@contextlib.contextmanager
def _built_dist():
    if not (DIST / "index.html").exists():
        raise _render_env.unavailable("dist/index.html is not built")
    with tempfile.TemporaryDirectory() as tmp:
        dist = Path(tmp) / "dist"
        shutil.copytree(DIST, dist, ignore=shutil.ignore_patterns("v2"))
        build_v2_page.build(dist)

        class QuietHandler(http.server.SimpleHTTPRequestHandler):
            def log_message(self, format, *args):
                pass
        handler = functools.partial(QuietHandler, directory=str(dist))
        with socketserver.ThreadingTCPServer(("127.0.0.1", 0), handler) as server:
            server.daemon_threads = True
            threading.Thread(target=server.serve_forever, daemon=True).start()
            try:
                yield f"http://127.0.0.1:{server.server_address[1]}/v2/#player-values"
            finally:
                server.shutdown()


def check_sources(page, width) -> list[str]:
    errors = []
    before = page.evaluate(ACTIVE)
    page.click("#v2EditSources")
    box = page.evaluate("() => { const b = document.getElementById('v2Popover').getBoundingClientRect(); return {w: b.width, h: b.height}; }")
    if width <= 390 and (box["w"] < 389 or box["h"] < 800):
        errors.append(f"sources panel is not full screen at 390: {box}")
    info = page.evaluate("() => Object.fromEntries(window.TradeValueCurveControls.getSourceInfo().map(i => [i.key, i]))")
    pairs = page.evaluate("""() => [...document.querySelectorAll('#v2Popover [data-series]')].map(b => ({key: b.dataset.series,
      on: b.getAttribute('aria-pressed') === 'true', disabled: b.disabled}))""")
    for p in pairs:
        if not info[p["key"]]["available"] and not p["disabled"]:
            errors.append(f"sources: unavailable {p['key']} is offered")
        if p["on"] != (p["key"] in before):
            errors.append(f"sources: {p['key']} pressed={p['on']} but engine active={p['key'] in before}")
    add = next((p["key"] for p in pairs if not p["on"] and not p["disabled"]), None)
    if not add:
        return errors + ["sources: no pair to add"]
    page.click(f'#v2Popover [data-series="{add}"]')
    if page.evaluate(ACTIVE) != before:
        errors.append("sources: a toggle reached the engine before Apply")
    page.click("#v2Popover .v2-panel-foot .v2-btn:not(.v2-btn-primary)")   # Cancel
    if page.evaluate(ACTIVE) != before:
        errors.append("sources: Cancel changed the selection")
    page.click("#v2EditSources")
    page.click(f'#v2Popover [data-series="{add}"]')
    page.click('#v2Popover [data-apply="sources"]')
    after = page.evaluate(ACTIVE)
    if sorted(after) != sorted(before + [add]):
        errors.append(f"sources: Apply gave {after}, wanted {before + [add]}")
    # An empty draft is refused.
    page.click("#v2EditSources")
    for key in after:
        page.click(f'#v2Popover [data-series="{key}"]')
    page.click('#v2Popover [data-apply="sources"]')
    refused = page.evaluate("() => !document.getElementById('v2Popover').hidden && !document.querySelector('#v2Popover .v2-perror').hidden")
    if not refused or page.evaluate(ACTIVE) != after:
        errors.append("sources: an empty selection was applied")
    page.keyboard.press("Escape")
    # Back to the first-use selection for the rest of the checks.
    page.click("#v2EditSources")
    page.click(f'#v2Popover [data-series="{add}"]')
    page.click('#v2Popover [data-apply="sources"]')
    return errors


def check_league(page) -> list[str]:
    errors = []
    start = page.evaluate("() => ({shape: window.TradeValueCurveControls.getRosterShape(), teams: window.TradeValueCurveControls.getState().teams})")
    page.click("#v2EditLeague")
    page.click('#v2Popover [aria-label="More WR"]')
    page.click('#v2Popover .v2-pseg button[data-value="10"]')
    if page.evaluate("() => window.TradeValueCurveControls.getRosterShape().WR") != start["shape"]["WR"]:
        errors.append("league: a stepper reached the engine before Apply")
    page.click('#v2Popover [data-apply="league"]')
    now = page.evaluate("() => ({shape: window.TradeValueCurveControls.getRosterShape(), teams: window.TradeValueCurveControls.getState().teams})")
    if now["shape"]["WR"] != start["shape"]["WR"] + 1 or now["teams"] != 10:
        errors.append(f"league: Apply gave WR {now['shape']['WR']} teams {now['teams']}, wanted WR {start['shape']['WR'] + 1} teams 10")
    line = page.text_content("#v2RosterLine")
    if f"{now['shape']['WR']} WR" not in line:
        errors.append(f"league: roster line {line!r} does not follow the engine")
    # SUPERFLEX (engine slot 0–1): the stepper reaches setRosterSpot on Apply, the roster line names it.
    page.click("#v2EditLeague")
    if page.locator('#v2Popover [aria-label="More SUPERFLEX"]').count():
        page.click('#v2Popover [aria-label="More SUPERFLEX"]')
    page.click('#v2Popover [data-apply="league"]')
    sf = page.evaluate("() => window.TradeValueCurveControls.getRosterShape().SUPERFLEX")
    if sf != 1 or "1 SUPERFLEX" not in page.text_content("#v2RosterLine"):
        errors.append(f"league: SUPERFLEX stepper gave engine {sf}, roster line {page.text_content('#v2RosterLine')!r}")
    # JEG-444: a league change that moves the bench share says so. Today's feasible range does not
    # depend on the roster, so the test makes the engine re-clamp on the next team change.
    page.evaluate("""() => { const C = window.TradeValueCurveControls; const setTeams = C.setTeams;
      C.setTeams = t => { setTeams(t); C.setBenchShareFraction(0.2); }; }""")
    page.click("#v2EditLeague")
    page.click('#v2Popover .v2-pseg button[data-value="14"]')
    page.click('#v2Popover [data-apply="league"]')
    toast = page.evaluate("() => document.getElementById('v2Status').hidden ? '' : document.getElementById('v2Status').textContent")
    if "Bench share moved from 15.0% to 20.0%" not in toast:
        errors.append(f"league: bench re-clamp not reported: {toast!r}")
    page.evaluate("() => window.TradeValueCurveControls.setBenchShareFraction(0.15)")
    page.click("#v2EditLeague")
    page.click("#v2Popover .v2-preset")
    page.click('#v2Popover [data-apply="league"]')
    back = page.evaluate("() => ({shape: window.TradeValueCurveControls.getRosterShape(), teams: window.TradeValueCurveControls.getState().teams})")
    if back != start:
        errors.append(f"league: Reset defaults gave {back}, first load was {start}")
    return errors


def check_weights(page) -> list[str]:
    errors = []
    page.click("#v2Weights")
    shown = page.evaluate("() => Object.fromEntries([...document.querySelectorAll('#v2Popover [data-weight]')].map(n => [n.dataset.weight, n.textContent]))")
    weights = page.evaluate("() => window.TradeValueCurveControls.getPositionWeights()")
    for pos, text in shown.items():
        if text != f"{float(weights[pos]) * 100:.1f}%":
            errors.append(f"weights: {pos} shows {text}, engine {weights[pos]}")
    bounds = page.evaluate("() => window.TradeValueCurveControls.getBenchBounds()")
    if bounds:
        target = round((bounds[0] + bounds[1]) / 2, 3)
        page.evaluate("v => { const s = document.getElementById('v2BenchSlider'); s.value = String(v); s.dispatchEvent(new Event('input')); }", target)
        page.click('#v2Popover [data-apply="weights"]')
        got = page.evaluate("() => window.TradeValueCurveControls.getBenchShare()")
        if abs(got - target) > 0.006:   # the slider steps by 0.005
            errors.append(f"weights: Apply set bench {got}, slider {target}")
        page.evaluate("() => window.TradeValueCurveControls.setBenchShareFraction(0.15)")
    else:
        page.keyboard.press("Escape")
    return errors


def check_freshness(page) -> list[str]:
    errors = []
    page.click("#v2Freshness")
    rows = page.evaluate("""() => [...document.querySelectorAll('#v2Popover tr[data-series]')].map(tr => ({key: tr.dataset.series,
      status: tr.lastElementChild.textContent}))""")
    info = page.evaluate("""() => { const fresh = window.TradeValueProductData?.getSourceFreshness?.()?.series || {};
      return window.TradeValueCurveControls.getSourceInfo().map(i => ({...i, stale: typeof fresh[i.key]?.is_older_week === 'boolean' ? fresh[i.key].is_older_week : i.stale})); }""")
    if [r["key"] for r in rows] != [i["key"] for i in info]:
        errors.append(f"freshness: rows {[r['key'] for r in rows]} != engine {[i['key'] for i in info]}")
    for r, i in zip(rows, info):
        if not i["available"] and "vailable" not in r["status"]:
            errors.append(f"freshness: {r['key']} unavailable but status {r['status']!r}")
        elif i["available"] and bool(i["stale"]) != ("Older" in r["status"]):
            errors.append(f"freshness: {r['key']} stale={i['stale']} but status {r['status']!r}")
    page.keyboard.press("Escape")
    return errors


def check_chart(page) -> list[str]:
    errors = []
    page.click("#v2ChartOptions")
    page.click('#v2Popover .v2-pseg button[data-value="bench"]')
    page.click('#v2Popover input[data-meta="team"]')
    page.click('#v2Popover .v2-pseg button[data-value="custom"]')
    page.fill("#v2Popover .row2 label:nth-child(2) input", "50")
    page.click('#v2Popover [data-apply="chart"]')
    got = page.evaluate("""() => { const v = window.TradeValueV2.view(); const s = window.TradeValueV2.state;
      return {window: s.window, ranks: v.rows.slice(s.window[0] - 1, s.window[1]).map(r => r.fullRank), zones: window.TradeValueCurveControls.getZones(),
        heads: [...document.querySelectorAll('#v2Table thead th')].map(th => th.textContent.replace(/[↕↓↑]/g, '').trim()),
        top: Math.max(...[...document.querySelectorAll('#v2Chart .axis text[text-anchor="end"]')].map(t => Number(t.textContent)).filter(Number.isFinite))}; }""")
    sb, bw = got["zones"]["starter_to_bench"], got["zones"]["bench_to_waiver"]
    if not got["ranks"] or min(got["ranks"]) < sb or max(got["ranks"]) > bw:
        errors.append(f"chart options: Bench window ranks {got['ranks'][:3]}…{got['ranks'][-3:]} outside {sb}–{bw}")
    if "Team" in got["heads"]:
        errors.append("chart options: Team column still shown after unticking it")
    if got["top"] != 50:
        errors.append(f"chart options: custom upper bound 50, axis tops out at {got['top']}")
    # Restore.
    page.click("#v2ChartOptions")
    page.click('#v2Popover .v2-pseg button[data-value="100"]')
    page.click('#v2Popover input[data-meta="team"]')
    page.click('#v2Popover .v2-pseg button[data-value="auto"]')
    page.click('#v2Popover [data-apply="chart"]')
    return errors


def check_navigator(page) -> list[str]:
    errors = []
    page.fill("#v2FromRank", "20")
    page.fill("#v2ToRank", "60")
    page.press("#v2ToRank", "Enter")
    page.evaluate("() => document.getElementById('v2ToRank').dispatchEvent(new Event('change'))")
    win = page.evaluate("() => window.TradeValueV2.state.window")
    if win != [20, 60]:
        errors.append(f"navigator: From 20 To 60 gave window {win}")
    page.click("#v2ResetAll")
    win = page.evaluate("() => [window.TradeValueV2.state.window, window.TradeValueV2.view().rows.length]")
    if win[0] != [1, win[1]]:
        errors.append(f"navigator: Reset to all gave {win[0]} of {win[1]}")
    return errors


def check_range(page) -> list[str]:
    errors = []
    page.click("#v2RangeBtn")
    sub = page.text_content("#v2Popover .v2-panel-head .v2-meta")
    rank = page.evaluate("() => window.TradeValueV2.view().rankKey")
    if "Basis" not in sub:
        errors.append(f"value range: no basis series named: {sub!r}")
    inputs = page.locator("#v2Popover .row2 input")
    inputs.nth(0).fill("30")
    inputs.nth(1).fill("10")
    page.click('#v2Popover [data-apply="range"]')
    if page.evaluate("() => document.getElementById('v2Popover').hidden"):
        errors.append("value range: minimum above maximum was accepted")
    inputs.nth(1).fill("40")
    page.click('#v2Popover [data-apply="range"]')
    vals = page.evaluate(f"() => window.TradeValueV2.view().rows.map(r => r.values['{rank}'])")
    if not vals or any(v is None or v < 30 or v > 40 for v in vals):
        errors.append(f"value range: rows outside 30–40 in {rank}: {[v for v in vals if v is None or v < 30 or v > 40][:5]}")
    page.click("#v2ClearFilters")
    return errors


def run_checks(v2_js=None, viewports=((1440, 1000), (390, 844))) -> list[str]:
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        raise _render_env.unavailable(f"Playwright is not available: {exc}") from exc
    errors = []
    with _built_dist() as url, sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(args=_render_env.HERMETIC_ARGS, executable_path=_chromium_executable(playwright))
        except PlaywrightError as exc:
            raise _render_env.unavailable(f"Chromium is not available: {exc}") from exc
        try:
            for width, height in viewports:
                page = browser.new_page(viewport={"width": width, "height": height})
                page_errors = []
                page.on("pageerror", lambda e: page_errors.append(str(e)))
                page.route(lambda u: not u.startswith("http://127.0.0.1"), lambda route: route.abort())
                if v2_js is not None:
                    page.route("**/v2/v2.js*", functools.partial(_serve, v2_js))
                page.goto(url, wait_until="networkidle")
                page.wait_for_function("() => window.TradeValueV2 && document.querySelector('#v2Table tbody tr')", timeout=40000)
                tag = f"[{width}px] "
                errors += [tag + e for e in check_sources(page, width)]
                if width == 1440:
                    for check in (check_league, check_weights, check_freshness, check_chart, check_navigator, check_range):
                        errors += [tag + e for e in check(page)]
                overflow = page.evaluate("() => document.documentElement.scrollWidth - innerWidth")
                if width <= 390 and overflow > 0:
                    errors.append(tag + f"horizontal overflow {overflow}px")
                if page_errors:
                    errors.append(tag + f"page errors {page_errors}")
                page.close()
        finally:
            browser.close()
    return errors


class PanelsRenderTest(unittest.TestCase):
    def test_panels_drive_the_engine(self):
        self.assertEqual(run_checks(), [])

    def test_guard_fails_on_broken_builds(self):
        v2 = V2_JS.read_text(encoding="utf-8")
        broken = {
            "pair toggle applied at once": v2.replace(
                "              if (draft.has(item.key)) draft.delete(item.key);\n              else draft.add(item.key);",
                "              if (draft.has(item.key)) draft.delete(item.key);\n              else draft.add(item.key);\n              toggleEngineSource(item.key);", 1),
            "zone preset ignored": v2.replace("    const zone = zoneWindow(rows, state.windowPreset);", "    const zone = null;", 1),
            "Team box ignored": v2.replace("].filter(col => state.metaCols[col.id] !== false);", "];", 1),
            "From / To ignored": v2.replace('$("v2ToRank").addEventListener("change", onBounds);', "", 1),
            "no SUPERFLEX stepper": v2.replace(
                '    ["SUPERFLEX", "SUPERFLEX", 0, 1], ["BENCH", "Bench slots", 0, 14]];', '    ["BENCH", "Bench slots", 0, 14]];', 1),
            "bench move not reported": v2.replace(
                "    if (Number.isFinite(benchBefore) && Number.isFinite(benchAfter) && Math.abs(benchAfter - benchBefore) > 1e-9) {",
                "    if (false) {", 1),
            "league Apply does nothing": v2.replace(
                "          ROSTER_SLOTS.forEach(([key]) => { if (draft.roster[key] !== shape[key]) C.setRosterSpot(key, draft.roster[key]); });",
                "", 1),
        }
        for name, body in broken.items():
            with self.subTest(mutation=name):
                self.assertNotEqual(body, v2, f"mutation anchor for {name!r} is stale")
                self.assertNotEqual(run_checks(v2_js=body, viewports=((1440, 1000),)), [], f"render checks did not catch: {name}")


if __name__ == "__main__":
    unittest.main()
