"""JEG-1035: TradeValueCurveControls.setValueOverrides / getValueOverrides.

Jeremy, 2026-10-24: "select a player and say their ddf is actually a different
value ... have it permeate through the full dashboard."

Checks, on the build-only engine page, at four league settings:
1. Off by default: getValueOverrides() is empty and no row carries an override.
2. An override replaces DDF Value (ddf_value only since JEG-1073; the projections
   alternate ddf_value_projections is not overridden) on that
   player's row in getAllRows(), getRows() and searchPlayers(), marks the row
   (valueOverride, ddfPipelineValue) and moves him in the DDF Value ranking.
3. Nothing else moves: every other player's values, the overridden player's
   other series (trade chart average, each source, Indexed/VORP), and the
   pipeline's own DDF Value (getCompositeValues) are unchanged.
4. Clearing restores every value exactly; invalid entries are refused.
5. JEG-1058: an adjustment ("+5", "-3") adds to the pipeline's own DDF Value,
   capped at the 0-100 value scale; the pipeline's value and the trade chart
   average do not move, and an adjustment without a usable delta is refused.
6. JEG-1058: an override that arrives from outside the editor (a share link,
   an import, a saved record) is put on the scale the editor shows: an
   absolute value above 100 is capped, an adjustment is capped to the scale's
   span.
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
  const OV = ['ddf_value'];   // JEG-1073: the projections alternate is not overridden
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
    if (row.ddfByVersion.projections.overridden || row.values.ddf_value_projections !== base[`${low.player_key}|ddf_value_projections`]) problems.push(`${tag}: projections alternate was overridden`);
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

# JEG-1058: the second kind of override. An adjustment ("+5", "-3") adds to the
# pipeline's own DDF Value, capped at the 0-100 value scale; the pipeline's own
# value and the trade chart average do not move.
ADJUSTMENT_SCRIPT = """async () => {
  const c = window.TradeValueCurveControls;
  const problems = [];
  const rows = c.getAllRows().filter(r => r.pos === 'RB' && Number.isFinite(r.values.ddf_value))
    .sort((a, b) => b.values.ddf_value - a.values.ddf_value);
  const target = rows[3];
  const key = target.player_key;
  const pipeline = target.values.ddf_value;
  const comp = JSON.stringify(c.getCompositeValues('ddf_value').current);
  const valueOf = () => c.getAllRows().find(r => r.player_key === key).values.ddf_value;
  // +5 adds to the pipeline's own value.
  c.setValueOverrides({[key]: {type: 'adjustment', delta: 5}});
  if (Math.abs(valueOf() - (pipeline + 5)) > 1e-9) problems.push(`+5 gave ${valueOf()}, expected ${pipeline + 5}`);
  const row = c.getAllRows().find(r => r.player_key === key);
  if (!row.valueOverrideSpec || row.valueOverrideSpec.type !== 'adjustment' || row.valueOverrideSpec.delta !== 5) {
    problems.push(`valueOverrideSpec ${JSON.stringify(row.valueOverrideSpec)}`);
  }
  if (row.ddfPipelineValue !== pipeline) problems.push(`ddfPipelineValue ${row.ddfPipelineValue}`);
  const got = c.getValueOverrides();
  if (!got[key] || got[key].type !== 'adjustment' || got[key].delta !== 5) problems.push(`getValueOverrides ${JSON.stringify(got)}`);
  if (JSON.stringify(c.getCompositeValues('ddf_value').current) !== comp) problems.push('the pipeline value changed');
  // -3 takes off.
  c.setValueOverrides({[key]: {type: 'adjustment', delta: -3}});
  if (Math.abs(valueOf() - (pipeline - 3)) > 1e-9) problems.push(`-3 gave ${valueOf()}`);
  // The value scale is 0-100: an adjustment past either end is capped.
  c.setValueOverrides({[key]: {type: 'adjustment', delta: 500}});
  if (valueOf() !== 100) problems.push(`not capped at 100: ${valueOf()}`);
  c.setValueOverrides({[key]: {type: 'adjustment', delta: -500}});
  if (valueOf() !== 0) problems.push(`not capped at 0: ${valueOf()}`);
  // An adjustment without a usable delta is refused.
  c.setValueOverrides({[key]: {type: 'adjustment'}, [rows[4].player_key]: {type: 'adjustment', delta: 'x'}});
  if (Object.keys(c.getValueOverrides()).length) problems.push(`invalid adjustments not refused: ${JSON.stringify(c.getValueOverrides())}`);
  // Clearing restores the pipeline's own value.
  c.setValueOverrides(null);
  if (valueOf() !== pipeline) problems.push(`not restored: ${valueOf()}`);
  return problems;
}"""

# JEG-1058: an override that arrives from outside the editor (a share link, an
# import, a saved record) is put on the scale the editor shows: an absolute
# value above 100 is capped, an adjustment is capped to the scale's span (so it
# always fits a packed share link and the value it produces is unchanged).
SCALE_SCRIPT = """async () => {
  const c = window.TradeValueCurveControls;
  const problems = [];
  const rows = c.getAllRows().filter(r => r.pos === 'RB' && Number.isFinite(r.values.ddf_value))
    .sort((a, b) => b.values.ddf_value - a.values.ddf_value);
  const target = rows[3];
  const key = target.player_key;
  const valueOf = () => c.getAllRows().find(r => r.player_key === key).values.ddf_value;
  // An absolute value past the top of the scale is capped, not applied as it is.
  c.setValueOverrides({[key]: 120});
  if (valueOf() !== 100) problems.push(`120 gave ${valueOf()}, expected 100`);
  if (c.getValueOverrides()[key] !== 100) problems.push(`120 stored as ${JSON.stringify(c.getValueOverrides()[key])}`);
  // An adjustment past the scale is capped to the span of the scale: the value
  // is the same, and the delta it travels as is inside the packed link's range.
  c.setValueOverrides({[key]: {type: 'adjustment', delta: 5000}});
  if (valueOf() !== 100) problems.push(`+5000 gave ${valueOf()}, expected 100`);
  const spec = c.getValueOverrides()[key];
  if (!spec || spec.type !== 'adjustment' || spec.delta !== 100) problems.push(`+5000 stored as ${JSON.stringify(spec)}`);
  c.setValueOverrides({[key]: {type: 'adjustment', delta: -5000}});
  if (valueOf() !== 0) problems.push(`-5000 gave ${valueOf()}, expected 0`);
  const down = c.getValueOverrides()[key];
  if (!down || down.type !== 'adjustment' || down.delta !== -100) problems.push(`-5000 stored as ${JSON.stringify(down)}`);
  c.setValueOverrides(null);
  return problems;
}"""


def run(script, arg=None):
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        # JEG-1075: skip locally, error under RENDER_TESTS_REQUIRED=1.
        raise _render_env.unavailable("Playwright is not installed")
    with sync_playwright() as p:
        exe = _render_env.chromium_executable(p)
        if exe is None:
            raise _render_env.unavailable("no Chromium available")
        browser = p.chromium.launch(args=_render_env.HERMETIC_ARGS, executable_path=exe)
        try:
            with serve(DIST) as base:
                page = browser.new_page(viewport={"width": 1280, "height": 900})
                page.add_init_script(_render_env.pin_data_week_script())
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

    def test_an_adjustment_adds_to_the_pipeline_value_and_is_capped(self):
        problems = run(ADJUSTMENT_SCRIPT)
        self.assertEqual(problems, [], "\n".join(problems[:40]))

    def test_an_override_from_outside_the_editor_is_capped_at_the_scale(self):
        problems = run(SCALE_SCRIPT)
        self.assertEqual(problems, [], "\n".join(problems[:40]))


if __name__ == "__main__":
    unittest.main()
