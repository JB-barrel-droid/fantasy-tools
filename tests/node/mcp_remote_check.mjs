// JEG-1012: exercises the remote MCP dispatch and tool logic with a stub
// get-values, so it needs no network. Run by tests/test_mcp_remote.py.
import assert from "node:assert/strict";
import { handleRpc } from "../../supabase/functions/mcp/rpc.ts";

const players = [
  { player_key: 1, name: "Bijan Robinson", pos: "RB", value: 71.8, tier: 1 },
  { player_key: 2, name: "Ja'Marr Chase", pos: "WR", value: 70.2, tier: 1 },
  { player_key: 3, name: "Josh Allen", pos: "QB", value: 40, tier: 3 },
  { player_key: 4, name: "Josh Jacobs", pos: "RB", value: 39, tier: 3 },
  { player_key: 5, name: "Zero Guy", pos: "TE", value: 0, tier: 9 },
];
let calls = [];
const stub = async (scoring, teams, superflex) => {
  calls.push([scoring, teams, superflex]);
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
r = await rpc("initialize", { protocolVersion: "1999-01-01" });
assert.equal(r.result.protocolVersion, "2025-06-18");

assert.equal(await handleRpc({ jsonrpc: "2.0", method: "notifications/initialized" }, stub), null);
assert.deepEqual((await rpc("ping")).result, {});
r = await rpc("tools/list");
assert.deepEqual(r.result.tools.map((t) => t.name),
  ["get_values", "get_player_value", "trade_targets", "compare_trade", "explain"]);
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

// Partial match picks the best-valued candidate, exact wins over partial.
r = await call("get_player_value", { names: "josh" });
assert.equal(r.result.structuredContent.results[0].player.name, "Josh Allen");

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
console.log("ok");
