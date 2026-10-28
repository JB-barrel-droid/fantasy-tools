"""v2 source counts are the sources the blend reads (JEG-807).

Live QA 2026-10-22: every DDF Value row said "1 source" (true: four sources were
red-held and the two unheld charts were not yet published for the content week),
while Customize said "Built from 5 inputs", Trade targets' "On this page" said
"+ 4 rescaled trade charts" with 2 compared, and Risers said "5 of 5 sources have
a prior week". The engine keeps a held source in its pipeline pool (`inputs`,
JEG-569: weights and pie stay stable) but blends only `series`; v2 counted the
pool.

Builds dist/v2 into a temp copy of the built dist/ with the pinned holds
(tests/_holds.py: CBS held, plus Razzball held here, JEG-804), loads it headless and checks against the engine:

  * Overrides > Custom blend (JEG-1044, replaced the Customize DDF blend tab and its "Using N of M sources"): the
    sources that carry a share are the ticked inputs the engine blends (getCompositeInputs().series), their shares sum
    to 100, and a held input's row says "Paused this week" and is locked, as is its preset; Customize's Chart lines
    still say "Paused this week" for a held chart;
  * Trade targets "On this page": the rescaled trade chart count is the number of
    charts the page can read (available), never a held one;
  * Risers (DDF Value): "a of b sources have a prior week" counts the blended
    series (getPriorWeek("ddf_value").series), not the pool.

Discrimination: test_guard_fails_on_broken_builds serves v2.js with each count
read from the pool again and requires the checks to fail.
"""
from __future__ import annotations

import contextlib
import functools
import http.server
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
from tests._holds import pin_holds_in_dist  # noqa: E402


def setUpModule():
    _render_env.ensure_built()


V2_JS = ROOT / "app" / "v2" / "v2.js"
# JEG-804 (#814): DDF Value is projections-only, so the pinned CBS hold (a trade chart) no longer reaches the blend.
# Razzball is held in this test's copy so the pool (3 projections) still differs from the blend (2), the JEG-807 premise.
HELD_INPUT = ("razzball",)


def _serve(body, content_type, route, *_):
    route.fulfill(status=200, content_type=content_type, body=body)


@contextlib.contextmanager
def _built_dist():
    if not (DIST / "index.html").exists():
        raise _render_env.unavailable("dist/index.html is not built")
    with tempfile.TemporaryDirectory() as tmp:
        dist = Path(tmp) / "dist"
        shutil.copytree(DIST, dist, ignore=shutil.ignore_patterns("v2"))
        pin_holds_in_dist(dist, extra_held=HELD_INPUT)
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


ENGINE = """() => {
  const C = window.TradeValueCurveControls;
  const ci = C.getCompositeInputs();
  const info = C.getSourceInfo().filter(i => !i.key.endsWith('_adjusted'));
  const charts = ['usatoday', 'fantasycalc', 'fantasypros', 'cbs'];
  return {inputs: ci.inputs, series: ci.series, allowed: ci.allowed,
    excluded: Object.fromEntries((ci.excluded || []).map(e => [e.key, e.reason])),
    availableCharts: charts.filter(k => info.find(i => i.key === k && i.available)),
    heldCharts: charts.filter(k => { const i = info.find(x => x.key === k); return i && !i.available && /^held/i.test(i.excludedReason || ''); })};
}"""

OVERRIDES = """() => ({
  rows: Object.fromEntries([...document.querySelectorAll('.v2-ov-wrow')].map(r => [r.dataset.sourceRow, {
    paused: r.classList.contains('is-paused'), note: (r.querySelector('.v2-ov-wnote') || {}).textContent || '',
    pct: (r.querySelector('[data-pct]') || {}).textContent || '', locked: r.querySelector('input[type=checkbox]').disabled}])),
  presets: Object.fromEntries([...document.querySelectorAll('#v2OvPresets [role=radio]')].map(b =>
    [b.dataset.preset, b.getAttribute('aria-disabled') === 'true']))
})"""

CUSTOMIZE = """() => ({
  tabs: document.querySelectorAll('#v2Popover [role=tab], #v2Popover [data-ddf-input]').length,
  chartReasons: Object.fromEntries([...document.querySelectorAll('#v2Popover input[data-series]')].map(b =>
    [b.dataset.series, b.closest('label')?.querySelector('.v2-meta')?.textContent || '']))
})"""


