"""JEG-471 (part 1, engine): the DDF Composite Value ("DDF Value") series.

Jeremy, 2026-10-08 (JEG-455): per player, the equal-weight mean of the
ADJUSTED values -- our projections (espn, cbsros, razzball) and the
bias-adjusted trade charts (*_adjusted) -- over the series that price him.
A missing series never counts as 0; ESPN's 0 for a player it lists at 0
(GAP-025) does. Default inputs: every available current-week input. Tier: rank
by DDF Value and cut at the league's slot counts.

Checks, headless on the built dist/ (the live page):
1. ValueModel.compositeValue: mean of finite values, missing left out, 0 kept.
2. Every row's values.ddf_value / ddfCount / ddfSources is that mean over the
   default inputs, across scorings, team counts, a superflex roster, a bench
   share and a position-share edit (it recomputes with each).
3. setCompositeInputs: a subset changes ddf_value (and only ddf_value), fires
   the rows and shared events (shared only with publish), invalid input is
   refused with no change, null restores every value exactly.
4. Rank, zones and tiers by DDF Value: setLockOrder("ddf_value") ranks by it
   (it survives a league change), the tiers are the slot-count cut by DDF
   Value, and getZones() sits at those tier counts in every position view.
5. Prior week: Δ pairs use the same inputs on both sides; an input without the
   prior week is dropped from both (simulated with an edited history index).
6. Existing series: no ddf entry in getSourceInfo() or getActiveSources() unless
   asked for; the full before/after 12-combo x 3-view sweep is in the PR.
"""
from __future__ import annotations

import json
import unittest

from tests._dist_server import DIST, serve
from tests import _render_env  # noqa: E402


def setUpModule():
    _render_env.ensure_built()


INPUTS = ["espn", "cbsros", "razzball", "fantasycalc_adjusted", "usatoday_adjusted",
          "fantasypros_adjusted", "cbs_adjusted"]

HELPERS = """
  const c = window.TradeValueCurveControls;
  const INPUTS = %s;
  const mean = (row, keys) => {
    const v = keys.map(k => row.values[k]).filter(x => typeof x === 'number' && Number.isFinite(x));
    return {value: v.length ? v.reduce((a, b) => a + b, 0) / v.length : null, count: v.length};
  };
  const others = () => JSON.stringify(c.getAllRows().map(r => {
    const v = {...r.values}; delete v.ddf_value; return [r.player_key, r.espnRole, v];
  }));
  const ddf = () => JSON.stringify(c.getAllRows().map(r => [r.player_key, r.values.ddf_value, r.ddfCount, r.ddfTier]));
  const checkMean = (tag, keys, problems) => {
    let priced = 0;
    c.getAllRows().forEach(r => {
      const want = mean(r, keys);
      const got = r.values.ddf_value;
      if (want.value === null ? got !== null : !(Math.abs(got - want.value) <= 1e-9)) {
        if (problems.length < 40) problems.push(`${tag} ${r.name}: ddf ${got} != mean ${want.value}`);
      }
      if (r.ddfCount !== want.count) problems.push(`${tag} ${r.name}: ddfCount ${r.ddfCount} != ${want.count}`);
      const used = keys.filter(k => typeof r.values[k] === 'number' && Number.isFinite(r.values[k]));
      if (JSON.stringify(r.ddfSources) !== JSON.stringify(used)) problems.push(`${tag} ${r.name}: ddfSources ${r.ddfSources}`);
      if (got !== null) priced += 1;
    });
    if (priced < 100) problems.push(`${tag}: only ${priced} players have a DDF Value`);
    return priced;
  };
""" % json.dumps(INPUTS)

PURE = """() => {
  const m = window.ValueModel.compositeValue;
  return {
    mixed: m({a: 10, b: null, c: 0, d: NaN, e: undefined, f: 20}, ['a', 'b', 'c', 'd', 'e', 'f', 'g']),
    none: m({a: null}, ['a', 'b']),
    order: m({a: 1, b: 2}, ['b', 'a']),
  };
}"""

