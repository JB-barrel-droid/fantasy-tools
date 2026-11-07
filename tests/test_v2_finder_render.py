"""v2 Find a trade (JEG-481), rendered.

Builds dist/v2 into a temp copy of the built dist/ and loads Compare a trade headless at 1440 and 390.
Two rosters are typed in with the card's own player search (top players by DDF Value, alternating, so
a trade can clear), then "Find trades" runs. Checks, against the engine's own rows:

  * every listed trade has DDF Value edge > 0 (sum of what you receive - sum of what you give, from
    getAllRows), at least one available trade chart at net <= 0 for you (JEG-1403; 3 of 4 before), and the edge
    shown is that sum;
  * the list is ranked (scores never rise down the list) and has at most 10 rows;
  * "Open in Compare a trade" opens the same players on the two sides of Compare a trade;
  * a player cannot be added to both rosters; Remove empties a roster and clears the result;
  * the card is a module (chevron), no page errors, no sideways scroll at 390.

Discrimination: test_guard_fails_on_broken_builds serves finder.js with the DDF edge read the wrong way round,
and with the link opening the wrong sides, and requires each to fail.
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

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipelines"))
import build_v2_page  # noqa: E402
from tests import _render_env  # noqa: E402
from tests.test_published_league_settings_render import _chromium_executable
from tests._holds import pin_holds_in_dist
from tests.test_v2_modules_render import DIST, _serve

ROOT = Path(__file__).resolve().parents[1]
FINDER_JS = ROOT / "app" / "v2" / "finder.js"


@contextlib.contextmanager
def _built_dist():
    """Built dist with the pinned holds (CBS held), so the held-chart check has a held chart to look for (JEG-881)."""
    # build_v2_page reads the gitignored build/engine/index.html; build it here so a module without
    # setUpModule (or a single test run on a clean checkout) does not depend on an earlier module's build (JEG-1182).
    _render_env.ensure_built()
    if not (DIST / "index.html").exists():
        raise _render_env.unavailable("dist/index.html is not built")
    with tempfile.TemporaryDirectory() as tmp:
        dist = Path(tmp) / "dist"
        shutil.copytree(DIST, dist, ignore=shutil.ignore_patterns("v2"))
        pin_holds_in_dist(dist)
        build_v2_page.build(dist)

        class Quiet(http.server.SimpleHTTPRequestHandler):
            def log_message(self, format, *args):
                pass

        with socketserver.ThreadingTCPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=str(dist))) as server:
            server.daemon_threads = True
            threading.Thread(target=server.serve_forever, daemon=True).start()
            try:
                yield f"http://127.0.0.1:{server.server_address[1]}/v2/"
            finally:
                server.shutdown()


def setUpModule():
    _render_env.ensure_built()


PICK = """() => {
  const C = window.TradeValueCurveControls;
  const rows = C.getAllRows().filter(r => r.values && Number.isFinite(r.values.ddf_value) && r.name)
    .sort((a, b) => b.values.ddf_value - a.values.ddf_value);
  const names = new Map(); rows.forEach(r => names.set(r.name, (names.get(r.name) || 0) + 1));
  const unique = rows.filter(r => names.get(r.name) === 1).slice(0, 30);
  return {mine: unique.filter((_, i) => i % 2 === 0).slice(0, 12).map(r => r.name),
          theirs: unique.filter((_, i) => i % 2 === 1).slice(0, 6).map(r => r.name)};
}"""

READ = """() => {
  const C = window.TradeValueCurveControls;
  const byName = new Map(C.getAllRows().map(r => [r.name, r]));
  // JEG-819: only count charts the engine says are available (same set the finder now uses).
  const available = new Set((C.getSourceInfo ? C.getSourceInfo() : []).filter(i => i.available).map(i => i.key));
  const chartKeys = ['usatoday', 'fantasycalc', 'fantasypros', 'cbs'].filter(k => available.has(k));
  const minCharts = Math.min(1, chartKeys.length);   // JEG-1403: the search's default gate is one chart
  const items = [...document.querySelectorAll('#v2FindList li')].map(li => {
    const text = li.querySelector('b').textContent;
    const [give, get] = text.replace('You give ', '').split('; you receive ').map(s => s.split(' + '));
    const sum = (names, key) => names.reduce((a, n) => a + byName.get(n).values[key], 0);
    const nets = chartKeys.map(k => sum(get, k) - sum(give, k));
    return {give, get, shownEdge: Number(li.dataset.findEdge), edge: sum(get, 'ddf_value') - sum(give, 'ddf_value'),
      accepting: nets.filter(n => Math.abs(n) < 0.05 || n < 0).length, chartCount: chartKeys.length, minCharts,
      href: li.querySelector('a').getAttribute('href')};
  });
  // JEG-819: names of held/unavailable charts, to verify they do not appear in the output text.
  const CHART_NAMES = {usatoday: 'USA Today', fantasycalc: 'FantasyCalc', fantasypros: 'FantasyPros', cbs: 'CBS Sports'};
  const heldNames = ['usatoday', 'fantasycalc', 'fantasypros', 'cbs'].filter(k => !available.has(k)).map(k => CHART_NAMES[k]);
  return {items, rowsShown: items.length, chartCount: chartKeys.length, minCharts, heldNames,
    out: document.getElementById('v2FindOut').textContent.trim()};
}"""


def add(page, side, name):
    page.fill(f"#v2Find{side}Search", name)
    page.click(f"#v2Find{side}Results button:not([disabled]) >> nth=0")


def check(page, tag, width) -> list[str]:
    errors = []
    page.evaluate("() => { location.hash = '#compare-trade'; }")
    page.wait_for_function("() => window.TradeValueV2 && window.TradeValueV2.compare() && document.getElementById('v2Find')", timeout=60000)
    # JEG-852: the finder is its own tab; Compare a trade no longer holds it.
    if page.evaluate("() => Boolean(document.querySelector('#v2Compare #v2Find'))"):
        errors.append(tag + "the finder is still inside Compare a trade")
    page.evaluate("() => { location.hash = '#find-trade'; }")
    page.wait_for_function("() => !document.getElementById('v2FindTrade').hidden", timeout=20000)
    state = page.evaluate("""() => ({compare: document.getElementById('v2Compare').hidden, find: document.querySelector('.v2-tab[data-view=find]').getAttribute('aria-current'),
      inPage: Boolean(document.querySelector('#v2FindTrade #v2Find')), customize: document.getElementById('v2EditSources').hidden})""")
    if not state["compare"] or state["find"] != "page" or not state["inPage"]:
        errors.append(tag + f"Find a trade tab did not route cleanly: {state}")
    if errors:
        return errors
    pick = page.evaluate(PICK)
    for name in pick["mine"]:
        add(page, "Mine", name)
    for name in pick["theirs"]:
        add(page, "Theirs", name)
    # A player already on a roster cannot be added to the other.
    page.fill("#v2FindTheirsSearch", pick["mine"][0])
    if page.locator("#v2FindTheirsResults button:not([disabled])").count():
        errors.append(tag + "a player on my roster can be added to theirs")
    page.fill("#v2FindTheirsSearch", "")
    page.select_option("#v2FindSize", "3")
    page.click("#v2FindGo")
    page.wait_for_timeout(300)
    got = page.evaluate(READ)
    if not got["items"]:
        errors.append(tag + f"no trade found for the typed rosters: {got['out']}")
        return errors
    if got["rowsShown"] > 10:
        errors.append(tag + f"{got['rowsShown']} rows listed, max 10")
    # JEG-819: a held chart must not appear in the finder's output text.
    # JEG-881: the loop is vacuous without a held chart, so require at least one.
    if not got.get("heldNames"):
        errors.append(tag + "no held chart in the served fixture: the held-name check proves nothing")
    for held in got.get("heldNames", []):
        if held in got["out"]:
            errors.append(tag + f"held chart '{held}' appears in finder output")
    for item in got["items"]:
        if item["edge"] < 0.05 or abs(item["edge"] - item["shownEdge"]) > 1e-6:
            errors.append(tag + f"edge {item['edge']} vs shown {item['shownEdge']}: {item['give']} -> {item['get']}")
        if item["accepting"] < item["minCharts"]:
            errors.append(tag + f"only {item['accepting']} of {item['chartCount']} available charts accept (need {item['minCharts']}): {item['give']} -> {item['get']}")
    # The link opens those players on the two sides.
    first = got["items"][0]
    page.click("#v2FindList li >> nth=0 >> a")
    page.wait_for_function("() => document.querySelectorAll('#v2GivePlayers li').length && document.querySelectorAll('#v2GetPlayers li').length && !document.querySelector('#v2GivePlayers li.is-example') && location.hash.includes('give=')", timeout=20000)
    sides = page.evaluate("""() => ({give: [...document.querySelectorAll('#v2GivePlayers li .v2-trade-name')].map(e => e.textContent),
      get: [...document.querySelectorAll('#v2GetPlayers li .v2-trade-name')].map(e => e.textContent)})""")
    if sorted(sides["give"]) != sorted(first["give"]) or sorted(sides["get"]) != sorted(first["get"]):
        errors.append(tag + f"link opened {sides}, expected give {first['give']} get {first['get']}")
    # Remove clears the result.
    page.evaluate("() => { location.hash = '#find-trade'; }")
    page.click("#v2FindEdit")   # JEG-972: the roster input is folded after Find
    page.click("#v2FindMinePlayers li >> nth=0 >> button.v2-find-remove")
    if page.evaluate("() => !document.getElementById('v2FindOut').hidden"):
        errors.append(tag + "the result stayed after a roster changed")
    if not page.evaluate("() => Boolean(document.querySelector('#v2Find > .v2-mod-ctl .v2-mod-chevron'))"):
        errors.append(tag + "the card has no chevron")
    if width <= 390 and page.evaluate("() => document.documentElement.scrollWidth - innerWidth") > 0:
        errors.append(tag + "horizontal overflow")
    return errors


def run_checks(overrides=None, viewports=((1440, 900), (390, 844))) -> list[str]:
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
                context = browser.new_context(viewport={"width": width, "height": height})
                page = context.new_page()
                page_errors = []
                page.on("pageerror", lambda e: page_errors.append(str(e)))
                page.route(lambda u: not u.startswith("http://127.0.0.1"), lambda route: route.abort())
                for name, body in (overrides or {}).items():
                    page.route(f"**/v2/{name}*", functools.partial(_serve, body, "text/javascript"))
                page.goto(base + "#find-trade", wait_until="networkidle")
                page.wait_for_function("() => window.TradeValueV2 && window.TradeValueV2.view()", timeout=60000)
                errors += check(page, f"[{width}px] ", width)
                if page_errors:
                    errors.append(f"[{width}px] page errors {page_errors}")
                context.close()
        finally:
            browser.close()
    return errors


class FinderRenderTest(unittest.TestCase):
    def test_find_a_trade(self):
        self.assertEqual(run_checks(), [])

    def test_guard_fails_on_broken_builds(self):
        js = FINDER_JS.read_text(encoding="utf-8")
        broken = {
            "edge read the wrong way round": js.replace("? null : get[0] - give[0];", "? null : give[0] - get[0];", 1),
            "held chart counted (availability filter dropped)": js.replace("const charts = CHART_KEYS.filter(key => availableKeys.has(key));", "const charts = CHART_KEYS.slice();", 1),
            "finder back inside Compare a trade": js.replace('const host = $("v2FindTrade");', 'const host = $("v2Compare");', 1),
            "link swaps the sides": js.replace("#compare-trade?give=${ids(giveRows)}&get=${ids(recvRows)}", "#compare-trade?give=${ids(recvRows)}&get=${ids(giveRows)}", 1),
        }
        for name, body in broken.items():
            with self.subTest(mutation=name):
                self.assertNotEqual(body, js, f"mutation anchor for {name!r} is stale")
                self.assertNotEqual(run_checks({"finder.js": body}, viewports=((1440, 900),)), [], f"not caught: {name}")


if __name__ == "__main__":
    unittest.main()
