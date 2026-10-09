"""v2 settings panels and the Player values toolbar, brushes and table (frames 09–12, 20, 24; JEG-470/472/473/475), rendered.

Builds dist/v2 into a temp copy of the built dist/ and loads Player values
headless at 1440 × 900, 1366 × 768 and 390. Every check reads the engine back
(TradeValueCurveControls), so a control that only looks right fails:

  * Choose your sources (09 / 20): toggling a pair changes nothing until
    Apply; Apply adds exactly that pair to getActiveSources(); Cancel
    discards; an empty draft cannot be applied ("Choose at least one");
    an unavailable pair is disabled; full screen at 390;
  * Your league (12): steppers and segmented buttons are a draft; Apply sets
    getRosterShape() / getState().teams, SUPERFLEX included; a change that
    moves the bench share says so (JEG-444); Reset defaults returns to the
    first-load league;
  * Weights & bench (11): position shares shown equal getPositionWeights();
    an edited share reaches the engine on Apply (setPositionWeights) and the
    shares still total 1; Reset defaults returns them to
    getDefaultPositionWeights(); Apply sets getBenchShare() to the slider;
  * Source freshness (10, JEG-463): one row per root source (publisher), Prior
    week where the data's freshness record says so, no pipeline jargon; a
    failed import in reference-freshness.json shows that source as Not
    updating and warns on the header chip; fail closed: with the file missing
    (404) every source shows "Freshness unknown" (no tick) and the chip says
    "unconfirmed"; a source whose own rows are missing is unknown while the
    rest are current;
  * toolbar (JEG-475): Search · Position · Show · Rank by · Δ · More · Reset,
    each exactly once, left to right, sticky; the chart-options box, rank
    window buttons, Reset to all / Reset zoom / Clear filters are gone; only
    brushes and zoom sit inside the chart; Show Top 25 / Starters / Bench /
    Waiver follow getZones(); a brush drag sets Show to "Custom lo–hi"; More
    holds exact From / To ranks; one Reset restores every default;
  * Y value brush (JEG-472): two labelled vertical range inputs with
    "Value x.x" text; mouse drag and PageDown / arrows move it; it keeps only
    players whose ranking-series value is inside the bounds AND whose rank is
    inside the rank window; players without a basis value are counted; the
    "Set exact values" popover names its basis and refuses min > max; below
    768 px the popover replaces the brush;
  * table (JEG-473): no sideways scroll at the default selection, headers at
    most two lines under a method-group row that matches each series' method,
    sticky header row and Player column, compact rows, right-aligned
    one-decimal numbers with 6–8 px padding, heat tint direction matching the
    two shown values and named in the title, "—" with a reason; the Columns
    menu hides a group but never the ranking series;
  * above the fold (JEG-470): at 1440 × 900 and 1366 × 768 the chart card and
    at least six table rows are visible without scrolling; h1 26–28 px; the
    value line names the engine's week;
  * no page errors, no horizontal overflow at 390.

Discrimination: test_guard_fails_on_broken_builds serves v2.js / v2.css with
one fault each (pair toggle applied at once, zone preset ignored, Team box
ignored, From / To ignored, brush drag keeps the preset, value range ignores
the rank window, Y brush does nothing, Reset keeps the value range, Columns
menu ignored, no SUPERFLEX stepper, bench move not reported, shares not
applied, freshness fails open, league Apply does nothing, no chart-and-table split, header not
sticky, cells wide enough to scroll sideways) and requires each to fail.
"""
from __future__ import annotations

import contextlib
import functools
import http.server
import json
import re
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
V2_CSS = ROOT / "app" / "v2" / "v2.css"
ACTIVE = "() => window.TradeValueV2.shown()"


def _serve(body, route, *_):
    route.fulfill(status=200, content_type="text/javascript", body=body)


def _serve_css(body, route, *_):
    route.fulfill(status=200, content_type="text/css", body=body)


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
        # Two pages load at once in check_freshness; the default backlog (5) refuses connections under load.
        class Server(socketserver.ThreadingTCPServer):
            request_queue_size = 128
        with Server(("127.0.0.1", 0), handler) as server:
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
    info = page.evaluate("() => Object.fromEntries(window.TradeValueCurveControls.getSourceInfo({includeComposite: true}).map(i => [i.key, i]))")
    pairs = page.evaluate("""() => [...document.querySelectorAll('#v2Popover [data-series]')].map(b => ({key: b.dataset.series,
      on: b.checked === true || b.getAttribute('aria-pressed') === 'true', disabled: b.disabled}))""")
    for p in pairs:
        if not info[p["key"]]["available"] and not p["disabled"]:
            errors.append(f"sources: unavailable {p['key']} is offered")
        if p["on"] != (p["key"] in before):
            errors.append(f"sources: {p['key']} pressed={p['on']} but engine active={p['key'] in before}")
    add = next((p["key"] for p in pairs if not p["on"] and not p["disabled"] and not p["key"].endswith("_vorp")), None)
    if not add:
        return errors + ["sources: no pair to add"]
    page.click(f'#v2Popover [data-series="{add}"]')
    if page.evaluate(ACTIVE) != before:
        errors.append("sources: a toggle reached the engine before Apply")
    page.click("#v2Popover .v2-panel-foot button:has-text('Cancel')")
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
    # Position shares (frame 11, JEG-452): the edited share reaches the engine, the rest rebalance there.
    page.fill("#v2ShareQB", "10")
    page.click('#v2Popover [data-apply="weights"]')
    got = page.evaluate("() => window.TradeValueCurveControls.getPositionWeights()")
    if abs(got["QB"] - 0.10) > 0.002 or abs(sum(got[p] for p in ("QB", "RB", "WR", "TE")) - 1) > 1e-6:
        errors.append(f"weights: QB 10% applied as {got}")
    page.click("#v2Weights")
    page.click("#v2Popover .v2-preset")
    page.click('#v2Popover [data-apply="weights"]')
    back = page.evaluate("""() => { const C = window.TradeValueCurveControls; const a = C.getPositionWeights(), d = C.getDefaultPositionWeights();
      return ['QB', 'RB', 'WR', 'TE'].every(p => Math.abs(a[p] - d[p]) < 1e-9); }""")
    if not back:
        errors.append("weights: Reset defaults did not return the position shares to the league's defaults")
    page.click("#v2Weights")
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


