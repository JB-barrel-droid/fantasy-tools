// JEG-1329: the connector's trade tools return both sides of the trade, and the league scan's
// site link keeps every team. Pure Node, no network. Run by tests/test_mcp_remote.py.
//
// Checked here:
//   (a) every find_trades and find_trades_league row carries their side (Trade chart average net,
//       starters change) and both teams' roster construction, equal to the finder's own tradeFit
//       on the same trade;
//   (b) the trade text shows their starters change;
//   (c) find_trades_league's site link opens #find-league with every team, yours marked first,
//       read back by the site's own workspace.js decodeShare, plus the league settings;
//   (d) no fit context (an older get-values): no sides, never approximated.
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { handleRpc } from "../../supabase/functions/mcp/rpc.ts";
import { leagueShareText } from "../../supabase/functions/mcp/state.ts";

const require = createRequire(import.meta.url);
const codec = require("../../app/v2/ddf-state.js");
const F = require("../../app/v2/finder.js");
const W = require("../../app/v2/workspace.js");
const ORIGIN = "https://site.test";
const deps = { codec, siteOrigin: ORIGIN };

const ch = (a, b, c, d) => ({ usatoday: a, fantasycalc: b, fantasypros: c, cbs: d });
const P = (player_key, name, pos, value, adj, idx) => ({ player_key, name, pos, value, tier: "starter",
  chart_values: adj, chart_indexed: idx, ddf_value_charts: value, ddf_value_projections: value });
const players = [
  P(3, "Josh Allen", "QB", 40, ch(35, 38, 42, 36), ch(35, 38, 42, 36)),
  P(4, "Josh Jacobs", "RB", 39, ch(34, 37, 41, 35), ch(34, 37, 41, 35)),
  P(7, "Brian Thomas Jr.", "WR", 33, ch(30, 31, 32, 30), ch(30, 31, 32, 30)),
  // Cheap on the charts and dear on DDF Value, so trades exist (as in mcp_remote_check.mjs).
  P(6, "Chart Gem", "RB", 45, ch(45, 45, 45, 45), ch(10, 11, 9, 10)),
  P(1, "Bijan Robinson", "RB", 71.8, ch(65, 68, 70, 66), ch(65, 68, 70, 66)),
  P(2, "Ja'Marr Chase", "WR", 70.2, ch(64, 67, 69, 65), ch(64, 67, 69, 65)),
  P(12345, "Keyed Player", "WR", 20, ch(25, 26, 24, 25), ch(25, 26, 24, 25)),
  P(9, "DJ Moore", "WR", 28, ch(26, 27, 29, 27), ch(26, 27, 29, 27)),
];
const BENCH = { QB: 0.2, RB: 0.3, WR: 0.3, TE: 0.25, overall: 0.28, input: 0.15 };
const charts = async (scoring, teams, superflex) => ({
  attribution: "Data Driven Football", as_of: "2026-10-29", setting: { scoring, teams, superflex }, players,
  sources_included: ["espn", "usatoday", "fantasycalc", "fantasypros", "cbs"], sources_excluded: [], bench_share: BENCH,
});
const stub = async (scoring, teams, superflex) => ({ ...(await charts(scoring, teams, superflex)) });
const call = (name, args, fetchCharts = charts) => handleRpc(
  { jsonrpc: "2.0", id: 1, method: "tools/call", params: { name, arguments: args } }, stub, deps, { finder: F, fetchCharts });

// The finder's own judgement of one returned row, from the same rows the connector builds
// (Indexed chart values, the engine's bench weights, the default league shape).
const CH = ["usatoday", "fantasycalc", "fantasypros", "cbs"];
const SHAPE = { QB: 1, RB: 2, WR: 2, TE: 1, FLEX: 1, SUPERFLEX: 0 };
const byName = new Map(players.map((p) => [p.name, p]));
const rowOf = (p) => ({ player_key: p.player_key, name: p.name, pos: p.pos,
  values: { ddf_value: p.value, ...p.chart_indexed, ddf_value_charts: p.ddf_value_charts, ddf_value_projections: p.ddf_value_projections } });
function reference(mineNames, theirNames, t) {
  const mine = F.withChartAverage(mineNames.map((n) => rowOf(byName.get(n))), CH);
  const theirs = F.withChartAverage(theirNames.map((n) => rowOf(byName.get(n))), CH);
  const pick = (list, side) => side.map((p) => list.find((r) => r.name === p.name));
  const give = pick(mine, t.userGives);
  const recv = pick(theirs, t.userGets);
  const weights = { overall: BENCH.overall, QB: BENCH.QB, RB: BENCH.RB, WR: BENCH.WR, TE: BENCH.TE };
  return F.tradeFit({ mine: { roster: mine, leaving: give, arriving: recv }, theirs: { roster: theirs, leaving: recv, arriving: give } },
    { shape: SHAPE, chartKeys: CH, weights, expected: null, ourKey: F.OUR_KEY, marketKey: F.MARKET_KEY, z: F.FIT_Z });
}
const r1 = (n) => Math.round(n * 10) / 10;
function checkSides(t, ref, id) {
  assert.ok(t.yours && t.theirs, `${id}: both sides present: ${JSON.stringify(t)}`);
  assert.equal(t.theirs.marketNet, r1(ref.them.net), `${id}: their Trade chart average net`);
  assert.equal(t.theirs.starters, r1(ref.them.starterDelta), `${id}: their starters change`);
  assert.equal(t.yours.constructionOk, ref.myConstruction.ok, `${id}: your roster construction`);
  assert.equal(t.theirs.constructionOk, ref.theirConstruction.ok, `${id}: their roster construction`);
  // The issue sentences stay in the one fit reason (the finder's fitText), not repeated per side.
  for (const issue of ref.myConstruction.issues.concat(ref.theirConstruction.issues)) assert.ok(t.fitReason.includes(issue), `${id}: reason names ${issue}`);
}

