"""JEG-1213: opponent fit readout and useful high-value-for-depth packages.

The named-player scenario uses controlled prices, not a claim about this week's values.
Both incoming RBs start for the receiving team. The real finder, league pairing,
all-opponents runner and table sorter run without stubs.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app" / "v2"
SCRIPT = r"""
const path = require('path');
const dir = process.argv[1], mode = process.argv[2];
const F = require(path.join(dir, 'finder.js'));
const O = require(path.join(dir, 'opportunities.js'));
const S = require(path.join(dir, 'table-sort.js'));
const row = (key, name, ddf, market) => ({player_key: key, name, pos: 'RB', ddfTier: 'starter', values:
  Object.fromEntries([['ddf_value', ddf], ['ddf_value_projections', ddf], ...F.CHART_KEYS.map(k => [k, market])])});
const bijan = row('bijan', 'Bijan Robinson', 70, 90);
const filler = row('starter', 'Other starter', 4, 4);
const bench = row('bench', 'Bench player', 0.5, 0.5);
const kyren = row('kyren', 'Kyren Williams', 55, 55);
const warren = row('warren', 'Jaylen Warren', 30, 25);
const other = row('other', 'Other RB', 20, 20);
const mineRows = [bijan, filler, ...(mode === 'noBench' ? [] : [bench])];
const theirRows = [kyren, warren, other];
const team = (id, rows) => ({id, name: id, entries: rows.map(r => ({key: r.player_key}))});
const mine = team('mine', mineRows), opp = team('opponent', theirRows);
const ctx = {rowsByKey: new Map(mineRows.concat(theirRows).map(r => [r.player_key, r])),
  shape: {QB: 0, RB: 2, WR: 0, TE: 0, FLEX: 0, SUPERFLEX: 0},
  expected: Object.fromEntries(['QB', 'RB', 'WR', 'TE'].map(pos => [pos, {lo: pos === 'RB' ? 2 : 0, hi: pos === 'RB' ? 3 : 0}])),
  weights: {overall: 0.2}, charts: F.CHART_KEYS, market: F.CHART_KEYS, maxSize: 2, keepMine: true, keepTheirs: true};