ROOTS_JS = """() => { const fresh = window.TradeValueProductData?.getSourceFreshness?.()?.series || {};
  const pubOf = k => k.replace(/_(vorp|adjusted)$/, '');
  const out = {};
  for (const i of window.TradeValueCurveControls.getSourceInfo()) {
    const stale = typeof fresh[i.key]?.is_older_week === 'boolean' ? fresh[i.key].is_older_week : i.stale;
    const pub = pubOf(i.key); out[pub] = out[pub] || {prior: false, paused: false};
    if (i.available && stale) out[pub].prior = true;
    if (i.paused) out[pub].paused = true;
  }
  return out; }"""


def check_freshness(page) -> list[str]:
    """JEG-463: one row per root source; pipeline failures fold into that source as Not updating."""
    errors = []
    page.click("#v2Freshness")
    rows = page.evaluate("""() => [...document.querySelectorAll('#v2Popover tr[data-source]')].map(tr => ({pub: tr.dataset.source,
      status: tr.dataset.status, text: tr.lastElementChild.textContent}))""")
    roots = page.evaluate(ROOTS_JS)
    if sorted(r["pub"] for r in rows) != sorted(roots):
        errors.append(f"freshness: rows {[r['pub'] for r in rows]} != root sources {sorted(roots)}")
    for r in rows:
        want = roots.get(r["pub"], {})
        if want.get("paused") and r["status"] != "stuck":
            errors.append(f"freshness: {r['pub']} paused but {r['text']!r}")
        elif not want.get("paused") and want.get("prior") != (r["status"] == "prior"):
            errors.append(f"freshness: {r['pub']} prior={want.get('prior')} but {r['text']!r}")
        if any(word in r["text"] for word in ("L1", "fixture", "artifact", "as_of")):
            errors.append(f"freshness: pipeline jargon in {r['text']!r}")
    page.keyboard.press("Escape")
    # A failed import shows its source as Not updating, and the header says so.
    def broken(route, *_):
        doc = _freshness_doc()
        for item in doc.get("items", []):
            if item.get("key") == "source_import.fantasypros":
                item["freshness_ok"] = False
                item["value"] = "2026-10-06"
        route.fulfill(status=200, json=doc)
    rows, label = _freshness_with(page, broken)
    fp = rows.get("fantasypros")
    if not fp or fp["status"] != "stuck" or "since 2026-10-06" not in fp["text"]:
        errors.append(f"freshness: failed FantasyPros import not shown as Not updating: {fp}")
    if "1 source not updating" not in label:
        errors.append(f"freshness: header chip {label!r} does not warn")

    # Fail closed: a missing freshness file never shows a source as current.
    def missing(route, *_):
        route.fulfill(status=404, content_type="text/plain", body="not found")
    rows, label = _freshness_with(page, missing)
    for pub, want in roots.items():
        r = rows.get(pub)
        expect = "stuck" if want.get("paused") else "prior" if want.get("prior") else "unknown"
        if not r or r["status"] != expect or (expect == "unknown" and (
                "Freshness unknown" not in r["text"] or "✓" in r["text"] or "couldn't confirm" not in r["text"])):
            errors.append(f"freshness: with the file missing {pub} shows {r}, want {expect}")
    if "all sources current" in label or "unconfirmed" not in label:
        errors.append(f"freshness: with the file missing the header chip says {label!r}")

    # Fail closed: a source whose own rows are missing is unknown; every other source confirmed current.
    def dropped(route, *_):
        doc = _freshness_doc()
        items = [item for item in doc.get("items", [])
                 if item.get("key") not in ("source_import.fantasypros", "comparison.source.fantasypros")]
        for item in items:
            if str(item.get("key", "")).startswith(("source_import.", "comparison.")):
                item["freshness_ok"] = True
                if "weeks_behind" in item:
                    item["weeks_behind"] = 0
        doc["items"] = items
        route.fulfill(status=200, json=doc)
    rows, label = _freshness_with(page, dropped)
    for pub, want in roots.items():
        r = rows.get(pub)
        expect = ("stuck" if want.get("paused") else "prior" if want.get("prior")
                  else "unknown" if pub == "fantasypros" else "current")
        if not r or r["status"] != expect:
            errors.append(f"freshness: with FantasyPros rows removed {pub} shows {r}, want {expect}")
    fp = rows.get("fantasypros") or {}
    if "✓" in fp.get("text", "") or "Freshness unknown" not in fp.get("text", ""):
        errors.append(f"freshness: FantasyPros without rows shows {fp}")
    if "all sources current" in label or "1 source unconfirmed" not in label:
        errors.append(f"freshness: with one source unconfirmed the header chip says {label!r}")
    return errors