// (a) and (b), one team.
const MINE = ["Josh Allen", "Josh Jacobs", "Brian Thomas Jr."];
const GEM = ["Chart Gem", "Bijan Robinson"];
let r = await call("find_trades", { mine: MINE.join(", "), theirs: GEM.join(", ") });
assert.notEqual(r.result.isError, true, JSON.stringify(r.result));
let rows = r.result.structuredContent.trades;
assert.ok(rows.length > 0, "the fixture finds trades");
rows.forEach((t, i) => checkSides(t, reference(MINE, GEM, t), `find_trades #${i + 1}`));
assert.match(r.result.content[0].text, /\| their starters [+-]\d+\.\d \|/, "the text shows their starters change");

// (a), (b) and (c), the league.
const OPPS = [
  { name: "Gem Team", roster: GEM.join(", ") },
  { name: "Wide & Co", roster: "Ja'Marr Chase, Keyed Player, DJ Moore" },
  { name: "Ghosts", roster: "Nobody Atall" },
];
r = await call("find_trades_league", { mine: MINE.join(", "), opponents: OPPS, scoring: "half_ppr", teams: 10 });
assert.notEqual(r.result.isError, true, JSON.stringify(r.result));
const sc = r.result.structuredContent;
const rosterOf = { "Gem Team": GEM, "Wide & Co": ["Ja'Marr Chase", "Keyed Player", "DJ Moore"] };
assert.ok(sc.trades.length > 0, "the league scan finds trades");
sc.trades.forEach((t, i) => checkSides(t, reference(MINE, rosterOf[t.team], t), `league #${i + 1} vs ${t.team}`));
sc.package.offers.forEach((t, i) => checkSides(t, reference(MINE, rosterOf[t.team], t), `package #${i + 1}`));
assert.match(r.result.content[0].text, /vs Gem Team give .*\| their starters [+-]\d+\.\d \|/);

const url = sc.site_url;
assert.ok(url.startsWith(`${ORIGIN}/#find-league?workspace=`), `league link opens the league finder: ${url}`);
assert.ok(r.result.content[0].text.includes(url), "the text carries the same link");
const hash = url.slice(ORIGIN.length + 1);
// Read it the way league.js readShareHash does: the raw text up to the next &, then decodeShare.
const text = hash.slice(hash.indexOf("workspace=") + "workspace=".length).split("&")[0];
const byKey = new Map(players.map((p) => [String(p.player_key), { name: p.name, pos: p.pos }]));
const teams = W.decodeShare(text, byKey);
assert.deepEqual(teams.map((t) => t.name), ["My team", "Gem Team", "Wide & Co", "Ghosts"], "every team, yours first, in order");
const keysOf = (names) => names.map((n) => String(byName.get(n).player_key));
assert.deepEqual(teams[0].entries.map((e) => e.key), keysOf(MINE), "your roster");
assert.deepEqual(teams[1].entries.map((e) => e.key), keysOf(GEM), "Gem Team's roster");
assert.deepEqual(teams[2].entries.map((e) => e.key), keysOf(rosterOf["Wide & Co"]), "Wide & Co's roster, a 5-digit key included");
assert.deepEqual(teams[3].entries, [], "a team with no matched player still travels, with no players");
assert.ok(teams.every((t) => t.entries.every((e) => !e.unknown)), "every key resolves on the site");
const params = new URLSearchParams(hash.slice(hash.indexOf("?") + 1));
assert.equal(params.get("wm"), "0", "team 0 is marked as yours");
assert.equal(params.get("scoring"), "half_ppr", "the league's scoring travels");
assert.equal(params.get("teams"), "10", "the league's team count travels");
assert.equal(params.has("mine"), false, "no finder work lists in the league link");
// The shared encoder equals the site's own encodeShare for the same league.
const ws = { myTeamId: "a", teams: teams.map((t, i) => ({ id: i ? `b${i}` : "a", name: t.name, entries: t.entries })) };
assert.equal(leagueShareText(teams.map((t) => ({ name: t.name, keys: t.entries.map((e) => e.key) }))), W.encodeShare(ws).text,
  "leagueShareText writes what workspace.js encodeShare writes");
assert.equal(leagueShareText([{ name: "A", keys: ["sl:42"] }]), "A:~sl%3A42", "a non-numeric key is ~ and percent-encoded");
// The DDF state for read_state still carries your roster as before.
assert.deepEqual(sc.state.work.mine.map((e) => e.key), keysOf(MINE));

// find_trades keeps its two-roster finder link.
r = await call("find_trades", { mine: MINE.join(", "), theirs: GEM.join(", ") });
assert.ok(r.result.structuredContent.site_url.startsWith(`${ORIGIN}/#find-trade?`));

// (d) an older get-values with no bench_share: no fit, so no sides.
const noReadout = async (...a) => { const { bench_share, ...rest } = await charts(...a); return rest; };
r = await call("find_trades", { mine: MINE.join(", "), theirs: GEM.join(", ") }, noReadout);
rows = r.result.structuredContent.trades;
assert.ok(rows.length > 0 && rows.every((t) => t.yours === undefined && t.theirs === undefined), "no fit context, no sides");
assert.doesNotMatch(r.result.content[0].text, /their starters/);

console.log("ok");
