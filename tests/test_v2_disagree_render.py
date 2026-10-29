"""v2 Risers & fallers: where the market and the projections disagree, rendered (JEG-488, contract RF-02).

The built data may have no prior week for the Trade chart average (charts not yet published for the week), so the
page is fed deterministic priors for ddf_value_charts and ddf_value_projections and the first rows' current values
(the engine's getPriorWeek and getRows are wrapped before the tab opens). Then at 1440 and 390 px:

  * "Market moved, projections didn't" and "Projections moved, market didn't" list exactly the players an
    independent recomputation says qualify (|move| >= 2.5 on one side and <= 1.0 on the other), largest move first,
    each with both changes and the rule-based read;
  * players that moved on both sides, on neither, or only just short of the thresholds are in no list;
  * with no prior week for a series the section says so and lists nothing;
  * no page errors and no horizontal overflow at 390 px.

Discrimination: test_guard_fails_on_broken_builds serves movers.js with the threshold raised and the reads swapped,
and requires failures.
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
MOVERS_JS = ROOT / "app" / "v2" / "movers.js"

from tests import _render_env  # noqa: E402
from tests.test_published_league_settings_render import _chromium_executable  # noqa: E402

CASES = [(3.0, 0.5), (-4.0, 0.2), (0.3, 3.0), (-0.5, -2.6), (2.5, 1.0), (2.4, 0.0), (2.5, 1.05), (3.0, 3.0), (0.2, 0.3),
         (-2.5, -1.0), (0.0, 6.0), (5.0, -0.9), (1.0, 2.5), (1.05, 2.5)]
READS = {"market|up": "Buying in without the production: sell", "market|down": "Panic the projections don't share: buy",
         "projections|up": "Market hasn't caught up: buy", "projections|down": "Market hasn't reacted: sell"}

FEED = """(cases) => { const C = window.TradeValueCurveControls; const origRows = C.getRows.bind(C); const origPrior = C.getPriorWeek.bind(C);
  const order = origRows().map(r => String(r.player_key));
  const delta = new Map(order.slice(0, cases.length).map((k, i) => [k, cases[i]]));
  C.getRows = () => origRows().map(r => { const d = delta.get(String(r.player_key)); return d ? {...r, values: {...r.values,
    ddf_value_charts: 20 + d[0], ddf_value_projections: 20 + d[1]}} : {...r, values: {...r.values, ddf_value_charts: 20, ddf_value_projections: 20}}; });
  C.getPriorWeek = async key => (key === 'ddf_value_charts' || key === 'ddf_value_projections')
    ? {available: true, currentWeek: 6, priorWeek: 5, values: Object.fromEntries(order.map(k => [k, 20]))} : origPrior(key);
  window.__order = order.slice(0, cases.length); }"""

READ = """() => {
  const list = id => [...document.querySelectorAll('#' + id + ' li[data-player-key]')].map(li => ({key: li.dataset.playerKey,
    moved: li.dataset.moved, lead: li.querySelector('[data-col=moved]').textContent, market: li.querySelector('[data-col=market]').textContent,
    projections: li.querySelector('[data-col=projections]').textContent, read: li.querySelector('[data-col=read]').textContent}));
  return {order: window.__order, mkt: list('v2RMkt'), proj: list('v2RProj'), meta: document.getElementById('v2RDisagreeMeta').textContent,
    empty: [document.getElementById('v2RMktEmpty').hidden, document.getElementById('v2RProjEmpty').hidden],
    h2: document.getElementById('v2RDisagreeTitle').textContent, overflow: document.documentElement.scrollWidth - innerWidth};
}"""


@contextlib.contextmanager
def _served(movers_js=None):
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


def expected():
    market, projections = [], []
    for i, (dm, dp) in enumerate(CASES):
        if abs(dm) >= 2.5 and abs(dp) <= 1.0:
            market.append((i, abs(dm), READS[f"market|{'up' if dm > 0 else 'down'}"]))
        elif abs(dp) >= 2.5 and abs(dm) <= 1.0:
            projections.append((i, abs(dp), READS[f"projections|{'up' if dp > 0 else 'down'}"]))
    order = lambda t: (-t[1], t[0])
    return sorted(market, key=order), sorted(projections, key=order)


def signed(delta):
    return f"{'+' if delta > 0 else '−'}{abs(delta):.1f}" if round(abs(delta), 1) != 0 else "0.0"


def check(snap, tag) -> list[str]:
    errors = []
    want_m, want_p = expected()
    for name, got, want in (("market", snap["mkt"], want_m), ("projections", snap["proj"], want_p)):
        ids = [snap["order"].index(g["key"]) for g in got]
        if ids != [w[0] for w in want]:
            errors.append(f"{tag}{name} list {ids}, want {[w[0] for w in want]}")
            continue
        for g, w in zip(got, want):
            dm, dp = CASES[w[0]]
            if g["read"] != w[2]:
                errors.append(f"{tag}{name} player {w[0]}: read {g['read']!r}, want {w[2]!r}")
            if signed(dm) not in g["market"] or signed(dp) not in g["projections"]:
                errors.append(f"{tag}{name} player {w[0]}: shows {g['market']!r} / {g['projections']!r}, want {signed(dm)} / {signed(dp)}")
            if g["moved"] != name:
                errors.append(f"{tag}{name} player {w[0]}: in the wrong list ({g['moved']})")
    if "Week 5 → Week 6" not in snap["meta"] or "like for like" not in snap["meta"] or "compared" not in snap["meta"]:
        errors.append(f"{tag}meta line {snap['meta']!r}")
    if snap["h2"] != "Mixed signals":   # JEG-1130 name (PMM doc 3.2), was JEG-1073's
        errors.append(f"{tag}heading {snap['h2']!r}")
    return errors


def run_checks(movers_patch=None) -> list[str]:
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        raise _render_env.unavailable(f"Playwright is not available: {exc}") from exc
    js = MOVERS_JS.read_text(encoding="utf-8")
    if movers_patch:
        old, new = movers_patch
        assert old in js, f"patch anchor missing: {old!r}"
        js = js.replace(old, new, 1)
    errors: list[str] = []
    with _served() as base, sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(args=_render_env.HERMETIC_ARGS, executable_path=_chromium_executable(playwright))
        except PlaywrightError as exc:
            raise _render_env.unavailable(f"Chromium is not available: {exc}") from exc
        try:
            for width, height in ((1440, 1000), (390, 844)):
                page = browser.new_page(viewport={"width": width, "height": height})
                page_errors: list[str] = []
                page.on("pageerror", lambda e: page_errors.append(str(e)))
                page.route(lambda u: not u.startswith("http://127.0.0.1"), lambda route: route.abort())
                if movers_patch:
                    page.route("**/v2/movers.js*", lambda route, *_: route.fulfill(status=200, content_type="text/javascript", body=js))
                page.goto(base + "#player-values", wait_until="networkidle")
                page.wait_for_function("() => window.TradeValueV2 && window.TradeValueV2.view()", timeout=60000)
                page.evaluate(FEED, [list(c) for c in CASES])
                page.evaluate("() => { location.hash = '#risers-fallers'; }")
                page.wait_for_function("() => document.querySelector('#v2RMkt li, #v2RMktEmpty:not([hidden])')", timeout=60000)
                page.wait_for_timeout(500)
                snap = page.evaluate(READ)
                errors += check(snap, f"[{width}px] ")
                if width <= 390 and snap["overflow"] > 0:
                    errors.append(f"[{width}px] horizontal overflow {snap['overflow']}px")
                if width == 1440:
                    # Unfed: with the real engine data the section either lists players or says why it cannot
                    # (no prior week for a series) and lists nothing, never a partial comparison.
                    fresh = browser.new_page(viewport={"width": 1440, "height": 1000})
                    fresh.on("pageerror", lambda e: page_errors.append(str(e)))
                    fresh.route(lambda u: not u.startswith("http://127.0.0.1"), lambda route: route.abort())
                    fresh.goto(base + "#risers-fallers", wait_until="networkidle")
                    fresh.wait_for_function("() => document.getElementById('v2RDisagreeMeta').textContent.length > 5 && !/^One moved/.test(document.getElementById('v2RDisagreeMeta').textContent)", timeout=60000)
                    fresh.wait_for_timeout(500)
                    real = fresh.evaluate("""() => ({meta: document.getElementById('v2RDisagreeMeta').textContent,
                      n: document.querySelectorAll('#v2RMkt li[data-player-key], #v2RProj li[data-player-key]').length})""")
                    if real["meta"].startswith("No comparison yet") and real["n"]:
                        errors.append(f"[real data] no comparison but {real['n']} players listed: {real['meta']!r}")
                    if real["meta"].startswith("No comparison yet") and "Trade chart average" not in real["meta"] and "DDF Value" not in real["meta"]:
                        errors.append(f"[real data] the reason names no series: {real['meta']!r}")
                    fresh.close()
                if page_errors:
                    errors.append(f"[{width}px] page errors {page_errors}")
                page.close()
        finally:
            browser.close()
    return errors


PATCHES = {
    "move threshold raised": ("const MOVE = 2.5;", "const MOVE = 3.5;"),
    "reads swapped": ('"projections|up": "Market hasn\'t caught up: buy"', '"projections|up": "Market hasn\'t reacted: sell"'),
    "both moved counted": ("Math.abs(m.delta) >= MOVE && Math.abs(p.delta) <= QUIET", "Math.abs(m.delta) >= MOVE"),
}


class DisagreeRenderTest(unittest.TestCase):
    def test_lists(self):
        self.assertEqual(run_checks(), [])

    def test_guard_fails_on_broken_builds(self):
        for name, patch in PATCHES.items():
            with self.subTest(patch=name):
                self.assertNotEqual(run_checks(patch), [], f"checks did not catch: {name}")


if __name__ == "__main__":
    unittest.main()
