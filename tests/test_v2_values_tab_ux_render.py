"""Player values tab: chart layout, search on the graph, source symbols, exact values, player page numbers (JEG-926), rendered.

Jeremy, 2026-10-22. Builds dist/v2 into a temp copy of the built dist/ and loads Player values headless at 1366, 1280,
1024 and 390 px. Each value check reads the engine back (TradeValueCurveControls / TradeValueV2), so a view that only
looks right fails:

  1. Layout: the chart card spans the full content width and the values table card sits underneath it (same left and
     right edge, table top below chart bottom), at every width; no horizontal overflow at 390.
  2. Search on the graph: #v2PlotSearch is inside the chart, visible, and drives the same search as the toolbar box
     (engine rows narrow to the match, the toolbar box mirrors it, clearing restores the list).
  3. Source symbols: every plotted series has its publisher symbol (the legend's) on the chart, anchored at that
     series' left-most visible player (x equals the chart's x for the first player the series prices), and the symbols
     follow the left-most player when the rank window or position changes.
  4. Expanded chart: the position selector is visible on the graph (inside #v2Plot, inside the dialog), changing it
     changes the engine's position and the toolbar's; hidden in the unexpanded chart (the toolbar has it there).
  5. "Set exact values": no separate toolbar button; it is an item in the Show menu. Picking it (mouse or keyboard
     typeahead) opens the Value range dialog, leaves Show as it was, and Escape returns focus to the Show menu.
  6. Player page (Jeremy, 2026-10-23, replacing 2026-10-22's "every series with an Add link"): by default it lists
     only the sources selected through the chart controls, each with the engine's number (one decimal); no row has an
     empty value, no "Add" link exists; a clearly labelled "Show all sources" toggle is off by default, and turning
     it on lists every source that has a number for the player (engine values) and writes nothing to storage.

Discrimination: test_guard_fails_on_broken_builds serves v2.js / v2.css with one fault each (table back beside the
chart, search box not forwarded, symbols not drawn, symbols at the right end, position hidden when expanded, exact
values not in the Show menu, unselected sources listed by default, toggle on by default, toggle ignored, a source row
with no number) and requires each to fail.
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

LAYOUT = """() => { const r = s => { const e = document.querySelector(s); if (!e) return null; const b = e.getBoundingClientRect();
  return {left: b.left, right: b.right, top: b.top + scrollY, bottom: b.bottom + scrollY, width: b.width}; };
  return {chart: r('.v2-chart-card'), table: r('.v2-table-card'), main: r('#v2Main'), overflow: document.documentElement.scrollWidth - innerWidth}; }"""

# Symbols against the engine: for each plotted series, where its symbol sits and where the chart puts that series'
# first priced player.
MARKS = """() => { const V2 = window.TradeValueV2, ch = V2.chart(), C = window.TradeValueCurveControls;
  const byKey = new Map(C.getRows().map(r => [String(r.player_key), r]));
  const keys = [...document.querySelectorAll('#v2Chart path.series')].map(p => p.dataset.source);
  const legend = document.getElementById('v2Legend') ? document.getElementById('v2Legend').textContent : '';
  const marks = [...document.querySelectorAll('#v2Chart text.series-mark')].map(t => ({key: t.dataset.source, text: t.textContent,
    x: Number(t.getAttribute('x')), y: Number(t.getAttribute('y'))}));
  const want = keys.map(key => { const i = ch.slice.findIndex(r => Number.isFinite(byKey.get(String(r.player_key)).values[key]));
    return {key, x: i < 0 ? null : ch.x(i), first: i < 0 ? null : ch.slice[i].name, leftmost: ch.slice[0].name}; });
  return {keys, marks, want, legend, plotH: ch.height, n: ch.slice.length}; }"""

SEARCH = """() => { const V2 = window.TradeValueV2, v = V2.view();
  const box = document.getElementById('v2PlotSearch'), r = box.getBoundingClientRect();
  return {state: V2.state.search, toolbar: document.getElementById('v2Search').value, chartBox: box.value,
    inChart: Boolean(box.closest('.v2-chart-card')), visible: Boolean(box.offsetParent) && r.width > 40 && r.height > 20,
    rows: v.rows.length, names: v.rows.slice(0, 20).map(x => x.name)}; }"""

DRAWER = """() => { const V2 = window.TradeValueV2, drawer = document.getElementById('v2Drawer');
  const key = document.querySelector('#v2Table tbody tr').dataset.playerKey || V2.view().rows[0].player_key;
  const row = window.TradeValueCurveControls.getRows().find(r => String(r.player_key) === String(key));
  const view = V2.view();
  const selected = view.active.filter(k => k === view.rankKey || !V2.state.hiddenSeries.has(k));
  const available = view.info.filter(i => i.available).map(i => i.key)
    .concat(['ddf_value', 'ddf_value_charts', 'ddf_value_projections'].filter(k => row && Number.isFinite(row.values[k]) && !view.info.some(i => i.key === k)));
  const toggle = document.getElementById('v2DrawerAll');
  const label = toggle ? toggle.closest('label') : null;
  const rows = [...drawer.querySelectorAll('.v2-dmatrix tbody tr')].map(tr => { const v = tr.querySelector('td.num:last-child') || tr;
    const kind = tr.querySelector('td.kind');
    return {key: tr.dataset.source, kind: kind ? kind.textContent : '', hasNumber: Boolean(v.dataset && v.dataset.source), text: v.textContent.trim()}; });
  const store = JSON.stringify([Object.entries(localStorage), Object.entries(sessionStorage)]);
  return {hidden: drawer.hidden, values: row ? row.values : null, rows, selected, available, store,
    toggle: toggle ? {checked: toggle.checked, label: label.textContent.trim(), visible: Boolean(toggle.offsetParent)} : null,
    addControls: drawer.querySelectorAll('.v2-dadd, [data-add-series]').length,
    addText: /\\bAdd\\b[^a-z]*↗|Available ↗/.test(drawer.textContent),
    overflow: document.documentElement.scrollWidth - innerWidth}; }"""


def _settle(page, ms=150):
    page.wait_for_timeout(ms)


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


def check_layout(page, tag, width) -> list[str]:
    errors = []
    page.evaluate("() => window.scrollTo(0, 0)")
    lay = page.evaluate(LAYOUT)
    chart, table = lay["chart"], lay["table"]
    if not chart or not table:
        return [tag + "chart or table card missing"]
    if abs(chart["left"] - table["left"]) > 1 or abs(chart["right"] - table["right"]) > 1:
        errors.append(tag + f"chart card ({chart['left']:.0f}-{chart['right']:.0f}) and table card "
                      f"({table['left']:.0f}-{table['right']:.0f}) do not share the full content width")
    if table["top"] < chart["bottom"] - 1:
        errors.append(tag + f"table starts at {table['top']:.0f}px, inside the chart card (ends {chart['bottom']:.0f}px): side by side")
    if chart["width"] < 0.9 * lay["main"]["width"]:
        errors.append(tag + f"chart card is {chart['width']:.0f}px of {lay['main']['width']:.0f}px content width")
    if width <= 390 and lay["overflow"] > 0:
        errors.append(tag + f"horizontal overflow {lay['overflow']}px")
    return errors


def check_search(page, tag) -> list[str]:
    errors = []
    base = page.evaluate(SEARCH)
    if not base["inChart"] or not base["visible"]:
        return [tag + f"search box is not visible on the graph: {base}"]
    page.fill("#v2PlotSearch", "Chase")
    _settle(page, 500)
    snap = page.evaluate(SEARCH)
    if snap["state"] != "Chase" or snap["toolbar"] != "Chase":
        errors.append(tag + f"typing on the graph: search state {snap['state']!r}, toolbar box {snap['toolbar']!r}")
    if not (0 < snap["rows"] < base["rows"]) or not all("chase" in n.lower() for n in snap["names"]):
        errors.append(tag + f"typing on the graph did not narrow the engine rows to the match: {snap['rows']} rows {snap['names'][:3]}")
    # The toolbar box drives the on-graph box too.
    page.fill("#v2Search", "")
    _settle(page, 500)
    back = page.evaluate(SEARCH)
    if back["chartBox"] != "" or back["rows"] != base["rows"]:
        errors.append(tag + f"clearing the toolbar search: graph box {back['chartBox']!r}, rows {back['rows']} (was {base['rows']})")
    return errors


def check_marks(page, tag) -> list[str]:
    errors = []

    def read(label):
        snap = page.evaluate(MARKS)
        if not snap["keys"]:
            return [label + "no series plotted"]
        found = {m["key"]: m for m in snap["marks"]}
        problems = []
        for want in snap["want"]:
            mark = found.get(want["key"])
            if want["x"] is None:
                continue
            if not mark:
                problems.append(label + f"{want['key']}: no source symbol on the chart")
                continue
            if abs(mark["x"] - want["x"]) > 0.6:
                problems.append(label + f"{want['key']}: symbol at x={mark['x']:.1f}, the series' left-most visible player "
                                f"({want['first']}) is at x={want['x']:.1f}")
            if mark["text"] not in snap["legend"]:
                problems.append(label + f"{want['key']}: symbol {mark['text']!r} is not the legend's")
            if not (0 <= mark["y"] <= snap["plotH"]):
                problems.append(label + f"{want['key']}: symbol at y={mark['y']:.0f} is outside the plot")
        ys = sorted(m["y"] for m in snap["marks"])
        if any(b - a < 10 for a, b in zip(ys, ys[1:])):
            problems.append(label + f"symbols overlap: y positions {[round(y) for y in ys]}")
        return problems
    errors += read(tag + "Top 100: ")
    page.select_option("#v2Show", "25")
    page.select_option("#v2Position", "WR")
    _settle(page, 300)
    errors += read(tag + "Top 25 WR: ")
    page.click("#v2Reset")
    _settle(page, 300)
    return errors


def check_expanded_position(page, tag) -> list[str]:
    errors = []
    hidden = page.evaluate("() => { const s = document.getElementById('v2PlotPosition'); return !s.offsetParent; }")
    if not hidden:
        errors.append(tag + "the position selector is on the unexpanded chart as well as the toolbar")
    page.click("#v2ExpandChart")
    _settle(page, 300)
    info = page.evaluate("""() => { const s = document.getElementById('v2PlotPosition'), r = s.getBoundingClientRect();
      const plot = document.getElementById('v2Plot').getBoundingClientRect();
      return {visible: Boolean(s.offsetParent) && r.width > 40 && r.height > 20, inDialog: Boolean(s.closest('#v2Expand')),
        inPlot: Boolean(s.closest('#v2Plot')), within: r.top >= plot.top - 1 && r.bottom <= plot.bottom + 1,
        search: Boolean(document.getElementById('v2PlotSearch').offsetParent)}; }""")
    if not (info["visible"] and info["inDialog"] and info["inPlot"] and info["within"]):
        errors.append(tag + f"expanded chart: the position selector is not visible on the graph: {info}")
    if not info["search"]:
        errors.append(tag + "expanded chart: the search box is not on the graph")
    elif info["visible"]:
        page.select_option("#v2PlotPosition", "RB")
        _settle(page, 400)
        got = page.evaluate("() => ({engine: window.TradeValueCurveControls.getState().position, toolbar: document.getElementById('v2Position').value,"
                            " rows: window.TradeValueV2.view().visible.map(r => r.pos)})")
        if got["engine"] != "RB" or got["toolbar"] != "RB" or any(p != "RB" for p in got["rows"]) or not got["rows"]:
            errors.append(tag + f"expanded chart: position selector did not set RB: {got['engine']} / {got['toolbar']} / {set(got['rows'])}")
    page.keyboard.press("Escape")
    _settle(page, 300)
    page.click("#v2Reset")
    _settle(page, 300)
    return errors


def check_exact(page, tag) -> list[str]:
    errors = []
    if page.query_selector("#v2YExact"):
        errors.append(tag + "the separate Set exact values button is still on the page")
    opts = page.evaluate("() => [...document.querySelectorAll('#v2Show option')].map(o => o.textContent.trim())")
    if not any(o.lower().startswith("set exact values") for o in opts):
        return errors + [tag + f"Show menu has no Set exact values item: {opts}"]
    page.select_option("#v2Show", "50")
    _settle(page)
    # Mouse / pointer path.
    page.select_option("#v2Show", "exact")
    _settle(page, 300)
    snap = page.evaluate("""() => ({open: !document.getElementById('v2Popover').hidden,
      title: (document.querySelector('#v2Popover .v2-panel-head') || {}).textContent || '', show: document.getElementById('v2Show').value,
      preset: window.TradeValueV2.state.windowPreset})""")
    if not snap["open"] or "Value range" not in snap["title"]:
        errors.append(tag + f"Set exact values did not open the Value range dialog: {snap}")
    if snap["show"] != "50" or snap["preset"] != "50":
        errors.append(tag + f"Set exact values changed Show to {snap['show']!r} / {snap['preset']!r}, want 50")
    page.keyboard.press("Escape")
    _settle(page, 300)
    back = page.evaluate("() => ({open: !document.getElementById('v2Popover').hidden, focus: document.activeElement && document.activeElement.id})")
    if back["open"] or back["focus"] != "v2Show":
        errors.append(tag + f"closing the dialog: open {back['open']}, focus on {back['focus']!r}, want the Show menu")
    # Keyboard path: focus the menu and type the item's first letters.
    page.focus("#v2Show")
    page.keyboard.type("Set exact")
    _settle(page, 400)
    kb = page.evaluate("() => ({open: !document.getElementById('v2Popover').hidden, show: document.getElementById('v2Show').value})")
    if not kb["open"]:
        errors.append(tag + f"keyboard (typeahead on the Show menu) did not open the dialog: {kb}")
    # And the dialog still applies a range.
    if kb["open"]:
        inputs = page.locator("#v2Popover .row2 input")
        inputs.nth(0).fill("10")
        inputs.nth(1).fill("40")
        page.click('#v2Popover [data-apply="range"]')
        _settle(page, 300)
        applied = page.evaluate("() => window.TradeValueV2.state.range")
        if applied["min"] != 10 or applied["max"] != 40:
            errors.append(tag + f"the Value range dialog applied {applied}, want 10 to 40")
    page.click("#v2Reset")
    _settle(page, 300)
    return errors


def _finite(value):
    return isinstance(value, (int, float)) and value == value and abs(value) != float("inf")


def _check_rows(d, tag, want_keys) -> list[str]:
    """Rows listed must be exactly want_keys (those with a number), each showing the engine's number; none blank."""
    errors = []
    values = d["values"] or {}
    numbered = [r for r in d["rows"] if r["hasNumber"]]
    for r in d["rows"]:
        if not r["text"]:
            errors.append(tag + f"player page row {r['key']} has an empty value cell")
        if r["hasNumber"] and not any(ch.isdigit() for ch in r["text"]):
            errors.append(tag + f"player page row {r['key']} is listed without a number: {r['text']!r}")
    for r in numbered:
        want = values.get(r["key"])
        if not _finite(want):
            errors.append(tag + f"player page lists {r['key']} but the engine has no number for this player")
        elif not r["text"].startswith(f"{want:.1f}"):
            errors.append(tag + f"player page {r['key']} shows {r['text']!r}, engine {want!r}")
    got = sorted(r["key"] or "" for r in numbered)
    want_sorted = sorted(k for k in want_keys if _finite(values.get(k)))
    if got != want_sorted:
        errors.append(tag + f"player page lists {got}, want {want_sorted}")
    return errors


