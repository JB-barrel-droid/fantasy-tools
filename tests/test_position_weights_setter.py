"""JEG-452 (BE-2): TradeValueCurveControls.setPositionWeights and
getPositionWeightBounds.

A position share scales that position's calibration pie (activePies); the
live DDF calibration, the ESPN anchor fitted to it and the *_adjusted series
follow. Defaults are the shares derived from the calibration pies.

Checks, on the build-only engine page (the old chart dashboard, served at /classic/ by the test server; JEG-453):
1. Defaults unchanged. Across the 12 league combos (3 scorings x 8/10/12/14
   teams) and all three views, every getAllRows value is the same at load,
   after setting the derived defaults back, and after a custom share followed
   by a reset (null). The pre-change widget gave the same 148,716 values as
   this one with no setter call (before/after sweep in the PR).
2. Direction. Raising one position's share raises that position's share of
   the ESPN anchor's total and lowers every other position's; its top value
   does not fall and no other position's top value rises (the 70/max display
   scale can leave the top unchanged). fixedPieIndexed holds.
3. Bounds and clamping. Out-of-bounds shares clamp into
   getPositionWeightBounds(), the four shares total 1, invalid input is
   refused with no state change, and every position stays priced at the
   bounds (no withheld position).
4. 12-combo sweep with a share edit: fixedPieIndexed holds and every
   position's ESPN curve has a start in each combo; a league change resets
   the shares to that combo's defaults.
"""
from __future__ import annotations

import json
import unittest

from tests._dist_server import DIST, ENGINE_PAGE, serve
from tests import _render_env  # noqa: E402


def setUpModule():
    _render_env.ensure_built()


COMBOS = [[s, t] for s in ("standard", "half_ppr", "ppr") for t in (8, 10, 12, 14)]

HELPERS = """
  const c = window.TradeValueCurveControls;
  const P = ['QB', 'RB', 'WR', 'TE'];
  const view = v => document.querySelector(`#viewModeTabs [data-view-mode=${v}]`).click();
  const allValues = () => {
    const out = {};
    c.getAllRows().forEach(r => Object.entries(r.values).forEach(([k, v]) => {
      if (typeof v === 'number') out[`${r.player_key}|${k}`] = v;
    }));
    return out;
  };
  const espnByPos = () => {
    const total = {}, top = {};
    c.getAllRows().forEach(r => {
      const v = r.values.espn;
      if (typeof v !== 'number' || !P.includes(r.pos)) return;
      total[r.pos] = (total[r.pos] || 0) + v;
      top[r.pos] = Math.max(top[r.pos] || 0, v);
    });
    const sum = P.reduce((s, p) => s + (total[p] || 0), 0);
    return {share: Object.fromEntries(P.map(p => [p, (total[p] || 0) / sum])), top};
  };
  const fixedPie = () => window.TradeValueCurveDiagnostics.fixedPieIndexed === true;
"""

DEFAULTS = """async (combos) => {""" + HELPERS + """
  const problems = [];
  let compared = 0;
  for (const [scoring, teams] of combos) {
    c.setScoring(scoring); c.setTeams(teams);
    for (const v of ['indexed', 'vorp', 'adj']) {
      view(v);
      const tag = `${scoring}/${teams}/${v}`;
      const base = allValues();
      const n = Object.keys(base).length;
      compared += n;
      const r1 = c.setPositionWeights(c.getDefaultPositionWeights());
      if (!r1.ok || !r1.isDefault) problems.push(`${tag}: setting the defaults did not report isDefault`);
      const same1 = JSON.stringify(allValues()) === JSON.stringify(base);
      if (!same1) problems.push(`${tag}: values moved after setting the derived defaults back`);
      const qb = c.getPositionWeights().QB;
      c.setPositionWeights({QB: qb + 0.05});
      const moved = JSON.stringify(allValues()) !== JSON.stringify(base);
      if (v === 'indexed' && !moved) problems.push(`${tag}: a custom QB share moved no value`);
      c.setPositionWeights(null);
      if (JSON.stringify(allValues()) !== JSON.stringify(base)) problems.push(`${tag}: reset did not restore every value`);
      if (!fixedPie()) problems.push(`${tag}: fixedPieIndexed false at defaults`);
    }
  }
  view('indexed');
  return {compared, problems};
}"""

