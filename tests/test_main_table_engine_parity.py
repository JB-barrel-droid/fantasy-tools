"""GAP-MAIN-TABLE-ESPN-DRIFT: the main page table shows the engine's values.

What went wrong (measured 2026-10-08 on the origin/main 3ddf90d build, 12-team
PPR, ten identical loads): the comparison table under the chart re-derived
every column with its own copy of the value math, and

  * its *_adjusted columns depended on load order. When the table finished
    loading before the chart, it priced them with the baked cells in
    adjustment-inputs.json; when the chart finished first, with the chart's
    live refit cells (window.TradeValueTwoTierLive). Darren Waller's
    FantasyCalc Adjusted was 2.0 on some loads and 4.8 on others -- the chart
    itself had 1.5 on all of them;
  * its other columns disagreed with the chart on every load (ESPN for Waller
    3.4 against the engine's 0; 100-220 cells per column), and it dropped the
    CBS ROS / Razzball VORP vs waivers columns altogether.

The table now renders the engine's rows (TradeValueCurveControls.getAllRows)
once the engine reports a finished build, and re-reads them after every
rebuild (trade-value-rows-change).

This test serves the built dist/ with server-side delays on the scripts and
fixtures, so each scenario forces a different finishing order, and requires,
for every scenario:

  * every table cell, all columns switched on, to equal the engine's value for
    that player and series (to the table's one decimal), the ESPN tier to equal
    the engine's role, and the table's players to be exactly the engine's;
  * the same after the chart is moved to 10 teams / Half PPR (the table must
    follow engine rebuilds, not just the first one).

Discrimination (test_guard_fails_on_broken_tables): the same checks must fail
on the pre-fix table (origin/main 9b97f88 comparison-dashboard.js, read from
git; skipped when that commit is not in the clone) and on a table that ignores
the engine's rebuild signal.
"""
from __future__ import annotations

import contextlib
import functools
import http.server
import socketserver
import subprocess
import threading
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
DASHBOARD_JS = ROOT / "app" / "trade-value-chart" / "assets" / "comparison-dashboard.js"
PRE_FIX_COMMIT = "9b97f88"
SOURCE_KEYS = (
    "usatoday", "fantasycalc", "fantasypros", "cbs", "cbsros", "razzball",
    "cbs_adjusted", "fantasycalc_adjusted", "usatoday_adjusted",
    "fantasypros_adjusted", "espn", "espn_vorp", "cbsros_vorp", "razzball_vorp",
)
# Seconds of server-side delay per asset name. Each scenario changes which of
# the chart engine and the table finishes loading first.
SCENARIOS = {
    "no delay": {},
    "engine script late": {"curve-widget.js": 2.0},
    "table script late": {"comparison-dashboard.js": 2.0},
    "fixtures late": {"comparison-sources-data.json": 1.0, "adjustment-inputs.json": 2.0},
}
READY = """() => window.TradeValueCurveControls && window.TradeValueCurveDiagnostics
  && document.querySelector('#tableWrap tbody tr.row-main')"""
READ = """() => {
  document.querySelectorAll('#columnToggles [data-column][aria-pressed="false"]').forEach(b => b.click());
  const heads = [...document.querySelectorAll('#tableWrap thead [data-sort]')].map(b => b.dataset.sort);
  const table = {};
  document.querySelectorAll('#tableWrap tbody tr.row-main').forEach(tr => {
    const cells = [...tr.querySelectorAll('td')];
    const rec = {};
    heads.forEach((key, i) => { rec[key] = cells[i].textContent.trim(); });
    table[tr.dataset.playerKey] = rec;
  });
  const engine = {};
  window.TradeValueCurveControls.getAllRows().forEach(row => {
    engine[row.player_key] = {values: row.values, role: row.espnRole || "waiver"};
  });
  const info = window.TradeValueCurveControls.getSourceInfo().filter(s => s.available).map(s => s.key);
  return {heads, table, engine, available: info};
}"""


