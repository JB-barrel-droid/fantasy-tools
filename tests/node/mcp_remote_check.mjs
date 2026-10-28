// JEG-1012: exercises the remote MCP dispatch and tool logic with a stub
// get-values, so it needs no network. Run by tests/test_mcp_remote.py.
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { handleRpc } from "../../supabase/functions/mcp/rpc.ts";
import { MCP_BUILD_SHA } from "../../supabase/functions/mcp/build.ts";
import { checkTradeReplySize, ToolInputError } from "../../supabase/functions/mcp/tools.ts";
import { evalFinder } from "../../supabase/functions/mcp/find-trades.ts";
import { readFileSync } from "node:fs";
const codec = createRequire(import.meta.url)("../../app/v2/ddf-state.js");
const ORIGIN = "https://site.test";
const deps = { codec, siteOrigin: ORIGIN };

const players = [
  { player_key: 1, name: "Bijan Robinson", pos: "RB", value: 71.8, tier: "starter" },
  { player_key: 2, name: "Ja'Marr Chase", pos: "WR", value: 70.2, tier: "starter" },
  { player_key: 3, name: "Josh Allen", pos: "QB", value: 40, tier: "starter" },
  { player_key: 4, name: "Josh Jacobs", pos: "RB", value: 39, tier: "starter" },
  { player_key: 5, name: "Zero Guy", pos: "TE", value: 0, tier: "waiver" },
  { player_key: 6, name: "Amon-Ra St. Brown", pos: "WR", value: 55, tier: "starter" },
  { player_key: 7, name: "Brian Thomas Jr.", pos: "WR", value: 33, tier: "starter" },
  { player_key: 8, name: "Keenan Allen", pos: "WR", value: 22, tier: "starter" },
  { player_key: 9, name: "DJ Moore", pos: "WR", value: 28, tier: "starter" },
];
let calls = [];
let leagues = [];
const stub = async (scoring, teams, superflex, league) => {
  calls.push([scoring, teams, superflex]);
  leagues.push(league);
  return {
    attribution: "Data Driven Football", as_of: "2026-10-24",
    setting: { scoring, teams, superflex }, players,
    sources_included: ["espn"], sources_excluded: [],
  };
};
const rpc = (method, params, id = 1) => handleRpc({ jsonrpc: "2.0", id, method, params }, stub);
const call = (name, args) => rpc("tools/call", { name, arguments: args });

let r = await rpc("initialize", { protocolVersion: "2025-06-18" });
assert.equal(r.result.protocolVersion, "2025-06-18");
assert.ok(r.result.capabilities.tools);
assert.equal(r.result.serverInfo.version, "1.2.0");
assert.equal(r.result.serverInfo.build, MCP_BUILD_SHA);
assert.match(r.result.serverInfo.build, /^[0-9a-f]{40}$/);
r = await rpc("initialize", { protocolVersion: "1999-01-01" });
assert.equal(r.result.protocolVersion, "2025-06-18");

assert.equal(await handleRpc({ jsonrpc: "2.0", method: "notifications/initialized" }, stub), null);
assert.deepEqual((await rpc("ping")).result, {});
r = await rpc("tools/list");
assert.deepEqual(r.result.tools.map((t) => t.name),
  ["get_values", "get_player_value", "trade_targets", "compare_trade", "read_state", "make_state", "find_trades", "find_trades_league", "explain"]);
assert.ok(r.result.tools.every((t) => t.inputSchema.type === "object" && !/0-70/.test(t.description)));
assert.equal((await rpc("nope")).error.code, -32601);
assert.equal((await handleRpc({ foo: 1 }, stub)).error.code, -32600);

// get_values: position filter, limit, structured output, settings forwarded.
r = await call("get_values", { scoring: "half_ppr", teams: 10, superflex: true, position: "RB", limit: 1 });
assert.deepEqual(calls.at(-1), ["half_ppr", 10, 1]);
assert.deepEqual(r.result.structuredContent.players.map((p) => p.name), ["Bijan Robinson"]);

// Names: apostrophes, partial matches; a 0 value is shown as 0, not dropped.
r = await call("get_player_value", { names: "jamarr chase, zero guy, nobody" });
const res = r.result.structuredContent.results;
assert.equal(res[0].player.name, "Ja'Marr Chase");
assert.equal(res[1].player.value, 0);
assert.equal(res[2].player, null);
assert.match(r.result.content[0].text, /nobody: NOT FOUND/);

// A shared first name is ambiguous. It is not given to the best-valued player.
r = await call("get_player_value", { names: "josh" });
assert.equal(r.result.structuredContent.results[0].player, null);
assert.equal(r.result.structuredContent.results[0].match, "ambiguous");
assert.match(r.result.content[0].text, /AMBIGUOUS/);
assert.match(r.result.content[0].text, /Josh Allen/);
assert.match(r.result.content[0].text, /Josh Jacobs/);

r = await call("trade_targets", { player_name: "Josh Allen", range_pct: 10 });
assert.deepEqual(r.result.structuredContent.targets.map((t) => t.name), ["Josh Jacobs"]);
r = await call("trade_targets", { player_name: "Nobody" });
assert.equal(r.result.isError, true);

// compare_trade: verdict direction and missing names.
r = await call("compare_trade", { side_a: "Josh Allen", side_b: "Bijan Robinson" });
const c = r.result.structuredContent;
assert.equal(c.difference, -31.8);
assert.match(c.verdict, /team B gives up more value|team A comes out ahead/);
assert.match(c.verdict, /team A comes out ahead by 31\.8/);
r = await call("compare_trade", { side_a: "Josh Allen", side_b: "Josh Jacobs, Ghost" });
assert.deepEqual(r.result.structuredContent.not_found, ["Ghost"]);
assert.match(r.result.structuredContent.verdict, /roughly even/);

