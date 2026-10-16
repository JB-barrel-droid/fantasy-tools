"""v2 Player values chart: break lines and labels, whole-range brush drag, legend toggles (JEG-503).

Contract PV-04, PV-06, PV-07. Loads the built page headless at 1440 px and checks:

  * a vertical line at the starter -> bench and the bench -> waiver boundary, placed between the two listed
    players the engine's getZones() boundary falls between (not at a fixed position count);
  * light grey labels "Starter", "Bench", "Waiver" centred between the lines (and the plot edges), redrawn
    when the rank window is zoomed: a boundary outside the shown ranks has no line;
  * grabbing the fill between a brush's handles moves both ends together and keeps the width, for the rank
    brush (pointer drag and Shift+arrow) and the value brush;
  * a legend entry turns exactly that series' line and table column off and on; the ranking series stays on;
    the entry shows its state with a symbol and aria-pressed.

Discrimination: test_guard_fails_on_broken_builds serves v2.js with the zone lines removed, the drag moving
only one end, the legend toggle ignored, and the legend hiding the ranking series, and requires failures.
"""
from __future__ import annotations

import contextlib
import functools
import http.server
import shutil
import socketserver
import tempfile
import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
V2_JS = ROOT / "app" / "v2" / "v2.js"

from tests import _render_env  # noqa: E402
from tests.test_published_league_settings_render import _chromium_executable  # noqa: E402

ZONES = """() => {
  const V = window.TradeValueV2, C = window.TradeValueCurveControls;
  const chart = V.chart();
  const z = C.getZones();
  const slice = chart.slice.map(r => r.fullRank);
  const xs = chart.slice.map((r, i) => chart.x(i));
  const svg = chart.svg;
  const lines = [...svg.querySelectorAll('.zone-line')].map(l => ({name: l.dataset.zone, x: Number(l.getAttribute('x1'))}));
  const labels = [...svg.querySelectorAll('.zone-label')].map(l => ({name: l.textContent, x: Number(l.getAttribute('x')),
    fill: getComputedStyle(l).fill, anchor: l.getAttribute('text-anchor')}));
  return {zones: z, slice, xs, lines, labels, left: chart.pad.l, right: chart.width - chart.pad.r};
}"""

BRUSH = """() => {
  const V = window.TradeValueV2;
  const r = el => { const b = document.getElementById(el).getBoundingClientRect(); return {x: b.x, y: b.y, w: b.width, h: b.height}; };
  return {window: V.state.window.slice(), range: {...V.state.range}, fillX: r('v2BrushFill'), fillY: r('v2YBrushFill'),
    rows: V.view().rows.length, yScale: V.view().yScale};
}"""

LEGEND = """() => {
  const V = window.TradeValueV2;
  const items = [...document.querySelectorAll('#v2Legend .v2-legend-item')].map(b => ({key: b.dataset.series, pressed: b.getAttribute('aria-pressed'),
    disabled: b.disabled, mark: b.querySelector('.v2-legend-mark').textContent}));
  const lines = [...document.querySelectorAll('#v2Chart path.series')].map(p => p.dataset.source);
  const cols = [...document.querySelectorAll('#v2Table thead th')].map(th => th.dataset.source || th.dataset.key || '').filter(Boolean);
  const heads = [...document.querySelectorAll('#v2Table thead th')].map(th => th.textContent.trim());
  return {items, lines, cols, heads, rank: V.view().rankKey, keys: V.view().plotKeys};
}"""


@contextlib.contextmanager
def _served():
    if not (DIST / "index.html").exists():
        raise _render_env.unavailable("dist/index.html is not built")
    with tempfile.TemporaryDirectory() as tmp:
        dist = Path(tmp) / "dist"
        shutil.copytree(DIST, dist)

        class Quiet(http.server.SimpleHTTPRequestHandler):
            def log_message(self, format, *args):
                pass
        handler = functools.partial(Quiet, directory=str(dist))
        with socketserver.ThreadingTCPServer(("127.0.0.1", 0), handler) as server:
            server.daemon_threads = True
            threading.Thread(target=server.serve_forever, daemon=True).start()
            try:
                yield f"http://127.0.0.1:{server.server_address[1]}/v2/"
            finally:
                server.shutdown()


