// JEG-1125 review: min_rival_edge in mcp/find-trades.ts counts only the rival's own gain on each chart.
// Under the shared even band, a chart that has you up by less than the band is rival-ok, but the rival
// gains nothing there, so it must not count toward the rival's edge.
// Run by tests/test_trade_bands.py: node --experimental-strip-types tests/node/rival_edge_band_check.mjs <finder.js>
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { findTradesForPair } from "../../supabase/functions/mcp/find-trades.ts";

const require = createRequire(import.meta.url);
const finder = require(process.argv[2]);
const row = (key, ddf, chart) => ({player_key: key, name: `P${key}`, pos: "RB",
  values: Object.fromEntries([["ddf_value", ddf], ...finder.CHART_KEYS.map(k => [k, chart])])});

// You give 20 / 30 on the charts. Theirs: +5 DDF for you; charts +0.9 for you (inside the band: rival even,
// gains 0), or −2 for you (rival gains 2).
const mine = [row(1, 20, 30)];
const listed = (theirs, minRivalEdge) => findTradesForPair(finder, mine, theirs, {maxSize: 1, limit: 10, minRivalEdge}).trades.length;
const inside = [row(2, 25, 30.9)];
const ahead = [row(3, 25, 28)];
assert.equal(listed(inside, 0), 1, "a chart inside the band is rival-ok, so the trade is listed with no rival-edge floor");
assert.equal(listed(inside, 0.5), 0, "the rival gains nothing on a chart that has you up 0.9, so a 0.5 rival-edge floor drops it");
assert.equal(listed(ahead, 0.5), 1, "the rival gains 2 on every chart, so a 0.5 floor keeps it");
assert.equal(listed(ahead, 2.5), 0, "a 2.5 floor drops a 2-point rival edge");
console.log("rival edge ok");
