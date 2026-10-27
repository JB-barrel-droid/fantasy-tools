"""JEG-1156 (Jeremy, 2026-10-27, option A): on the content-week flip, before any trade chart has
posted the new week, DDF Value falls back to the latest published week and the page says so.

The page clock is pinned (window.TRADE_VALUE_TODAY), never the real one:
- the Tuesday the week after the fixture's newest chart week: DDF Value is priced (not blank) on
  the dashboard and on v2, and both name the fallback ("Week 7 values, week 8 not published yet");
- a day in the fixture's own chart week: DDF Value is priced and no fallback label shows.
Fails without the fix: every chart is "not yet published" on the flip day and DDF Value is blank.
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))
from nfl_week import content_week_start  # noqa: E402
from tests import _render_env  # noqa: E402
from tests.test_published_league_settings_render import _chromium_executable  # noqa: E402
from tests.test_v2_share_render import _built_dist  # noqa: E402
from tests.test_week_history import READY, _fixture_today  # noqa: E402

FIXTURE = ROOT / "app" / "trade-value-chart" / "assets" / "comparison-sources-data.json"
CHARTS = ("usatoday", "fantasycalc", "fantasypros", "cbs")


def setUpModule():
    _render_env.ensure_built()


def newest_chart_week() -> int:
    sources = json.loads(FIXTURE.read_text(encoding="utf-8"))["sources"]
    weeks = []
    for key in CHARTS:
        label = str((sources.get(key) or {}).get("week_designated") or "")
        digits = "".join(ch for ch in label if ch.isdigit())
        if digits:
            weeks.append(int(digits))
    return max(weeks)


PROBE = """() => {
  const f = window.TradeValueProductData.getSourceFreshness();
  const c = window.TradeValueCurveControls;
  const ddf = c.getCompositeValues('ddf_value');
  return {fallback: f.values_week_fallback, label: f.values_week_label, valuesWeek: f.values_week,
    priced: Object.keys((ddf && ddf.current) || {}).length,
    context: document.querySelector('#curveContext')?.textContent || '',
    asof: document.querySelector('[data-page-asof]')?.textContent || '',
    header: document.querySelector('#v2FreshnessLabel')?.textContent || ''};
}"""


def run_checks() -> list[str]:
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        raise _render_env.unavailable(f"Playwright is not available: {exc}") from exc
    week = newest_chart_week()
    flip_day = content_week_start(week + 1).isoformat()
    label = f"Week {week} values, week {week + 1} not published yet"
    errors = []
    with _built_dist() as base, sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(args=_render_env.HERMETIC_ARGS,
                                                 executable_path=_chromium_executable(playwright))
        except PlaywrightError as exc:
            raise _render_env.unavailable(f"Chromium is not available: {exc}") from exc
        try:
            for surface, url, width in (("dashboard", base.rsplit("v2/", 1)[0], 1440),
                                        ("v2", base + "#values", 1440), ("v2", base + "#values", 390)):
                for day, fallback in ((flip_day, True), (_fixture_today(), False)):
                    tag = f"{surface}@{width} {day}"
                    page = browser.new_page(viewport={"width": width, "height": 900})
                    page_errors = []
                    page.on("pageerror", lambda e: page_errors.append(str(e)))
                    page.add_init_script(f"window.TRADE_VALUE_TODAY = {json.dumps(day)};")
                    page.route(lambda u: not u.startswith("http://127.0.0.1"), lambda route: route.abort())
                    page.goto(url, wait_until="networkidle", timeout=120000)
                    page.wait_for_function(READY, timeout=60000)
                    if surface == "v2":
                        page.wait_for_function("() => document.querySelector('[data-page-asof]')?.textContent",
                                               timeout=30000)
                    s = page.evaluate(PROBE)
                    if s["priced"] < 50:
                        errors.append(f"{tag}: DDF Value priced only {s['priced']} players (blank values)")
                    if s["fallback"] is not fallback:
                        errors.append(f"{tag}: values_week_fallback {s['fallback']}, expected {fallback}")
                    shown = s["context"] if surface == "dashboard" else s["asof"] + " | " + s["header"]
                    if fallback and (s["label"] != label or shown.count(label) < (1 if surface == "dashboard" else 2)):
                        errors.append(f"{tag}: label {s['label']!r} not shown as {label!r}: {shown!r}")
                    if not fallback and "not published yet" in shown and "values" in shown:
                        errors.append(f"{tag}: fallback label shown on a normal week: {shown!r}")
                    if page_errors:
                        errors.append(f"{tag}: page errors {page_errors[:2]}")
                    page.close()
        finally:
            browser.close()
    return errors


class WeekFallbackRenderTest(unittest.TestCase):
    def test_flip_day_falls_back_and_labels(self):
        self.assertEqual(run_checks(), [])


if __name__ == "__main__":
    unittest.main()