# The selected-source player gap: the listed player missing the most selected sources (so a player missing both a
# DDF Value version and a publisher's series is preferred, and both drawer row builders are exercised).
GAP = """() => { const V2 = window.TradeValueV2, v = V2.view();
  const sel = v.active.filter(k => k === v.rankKey || !V2.state.hiddenSeries.has(k));
  const missed = r => sel.filter(k => !Number.isFinite(r.values[k]));
  const r = window.TradeValueCurveControls.getRows().reduce((best, r) => (missed(r).length > (best ? missed(best).length : 0) ? r : best), null);
  return r ? {name: r.name, missing: missed(r)} : null; }"""

# Sources to select when the default selection prices every listed player: take the listed player that the most
# available, unselected sources leave unpriced, and select one DDF Value version and one publisher series that player lacks,
# with the page's own setShown (what Customize's Done does). Returns the keys added, or null when no source has a gap.
SELECT_GAP_SOURCES = """() => { const V2 = window.TradeValueV2, shown = V2.shown();
  const rows = window.TradeValueCurveControls.getRows();
  const keys = V2.view().info.filter(i => i.available && !shown.includes(i.key)
    && rows.some(r => Number.isFinite(r.values[i.key]))).map(i => i.key);
  const missed = r => keys.filter(k => !Number.isFinite(r.values[k]));
  const row = rows.reduce((best, r) => (missed(r).length > missed(best).length ? r : best), rows[0]);
  const gaps = row ? missed(row) : [];
  const isDdf = k => k.startsWith("ddf_value");
  const pick = [gaps.find(isDdf), gaps.find(k => !isDdf(k))].filter(Boolean);
  if (pick.length) V2.setShown(shown.concat(pick));
  return pick.length ? pick : null; }"""


