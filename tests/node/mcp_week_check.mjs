// JEG-1157: the MCP tools name the values week get-values sends (JEG-1156 option A), in text and in
// structured content, and say nothing extra when an older get-values does not send it.
// Usage: node --experimental-strip-types tests/node/mcp_week_check.mjs
import assert from "node:assert/strict";
import { runTool } from "../../supabase/functions/mcp/tools.ts";

const NOTE = "Week 7 values, week 8 not published yet";
const base = {
  attribution: "Data Driven Football — https://example.test/",
  as_of: "2026-10-26",
  setting: { scoring: "ppr", teams: 12, superflex: 0 },
  players: [
    { player_key: 1, name: "Bijan Robinson", pos: "RB", value: 90.1, tier: "1" },
    { player_key: 2, name: "Ja'Marr Chase", pos: "WR", value: 88.4, tier: "1" },
  ],
  sources_included: ["fantasycalc", "usatoday", "fantasypros", "cbs"],
  sources_excluded: [{ key: "razzball", reason: "example reason" }],
};
const fallback = { ...base, values_week: 7, current_week: 8, values_week_note: NOTE,
  sources_fallback: [{ key: "cbs", week: 7, reason: "week 8 not published yet; using its week 7 chart" }] };
const fetchOf = (data) => async () => data;
const codec = {
  decodeBlock: () => ({ state: { v: 1, league: { scoring: "ppr", teams: 12 }, work: { give: [{ key: "1", name: "Bijan Robinson" }] } }, warnings: [] }),
  normalize: (state) => ({ state }),
  encodeQuery: () => "v=1",
  encodeBlock: () => "```ddf-state\n{}\n```",
};
const deps = { codec, siteOrigin: "https://example.test" };

for (const [name, args] of [["get_values", { limit: 2 }], ["get_player_value", { names: "Bijan Robinson" }],
  ["read_state", { state: "```ddf-state {} ```" }]]) {
  const r = await runTool(name, args, fetchOf(fallback), deps);
  assert.ok(r.content[0].text.includes(`Values week: ${NOTE}`), `${name} text names the values week`);
  assert.equal(r.structuredContent.values_week, 7, `${name} structured values_week`);
  assert.equal(r.structuredContent.values_week_note, NOTE, `${name} structured note`);
  const old = await runTool(name, args, fetchOf(base), deps);
  assert.ok(!old.content[0].text.includes("Values week:"), `${name}: no week line from an older get-values`);
  assert.equal(old.structuredContent.values_week, null);
}

// get_values says which sources were left out and why (an empty list is no longer silent).
const r = await runTool("get_values", { limit: 2 }, fetchOf(fallback), deps);
assert.ok(r.content[0].text.includes("Sources excluded: razzball (example reason)"));
assert.deepEqual(r.structuredContent.sources_excluded, base.sources_excluded);

console.log("ok");
