"""JEG-479 follow-up: missing values on the rows (Jeremy 2026-10-08/09).

1. Every null value on a row has a reason: row.missingReasons[seriesKey] is a
   non-empty string for each null in row.values (ddf_value: the same text as
   ddfReason), in all three views and across league settings, and when the
   adjustment data fails to load ("Adjustment data failed to load").
2. Missing = 0 for a fully loaded published chart: at a position where the
   chart's waiver line is set by its own list (waiver method
   "roster_determined"), every row has a number from that chart and from its
   *_adjusted series (0 for a player it does not list). Where the chart is too
   shallow, an unlisted player's value is null with "Chart doesn't list
   players this deep at <pos>".
3. Identity-fallback adjustment cells are blank: a *_adjusted value is null
   with "Not enough players to fit an adjustment" or "Adjustment fit refused
   (order would invert)", never the unadjusted chart value.

Headless on the built dist/ (the live page).

JEG-508 (docs/methodology.md "Value Pipeline", VP-2.4 / VP-6.2 / VP-10)
changed rules 2 and 3, and only those assertions moved:
2'. A chart that prices a position gives EVERY row at that position a
    number, in every view: its listed players, the rosterable players it does
    not list (estimated, marked in row.estimated), and 0 below rosterable
    depth ("Below rosterable depth; <label> doesn't list him"). The shallow
    "Chart doesn't list players this deep" null is retired.
3'. The adjustment fits (identity-fallback cells, adjustment-inputs.json) are
    retired: the "*_adjusted" aliases carry the chart's Adjusted values, so a
    failed adjustment-inputs load changes no value and leaves no null.
"""
from __future__ import annotations

import json
import unittest

from tests._dist_server import DIST, serve
from tests import _render_env  # noqa: E402


def setUpModule():
    _render_env.ensure_built()


CHARTS = ["usatoday", "fantasycalc", "fantasypros", "cbs"]
FALLBACK_REASONS = {"Not enough players to fit an adjustment", "Adjustment fit refused (order would invert)"}

SWEEP = """async (charts) => {
  const c = window.TradeValueCurveControls;
  const view = v => document.querySelector(`#viewModeTabs [data-view-mode=${v}]`).click();
  const out = {unexplained: [], ddfMismatch: [], fullNull: [], shallowWrong: [], nulls: 0, zeros: 0,
    shallowNulls: 0, fallbackNulls: 0, estimated: 0, reasons: {}};
  const cases = [['ppr', 12], ['standard', 8], ['half_ppr', 14]];
  for (const [scoring, teams] of cases) {
    c.setScoring(scoring); c.setTeams(teams);
    for (const v of ['indexed', 'vorp', 'adj']) {
      view(v);
      const tag = `${scoring}/${teams}/${v}`;
      const info = Object.fromEntries(c.getSourceInfo().map(s => [s.key, s]));
      const rows = c.getAllRows();
      rows.forEach(r => {
        Object.entries(r.values).forEach(([key, value]) => {
          if (value !== null) return;
          out.nulls += 1;
          const reason = (r.missingReasons || {})[key];
          if (typeof reason !== 'string' || !reason.trim()) {
            if (out.unexplained.length < 20) out.unexplained.push(`${tag} ${r.name} ${key}`);
            return;
          }
          out.reasons[reason.replace(/ at (QB|RB|WR|TE)$/, ' at <pos>').replace(/for .* teams$/, 'for <setting>')] = true;
          if (reason.startsWith("Chart doesn't list")) out.shallowNulls += 1;
          if (reason.startsWith('Below rosterable depth')) out.shallowWrong.push(`${tag} ${r.name} ${key}: null with ${reason}`);
          if (key.endsWith('_adjusted') && (reason.startsWith('Not enough players') || reason.startsWith('Adjustment fit refused'))) out.fallbackNulls += 1;
        });
        if (r.values.ddf_value === null && r.missingReasons?.ddf_value !== r.ddfReason) {
          out.ddfMismatch.push(`${tag} ${r.name}`);
        }
        for (const chart of charts) {
          const waiver = info[chart]?.waiver;
          if (!waiver || !info[chart].available) continue;
          const method = waiver.positions?.[r.pos]?.method;
          for (const key of [chart, `${chart}_adjusted`]) {
            const value = r.values[key];
            const reason = r.missingReasons?.[key] || '';
            if (!info[key]?.available) continue;
            if (method && method !== 'no_players') {
              if (value === 0) out.zeros += 1;
              if (r.estimated?.[chart]) out.estimated += 1;
              if (value === null && out.fullNull.length < 20) out.fullNull.push(`${tag} ${r.name} ${r.pos} ${key}: ${reason}`);
            }
          }
        }
      });
    }
  }
  view('indexed');
  c.setScoring('ppr'); c.setTeams(12);
  out.reasons = Object.keys(out.reasons).sort();
  return out;
}"""