def check_drawer(page, tag) -> list[str]:
    errors = []
    page.click("#v2Table tbody tr td:nth-child(2)")
    _settle(page, 600)
    d = page.evaluate(DRAWER)
    if d["hidden"]:
        return [tag + "player page did not open"]
    values = d["values"] or {}
    unselected = [k for k in d["available"] if k not in d["selected"] and _finite(values.get(k))]
    if not unselected:
        errors.append(tag + "player page: no unselected source with a number in the fixture, so the check proves nothing")
    errors += _check_rows(d, tag + "(default) ", d["selected"])
    if not d["rows"]:
        errors.append(tag + "player page lists no sources by default")
    if d["addControls"] or d["addText"]:
        errors.append(tag + "player page still has an Add control")
    if not d["toggle"] or not d["toggle"]["visible"]:
        return errors + [tag + "player page has no visible 'Show all sources' toggle"]
    if d["toggle"]["label"] != "Show all sources":
        errors.append(tag + f"toggle is labelled {d['toggle']['label']!r}")
    if d["toggle"]["checked"]:
        errors.append(tag + "'Show all sources' is on by default")
    if d["overflow"] > 0 and tag.startswith("390"):
        errors.append(tag + f"horizontal overflow {d['overflow']}px")
    page.click("#v2DrawerAll")
    _settle(page, 300)
    on = page.evaluate(DRAWER)
    errors += _check_rows(on, tag + "(all) ", on["available"])
    if not on["toggle"] or not on["toggle"]["checked"]:
        errors.append(tag + "'Show all sources' did not stay on after clicking it")
    for k in unselected:
        if k not in [r["key"] for r in on["rows"]]:
            errors.append(tag + f"'Show all sources' does not list {k}, which has a number")
    if on["store"] != d["store"]:
        errors.append(tag + "'Show all sources' wrote to local or session storage")
    if on["addControls"]:
        errors.append(tag + "Add control present with all sources shown")
    page.click("#v2DrawerAll")
    _settle(page, 300)
    off = page.evaluate(DRAWER)
    errors += _check_rows(off, tag + "(off again) ", off["selected"])
    page.keyboard.press("Escape")
    _settle(page, 300)
    # A player the engine leaves unpriced for a selected source: that source gets no row (never a blank one).
    gap = page.evaluate(GAP)
    if not gap:
        # Since 679fa54e (JEG-1073) DDF Value is the trade-chart average and every chart is filled to the
        # rosterable set (fill-in rule, OC-5), so the default selection prices every listed player. Select a
        # source that leaves a listed player unpriced (a projection), as Customize's Done would, and look again.
        added = page.evaluate(SELECT_GAP_SOURCES)
        _settle(page, 600)
        gap = page.evaluate(GAP) if added else None
    if not gap:
        return errors + [tag + "fixture has no player unpriced for a selectable source, so the no-blank-row check proves nothing"]
    page.fill("#v2Search", gap["name"])
    _settle(page, 600)
    page.click("#v2Table tbody tr td:nth-child(2)")
    _settle(page, 600)
    g = page.evaluate(DRAWER)
    errors += _check_rows(g, tag + f"({gap['name']}) ", [k for k in g["selected"] if k not in gap["missing"]])
    for key in gap["missing"]:
        if key in [r["key"] for r in g["rows"]]:
            errors.append(tag + f"{gap['name']} has no {key} number but the player page lists it")
    page.keyboard.press("Escape")
    page.fill("#v2Search", "")
    _settle(page, 300)
    return errors