def run_checks(v2_js=None, overrides_js=None) -> list[str]:
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
            page = browser.new_page(viewport={"width": 1280, "height": 900})
            page_errors = []
            page.on("pageerror", lambda e: page_errors.append(str(e)))
            page.route(lambda u: not u.startswith("http://127.0.0.1"), lambda route: route.abort())
            if v2_js is not None:
                page.route("**/v2/v2.js*", functools.partial(_serve, v2_js, "text/javascript"))
            if overrides_js is not None:
                page.route("**/v2/overrides.js*", functools.partial(_serve, overrides_js, "text/javascript"))
            page.goto(base + "#player-values", wait_until="networkidle")
            page.wait_for_function("() => window.TradeValueV2 && document.querySelector('#v2Table tbody tr')", timeout=30000)
            engine = page.evaluate(ENGINE)
            # JEG-1212: the public chart comparison is a distinct readout from
            # FantasyCalc, and a held CBS chart cannot silently lower its denominator.
            page.locator("#v2Table tbody tr:first-child td:first-child").click()
            page.wait_for_selector("#v2Drawer [data-comparison-view]")
            comparisons = page.locator("#v2Drawer [data-comparison-view]").all_text_contents()
            if len(comparisons) != 2 or not comparisons[0].startswith("Published chart average: Unavailable"):
                errors.append(f"Player detail comparison with held CBS is {comparisons!r}")
            if len(comparisons) == 2 and not comparisons[1].startswith("Observed-trade estimate:"):
                errors.append(f"FantasyCalc is not a distinct observed-trade readout: {comparisons!r}")
            page.get_by_role("button", name="Close player details").click()
            hidden = [k for k in engine["inputs"] if k not in engine["series"]]
            # Premise: the Razzball hold keeps a hidden source in the pool, so pool and blend differ.
            if not hidden:
                errors.append(f"premise: no held source in the engine pool (inputs {engine['inputs']}, series {engine['series']})")

            def go(name):
                page.evaluate(f"() => {{ location.hash = '{name}'; }}")
                page.wait_for_function("(h) => location.hash.startsWith(h)", arg=name)
                page.wait_for_timeout(300)

            # 1. Overrides > Custom blend: the share rows count the sources the engine blends, not the pool.
            go("#value-overrides")
            page.wait_for_selector("#v2OvPresets")
            page.click('#v2OvPresets [data-preset="blend"]')
            page.wait_for_selector("#v2OvOn-espn")
            page.wait_for_timeout(300)
            panel = page.evaluate(OVERRIDES)
            sharing = sorted(k for k, r in panel["rows"].items() if re.match(r"\d+% of the blend", r["pct"]))
            want_used = sorted(k for k in engine["series"] if k in engine["inputs"])
            if sharing != want_used:
                errors.append(f"Overrides shows a share for {sharing}; the engine blends {want_used} (pool {engine['inputs']}, blend {engine['series']})")
            total = sum(int(re.match(r"(\d+)%", panel["rows"][k]["pct"]).group(1)) for k in sharing)
            if sharing and total != 100:
                errors.append(f"Overrides' shares sum to {total}, want 100: {[panel['rows'][k]['pct'] for k in sharing]}")
            for key in hidden:
                row = panel["rows"].get(key) or {}
                if "Paused this week" not in row.get("note", "") or not row.get("paused") or not row.get("locked") or row.get("pct") != "paused":
                    errors.append(f"Overrides row for held input {key} is {row}, want paused, locked, 'Paused this week'")
                if not panel["presets"].get(f"single:{key}"):
                    errors.append(f"Overrides still offers held input {key} as a single-source basis")
            page.click('#v2OvPresets [data-preset="default"]')
            go("#player-values")
            page.click("#v2EditSources")
            page.wait_for_selector("#v2Popover .v2-panel-body")
            panel = page.evaluate(CUSTOMIZE)
            if panel["tabs"]:
                errors.append(f"Customize still has {panel['tabs']} tab or DDF-input controls")
            for key in engine["heldCharts"]:
                if "Paused this week" not in panel["chartReasons"].get(key, ""):
                    errors.append(f"Customize row for held chart {key} says {panel['chartReasons'].get(key)!r}, want 'Paused this week'")
            page.click("#v2Popover .v2-panel-close")

            # 2. Trade targets "On this page": only the charts the page reads are counted.
            go("#trade-targets")
            showing = page.evaluate("() => document.getElementById('v2ShowingText').textContent")
            # JEG-1212: chart inputs are shown in two categories. The old assertion
            # expected one combined label; count both without changing the tools' keys.
            published = re.search(r"(\d+) published charts?", showing)
            observed = re.search(r"(\d+) observed-trade estimates?", showing)
            used = page.evaluate("() => window.TradeValueV2.targets().used")
            counted = (int(published.group(1)) if published else 0) + (int(observed.group(1)) if observed else 0)
            if counted != len(used) or set(used) - set(engine["availableCharts"]):
                errors.append(f"Trade targets says {showing!r}; it compares {used} (available {engine['availableCharts']})")

            # 3. Risers on DDF Value: the prior-week count is over the blended series.
            go("#risers-fallers")
            page.wait_for_function("() => !/Recomputing|Reading/.test(document.getElementById('v2RMeta').textContent)", timeout=30000)
            mover = page.locator("#v2RRise li[data-player-key]").first
            if mover.count():
                mover.click()
                page.wait_for_selector("#v2Drawer:not([hidden])")
                if page.locator("#v2Drawer [data-comparison-view]").count():
                    errors.append("Risers' mixed-week player row shows a current-view source average")
                page.get_by_role("button", name="Close player details").click()
            prior = page.evaluate("async () => { const p = await window.TradeValueCurveControls.getPriorWeek('ddf_value');"
                                  " return {available: p.available, series: p.series || null, sources: p.sources || null}; }")
            meta = page.evaluate("() => document.getElementById('v2RMeta').textContent")
            if prior["available"] and prior["series"] is not None:
                have = re.search(r"(\d+) of (\d+) sources have a prior week", meta)
                want = (len([k for k in (prior["sources"] or []) if k in prior["series"]]), len(prior["series"]))
                if not have:
                    errors.append(f"Risers meta {meta!r} has no prior-week source count")
                elif (int(have.group(1)), int(have.group(2))) != want:
                    errors.append(f"Risers meta {meta!r}; engine blends {want[0]} of {want[1]} (pool {prior['sources']})")
            if page_errors:
                errors.append(f"page errors {page_errors}")
            page.close()
        finally:
            browser.close()
    return errors