MEAN = """async () => {""" + HELPERS + """
  const problems = [];
  const info = c.getCompositeInputs();
  if (!info.isDefault) problems.push('inputs are not the defaults on load');
  const keys = info.inputs;
  let zeroPlayers = 0, missingPlayers = 0;
  const steps = [
    ['load', () => {}],
    ['standard/8', () => { c.setScoring('standard'); c.setTeams(8); }],
    ['half_ppr/14', () => { c.setScoring('half_ppr'); c.setTeams(14); }],
    ['ppr/10', () => { c.setScoring('ppr'); c.setTeams(10); }],
    ['ppr/12 superflex', () => { c.setTeams(12); c.setRosterSpot('SUPERFLEX', 1); }],
    ['bench share 25%', () => { c.setRosterSpot('SUPERFLEX', 0); c.setBenchShareFraction(0.25); }],
    ['QB share +5pp', () => { c.setBenchShareFraction(0.15); c.setPositionWeights({QB: c.getPositionWeights().QB + 0.05}); }],
  ];
  for (const [tag, step] of steps) {
    step();
    const now = c.getCompositeInputs().inputs;
    checkMean(tag, now, problems);
    c.getAllRows().forEach(r => {
      if (r.espnProjectsZero && r.values.espn === 0 && now.includes('espn')) {
        zeroPlayers += 1;
        if (!r.ddfSources.includes('espn')) problems.push(`${tag} ${r.name}: ESPN 0 left out of the DDF Value`);
      }
      if (r.ddfCount > 0 && r.ddfCount < now.length) missingPlayers += 1;
    });
  }
  c.setPositionWeights(null);
  return {problems, keys, zeroPlayers, missingPlayers};
}"""

SETTER = """async () => {""" + HELPERS + """
  const out = {problems: []};
  const events = {rows: 0, shared: []};
  window.addEventListener('trade-value-rows-change', () => { events.rows += 1; });
  window.addEventListener('trade-value-shared-change', e => { events.shared.push(e.detail.compositeInputs); });
  const baseOthers = others(), baseDdf = ddf();
  const pick = ['espn', 'fantasycalc_adjusted'];
  out.set = c.setCompositeInputs(['fantasycalc_adjusted', 'espn', 'espn']);
  checkMean('subset', pick, out.problems);
  out.subsetMoved = ddf() !== baseDdf;
  out.othersSame = others() === baseOthers;
  out.eventsAfterSet = JSON.parse(JSON.stringify(events));
  out.get = c.getCompositeInputs();
  const before = ddf();
  out.invalid = [c.setCompositeInputs([]), c.setCompositeInputs(['fantasycalc']), c.setCompositeInputs(['espn_vorp']),
    c.setCompositeInputs(['ddf_value']), c.setCompositeInputs('espn'), c.setCompositeInputs({espn: true}), c.setCompositeInputs(['espn', 'usatoday'])];
  out.unchangedAfterInvalid = ddf() === before && JSON.stringify(c.getCompositeInputs()) === JSON.stringify(out.get);
  const quiet = events.shared.length;
  c.setCompositeInputs(['razzball'], false);
  checkMean('razzball only', ['razzball'], out.problems);
  out.quietShared = events.shared.length - quiet;
  out.reset = c.setCompositeInputs(null);
  out.resetRestores = ddf() === baseDdf && others() === baseOthers;
  out.explicitDefaults = c.setCompositeInputs(c.getCompositeInputs().defaults);
  out.explicitDefaultsSame = ddf() === baseDdf;
  out.resetAlias = c.resetCompositeInputs();
  out.eventsEnd = events;
  return out;
}"""