CHECKS = ("layout", "search", "marks", "expanded", "exact", "drawer")
VIEWPORTS = ((1366, 800), (1280, 800), (1024, 768), (390, 844))


def run_checks(overrides=None, viewports=VIEWPORTS, checks=CHECKS) -> list[str]:
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
                page.add_init_script(_render_env.pin_data_week_script())   # JEG-1152: the data's week, not the calendar's
                page.goto(base + "#player-values", wait_until="networkidle")
                page.wait_for_function("() => window.TradeValueV2 && document.querySelector('#v2Table tbody tr')", timeout=60000)
                _settle(page, 400)
                deep = width in (1366, 390)
                if "layout" in checks:
                    errors += check_layout(page, tag, width)
                if "search" in checks and deep:
                    errors += check_search(page, tag)
                if "marks" in checks and deep:
                    errors += check_marks(page, tag)
                if "expanded" in checks and deep:
                    errors += check_expanded_position(page, tag)
                if "exact" in checks and deep:
                    errors += check_exact(page, tag)
                if "drawer" in checks and deep:
                    errors += check_drawer(page, tag)
                if width <= 390:
                    overflow = page.evaluate("() => document.documentElement.scrollWidth - innerWidth")
                    if overflow > 0:
                        errors.append(tag + f"horizontal overflow {overflow}px")
                if page_errors:
                    errors.append(tag + f"page errors {page_errors}")
                context.close()
        finally:
            browser.close()
    return errors


