"""JEG-1035: TradeValueCurveControls.setValueOverrides / getValueOverrides.

Jeremy, 2026-10-24: "select a player and say their ddf is actually a different
value ... have it permeate through the full dashboard."

Checks, on the build-only engine page, at four league settings:
1. Off by default: getValueOverrides() is empty and no row carries an override.
2. An override replaces DDF Value (ddf_value and ddf_value_projections) on that
   player's row in getAllRows(), getRows() and searchPlayers(), marks the row
   (valueOverride, ddfPipelineValue) and moves him in the DDF Value ranking.
3. Nothing else moves: every other player's values, the overridden player's
   other series (trade chart average, each source, Indexed/VORP), and the
   pipeline's own DDF Value (getCompositeValues) are unchanged.
4. Clearing restores every value exactly; invalid entries are refused.
"""
from __future__ import annotations

import unittest

from tests._dist_server import DIST, ENGINE_PAGE, serve
from tests import _render_env  # noqa: E402


def setUpModule():
    _render_env.ensure_built()


COMBOS = [["ppr", 12], ["standard", 8], ["half_ppr", 10], ["ppr", 14]]

SCRIPT = """async (combos) => {
  const c = window.TradeValueCurveControls;
  const OV = ['ddf_value', 'ddf_value_projections'];
  const snap = () => {
    const out = {};
    c.getAllRows().forEach(r => Object.entries(r.values).forEach(([k, v]) => { out[`${r.player_key}|${k}`] = v; }));
    return out;
  };
  const problems = [];
  if (Object.keys(c.getValueOverrides()).length) problems.push('overrides not empty at load');
  for (const [scoring, teams] of combos) {
    c.setScoring(scoring); c.setTeams(teams);
    const tag = `${scoring}/${teams}`;
    if (c.getAllRows().some(r => r.valueOverride !== null && r.valueOverride !== undefined)) problems.push(`${tag}: a row has an override by default`);
    const base = snap();
    const comp = JSON.stringify(c.getCompositeValues('ddf_value').current);
    const ranked = c.getAllRows().filter(r => r.pos === 'RB' && Number.isFinite(r.values.ddf_value))
      .sort((a, b) => b.values.ddf_value - a.values.ddf_value);
    const low = ranked[Math.min(40, ranked.length - 1)];
    const top = ranked[0].values.ddf_value;
    const target = Math.round((top + 1) * 100) / 100;
    c.setValueOverrides({[low.player_key]: target, bogus: 5, 123456789.5: 3, [ranked[1].player_key]: -4});
    const got = c.getValueOverrides();
    if (Object.keys(got).length !== 1 || got[low.player_key] !== target) problems.push(`${tag}: invalid entries not refused: ${JSON.stringify(got)}`);
    const after = snap();
    Object.keys(base).forEach(k => {
      const [key, series] = k.split('|');
      const mine = Number(key) === low.player_key && OV.includes(series);
      if (mine) { if (after[k] !== target) problems.push(`${tag}: ${series} not overridden (${after[k]})`); }
      else if (after[k] !== base[k]) problems.push(`${tag}: ${k} moved ${base[k]} -> ${after[k]}`);
    });
    const row = c.getAllRows().find(r => r.player_key === low.player_key);
    if (row.valueOverride !== target) problems.push(`${tag}: row.valueOverride ${row.valueOverride}`);
    if (row.ddfPipelineValue !== base[`${low.player_key}|ddf_value`]) problems.push(`${tag}: ddfPipelineValue ${row.ddfPipelineValue}`);
    if (row.ddfByVersion.blended.value !== target || !row.ddfByVersion.blended.overridden) problems.push(`${tag}: ddfByVersion.blended not overridden`);
    if (row.ddfByVersion.charts.overridden) problems.push(`${tag}: trade chart average marked overridden`);
    const hit = c.searchPlayers(low.name, {limit: 5}).find(r => r.player_key === low.player_key);
    if (!hit || hit.values.ddf_value !== target) problems.push(`${tag}: searchPlayers row not overridden`);
    c.setPosition('RB'); c.setLockOrder('ddf_value');
    const first = c.getRows()[0];
    if (!first || first.player_key !== low.player_key) problems.push(`${tag}: overridden player is not first in the DDF Value ranking (${first && first.name})`);
    c.setPosition('ALL');
    if (JSON.stringify(c.getCompositeValues('ddf_value').current) !== comp) problems.push(`${tag}: pipeline DDF Value changed`);
    c.setValueOverrides(null);
    const back = snap();
    if (JSON.stringify(back) !== JSON.stringify(base)) problems.push(`${tag}: values not restored after clearing`);
  }
  return problems;
}"""


def run(script, arg=None):
    from playwright.sync_api import sync_playwright
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


class ValueOverridesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not ENGINE_PAGE.exists():
            raise _render_env.unavailable("dist/ not built (run make sync)")

    def test_override_replaces_ddf_value_only_and_clears(self):
        problems = run(SCRIPT, COMBOS)
        self.assertEqual(problems, [], "\n".join(problems[:40]))


if __name__ == "__main__":
    unittest.main()