// Bad input is a tool error, not a protocol error.
for (const [name, args] of [["get_values", { scoring: "bad" }], ["get_values", { teams: 11 }],
  ["get_values", { position: "K" }], ["explain", { topic: "x" }], ["nope", {}],
  ["compare_trade", { side_a: "", side_b: "x" }]]) {
  const e = await call(name, args);
  assert.equal(e.result.isError, true, name + JSON.stringify(args));
}
r = await call("explain", { topic: "value_scale" });
assert.doesNotMatch(r.result.content[0].text, /0-70/);

// An upstream failure surfaces as a tool error without leaking details.
const down = await handleRpc({ jsonrpc: "2.0", id: 9, method: "tools/call", params: { name: "get_values", arguments: {} } },
  async () => { throw new Error("get-values 500 secret"); });
assert.equal(down.result.isError, true);
assert.doesNotMatch(down.result.content[0].text, /secret/);
// ---------- JEG-1027: state in and out, links back to the site ----------
const callD = (name, args, d = deps) => handleRpc({ jsonrpc: "2.0", id: 1, method: "tools/call", params: { name, arguments: args } }, stub, d);

// Without deps the tools behave as before: no link.
r = await call("get_values", { limit: 1 });
assert.doesNotMatch(r.result.content[0].text, /Open this on the site/);

