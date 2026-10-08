"""v2 Trade targets, rendered: the tab's numbers are the engine's numbers.

Builds dist/v2 into a temp copy of the built dist/, loads /v2/#trade-targets
headless (desktop 1440 and mobile 390), and for every rendered row checks,
against window.TradeValueCurveControls.getRows() for the same player:

  * "Our value" shows the engine's value for the series picked in "Our value"
    (ESPN by default, then CBS rest-of-season and Razzball through the picker);
  * each chart cell shows the engine's value for that chart, and its gap is
    exactly chart − ours with the right sign; a value the engine does not have
    shows — plus a reason, never 0.0;
  * a chart value at or below its waiver line (0) shows "waiver line" and no
    gap, and no buy target comes from one (Jeremy, 2026-10-07);
  * sell rows are ordered largest positive gap first, buy rows most negative first;
  * the picked series survives a round trip to Player values; the Methods row
    stays hidden on this tab;
  * no page errors and no horizontal overflow at 390 px.

Discrimination: test_guard_fails_on_broken_builds serves targets.js with the
gap sign flipped, missing values read as 0, the waiver rule removed and the
picked series ignored, and requires the checks to fail on each.
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


TARGETS_JS = ROOT / "app" / "v2" / "targets.js"
OURS = ("espn", "cbsros", "razzball")

READ = """([side, ours]) => {
  const rows = window.TradeValueCurveControls.getRows();
  const engine = Object.fromEntries(rows.map(r => [String(r.player_key), r.values]));
  const text = node => (node ? node.childNodes[0]?.textContent || "" : null);
  const table = [...document.querySelectorAll('#v2TTable tbody tr')].map(tr => ({
    key: tr.dataset.playerKey,
    ours: tr.querySelector('[data-ours]').textContent,
    best: text(tr.querySelector('td.best')),
    bestChart: tr.querySelector('td.best').dataset.best,
    cells: Object.fromEntries([...tr.querySelectorAll('td[data-chart]')].map(td => [td.dataset.chart, {
      value: text(td), gap: td.querySelector('.gap')?.textContent ?? null,
      atWaiver: Boolean(td.querySelector('.at-waiver')),
      missing: Boolean(td.querySelector('.missing')), why: td.querySelector('.missing .why')?.textContent ?? null}]))
  }));
  const cards = [...document.querySelectorAll('#v2TCards li')].map(li => ({
    key: li.dataset.playerKey,
    ours: li.querySelector('.ours').textContent,
    cells: Object.fromEntries([...li.querySelectorAll('[data-chart]')].map(span => [span.dataset.chart, {
      value: span.childNodes[1]?.textContent ?? null, gap: span.querySelector('.gap')?.textContent ?? null,
      atWaiver: Boolean(span.querySelector('.at-waiver')),
      missing: Boolean(span.querySelector('.missing'))}]))
  }));
  return {side, ours, engine, table, cards, used: window.TradeValueV2.targets().used,
    picker: document.getElementById('v2TOurs').value,
    // Every target on this side, not only the rendered page.
    allBest: window.TradeValueV2.targets()[side].map(p => [String(p.row.player_key), (side === 'sell' ? p.bestSell : p.bestBuy).chart]),
    methodsHidden: document.getElementById('v2Methods').hidden,
    overflow: document.documentElement.scrollWidth - window.innerWidth};
}"""


def fmt(value):
    return f"{value:.1f}"


def fmt_gap(gap):
    text = f"{abs(gap):.1f}"
    if text == "0.0":
        return "0.0"
    return ("+" if gap > 0 else "−") + text


def finite(value):
    return isinstance(value, (int, float)) and value == value and abs(value) != float("inf")


def check(snapshot) -> list[str]:
    errors = []
    side = snapshot["side"]
    our_key = snapshot["ours"]
    engine = snapshot["engine"]
    if snapshot["picker"] != our_key:
        errors.append(f"picker shows {snapshot['picker']!r}, expected {our_key!r}")
    if not snapshot["methodsHidden"]:
        errors.append("the Methods row must stay hidden on Trade targets")
    if not snapshot["used"]:
        errors.append("no published chart compared")
    if not snapshot["table"]:
        errors.append(f"no {side} rows rendered")
    for key, chart in snapshot["allBest"]:
        value = (engine.get(key) or {}).get(chart)
        if not finite(value) or value <= 0:
            errors.append(f"{key}: {side} target from {chart} at {value!r}, at or below that chart's waiver line")
    best_gaps = []
    for row in snapshot["table"]:
        values = engine.get(row["key"])
        if values is None:
            errors.append(f"row {row['key']} is not an engine row")
            continue
        ours = values.get(our_key)
        if not finite(ours) or row["ours"] != fmt(ours):
            errors.append(f"{row['key']}: ours {row['ours']!r} != engine {our_key} {ours!r}")
            continue
        gaps = {}
        for chart, cell in row["cells"].items():
            value = values.get(chart)
            if not finite(value):
                if not cell["missing"] or not cell["why"] or "0.0" in (cell["value"] or ""):
                    errors.append(f"{row['key']}/{chart}: engine has no value but cell shows {cell}")
                continue
            if cell["missing"] or cell["value"] != fmt(value):
                errors.append(f"{row['key']}/{chart}: shows {cell['value']!r}, engine {value!r}")
            if value <= 0:
                # At this chart's waiver line: never a target, no gap.
                if cell["gap"] is not None or not cell["atWaiver"]:
                    errors.append(f"{row['key']}/{chart}: chart value {value} is at the waiver line but shows {cell}")
                continue
            gap = value - ours
            gaps[chart] = gap
            if cell["gap"] != fmt_gap(gap):
                errors.append(f"{row['key']}/{chart}: gap {cell['gap']!r}, expected {fmt_gap(gap)!r} (chart − ours)")
        if not gaps:
            errors.append(f"{row['key']}: listed as {side} target with no chart above its waiver line")
            continue
        pick = max(gaps, key=gaps.get) if side == "sell" else min(gaps, key=gaps.get)
        if (side == "sell" and gaps[pick] <= 0) or (side == "buy" and gaps[pick] >= 0):
            errors.append(f"{row['key']}: listed as {side} target with gaps {gaps}")
            continue
        if row["bestChart"] != pick or row["best"] != fmt_gap(gaps[pick]):
            errors.append(f"{row['key']}: largest gap {row['best']!r} {row['bestChart']} != {fmt_gap(gaps[pick])} {pick}")
        best_gaps.append(gaps[pick])
    ordered = sorted(best_gaps, reverse=(side == "sell"))
    if best_gaps != ordered:
        errors.append(f"{side} rows are not ordered by largest gap")
    for card in snapshot["cards"]:
        values = engine.get(card["key"], {})
        if not finite(values.get(our_key)) or card["ours"] != f"Ours {fmt(values[our_key])}":
            errors.append(f"card {card['key']}: {card['ours']!r} vs engine {our_key} {values.get(our_key)!r}")
            continue
        for chart, cell in card["cells"].items():
            value = values.get(chart)
            if not finite(value):
                if not cell["missing"]:
                    errors.append(f"card {card['key']}/{chart}: engine has no value but card shows {cell}")
            elif value <= 0:
                if cell["value"] != fmt(value) or cell["gap"] is not None or not cell["atWaiver"]:
                    errors.append(f"card {card['key']}/{chart}: chart value {value} is at the waiver line but shows {cell}")
            elif cell["value"] != fmt(value) or cell["gap"] != fmt_gap(value - values[our_key]):
                errors.append(f"card {card['key']}/{chart}: {cell} vs engine {value}")
    return errors


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
                yield f"http://127.0.0.1:{server.server_address[1]}/v2/#trade-targets"
            finally:
                server.shutdown()


def collect(targets_body=None, viewports=((1440, 1000), (390, 844))):
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        raise _render_env.unavailable(f"Playwright is not available: {exc}") from exc
    snapshots = []
    with _built_dist() as url, sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(args=_render_env.HERMETIC_ARGS, executable_path=_chromium_executable(playwright))
        except PlaywrightError as exc:
            raise _render_env.unavailable(f"Chromium is not available: {exc}") from exc
        try:
            for width, height in viewports:
                page = browser.new_page(viewport={"width": width, "height": height})
                errors = []
                page.on("pageerror", lambda e: errors.append(str(e)))
                # Only the local build is under test; the web font is not.
                page.route(lambda u: not u.startswith("http://127.0.0.1"), lambda route: route.abort())
                if targets_body is not None:
                    page.route("**/v2/targets.js*", lambda route: route.fulfill(
                        status=200, content_type="text/javascript", body=targets_body))
                page.goto(url, wait_until="networkidle")
                page.wait_for_function("() => window.TradeValueV2 && window.TradeValueV2.targets()", timeout=30000)
                for ours in OURS:
                    if ours != "espn":
                        page.select_option("#v2TOurs", ours)
                        # The pick must survive a trip to Player values and back.
                        page.evaluate("() => { location.hash = '#player-values'; }")
                        page.wait_for_function("() => !document.getElementById('v2Main').hidden")
                        page.evaluate("() => { location.hash = '#trade-targets'; }")
                        page.wait_for_function("() => !document.getElementById('v2Targets').hidden")
                    for side in ("sell", "buy"):
                        page.click(f"#v2Targets [data-side={side}]")
                        snap = page.evaluate(READ, [side, ours])
                        snap["width"] = width
                        snap["pageErrors"] = list(errors)
                        snapshots.append(snap)
                page.close()
        finally:
            browser.close()
    return snapshots


def check_all(snapshots) -> list[str]:
    errors = []
    for snap in snapshots:
        prefix = f"[{snap['width']}px {snap['ours']} {snap['side']}] "
        errors += [prefix + e for e in check(snap)]
        if snap["pageErrors"]:
            errors.append(prefix + f"page errors: {snap['pageErrors']}")
        if snap["width"] <= 390 and snap["overflow"] > 0:
            errors.append(prefix + f"horizontal overflow {snap['overflow']}px")
    return errors


class TradeTargetsRenderTest(unittest.TestCase):
    def test_rendered_numbers_match_engine(self):
        snapshots = collect()
        self.assertEqual(check_all(snapshots), [])
        self.assertTrue(any(s["table"] for s in snapshots if s["width"] == 1440))
        self.assertTrue(any(s["cards"] for s in snapshots if s["width"] == 390))

    def test_guard_fails_on_broken_builds(self):
        source = TARGETS_JS.read_text(encoding="utf-8")
        broken = {
            "sign flipped": source.replace("const gap = value - ours;", "const gap = ours - value;", 1),
            "missing read as zero": source.replace("const value = row.values[chart];",
                                                   "const value = row.values[chart] ?? 0;", 1),
            "waiver rule removed": source.replace("if (value <= 0) {", "if (false) {", 1),
            "picked series ignored": source.replace("const ourKey = (opts && opts.ours) || OUR_KEY;",
                                                    "const ourKey = OUR_KEY;", 1),
        }
        for name, body in broken.items():
            with self.subTest(mutation=name):
                self.assertNotEqual(body, source, f"mutation anchor for {name!r} is stale")
                self.assertNotEqual(check_all(collect(body, viewports=((1440, 1000),))), [],
                                    f"render checks did not catch: {name}")


if __name__ == "__main__":
    unittest.main()
