// Node driver for tests/test_published_league_settings_engine.py (JEG-332 step 3)
// and tests/test_published_views_engine.py (JEG332-VORP-VIEWS).
//
// Usage: node published_engine_driver.js <value-model.js path>  < cases.json
// Default mode runs ValueModel.derivePublishedSetup (pure, no DOM) on each case
// and prints {"results": [{values: {key: value}, translated, belowWaiver,
// version} | {error}]}. With payload.mode === "views" each case is one batch
// for ValueModel.derivePublishedViews and the result carries
// {sources: {src: {vorp, adj}}, batchMax, adjScale, version} | {error}.
"use strict";
const fs = require("fs");
const path = require("path");

const modelPath = path.resolve(process.argv[2]);
const ValueModel = require(modelPath);
const payload = JSON.parse(fs.readFileSync(0, "utf8"));

function runSetup(c) {
  const native = new Map(c.native.map(([k, v]) => [k, v]));
  const saved = new Map(c.saved.map(([k, v]) => [k, v]));
  const pos = new Map(Object.entries(c.pos).map(([k, p]) => [Number(k), p]));
  const out = ValueModel.derivePublishedSetup({
    native, saved, indexTotal: c.index_total, posOf: k => pos.get(k),
    anchor: c.anchor ? new Map(c.anchor.map(([k, v]) => [k, v])) : undefined,
    teams: c.teams, shape: c.shape,
    projection: c.projection ? new Map(c.projection.map(([k, v]) => [k, v])) : undefined,
    peers: c.peers ? Object.fromEntries(Object.entries(c.peers).map(([src, rows]) =>
      [src, new Map(rows.map(([k, v]) => [k, v]))])) : undefined,
  });
  return {
    values: Object.fromEntries([...out.values.entries()]),
    translated: out.translated, belowWaiver: out.belowWaiver, version: out.version,
    factor: out.factor, basis: out.basis, shared: out.shared,
    positionalMax: out.positionalMax, ourMax: out.ourMax,
    savedSetup: ValueModel.isSavedSetup(c.teams, c.shape),
    waiver: out.waiver,
  };
}

function runViews(c) {
  const pos = new Map(Object.entries(c.pos).map(([k, p]) => [Number(k), p]));
  const sources = {};
  Object.entries(c.sources).forEach(([src, s]) => {
    sources[src] = {native: new Map(s.native.map(([k, v]) => [k, v])), keys: s.keys, budgets: s.budgets};
  });
  const out = ValueModel.derivePublishedViews({
    sources, posOf: k => pos.get(k), teams: c.teams, shape: c.shape,
  });
  const res = {version: out.version, batchMax: out.batchMax, adjScale: out.adjScale, sources: {}};
  Object.entries(out.sources).forEach(([src, s]) => {
    res.sources[src] = {vorp: Object.fromEntries([...s.vorp.entries()]),
                        adj: Object.fromEntries([...s.adj.entries()]), groups: s.groups,
                        waiver: s.waiver};
  });
  return res;
}

const run = payload.mode === "views" ? runViews : runSetup;
const results = payload.cases.map(c => {
  try {
    return run(c);
  } catch (error) {
    return {error: String(error && error.message || error)};
  }
});
process.stdout.write(JSON.stringify({results}));