(async () => {
  if (mode === 'package' || mode === 'noBench') {
    const pairing = O.computePairing(mine, opp, ctx);
    const run = await O.runAll(mine, [opp], ctx, {yieldFn: async () => {}});
    const ordered = S.sortRows(run.rows, O.OPP_COLUMNS, O.OPP_DEFAULT, O.OPP_TIES);
    const pick = rows => rows.find(r => r.give.some(p => p.player_key === 'bijan') &&
      r.receive.length === 2 && r.receive.some(p => p.player_key === 'kyren') && r.receive.some(p => p.player_key === 'warren'));
    const found = pick(ordered);
    const after = F.pickStarters(mineRows.filter(r => !found || !found.give.some(p => p.player_key === r.player_key))
      .concat(found ? found.receive : []), ctx.shape, 'ddf_value').starters;
    console.log(JSON.stringify({pair: pick(pairing.rows) || null, found: found || null,
      ranks: ordered.map(r => r.rank), starts: after.map(r => r.player_key)}));
  } else if (mode === 'missing') {
    const missing = {...kyren, values: {...kyren.values, chart_avg: null}};
    const priced = {...bijan, values: {...bijan.values, chart_avg: 90}};
    const t = F.teamFit({roster: [missing], leaving: [missing], arriving: [priced]}, ctx, 'chart_avg');
    console.log(JSON.stringify({team: t, readout: O.theirFitOf({them: t, marketSupported: true, theirConstruction: {ok: true, issues: []}})}));
  } else if (mode === 'readout') {
    const build = (totalDelta, starterDelta, net, construction) => O.theirFitOf({
      them: {totalDelta, starterDelta, net, tau: 1}, marketSupported: net > 0.05, theirConstruction: construction});
    console.log(JSON.stringify({
      loss: build(-8, 3, 2, {ok: false, issues: ['bench promoted to starter: Other RB']}),
      gain: build(8, -3, -2, {ok: true, issues: []}), tips: F.FIT_TIPS}));
  } else if (mode === 'rank') {
    const ranked = O.rankRows([{id: 'force', tier: 2, edge: 99, score: 99, size: 2, opponent: 'A'},
      {id: 'best', tier: 0, edge: 4, score: 4, size: 3, opponent: 'B'},
      {id: 'second', tier: 0, edge: 2, score: 2, size: 2, opponent: 'C'}]);
    console.log(JSON.stringify(S.sortRows(ranked.reverse(), O.OPP_COLUMNS, O.OPP_DEFAULT, O.OPP_TIES).map(r => ({id: r.id, rank: r.rank}))));
  }
})().catch(e => { console.error(e); process.exit(1); });
"""


def run(mode, app=APP):
    if not shutil.which("node"):
        raise unittest.SkipTest("node is not installed")
    result = subprocess.run(["node", "-e", SCRIPT, str(app), mode], check=True, text=True,
                            capture_output=True, timeout=30)
    return json.loads(result.stdout)


class Jeg1213LogicTests(unittest.TestCase):
    def test_high_value_player_for_two_useful_starters_surfaces(self):
        result = run("package")
        self.assertIsNotNone(result["pair"])
        trade = result["found"]
        self.assertIsNotNone(trade)
        self.assertLess(max(p["values"]["ddf_value"] for p in trade["receive"]), 70)
        self.assertTrue({"kyren", "warren"} <= set(result["starts"]))
        self.assertGreater(trade["edge"], 0)
        self.assertEqual(trade["rivalOkCount"], 4)
        self.assertEqual(trade["addedThrowIns"][0]["row"]["player_key"], "bench")
        self.assertEqual(trade["addedThrowIns"][0]["side"], "give")
        self.assertFalse(trade["unbalanced"])
        self.assertAlmostEqual(trade["theirs"]["totalDelta"], 10.5)
        self.assertAlmostEqual(trade["theirs"]["starterDelta"], 30)
        self.assertIn("roster construction bench promoted to starter", trade["theirs"]["detail"])

    def test_one_for_two_stays_when_there_is_no_bench_throw_in(self):
        result = run("noBench")
        self.assertIsNotNone(result["pair"])
        trade = result["found"]
        self.assertIsNotNone(trade)
        self.assertEqual(len(trade["give"]), 1)
        self.assertEqual(len(trade["receive"]), 2)
        self.assertTrue(trade["unbalanced"])
        self.assertIsNone(trade["addedThrowIns"])

    def test_opponent_total_starters_and_construction_are_independent(self):
        result = run("readout")
        self.assertEqual(result["loss"]["label"], "favorable")  # Existing weighted fit label.
        self.assertIn("market total −8.0; market starters +3.0", result["loss"]["detail"])
        self.assertIn("bench promoted to starter: Other RB", result["loss"]["detail"])
        self.assertIn("market total +8.0; market starters −3.0; roster construction OK", result["gain"]["detail"])
        self.assertIn("bench share", result["tips"]["natural"])
        self.assertIn("starters lose value", result["tips"]["market"])

    def test_missing_market_value_is_unavailable_not_zero(self):
        result = run("missing")
        self.assertIsNone(result["team"]["totalDelta"])
        self.assertIsNone(result["readout"]["totalDelta"])
        self.assertIsNone(result["readout"]["starterDelta"])
        self.assertIn("market total unavailable; market starters unavailable", result["readout"]["detail"])

    def test_default_sort_keeps_best_opportunity_number_one(self):
        self.assertEqual(run("rank"), [{"id": "best", "rank": 1}, {"id": "second", "rank": 2}, {"id": "force", "rank": 3}])

    def test_guards_catch_missing_details_and_reversed_default(self):
        mutations = [
            ("opportunities.js", 'const OPP_DEFAULT = {col: "rank", dir: "asc"};',
             'const OPP_DEFAULT = {col: "rank", dir: "desc"};', "rank"),
            ("finder.js", "? next.total - before.total : null", "? 123 : null", "package"),
        ]
        for filename, old, new, mode in mutations:
            with self.subTest(mutation=filename):
                with tempfile.TemporaryDirectory() as tmp:
                    dest = Path(tmp)
                    for name in ("finder.js", "opportunities.js", "table-sort.js"):
                        shutil.copy2(APP / name, dest / name)
                    text = (dest / filename).read_text()
                    self.assertIn(old, text)
                    (dest / filename).write_text(text.replace(old, new, 1))
                    broken = run(mode, dest)
                    if mode == "rank":
                        self.assertNotEqual(broken[0]["rank"], 1)
                    else:
                        self.assertNotAlmostEqual(broken["found"]["theirs"]["totalDelta"], 10.5)


if __name__ == "__main__":
    unittest.main()
