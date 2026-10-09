"""Math inspector (internal page, dist/modules/math-inspector.html).

The inspector shows every input and intermediate of the value math for any
league setting. It must never show a number the chart does not: its tables are
read from the engine's read-only TradeValueCurveControls.getInspection(), and
this test holds them to the engine's own getAllRows() -- the rows the chart and
the main table render -- in all three views (Indexed, VORP vs waivers,
Adjusted values) at three settings:

  * 12 teams, Full PPR, standard roster (the saved setup: published charts
    show their saved values / saved views);
  * 10 teams, Half PPR (derived in the browser);
  * 14 teams, Standard, WR 2, bench 8 (derived, a different roster).

At the derived settings it also requires the inspector's intermediate columns
to rebuild the shown values: above waivers (native) x the chart's factor ==
VORP vs waivers, and above waivers x budget / group sum x the top-of-scale
factor == Adjusted values, for every player. That proves the intermediates
shown are the ones the engine used, not a parallel calculation.

Discrimination (test_guard_fails_on_broken_inspector): the same comparison
must fail on three broken inspectors that each show a plausible engine number
that is NOT the one the chart shows: the saved 12-team Indexed values at a
10-team setting, and the browser derivation instead of the saved VORP vs
waivers / Adjusted views at the saved setup.

The static tests check the builder: noindex/nofollow, no canonical, the
engine scripts kept, the inspector script added, and a refusal on a page
without the engine.
"""
from __future__ import annotations

import contextlib
import functools
import http.server
import os
import shutil
import socketserver
import sys
import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))

import build_inspector_page  # noqa: E402
from tests import _render_env  # noqa: E402


def setUpModule():
    # Build app/ and dist/ from the committed fixtures first, so the
    # test never reads a stale committed build (GAP-APP-ASSETS-LAG).
    _render_env.ensure_built()


DIST = ROOT / "dist"
PAGE = "modules/math-inspector.html"
INSPECTOR_JS = ROOT / "app" / "inspector" / "math-inspector.js"
PUBLISHED = ("usatoday", "fantasycalc", "fantasypros", "cbs")
TOL = 1e-9

SETTINGS = {
    "12 teams Full PPR (saved setup)": ("() => true", True),
    "10 teams Half PPR": ("() => { const c = window.TradeValueCurveControls; c.setScoring('half_ppr'); c.setTeams(10); }", False),
    "14 teams Standard WR2 bench 8": ("() => { const c = window.TradeValueCurveControls; c.setScoring('standard'); c.setTeams(14);"
                                      " c.setRosterSpot('WR', 2); c.setRosterSpot('BENCH', 8); }", False),
}

# Each view: the inspector table whose per-source columns are what the chart
# shows in that view, and the series those columns cover.
VIEW_TABLES = {"indexed": "indexed-players", "vorp": "vorp-players", "adj": "adjusted-players"}

READ = """async (view) => {
  const tab = document.querySelector(`#viewModeTabs [data-view-mode="${view}"]`);
  if (!tab) throw new Error('engine view tab ' + view + ' missing');
  tab.click();
  await window.MathInspector.render();
  const engine = {};
  window.TradeValueCurveControls.getAllRows().forEach(row => { engine[row.player_key] = row.values; });
  const tableId = view === 'indexed' ? 'indexed-players' : view === 'vorp' ? 'vorp-players' : 'adjusted-players';
  const rows = window.MathInspector.table(tableId);
  const snap = window.MathInspector.snapshot();
  const dom = {};
  document.querySelectorAll(`[data-table="${tableId}"] tbody tr`).forEach(tr => {
    const cells = {};
    tr.querySelectorAll('td').forEach(td => { cells[td.dataset.col] = td.textContent; });
    dom[tr.dataset.row] = cells;
  });
  return {engine, rows, dom, seriesKeys: snap.seriesKeys, setting: snap.setting,
    modes: Object.fromEntries(Object.entries(snap.published).map(([k, p]) => [k, [p.indexed.mode, p.vorp.mode, p.adj.mode]])),
    vorpScale: Object.fromEntries(Object.entries(snap.published).map(([k, p]) => [k, p.views ? p.views.vorpScale : null]))};
}"""