// Every result ends with a link to the exact view, carrying the league used.
r = await callD("get_values", { scoring: "half_ppr", teams: 10, superflex: true, limit: 1 });
let url = r.result.structuredContent.site_url;
assert.ok(url.startsWith(ORIGIN + "/#trade-targets?"), url);
assert.match(r.result.content[0].text, /Open this on the site: https:\/\/site\.test\/#trade-targets\?/);
let back = codec.decodeQuery(url.split("?")[1]).state;
assert.equal(back.league.scoring, "half_ppr");
assert.equal(back.league.teams, 10);
assert.equal(back.league.roster.SUPERFLEX, 1);

// compare_trade: the link is a Compare a trade link; team A gives, team B gets; keys not just names.
r = await callD("compare_trade", { side_a: "Josh Allen", side_b: "Bijan Robinson, Ghost" });
url = r.result.structuredContent.site_url;
assert.ok(url.startsWith(ORIGIN + "/#compare-trade?"));
back = codec.decodeQuery(url.split("?")[1]).state;
assert.deepEqual(back.work.give, [{ key: "3" }]);
assert.deepEqual(back.work.get, [{ key: "1" }, { name: "Ghost" }]);

// Trade targets links the target player.
r = await callD("trade_targets", { player_name: "Josh Allen" });
back = codec.decodeQuery(r.result.structuredContent.site_url.split("?")[1]).state;
assert.deepEqual(back.work.target, { key: "3" });

// A pasted state supplies the league; explicit arguments win; the call prices that league.
const pasted = codec.encodeBlock({ league: { scoring: "standard", teams: 8, roster: { SUPERFLEX: 1 } }, work: { give: [{ key: "3" }] } });
await callD("get_values", { state: pasted, limit: 1 });
assert.deepEqual(calls.at(-1), ["standard", 8, 1]);
await callD("get_values", { state: pasted, scoring: "ppr", limit: 1 });
assert.deepEqual(calls.at(-1), ["ppr", 8, 1]);

// JEG-1031: a league with shares is sent to the endpoint, not noted as unpriced.
const custom = codec.encodeBlock({ league: { scoring: "ppr", teams: 12, shares: { QB: 0.2, RB: 0.35, WR: 0.35, TE: 0.1 } } });
r = await callD("get_values", { state: custom, limit: 1 });
assert.doesNotMatch(r.result.content[0].text, /not applied here/);
assert.deepEqual(leagues.at(-1), { shares: { QB: 0.2, RB: 0.35, WR: 0.35, TE: 0.1 } });
assert.equal((await callD("get_values", { limit: 1 })).result.content[0].text.includes("not applied here"), false);

// Work carried in a state survives a tool call that does not touch it.
const carried = codec.encodeBlock({ league: { scoring: "ppr" }, work: { mine: [{ key: "1" }, { key: "2" }], theirs: [{ key: "3" }] } });
r = await callD("get_values", { state: carried, limit: 1 });
assert.deepEqual(r.result.structuredContent.state.work.mine, [{ key: "1" }, { key: "2" }]);

// If the codec cannot be loaded, tools still answer and say the state was not read.
r = await callD("get_values", { state: pasted, limit: 1 }, { codec: null, siteOrigin: ORIGIN });
assert.notEqual(r.result.isError, true);
assert.match(r.result.content[0].text, /state reader is unavailable/);
r = await callD("read_state", { state: pasted }, { codec: null, siteOrigin: ORIGIN });
assert.equal(r.result.isError, true);

// read_state: resolves keys and names, totals each list, lists what it could not match.
const work = codec.encodeBlock({ league: { scoring: "ppr", teams: 12 },
  work: { give: [{ key: "3" }, { name: "jamarr chase" }], get: [{ name: "Nobody" }], target: { name: "Zero Guy" } } });
r = await callD("read_state", { state: work });
const sc = r.result.structuredContent;
assert.deepEqual(sc.unmatched, ["Nobody"]);
assert.equal(sc.lists.give[1].player.name, "Ja'Marr Chase");
assert.match(r.result.content[0].text, /give \(total 110\.2\)/);
assert.match(r.result.content[0].text, /target: Zero Guy \(TE\): 0/);
assert.deepEqual(sc.state.work.give, [{ key: "3", name: "Josh Allen" }, { key: "2", name: "Ja'Marr Chase" }]);
assert.ok(sc.site_url.startsWith(ORIGIN + "/#compare-trade?"), "view inferred from give/get");
for (const bad of ["", "no state here"]) {
  r = await callD("read_state", { state: bad });
  assert.equal(r.result.isError, true, JSON.stringify(bad));
}

// make_state: names in, a pasteable block and a link out; the block reads back to the same work.
r = await callD("make_state", { scoring: "ppr", teams: 12, mine: "Josh Allen, Josh Jacobs", theirs: "Bijan Robinson, Ghost" });
const text = r.result.content[0].text;
assert.match(text, /```ddf-state/);
assert.match(text, /Could not match: Ghost/);
const readBack = codec.decodeBlock(text).state;
assert.deepEqual(readBack.work.mine, [{ key: "3", name: "Josh Allen" }, { key: "4", name: "Josh Jacobs" }]);
assert.deepEqual(readBack.work.theirs, [{ key: "1", name: "Bijan Robinson" }, { name: "Ghost" }]);
assert.equal(readBack.work.view, "finder");
assert.ok(r.result.structuredContent.site_url.startsWith(ORIGIN + "/#find-trade?"));
r = await callD("make_state", { scoring: "ppr" });
assert.equal(r.result.isError, true);

// explain points back to the site without imposing a league.
r = await callD("explain", { topic: "tiers" });
assert.equal(r.result.structuredContent.site_url, ORIGIN + "/");
assert.equal(r.result.structuredContent.state, null);

// The server instructions tell the model to link back and to use the state tools.
const init = await handleRpc({ jsonrpc: "2.0", id: 1, method: "initialize", params: {} }, stub, deps);
assert.match(init.result.instructions, /always include that link/);
assert.match(init.result.instructions, /read_state/);
assert.match(init.result.instructions, /make_state/);
// JEG-1032: the explanations state what the live data shows (tier = starter/bench/waiver, no 0-70 scale).
r = await call("explain", { topic: "tiers" });
let t = r.result.content[0].text;
assert.match(t, /starter/); assert.match(t, /bench/); assert.match(t, /waiver/);
assert.match(t, /not a quality band/);
assert.doesNotMatch(t, /similar value/);
r = await call("explain", { topic: "value_scale" });
t = r.result.content[0].text;
assert.doesNotMatch(t, /around 70|45\+|30-45|15-30/);
assert.match(t, /no fixed maximum/);
r = await call("explain", { topic: "how_to_trade" });
assert.match(r.result.content[0].text, /rule of thumb/);
// JEG-1033 / JEG-1031: a pasted league is priced by the endpoint, so no "numbers can differ" note, and the
// settings beyond scoring/teams/superflex go to get-values as `league`.
const sfOnly = codec.encodeBlock({ league: { scoring: "ppr", teams: 12, roster: { SUPERFLEX: 1 } } });
r = await callD("get_values", { state: sfOnly, limit: 1 });
assert.doesNotMatch(r.result.content[0].text, /not applied here|default lineup/);
assert.equal(leagues.at(-1), undefined);
const ms = await callD("make_state", { scoring: "ppr", superflex: true, mine: "Josh Allen" });
r = await callD("read_state", { state: ms.result.content[0].text });
assert.doesNotMatch(r.result.content[0].text, /not applied here|default lineup/);
const customLeague = { scoring: "ppr", teams: 12, roster: { QB: 1, RB: 2, WR: 3, TE: 1, FLEX: 1, SUPERFLEX: 1, BENCH: 6 },
  shares: { QB: 0.2, RB: 0.4, WR: 0.3, TE: 0.1 }, bso: 0.2, inj: "all", conf: 1.5, weeks: { regend: 13, playoffs: [14, 16] } };
r = await callD("get_values", { state: codec.encodeBlock({ league: customLeague }), limit: 1 });
assert.doesNotMatch(r.result.content[0].text, /not applied here|default lineup/);
assert.deepEqual(calls.at(-1), ["ppr", 12, 1]);
assert.deepEqual(leagues.at(-1), { roster: { QB: 1, RB: 2, WR: 3, TE: 1, FLEX: 1, BENCH: 6 },
  shares: customLeague.shares, bso: 0.2, inj: "all", conf: 1.5, weeks: customLeague.weeks });
// An explicit argument still wins over the pasted state for the top-level settings.
r = await callD("get_values", { state: codec.encodeBlock({ league: customLeague }), superflex: false, limit: 1 });
assert.deepEqual(calls.at(-1), ["ppr", 12, 0]);
// JEG-1029 (interim): the chat verdict says what it is, so it is not mistaken for the site's lineup-aware view.
r = await call("compare_trade", { side_a: "Josh Allen", side_b: "Bijan Robinson" });
assert.match(r.result.content[0].text, /DDF Value sum, not lineup-aware/);
assert.match(r.result.content[0].text, /per-chart breakdown/);
assert.equal(r.result.structuredContent.method, "sum_of_ddf_values");
assert.match((await rpc("tools/list")).result.tools.find((t) => t.name === "compare_trade").description, /not lineup-aware/);

// ---------- find_trades tool ----------
const finder = createRequire(import.meta.url)("../../app/v2/finder.js");

// Chart-enriched stub: adds chart_values (Adjusted), chart_indexed (Indexed) and DDF sub-versions to each player.
const chartPlayers = [
  { player_key: 1, name: "Bijan Robinson", pos: "RB", value: 71.8, tier: "starter",
    chart_values: { usatoday: 65, fantasycalc: 68, fantasypros: 70, cbs: 66 },
    chart_indexed: { usatoday: 65, fantasycalc: 68, fantasypros: 70, cbs: 66 },
    ddf_value_charts: 72, ddf_value_projections: 71.5 },
  { player_key: 2, name: "Ja'Marr Chase", pos: "WR", value: 70.2, tier: "starter",
    chart_values: { usatoday: 64, fantasycalc: 67, fantasypros: 69, cbs: 65 },
    chart_indexed: { usatoday: 64, fantasycalc: 67, fantasypros: 69, cbs: 65 },
    ddf_value_charts: 70, ddf_value_projections: 70.5 },
  { player_key: 3, name: "Josh Allen", pos: "QB", value: 40, tier: "starter",
    chart_values: { usatoday: 35, fantasycalc: 38, fantasypros: 42, cbs: 36 },
    chart_indexed: { usatoday: 35, fantasycalc: 38, fantasypros: 42, cbs: 36 },
    ddf_value_charts: 41, ddf_value_projections: 39 },
  { player_key: 4, name: "Josh Jacobs", pos: "RB", value: 39, tier: "starter",
    chart_values: { usatoday: 34, fantasycalc: 37, fantasypros: 41, cbs: 35 },
    chart_indexed: { usatoday: 34, fantasycalc: 37, fantasypros: 41, cbs: 35 },
    ddf_value_charts: 40, ddf_value_projections: 38 },
  { player_key: 5, name: "Zero Guy", pos: "TE", value: 0, tier: "waiver",
    chart_values: { usatoday: 0, fantasycalc: 0, fantasypros: 0, cbs: 0 },
    chart_indexed: { usatoday: 0, fantasycalc: 0, fantasypros: 0, cbs: 0 },
    ddf_value_charts: 0, ddf_value_projections: 0 },
  // JEG-1115: a player the trade charts price far below DDF Value, so a trade exists
  // (you gain on DDF Value, the charts say the rival breaks even or wins).
  { player_key: 6, name: "Chart Gem", pos: "RB", value: 45, tier: "starter",
    chart_values: { usatoday: 45, fantasycalc: 45, fantasypros: 45, cbs: 45 },
    chart_indexed: { usatoday: 10, fantasycalc: 11, fantasypros: 9, cbs: 10 },
    ddf_value_charts: 45, ddf_value_projections: 45 },
];
const chartStub = async (scoring, teams, superflex) => ({
  attribution: "Data Driven Football", as_of: "2026-10-24",
  setting: { scoring, teams, superflex }, players: chartPlayers,
  sources_included: ["espn", "usatoday", "fantasycalc", "fantasypros", "cbs"], sources_excluded: [],
  // JEG-1115: the engine's bench-share readout, the fit rule's bench weights.
  bench_share: { QB: 0.2, RB: 0.3, WR: 0.3, TE: 0.25, overall: 0.28, input: 0.15 },
});
const finderDeps = { finder, fetchCharts: chartStub };
const callF = (name, args) => handleRpc(
  { jsonrpc: "2.0", id: 1, method: "tools/call", params: { name, arguments: args } },
  stub, deps, finderDeps);

// find_trades: basic search between two rosters.
r = await callF("find_trades", { mine: "Josh Allen, Josh Jacobs", theirs: "Bijan Robinson, Ja'Marr Chase" });
assert.notEqual(r.result.isError, true, "find_trades should not error: " + JSON.stringify(r.result));
const ft = r.result.structuredContent;
assert.ok(ft.total >= 0, "total trades is a number");
assert.ok(Array.isArray(ft.trades), "trades is an array");
assert.ok(r.result.content[0].text.includes("Data Driven Football"), "text includes attribution");
assert.ok(r.result.content[0].text.includes("Open this on the site"), "text includes site link");
assert.ok(ft.mine.searched > 0, "mine searched > 0");
assert.ok(ft.theirs.searched > 0, "theirs searched > 0");

// If trades are found, each has the viability-scored shape.
if (ft.trades.length > 0) {
  const first = ft.trades[0];
  assert.ok(Array.isArray(first.userGives) && first.userGives.length > 0, "userGives is a non-empty array");
  assert.ok(Array.isArray(first.userGets) && first.userGets.length > 0, "userGets is a non-empty array");
  assert.equal(typeof first.ddfEdge, "number", "ddfEdge is a number");
  assert.equal(typeof first.viable, "boolean", "viable is a boolean");
  assert.equal(first.checks, undefined, "compact trades omit the nine check writeups");
  assert.ok(Array.isArray(first.failed), "failed check names are a short list");
  assert.equal(typeof first.lineup, "number");
  assert.ok(first.ddfEdge > 0, "your edge is positive (you gain)");
  if (first.viable) {
    assert.ok(["High", "Med-High", "Medium"].includes(first.label), "viable offer has a label");
  }
}

// JEG-1115: every returned trade carries the finder's fit label and reason, in the text too.
// Chart Gem is cheap on the charts and dear on DDF Value, so trades exist.
{
  r = await callF("find_trades", { mine: "Josh Allen, Josh Jacobs", theirs: "Chart Gem, Bijan Robinson" });
  assert.notEqual(r.result.isError, true, JSON.stringify(r.result));
  const trades = r.result.structuredContent.trades;
  assert.ok(trades.length > 0, "the fit fixture finds trades");
  for (const t of trades) {
    assert.ok(["Natural", "Market supported", "Force"].includes(t.fit), "trade has a fit label: " + JSON.stringify(t));
    assert.equal(typeof t.fitReason, "string", "trade has a fit reason");
    assert.ok(t.fitReason.startsWith(t.fit === "Market supported" ? "Market supported" : `${t.fit} fit`), "the reason names the label: " + t.fitReason);
  }
  assert.match(r.result.content[0].text, /\n   (Natural fit|Market supported|Force fit): /, "the text shows the fit and its reason");
  r = await callF("find_trades_league", { mine: "Josh Allen, Josh Jacobs", opponents: [{ name: "Gem Team", roster: "Chart Gem, Bijan Robinson" }] });
  assert.notEqual(r.result.isError, true, JSON.stringify(r.result));
  const lt = r.result.structuredContent.trades;
  assert.ok(lt.length > 0 && lt.every((t) => ["Natural", "Market supported", "Force"].includes(t.fit)), "league trades carry the fit: " + JSON.stringify(lt));
  for (const o of r.result.structuredContent.package.offers) assert.ok(o.fit, "package offers carry the fit");
  // An older get-values with no bench_share readout: the fit is left out, never approximated.
  const noReadout = async (scoring, teams, superflex) => { const { bench_share, ...rest } = await chartStub(scoring, teams, superflex); return rest; };
  r = await handleRpc({ jsonrpc: "2.0", id: 1, method: "tools/call", params: { name: "find_trades",
    arguments: { mine: "Josh Allen, Josh Jacobs", theirs: "Chart Gem, Bijan Robinson" } } }, stub, deps, { finder, fetchCharts: noReadout });
  assert.notEqual(r.result.isError, true);
  assert.ok(r.result.structuredContent.trades.length > 0 && r.result.structuredContent.trades.every((t) => t.fit === undefined), "no readout, no fit");
}

// JEG-1129: the other team is judged on the trade charts' Indexed values (chart_indexed), never on
// the Adjusted values (chart_values), whose mean is DDF Value itself. Here the Adjusted values mirror
// DDF Value, as they do live, so the old rows gave theirMarketNet = -ddfEdge and nothing could pass.
{
  const ch = (v) => ({ usatoday: v, fantasycalc: v, fantasypros: v, cbs: v });
  const arb = [
    { player_key: 11, name: "Market Darling", pos: "RB", value: 30, tier: "starter", chart_values: ch(30), chart_indexed: ch(40),
      ddf_value_charts: 30, ddf_value_projections: 30 },
    { player_key: 12, name: "Market Laggard", pos: "RB", value: 35, tier: "starter", chart_values: ch(35), chart_indexed: ch(32),
      ddf_value_charts: 35, ddf_value_projections: 35 },
  ];
  const arbCharts = async (scoring, teams, superflex) => ({ ...(await chartStub(scoring, teams, superflex)), players: arb });
  const callA = (args) => handleRpc({ jsonrpc: "2.0", id: 1, method: "tools/call", params: { name: "find_trades", arguments: args } },
    stub, deps, { finder, fetchCharts: arbCharts });
  r = await callA({ mine: "Market Darling", theirs: "Market Laggard", max_per_side: 1 });
  assert.notEqual(r.result.isError, true, JSON.stringify(r.result));
  const t = r.result.structuredContent.trades.find((x) => x.userGives[0].name === "Market Darling");
  assert.ok(t, "the arbitrage trade is found: " + JSON.stringify(r.result.structuredContent.trades));
  assert.ok(Math.abs(t.ddfEdge - 5) < 1e-9, `you gain 5 on DDF Value, got ${t.ddfEdge}`);
  // The compact reply (JEG-1012) lists only failed checks: they gain 8 on the Indexed chart mean, so the other team's
  // market check passes; on the Adjusted values they would lose 5 and it would fail.
  assert.ok(Array.isArray(t.failed) && !t.failed.includes("perceived_fairness"),
    "the other team's market check passes on the Indexed chart mean: " + JSON.stringify(t));

  // A get-values without Indexed chart values (the old shape) is unavailable, never silently priced on Adjusted.
  const oldShape = arb.map(({ chart_indexed, ...rest }) => rest);
  const oldCharts = async (scoring, teams, superflex) => ({ ...(await chartStub(scoring, teams, superflex)), players: oldShape });
  for (const name of ["find_trades", "find_trades_league"]) {
    const args = name === "find_trades" ? { mine: "Market Darling", theirs: "Market Laggard" }
      : { mine: "Market Darling", opponents: [{ name: "Them", roster: "Market Laggard" }] };
    r = await handleRpc({ jsonrpc: "2.0", id: 1, method: "tools/call", params: { name, arguments: args } }, stub, deps, { finder, fetchCharts: oldCharts });
    assert.equal(r.result.isError, true, `${name} without chart_indexed is an error`);
    assert.match(r.result.content[0].text, /Chart values are unavailable/);
  }
}

// Unmatched names are reported.
r = await callF("find_trades", { mine: "Josh Allen, Ghost", theirs: "Bijan Robinson" });
assert.notEqual(r.result.isError, true);
assert.deepEqual(r.result.structuredContent.mine.unmatched, ["Ghost"]);

// JEG-1070: a pasted custom league reaches the chart fetch for both finder tools, so the
// finder prices the same league as get_values; a default league sends none.
const chartLeagues = [];
const recordingCharts = async (scoring, teams, superflex, league) => {
  chartLeagues.push(league);
  return chartStub(scoring, teams, superflex);
};
const recDeps = { finder, fetchCharts: recordingCharts };
const callR = (name, args) => handleRpc(
  { jsonrpc: "2.0", id: 1, method: "tools/call", params: { name, arguments: args } },
  stub, deps, recDeps);
const finderLeague = { roster: { QB: 1, RB: 2, WR: 3, TE: 1, FLEX: 1, BENCH: 6 }, shares: { QB: 0.2, RB: 0.35, WR: 0.35, TE: 0.1 } };
const finderState = codec.encodeBlock({ league: { scoring: "ppr", teams: 12, ...finderLeague } });
r = await callR("find_trades", { state: finderState, mine: "Josh Allen, Josh Jacobs", theirs: "Bijan Robinson, Ja'Marr Chase" });
assert.notEqual(r.result.isError, true, JSON.stringify(r.result));
assert.deepEqual(chartLeagues.at(-1), finderLeague, "find_trades passes the pasted league to fetchCharts");
r = await callR("find_trades_league", { state: finderState, mine: "Josh Allen, Josh Jacobs",
  opponents: [{ name: "Opp", roster: "Bijan Robinson, Ja'Marr Chase" }] });
assert.notEqual(r.result.isError, true, JSON.stringify(r.result));
assert.deepEqual(chartLeagues.at(-1), finderLeague, "find_trades_league passes the pasted league to fetchCharts");
r = await callR("find_trades", { scoring: "ppr", teams: 12, mine: "Josh Allen", theirs: "Bijan Robinson" });
assert.equal(chartLeagues.at(-1), undefined, "no pasted league sends none");

// Empty roster is an error.
r = await callF("find_trades", { mine: "", theirs: "Bijan Robinson" });
assert.equal(r.result.isError, true);

// Missing finder dependency surfaces as a tool error.
const noFinderDeps = { finder: null, fetchCharts: chartStub };
r = await handleRpc(
  { jsonrpc: "2.0", id: 1, method: "tools/call", params: { name: "find_trades", arguments: { mine: "Josh Allen", theirs: "Bijan Robinson" } } },
  stub, deps, noFinderDeps);
assert.equal(r.result.isError, true);
assert.match(r.result.content[0].text, /unavailable/);

// The site link points to find-trade.
r = await callF("find_trades", { mine: "Josh Allen", theirs: "Bijan Robinson" });
assert.ok(r.result.structuredContent.site_url.includes("#find-trade"), "link points to find-trade view");

// The edge function evals the published finder.js with no DOM. The file publishes TradeValueFinder and then runs
// browser-only page code that throws without a document; the loader must keep the API anyway.
{
  const src = readFileSync(new URL("../../app/v2/finder.js", import.meta.url), "utf8");
  assert.equal(typeof globalThis.document, "undefined", "test runs without a DOM");
  assert.throws(() => (0, eval)(src), /document is not defined/, "the raw eval throws without a DOM");
  delete globalThis.TradeValueFinder;
  const loaded = evalFinder(src, eval);
  assert.equal(typeof loaded?.findTrades, "function", "finder loads despite the browser-only tail");
  assert.equal(evalFinder("throw new Error('boom')", eval, {}), null, "a source that never publishes the API is unavailable");
  delete globalThis.TradeValueFinder;
}

// ---------- compact answers, name matching, validation ----------
const valuesTool = (await rpc("tools/list")).result.tools.find((t) => t.name === "get_values");
assert.match(valuesTool.description, /average of the four adjusted trade charts/);
assert.doesNotMatch(valuesTool.description, /blended across/);

// Typos, hyphens and a suffix comma resolve. A shared name or a bare suffix does not pick one player.
r = await call("get_player_value", { names: "Jamar Chase, Bijan Robinsen, Amon Ra St Brown, Brian Thomas, Jr" });
assert.equal(r.result.isError, undefined);
const named = r.result.structuredContent.results;
assert.equal(named[0].player.name, "Ja'Marr Chase");
assert.equal(named[1].player.name, "Bijan Robinson");
assert.equal(named[2].player.name, "Amon-Ra St. Brown");
assert.equal(named[2].match, "exact");
assert.equal(named[3].player.name, "Brian Thomas Jr.");
r = await call("get_player_value", { names: "Allen" });
assert.equal(r.result.structuredContent.results[0].player, null);
assert.match(r.result.content[0].text, /Keenan Allen/);
assert.match(r.result.content[0].text, /Josh Allen/);
r = await call("get_player_value", { names: "Jr" });
assert.equal(r.result.structuredContent.results[0].player, null);
assert.match(r.result.content[0].text, /Brian Thomas Jr/);

// Bad input is rejected instead of coerced.
for (const [tool, args, needle] of [
  ["get_values", { superflex: "maybe" }, /superflex/],
  ["get_values", { limit: 0 }, /limit/],
  ["get_values", { scoring: "points" }, /scoring/],
  ["trade_targets", { player_name: "" }, /player_name is required/],
  ["trade_targets", { player_name: "   " }, /player_name is required/],
  ["find_trades_league", { mine: "Josh Allen", opponents: "Bijan Robinson" }, /array/],
]) {
  const e = await call(tool, args);
  assert.equal(e.result.isError, true, tool + JSON.stringify(args));
  assert.match(e.result.content[0].text, needle, e.result.content[0].text);
  assert.equal(e.result.content[0].text.split("DDF state").length, 1);
}
r = await call("get_values", { scoring: "PPR", teams: 12, superflex: "yes", limit: 1 });
assert.notEqual(r.result.isError, true, JSON.stringify(r.result));
assert.deepEqual(calls.at(-1), ["ppr", 12, 1]);
r = await call("get_values", { scoring: "0.5ppr", limit: 1 });
assert.deepEqual(calls.at(-1), ["half_ppr", 12, 0]);

// A repeated player is counted once. The same player on both sides stays on team A.
r = await call("compare_trade", { side_a: "Josh Allen, Josh Allen", side_b: "Bijan Robinson" });
assert.equal(r.result.structuredContent.side_a.total, 40);
assert.match(r.result.content[0].text, /counted once/);
r = await call("compare_trade", { side_a: "DJ Moore", side_b: "DJ Moore" });
assert.equal(r.result.isError, true);
assert.match(r.result.content[0].text, /team A only/);

// Identical rosters do not propose a player for himself.
r = await callF("find_trades", { mine: "Josh Allen, Josh Jacobs", theirs: "Josh Allen, Josh Jacobs" });
assert.equal(r.result.isError, true, JSON.stringify(r.result));
assert.match(r.result.content[0].text, /also on yours/);

// A pasted league's roster and shares are in the settings line. A bad paste says so once.
r = await callD("get_values", { state: codec.encodeBlock({ league: customLeague }), limit: 1 });
assert.match(r.result.content[0].text, /roster QB1 RB2 WR3 TE1 FLEX1 BENCH6/);
assert.match(r.result.content[0].text, /shares QB 0\.20 RB 0\.40 WR 0\.30 TE 0\.10/);
r = await callD("read_state", { state: "no state here" });
assert.equal(r.result.isError, true);
assert.equal(r.result.content[0].text.match(/DDF state/gi).length, 1, r.result.content[0].text);

// A name with a space is encoded once in the site link.
r = await callD("make_state", { scoring: "ppr", teams: 12, give: "Josh Allen", get: "Ghost Player" });
assert.match(r.result.structuredContent.site_url, /n:Ghost%20Player/);
assert.doesNotMatch(r.result.structuredContent.site_url, /%2520/);
assert.equal(codec.decodeQuery(r.result.structuredContent.site_url.split("?")[1]).state.work.get[0].name, "Ghost Player");

// Response size. Before this change a 15-for-15 default find_trades was ~23KB for 10 trades,
// get_values limit 200 was ~26KB, and an 11-opponent scan was ~36KB on this fixture (about 212KB
// on a full live scan). The caps below fail if the full viability objects are copied into the payload again.
function sizedPlayer(i, side, pos) {
  const value = side === 1 ? 12 + i : 40 + i;
  const chart = side === 1 ? 70 - i : 20 + i * 0.2;
  const charts = { usatoday: chart, fantasycalc: chart - 1, fantasypros: chart + 1, cbs: chart - 0.5 };
  return {
    player_key: side * 1000 + i, name: `${side === 1 ? "Mine" : "Theirs"} Player ${i}`, pos,
    value: Math.round(value * 10) / 10, tier: "starter", chart_values: charts, chart_indexed: charts,
    ddf_value_charts: chart, ddf_value_projections: value,
  };
}
const sizePos = ["QB", "RB", "RB", "WR", "WR", "WR", "TE", "RB", "WR", "QB", "TE", "RB", "WR", "WR", "RB"];
const sizeMine = sizePos.map((pos, i) => sizedPlayer(i + 1, 1, pos));
const sizeTheirs = sizePos.map((pos, i) => sizedPlayer(i + 1, 2, pos));
const sizeAll = sizeMine.concat(sizeTheirs);
const sizeCharts = async () => ({
  attribution: "Data Driven Football", as_of: "2026-10-26",
  setting: { scoring: "ppr", teams: 12, superflex: 0 }, players: sizeAll,
  sources_included: ["espn", "usatoday", "fantasycalc", "fantasypros", "cbs"], sources_excluded: [],
  bench_share: { QB: 0.2, RB: 0.3, WR: 0.3, TE: 0.25, overall: 0.28, input: 0.15 },
  week: 7, default_week: 7, weeks: [7], missing_sources: [],
});
const sizeCall = (name, args, fetch = sizeCharts) => handleRpc(
  { jsonrpc: "2.0", id: 1, method: "tools/call", params: { name, arguments: args } },
  stub, deps, { finder, fetchCharts: fetch });
const nbytes = (res) => Buffer.byteLength(JSON.stringify(res.result), "utf8");
const mineList = sizeMine.map((p) => p.name).join(", ");
const theirList = sizeTheirs.map((p) => p.name).join(", ");
const sizes = {};
r = await sizeCall("find_trades", { mine: mineList, theirs: theirList });
assert.notEqual(r.result.isError, true, JSON.stringify(r.result).slice(0, 400));
// Jeremy's limits are upper bounds; fit reasons may require a shorter prefix.
assert.ok(r.result.structuredContent.shown >= 1 && r.result.structuredContent.shown <= 10);
assert.equal(r.result.structuredContent.trades.length, r.result.structuredContent.shown);
const defaultFind = r.result;
const assertFitReply = (reply) => {
  const rows = reply.structuredContent.trades;
  assert.ok(rows.length > 0 && rows.every(t => t.fit && typeof t.fitReason === "string" && t.fitReason.length > 0));
  assert.equal(reply.structuredContent.shown, rows.length);
  assert.ok(rows.length <= reply.structuredContent.limit);
  assert.ok((reply.structuredContent.package?.offers ?? []).every(t => t.fit && t.fitReason));
  assert.match(reply.content[0].text, new RegExp(`showing ${rows.length}\\b`));
  assert.ok(reply.content[0].text.includes(reply.structuredContent.site_url));
  const [, candidates = reply.content[0].text] = reply.content[0].text.split("\nCandidates:\n");
  assert.equal(candidates.split("\n").filter(l => /^\d+\. /.test(l)).length, Math.min(5, rows.length));
  if (rows.length > 5) assert.match(candidates, new RegExp(`^${rows.length - 5} more in the structured result`, "m"));
};
assertFitReply(r.result);
sizes.findDefault = nbytes(r);
assert.ok(sizes.findDefault < 6700, `find_trades default ${sizes.findDefault} bytes`);
// The final guard measures the complete UTF-8 result after decorators such as week metadata.
// Pin its exact boundary separately from the ranked-prefix trimming below.
for (const [name, limit, budget] of [["find_trades", 10, 6700], ["find_trades", 50, 17000],
  ["find_trades_league", 10, 8000], ["find_trades_league", 100, 11500]]) {
  const decorated = structuredClone(defaultFind);
  decorated.structuredContent.limit = limit;
  decorated.structuredContent.week_note = "足🏈";
  const padding = budget - Buffer.byteLength(JSON.stringify(decorated), "utf8") - 1;
  decorated.structuredContent.week_note += "x".repeat(padding);
  assert.doesNotThrow(() => checkTradeReplySize(name, decorated));
  decorated.structuredContent.week_note += "x";
  assert.throws(() => checkTradeReplySize(name, decorated), ToolInputError);
}
r = await sizeCall("find_trades", { mine: mineList, theirs: theirList, limit: 50 });
// Jeremy, 2026-10-26: the rewritten finder may yield fewer distinct trades than the limit; accept 1..limit.
const shown50 = r.result.structuredContent.shown;
assert.ok(shown50 >= 1 && shown50 <= 50, `showing ${shown50} of limit 50`);
assert.equal(r.result.structuredContent.trades.length, shown50);
assert.equal(new Set(r.result.structuredContent.trades.map((t) => JSON.stringify(t))).size, shown50, "find_trades limit 50 has duplicates");
assert.match(r.result.content[0].text, new RegExp(`showing ${shown50}\\b`));
assertFitReply(r.result);
assert.deepEqual(defaultFind.structuredContent.trades, r.result.structuredContent.trades.slice(0, defaultFind.structuredContent.shown), "budget trimming preserves rank order");
assert.match(defaultFind.content[0].text, /Fewer candidates shown to keep this reply compact/);
sizes.find50 = nbytes(r);
assert.ok(sizes.find50 < 17000, `find_trades limit 50 ${sizes.find50} bytes`);
const sizeOpps = Array.from({ length: 11 }, (_, i) => ({ name: `Opp ${i + 1}`, roster: theirList }));
r = await sizeCall("find_trades_league", { mine: mineList, opponents: sizeOpps });
assert.notEqual(r.result.isError, true, JSON.stringify(r.result).slice(0, 400));
assert.equal(r.result.structuredContent.limit, 10);
assertFitReply(r.result);
const defaultLeague = r.result;
sizes.league = nbytes(r);
assert.ok(sizes.league < 8000, `find_trades_league ${sizes.league} bytes`);
// The larger league budget still preserves the same entire package and a ranked candidate prefix.
r = await sizeCall("find_trades_league", { mine: mineList, opponents: sizeOpps, limit: 100 });
assertFitReply(r.result);
sizes.league100 = nbytes(r);
assert.ok(sizes.league100 < 11500, `league limit 100 ${sizes.league100} bytes`);
assert.deepEqual(defaultLeague.structuredContent.package, r.result.structuredContent.package);
assert.deepEqual(defaultLeague.structuredContent.trades,
  r.result.structuredContent.trades.slice(0, defaultLeague.structuredContent.shown));

// UTF-8 bytes (not JS code units), and an irreducible state/package must give a small error.
const unicodeMine = sizeMine.map(p => ({ ...p, name: `${p.name} 足🏈` }));
const unicodeCharts = async () => ({ ...await sizeCharts(), players: unicodeMine.concat(sizeTheirs) });
r = await sizeCall("find_trades", { mine: unicodeMine.map(p => p.name).join(", "), theirs: theirList }, unicodeCharts);
assertFitReply(r.result);
assert.ok(nbytes(r) < 6700);
r = await sizeCall("find_trades_league", { mine: mineList,
  opponents: [{ name: "足🏈".repeat(1800), roster: theirList }], limit: 1 });
assert.equal(r.result.isError, true);
assert.match(r.result.content[0].text, /reply is too large/);
assert.ok(nbytes(r) < 300, "size errors never echo the oversized input");

// Two display names may coincide. Fit must still use the right roster, and package team
// identity must not collapse distinct opponents. Original index travels with every row.
const extraPlayer = { ...sizeTheirs[0], player_key: 9001, name: "Third Roster QB" };
const duplicateCharts = async () => ({ ...await sizeCharts(), players: [...sizeAll, extraPlayer] });
const scan = async (opponents) => (await sizeCall("find_trades_league", { mine: mineList, opponents, limit: 100 }, duplicateCharts)).result;
const original = await scan([{ name: "Same", roster: theirList }]);
const duplicate = await scan([{ name: "Same", roster: theirList }, { name: "Same", roster: extraPlayer.name }]);
const renamed = await scan([{ name: "First", roster: theirList }, { name: "Second", roster: extraPlayer.name }]);
const reordered = await scan([{ name: "Same", roster: extraPlayer.name }, { name: "Same", roster: theirList }]);
const tradeKey = t => JSON.stringify([t.userGives, t.userGets]);
const originals = new Map(original.structuredContent.trades.map(t => [tradeKey(t), t]));
for (const [reply, index] of [[duplicate, 0], [renamed, 0], [reordered, 1]]) {
  assert.notEqual(reply.isError, true);
  const comparable = reply.structuredContent.trades.filter(t => t.opponent_index === index && originals.has(tradeKey(t)));
  assert.ok(comparable.length > 0, "duplicate-name regression compares real trades");
  for (const t of comparable) {
    assert.equal(t.fit, originals.get(tradeKey(t)).fit);
    assert.equal(t.fitReason, originals.get(tradeKey(t)).fitReason);
  }
  assert.ok(reply.structuredContent.package.offers.every(t => Number.isInteger(t.opponent_index)));
  assert.equal(new Set(reply.structuredContent.package.offers.map(t => t.opponent_index)).size,
    reply.structuredContent.package.offers.length, "at most one package trade per input opponent");
}
assert.deepEqual(duplicate.structuredContent.perOpponent.map(t => [t.name, t.opponent_index]), [["Same", 0], ["Same", 1]]);
assert.ok(duplicate.structuredContent.trades.every(t => t.team === "Same"));

// Force one distinct candidate per opponent through the real viability/package and fit rules.
// Both are valid offers; equal display names must not turn the second into the same team.
const otherTeam = sizeTheirs.map(p => ({ ...p, player_key: p.player_key + 1000, name: p.name.replace("Theirs", "Other") }));
const packageCharts = async () => ({ ...await sizeCharts(), players: [...sizeAll, ...otherTeam] });
const pairFinder = { ...finder, findTrades: (mine, theirs) => {
  const second = theirs[0].player_key >= 3000;
  const give = [mine[second ? 3 : 1]], receive = [theirs[second ? 13 : 14]];
  const count = { searched: 15, of: 15, unpriced: 0 };
  return { trades: [{ give, receive, edge: 40, score: 40, rivalOkCount: 4, pricedCharts: 4, charts: [] }],
    total: 1, mine: count, theirs: count, chartKeys: finder.CHART_KEYS };
} };
r = await handleRpc({ jsonrpc: "2.0", id: 1, method: "tools/call", params: {
  name: "find_trades_league", arguments: { mine: mineList, limit: 100,
    opponents: [{ name: "Same", roster: theirList }, { name: "Same", roster: otherTeam.map(p => p.name).join(", ") }] }
} }, stub, deps, { finder: pairFinder, fetchCharts: packageCharts });
assert.notEqual(r.result.isError, true);
assert.deepEqual(r.result.structuredContent.package.offers.map(t => t.opponent_index).sort(), [0, 1],
  "equal display names keep both distinct teams in the package");
assert.ok(r.result.structuredContent.package.offers.every(t => t.team === "Same" && t.fit && t.fitReason));

const board = Array.from({ length: 200 }, (_, i) => ({
  player_key: i + 1, name: `Player Number ${i + 1}`, pos: "WR",
  value: Math.round((200 - i) * 0.4 * 10) / 10, tier: i < 80 ? "starter" : "bench",
}));
r = await handleRpc(
  { jsonrpc: "2.0", id: 1, method: "tools/call", params: { name: "get_values", arguments: { limit: 200 } } },
  async () => ({ attribution: "Data Driven Football", as_of: "2026-10-26", setting: { scoring: "ppr", teams: 12, superflex: 0 }, players: board, sources_included: ["espn"], sources_excluded: [] }),
  deps);
assert.equal(r.result.structuredContent.players.length, 200);
sizes.values200 = nbytes(r);
assert.ok(sizes.values200 < 24000, `get_values 200 ${sizes.values200} bytes`);
console.log("sizes", sizes);

console.log("ok");
