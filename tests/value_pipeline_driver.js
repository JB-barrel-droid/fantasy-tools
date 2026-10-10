// Node driver for the engine's source-neutral value pipeline (JEG-508).
//
// Usage:
//   node tests/value_pipeline_driver.js <value-model.js> <input.json> [--bench-share X]
//
// <input.json> is the worked-example shape (tests/fixtures/
// value_pipeline_worked_example.json): {setting, players, inputs: {src:
// {family, status, values}}}. Prints the pipeline result in the fixture's
// vocabulary (expected.* names) so a test or the lead's value_check can diff
// it field by field. Works for any setting and any sources, not only the
// fixture.
"use strict";
const fs = require("fs");
const path = require("path");

const args = process.argv.slice(2);
const ValueModel = require(path.resolve(args[0]));
const doc = JSON.parse(fs.readFileSync(args[1], "utf8"));
const setting = Object.assign({}, doc.setting);
const bsFlag = args.indexOf("--bench-share");
if (bsFlag !== -1) setting.bench_share = Number(args[bsFlag + 1]);

const sources = {};
Object.entries(doc.inputs || doc.sources).forEach(([key, s]) => {
  sources[key] = {family: s.family, status: s.status, values: s.values, label: s.label || key};
});
const result = ValueModel.runValuePipeline({
  setting, players: doc.players, sources,
  included: doc.included, compositeInputs: doc.compositeInputs,
});

const intKeys = (keys) => keys.map(Number);
const out = {
  version: result.version,
  included: result.included,
  pie: result.pie,
  bench_share_applied: result.benchShareApplied,
  mean_ppg: result.meanPpg,
  allocation: result.allocation,
  slot_fill_mean_ppg: result.slotFill,
  fill_sets: Object.fromEntries(Object.entries(result.fillSets).map(([p, ks]) => [p, intKeys(ks)])),
  starter_mix_mean: result.starterMixMean,
  bench_mix_mean: result.benchMixMean,
  ddf_weights: result.ddfWeights,
  group_budgets: result.budgets,
  default_ranking: intKeys(result.defaultRanking),
  sources: {},
  indexed: {},
  rows: {},
};
Object.entries(result.sources).forEach(([src, o]) => {
  const positions = {};
  Object.entries(o.positions).forEach(([pos, p]) => {
    const ratios = {};
    Object.entries(p.estimates).forEach(([k, e]) => {
      const peers = {};
      Object.entries(e.peers).forEach(([peer, r]) => {
        peers[peer] = {usable: r.usable, fit_players: intKeys(r.fitPlayers), num: r.num, den: r.den,
          ratio: r.ratio, peer_native: r.peerNative, estimate: r.estimate};
      });
      const rec = {peers, cap: e.cap, path: e.path, raw: e.raw, value: e.value, capped: e.capped,
        reason: e.reason};
      if (e.curve) {
        rec.curve = {points: intKeys(e.curve.points), mean_ppg: e.curve.meanPpg, kind: e.curve.kind};
        if (e.curve.kind === "ols") { rec.curve.slope = e.curve.slope; rec.curve.intercept = e.curve.intercept; }
      }
      ratios[k] = rec;
    });
    positions[pos] = {dedicated: p.dedicated, superflex: p.superflex, flex: p.flex, bench: p.bench,
      starters: p.starters, rostered: p.rostered, listed: p.listed, extended: p.nEstimated > 0,
      imputation_ratios: p.nEstimated > 0 ? ratios : null, waiver_value: p.waiver,
      starter_line: p.starterLine, method: p.method};
  });
  const playersOut = {};
  Object.entries(o.players).forEach(([k, r]) => {
    playersOut[k] = {pos: r.pos, native: r.native, imputed: r.estimated, rank: r.rank, role: r.role,
      vorp: r.vorp, bench_slice: r.benchSlice, starter_slice: r.starterSlice, adjusted: r.adjusted,
      vorp_display: r.vorpDisplay};
  });
  out.sources[src] = {family: o.family, status: o.status, positions, groups: o.groups,
    total_vorp: o.totalVorp, players: playersOut, weights: o.weights, starter_mix: o.starterMix,
    bench_mix: o.benchMix, rates: o.rates, unfunded_moved: o.unfundedMoved,
    unfunded_groups: o.unfundedGroups, vorp_display_factor: o.vorpFactor};
});
Object.entries(result.indexed).forEach(([src, ix]) => {
  const values = {};
  Object.entries(result.rows).forEach(([k, row]) => { values[k] = row.indexed[src]; });
  out.indexed[src] = {factor: ix.factor, shared_players: ix.sharedPlayers, ddf_total: ix.ddfTotal,
    native_total: ix.nativeTotal, values};
});
const ddf = (e) => ({value: e.value, count: e.count, low_confidence: e.lowConfidence, sources: e.sources,
  reason: e.reason});
Object.entries(result.rows).forEach(([k, row]) => {
  out.rows[k] = {name: row.name, pos: row.pos, adjusted: row.adjusted, vorp_vs_waivers: row.vorp,
    estimated: row.estimatedPath, estimated_reason: row.estimated, reasons: row.reasons,
    ddf_blended: ddf(row.ddfByVersion.blended), ddf_charts: ddf(row.ddfByVersion.charts),
    ddf_projections: ddf(row.ddfByVersion.projections), indexed: Object.fromEntries(
      Object.entries(row.indexed).filter(([src]) => result.sources[src].family === "chart")),
    ddf_tier: row.tier, mean_ppg: row.meanPpg};
});
process.stdout.write(JSON.stringify(out));