DIRECTION = """async (combos) => {""" + HELPERS + """
  const problems = [];
  for (const [scoring, teams] of combos) {
    c.setScoring(scoring); c.setTeams(teams);
    view('indexed');
    const base = espnByPos();
    const defaults = c.getDefaultPositionWeights();
    for (const pos of P) {
      const tag = `${scoring}/${teams} ${pos}+5pp`;
      const r = c.setPositionWeights({[pos]: defaults[pos] + 0.05});
      if (!r.ok || r.clamped) { problems.push(`${tag}: ${JSON.stringify(r)}`); continue; }
      const w = c.getPositionWeights();
      P.filter(p => p !== pos).forEach(p => {
        // Unnamed shares give up the difference in proportion to their size.
        const expected = defaults[p] * (1 - w[pos]) / (1 - defaults[pos]);
        if (Math.abs(w[p] - expected) > 1e-9) problems.push(`${tag}: ${p} share ${w[p]} not proportional (${expected})`);
      });
      const now = espnByPos();
      if (!(now.share[pos] > base.share[pos] + 1e-6)) problems.push(`${tag}: ${pos} share of the anchor ${base.share[pos]} -> ${now.share[pos]}`);
      if (now.top[pos] < base.top[pos] - 1e-6) problems.push(`${tag}: ${pos} top fell ${base.top[pos]} -> ${now.top[pos]}`);
      P.filter(p => p !== pos).forEach(p => {
        if (!(now.share[p] < base.share[p] - 1e-6)) problems.push(`${tag}: ${p} share did not fall ${base.share[p]} -> ${now.share[p]}`);
        if (now.top[p] > base.top[p] + 1e-6) problems.push(`${tag}: ${p} top rose ${base.top[p]} -> ${now.top[p]}`);
      });
      if (!fixedPie()) problems.push(`${tag}: fixedPieIndexed false`);
      c.setPositionWeights(null);
    }
  }
  return {problems};
}"""

CLAMP = """async () => {""" + HELPERS + """
  c.setScoring('ppr'); c.setTeams(12); view('indexed');
  const out = {bounds: c.getPositionWeightBounds(), defaults: c.getDefaultPositionWeights()};
  const priced = () => P.every(p => (espnByPos().top[p] || 0) > 0);
  out.high = c.setPositionWeights({QB: 5}); out.highPriced = priced(); out.highFixedPie = fixedPie();
  out.low = c.setPositionWeights({TE: -1}); out.lowPriced = priced(); out.lowFixedPie = fixedPie();
  out.four = c.setPositionWeights({QB: 0.5, RB: 0.5, WR: 0.5, TE: 0.5});
  out.fourFloor = c.setPositionWeights({QB: 2, RB: 2, WR: 0, TE: 0}); out.fourFloorPriced = priced();
  out.string = c.setPositionWeights({WR: '0.4'});
  const before = c.getPositionWeights();
  out.invalid = [
    c.setPositionWeights({XX: 0.2}), c.setPositionWeights({QB: NaN}), c.setPositionWeights({QB: 'abc'}),
    c.setPositionWeights({}), c.setPositionWeights([0.25]), c.setPositionWeights(42), c.setPositionWeights({QB: null}),
  ];
  out.unchangedAfterInvalid = JSON.stringify(c.getPositionWeights()) === JSON.stringify(before);
  out.reset = c.resetPositionWeights();
  c.setPositionWeights({RB: 0.3});
  c.setTeams(10);
  out.afterLeagueChange = c.getPositionWeights();
  out.defaults10 = c.getDefaultPositionWeights();
  c.setTeams(12);
  return out;
}"""