def _freshness_doc() -> dict:
    """The built freshness record, read from disk (a route.fetch round trip to the test server
    was refused intermittently on Windows)."""
    return json.loads((DIST / "assets" / "reference-freshness.json").read_text(encoding="utf-8"))


def _freshness_with(page, handler):
    """Load Player values with reference-freshness.json served by handler; return the rows and the chip."""
    other = page.context.browser.new_page(viewport={"width": 1440, "height": 1000})
    other.route(lambda u: not u.startswith("http://127.0.0.1"), lambda route: route.abort())
    if getattr(page, "v2_js", None) is not None:
        other.route("**/v2/v2.js*", functools.partial(_serve, page.v2_js))
    other.route("**/assets/reference-freshness.json*", handler)
    other.goto(page.url.split("#")[0] + "#player-values", wait_until="load", timeout=120000)
    other.wait_for_function("() => window.TradeValueV2 && document.querySelector('#v2Table tbody tr')", timeout=120000)
    other.wait_for_timeout(1500)   # the freshness record loads after the engine
    other.wait_for_function("() => !document.getElementById('v2FreshnessLabel').textContent.includes('checking sources')", timeout=60000)
    other.click("#v2Freshness")
    rows = other.evaluate("""() => Object.fromEntries([...document.querySelectorAll('#v2Popover tr[data-source]')].map(tr =>
      [tr.dataset.source, {status: tr.dataset.status, text: tr.lastElementChild.textContent}]))""")
    label = other.evaluate("() => document.getElementById('v2FreshnessLabel').textContent")
    other.close()
    return rows, label


VIEW = "window.TradeValueV2"
SNAP = """() => { const v = window.TradeValueV2.view(); const s = window.TradeValueV2.state;
  return {window: s.window, preset: s.windowPreset, range: s.range, rankKey: v.rankKey, n: v.rows.length,
    visible: v.visible.map(r => ({rank: r.rank, fullRank: r.fullRank, value: r.values[v.rankKey] ?? null})),
    show: document.getElementById('v2Show').selectedOptions[0]?.textContent || '',
    showValue: document.getElementById('v2Show').value,
    firstRow: document.querySelector('#v2Table tbody tr td.rank')?.textContent || '',
    zones: window.TradeValueCurveControls.getZones()}; }"""
TOOLBAR_ORDER = ["v2Search", "v2Position", "v2Show", "v2RankBy", "v2DeltaBtn", "v2More", "v2Reset"]
REMOVED = ["#v2ChartOptions", "#v2RangeBtn", "#v2ClearFilters", "#v2ResetAll", "#v2ZoomReset", "#v2FromRank",
           "#v2Main .v2-seg [data-window]"]


def _settle(page):
    page.wait_for_timeout(120)   # brushes redraw on the next animation frame


def _set_range_input(page, element_id, value):
    page.evaluate("""([id, v]) => { const s = document.getElementById(id); s.value = String(v);
      s.dispatchEvent(new Event('input', {bubbles: true})); }""", [element_id, value])
    _settle(page)