def check_zones(z: dict, tag: str, expect_all: bool) -> list[str]:
    errors = []
    slice_, xs = z["slice"], z["xs"]
    want = {"starter_to_bench": z["zones"]["starter_to_bench"], "bench_to_waiver": z["zones"]["bench_to_waiver"]}
    got = {line["name"]: line["x"] for line in z["lines"]}
    bounds = [z["left"]]
    for name, zone in want.items():
        inside = slice_[0] < zone < slice_[-1]
        if not inside:
            if name in got:
                errors.append(f"{tag}{name} line drawn although the boundary {zone} is outside the shown ranks {slice_[0]}-{slice_[-1]}")
            continue
        i = max(k for k, r in enumerate(slice_) if r < zone)
        if name not in got:
            errors.append(f"{tag}no {name} line for the boundary {zone}")
            continue
        if not (xs[i] - 0.01 <= got[name] <= xs[i + 1] + 0.01):
            errors.append(f"{tag}{name} line at x={got[name]:.1f}, want between players ranked {slice_[i]} and {slice_[i + 1]} ({xs[i]:.1f}-{xs[i + 1]:.1f})")
        bounds.append(got[name])
    bounds.append(z["right"])
    # Sections: left edge / first line / second line / right edge; labels sit in their section's centre.
    names = ["Starter", "Bench", "Waiver"]
    edges = [z["left"]] + [got[n] for n in want if n in got] + [z["right"]]
    # A boundary left of the first listed player collapses the section to nothing: work out the sections from the zones.
    sec = []
    lo = z["left"]
    for name, zone in want.items():
        if zone <= slice_[0]:
            continue
        hi = got.get(name, z["right"] if zone >= slice_[-1] else None)
        if hi is None:
            return errors   # the missing line is already reported
        sec.append((lo, hi))
        lo = hi
    sec.append((lo, z["right"]))
    first = len(names) - len(sec)
    labels = {label["name"]: label for label in z["labels"]}
    for k, (a, b) in enumerate(sec):
        name = names[first + k]
        if b - a < 46:
            if name in labels:
                errors.append(f"{tag}label {name} drawn in a section only {b - a:.0f}px wide")
            continue
        if name not in labels:
            errors.append(f"{tag}no {name} label for the section {a:.0f}-{b:.0f}")
            continue
        if abs(labels[name]["x"] - (a + b) / 2) > 1.0:
            errors.append(f"{tag}{name} label at x={labels[name]['x']:.1f}, want the centre {(a + b) / 2:.1f}")
    if expect_all and not z["lines"]:
        errors.append(f"{tag}no break lines at all")
    return errors


