// JEG-1376: a player name that matches nobody must never be scored as 0 and still get a verdict,
// in compare_trade or read_state. Uses the ticket's own example ("Gibbs" vs "Hubbard, Zzyzx
// Notaplayer", which once returned "team B ahead by 35.6") under all three scorings. Stub
// get-values, no network. Run by tests/test_mcp_remote.py.
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { handleRpc } from "../../supabase/functions/mcp/rpc.ts";
const codec = createRequire(import.meta.url)("../../app/v2/ddf-state.js");
const deps = { codec, siteOrigin: "https://site.test" };

const players = [
  { player_key: 11, name: "Jahmyr Gibbs", pos: "RB", value: 62.4, tier: "starter" },
  { player_key: 12, name: "Chuba Hubbard", pos: "RB", value: 27.0, tier: "starter" },
  { player_key: 13, name: "Tylan Wallace", pos: "WR", value: 3.1, tier: "waiver" },
  { player_key: 14, name: "Kenneth Walker III", pos: "RB", value: 30.2, tier: "starter" },
  { player_key: 15, name: "Josh Palmer", pos: "WR", value: 6.5, tier: "bench" },
  { player_key: 16, name: "Josh Allen", pos: "QB", value: 40.0, tier: "starter" },
];
const stub = async (scoring, teams, superflex) => ({
  attribution: "Data Driven Football", as_of: "2026-10-24",
  setting: { scoring, teams, superflex }, players,
  sources_included: ["espn"], sources_excluded: [],
});
const call = (name, args) =>
  handleRpc({ jsonrpc: "2.0", id: 1, method: "tools/call", params: { name, arguments: args } }, stub, deps);
const VERDICT = /ahead by|Verdict|even trade|wins? the trade/i;

for (const scoring of ["standard", "half_ppr", "ppr"]) {
  // compare_trade: no verdict, and the reply names the unmatched player.
  let r = await call("compare_trade", { scoring, side_a: "Gibbs", side_b: "Hubbard, Zzyzx Notaplayer" });
  let text = r.result.content[0].text;
  assert.equal(r.result.isError, true, `${scoring} compare_trade: ${text}`);
  assert.doesNotMatch(text, VERDICT, `${scoring} compare_trade gave a verdict`);
  assert.match(text, /"Zzyzx Notaplayer" matches no player; closest: [A-Z]/);
  assert.match(text, /Ask the user which player they meant/);
  assert.equal(r.result.structuredContent?.verdict, undefined);

  // read_state: the same trade carried in a pasted state. The list with the unmatched name gives
  // no total (so no side can be read as ahead), and the reply names that player with its closest names.
  const state = codec.encodeBlock({ league: { scoring, teams: 12 },
    work: { give: [{ name: "Gibbs" }], get: [{ name: "Hubbard" }, { name: "Zzyzx Notaplayer" }] } });
  r = await call("read_state", { state });
  text = r.result.content[0].text;
  const sc = r.result.structuredContent;
  assert.notEqual(r.result.isError, true, `${scoring} read_state: ${text}`);
  assert.equal(sc.setting.scoring, scoring);
  assert.match(text, /give \(total 62\.4\)/, `${scoring} read_state: ${text}`);
  assert.match(text, /get \(no total: 1 name not matched\)/, `${scoring} read_state scored the unmatched name: ${text}`);
  assert.doesNotMatch(text, /get \(total/);
  assert.doesNotMatch(text, VERDICT, `${scoring} read_state gave a verdict`);
  assert.deepEqual(sc.unmatched, ["Zzyzx Notaplayer"]);
  assert.equal(sc.lists.get[1].player, null);
  assert.match(text, /Could not match: Zzyzx Notaplayer \(closest: [A-Z][^)]+\)\. Ask the user which player they meant/,
    `${scoring} read_state did not name closest players: ${text}`);
}

// read_state edge cases (review of #1231): an ambiguous name lists every player it fits, a key-only
// miss gets no made-up closest names, an unmatched target is named, and closest names are worked
// out for at most 5 misses so a pasted state full of junk names stays cheap.
const edge = codec.encodeBlock({ league: { scoring: "half_ppr", teams: 12 },
  work: { give: [{ name: "Josh" }, { key: "999" }], target: { name: "Zzyzx Notaplayer" } } });
let r = await call("read_state", { state: edge });
let text = r.result.content[0].text;
assert.match(text, /give \(no total: 2 names not matched\)/, text);
assert.match(text, /Could not match: Josh \(could be Josh Palmer, Josh Allen\)|Could not match: Josh \(could be Josh Allen, Josh Palmer\)/, text);
assert.match(text, /; 999; /, `key-only miss should be named alone: ${text}`);
assert.doesNotMatch(text, /999 \(closest/);
assert.match(text, /Zzyzx Notaplayer \(closest: [A-Z][^)]+\)\. Ask the user/, text);
assert.deepEqual(r.result.structuredContent.unmatched, ["Josh", "999", "Zzyzx Notaplayer"]);

const junk = Array.from({ length: 8 }, (_, i) => ({ name: `Qqqxv Junkname${i}` }));
r = await call("read_state", { state: codec.encodeBlock({ league: { scoring: "ppr" }, work: { get: junk } }) });
text = r.result.content[0].text;
assert.match(text, /get \(no total: 8 names not matched\)/);
const line = text.split("\n").find((l) => l.startsWith("Could not match:"));
assert.ok(line, text);
assert.ok((line.match(/\(closest: /g) ?? []).length <= 5, `closest names past the cap: ${line}`);
assert.match(line, /Qqqxv Junkname7/, "every miss is still named");

console.log("ok");