class SourceCountRenderTest(unittest.TestCase):
    def test_counts_match_engine_blend(self):
        self.assertEqual(run_checks(), [])

    def test_guard_fails_on_broken_builds(self):
        js = V2_JS.read_text(encoding="utf-8")
        overrides = (ROOT / "app" / "v2" / "overrides.js").read_text(encoding="utf-8")
        broken_overrides = {
            "Overrides marks no source paused": (
                "const paused = st && !st.usable;",
                "const paused = false;"),
            "Overrides shares count the pool": (
                "const on = BASIS_KEYS.filter(key => S.blend[key].on && isUsable(key));",
                "const on = BASIS_KEYS.filter(key => S.blend[key].on);"),
        }
        for name, (anchor, replacement) in broken_overrides.items():
            with self.subTest(mutation=name):
                self.assertIn(anchor, overrides, f"mutation anchor for {name!r} is stale")
                self.assertNotEqual(run_checks(overrides_js=overrides.replace(anchor, replacement, 1)), [],
                                    f"render checks did not catch: {name}")
        broken = {
            "On this page counts held charts": (
                "view.infoByKey[key] && view.infoByKey[key].available && !pageCannotUse(page, key)",
                "view.infoByKey[key] && !pageCannotUse(page, key)"),
            "Risers counts the pool": (
                "const blendSeries = Array.isArray(prior.series) ? prior.series : prior.inputs;",
                "const blendSeries = prior.inputs;"),
            "held reads as not available for this league": (
                "heldReason(item) ? \"Paused this week\"\n            : item.paused",
                "item.paused"),
        }
        for name, (anchor, replacement) in broken.items():
            with self.subTest(mutation=name):
                self.assertIn(anchor, js, f"mutation anchor for {name!r} is stale")
                self.assertNotEqual(run_checks(v2_js=js.replace(anchor, replacement, 1)), [],
                                    f"render checks did not catch: {name}")


if __name__ == "__main__":
    unittest.main()