def _chromium_executable(playwright):
    candidates = [Path(playwright.chromium.executable_path),
                  Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return None


@contextlib.contextmanager
def _server(delays):
    """Serve dist/ with per-asset delays applied on the server's own thread,
    so a slow asset never holds up the others."""
    class Handler(http.server.SimpleHTTPRequestHandler):
        def log_message(self, format, *args):
            pass

        def do_GET(self):
            name = self.path.split("?")[0].rsplit("/", 1)[-1]
            if name in delays["by_name"]:
                time.sleep(delays["by_name"][name])
            body = delays["overrides"].get(name)
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
            yield f"http://127.0.0.1:{server.server_address[1]}/index.html"
        finally:
            server.shutdown()


def mismatches(snapshot):
    """Every table cell that differs from the engine, as readable strings."""
    errors = []
    heads = snapshot["heads"]
    missing = [key for key in snapshot["available"] if key not in heads]
    if missing:
        errors.append(f"series the chart draws but the table does not show: {missing}")
    table, engine = snapshot["table"], snapshot["engine"]
    if set(table) != set(engine):
        errors.append(f"players: {len(set(engine) - set(table))} engine-only, "
                      f"{len(set(table) - set(engine))} table-only")
    for player_key, rec in table.items():
        row = engine.get(player_key)
        if row is None:
            continue
        if rec.get("espn_role") != row["role"]:
            errors.append(f"{player_key} ESPN tier {rec.get('espn_role')!r}, engine {row['role']!r}")
        for key in SOURCE_KEYS:
            if key not in rec:
                continue
            value = row["values"].get(key)
            want = "—" if value is None else f"{value:.1f}"
            if rec[key] != want:
                errors.append(f"{player_key} {key}: table {rec[key]}, engine {want}")
    return errors


def collect(overrides=None, scenarios=SCENARIOS):
    """{scenario: {"load": [errors], "after rebuild": [errors]}}"""
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        raise unittest.SkipTest(f"Playwright is not available: {exc}") from exc
    if not (DIST / "index.html").exists():
        raise unittest.SkipTest("dist/index.html is not built")
    delays = {"by_name": {}, "overrides": dict(overrides or {})}
    results = {}
    with _server(delays) as url, sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(executable_path=_chromium_executable(playwright))
        except PlaywrightError as exc:
            raise unittest.SkipTest(f"Chromium is not available: {exc}") from exc
        try:
            for name, by_name in scenarios.items():
                delays["by_name"] = by_name
                page = browser.new_page(viewport={"width": 1440, "height": 1000})
                page_errors = []
                page.on("pageerror", lambda e: page_errors.append(str(e)))
                page.route(lambda u: not u.startswith("http://127.0.0.1"), lambda route: route.abort())
                page.goto(url, wait_until="networkidle", timeout=120000)
                try:
                    page.wait_for_function(READY, timeout=15000)
                    load = mismatches(page.evaluate(READ))
                except PlaywrightError as exc:
                    load = [f"table never rendered values: {exc}".splitlines()[0]]
                page.evaluate("() => { const c = window.TradeValueCurveControls; c.setTeams(10); c.setScoring('half'); }")
                after = mismatches(page.evaluate(READ))
                results[name] = {"load": load + [f"page error: {e}" for e in page_errors],
                                 "after rebuild": after}
                page.close()
        finally:
            browser.close()
    return results


def _failures(results):
    return {f"{name} / {phase}": errors[:5] + ([f"... {len(errors) - 5} more"] if len(errors) > 5 else [])
            for name, phases in results.items() for phase, errors in phases.items() if errors}


class MainTableEngineParityTest(unittest.TestCase):
    def test_table_equals_engine_whatever_loads_first(self):
        failures = _failures(collect())
        self.assertEqual(failures, {}, failures)

    def test_guard_fails_on_broken_tables(self):
        current = DASHBOARD_JS.read_text(encoding="utf-8")
        listener = 'window.addEventListener("trade-value-rows-change", () => syncFromEngine());'
        self.assertIn(listener, current, "mutation anchor for the rebuild listener is stale")
        broken = {"table ignores engine rebuilds": current.replace(listener, "", 1)}
        try:
            broken["pre-fix table (origin/main 9b97f88)"] = subprocess.run(
                ["git", "show", f"{PRE_FIX_COMMIT}:app/trade-value-chart/assets/comparison-dashboard.js"],
                cwd=ROOT, capture_output=True, text=True, check=True).stdout
        except (OSError, subprocess.CalledProcessError):
            pass  # shallow clone: the in-file mutation still runs
        for name, body in broken.items():
            with self.subTest(table=name):
                self.assertNotEqual(_failures(collect({"comparison-dashboard.js": body})), {},
                                    f"parity checks did not catch: {name}")


if __name__ == "__main__":
    unittest.main()