def check_toolbar(page) -> list[str]:
    """JEG-475: one toolbar, every control once, in order; Show presets follow getZones()."""
    errors = []
    found = page.evaluate("""(ids) => ids.map(id => ({id, count: document.querySelectorAll('#' + id).length,
      inToolbar: Boolean(document.querySelector('#v2Toolbar #' + id)),
      left: document.getElementById(id)?.getBoundingClientRect().left ?? null,
      top: document.getElementById(id)?.getBoundingClientRect().top ?? null}))""", TOOLBAR_ORDER)
    for item in found:
        if item["count"] != 1 or not item["inToolbar"]:
            errors.append(f"toolbar: #{item['id']} count {item['count']}, in toolbar {item['inToolbar']}")
    lefts = [(round(i["top"] or 0), i["left"] or 0) for i in found]
    if lefts != sorted(lefts):
        errors.append(f"toolbar: controls are not left to right in ticket order: {[i['id'] for i in found]}")
    for selector in REMOVED:
        if page.locator(selector).count():
            errors.append(f"toolbar: removed control still present: {selector}")
    text = page.text_content("#v2Main")
    # "Reset zoom" came back in JEG-483 (shown only while zoomed; tests/test_v2_expand_render.py).
    for gone in ("Chart options", "Reset to all", "Clear filters"):
        if gone in text:
            errors.append(f"toolbar: {gone!r} is still on Player values")
    resets = page.evaluate("() => [...document.querySelectorAll('#v2Main button')].filter(b => /^Reset$/.test(b.textContent.trim()) && b.offsetParent).length")
    if resets != 1:
        errors.append(f"toolbar: {resets} visible Reset buttons, want 1")
    sticky = page.evaluate("() => getComputedStyle(document.getElementById('v2Toolbar')).position")
    if sticky != "sticky":
        errors.append(f"toolbar: position {sticky}, want sticky")
    # Chart: only direct manipulation inside (brushes, zoom), no rank-window buttons.
    inside = page.evaluate("""() => [...document.querySelectorAll('.v2-chart-card button, .v2-chart-card select, .v2-chart-card input')]
      .filter(n => n.offsetParent).map(n => n.id || n.textContent.trim())""")
    allowed = {"v2ZoomIn", "v2ZoomOut", "v2YExact", "v2BrushLo", "v2BrushHi", "v2YBrushLo", "v2YBrushHi",
               "v2ExpandChart", "v2ResetZoom"}   # JEG-483: expand and (while zoomed) Reset zoom
    extra = [n for n in inside if n not in allowed]
    if extra:
        errors.append(f"chart: controls other than brushes and zoom inside the chart: {extra}")
    # Show presets.
    page.select_option("#v2Show", "25")
    snap = page.evaluate(SNAP)
    if [r["rank"] for r in snap["visible"]] != list(range(1, 26)):
        errors.append(f"Show Top 25: visible ranks {[r['rank'] for r in snap['visible']][:5]}… ({len(snap['visible'])})")
    for preset, test in (("starter", lambda r, sb, bw: r < sb), ("bench", lambda r, sb, bw: sb < r < bw),
                         ("waiver", lambda r, sb, bw: r > bw)):
        page.select_option("#v2Show", preset)
        snap = page.evaluate(SNAP)
        sb, bw = snap["zones"]["starter_to_bench"], snap["zones"]["bench_to_waiver"]
        ranks = [r["fullRank"] for r in snap["visible"]]
        if not ranks or not all(test(r, sb, bw) for r in ranks):
            errors.append(f"Show {preset}: ranks {ranks[:3]}…{ranks[-3:]} outside the engine zones {sb}/{bw}")
        rows = page.evaluate("() => document.querySelectorAll('#v2Table tbody tr').length")
        if rows != min(len(ranks), 50):
            errors.append(f"Show {preset}: table has {rows} rows, chart window {len(ranks)}")
    page.click("#v2Reset")
    return errors


def check_x_brush(page) -> list[str]:
    """Dragging the rank brush sets Show to "Custom lo–hi"; More holds the exact From / To ranks."""
    errors = []
    track = page.locator("#v2Brush").bounding_box()
    snap = page.evaluate(SNAP)
    n, hi = snap["n"], snap["window"][1]
    thumb_x = track["x"] + 7 + (hi - 1) / max(1, n - 1) * (track["width"] - 14)
    y = track["y"] + track["height"] / 2
    page.mouse.move(thumb_x, y)
    page.mouse.down()
    page.mouse.move(thumb_x - track["width"] * 0.08, y, steps=6)
    page.mouse.up()
    _settle(page)
    snap = page.evaluate(SNAP)
    lo, hi2 = snap["window"]
    if snap["preset"] != "custom" or snap["showValue"] != "custom" or snap["show"] != f"Custom {lo}–{hi2}" or hi2 >= hi:
        errors.append(f"X brush drag: window {snap['window']} preset {snap['preset']} Show {snap['show']!r} (was …{hi})")
    if [r["rank"] for r in snap["visible"]] != list(range(lo, hi2 + 1)):
        errors.append("X brush drag: the table / chart rows do not follow the brushed window")
    # More: exact ranks.
    page.click("#v2More")
    if page.get_attribute("#v2More", "aria-expanded") != "true":
        errors.append("More: aria-expanded not set")
    page.fill("#v2FromRank", "20")
    page.fill("#v2ToRank", "60")
    page.evaluate("() => document.getElementById('v2ToRank').dispatchEvent(new Event('change'))")
    _settle(page)
    # The redraw runs on the next animation frame; under load that can take longer than the settle.
    # Wait (up to 3 s) for the drawn rows to match the window; a redraw that never comes still fails below.
    with contextlib.suppress(Exception):
        page.wait_for_function("() => { const v = window.TradeValueV2.view(); const w = window.TradeValueV2.state.window;"
                               " return v.visible.length && v.visible[0].rank === w[0]; }", timeout=3000)
    snap = page.evaluate(SNAP)
    if snap["window"] != [20, 60] or snap["show"] != "Custom 20–60" or snap["firstRow"] != "20":
        errors.append(f"More From 20 To 60: window {snap['window']} Show {snap['show']!r} first row {snap['firstRow']!r}")
    page.keyboard.press("Escape")
    page.click("#v2Reset")
    return errors


