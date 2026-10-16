"""v2 Player values: auto-fit Y axis, hidden all-zero players, rank by each DDF projection model (JEG-477).

Loads the built page headless at 1440 px and checks, against independent recomputations from the engine rows:

  * the main chart's Y axis follows the top and bottom visible points (values at or below 0 ignored), 4% padding,
    nice steps, at most about six steps: the tick labels equal the recomputation, at the default Show and after
    narrowing the rank window;
  * a player no shown series (DDF Value included) prices above 0 is not listed; a note says how many are hidden;
    a search for a hidden player lists him with 0 values; every listed player is priced above 0 by some shown series;
  * Rank by always offers ESPN and CBS rest of season (and Razzball when the engine has it), shown or not; choosing one
    ranks the list by that series (descending) and puts it on the chart legend and in the table.

Discrimination: test_guard_fails_on_broken_builds serves v2.js with the axis back at 0, zero players listed, and
the projection models not offered, and requires failures.
"""
from __future__ import annotations

import contextlib
import functools
import http.server
import math
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

READ = """() => { const V = window.TradeValueV2, C = window.TradeValueCurveControls; const view = V.view(); const chart = V.chart();
  const ticks = chart ? [...chart.svg.querySelectorAll('.axis text[text-anchor="end"]')].map(t => Number(t.textContent)) : [];
  const keys = chart.keys;
  const slice = chart.slice.map(r => keys.map(k => r.values[k]));
  return {ticks, slice, keys, listed: view.rows.length, total: view.totalRows, hiddenZero: view.hiddenZero,
    rowsAllZero: view.rows.filter(r => !view.plotKeys.concat(view.vorpKeys).some(k => Number.isFinite(r.values[k]) && r.values[k] > 0)).length,
    note: document.getElementById('v2FilterNote').hidden ? '' : document.getElementById('v2FilterNote').textContent,
    rankOptions: [...document.querySelectorAll('#v2RankBy option')].map(o => o.value), rank: C.getRankSource(),
    first: view.visible.slice(0, 8).map(r => r.values[C.getRankSource()]), legend: [...document.querySelectorAll('#v2Legend .v2-legend-item')].map(b => b.dataset.series),
    heads: [...document.querySelectorAll('#v2Table thead th')].map(th => th.textContent.trim())}; }"""


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


def expected_ticks(slice_rows):
    values = [v for row in slice_rows for v in row if isinstance(v, (int, float)) and v > 0]
    if not values:
        return None
    lo, hi = min(values), max(values)
    if hi - lo < 1:
        lo, hi = max(0, lo - 0.5), hi + 0.5
    pad = (hi - lo) * 0.04
    step = next((s for s in (0.5, 1, 2, 5, 10, 20, 50) if (hi - lo + 2 * pad) / s <= 6), 50)
    low = max(0, math.floor((lo - pad) / step) * step)
    high = math.ceil((hi + pad) / step) * step
    ticks, v = [], low
    while v <= high + 1e-9:
        ticks.append(round(v, 4))
        v += step
    return ticks, lo, hi


