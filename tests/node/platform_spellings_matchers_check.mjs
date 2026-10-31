// JEG-1387 (part of JEG-1202): do the page's roster paste (app/v2/roster-paste.js) and the chat
// connector's name match (supabase/functions/mcp/names.ts) land each stored ESPN, Sleeper and Yahoo
// spelling (data/inputs/player_platform_spellings.json) on its player? Read-only: runs both matchers
// against the published players (data/fixtures/current/players.json) and prints one JSON line.
// Only rows whose player is priced are checked. Run by tests/test_platform_spellings.py.
import { createRequire } from "node:module";
import { readFileSync } from "node:fs";
import { matchName } from "../../supabase/functions/mcp/names.ts";

const require = createRequire(import.meta.url);
const paste = require("../../app/v2/roster-paste.js");
const read = (rel) => JSON.parse(readFileSync(new URL(`../../${rel}`, import.meta.url), "utf8"));

const players = read("data/fixtures/current/players.json").players
  .map((p) => ({ player_key: p.player_key, name: p.name, pos: p.pos, team: p.team }));
const priced = new Set(players.map((p) => p.player_key));
const index = paste.buildIndex(players);
const result = { checked: 0, paste: {}, mcp: {}, misses: [] };

for (const r of read("data/inputs/player_platform_spellings.json").rows) {
  if (!priced.has(r.player_key)) continue;
  result.checked++;
  const isDST = r.position === "DST";
  const c = paste.matchCandidate(
    { name: r.source_player_name, posHint: r.position, teamHint: r.team || null, isDST }, index, {});
  const pasteKey = c && c.match ? c.match.player_key : null;
  const pasteOut = pasteKey === r.player_key ? "ok" : pasteKey == null ? "none" : "other";
  // The connector matches within the asked position's priced players.
  const m = matchName(players.filter((p) => p.pos === r.position), r.source_player_name);
  const mcpKey = m.player ? m.player.player_key : null;
  const mcpOut = mcpKey === r.player_key ? `ok:${m.match}` : mcpKey == null ? m.match : `other:${m.match}`;
  result.paste[pasteOut] = (result.paste[pasteOut] || 0) + 1;
  result.mcp[mcpOut] = (result.mcp[mcpOut] || 0) + 1;
  if (pasteOut !== "ok" || !mcpOut.startsWith("ok:")) {
    result.misses.push({ source: r.source, name: r.source_player_name, pos: r.position, player_key: r.player_key,
                         paste: pasteOut, paste_key: pasteKey, mcp: mcpOut, mcp_key: mcpKey });
  }
}
console.log(JSON.stringify(result));
