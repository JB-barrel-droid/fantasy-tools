// JEG-1188: the league page's trade search (opportunities.js computePairing, finder.js unchanged) on rows priced at a
// league bench level. Driven by tests/test_league_levels_trades.py.
//   node tests/league_levels_trades.cjs <app/v2 dir> <input.json>
// input: {rows: [row], mine: [key], opponents: {id: [key]}, shape, maxSize}. Prints, per opponent, the found trades
// (player keys, edge, chart nets, the throw-ins the search added to even the counts, unbalanced) and each team's
// starters as the throw-in rule picks them.
"use strict";
const fs = require("fs");
const path = require("path");
const [dir, inputPath] = process.argv.slice(2);
const F = require(path.join(dir, "finder.js"));
const O = require(path.join(dir, "opportunities.js"));
const input = JSON.parse(fs.readFileSync(inputPath, "utf8"));
const rowsByKey = new Map(input.rows.map(r => [String(r.player_key), r]));
const entries = keys => keys.map(key => ({key: String(key)}));
const rowsOf = keys => keys.map(k => rowsByKey.get(String(k))).filter(Boolean);
const ctx = {rowsByKey, shape: input.shape, charts: F.CHART_KEYS, market: F.CHART_KEYS, maxSize: input.maxSize || 2};
const keysOf = list => list.map(r => String(r.player_key));
const starters = keys => keysOf(F.pickStarters(rowsOf(keys), input.shape, F.OUR_KEY).starters);
const out = {mineStarters: starters(input.mine), opponents: {}};
for (const [id, keys] of Object.entries(input.opponents)) {
  const res = O.computePairing({id: "mine", name: "Mine", entries: entries(input.mine)}, {id, name: id, entries: entries(keys)}, ctx);
  out.opponents[id] = {starters: starters(keys), trades: res.rows.map(r => ({give: keysOf(r.give), receive: keysOf(r.receive), edge: r.edge,
    charts: r.charts.map(c => ({key: c.key, net: c.net})),
    added: (r.addedThrowIns || []).map(a => ({side: a.side, key: String(a.row.player_key)})), unbalanced: r.unbalanced}))};
}
console.log(JSON.stringify(out));
