"""Customize on every page, with per-page defaults (JEG-498, contract GL-07 / GL-11).

Builds dist/v2 into a temp copy of the built dist/ and loads it headless:

  * Player values, Trade targets, Risers & fallers and Compare a trade each show a Customize button with a 44 px hit area;
  * each page's Customize lists every dataset the engine knows, and the ticked set is the page's default:
    Trade targets = DDF Value + the as-published charts, Risers opens on DDF Value, Compare = DDF Value + every chart;
  * a change on one page applies to that page only (the others keep their set), and it is remembered on the device
    (it survives a reload);
  * Edit league is the primary button of the league bar and Position weights is the secondary one.

Discrimination: test_guard_fails_on_broken_builds serves v2.js with Compare reading Player values' set, with every page
sharing one saved list and with Risers ignoring its ticked series; each must fail the checks.
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
PAGES = {"values": "#player-values", "targets": "#trade-targets", "risers": "#risers-fallers", "compare": "#compare-trade"}
CHARTS = ["usatoday", "fantasycalc", "fantasypros", "cbs"]
# JEG-1073: ddf_value_charts is the same series as DDF Value (the Adjusted trade chart average), hidden via sameAs.
HIDDEN_DUPLICATES = {"ddf_value_charts"}


def _serve(body, content_type, route, *_):
    route.fulfill(status=200, content_type=content_type, body=body)


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


PANEL = """() => ({
  title: document.querySelector('#v2PanelTitle')?.textContent || null,
  summary: document.querySelector('.v2-psummary')?.textContent || '',
  rows: [...document.querySelectorAll('#v2Popover input[data-series]')].map(i => ({key: i.dataset.series, on: i.checked, off: i.disabled}))
})"""


def run_checks(v2_js=None) -> list[str]:
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
            page.goto(base + "#player-values", wait_until="networkidle")
            page.wait_for_function("() => window.TradeValueV2 && document.querySelector('#v2Table tbody tr')", timeout=30000)

            def go(name):
                page.evaluate(f"() => {{ location.hash = '{PAGES[name]}'; }}")
                page.wait_for_function("(h) => location.hash.startsWith(h)", arg=PAGES[name])
                page.wait_for_timeout(300)

            def open_panel(name):
                go(name)
                box = page.evaluate("""() => { const b = document.getElementById('v2EditSources'); const r = b.getBoundingClientRect();
                  return {hidden: b.getClientRects().length === 0, h: r.height, w: r.width}; }""")
                if box["hidden"]:
                    errors.append(f"[{name}] no Customize button on the page")
                    return None
                if box["h"] < 44:
                    errors.append(f"[{name}] Customize hit area is {box['h']:.0f}px high, want 44")
                page.click("#v2EditSources")
                page.wait_for_selector("#v2Popover input[data-series]")
                return page.evaluate(PANEL)

            def done():
                page.click('[data-apply="sources"]')
                page.wait_for_timeout(300)

            known = page.evaluate("() => window.TradeValueCurveControls.getSourceInfo({includeComposite: true}).filter(i => !i.key.endsWith('_adjusted')).map(i => i.key)")
            # JEG-863 / JEG-1073 (Jeremy, 2026-10-25): the duplicate DDF id is hidden from every picker (sameAs ddf_value),
            # Customize included, so "every dataset" is every one a reader can pick.
            known = [key for key in known if key not in HIDDEN_DUPLICATES]
            available = page.evaluate("() => window.TradeValueV2.view().info.filter(i => i.available).map(i => i.key)")
            snap = {}
            for name in PAGES:
                panel = open_panel(name)
                if not panel:
                    continue
                snap[name] = panel
                listed = {row["key"] for row in panel["rows"]}
                if listed != set(known):
                    errors.append(f"[{name}] Customize lists {sorted(listed)}; every dataset is {sorted(known)}")
                if listed & HIDDEN_DUPLICATES:
                    errors.append(f"[{name}] Customize lists the hidden duplicate {sorted(listed & HIDDEN_DUPLICATES)}")
                if name != "values" and "applies to" not in panel["summary"]:
                    errors.append(f"[{name}] summary does not say what it applies to: {panel['summary']!r}")
                page.click("#v2Popover .v2-panel-close")
            on = {name: {r["key"] for r in snap[name]["rows"] if r["on"]} for name in snap}
            want_charts = {k for k in CHARTS if k in available}
            if "ddf_value" not in on.get("targets", set()) or not want_charts <= on.get("targets", set()):
                errors.append(f"[targets] default should be DDF Value + the published charts, got {sorted(on.get('targets', []))}")
            if on.get("risers") != {"ddf_value"}:
                errors.append(f"[risers] default should be DDF Value only, got {sorted(on.get('risers', []))}")
            if "ddf_value" not in on.get("compare", set()) or not want_charts <= on.get("compare", set()):
                errors.append(f"[compare] default should be DDF Value + every chart, got {sorted(on.get('compare', []))}")
            go("risers")
            opened = page.evaluate("() => window.TradeValueV2.risersState.series")
            if opened != "ddf_value":
                errors.append(f"[risers] opens on {opened!r}, want its ticked DDF Value")
            # Ticking another series (and not DDF Value) moves the page to it, when the engine has its prior week.
            other = page.evaluate("""async () => { const C = window.TradeValueCurveControls;
              for (const key of ['fantasycalc', 'usatoday', 'fantasypros', 'cbs']) {
                // JEG-906: a held source is never offered on Risers, so it cannot be the one the page opens on.
                const info = C.getSourceInfo().find(i => i.key === key);
                if ((await C.getPriorWeek(key)).available && !(info && info.available === false)) return key; }
              return null; }""")
            if other:
                page.evaluate("(key) => window.TradeValueV2.setPageKeys('risers', [key])", other)
                page.evaluate("() => { window.TradeValueV2.risersState.series = null; }")
                page.evaluate("() => { location.hash = '#player-values'; }")
                go("risers")
                try:
                    page.wait_for_function("(key) => window.TradeValueV2.risersState.series === key", arg=other, timeout=15000)
                except Exception:
                    now = page.evaluate("() => window.TradeValueV2.risersState.series")
                    errors.append(f"[risers] ticked {other!r} but the page opened on {now!r}")
                page.evaluate("() => window.TradeValueV2.setPageKeys('risers', ['ddf_value'])")

            # One page's change stays on that page, and it is remembered across a reload.
            drop = next((k for k in CHARTS if k in available), None)
            if drop is None:
                errors.append("no published chart is available to test with")
            else:
                panel = open_panel("compare")
                page.uncheck(f'#v2Popover input[data-series="{drop}"]')
                done()
                used = page.evaluate("() => window.TradeValueV2.compare().pointKeys")
                if drop in used:
                    errors.append(f"[compare] {drop} was unticked but Compare still reads it: {used}")
                for other in ("values", "targets"):
                    other_panel = open_panel(other)
                    if not any(r["key"] == drop and r["on"] for r in other_panel["rows"]):
                        errors.append(f"[{other}] {drop} was unticked on Compare only, but it is off here too")
                    page.click("#v2Popover .v2-panel-close")
                go("values")
                page.reload(wait_until="networkidle")
                page.wait_for_function("() => window.TradeValueV2 && document.querySelector('#v2Table tbody tr')", timeout=30000)
                panel = open_panel("compare")
                if any(r["key"] == drop and r["on"] for r in panel["rows"]):
                    errors.append(f"[compare] the unticked {drop} came back after a reload")
                page.click("#v2Popover .v2-panel-close")
                # Targets: leaving a chart out removes it from the comparison and from the chart picker.
                panel = open_panel("targets")
                page.uncheck(f'#v2Popover input[data-series="{drop}"]')
                done()
                t_used = page.evaluate("() => window.TradeValueV2.targets().used")
                options = page.evaluate("() => [...document.querySelectorAll('#v2TChart option')].map(o => o.value)")
                if drop in t_used or drop in options:
                    errors.append(f"[targets] {drop} unticked but still compared ({t_used}) or offered ({options})")

            # League bar: Edit league primary, Position weights secondary.
            go("values")
            bar = page.evaluate("""() => { const e = document.getElementById('v2EditLeague'), w = document.getElementById('v2Weights');
              return {edit: e.classList.contains('v2-btn-primary'), weights: w.classList.contains('v2-btn-primary'),
                bg: [getComputedStyle(e).backgroundColor, getComputedStyle(w).backgroundColor]}; }""")
            if not bar["edit"] or bar["weights"] or bar["bg"][0] == bar["bg"][1]:
                errors.append(f"league bar: Edit league must be primary and Position weights secondary: {bar}")
            if page_errors:
                errors.append(f"page errors {page_errors}")
            page.close()
        finally:
            browser.close()
    return errors


class CustomizePagesRenderTest(unittest.TestCase):
    def test_customize_on_every_page(self):
        self.assertEqual(run_checks(), [])

    def test_guard_fails_on_broken_builds(self):
        js = V2_JS.read_text(encoding="utf-8")
        broken = {
            "compare reads Player values' set": (
                'const mine = pageKeys("compare").filter(key => view.infoByKey[key]);',
                "const mine = view.active.filter(key => view.infoByKey[key]);"),
            "every page shares one saved list": (
                "const saved = pageSaved[page];", "const saved = pageSaved.compare;"),
            "risers picker ignores its Customize": (
                "const ticked = choices.filter(c => mineSeries.has(c.key));", "const ticked = [];"),
        }
        for name, (anchor, replacement) in broken.items():
            with self.subTest(mutation=name):
                self.assertIn(anchor, js, f"mutation anchor for {name!r} is stale")
                self.assertNotEqual(run_checks(v2_js=js.replace(anchor, replacement, 1)), [],
                                    f"render checks did not catch: {name}")


if __name__ == "__main__":
    unittest.main()