def run_checks(patch=None) -> list[str]:
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        raise _render_env.unavailable(f"Playwright is not available: {exc}") from exc
    js = V2_JS.read_text(encoding="utf-8")
    if patch:
        old, new = patch
        assert old in js, f"patch anchor missing: {old!r}"
        js = js.replace(old, new, 1)
    errors: list[str] = []
    with _served() as base, sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(args=_render_env.HERMETIC_ARGS, executable_path=_chromium_executable(playwright))
        except PlaywrightError as exc:
            raise _render_env.unavailable(f"Chromium is not available: {exc}") from exc
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1300})
            page_errors: list[str] = []
            page.on("pageerror", lambda e: page_errors.append(str(e)))
            page.route(lambda u: not u.startswith("http://127.0.0.1"), lambda route: route.abort())
            if patch:
                page.route("**/v2/v2.js*", lambda route, *_: route.fulfill(status=200, content_type="text/javascript", body=js))
            page.goto(base + "#player-values", wait_until="networkidle")
            page.wait_for_function("() => window.TradeValueV2 && window.TradeValueV2.chart() && document.querySelectorAll('#v2Chart path.series').length", timeout=60000)

            # 1. Break lines and labels at the default Show (top 100): the starter -> bench line is on screen.
            page.select_option("#v2Show", "all") if page.query_selector("#v2Show") else None
            page.wait_for_timeout(400)
            z = page.evaluate(ZONES)
            errors += check_zones(z, "[show all] ", True)
            if not z["lines"] or len(z["lines"]) != 2:
                errors.append(f"[show all] want both break lines, got {z['lines']}")
            if any(label["anchor"] != "middle" for label in z["labels"]):
                errors.append(f"[show all] labels are not centred: {z['labels']}")

            # 2. Zoom the rank window to ranks 1..60: the boundaries beyond it have no line; labels redraw.
            page.evaluate("() => { const hi = document.getElementById('v2BrushHi'); hi.value = '60'; hi.dispatchEvent(new Event('input', {bubbles: true})); }")
            page.wait_for_timeout(500)
            errors += check_zones(page.evaluate(ZONES), "[ranks 1-60] ", False)

            # 3. Whole-range drag of the rank brush: ranks 100..400 dragged right keeps the width.
            page.evaluate("() => { const hi = document.getElementById('v2BrushHi'); hi.value = '400'; hi.dispatchEvent(new Event('input', {bubbles: true})); }")
            page.wait_for_timeout(400)
            page.evaluate("() => { const lo = document.getElementById('v2BrushLo'); lo.value = '100'; lo.dispatchEvent(new Event('input', {bubbles: true})); }")
            page.wait_for_timeout(500)
            b = page.evaluate(BRUSH)
            if b["window"] != [100, 400]:
                errors.append(f"[drag setup] window {b['window']}, want [100, 400]")
            else:
                b = page.evaluate(BRUSH)
                fx, fy = b["fillX"]["x"] + b["fillX"]["w"] / 2, b["fillX"]["y"] + b["fillX"]["h"] / 2
                page.mouse.move(fx, fy)
                page.mouse.down()
                page.mouse.move(fx + 60, fy, steps=6)
                page.mouse.up()
                page.wait_for_timeout(500)
                after = page.evaluate(BRUSH)["window"]
                if after[1] - after[0] != 300:
                    errors.append(f"[drag] width changed: {b['window']} -> {after}")
                if not (after[0] > 100 and after[1] > 400):
                    errors.append(f"[drag] both ends should move right: {b['window']} -> {after}")
                # Keyboard: focus the fill, Shift+ArrowLeft moves both ends one rank.
                page.focus("#v2BrushFill")
                page.keyboard.press("Shift+ArrowLeft")
                page.wait_for_timeout(400)
                key = page.evaluate(BRUSH)["window"]
                if key != [after[0] - 1, after[1] - 1]:
                    errors.append(f"[keys] Shift+ArrowLeft moved {after} -> {key}, want both ends down one")
                page.keyboard.press("ArrowLeft")
                page.wait_for_timeout(200)
                if page.evaluate(BRUSH)["window"] != key:
                    errors.append("[keys] a plain arrow on the fill must not move the range")

            # 4. Whole-range drag of the value brush (every rank shown, so the value range keeps players on screen).
            page.select_option("#v2Show", "all")
            page.wait_for_timeout(500)
            page.evaluate("""() => { const V = window.TradeValueV2; const s = V.view().yScale;
              const lo = document.getElementById('v2YBrushLo'), hi = document.getElementById('v2YBrushHi');
              hi.value = String(s.lo + (s.hi - s.lo) * 0.6); hi.dispatchEvent(new Event('input', {bubbles: true}));
              lo.value = String(s.lo + (s.hi - s.lo) * 0.2); lo.dispatchEvent(new Event('input', {bubbles: true})); }""")
            page.wait_for_timeout(600)
            b = page.evaluate(BRUSH)
            lo0, hi0 = b["range"]["min"], b["range"]["max"]
            if lo0 is None or hi0 is None:
                errors.append(f"[y drag setup] range {b['range']}")
            else:
                b = page.evaluate(BRUSH)
                fx, fy = b["fillY"]["x"] + b["fillY"]["w"] / 2, b["fillY"]["y"] + b["fillY"]["h"] / 2
                page.mouse.move(fx, fy)
                page.mouse.down()
                page.mouse.move(fx, fy - 30, steps=6)
                page.mouse.up()
                page.wait_for_timeout(500)
                r = page.evaluate(BRUSH)["range"]
                if r["min"] is None or r["max"] is None or abs((r["max"] - r["min"]) - (hi0 - lo0)) > 1e-6:
                    errors.append(f"[y drag] width changed: {lo0}-{hi0} -> {r}")
                elif not (r["min"] > lo0 and r["max"] > hi0):
                    errors.append(f"[y drag] dragging up should raise both ends: {lo0}-{hi0} -> {r}")
            page.evaluate("() => { const V = window.TradeValueV2; }")

            # 5. Legend toggles (on a fresh load so the brushes do not interfere).
            page.goto(base + "#player-values", wait_until="networkidle")
            page.evaluate("() => { localStorage.clear(); }")
            page.reload(wait_until="networkidle")
            page.wait_for_function("() => document.querySelectorAll('#v2Legend .v2-legend-item').length > 1", timeout=60000)
            before = page.evaluate(LEGEND)
            rank_item = next((i for i in before["items"] if i["key"] == before["rank"]), None)
            if not rank_item or not rank_item["disabled"]:
                errors.append(f"[legend] the ranking series must stay on: {rank_item}")
            target = next((i for i in before["items"] if i["key"] != before["rank"]), None)
            if not target:
                errors.append("[legend] no second series to toggle")
            else:
                page.locator(f'#v2Legend .v2-legend-item[data-series="{target["key"]}"]').dispatch_event("click")
                page.wait_for_timeout(500)
                off = page.evaluate(LEGEND)
                want_lines = [k for k in before["lines"] if k != target["key"]]
                if off["lines"] != want_lines:
                    errors.append(f"[legend] hiding {target['key']}: lines {before['lines']} -> {off['lines']}, want {want_lines}")
                if len(off["heads"]) != len(before["heads"]) - 1:
                    errors.append(f"[legend] hiding {target['key']} should remove one table column: {len(before['heads'])} -> {len(off['heads'])}")
                it = next(i for i in off["items"] if i["key"] == target["key"])
                if it["pressed"] != "false" or it["mark"] == target["mark"]:
                    errors.append(f"[legend] the off state needs aria-pressed=false and a different symbol: {it} vs {target}")
                if rank_item and not page.evaluate("k => !document.querySelector(`#v2Legend .v2-legend-item[data-series=\"${k}\"]`).classList.contains('is-off')", before["rank"]):
                    errors.append("[legend] the ranking series entry was turned off")
                page.locator(f'#v2Legend .v2-legend-item[data-series="{target["key"]}"]').dispatch_event("click")
                page.wait_for_timeout(500)
                on = page.evaluate(LEGEND)
                if on["lines"] != before["lines"] or len(on["heads"]) != len(before["heads"]):
                    errors.append(f"[legend] turning it back on should restore the chart and table: {on['lines']}")
                # The ranking series entry cannot be turned off, even by a forced click.
                page.evaluate("k => document.querySelector(`#v2Legend .v2-legend-item[data-series=\"${k}\"]`).click()", before["rank"])
                page.wait_for_timeout(300)
                if page.evaluate(LEGEND)["lines"] != before["lines"]:
                    errors.append("[legend] the ranking series was hidden")
            if page_errors:
                errors.append(f"page errors {page_errors}")
            page.close()
        finally:
            browser.close()
    return errors


PATCHES = {
    "zone lines removed": ("const zones = opts.zones ? drawZones(svg, slice, {x, pad, width, height}) : null;", "const zones = null;"),
    "drag moves one end": ("const hi = lo + width;", "const hi = start.hi;"),
    "legend toggle ignored": ("if (state.hiddenSeries.has(key)) state.hiddenSeries.delete(key); else state.hiddenSeries.add(key);", ""),
    "ranking series entry can be clicked": ("if (key === view.rankKey) span.disabled = true;", ""),
    "labels off centre": ('x: (a + b) / 2, y: top + 12, class: "zone-label"', 'x: a + 10, y: top + 12, class: "zone-label"'),
}


class ChartZonesRenderTest(unittest.TestCase):
    def test_zones_drag_and_legend(self):
        self.assertEqual(run_checks(), [])

    def test_guard_fails_on_broken_builds(self):
        for name, patch in PATCHES.items():
            with self.subTest(patch=name):
                self.assertNotEqual(run_checks(patch), [], f"checks did not catch: {name}")


if __name__ == "__main__":
    unittest.main()
