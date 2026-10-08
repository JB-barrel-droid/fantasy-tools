"""Rendered regression: the "Largest disagreement" spread never mixes units.

docs/v2-design-notes.md frame 22: "never compute a spread or aggregate across
unlike units". VORP vs waivers series (espn_vorp, cbsros_vorp, razzball_vorp,
and the published charts while the VORP vs waivers view is on) are not on the
trade-value point scale the Indexed and Data Driven Adjusted series share.
Until 2026-10-07 both disagreement spreads -- the chart's lock order
(curve-widget.js disagreement()) and the table's Disagreement column
(comparison-dashboard.js rows()) -- took highest minus lowest across every
series, VORP vs waivers included.

Discrimination: each test first checks the live data actually separates the
two definitions (the all-series spread orders/values players differently from
the point-scale spread), so a pass cannot come from data where the bug is
invisible. Negative-tested 2026-10-07 against the pre-fix curve-widget.js and
comparison-dashboard.js: all three tests fail there.
"""

import contextlib
import functools
import http.server
import json
import shutil
import socketserver
import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app" / "trade-value-chart"
PURE_VORP_KEYS = ("espn_vorp", "cbsros_vorp", "razzball_vorp")
PUBLISHED_KEYS = ("usatoday", "fantasycalc", "fantasypros", "cbs")
# comparison-dashboard.js SOURCE_KEYS, in its order.
DASHBOARD_SOURCE_KEYS = (
    "usatoday", "fantasycalc", "fantasypros", "cbs", "cbsros", "razzball",
    "cbs_adjusted", "fantasycalc_adjusted", "usatoday_adjusted",
    "fantasypros_adjusted", "espn", "espn_vorp", "cbsros_vorp", "razzball_vorp",
)


def _chromium_executable(playwright):
    candidates = [
        Path(playwright.chromium.executable_path),
        Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
    ]
    chromium = shutil.which("chromium")
    if chromium:
        candidates.append(Path(chromium))
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return None


@contextlib.contextmanager
def _chart_page():
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        raise unittest.SkipTest(f"Playwright is not available: {exc}") from exc

    class QuietHandler(http.server.SimpleHTTPRequestHandler):
        def log_message(self, format, *args):
            pass

    handler = functools.partial(QuietHandler, directory=str(APP))
    with socketserver.ThreadingTCPServer(("127.0.0.1", 0), handler) as server:
        server.daemon_threads = True
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            with sync_playwright() as playwright:
                try:
                    browser = playwright.chromium.launch(executable_path=_chromium_executable(playwright))
                except PlaywrightError as exc:
                    raise unittest.SkipTest(f"Chromium is not available: {exc}") from exc
                try:
                    page = browser.new_page()
                    page.goto(f"http://127.0.0.1:{server.server_address[1]}/", wait_until="networkidle")
                    page.wait_for_function(
                        """() => window.TradeValueCurveControls && window.TradeValueCurveDiagnostics
                          && document.querySelector("#tableWrap table")""",
                        timeout=20000,
                    )
                    yield page
                finally:
                    browser.close()
        finally:
            server.shutdown()


def spread(values, keys):
    priced = [values[key] for key in keys if isinstance(values.get(key), (int, float))]
    return max(priced) - min(priced) if len(priced) >= 2 else None


def is_sorted_by(rows, keys):
    """Descending by spread over `keys`, missing spreads last."""
    spreads = [spread(row["values"], keys) for row in rows]
    priced = [s for s in spreads if s is not None]
    if spreads[:len(priced)] != priced:
        return False
    return all(a >= b - 1e-9 for a, b in zip(priced, priced[1:]))


READ_ROWS = """() => {
  const c = window.TradeValueCurveControls;
  c.setLockOrder("disagreement");
  return c.getRows().map(row => ({player_key: row.player_key, values: row.values}));
}"""


class ChartDisagreementUnitsTest(unittest.TestCase):
    def _check(self, rows, excluded):
        all_keys = sorted({key for row in rows for key in row["values"]})
        self.assertTrue(set(PURE_VORP_KEYS) <= set(all_keys), "fixture must carry the VORP vs waivers series")
        point_keys = [key for key in all_keys if key not in excluded]
        # Independent of the page's own order: the correct order must not
        # also satisfy the all-series spread, or this data hides the bug.
        correct = sorted(rows, key=lambda row: (spread(row["values"], point_keys) is None,
                                                -(spread(row["values"], point_keys) or 0)))
        self.assertFalse(
            is_sorted_by(correct, all_keys),
            "data must separate the two spreads, or this test cannot see the bug",
        )
        self.assertTrue(
            is_sorted_by(rows, point_keys),
            f"Largest disagreement must sort by the spread over {point_keys} only",
        )

    def test_indexed_view_sort_excludes_vorp_vs_waivers_series(self):
        with _chart_page() as page:
            self._check(page.evaluate(READ_ROWS), set(PURE_VORP_KEYS))

    def test_vorp_view_sort_excludes_published_vorp_values(self):
        with _chart_page() as page:
            page.locator('#viewModeTabs [data-view-mode="vorp"]').click()
            page.wait_for_selector('#viewModeVorpTab[aria-selected="true"]', timeout=5000)
            # In this view the published charts carry VORP vs waivers values.
            self._check(page.evaluate(READ_ROWS), set(PURE_VORP_KEYS) | set(PUBLISHED_KEYS))


class TableDisagreementUnitsTest(unittest.TestCase):
    def test_disagreement_column_excludes_vorp_vs_waivers_columns(self):
        with _chart_page() as page:
            columns = ["disagreement", *DASHBOARD_SOURCE_KEYS]
            state = {"version": 8, "settings": {"scoring": "full", "teams": 12},
                     "sort": {"column": "disagreement", "direction": "desc"},
                     "filters": {"position": "ALL", "search": ""}, "columns": columns}
            table = page.evaluate(
                """state => {
                  document.querySelector("#importText").value = JSON.stringify(state);
                  document.querySelector("#applyImport").click();
                  const status = document.querySelector("#stateStatus").textContent;
                  const head = [...document.querySelectorAll("#tableWrap thead [data-sort]")].map(b => b.dataset.sort);
                  const body = [...document.querySelectorAll("#tableWrap tbody tr.row-main")]
                    .map(tr => [...tr.children].slice(1).map(td => td.textContent.trim()));
                  return {status, head, body};
                }""",
                state,
            )
            self.assertEqual(table["status"], "Imported comparison settings.")
            # A source unavailable at this setting renders no column and
            # carries no value into the spread either.
            rendered = table["head"][1:]
            self.assertEqual(rendered[0], "disagreement")
            self.assertTrue(set(PURE_VORP_KEYS) & set(rendered), rendered)
            self.assertGreater(len(table["body"]), 50)
            separated = 0
            for cells in table["body"]:
                values = {key: float(text) for key, text in zip(rendered, cells) if text not in ("—", "")}
                shown = values.pop("disagreement", None)
                point = spread(values, [k for k in DASHBOARD_SOURCE_KEYS if k not in PURE_VORP_KEYS])
                every = spread(values, DASHBOARD_SOURCE_KEYS)
                if point is None:
                    self.assertIsNone(shown)
                    continue
                # Cells are rounded to 0.1, so the recomputed spread carries
                # up to 0.1 of rounding error.
                self.assertAlmostEqual(shown, point, delta=0.11)
                if every - point > 0.5:
                    separated += 1
            self.assertGreater(separated, 0, "data must separate the two spreads, or this test cannot see the bug")


if __name__ == "__main__":
    unittest.main()