def check_y_brush(page) -> list[str]:
    """JEG-472: the value brush filters to the ranking series' value window, composed with the rank window."""
    errors = []
    attrs = page.evaluate("""() => ['v2YBrushLo', 'v2YBrushHi'].map(id => { const s = document.getElementById(id);
      return {type: s.type, orient: s.getAttribute('aria-orientation'), text: s.getAttribute('aria-valuetext'), label: s.getAttribute('aria-label')}; })""")
    for a in attrs:
        if a["type"] != "range" or a["orient"] != "vertical" or not re.fullmatch(r"Value -?\d+\.\d", a["text"] or "") or not a["label"]:
            errors.append(f"Y brush: input not a labelled vertical range with 'Value x.x' text: {a}")
    # Mouse: drag the top handle down.
    box = page.locator("#v2YBrushHi").bounding_box()
    page.mouse.move(box["x"] + box["width"] / 2, box["y"] + 4)
    page.mouse.down()
    page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] * 0.45, steps=8)
    page.mouse.up()
    _settle(page)
    snap = page.evaluate(SNAP)
    if snap["range"]["max"] is None or snap["preset"] != "custom" or not snap["show"].startswith("Custom "):
        errors.append(f"Y brush drag: range {snap['range']} preset {snap['preset']} Show {snap['show']!r}")
    # Keyboard: PageDown on the top handle jumps; arrows step.
    before = page.evaluate("() => Number(document.getElementById('v2YBrushHi').value)")
    page.focus("#v2YBrushHi")
    page.keyboard.press("PageDown")
    page.keyboard.press("ArrowDown")
    _settle(page)
    after = page.evaluate("() => Number(document.getElementById('v2YBrushHi').value)")
    if not after < before - 0.5:
        errors.append(f"Y brush keys: PageDown + ArrowDown moved {before} → {after}")
    page.click("#v2Reset")
    # Exact bounds through the handles; rank ∩ value against a narrowed rank window.
    page.select_option("#v2Show", "50")
    _set_range_input(page, "v2YBrushLo", 12)
    _set_range_input(page, "v2YBrushHi", 30)
    snap = page.evaluate(SNAP)
    rng = snap["range"]
    lo_v, hi_v = rng["min"] if rng["min"] is not None else float("-inf"), rng["max"] if rng["max"] is not None else float("inf")
    bad = [r for r in snap["visible"] if r["value"] is None or r["value"] < lo_v or r["value"] > hi_v]
    if rng != {"min": 12, "max": 30} or not snap["visible"] or bad:
        errors.append(f"Y brush 12–30: range {rng}, {len(snap['visible'])} rows, outside: {bad[:3]}")
    outside_window = [r["rank"] for r in snap["visible"] if not 1 <= r["rank"] <= 50]
    if outside_window:
        errors.append(f"Y brush: rows outside the rank window 1–50 shown (rank ∩ value broken): {outside_window[:5]}")
    table_vals = page.evaluate("""(key) => [...document.querySelectorAll('#v2Table tbody td.is-rank')].map(td => Number(td.firstChild.textContent))""", snap["rankKey"])
    if not table_vals or any(v < 12 - 0.05 or v > 30 + 0.05 for v in table_vals):
        errors.append(f"Y brush: table ranking values outside 12–30: {table_vals[:5]}")
    labels = page.evaluate("() => [document.getElementById('v2YLoLabel').textContent, document.getElementById('v2YHiLabel').textContent]")
    if labels != ["12.0", "30.0"]:
        errors.append(f"Y brush: thumb labels {labels}, want 12.0 / 30.0")
    page.click("#v2Reset")
    # Players with no value in the basis series are left out and counted (frame 22).
    missing = page.evaluate("""() => { const C = window.TradeValueCurveControls; const keys = C.getActiveSources();
      const rows = C.getRows(); const counts = keys.map(k => [k, rows.filter(r => !Number.isFinite(r.values[k])).length]);
      return counts.filter(c => c[1] > 0).map(c => c[0]); }""")
    if missing:
        key = missing[0]
        before_rank = page.evaluate("() => window.TradeValueCurveControls.getRankSource()")
        page.select_option("#v2RankBy", key)
        page.select_option("#v2Show", "all")
        _set_range_input(page, "v2YBrushLo", 1)
        expect = page.evaluate("(k) => window.TradeValueCurveControls.getRows().filter(r => !Number.isFinite(r.values[k])).length", key)
        note = page.evaluate("() => document.getElementById('v2FilterNote').hidden ? '' : document.getElementById('v2FilterNote').textContent")
        if f"{expect} player" not in note or "omitted" not in note:
            errors.append(f"Y brush: no visible count of the {expect} players without a {key} value: {note!r}")
        page.click("#v2Reset")
        page.select_option("#v2RankBy", before_rank)
    # Set exact values (frame 24 popover) still works, names its basis and refuses min > max.
    page.click("#v2YExact")
    sub = page.text_content("#v2Popover .v2-panel-head .v2-meta")
    if "Basis" not in sub:
        errors.append(f"Set exact values: no basis series named: {sub!r}")
    inputs = page.locator("#v2Popover .row2 input")
    inputs.nth(0).fill("30")
    inputs.nth(1).fill("10")
    page.click('#v2Popover [data-apply="range"]')
    if page.evaluate("() => document.getElementById('v2Popover').hidden"):
        errors.append("Set exact values: minimum above maximum was accepted")
    inputs.nth(1).fill("40")
    page.click('#v2Popover [data-apply="range"]')
    _settle(page)
    snap = page.evaluate(SNAP)
    vals = [r["value"] for r in snap["visible"]]
    if not vals or any(v is None or v < 30 or v > 40 for v in vals) or snap["show"][:6] != "Custom":
        errors.append(f"Set exact values 30–40: {vals[:5]} Show {snap['show']!r}")
    page.click("#v2Reset")
    return errors