def check_axis(snap, tag):
    errors = []
    want = expected_ticks(snap["slice"])
    if not want:
        return errors
    ticks, lo, hi = want
    got = [round(t, 4) for t in snap["ticks"]]
    if got != ticks:
        errors.append(f"{tag}Y ticks {got}, want {ticks} for visible values {lo:.1f}..{hi:.1f}")
    if got and (got[0] > lo or got[-1] < hi):
        errors.append(f"{tag}ticks {got[0]}..{got[-1]} do not cover the visible values {lo:.1f}..{hi:.1f}")
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
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            page_errors: list[str] = []
            page.on("pageerror", lambda e: page_errors.append(str(e)))
            page.route(lambda u: not u.startswith("http://127.0.0.1"), lambda route: route.abort())
            if patch:
                page.route("**/v2/v2.js*", lambda route, *_: route.fulfill(status=200, content_type="text/javascript", body=js))
            page.goto(base + "#player-values", wait_until="networkidle")
            page.wait_for_function("() => window.TradeValueV2 && window.TradeValueV2.chart()", timeout=60000)
            page.wait_for_timeout(500)
            snap = page.evaluate(READ)
            # Y axis follows the visible points.
            errors += check_axis(snap, "[default Show] ")
            page.evaluate("() => { const hi = document.getElementById('v2BrushHi'); hi.value = '40'; hi.dispatchEvent(new Event('input', {bubbles: true})); }")
            page.wait_for_timeout(500)
            errors += check_axis(page.evaluate(READ), "[ranks 1-40] ")
            page.select_option("#v2Show", "all")
            page.wait_for_timeout(500)
            snap = page.evaluate(READ)
            errors += check_axis(snap, "[all ranks] ")
            # All-zero players are hidden, counted, and found again by search.
            if snap["rowsAllZero"]:
                errors.append(f"{snap['rowsAllZero']} listed players have no value above 0 on any shown series")
            if snap["hiddenZero"] <= 0:
                errors.append("no all-zero players were hidden: the engine has hundreds of them")
            elif f"{snap['hiddenZero']} players with a value of 0 on every shown series are hidden" not in snap["note"]:
                errors.append(f"hidden count {snap['hiddenZero']} not in the note: {snap['note']!r}")
            if snap["listed"] + snap["hiddenZero"] != snap["total"]:
                errors.append(f"listed {snap['listed']} + hidden {snap['hiddenZero']} != total {snap['total']}")
            zero_name = page.evaluate("""() => { const C = window.TradeValueCurveControls, V = window.TradeValueV2.view();
              const keys = V.plotKeys.concat(V.vorpKeys);
              const row = C.getRows().find(r => !keys.some(k => Number.isFinite(r.values[k]) && r.values[k] > 0)); return row ? row.name : null; }""")
            if zero_name:
                page.fill("#v2Search", zero_name)
                page.wait_for_timeout(600)
                found = page.evaluate("(n) => window.TradeValueV2.view().rows.some(r => r.name === n)", zero_name)
                if not found:
                    errors.append(f"searching for the hidden player {zero_name!r} does not list him")
                page.fill("#v2Search", "")
                page.wait_for_timeout(400)
            # Rank by the DDF projection models.
            opts = page.evaluate(READ)["rankOptions"]
            for key in ("espn", "cbsros"):
                if key not in opts:
                    errors.append(f"Rank by does not offer {key}: {opts}")
            if "espn" in opts:
                page.select_option("#v2RankBy", "espn")
                page.wait_for_timeout(600)
                snap = page.evaluate(READ)
                if snap["rank"] != "espn":
                    errors.append(f"Rank by espn left the ranking on {snap['rank']}")
                vals = [v for v in snap["first"] if isinstance(v, (int, float))]
                if vals != sorted(vals, reverse=True) or not vals:
                    errors.append(f"ranked by espn but the first rows are {snap['first']}")
                if "espn" not in snap["legend"] or not any("ESPN" in h for h in snap["heads"]):
                    errors.append(f"ESPN ranks the list but is not on the chart legend {snap['legend']} or in the table {snap['heads']}")
            if page_errors:
                errors.append(f"page errors {page_errors}")
            page.close()
        finally:
            browser.close()
    return errors


PATCHES = {
    "axis back at 0": ("      if (fit) { ymin = fit.min; ymax = fit.max; ystep = fit.step; axisZoom = true; }", ""),
    "zero players listed": ("    const listed = needle ? allRows : allRows.filter(pricedAbove0);", "    const listed = allRows;"),
    "projection models not offered": ('    ["espn", "cbsros", "razzball"].forEach(key => { if (view.infoByKey[key] && !rankKeys.includes(key)) rankKeys.push(key); });', ""),
    "padding dropped": ("    const pad = (hi - lo) * 0.04;", "    const pad = 0;"),
}


class ChartFitRenderTest(unittest.TestCase):
    def test_fit_zero_players_and_rank_by(self):
        self.assertEqual(run_checks(), [])

    def test_guard_fails_on_broken_builds(self):
        for name, patch in PATCHES.items():
            with self.subTest(patch=name):
                try:
                    errors = run_checks(patch)
                except Exception as exc:
                    if "unavailable" in type(exc).__name__.lower() or type(exc).__name__ == "SkipTest":
                        raise
                    errors = [f"walk-through stopped: {type(exc).__name__}"]
                self.assertNotEqual(errors, [], f"checks did not catch: {name}")


if __name__ == "__main__":
    unittest.main()
