"""Regression: Razzball must render in the comparison dashboard (JEG-6).

On 2026-10-01 the Razzball leg was live in the data layer
(comparison-sources-data.json: source_validation.razzball == "live") and wired
into the curve widget, but the comparison dashboard's SOURCE_KEYS/LABELS/TIPS
registries never listed it -- so no column chip ever rendered for Razzball
while the data sat unused.

Rewritten 2026-10-08 (GAP-STALE-DASHBOARD-UNIT-TESTS): the old version ran
comparison-dashboard.js in a hand-made stub DOM that no longer reached
runRegressionGuards, and pinned a 12-source count against 14 registry keys,
so it failed on every run and tested nothing. It now loads the built page
headless and reads what a reader sees: the dashboard's own regression
diagnostics and the rendered column chips.

Discrimination: test_guard_fails_without_razzball serves the dashboard with
razzball removed from SOURCE_KEYS (the JEG-6 state) and requires the checks
to fail.
"""
import contextlib
import functools
import http.server
import json
import re
import socketserver
import threading
import unittest
from pathlib import Path

from tests import _render_env  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
APP = REPO / "app" / "trade-value-chart"
DASH_JS = APP / "assets" / "comparison-dashboard.js"
FIXTURE = REPO / "data" / "fixtures" / "current" / "comparison-sources-data.json"
RAZZBALL_KEY = '    "razzball",\n'


def setUpModule():
    # Build app/ from the committed fixtures first (GAP-APP-ASSETS-LAG).
    _render_env.ensure_built()


@contextlib.contextmanager
def _server():
    class QuietHandler(http.server.SimpleHTTPRequestHandler):
        def log_message(self, format, *args):
            pass
    handler = functools.partial(QuietHandler, directory=str(APP))
    with socketserver.ThreadingTCPServer(("127.0.0.1", 0), handler) as server:
        server.daemon_threads = True
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            yield f"http://127.0.0.1:{server.server_address[1]}/"
        finally:
            server.shutdown()


def collect(dashboard_js=None):
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        raise _render_env.unavailable(f"Playwright is not available: {exc}") from exc
    with _server() as url, sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(args=_render_env.HERMETIC_ARGS, 
                executable_path=_render_env.chromium_executable(playwright))
        except PlaywrightError as exc:
            raise _render_env.unavailable(f"Chromium is not available: {exc}") from exc
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.route(lambda u: not u.startswith("http://127.0.0.1"), lambda route: route.abort())
            if dashboard_js is not None:
                page.route("**/assets/comparison-dashboard.js*", lambda route: route.fulfill(
                    status=200, content_type="text/javascript", body=dashboard_js))
            page.goto(url, wait_until="networkidle")
            page.wait_for_function("() => window.TradeValueComparisonDiagnostics"
                                   " && document.querySelector('#columnToggles')", timeout=30000)
            out = page.evaluate("""() => {
              const box = document.querySelector('#columnToggles');
              return {
                diagnostics: window.TradeValueComparisonDiagnostics,
                chips: [...box.querySelectorAll('label, button')].map(e => e.textContent.trim()),
                titles: [...box.querySelectorAll('[title]')].map(e => e.title),
              };
            }""")
            out["errors"] = errors
            return out
        finally:
            browser.close()


def check(out):
    problems = []
    diag = out["diagnostics"] or {}
    for guard in ("allSources", "configurableColumns", "rolloverAware"):
        if diag.get(guard) is not True:
            problems.append(f"dashboard guard {guard} is {diag.get(guard)!r}")
    registry = re.search(r"const SOURCE_KEYS = \[(.*?)\];", DASH_JS.read_text(encoding="utf-8"), re.S)
    keys = re.findall(r'"([a-z_]+)"', registry.group(1)) if registry else []
    if "razzball" not in keys:
        problems.append("razzball missing from the dashboard SOURCE_KEYS registry file")
    if not any(re.fullmatch(r"Razzball Wk \d+", chip) for chip in out["chips"]):
        problems.append(f"no 'Razzball Wk N' column chip rendered: {out['chips']}")
    if not any("Razzball rest-of-season projections" in t for t in out["titles"]):
        problems.append("Razzball column tooltip (TIPS) not rendered")
    if out["errors"]:
        problems.append(f"page errors: {out['errors'][:2]}")
    return problems


class RazzballDashboardRenderTest(unittest.TestCase):
    def test_razzball_live_in_fixture(self):
        payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
        self.assertEqual(payload["source_validation"].get("razzball"), "live",
                         "fixture must carry a validated-live razzball section")
        combos = payload["sources"]["razzball"]["combos"]
        for combo in ("standard_12", "half_12", "full_12"):
            values = combos.get(combo, {}).get("values", {})
            self.assertTrue(len(values) > 100,
                            f"razzball {combo} has too few values to render")

    def test_razzball_renders_in_dashboard(self):
        self.assertEqual(check(collect()), [])

    def test_guard_fails_without_razzball(self):
        dashboard = DASH_JS.read_text(encoding="utf-8")
        self.assertEqual(dashboard.count(RAZZBALL_KEY), 1, "SOURCE_KEYS anchor is stale")
        broken = dashboard.replace(RAZZBALL_KEY, "", 1)
        problems = check(collect(broken))
        self.assertTrue(any("Razzball Wk" in p for p in problems),
                        f"render checks did not catch a dashboard without razzball: {problems}")


if __name__ == "__main__":
    unittest.main()
