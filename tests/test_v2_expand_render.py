"""Player values: expanded chart and table, Reset zoom, active filter chips (JEG-483), rendered.

Builds dist/v2 into a temp copy of the built dist/ and loads Player values
headless at 1440 x 900 and 390 x 844. Every value check reads the engine back
(TradeValueCurveControls), so a view that only looks right fails:

  * expanded chart: the button opens a large dialog with focus on its close
    button; its series lines are the main chart's lines (same data-source set)
    and the rows it plots are the engine's rows for the rank window; each
    line's first and last points sit at the engine's row.values; both brushes
    and the legend are inside; the 25 / 50 / 100 / All chips set Show (toolbar
    and table follow); a Y brush change there updates Show and the table, and
    with axis zoom the Y axis spans the value range; player names label the
    points once zoomed in; Esc closes it and focus returns to the button;
  * expanded table: Pos / Team / Tier are their own sortable columns, equal to
    the engine rows (Tier from the ranking series: row.ddfTier for DDF Value,
    getZones() boundaries otherwise), sticky header, heat tint, Show more
    paging; Esc closes it and focus returns to its button;
  * Reset zoom: hidden until a zoom or brush makes Show Custom; it restores
    the Show preset from before the zoom and leaves search alone;
  * filter chips: one per active filter (value, ranks, search, position) and
    each clears only its own filter; "Set exact values" is a 44 px control;
  * no page errors; no horizontal overflow at 390, expanded views full screen.

Discrimination: test_guard_fails_on_broken_builds serves v2.js / v2.css with
one fault each (expanded chart drops a line, Esc leaves it open, focus not
returned, expanded table hides Pos / Team / Tier, Tier read from ESPN, Reset
zoom ignores the remembered preset, the value chip also clears search, the
ranks chip also clears the value range, "Set exact values" back to a small
link) and requires each to fail.
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
    _render_env.ensure_built()


V2_JS = ROOT / "app" / "v2" / "v2.js"
V2_CSS = ROOT / "app" / "v2" / "v2.css"

SNAP = """() => { const s = window.TradeValueV2.state; const v = window.TradeValueV2.view();
  return {preset: s.windowPreset, window: s.window, range: s.range, search: s.search,
    input: document.getElementById('v2Search').value, position: window.TradeValueCurveControls.getState().position,
    show: document.getElementById('v2Show').value, n: v.rows.length, visible: v.visible.length,
    tableRows: document.querySelectorAll('#v2Table tbody tr').length,
    resetZoom: !document.getElementById('v2ResetZoom').hidden,
    chips: [...document.querySelectorAll('#v2FilterChips .v2-fchip')].map(b => ({id: b.dataset.chip, text: b.textContent.trim()})),
    expanded: window.TradeValueV2.expanded(), active: document.activeElement ? document.activeElement.id : ''}; }"""

# The expanded chart against the engine: lines, rows and each line's end points.
CHART = """() => { const C = window.TradeValueCurveControls, V2 = window.TradeValueV2, v = V2.view(), ch = V2.chart();
  const engine = new Map(C.getRows().map(r => [String(r.player_key), r]));
  const [lo, hi] = V2.state.window;
  // Shown = the rank window, then the value range on the ranking series (JEG-472).
  const {min, max} = V2.state.range;
  const windowKeys = v.rows.slice(lo - 1, hi).filter(r => (min === null && max === null) || (Number.isFinite(r.values[v.rankKey])
    && (min === null || r.values[v.rankKey] >= min) && (max === null || r.values[v.rankKey] <= max))).map(r => String(r.player_key));
  const sliceKeys = ch.slice.map(r => String(r.player_key));
  const box = document.querySelector('#v2Expand .v2-expand-box');
  const scope = box && !document.getElementById('v2Expand').hidden ? box : document;
  const paths = [...scope.querySelectorAll('#v2Chart path.series')];
  const ends = paths.map(p => {
    const key = p.dataset.source;
    const pts = [...p.getAttribute('d').matchAll(/[ML](-?[\\d.]+),(-?[\\d.]+)/g)].map(m => [Number(m[1]), Number(m[2])]);
    const idx = ch.slice.map((r, i) => Number.isFinite(engine.get(String(r.player_key)).values[key]) ? i : -1).filter(i => i >= 0);
    const want = i => [ch.x(i), ch.y(Math.max(0, engine.get(String(ch.slice[i].player_key)).values[key]))];
    return {key, first: pts[0], last: pts[pts.length - 1], wantFirst: idx.length ? want(idx[0]) : null,
      wantLast: idx.length ? want(idx[idx.length - 1]) : null};
  });
  const plot = document.getElementById('v2Plot').getBoundingClientRect();
  const boxRect = box ? box.getBoundingClientRect() : {width: 0, height: 0};
  return {keys: paths.map(p => p.dataset.source).sort(), sliceKeys, windowKeys, ends,
    inOverlay: Boolean(document.querySelector('#v2Expand #v2Plot')),
    brushes: ['v2BrushLo', 'v2BrushHi', 'v2YBrushLo', 'v2YBrushHi'].every(id => document.querySelector('#v2Expand #' + id)?.offsetParent),
    legend: document.querySelectorAll('#v2ExpandLegend > span').length, plotKeys: v.plotKeys.length,
    names: document.querySelectorAll('#v2Chart .name-label').length, nVisible: v.visible.length,
    ymin: ch.ymin, ymax: ch.ymax, plotH: plot.height, boxW: boxRect.width, boxH: boxRect.height,
    innerW: innerWidth, innerH: innerHeight}; }"""

# The expanded table's Pos / Team / Tier cells against the engine rows.
TABLE = """() => { const C = window.TradeValueCurveControls, rank = C.getRankSource(), z = C.getZones();
  const label = t => ({starter: 'Starter', bench: 'Bench', waiver: 'Waiver'}[t] || '—');
  const rows = C.getRows();
  const want = new Map(rows.map((r, i) => [String(r.player_key), {pos: r.pos, team: r.team || 'FA',
    tier: label(rank === 'ddf_value' ? r.ddfTier : !Number.isFinite(r.values[rank]) ? null
      : (i + 1 < z.starter_to_bench ? 'starter' : i + 1 < z.bench_to_waiver ? 'bench' : 'waiver'))}]));
  // "◐ 1 source" wherever the engine flags a DDF Value as low confidence, as in the main table.
  const lowWant = new Set(rows.filter(r => r.ddfLowConfidence && Number.isFinite(r.values.ddf_value)).map(r => String(r.player_key)));
  const scope = document.querySelector('#v2Expand #v2Table');
  const heads = scope ? [...scope.querySelectorAll('.v2-head-row th')].map(th => ({col: th.dataset.col, button: Boolean(th.querySelector('button')),
    sticky: getComputedStyle(th).position})) : [];
  const cells = scope ? [...scope.querySelectorAll('tbody tr')].map(tr => ({key: tr.dataset.playerKey,
    pos: tr.querySelector('td[data-col=pos]')?.textContent ?? null, team: tr.querySelector('td[data-col=team]')?.textContent ?? null,
    tier: tr.querySelector('td[data-col=tier]')?.textContent ?? null,
    ddfCell: Boolean(tr.querySelector('td[data-source="ddf_value"]')),
    low: Boolean(tr.querySelector('td[data-source="ddf_value"] [data-low-confidence]'))})) : [];
  return {rank, heads, cells, want: Object.fromEntries(cells.map(c => [c.key, want.get(c.key)])),
    lowBad: cells.filter(c => c.ddfCell && c.low !== lowWant.has(c.key)).map(c => c.key),
    heat: scope ? scope.querySelectorAll('td[data-vs]').length : 0,
    more: Boolean(document.querySelector('#v2Expand #v2ShowMore') && !document.getElementById('v2ShowMore').hidden),
    box: (() => { const b = document.querySelector('#v2Expand .v2-expand-box').getBoundingClientRect(); return {w: b.width, h: b.height}; })(),
    innerW: innerWidth, innerH: innerHeight}; }"""


def _settle(page, ms=150):
    page.wait_for_timeout(ms)


def _set_range_input(page, element_id, value):
    page.evaluate("""([id, v]) => { const s = document.getElementById(id); s.value = String(v);
      s.dispatchEvent(new Event('input', {bubbles: true})); }""", [element_id, value])
    _settle(page)


def _close(a, b, tol=0.2):
    return a is not None and b is not None and abs(a[0] - b[0]) <= tol and abs(a[1] - b[1]) <= tol


def _force_close(page):
    """A faulty build may leave the dialog open; close it with ✕ so later checks can reach the page."""
    if page.evaluate("() => window.TradeValueV2.expanded()"):
        page.click("#v2ExpandClose")
        _settle(page, 250)


def check_chart_lines(chart, tag) -> list[str]:
    errors = []
    if chart["sliceKeys"] != chart["windowKeys"]:
        errors.append(tag + f"plotted rows are not the engine's rows for the rank window ({len(chart['sliceKeys'])} vs {len(chart['windowKeys'])})")
    for end in chart["ends"]:
        if not _close(end["first"], end["wantFirst"]) or not _close(end["last"], end["wantLast"]):
            errors.append(tag + f"{end['key']}: line ends {end['first']} / {end['last']}, engine values at {end['wantFirst']} / {end['wantLast']}")
    return errors[:6]


def check_expanded_chart(page, tag, width) -> list[str]:
    errors = []
    page.select_option("#v2Show", "100")
    _settle(page)
    main = page.evaluate(CHART)
    errors += check_chart_lines(main, tag + "main chart: ")
    page.click("#v2ExpandChart")
    _settle(page, 250)
    snap = page.evaluate(SNAP)
    chart = page.evaluate(CHART)
    if snap["expanded"] != "chart" or not chart["inOverlay"]:
        return errors + [tag + f"expand chart: did not open ({snap['expanded']})"]
    if snap["active"] != "v2ExpandClose":
        errors.append(tag + f"expand chart: focus on {snap['active']!r}, want the close button")
    if chart["keys"] != main["keys"] or not chart["keys"]:
        errors.append(tag + f"expand chart: lines {chart['keys']} differ from the main chart's {main['keys']}")
    errors += check_chart_lines(chart, tag + "expanded chart: ")
    if not chart["brushes"]:
        errors.append(tag + "expand chart: the X and Y brushes are not both inside")
    if chart["legend"] < chart["plotKeys"]:
        errors.append(tag + f"expand chart: legend has {chart['legend']} entries for {chart['plotKeys']} lines")
    if width >= 1280 and (chart["boxW"] < 0.8 * chart["innerW"] or chart["plotH"] < 0.6 * chart["innerH"]):
        errors.append(tag + f"expand chart: not a large view (box {chart['boxW']:.0f} wide, plot {chart['plotH']:.0f} tall)")
    if width <= 390 and (chart["boxW"] < chart["innerW"] - 1 or chart["boxH"] < chart["innerH"] - 1):
        errors.append(tag + f"expand chart: not full screen at 390 ({chart['boxW']:.0f} x {chart['boxH']:.0f})")
    if width <= 390:
        overflow = page.evaluate("() => document.documentElement.scrollWidth - innerWidth")
        if overflow > 0:
            errors.append(tag + f"expand chart: horizontal overflow {overflow}px")
    # Quick chips set Show; the toolbar and the table follow.
    page.click("#v2ExpandTools [data-xshow='50']")
    _settle(page)
    snap = page.evaluate(SNAP)
    if snap["preset"] != "50" or snap["show"] != "50" or snap["visible"] != min(50, snap["n"]) or snap["tableRows"] != snap["visible"]:
        errors.append(tag + f"expand chart Top 50: preset {snap['preset']} Show {snap['show']} visible {snap['visible']} table {snap['tableRows']}")
    if width >= 1280:
        page.click("#v2ExpandTools [data-xshow='25']")
        _settle(page)
        chart = page.evaluate(CHART)
        if chart["names"] != chart["nVisible"]:
            errors.append(tag + f"expand chart Top 25: {chart['names']} player names for {chart['nVisible']} points")
        page.click("#v2ExpandTools [data-xshow='100']")
        _settle(page)
        # A Y brush change in the expanded view: Show, the table and (axis zoom) the Y axis follow.
        _set_range_input(page, "v2YBrushLo", 12)
        _set_range_input(page, "v2YBrushHi", 30)
        snap = page.evaluate(SNAP)
        chart = page.evaluate(CHART)
        vals = page.evaluate("() => [...document.querySelectorAll('#v2Table tbody td.is-rank')].map(td => Number(td.firstChild.textContent))")
        if snap["preset"] != "custom" or snap["show"] != "custom" or not vals or any(v < 11.95 or v > 30.05 for v in vals):
            errors.append(tag + f"expand chart Y brush 12–30: Show {snap['show']}, table values {vals[:4]}")
        if (chart["ymin"], chart["ymax"]) != (12, 30):
            errors.append(tag + f"expand chart axis zoom: Y axis {chart['ymin']}–{chart['ymax']}, want 12–30")
        errors += check_chart_lines(chart, tag + "expanded chart, axis zoom: ")
        page.click("#v2AxisZoom")
        _settle(page)
        chart = page.evaluate(CHART)
        if chart["ymin"] != 0:
            errors.append(tag + f"expand chart axis zoom off: Y axis starts at {chart['ymin']}")
        page.click("#v2AxisZoom")
    page.keyboard.press("Escape")
    _settle(page, 250)
    snap = page.evaluate(SNAP)
    back = page.evaluate("() => Boolean(document.querySelector('.v2-chart-card #v2Plot')) && document.getElementById('v2Expand').hidden")
    if snap["expanded"] is not None or not back:
        errors.append(tag + "Esc did not close the expanded chart")
    if snap["active"] != "v2ExpandChart":
        errors.append(tag + f"after Esc focus is on {snap['active']!r}, want the expand button")
    _force_close(page)
    page.click("#v2Reset")
    _settle(page)
    return errors


def check_table_meta(table, tag) -> list[str]:
    errors = []
    cols = {h["col"]: h for h in table["heads"]}
    for col in ("pos", "team", "tier"):
        if col not in cols or not cols[col]["button"]:
            errors.append(tag + f"expanded table: no sortable {col} column")
    if not table["cells"]:
        return errors + [tag + "expanded table: no rows"]
    bad = [(c["key"], {k: c[k] for k in ("pos", "team", "tier")}, table["want"][c["key"]]) for c in table["cells"]
           if {k: c[k] for k in ("pos", "team", "tier")} != table["want"][c["key"]]]
    if bad:
        errors.append(tag + f"expanded table ({table['rank']}): {len(bad)} rows differ from the engine, e.g. {bad[:2]}")
    if table["lowBad"]:
        errors.append(tag + f"expanded table: '◐ 1 source' tag differs from the engine's flag for {table['lowBad'][:3]}")
    return errors


def check_expanded_table(page, tag, width) -> list[str]:
    errors = []
    page.click("#v2ExpandTable")
    _settle(page, 250)
    snap = page.evaluate(SNAP)
    if snap["expanded"] != "table":
        return errors + [tag + "expand table: did not open"]
    table = page.evaluate(TABLE)
    errors += check_table_meta(table, tag)
    if width >= 768 and not all(h["sticky"] == "sticky" for h in table["heads"]):
        errors.append(tag + "expanded table: header row not sticky")
    if not table["heat"]:
        errors.append(tag + "expanded table: no heat-tinted cells")
    if width <= 390 and (table["box"]["w"] < table["innerW"] - 1 or table["box"]["h"] < table["innerH"] - 1):
        errors.append(tag + f"expanded table: not full screen at 390 {table['box']}")
    if width >= 1280:
        if snap["visible"] > 50:
            if not table["more"]:
                errors.append(tag + "expanded table: no Show more")
            else:
                page.click("#v2Expand #v2ShowMore")
                _settle(page)
                rows = page.evaluate("() => document.querySelectorAll('#v2Expand #v2Table tbody tr').length")
                if rows != min(100, snap["visible"]):
                    errors.append(tag + f"expanded table Show more: {rows} rows")
        # Sort by Tier: Starter, then Bench, then Waiver.
        if page.locator("#v2Expand th[data-col='tier'] button").count():
            page.click("#v2Expand th[data-col='tier'] button")
            _settle(page)
        tiers = page.evaluate("() => [...document.querySelectorAll('#v2Expand td[data-col=tier]')].map(td => td.textContent)")
        order = {"Starter": 0, "Bench": 1, "Waiver": 2, "—": 3}
        if [order[t] for t in tiers] != sorted(order[t] for t in tiers):
            errors.append(tag + f"expanded table: Tier sort out of order {tiers[:6]}")
        # Another ranking series: Tier follows the engine zones for that ranking.
        other = page.evaluate("() => [...document.getElementById('v2RankBy').options].map(o => o.value).find(k => k !== 'ddf_value' && !/_vorp$/.test(k))")
        if other:
            page.keyboard.press("Escape")
            _settle(page)
            _force_close(page)
            page.select_option("#v2RankBy", other)
            _settle(page, 300)
            page.click("#v2ExpandTable")
            _settle(page, 250)
            errors += check_table_meta(page.evaluate(TABLE), tag + f"[rank {other}] ")
    page.keyboard.press("Escape")
    _settle(page, 250)
    snap = page.evaluate(SNAP)
    if snap["expanded"] is not None or snap["active"] != "v2ExpandTable":
        errors.append(tag + f"Esc on the expanded table: expanded {snap['expanded']}, focus {snap['active']!r}")
    _force_close(page)
    page.click("#v2Reset")
    _settle(page, 300)
    return errors


def check_reset_zoom(page, tag) -> list[str]:
    errors = []
    page.fill("#v2Search", "a")
    _settle(page, 300)
    page.select_option("#v2Show", "50")
    _settle(page)
    if page.evaluate(SNAP)["resetZoom"]:
        errors.append(tag + "Reset zoom shows before any zoom")
    page.click("#v2ZoomIn")
    _settle(page)
    snap = page.evaluate(SNAP)
    if snap["preset"] != "custom" or not snap["resetZoom"]:
        errors.append(tag + f"zoom in: preset {snap['preset']}, Reset zoom shown {snap['resetZoom']}")
    page.click("#v2ResetZoom")
    _settle(page)
    snap = page.evaluate(SNAP)
    if snap["preset"] != "50" or snap["show"] != "50" or snap["window"] != [1, min(50, snap["n"])] or snap["resetZoom"]:
        errors.append(tag + f"Reset zoom after Top 50: preset {snap['preset']} Show {snap['show']} window {snap['window']}")
    if snap["search"] != "a":
        errors.append(tag + "Reset zoom cleared the search")
    # A Y brush is a zoom too.
    page.select_option("#v2Show", "25")
    _set_range_input(page, "v2YBrushLo", 5)
    page.click("#v2ResetZoom")
    _settle(page)
    snap = page.evaluate(SNAP)
    if snap["preset"] != "25" or snap["range"] != {"min": None, "max": None}:
        errors.append(tag + f"Reset zoom after a Y brush: preset {snap['preset']} range {snap['range']}")
    page.click("#v2Reset")
    _settle(page)
    return errors


def _apply_all_filters(page):
    page.click("#v2Reset")
    _settle(page)
    page.fill("#v2Search", "a")
    _settle(page, 300)
    page.select_option("#v2Position", "WR")
    _settle(page)
    _set_range_input(page, "v2BrushLo", 3)
    _set_range_input(page, "v2BrushHi", 30)
    _set_range_input(page, "v2YBrushLo", 2)
    _set_range_input(page, "v2YBrushHi", 40)


def check_chips(page, tag) -> list[str]:
    errors = []
    _apply_all_filters(page)
    full = page.evaluate(SNAP)
    texts = {c["id"]: c["text"] for c in full["chips"]}
    want = {"range": "Value 2–40 ✕", "ranks": "Ranks 3–30 ✕", "search": "Search: a ✕", "position": "Position: WR ✕"}
    if texts != want:
        errors.append(tag + f"filter chips {texts}, want {want}")
    filters = lambda s: {"range": s["range"], "ranks": s["window"] if s["preset"] == "custom" else None,
                         "search": s["search"], "position": s["position"]}
    cleared = {"range": {"min": None, "max": None}, "search": "", "position": "ALL"}
    for chip in ("range", "ranks", "search", "position"):
        _apply_all_filters(page)
        before = filters(page.evaluate(SNAP))
        if not page.locator(f"#v2FilterChips [data-chip='{chip}']").count():
            errors.append(tag + f"chip {chip} missing")
            continue
        page.click(f"#v2FilterChips [data-chip='{chip}']")
        _settle(page, 250)
        snap = page.evaluate(SNAP)
        after = filters(snap)
        for other in before:
            if other == chip:
                if other == "ranks":
                    if after["ranks"] == before["ranks"]:
                        errors.append(tag + f"chip ranks: rank window still {after['ranks']}")
                elif after[other] != cleared[other]:
                    errors.append(tag + f"chip {chip}: filter not cleared ({after[other]})")
            elif after[other] != before[other]:
                errors.append(tag + f"chip {chip} also changed {other}: {before[other]} -> {after[other]}")
        if any(c["id"] == chip for c in snap["chips"]):
            errors.append(tag + f"chip {chip} still shown after clearing")
    page.click("#v2Reset")
    _settle(page)
    exact = page.evaluate("() => { const b = document.getElementById('v2YExact'); const r = b.getBoundingClientRect();"
                          " return {h: r.height, w: r.width, font: parseFloat(getComputedStyle(b).fontSize)}; }")
    if exact["h"] < 44 or exact["w"] < 44 or exact["font"] < 12:
        errors.append(tag + f"Set exact values is not a 44 px control: {exact}")
    return errors


def _serve(body, ctype, route, *_):
    route.fulfill(status=200, content_type=ctype, body=body)


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
                yield f"http://127.0.0.1:{server.server_address[1]}/v2/"
            finally:
                server.shutdown()


CHECKS = ("chart", "table", "reset", "chips")


def run_checks(overrides=None, viewports=((1440, 900), (390, 844)), checks=CHECKS) -> list[str]:
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        raise _render_env.unavailable(f"Playwright is not available: {exc}") from exc
    errors = []
    with _built_dist() as base, sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(args=_render_env.HERMETIC_ARGS, executable_path=_chromium_executable(playwright))
        except PlaywrightError as exc:
            raise _render_env.unavailable(f"Chromium is not available: {exc}") from exc
        try:
            for width, height in viewports:
                tag = f"[{width}px] "
                context = browser.new_context(viewport={"width": width, "height": height})
                page = context.new_page()
                page_errors = []
                page.on("pageerror", lambda e: page_errors.append(str(e)))
                page.route(lambda u: not u.startswith("http://127.0.0.1"), lambda route: route.abort())
                for name, (body, ctype) in (overrides or {}).items():
                    page.route(f"**/v2/{name}*", functools.partial(_serve, body, ctype))
                page.goto(base + "#player-values", wait_until="networkidle")
                page.wait_for_function("() => window.TradeValueV2 && document.querySelector('#v2Table tbody tr')", timeout=60000)
                _settle(page, 400)
                if "chart" in checks:
                    errors += check_expanded_chart(page, tag, width)
                if "table" in checks:
                    errors += check_expanded_table(page, tag, width)
                if width >= 1280 and "reset" in checks:
                    errors += check_reset_zoom(page, tag)
                if "chips" in checks:
                    errors += check_chips(page, tag)
                if width <= 390:
                    _apply_all_filters(page)
                    overflow = page.evaluate("() => document.documentElement.scrollWidth - innerWidth")
                    if overflow > 0:
                        errors.append(tag + f"horizontal overflow {overflow}px with every filter chip shown")
                if page_errors:
                    errors.append(tag + f"page errors {page_errors}")
                context.close()
        finally:
            browser.close()
    return errors


class ExpandRenderTest(unittest.TestCase):
    def test_expand_reset_zoom_and_filter_chips(self):
        self.assertEqual(run_checks(), [])

    def test_guard_fails_on_broken_builds(self):
        v2 = V2_JS.read_text(encoding="utf-8")
        css = V2_CSS.read_text(encoding="utf-8")
        js, cs = "text/javascript", "text/css"
        broken = {
            "expanded chart drops a line": ("chart", {"v2.js": (v2.replace(
                'mainChart = drawSeriesChart($("v2Chart"), view.plotKeys, {',
                'mainChart = drawSeriesChart($("v2Chart"), big ? view.plotKeys.slice(1) : view.plotKeys, {', 1), js)}),
            "Esc leaves the expanded view open": ("chart", {"v2.js": (v2.replace(
                "      else if (expanded) closeExpanded();\n", "", 1), js)}),
            "focus not returned to the expand button": ("chart", {"v2.js": (v2.replace(
                "      if (!silent) opener.focus();\n", "", 1), js)}),
            "expanded table keeps Pos / Team / Tier folded": ("table", {"v2.js": (v2.replace(
                'const metaColumnsShown = () => expanded === "table" ||', 'const metaColumnsShown = () => false ||', 1), js)}),
            "Tier read from ESPN": ("table", {"v2.js": (v2.replace(
                'get: row => valuesTier(row), text: true,', 'get: row => tierLabel(row.espnRole), text: true,', 1), js)}),
            "Reset zoom ignores the remembered preset": ("reset", {"v2.js": (v2.replace(
                "    if (state.windowPreset !== \"custom\") state.zoomFrom = state.windowPreset;\n", "", 1), js)}),
            "value chip also clears search": ("chips", {"v2.js": (v2.replace(
                "clear: () => setRange({min: null, max: null})});",
                "clear: () => { state.search = \"\"; $(\"v2Search\").value = \"\"; setRange({min: null, max: null}); }});", 1), js)}),
            "ranks chip also clears the value range": ("chips", {"v2.js": (v2.replace(
                "  function clearRankZoom() {\n", "  function clearRankZoom() {\n    state.range = {min: null, max: null};\n", 1), js)}),
            "Set exact values a small link": ("chips", {"v2.css": (css.replace(
                ".v2-app .v2-yexact { margin-left: auto; min-height: 44px; padding: 8px 12px; font-size: 13px;",
                ".v2-app .v2-yexact { margin-left: auto; min-height: 30px; padding: 0 2px; font-size: 10px;", 1), cs)}),
        }
        for name, (check, overrides) in broken.items():
            with self.subTest(mutation=name):
                for file, (body, _) in overrides.items():
                    source = {"v2.js": v2, "v2.css": css}[file]
                    self.assertNotEqual(body, source, f"mutation anchor for {name!r} is stale")
                self.assertNotEqual(run_checks(overrides, viewports=((1440, 900),), checks=(check,)), [],
                                    f"render checks did not catch: {name}")


if __name__ == "__main__":
    unittest.main()