RANK = """async () => {""" + HELPERS + """
  const problems = [];
  const P = ['QB', 'RB', 'WR', 'TE'];
  const sum = shape => P.reduce((s, p) => s + shape[p], 0) + shape.FLEX + (shape.SUPERFLEX || 0);
  c.setLockOrder('ddf_value');
  if (c.getRankSource() !== 'ddf_value') problems.push(`rank source ${c.getRankSource()} after setLockOrder`);
  const cases = [['ppr', 12, 0], ['standard', 8, 0], ['half_ppr', 14, 0], ['ppr', 10, 1]];
  for (const [scoring, teams, sf] of cases) {
    c.setScoring(scoring); c.setTeams(teams); c.setRosterSpot('SUPERFLEX', sf);
    const tag = `${scoring}/${teams}/sf${sf}`;
    if (c.getRankSource() !== 'ddf_value') problems.push(`${tag}: rank source fell back to ${c.getRankSource()}`);
    const shape = c.getRosterShape();
    const all = c.getAllRows();
    // Tier = the engine's slot fill (ValueModel.roleMap) on the DDF values.
    const values = new Map(all.filter(r => r.values.ddf_value !== null).map(r => [r.player_key, r.values.ddf_value]));
    const byKey = new Map(all.map(r => [r.player_key, r]));
    const roles = window.ValueModel.roleMap({values, playerOf: k => byKey.get(k), teams, shape});
    all.forEach(r => {
      const want = r.values.ddf_value === null ? null : (roles.get(r.player_key) || 'waiver');
      if (r.ddfTier !== want) problems.push(`${tag} ${r.name}: ddfTier ${r.ddfTier} != ${want}`);
    });
    const starters = all.filter(r => r.ddfTier === 'starter').length;
    const bench = all.filter(r => r.ddfTier === 'bench').length;
    if (starters !== teams * sum(shape)) problems.push(`${tag}: ${starters} DDF starters, slots ${teams * sum(shape)}`);
    if (bench !== teams * shape.BENCH) problems.push(`${tag}: ${bench} DDF bench, slots ${teams * shape.BENCH}`);
    for (const pos of ['ALL', 'QB', 'RB', 'WR', 'TE', 'FLEX']) {
      c.setPosition(pos);
      const rows = c.getRows();
      const t = `${tag}/${pos}`;
      for (let i = 1; i < rows.length; i += 1) {
        const a = rows[i - 1].values.ddf_value, b = rows[i].values.ddf_value;
        if (a === null && b !== null) { problems.push(`${t}: a priced player ranks after an unpriced one`); break; }
        if (a !== null && b !== null && b > a) { problems.push(`${t}: rows not in DDF Value order at ${i}`); break; }
      }
      const zones = c.getZones();
      const s = rows.filter(r => r.ddfTier === 'starter').length;
      const n = s + rows.filter(r => r.ddfTier === 'bench').length;
      const at = k => Math.max(1, Math.min(rows.length, k + 0.5));
      if (zones.starter_to_bench !== at(s)) problems.push(`${t}: starter zone ${zones.starter_to_bench}, DDF starters ${s}`);
      if (zones.bench_to_waiver !== at(n)) problems.push(`${t}: bench zone ${zones.bench_to_waiver}, DDF rostered ${n}`);
      if (P.includes(pos)) {
        // Within one position the tiers are a prefix of the DDF order (not in
        // ALL or FLEX: a slot can go to a lower value at another position).
        const rank = ['starter', 'bench', 'waiver', null];
        const order = rows.map(r => rank.indexOf(r.ddfTier));
        const firstBad = order.findIndex((tier, i) => i > 0 && tier < order[i - 1]);
        if (firstBad >= 0) problems.push(`${t}: tiers out of DDF order at ${firstBad}`);
      }
      if (!window.TradeValueCurveDiagnostics.fixedPieIndexed) problems.push(`${t}: fixedPieIndexed false`);
    }
    c.setPosition('ALL');
  }
  c.setRosterSpot('SUPERFLEX', 0); c.setScoring('ppr'); c.setTeams(12);
  c.setLockOrder('espn');
  const plain = {info: c.getSourceInfo().map(i => i.key), active: c.getActiveSources(),
    withComposite: c.getSourceInfo({includeComposite: true}).slice(-1)[0]};
  return {problems, plain, rank: c.getRankSource()};
}"""

