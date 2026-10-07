// Node driver for tests/test_published_league_settings_engine.py (JEG-332 step 3).
//
// Usage: node published_engine_driver.js <value-model.js path>  < cases.json
// Runs ValueModel.derivePublishedSetup (pure, no DOM) on each case and prints
// {"results": [{values: {key: value}, translated, fallbackSaved, fallbackPie,
// unpriced, version} | {error}]}.
"use strict";
const fs = require("fs");
const path = require("path");

const modelPath = path.resolve(process.argv[2]);
const ValueModel = require(modelPath);
const payload = JSON.parse(fs.readFileSync(0, "utf8"));
const results = payload.cases.map(c => {
  try {
    const native = new Map(c.native.map(([k, v]) => [k, v]));
    const saved = new Map(c.saved.map(([k, v]) => [k, v]));
    const pos = new Map(Object.entries(c.pos).map(([k, p]) => [Number(k), p]));
    const out = ValueModel.derivePublishedSetup({
      native, saved, indexTotal: c.index_total, posOf: k => pos.get(k),
      teams: c.teams, shape: c.shape,
      projection: c.projection ? new Map(c.projection.map(([k, v]) => [k, v])) : undefined,
    });
    return {
      values: Object.fromEntries([...out.values.entries()]),
      translated: out.translated, fallbackSaved: out.fallbackSaved,
      fallbackPie: out.fallbackPie, unpriced: out.unpriced, version: out.version,
      positionalMax: out.positionalMax, ourMax: out.ourMax,
      savedSetup: ValueModel.isSavedSetup(c.teams, c.shape),
    };
  } catch (error) {
    return {error: String(error && error.message || error)};
  }
});
process.stdout.write(JSON.stringify({results}));