def check_reset(page) -> list[str]:
    """One Reset clears search, position, Show, value range, sort and Δ."""
    errors = []
    page.fill("#v2Search", "a")
    page.wait_for_timeout(250)
    page.select_option("#v2Position", "RB")
    page.select_option("#v2Show", "25")
    _set_range_input(page, "v2YBrushLo", 5)
    page.click("#v2Table thead .v2-head-row th[data-col='name'] button")
    page.click("#v2DeltaBtn")
    page.click("#v2Reset")
    page.wait_for_timeout(200)
    got = page.evaluate("""() => { const s = window.TradeValueV2.state; return {search: s.search, input: document.getElementById('v2Search').value,
      position: window.TradeValueCurveControls.getState().position, preset: s.windowPreset, window: s.window, range: s.range, sort: s.sort,
      delta: s.delta, show: document.getElementById('v2Show').value}; }""")
    want = {"search": "", "input": "", "position": "ALL", "preset": "100", "window": [1, 100], "range": {"min": None, "max": None},
            "sort": None, "delta": False, "show": "100"}
    if got != want:
        errors.append(f"Reset: {got} != defaults {want}")
    return errors


def check_columns(page) -> list[str]:
    """JEG-473 Columns menu: hiding a method group removes its columns; the ranking series stays."""
    errors = []
    heads = lambda: page.evaluate("() => [...document.querySelectorAll('#v2Table .v2-head-row th[data-group]')].map(th => [th.dataset.col, th.dataset.group])")
    rank = page.evaluate("() => window.TradeValueV2.view().rankKey")
    groups = sorted({g for _, g in heads()})
    page.click("#v2Columns")
    target = next((g for g in groups if g != "spread" and any(c != rank and gg == g for c, gg in heads())), None)
    if not target:
        return errors + [f"columns: no hideable group in {groups}"]
    page.click(f'#v2Popover input[data-group="{target}"]')
    now = heads()
    if any(g == target and c != rank for c, g in now) or not any(c == rank for c, _ in now):
        errors.append(f"columns: hiding {target} left {now}")
    page.click(f'#v2Popover input[data-group="{target}"]')
    if sorted({g for _, g in heads()}) != groups:
        errors.append("columns: showing the group again did not restore it")
    # Team: below 1600 px it is part of the player sub-line.
    page.click('#v2Popover input[data-meta="team"]')
    sub = page.evaluate("""() => { const v = window.TradeValueV2.view(); const r = v.visible[0];
      return {sub: document.querySelector('#v2Table tbody .player-sub')?.textContent || '', team: r.team || 'FA'}; }""")
    if f"· {sub['team']} ·" in f"· {sub['sub']} ·":
        errors.append(f"columns: Team unticked but the player line still reads {sub['sub']!r}")
    page.click('#v2Popover input[data-meta="team"]')
    page.keyboard.press("Escape")
    return errors


TABLE_FIT = """() => { const wrap = document.getElementById('v2TableWrap'); const out = {scroll: wrap.scrollWidth - wrap.clientWidth};
  out.headLines = [...document.querySelectorAll('#v2Table .v2-head-row th button')].map(b =>
    [...b.children].map(c => Math.round(c.getBoundingClientRect().height / parseFloat(getComputedStyle(c).lineHeight || 14)))
      .reduce((a, x) => a + x, 0));
  out.headSticky = [...document.querySelectorAll('#v2Table thead th')].every(th => getComputedStyle(th).position === 'sticky');
  out.playerSticky = getComputedStyle(document.querySelector('#v2Table tbody td.player')).position;
  const rows = [...document.querySelectorAll('#v2Table tbody tr')];
  out.rowH = Math.max(...rows.slice(0, 10).map(r => r.getBoundingClientRect().height));
  out.nums = [...document.querySelectorAll('#v2Table tbody td.num')].slice(0, 60).map(td => ({text: td.firstChild?.textContent || '',
    align: getComputedStyle(td).textAlign, pad: parseFloat(getComputedStyle(td).paddingRight)}));
  const v = window.TradeValueV2.view();
  out.heat = [...document.querySelectorAll('#v2Table tbody td[data-vs]')].slice(0, 80).map(td => {
    const tr = td.closest('tr'); const rankTd = tr.querySelector('td.is-rank');
    return {vs: td.dataset.vs, title: td.title, value: Number(td.firstChild.textContent), rank: Number(rankTd.firstChild.textContent),
      tinted: /heat-/.test(td.className)}; });
  out.missing = [...document.querySelectorAll('#v2Table tbody .missing')].slice(0, 20).map(m => ({text: m.firstChild.textContent, title: m.title}));
  // Grouped header: each value column sits under its method group.
  const groupRow = [...document.querySelectorAll('#v2Table .v2-group-row th')];
  const cells = []; groupRow.forEach(th => { for (let i = 0; i < th.colSpan; i++) cells.push(th.dataset.group || ''); });
  out.groups = [...document.querySelectorAll('#v2Table .v2-head-row th')].map((th, i) => [th.dataset.col, cells[i], th.dataset.group || '']);
  out.groupLabels = groupRow.map(th => th.textContent);
  // Scroll the body: the header rows stay in view.
  const head = document.querySelector('#v2Table .v2-head-row th.num');
  const before = head.getBoundingClientRect().top; wrap.scrollTop = 200; const after = head.getBoundingClientRect().top; wrap.scrollTop = 0;
  out.stickyMoved = Math.abs(after - before);
  out.scrolls = wrap.scrollHeight > wrap.clientHeight;
  return out; }"""


def _group_of(key):
    if key == "ddf_value":
        return "ddf"
    if key.endswith("_vorp"):
        return "vorp"
    if key.endswith("_adjusted"):
        return "adjusted"
    if key in ("espn", "cbsros", "razzball"):
        return "projections"
    return "published"