PRIOR = """async () => {""" + HELPERS + """
  const out = {problems: []};
  const r = await c.getPriorWeek('ddf_value');
  out.result = {available: r.available, reason: r.reason, sources: r.sources, dropped: r.dropped, inputs: r.inputs,
    currentWeek: r.currentWeek, priorWeek: r.priorWeek, week: r.week};
  if (!r.available) return out;
  const each = {};
  for (const key of r.sources) each[key] = await c.getPriorWeek(key);
  const rows = c.getAllRows();
  let compared = 0;
  rows.forEach(row => {
    const k = row.player_key;
    const cur = mean(row, r.sources);
    if (cur.value === null ? k in r.currentValues : !(Math.abs(r.currentValues[k] - cur.value) <= 1e-9)) {
      if (out.problems.length < 30) out.problems.push(`${row.name}: current ${r.currentValues[k]} != mean ${cur.value}`);
    }
    if (cur.value !== null && r.currentCounts[k] !== cur.count) out.problems.push(`${row.name}: currentCount ${r.currentCounts[k]} != ${cur.count}`);
    const priorVals = r.sources.map(s => each[s].values[k]).filter(v => typeof v === 'number');
    const want = priorVals.length ? priorVals.reduce((a, b) => a + b, 0) / priorVals.length : null;
    if (want === null ? k in r.values : !(Math.abs(r.values[k] - want) <= 1e-9)) {
      if (out.problems.length < 30) out.problems.push(`${row.name}: prior ${r.values[k]} != mean ${want}`);
    }
    if (want !== null && r.counts[k] !== priorVals.length) out.problems.push(`${row.name}: prior count ${r.counts[k]} != ${priorVals.length}`);
    if (want !== null && cur.value !== null) compared += 1;
  });
  out.compared = compared;
  out.wrongWeek = await c.getPriorWeek('ddf_value', r.priorWeek - 1);
  const wk = await c.getWeekValues('ddf_value', r.priorWeek);
  out.weekValuesMatch = wk.available && JSON.stringify(wk.values) === JSON.stringify(r.values);
  out.history = await c.getHistoryWeeks('ddf_value');
  return out;
}"""


def _launch(p):
    exe = _render_env.chromium_executable(p)
    if exe is None:
        raise _render_env.unavailable("no Chromium available")
    return p.chromium.launch(args=_render_env.HERMETIC_ARGS, executable_path=exe)


def run(script: str, history_edit=None):
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise _render_env.unavailable(f"Playwright is not available: {exc}") from exc
    overrides = {}
    if history_edit:
        index = json.loads((DIST / "assets" / "history" / "index.json").read_text(encoding="utf-8"))
        history_edit(index)
        overrides["assets/history/index.json"] = json.dumps(index).encode("utf-8")
    with sync_playwright() as p:
        browser = _launch(p)
        try:
            with serve(DIST, overrides) as base:
                page = browser.new_page(viewport={"width": 1280, "height": 900})
                errors = []
                page.on("pageerror", lambda exc: errors.append(str(exc)))
                page.goto(base + "/", wait_until="networkidle")
                page.wait_for_function(
                    "() => window.TradeValueCurveControls && window.TradeValueCurveControls.isReady()", timeout=60000)
                page.wait_for_timeout(300)
                result = page.evaluate(script)
                if isinstance(result, dict):
                    result["pageErrors"] = errors
                return result
        finally:
            browser.close()


class DdfCompositeValueTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not (DIST / "index.html").exists():
            raise _render_env.unavailable("dist/ not built (run make sync)")

    def test_pure_mean_skips_missing_and_keeps_zero(self):
        out = run(PURE)
        self.assertEqual(out["mixed"]["value"], 10.0)
        self.assertEqual(out["mixed"]["count"], 3)
        self.assertEqual(out["mixed"]["used"], ["a", "c", "f"])
        self.assertEqual(out["none"], {"value": None, "count": 0, "used": []})
        self.assertEqual(out["order"]["used"], ["b", "a"])

    def test_rows_carry_the_mean_of_finite_adjusted_inputs(self):
        out = run(MEAN)
        self.assertEqual(out["pageErrors"], [])
        self.assertEqual(out["keys"], INPUTS, "default inputs are every current-week adjusted series")
        self.assertEqual(out["problems"], [], "\n".join(out["problems"][:40]))
        self.assertGreater(out["missingPlayers"], 0, "no player is missing a source, so missing-not-zero went untested")

    def test_set_composite_inputs(self):
        out = run(SETTER)
        self.assertEqual(out["pageErrors"], [])
        self.assertEqual(out["problems"], [], "\n".join(out["problems"][:40]))
        self.assertTrue(out["set"]["ok"], out["set"])
        self.assertEqual(out["set"]["inputs"], ["espn", "fantasycalc_adjusted"])
        self.assertFalse(out["set"]["isDefault"])
        self.assertTrue(out["subsetMoved"])
        self.assertTrue(out["othersSame"], "a DDF Value input change moved another series")
        self.assertGreaterEqual(out["eventsAfterSet"]["rows"], 1)
        self.assertEqual(out["eventsAfterSet"]["shared"], [["espn", "fantasycalc_adjusted"]])
        for refused in out["invalid"]:
            self.assertFalse(refused["ok"], refused)
            self.assertIn("error", refused)
        self.assertTrue(out["unchangedAfterInvalid"])
        self.assertEqual(out["quietShared"], 0, "publish=false still fired trade-value-shared-change")
        self.assertTrue(out["reset"]["ok"] and out["reset"]["isDefault"], out["reset"])
        self.assertTrue(out["resetRestores"], "null did not restore every value")
        self.assertTrue(out["explicitDefaults"]["isDefault"], out["explicitDefaults"])
        self.assertTrue(out["explicitDefaultsSame"])
        self.assertTrue(out["resetAlias"]["ok"])

    def test_rank_zones_and_tiers_by_ddf_value(self):
        out = run(RANK)
        self.assertEqual(out["pageErrors"], [])
        self.assertEqual(out["problems"], [], "\n".join(out["problems"][:40]))
        self.assertNotIn("ddf_value", out["plain"]["info"])
        self.assertNotIn("ddf_value", out["plain"]["active"])
        entry = out["plain"]["withComposite"]
        self.assertEqual((entry["key"], entry["label"], entry["composite"], entry["available"]),
                         ("ddf_value", "DDF Value", True, True))
        self.assertEqual(out["rank"], "espn")

    def test_prior_week_uses_the_same_inputs_on_both_sides(self):
        out = run(PRIOR)
        self.assertEqual(out["pageErrors"], [])
        res = out["result"]
        self.assertTrue(res["available"], res)
        self.assertEqual(res["priorWeek"], res["currentWeek"] - 1)
        self.assertEqual(res["week"], res["priorWeek"])
        self.assertEqual(sorted(res["sources"] + [d["source"] for d in res["dropped"]]), sorted(res["inputs"]))
        self.assertEqual(out["problems"], [], "\n".join(out["problems"]))
        self.assertGreater(out["compared"], 100)
        self.assertFalse(out["wrongWeek"]["available"])
        self.assertTrue(out["weekValuesMatch"], "getWeekValues(ddf_value, prior) differs from getPriorWeek")
        self.assertEqual(out["history"]["servedWeek"], res["currentWeek"])

    def test_inputs_without_the_prior_week_are_dropped_from_both_weeks(self):
        def edit(index):
            served = index["served"]
            served["cbs"] = {**served["cbs"], "week": served["cbs"]["week"] - 1}   # serves another week
            served.pop("razzball")                                               # no saved week matches
        out = run(PRIOR, history_edit=edit)
        self.assertEqual(out["pageErrors"], [])
        res = out["result"]
        self.assertTrue(res["available"], res)
        dropped = {d["source"]: d["reason"] for d in res["dropped"]}
        self.assertEqual(set(dropped), {"cbs_adjusted", "razzball"}, dropped)
        self.assertIn("not Week", dropped["cbs_adjusted"])
        self.assertNotIn("cbs_adjusted", res["sources"])
        self.assertNotIn("razzball", res["sources"])
        # Both sides are means over exactly res["sources"] (checked per player).
        self.assertEqual(out["problems"], [], "\n".join(out["problems"]))
        self.assertGreater(out["compared"], 100)


if __name__ == "__main__":
    unittest.main()
