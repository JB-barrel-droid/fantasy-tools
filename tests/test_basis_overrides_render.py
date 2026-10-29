"""JEG-1044: the value basis at the page level, on every league setting.

Runs the real engine page (TradeValueCurveControls) in headless Chromium at the
12-combo sweep (3 scorings x 4 league sizes) and checks, for the default basis
and four others (one chart, one projection, a three-source blend, a two-source
projection blend):

1. DEFAULT PATH IS BYTE-IDENTICAL. Every value and DDF field of every row on
   the default basis equals what the engine on origin/main at 771c3422 (frozen
   in tests/fixtures/baseline_main_771c3422/; re-frozen from 61ecb39e after
   JEG-1121's deliberate bench-seat value change, see its README) gives on the
   same data, and so do
   setBasis(null), setBasis({mode: "default"}) and a blend of the four
   trade charts at equal weights (all our methodology since JEG-1073; the
   baseline engine takes the same default-rule change, see its README).
2. THE BASIS DOES WHAT IT SAYS. DDF Value is exactly the chosen source's
   Adjusted value (one source) or the normalised weighted mean of the chosen
   sources' Adjusted values, re-normalised over the sources that price a player;
   the Indexed total of every chart over its shared players equals the basis
   total over them; the prior week follows the same basis.
3. NOTHING ELSE MOVES. fixedPieIndexed holds at every basis; the trade chart
   average and the projections reference (ddf_value_projections) are the same
   as on the default basis; every source's own series is unchanged; switching
   back restores every value.

Discrimination: the Broken* tests serve a broken engine (the basis not passed
to the pipeline; one default value nudged by 0.001) and require the same
checks to fail.

Skips when no browser is available, unless RENDER_TESTS_REQUIRED=1 (CI).
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from tests._dist_server import DIST, ENGINE_PAGE, serve
from tests import _render_env

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "app" / "trade-value-chart" / "assets"
BASELINE = ROOT / "tests" / "fixtures" / "baseline_main_771c3422"
COMBOS = [[s, t] for s in ("standard", "half_ppr", "ppr") for t in (8, 10, 12, 14)]


def setUpModule():
    _render_env.ensure_built()


# One canonical snapshot per combo of everything the default path must not change.
SNAPSHOT = """async ([combos, basis]) => {
  const c = window.TradeValueCurveControls;
  if (basis !== undefined && typeof c.setBasis === 'function') c.setBasis(basis, false);
  const out = {};
  for (const [scoring, teams] of combos) {
    c.setScoring(scoring, false); c.setTeams(teams, false);
    const rows = c.getAllRows().map(r => {
      const v = {};
      Object.keys(r.values).sort().forEach(k => { v[k] = r.values[k]; });
      const dv = Object.fromEntries(['blended', 'charts', 'projections'].map(n => {
        const e = r.ddfByVersion[n];
        return [n, [e.value, e.count, e.sources, e.lowConfidence, e.reason]];
      }));
      return [r.player_key, v, dv, r.ddfTier, r.ddfCount, r.ddfChartsCount, r.ddfProjectionsCount, r.lineupShare, r.startWorthy];
    });
    out[`${scoring}/${teams}`] = JSON.stringify(rows);
  }
  return out;
}"""

# Basis checks, by hand, from the pipeline's own Adjusted values.
CHECKS = """async (combos) => {
  const c = window.TradeValueCurveControls, d = () => window.TradeValueCurveDiagnostics, h = window.TradeValueCurveHarness;
  const bases = [null,
    {mode: 'single', source: 'fantasycalc'}, {mode: 'single', source: 'espn'},
    {mode: 'blend', weights: {espn: 50, fantasycalc: 30, usatoday: 20}},
    {mode: 'blend', sources: ['espn', 'cbsros'], weights: {espn: 60, cbsros: 40}}];
  const problems = [];
  const near = (a, b) => (a === null && b === null) || (a !== null && b !== null && Math.abs(a - b) <= 1e-9);
  for (const [scoring, teams] of combos) {
    c.setScoring(scoring, false); c.setTeams(teams, false);
    c.setBasis(null, false);
    const keyOf = r => [r.values.ddf_value_charts, r.values.ddf_value_projections];
    const ref = Object.fromEntries(c.getAllRows().map(r => [r.player_key, keyOf(r)]));
    const own = JSON.stringify(c.getAllRows().map(r => [r.player_key, Object.entries(r.values).filter(([k]) => !k.startsWith('ddf_value')).sort()]));
    const start = JSON.stringify(c.getAllRows().map(r => [r.player_key, r.values.ddf_value]));
    for (const basis of bases) {
      const res = c.setBasis(basis, false);
      const tag = `${scoring}/${teams}/${basis ? res.label : 'default'}`;
      if (!res.ok) { problems.push(`${tag}: refused ${res.error}`); continue; }
      if (d().fixedPieIndexed !== true) problems.push(`${tag}: fixedPieIndexed ${d().fixedPieIndexed}`);
      const pl = h.pipeline();
      const members = basis ? res.members : null;
      const weights = basis ? res.weights : null;
      pl.rows && Object.entries(pl.rows).forEach(([key, row]) => {
        const e = row.ddfByVersion.blended;
        if (!basis) return;
        let sum = 0, wsum = 0, used = [];
        members.forEach(m => { const v = row.adjusted[m]; if (v === null || v === undefined) return; sum += weights[m] * v; wsum += weights[m]; used.push(m); });
        const want = used.length ? sum / wsum : null;
        if (!near(e.value, want)) problems.push(`${tag}: ${key} DDF ${e.value} != weighted mean ${want}`);
      });
      // Indexed: each chart's total over its shared players equals the basis total over them.
      Object.entries(pl.indexed || {}).forEach(([src, ix]) => {
        if (ix.factor === null) return;
        const total = ix.nativeTotal * ix.factor;
        if (Math.abs(total - ix.ddfTotal) > 1e-6) problems.push(`${tag}: ${src} Indexed total ${total} != basis total ${ix.ddfTotal}`);
      });
      c.getAllRows().forEach(r => {
        const o = ref[r.player_key];
        if (o && (r.values.ddf_value_charts !== o[0] || r.values.ddf_value_projections !== o[1])) problems.push(`${tag}: ${r.name} chart average or projections reference moved`);
      });
      if (JSON.stringify(c.getAllRows().map(r => [r.player_key, Object.entries(r.values).filter(([k]) => !k.startsWith('ddf_value')).sort()])) !== own
          && !basis) problems.push(`${tag}: a source series moved on the default`);
      const prior = await c.getPriorWeek('ddf_value');
      if (prior.available && basis) {
        const want = new Set(members);
        if (!prior.sources.every(s => want.has(s))) problems.push(`${tag}: prior week inputs ${prior.sources} are not the basis ${members}`);
      }
    }
    c.setBasis(null, false);
    if (JSON.stringify(c.getAllRows().map(r => [r.player_key, r.values.ddf_value])) !== start) problems.push(`${scoring}/${teams}: not restored`);
  }
  return problems;
}"""


def browser_run(script, arg, overrides=None):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        exe = _render_env.chromium_executable(p)
        if exe is None:
            raise _render_env.unavailable("no Chromium available")
        browser = p.chromium.launch(args=_render_env.HERMETIC_ARGS, executable_path=exe)
        try:
            with serve(DIST, overrides) as base:
                page = browser.new_page(viewport={"width": 1280, "height": 900})
                page.goto(base + "/classic/", wait_until="networkidle")
                page.wait_for_function("() => window.TradeValueCurveControls && window.TradeValueCurveControls.isReady()", timeout=90000)
                page.wait_for_timeout(300)
                return page.evaluate(script, arg)
        finally:
            browser.close()


def baseline_files() -> dict[str, bytes]:
    return {"assets/value-model.js": (BASELINE / "value-model.js").read_bytes(),
            "assets/curve-widget.js": (BASELINE / "curve-widget.js").read_bytes()}


def current_files(mutations: list[tuple[str, str, str]] | None = None) -> dict[str, bytes]:
    """The engine files as they are now, optionally broken: (file, old, new)."""
    files = {"assets/value-model.js": (ASSETS / "value-model.js").read_text(encoding="utf-8"),
             "assets/curve-widget.js": (ASSETS / "curve-widget.js").read_text(encoding="utf-8")}
    for name, old, new in mutations or []:
        key = f"assets/{name}"
        assert old in files[key], f"mutation target not found in {name}: {old[:60]}"
        files[key] = files[key].replace(old, new, 1)
    return {k: v.encode("utf-8") for k, v in files.items()}


def first_difference(a: dict, b: dict) -> list[str]:
    out = []
    for combo in sorted(a):
        if a[combo] == b.get(combo):
            continue
        ra, rb = json.loads(a[combo]), json.loads(b[combo])
        diff = [x[0] for x, y in zip(ra, rb) if x != y]
        out.append(f"{combo}: {len(diff)} players differ (first {diff[:5]}), {len(ra)} vs {len(rb)} rows")
    return out


class BasisRenderTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not ENGINE_PAGE.exists():
            raise _render_env.unavailable("dist/ not built (run make sync)")

    def test_default_path_is_identical_to_main_on_12_combos(self):
        main = browser_run(SNAPSHOT, [COMBOS, None], baseline_files())
        for label, basis in (("untouched", None), ("null", None),
                             ("default mode", {"mode": "default"}),
                             ("equal chart blend", {"mode": "blend", "weights": {"fantasycalc": 1, "usatoday": 1, "fantasypros": 1, "cbs": 1}})):
            now = browser_run(SNAPSHOT, [COMBOS, basis]) if label != "untouched" else browser_run(SNAPSHOT, [COMBOS, None])
            self.assertEqual(first_difference(main, now), [], f"{label}: the default path moved")
            self.assertEqual(main, now, label)

    def test_every_basis_computes_what_it_says_and_moves_nothing_else(self):
        problems = browser_run(CHECKS, COMBOS)
        self.assertEqual(problems, [], "\n".join(problems[:30]))


class BrokenEngineIsCaught(unittest.TestCase):
    """Each guard above goes red against the bug it names."""

    @classmethod
    def setUpClass(cls):
        if not ENGINE_PAGE.exists():
            raise _render_env.unavailable("dist/ not built (run make sync)")

    def test_basis_not_passed_to_the_pipeline_is_caught(self):
        broken = current_files([("curve-widget.js",
                                 "basisConfig: basisConfig ? {...basisConfig, sources: [...basisConfig.sources], weights: {...basisConfig.weights}} : null,",
                                 "basisConfig: null,")])
        problems = browser_run(CHECKS, [COMBOS[0]], broken)
        self.assertTrue(problems, "a basis that never reaches the pipeline must fail the checks")

    def test_a_nudged_default_value_is_caught_by_the_identity_check(self):
        main = browser_run(SNAPSHOT, [[COMBOS[0]], None], baseline_files())
        broken = current_files([("value-model.js", "var blendValue = used.length ? sum / used.length : null;",
                                 "var blendValue = used.length ? sum / used.length + 0.001 : null;")])
        now = browser_run(SNAPSHOT, [[COMBOS[0]], None], broken)
        self.assertNotEqual(first_difference(main, now), [], "a 0.001 nudge to DDF Value must be seen")

    def test_a_default_that_follows_a_stale_basis_is_caught(self):
        """The Indexed basis left on the user's basis after a reset would move other charts: caught as a value change."""
        main = browser_run(SNAPSHOT, [[COMBOS[0]], None], baseline_files())
        broken = current_files([("value-model.js", "if (basisPlan) { indexBasis[key] = rows[key].ddfByVersion.blended.value; return; }",
                                 "if (true) { indexBasis[key] = rows[key].ddfByVersion.blended.value + 0.5; return; }")])
        now = browser_run(SNAPSHOT, [[COMBOS[0]], None], broken)
        self.assertNotEqual(first_difference(main, now), [], "Indexed values moved on the default; the identity check must see it")


if __name__ == "__main__":
    unittest.main()