def check_table_fit(page, width) -> list[str]:
    errors = []
    fit = page.evaluate(TABLE_FIT)
    tag = f"table fit {width}: "
    if fit["scroll"] > 0:
        errors.append(tag + f"horizontal scroll {fit['scroll']}px with the wide selection")
    if not fit["headLines"] or max(fit["headLines"]) > 2:
        errors.append(tag + f"headers over two lines: {fit['headLines']}")
    if fit["headSticky"] is not True or fit["playerSticky"] != "sticky":
        errors.append(tag + f"header {fit['headSticky']}, player column {fit['playerSticky']}; both must be sticky")
    if fit["scrolls"] and fit["stickyMoved"] > 1:
        errors.append(tag + f"header row moved {fit['stickyMoved']}px when the table body scrolled")
    if fit["rowH"] > 37:
        errors.append(tag + f"rows {fit['rowH']}px tall; compact rows are about 32 px")
    for cell in fit["nums"]:
        if not re.fullmatch(r"-?\d+\.\d", cell["text"]) or cell["align"] != "right" or not 6 <= cell["pad"] <= 8:
            errors.append(tag + f"number cell {cell}")
            break
    for cell in fit["heat"]:
        want = "above" if cell["value"] > cell["rank"] else "below" if cell["value"] < cell["rank"] else None
        if cell["vs"] not in ("above", "below", "same") or (cell["tinted"] and cell["vs"] != want) or cell["vs"] not in cell["title"].replace("about level with", "same"):
            errors.append(tag + f"heat cell {cell}")
            break
    for m in fit["missing"]:
        if m["text"] != "—" or not m["title"]:
            errors.append(tag + f"missing cell without a reason: {m}")
            break
    for col, group_cell, group in fit["groups"]:
        if group and group != "spread" and group != _group_of(col):
            errors.append(tag + f"{col} is in group {group}, its method says {_group_of(col)}")
        if group and group_cell not in (group, "rank-series"):
            errors.append(tag + f"{col} sits under group cell {group_cell!r}, not {group!r}")
    if not set(fit["groupLabels"]) & {"Projections", "Trade charts adjusted", "Trade charts as published", "VORP vs waivers"}:
        errors.append(tag + f"no method group header: {fit['groupLabels']}")
    return errors


FOLD = """() => { const card = document.querySelector('.v2-chart-card').getBoundingClientRect();
  const wrap = document.getElementById('v2TableWrap').getBoundingClientRect();
  const rows = [...document.querySelectorAll('#v2Table tbody tr')].filter(r => { const b = r.getBoundingClientRect();
    return b.top >= wrap.top - 0.5 && b.bottom <= Math.min(innerHeight, wrap.bottom) + 0.5; }).length;
  return {scrollY: window.scrollY, chartBottom: card.bottom, h: innerHeight, rows,
    h1: parseFloat(getComputedStyle(document.querySelector('#v2Main h1')).fontSize),
    line: document.getElementById('v2ValueLine').textContent}; }"""


def check_fold(page, width, height) -> list[str]:
    """JEG-470: chart and at least six table rows visible without scrolling."""
    errors = []
    page.evaluate("() => window.scrollTo(0, 0)")
    f = page.evaluate(FOLD)
    tag = f"above the fold {width}×{height}: "
    if f["chartBottom"] > f["h"] + 0.5:
        errors.append(tag + f"chart card ends at {f['chartBottom']:.0f}px")
    if f["rows"] < 6:
        errors.append(tag + f"{f['rows']} table rows visible, want 6")
    if not 26 <= f["h1"] <= 28.5:
        errors.append(tag + f"h1 {f['h1']}px, want 26–28")
    week = page.evaluate("() => window.TradeValueProductData?.getSourceFreshness?.()?.current_content_week || window.TradeValueCurveControls.getReferenceWeek()")
    if not f["line"].startswith("Trade values for every player") or (week and f"Week {week}" not in f["line"]):
        errors.append(tag + f"value line {f['line']!r} (engine week {week})")
    return errors


