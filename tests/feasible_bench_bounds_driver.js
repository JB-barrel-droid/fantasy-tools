// Node driver for tests/test_feasible_bench_bounds_parity.py (JEG-432 R2).
//
// Usage: node feasible_bench_bounds_driver.js <value-model.js path> < vectors.json
// Loads value-model.js (the file under test) plus curve-widget.js for the
// TwoTier pool builder, with no DOM. Per vector it runs
// ValueModel.feasibleBenchBounds twice:
//   given  -- on the tier exposures the Python side computed (pure rule parity);
//   built  -- on tiers built HERE by TwoTier.buildPositionTiers from the same
//             pool (end-to-end parity: the browser's own pool builder), only
//             when vector.build_tiers is set;
// plus, for built tiers, TwoTier.feasibleBenchShareInterval (the existing
// bisection) so the closed-form interval can be checked against it.
"use strict";
const fs = require("fs");
const path = require("path");

globalThis.window = globalThis;
const modelPath = path.resolve(process.argv[2]);
delete require.cache[modelPath];
const ValueModel = require(modelPath);
globalThis.ValueModel = ValueModel;
require(path.join(__dirname, "..", "app", "trade-value-chart", "assets", "curve-widget.js"));
const T = globalThis.TradeValueTwoTier;

const payload = JSON.parse(fs.readFileSync(0, "utf8"));
const results = payload.vectors.map(vector => {
  const pool = {};
  Object.entries(vector.pool).forEach(([pos, rows]) => {
    pool[pos] = rows.map(([key, value]) => ({key, value}));
  });
  const run = tiers => {
    try {
      return ValueModel.feasibleBenchBounds({
        teams: vector.teams, shape: vector.shape || undefined, scoring: vector.scoring || null,
        pool, tiers: tiers || undefined,
      });
    } catch (error) {
      return {error: String(error && error.message || error)};
    }
  };
  const out = {given: run(vector.tiers)};
  if (vector.build_tiers) {
    const lists = {};
    Object.entries(vector.pool).forEach(([pos, rows]) => {
      lists[pos] = rows.map(([key, value]) => ({id: String(key), x: value}));
    });
    const built = T.buildPositionTiers(lists, {
      teams: vector.teams, slots: {...T.REF_SLOTS}, flexCount: T.REF_FLEX_COUNT,
      flexEligible: [...T.REF_FLEX_ELIGIBLE], benchMix: T.legacyBenchMixFor(vector.teams),
    });
    out.built = run(built.tiers);
    out.bisect = {};
    T.POSITIONS.forEach(pos => {
      const t = built.tiers[pos];
      // Pie is the tier surplus, as in the widget (it cancels in the rule).
      out.bisect[pos] = t ? T.feasibleBenchShareInterval(t.aBench, t.bBench, t.aStart, t.bStart, t.surplus, pos) : null;
    });
  }
  return out;
});
process.stdout.write(JSON.stringify({results}));