SWEEP = """async (combos) => {""" + HELPERS + """
  const rows = [];
  for (const [scoring, teams] of combos) {
    c.setScoring(scoring); c.setTeams(teams); view('indexed');
    const d = c.getDefaultPositionWeights();
    c.setPositionWeights({QB: d.QB + 0.05, TE: d.TE + 0.02});
    const e = espnByPos();
    rows.push({combo: `${scoring}/${teams}`, fixedPie: fixedPie(), starts: e.top});
    c.setPositionWeights(null);
  }
  return rows;
}"""


def run(script: str, arg=None):
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
                page.goto(base + "/classic/", wait_until="networkidle")
                page.wait_for_function("() => window.TradeValueCurveDiagnostics", timeout=60000)
                page.wait_for_timeout(300)
                return page.evaluate(script, arg)
        finally:
            browser.close()


class PositionWeightsSetterTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not ENGINE_PAGE.exists():
            raise _render_env.unavailable("dist/ not built (run make sync)")

    def test_defaults_unchanged_and_reset_restores(self):
        result = run(DEFAULTS, COMBOS)
        self.assertGreater(result["compared"], 100000, result["compared"])
        self.assertEqual(result["problems"], [], "\n".join(result["problems"][:40]))

    def test_raising_a_share_moves_value_to_that_position(self):
        result = run(DIRECTION, [["ppr", 12], ["standard", 8], ["half_ppr", 10], ["ppr", 14]])
        self.assertEqual(result["problems"], [], "\n".join(result["problems"][:40]))

    def test_bounds_clamp_and_invalid_input(self):
        out = run(CLAMP)
        lo, hi = 0.01, 0.97
        self.assertEqual(out["bounds"], {p: [lo, hi] for p in ("QB", "RB", "WR", "TE")})

        def check(weights):
            self.assertAlmostEqual(sum(weights.values()), 1.0, places=12)
            for share in weights.values():
                self.assertGreaterEqual(share, lo - 1e-12)
                self.assertLessEqual(share, hi + 1e-12)

        high = out["high"]
        self.assertTrue(high["ok"] and high["clamped"], high)
        self.assertAlmostEqual(high["weights"]["QB"], hi, places=12)
        check(high["weights"])
        self.assertTrue(out["highPriced"] and out["highFixedPie"], out)

        low = out["low"]
        self.assertTrue(low["ok"] and low["clamped"], low)
        self.assertAlmostEqual(low["weights"]["TE"], lo, places=12)
        check(low["weights"])
        self.assertTrue(out["lowPriced"] and out["lowFixedPie"], out)

        four = out["four"]
        self.assertTrue(four["ok"] and four["clamped"], four)
        for share in four["weights"].values():
            self.assertAlmostEqual(share, 0.25, places=12)

        floor = out["fourFloor"]
        self.assertTrue(floor["ok"] and floor["clamped"], floor)
        check(floor["weights"])
        self.assertAlmostEqual(floor["weights"]["WR"], lo, places=12)
        self.assertAlmostEqual(floor["weights"]["QB"], floor["weights"]["RB"], places=12)
        self.assertTrue(out["fourFloorPriced"], out)

        self.assertTrue(out["string"]["ok"], out["string"])
        self.assertAlmostEqual(out["string"]["weights"]["WR"], 0.4, places=12)

        for refused in out["invalid"]:
            self.assertFalse(refused["ok"], refused)
            self.assertIn("error", refused)
        self.assertTrue(out["unchangedAfterInvalid"])

        self.assertTrue(out["reset"]["ok"] and out["reset"]["isDefault"], out["reset"])
        self.assertEqual(out["reset"]["weights"], out["defaults"])
        self.assertEqual(out["afterLeagueChange"], out["defaults10"])

    def test_twelve_combo_sweep_with_a_share_edit(self):
        rows = run(SWEEP, COMBOS)
        self.assertEqual(len(rows), 12)
        bad = [r for r in rows if not r["fixedPie"]
               or sorted(k for k, v in r["starts"].items() if v > 0) != ["QB", "RB", "TE", "WR"]]
        self.assertEqual(bad, [], json.dumps(rows, indent=1))


if __name__ == "__main__":
    unittest.main()