def run_checks(v2_js=None, v2_css=None, viewports=((1440, 900), (1366, 768), (390, 844)), full=True) -> list[str]:
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
                if v2_css is not None:
                    page.route("**/v2/v2.css*", functools.partial(_serve_css, v2_css))
                page.v2_js = v2_js
                page.goto(url, wait_until="networkidle")
                page.wait_for_function("() => window.TradeValueV2 && document.querySelector('#v2Table tbody tr')", timeout=40000)
                page.wait_for_timeout(150)
                tag = f"[{width}px] "
                if width >= 1280:
                    errors += [tag + e for e in check_fold(page, width, height)]
                    # Fit is judged with a wider selection than the first-visit default: at 1440 six value
                    # columns (DDF Value, ESPN, the four adjusted charts).
                    before_shown = page.evaluate("() => window.TradeValueV2.shown()")
                    # 1366 gets five (no ESPN), the same count the pre-DDF default had.
                    page.evaluate("""wide => window.TradeValueV2.setShown(['ddf_value'].concat(wide ? ['espn'] : [],
                      ['fantasycalc_adjusted', 'usatoday_adjusted', 'fantasypros_adjusted', 'cbs_adjusted']))""", width >= 1440)
                    page.wait_for_timeout(200)
                    errors += [tag + e for e in check_table_fit(page, width)]
                    page.evaluate("keys => window.TradeValueV2.setShown(keys)", before_shown)
                    page.wait_for_function("keys => JSON.stringify(window.TradeValueV2.view().active) === JSON.stringify(keys)", arg=before_shown)
                    page.wait_for_timeout(800)
                if width == 1440:
                    errors += [tag + e for e in check_toolbar(page)]
                    for check in (check_x_brush, check_y_brush, check_reset, check_columns):
                        errors += [tag + e for e in check(page)]
                if full and width == 1440:
                    errors += [tag + e for e in check_sources(page, width)]
                    for check in (check_league, check_weights, check_freshness):
                        errors += [tag + e for e in check(page)]
                if width <= 390:
                    if full:
                        errors += [tag + e for e in check_sources(page, width)]
                    mobile = page.evaluate("""() => ({ybrush: getComputedStyle(document.getElementById('v2YBrush')).display,
                      exact: Boolean(document.getElementById('v2YExact').offsetParent)})""")
                    if mobile["ybrush"] != "none" or not mobile["exact"]:
                        errors.append(tag + f"below 768 px the numeric value range replaces the Y brush: {mobile}")
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
        css = V2_CSS.read_text(encoding="utf-8")
        desktop = ((1440, 900),)
        broken = {
            "pair toggle applied at once": {"v2_js": v2.replace(
                "          if (box.checked) draft.add(item.key); else draft.delete(item.key);",
                "          if (box.checked) draft.add(item.key); else draft.delete(item.key);\n          toggleEngineSource(item.key);", 1)},
            "zone preset ignored": {"v2_js": v2.replace("    const zone = zoneWindow(rows, preset);", "    const zone = null;", 1)},
            "Team box ignored": {"v2_js": v2.replace("state.metaCols.team !== false && (row.team || \"FA\")", "(row.team || \"FA\")", 1)},
            "From / To ignored": {"v2_js": v2.replace(
                '      from.addEventListener("change", onBounds);\n      to.addEventListener("change", onBounds);\n', "", 1)},
            "brush drag keeps the preset": {"v2_js": v2.replace(
                '    state.window = win;\n    state.windowPreset = "custom";', "    state.window = win;", 1)},
            "value range ignores the rank window": {"v2_js": v2.replace(
                "    const visible = rows.slice(state.window[0] - 1, state.window[1]).filter(row => {",
                "    const visible = rows.filter(row => {", 1)},
            "Y brush does nothing": {"v2_js": v2.replace('      $(id).addEventListener("input", onYBrush);', "", 1)},
            "Reset keeps the value range": {"v2_js": v2.replace(
                "    state.range = {min: null, max: null};\n    state.windowPreset = SHOW_DEFAULT;", "    state.windowPreset = SHOW_DEFAULT;", 1)},
            "Columns menu ignored": {"v2_js": v2.replace(
                "      .filter(key => key === view.rankKey || !state.hiddenGroups.has(tableGroup(key)));", ";", 1)},
            "no SUPERFLEX stepper": {"v2_js": v2.replace(
                '    ["SUPERFLEX", "SUPERFLEX", 0, 1], ["BENCH", "Bench slots", 0, 14]];', '    ["BENCH", "Bench slots", 0, 14]];', 1)},
            "bench move not reported": {"v2_js": v2.replace(
                "    if (Number.isFinite(benchBefore) && Number.isFinite(benchAfter) && Math.abs(benchAfter - benchBefore) > 1e-9) {",
                "    if (false) {", 1)},
            "shares not applied": {"v2_js": v2.replace(
                "          const result = C.setPositionWeights(edited);", "          const result = {ok: true};", 1)},
            "pipeline failure ignored": {"v2_js": v2.replace(
                "find(item => item && item.freshness_ok === false);", "find(item => false);", 1)},
            "freshness fails open": {"v2_js": v2.replace(
                "const confirmed = Boolean(own && imp && own.freshness_ok === true && imp.freshness_ok === true);",
                "const confirmed = true;", 1)},
            "league Apply does nothing": {"v2_js": v2.replace(
                "          ROSTER_SLOTS.forEach(([key]) => { if (draft.roster[key] !== shape[key]) C.setRosterSpot(key, draft.roster[key]); });",
                "", 1)},
            # Table fit and above the fold (CSS).
            "no chart-and-table split": {"v2_css": css.replace(
                "@media (min-width: 1280px) {\n  .v2-values-grid", "@media (min-width: 99999px) {\n  .v2-values-grid", 1),
                "viewports": ((1366, 768),), "full": False},
            "header not sticky": {"v2_css": css.replace(
                "  .v2-vtable thead th { position: sticky;", "  .v2-vtable thead th { position: static;", 1), "full": False},
            "wide cells scroll sideways": {"v2_css": css + "\n.v2-vtable td.num { min-width: 120px; }\n", "full": False},
        }
        for name, kwargs in broken.items():
            with self.subTest(mutation=name):
                body = kwargs.get("v2_js") or kwargs.get("v2_css")
                self.assertNotIn(body, (v2, css), f"mutation anchor for {name!r} is stale")
                args = {"viewports": desktop, **kwargs}
                self.assertNotEqual(run_checks(**args), [], f"render checks did not catch: {name}")


if __name__ == "__main__":
    unittest.main()
