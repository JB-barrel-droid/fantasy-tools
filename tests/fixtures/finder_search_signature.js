// Seeded 9v9 rosters (LCG seed 7, four charts) for tests/test_v2_finder_search_unchanged.py: prints one signature per package size
// (trades found, groups, and a sha256 of every trade and group: members, edge, score and order). usage: node this.js path/to/finder.js
const crypto = require("crypto");
const F = require(require("path").resolve(process.argv[2]));
const POS = ["QB", "RB", "RB", "RB", "WR", "WR", "WR", "WR", "TE"];
const CHARTS = ["usatoday", "fantasycalc", "fantasypros", "cbs"];
let seed = 7;
const rnd = () => (seed = (seed * 1664525 + 1013904223) % 4294967296) / 4294967296;
const mk = (pre, n) => Array.from({length: n}, (_, i) => {
  const base = 5 + rnd() * 60;
  const values = {ddf_value: base};
  CHARTS.forEach(k => { values[k] = base * (0.8 + rnd() * 0.5); });
  return {player_key: `${pre}${i}`, name: `${pre}${i}`, pos: POS[i % POS.length], values};
});
const mine = mk("m", 9), theirs = mk("t", 9);
const out = {};
for (const size of [2, 3]) {
  const res = F.findTrades(mine, theirs, {chartKeys: CHARTS, maxSize: size, limit: 1e7});
  const groups = F.groupTrades(res.trades, {ourKey: res.ourKey});
  const sig = {trades: res.trades.map(t => [t.give.map(r => r.player_key), t.receive.map(r => r.player_key), t.edge, t.score]),
    groups: groups.map(g => [g.key, g.bestEdge, g.best.score, g.best.give.map(r => r.player_key), g.best.receive.map(r => r.player_key), g.trades.length])};
  out[`${size}-for-${size}`] = {trades: res.trades.length, groups: groups.length, sha256: crypto.createHash("sha256").update(JSON.stringify(sig)).digest("hex")};
}
console.log(JSON.stringify(out));
