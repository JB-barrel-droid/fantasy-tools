// Fit label distribution over the 20-team fixture league (JEG-1096 / JEG-1108). Pure Node, deterministic.
//   node tests/node/fit_diagnostic.cjs [modules dir (default app/v2)] [--assert]
// Team 0 is "you"; every other team is an opponent. Rows come from the same synthetic engine rows the league harness
// (tests/league_harness.cjs) uses, values and thresholds untouched. The real opportunities and finder code runs unchanged,
// and every opportunity row's overall fit is counted. Prints a table. Point the first argument at an older checkout's app/v2
// to measure an older build (labels it does not know print as their own rows).
// --assert fails when a label is missing from the table, when the counts do not add up, when the retired "value" label appears, or when Natural, Market supported or Force is empty.
"use strict";
const path = require("path");
const fs = require("fs");
const assert = require("assert");

const args = process.argv.slice(2);
const doAssert = args.includes("--assert");
const dir = path.resolve(args.find(a => !a.startsWith("--")) || path.join(__dirname, "..", "..", "app", "v2"));
const fixture = JSON.parse(fs.readFileSync(path.join(__dirname, "..", "fixtures", "league", "fixture-20team.json"), "utf8"));
const O = require(path.join(dir, "opportunities.js"));
const F = require(path.join(dir, "finder.js"));

const CH = ["usatoday", "fantasycalc", "fantasypros", "cbs"];
const hash = text => { let h = 2166136261; for (const c of String(text)) { h ^= c.charCodeAt(0); h = Math.imul(h, 16777619) >>> 0; } return h >>> 0; };
const unit = (key, salt) => (hash(`${key}:${salt}`) % 10000) / 10000;
function makeRows(players) {
  const map = new Map();
  players.forEach(p => {
    if (String(p.key).startsWith("x:") || map.has(String(p.key))) return;
    const ddf = Math.round((4 + 36 * Math.pow(unit(p.key, "d"), 1.6)) * 10) / 10;
    const values = {ddf_value: ddf};
    const market = 0.62 + 0.76 * unit(p.key, "m");
    CH.forEach(k => { values[k] = Math.round(ddf * market * (0.9 + 0.2 * unit(p.key, k)) * 10) / 10; });
    map.set(String(p.key), {player_key: String(p.key), name: p.name, pos: p.pos, team: p.team || "", values});
  });
  return map;
}
const SHAPE = {QB: 1, RB: 2, WR: 2, TE: 1, FLEX: 1, SUPERFLEX: 0};
const ALLOCATION = [{pos: "QB", rostered: 30, lineup: 12, bench: 18}, {pos: "RB", rostered: 60, lineup: 36, bench: 24}, {pos: "WR", rostered: 66, lineup: 36, bench: 30}, {pos: "TE", rostered: 24, lineup: 12, bench: 12}];
const WEIGHTS = {overall: 0.3, QB: 0.2, RB: 0.3, WR: 0.3, TE: 0.25};

async function main() {
  const players = [].concat(...fixture.teams.map(t => t.players));
  const rows = makeRows(players);
  const teams = fixture.teams.map((t, i) => ({id: `t${i}`, name: t.name, isMine: i === 0, entries: t.players.map(p => ({key: String(p.key), name: p.name, pos: p.pos, team: p.team}))}));
  const ctx = {rowsByKey: rows, shape: SHAPE, expected: F.expectedDepth(ALLOCATION, 12), weights: WEIGHTS, charts: CH.slice(), market: CH.slice(), chartKeys: CH.slice(), maxSize: 2, keepMine: true, keepTheirs: true};
  const out = await O.runAll(teams[0], teams.slice(1), ctx, {cache: O.createCache(), yieldFn: () => Promise.resolve(), budgetMs: 0});
  const counts = {};
  out.rows.forEach(r => { const k = r.overall || "unjudged"; counts[k] = (counts[k] || 0) + 1; });
  const total = out.rows.length;
  const order = ["natural", "market", "value", "force", "unjudged"];
  const labels = order.filter(k => counts[k] !== undefined || ["natural", "market", "force"].includes(k)).concat(Object.keys(counts).filter(k => !order.includes(k)));
  console.log(`Fit labels, 20-team fixture league, team 0 = you, ${teams.length - 1} opponents (modules: ${path.relative(process.cwd(), dir) || "."})`);
  console.log("label".padEnd(12) + "count".padStart(6) + "share".padStart(8));
  labels.forEach(k => console.log(k.padEnd(12) + String(counts[k] || 0).padStart(6) + `${(100 * (counts[k] || 0) / total).toFixed(1)}%`.padStart(8)));
  console.log("total".padEnd(12) + String(total).padStart(6));
  if (doAssert) {
    assert.ok(total > 0, "no opportunities found");
    assert.strictEqual(labels.reduce((n, k) => n + (counts[k] || 0), 0), total, "counts do not add up");
    assert.strictEqual(counts.value, undefined, "the retired value label appeared");
    assert.strictEqual(counts.unjudged, undefined, "rows without a fit label");
    assert.ok(counts.natural > 0, "no Natural rows: the rule cannot be satisfied on the reference league");
    assert.ok(counts.force > 0 && counts.market > 0, "a label is missing from the table: the rules no longer separate trades");
    console.log("assertions passed");
  }
}
main().catch(e => { console.error(e.stack || e); process.exit(1); });
