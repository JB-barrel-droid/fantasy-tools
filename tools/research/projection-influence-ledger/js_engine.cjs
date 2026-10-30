// JEG-1280: runs the production engine (value-model.js), read only, on the
// projection-influence ledger's pairs so the reference's chart DDF Value moves
// can be checked against the engine the page ships.
//
// Usage: node js_engine.cjs <value-model.js> <cases.json>
// cases.json: {players: {key: {pos, name}},
//              cases: {id: {setting, sources: {key: {family, values}}, included, hidden, lineup}}}
// Prints {id: {playerKey: DDF Value}} (the blended version, the chart average).
"use strict";
const fs = require("fs");
const path = require("path");

const [modelPath, casesPath] = process.argv.slice(2);
const ValueModel = require(path.resolve(modelPath));
const doc = JSON.parse(fs.readFileSync(casesPath, "utf8"));
const out = {};
Object.keys(doc.cases).sort().forEach((id) => {
  const c = doc.cases[id];
  const sources = {};
  Object.keys(c.sources).forEach((k) => {
    sources[k] = {family: c.sources[k].family, status: "included", values: c.sources[k].values, label: k};
  });
  const result = ValueModel.runValuePipeline({
    setting: c.setting, players: doc.players, sources,
    included: c.included, hidden: c.hidden, lineup: c.lineup,
  });
  const values = {};
  Object.keys(result.rows).forEach((k) => { values[k] = result.rows[k].ddfByVersion.blended.value; });
  out[id] = values;
});
process.stdout.write(JSON.stringify(out));
