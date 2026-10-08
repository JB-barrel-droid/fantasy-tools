// Node driver for tests/test_vorp_translation_js_parity.py (JEG-332 / JEG-364).
//
// Usage: node vorp_translation_parity_driver.js <value-model.js path>  < vectors.json
// Loads value-model.js with no DOM, runs ValueModel.translatePublishedVorp on
// every vector, prints {"results": [...]} (one entry per vector, or
// {"error": "..."} when the JS throws -- the Python side must throw too).
"use strict";
const fs = require("fs");
const path = require("path");

const modelPath = path.resolve(process.argv[2]);
delete require.cache[modelPath];
const ValueModel = require(modelPath);
const payload = JSON.parse(fs.readFileSync(0, "utf8"));
const results = payload.vectors.map(vector => {
  try {
    if (vector.kind === "max") {
      // JEG332-DERIVED-PEAKS: ValueModel.positionalMaxForSetup vs
      // unified.positional_max_for_setup.
      const projection = {};
      Object.entries(vector.projection).forEach(([pos, rows]) => {
        projection[pos] = rows.map(([key, value]) => ({key, value}));
      });
      return {maxes: ValueModel.positionalMaxForSetup({
        projection,
        teams: vector.teams,
        benchPerTeam: vector.bench_per_team,
        flexCount: vector.flex_count,
        slots: vector.slots || undefined,
        flexEligible: vector.flex_eligible || undefined,
        superflexCount: vector.superflex_count === null ? undefined : vector.superflex_count,
      })};
    }
    const toRanked = byPos => {
      const out = {};
      Object.entries(byPos || {}).forEach(([pos, rows]) => {
        out[pos] = rows.map(([key, value]) => ({key, value}));
      });
      return out;
    };
    const ranked = toRanked(vector.ranked);
    // V2-WAIVER-COVERAGE: the other published charts (peers).
    let peers;
    if (vector.peers) {
      peers = {};
      Object.entries(vector.peers).forEach(([src, byPos]) => { peers[src] = toRanked(byPos); });
    }
    if (vector.kind === "impute") {
      const sorted = {};
      Object.entries(ranked).forEach(([pos, rows]) => {
        sorted[pos] = rows.slice().sort((a, b) => b.value - a.value);
      });
      const ext = ValueModel.imputeExtension(sorted, peers);
      return {extension: Object.fromEntries(Object.entries(ext).map(([pos, rows]) =>
        [pos, rows.map(r => [String(r.key), r.value])]))};
    }
    const out = ValueModel.translatePublishedVorp({
      ranked,
      teams: vector.teams,
      benchPerTeam: vector.bench_per_team,
      flexCount: vector.flex_count,
      slots: vector.slots || undefined,
      flexEligible: vector.flex_eligible || undefined,
      ourMax: vector.our_max || undefined,
      superflexCount: vector.superflex_count === null ? undefined : vector.superflex_count,
      peers,
    });
    return {version: out.version, positions: out.positions, translated: out.translated};
  } catch (error) {
    return {error: String(error && error.message || error)};
  }
});
process.stdout.write(JSON.stringify({results}));