FALLBACK = """async () => {
  const c = window.TradeValueCurveControls;
  const out = {blanked: [], problems: []};
  c.getAllRows().forEach(r => {
    Object.entries(r.missingReasons || {}).forEach(([key, reason]) => {
      if (!key.endsWith('_adjusted')) return;
      if (reason.startsWith('Not enough players') || reason.startsWith('Adjustment fit refused')) {
        out.blanked.push([r.name, r.pos, key, reason]);
        if (r.values[key] !== null) out.problems.push(`${r.name} ${key} has a value with reason ${reason}`);
      }
    });
  });
  return out;
}"""

FAILED_LOAD = """() => {
  const c = window.TradeValueCurveControls;
  const out = {unexplained: [], adjusted: {}};
  c.getAllRows().forEach(r => {
    Object.entries(r.values).forEach(([key, value]) => {
      if (value !== null) return;
      const reason = r.missingReasons?.[key];
      if (!reason) out.unexplained.push(`${r.name} ${key}`);
      if (key.endsWith('_adjusted')) out.adjusted[reason] = (out.adjusted[reason] || 0) + 1;
    });
  });
  return out;
}"""


def run(script, arg=None, route_adjustments_fail=False):
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise _render_env.unavailable(f"Playwright is not available: {exc}") from exc
    with sync_playwright() as p:
        exe = _render_env.chromium_executable(p)
        if exe is None:
            raise _render_env.unavailable("no Chromium available")
        browser = p.chromium.launch(args=_render_env.HERMETIC_ARGS, executable_path=exe)
        try:
            with serve(DIST) as base:
                page = browser.new_page(viewport={"width": 1280, "height": 900})
                if route_adjustments_fail:
                    # The JEG-484 hook (tests/test_asset_load_retry.py): every
                    # adjustment-inputs request fails.
                    page.route("**/assets/adjustment-inputs.json*", lambda route: route.fulfill(status=503, body="down"))
                errors = []
                page.on("pageerror", lambda exc: errors.append(str(exc)))
                page.goto(base + "/", wait_until="domcontentloaded")
                page.wait_for_function(
                    "() => window.TradeValueCurveControls && window.TradeValueCurveControls.isReady()", timeout=90000)
                page.wait_for_timeout(300)
                out = page.evaluate(script, arg)
                out["pageErrors"] = errors
                return out
        finally:
            browser.close()


class RowMissingReasonsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not (DIST / "index.html").exists():
            raise _render_env.unavailable("dist/ not built (run make sync)")

    def test_every_null_has_a_reason_and_full_charts_price_zero(self):
        out = run(SWEEP, CHARTS)
        self.assertEqual(out["pageErrors"], [])
        self.assertGreater(out["nulls"], 100, "no nulls, so the reason rule went untested")
        self.assertEqual(out["unexplained"], [], "\n".join(out["unexplained"]))
        self.assertEqual(out["ddfMismatch"], [])
        self.assertEqual(out["fullNull"], [], "a chart that prices the position left a player missing:\n" + "\n".join(out["fullNull"]))
        self.assertEqual(out["shallowWrong"], [], "\n".join(out["shallowWrong"]))
        self.assertGreater(out["zeros"], 100, "no player below rosterable depth, so 0 went untested")
        self.assertGreater(out["estimated"], 0, "no estimated player, so the fill-in went untested")
        # VP-6.2: the shallow null and the fit fallbacks are retired.
        self.assertEqual((out["shallowNulls"], out["fallbackNulls"]), (0, 0))

    def test_failed_adjustment_load_changes_nothing(self):
        # JEG-508: the engine no longer reads adjustment-inputs.json, so a
        # failed load leaves every null explained and no "*_adjusted" null.
        out = run(FAILED_LOAD, route_adjustments_fail=True)
        self.assertEqual(out["unexplained"], [], "\n".join(out["unexplained"][:20]))
        self.assertNotIn("Adjustment data failed to load", out["adjusted"])

if __name__ == "__main__":
    unittest.main()