def _chromium_executable(playwright):
    candidates = [os.environ.get("CHROMIUM_PATH"), playwright.chromium.executable_path,
                  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", shutil.which("chromium")]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return str(candidate)
    return None


@contextlib.contextmanager
def _server(overrides):
    class Handler(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            name = self.path.split("?")[0].rsplit("/", 1)[-1]
            body = overrides.get(name)
            if body is not None:
                data = body.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/javascript")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                return
            super().do_GET()

    handler = functools.partial(Handler, directory=str(DIST))
    with socketserver.ThreadingTCPServer(("127.0.0.1", 0), handler) as server:
        server.daemon_threads = True
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            yield f"http://127.0.0.1:{server.server_address[1]}/{PAGE}"
        finally:
            server.shutdown()


def _fmt3(value):
    return "—" if value is None else f"{value:.3f}"


def mismatches(view, snapshot, derived_setting):
    """Every inspector number that differs from what the engine shows."""
    errors = []
    engine, rows = snapshot["engine"], snapshot["rows"]
    keys = snapshot["seriesKeys"] if view == "indexed" else list(PUBLISHED)
    shown = {}
    for row in rows:
        for key in keys:
            if row.get(key) is not None:
                shown[(str(row["player_key"]), key)] = row[key]
    wanted = {(pk, key): value for pk, values in engine.items() for key, value in values.items()
              if key in keys and value is not None}
    for pair in sorted(set(wanted) - set(shown)):
        errors.append(f"{view} {pair}: engine {wanted[pair]}, inspector missing")
    for pair in sorted(set(shown) - set(wanted)):
        errors.append(f"{view} {pair}: inspector {shown[pair]}, engine has no value")
    for pair in sorted(set(shown) & set(wanted)):
        if abs(shown[pair] - wanted[pair]) > TOL:
            errors.append(f"{view} {pair}: inspector {shown[pair]}, engine {wanted[pair]}")
    # What is drawn on the page is the table's data, rounded for display only.
    for row in rows[:80]:
        cells = snapshot["dom"].get(str(row["player_key"]))
        if cells is None:
            errors.append(f"{view} {row['player_key']}: in the table data but not rendered")
            continue
        for key in keys:
            if key in cells and cells[key] != _fmt3(row.get(key)):
                errors.append(f"{view} {row['player_key']} {key}: page shows {cells[key]}, data {row.get(key)}")
    if derived_setting and view in ("vorp", "adj"):
        for row in rows:
            for key in PUBLISHED:
                value = row.get(key)
                if value is None:
                    continue
                if view == "vorp":
                    rebuilt = (row.get(f"{key}__native") or 0) * (snapshot["vorpScale"][key] or 0)
                else:
                    rebuilt = row.get(f"{key}__check")
                if rebuilt is None or abs(rebuilt - value) > 1e-6:
                    errors.append(f"{view} {row['player_key']} {key}: intermediates give {rebuilt}, shown {value}")
    return errors


def collect(overrides=None, settings=SETTINGS):
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        raise _render_env.unavailable(f"Playwright is not available: {exc}") from exc
    if not (DIST / PAGE).exists():
        raise _render_env.unavailable(f"dist/{PAGE} is not built (run make sync)")
    results = {}
    with _server(dict(overrides or {})) as url, sync_playwright() as playwright:
        executable = _chromium_executable(playwright)
        if not executable:
            raise _render_env.unavailable("Chromium is not available")
        try:
            browser = playwright.chromium.launch(args=_render_env.HERMETIC_ARGS, executable_path=executable)
        except PlaywrightError as exc:
            raise _render_env.unavailable(f"Chromium is not available: {exc}") from exc
        try:
            for name, (apply, saved) in settings.items():
                page = browser.new_page(viewport={"width": 1440, "height": 1000})
                page_errors = []
                page.on("pageerror", lambda e: page_errors.append(str(e)))
                page.route(lambda u: not u.startswith("http://127.0.0.1"), lambda route: route.abort())
                page.goto(url, wait_until="networkidle", timeout=120000)
                page.wait_for_function("() => window.MathInspector && window.MathInspector.renderedSetting", timeout=30000)
                page.evaluate(apply)
                errors = [f"page error: {e}" for e in page_errors]
                for view in VIEW_TABLES:
                    snapshot = page.evaluate(READ, view)
                    if snapshot["setting"]["savedSetup"] != saved:
                        errors.append(f"{view}: savedSetup {snapshot['setting']['savedSetup']}, expected {saved}")
                    if not snapshot["rows"]:
                        errors.append(f"{view}: inspector table is empty")
                    errors.extend(mismatches(view, snapshot, derived_setting=not saved))
                results[name] = errors
                page.close()
        finally:
            browser.close()
    return results


def _summary(results):
    return {name: errors[:6] + ([f"... {len(errors) - 6} more"] if len(errors) > 6 else [])
            for name, errors in results.items() if errors}


class InspectorBuildTests(unittest.TestCase):
    CLASSIC = ('<html><head>\n  <base href="../">\n  <title>Trade Value</title>'
               '\n  <link rel="canonical" href="https://x/classic/">\n  <meta name="robots" content="noindex, follow">'
               '</head><body><div id="chart"></div>\n'
               '  <script src="assets/value-model.js?v=tv-1" defer></script>\n'
               '  <script src="assets/comparison-dashboard.js?v=tv-1" defer></script>\n</body></html>')

    def test_builder_output(self):
        html = build_inspector_page.build_inspector_html(self.CLASSIC, '<div class="mi-app"></div>')
        head = html[:html.index("</head>")]
        self.assertIn('<meta name="robots" content="noindex, nofollow">', head)
        self.assertNotIn('rel="canonical"', html)
        self.assertNotIn("noindex, follow", html)
        self.assertIn('<base href="../">', head)
        self.assertIn('<script src="modules/math-inspector.js?v=tv-1" defer></script>', html)
        self.assertIn('href="modules/math-inspector.css?v=tv-1"', head)
        # The engine runs unchanged, off-screen, after the inspector shell.
        self.assertLess(html.index('class="mi-app"'), html.index('id="inspectorEngine"'))
        self.assertLess(html.index('id="chart"'), html.index("assets/value-model.js"))
        self.assertIn('<script src="assets/value-model.js?v=tv-1"', html)

    def test_builder_refuses_a_page_without_the_engine(self):
        broken = self.CLASSIC.replace('<script src="assets/value-model.js?v=tv-1" defer></script>', "")
        with self.assertRaises(SystemExit):
            build_inspector_page.build_inspector_html(broken, "")

    def test_built_page_is_internal(self):
        built = DIST / PAGE
        if not built.exists():
            raise _render_env.unavailable("dist/modules/math-inspector.html is not built (run make sync)")
        html = built.read_text(encoding="utf-8")
        self.assertIn('<meta name="robots" content="noindex, nofollow">', html[:html.index("</head>")])
        for public in (DIST / "index.html", DIST / "v2" / "index.html", DIST / "classic" / "index.html"):
            if public.exists():
                self.assertNotIn("math-inspector", public.read_text(encoding="utf-8"), str(public))


class InspectorEngineParityTests(unittest.TestCase):
    def test_inspector_equals_engine_at_three_settings(self):
        failures = _summary(collect())
        self.assertEqual({}, failures)

    def test_guard_fails_on_broken_inspector(self):
        source = INSPECTOR_JS.read_text(encoding="utf-8")
        saved = {k: v for k, v in SETTINGS.items() if v[1]}
        derived = {k: v for k, v in SETTINGS.items() if k.startswith("10 teams")}
        # Each shows a plausible engine number that is not the one the chart shows.
        broken_variants = {
            # Indexed: the saved 12-team values at a 10-team setting (the
            # browser derivation reproduces them at the saved setup itself).
            "indexed shows saved 12-team values": (
                "row[key] = snap.series[key][k] ?? null;",
                "row[key] = (snap.published[key] ? snap.published[key].saved12 : snap.series[key])[k] ?? null;",
                derived),
            # VORP vs waivers: the browser derivation instead of the saved view shown.
            "vorp from derivation": ("        row[key] = p.vorp.values[k] ?? null;",
                                     "        row[key] = p.views?.vorp?.[k] ?? null;", saved),
            # Adjusted values tab shows another engine number (the chart's VORP
            # vs waivers). VA-3 (Jeremy 2026-10-09, "Compute live everywhere"):
            # the saved setup now derives live, so the former mutation (the
            # recomputed check column) equals the shown value everywhere and
            # is no longer a broken inspector.
            "adjusted shows VORP vs waivers": ("        row[key] = p.adj.values[k] ?? null;",
                                               "        row[key] = p.vorp.values[k] ?? null;", saved),
        }
        for name, (old, new, settings) in broken_variants.items():
            with self.subTest(variant=name):
                self.assertEqual(1, source.count(old), f"mutation target for {name!r} not found once")
                results = collect({"math-inspector.js": source.replace(old, new)}, settings=settings)
                self.assertNotEqual({}, _summary(results), f"broken inspector ({name}) passed the parity check")


if __name__ == "__main__":
    unittest.main()
