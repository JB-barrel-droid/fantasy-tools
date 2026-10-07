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
    const ranked = {};
    Object.entries(vector.ranked).forEach(([pos, rows]) => {
      ranked[pos] = rows.map(([key, value]) => ({key, value}));
    });
    const out = ValueModel.translatePublishedVorp({
      ranked,
      teams: vector.teams,
      benchPerTeam: vector.bench_per_team,
      flexCount: vector.flex_count,
      slots: vector.slots || undefined,
      flexEligible: vector.flex_eligible || undefined,
    });
    return {version: out.version, positions: out.positions, translated: out.translated};
  } catch (error) {
    return {error: String(error && error.message || error)};
  }
});
process.stdout.write(JSON.stringify({results}));