class ValuesTabUxRenderTest(unittest.TestCase):
    def test_values_tab_ux(self):
        self.assertEqual(run_checks(), [])

    def test_guard_fails_on_broken_builds(self):
        js = V2_JS.read_text(encoding="utf-8")
        css = V2_CSS.read_text(encoding="utf-8")
        broken = {
            "table beside the chart again": ({"v2.css": css + "\n@media (min-width: 1280px) { .v2-values-grid { display: grid; grid-template-columns: 420px 1fr; gap: 12px; } }\n"},
                                             "css", ("layout",), ((1366, 800),)),
            "search box not forwarded": ({"v2.js": js.replace(
                '      $("v2Search").dispatchEvent(new Event("input", {bubbles: true}));\n', "", 1)}, "js", ("search",), ((1366, 800),)),
            "source symbols not drawn": ({"v2.js": js.replace("if (opts.markers) drawSeriesMarkers(", "if (false) drawSeriesMarkers(", 1)},
                                         "js", ("marks",), ((1366, 800),)),
            "source symbols at the right end": ({"v2.js": js.replace(
                "const i = slice.findIndex(row => Number.isFinite(row.values[key]));",
                "const i = slice.length - 1 - [...slice].reverse().findIndex(row => Number.isFinite(row.values[key]));", 1)},
                                                "js", ("marks",), ((1366, 800),)),
            "position hidden when expanded": ({"v2.css": css.replace(
                ".v2-expand .v2-plot-pos { display: flex; }", ".v2-expand .v2-plot-pos { display: none; }", 1)},
                                              "css", ("expanded",), ((1366, 800),)),
            "exact values not in the Show menu": ({"v2.js": js.replace(
                'if (event.target.value === "exact") {', 'if (false) {', 1)}, "js", ("exact",), ((1366, 800),)),
            "unselected sources listed by default": ({"v2.js": js.replace(
                "        if (!selected && !all) return;\n", "", 1)}, "js", ("drawer",), ((1366, 800),)),
            "toggle on by default": ({"v2.js": js.replace(
                "let drawerAllSources = false;", "let drawerAllSources = true;", 1)}, "js", ("drawer",), ((1366, 800),)),
            "toggle ignored": ({"v2.js": js.replace(
                "drawerSourceRows(row, drawerAllSources)", "drawerSourceRows(row, false)", 1)}, "js", ("drawer",), ((1366, 800),)),
            "a source row with no number": ({"v2.js": js.replace(
                "if ((selected || all) && Number.isFinite(value)) {", "if (selected || all) {", 1)},
                                            "js", ("drawer",), ((1366, 800),)),
            "a publisher row with no number": ({"v2.js": js.replace(
                "        if (has) rows.push({pub, method, label, item, value: row.values[item.key], selected});\n",
                "        rows.push({pub, method, label, item, value: row.values[item.key], selected});\n", 1)},
                                               "js", ("drawer",), ((1366, 800),)),
        }
        for name, (files, kind, checks, viewports) in broken.items():
            with self.subTest(mutation=name):
                (fname, body), = files.items()
                self.assertNotEqual(body, js if kind == "js" else css, f"mutation anchor for {name!r} is stale")
                overrides = {fname: (body, "text/javascript" if kind == "js" else "text/css")}
                self.assertNotEqual(run_checks(overrides, viewports=viewports, checks=checks), [],
                                    f"render checks did not catch: {name}")


if __name__ == "__main__":
    unittest.main()
