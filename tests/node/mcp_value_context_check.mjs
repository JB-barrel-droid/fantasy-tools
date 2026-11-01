// JEG-1343 (JEG-1225 slice 4c): the MCP tools price a pasted site link under its own value basis and player
// overrides, name them in the reply, keep them in the link back, and give no numbers when get-values cannot price
// them. Part A runs the tools against a stub get-values that records what it was sent; part B runs them against
// the get-values handler itself (supabase/functions/get-values/index.ts, stub Deno, the built dist/ and the
// site's link reader), through the request the deployed MCP function makes (values-client.ts).
// Usage: node --experimental-strip-types tests/node/mcp_value_context_check.mjs <dist dir>
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { readFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { handleRpc } from "../../supabase/functions/mcp/rpc.ts";
import {
  askedValueContext, basisWords, linkValueContext, siteAppliesValueContext, VALUE_CONTEXT_NOT_SUPPORTED,
  valueContextLine, valueContextRefusal,
} from "../../supabase/functions/mcp/value-context.ts";
import { readValuesResponse, requestValuesWith } from "../../supabase/functions/mcp/values-client.ts";
import { checkTradeReplySize, ToolInputError } from "../../supabase/functions/mcp/tools.ts";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
const dist = resolve(process.argv[2] || join(ROOT, "dist"));
const require = createRequire(import.meta.url);
const codec = require("../../app/v2/ddf-state.js");
const finder = require("../../app/v2/finder.js");
const ValueLink = require("../../app/v2/ddf-value-link.js");
const ORIGIN = "https://site.test";
const deps = { codec, siteOrigin: ORIGIN };
const LEAGUE = "scoring=ppr&teams=12&v=1";
const queryOf = (url) => new URLSearchParams(String(url).split("?").slice(1).join("&"));

// ---------- A. the link's text, read and written ----------
assert.deepEqual(linkValueContext(`${ORIGIN}/#compare-trade?give=1&get=2&${LEAGUE}&basis=fantasycalc&ov=1:58`),
  { basis: "fantasycalc", ov: "1:58", complete: false });
assert.deepEqual(linkValueContext(`${ORIGIN}/#find-trade?mine=1&theirs=2&${LEAGUE}&valuecontext=1&basis=blend%3Aespn.60_fantasycalc.40&ov=2%3A%2B5`),
  { basis: "blend:espn.60_fantasycalc.40", ov: "2:+5", complete: true }, "percent-encoded, as overrides.js shareLink writes it");
assert.equal(linkValueContext(`x?ov=2:+5,3:-4`).ov, "2:+5,3:-4", "an unencoded + keeps its sign");
assert.deepEqual(linkValueContext(`x?give=1&valuecontext=1`), { basis: null, ov: null, complete: true },
  "valuecontext=1 alone is our methodology, asked for explicitly");
assert.equal(linkValueContext(`${ORIGIN}/#compare-trade?give=1&get=2&${LEAGUE}`), null, "a link with no value context");
assert.equal(askedValueContext({}), null);
// Pasted with punctuation, escaped ampersands, or beside another URL (review of #1219).
assert.equal(linkValueContext(`[open](${ORIGIN}/#compare-trade?give=1&basis=fantasycalc)`).basis, "fantasycalc", "a markdown link's )");
assert.equal(linkValueContext(`See ${ORIGIN}/#compare-trade?give=1&ov=1%3A58.`).ov, "1:58", "a sentence's full stop");
const MARKED = `${ORIGIN}/#find-trade?mine=1&valuecontext=1&basis=blend%3Aespn.60_razzball.40&ov=202%3A%2B5`;
for (const [pasted, label] of [[`[${MARKED}](${MARKED})`, "markdown [url](url)"], [`<${MARKED}|the link>`, "Slack <url|text>"],
  [`"${MARKED}"`, "quoted"]]) {
  assert.deepEqual(linkValueContext(pasted), { basis: "blend:espn.60_razzball.40", ov: "202:+5", complete: true }, label);
}
assert.equal(linkValueContext(`${ORIGIN}/#compare-trade?give=1&amp;valuecontext=1&amp;ov=1%3A58`).ov, "1:58", "&amp;");
assert.equal(linkValueContext(`https://other.test/x?ov=9:1 then ${ORIGIN}/#find-trade?mine=1&valuecontext=1&ov=1%3A58`).ov,
  "1:58", "the site's marked query wins over another URL's ov=");
// The basis is named from the link's text; get-values' value_context.basis is the engine's object.
const engineBasis = { mode: "single", source: "fantasycalc" };
assert.equal(valueContextLine({ basis: engineBasis, overrides_applied: 1, overrides_not_priced: [9] }, { basis: "fantasycalc", ov: "1:58" }),
  "Values: priced under the link's basis fantasycalc, with 1 player override from the link, 1 override for players with no value this week left out.");
assert.equal(basisWords("blend:espn.60_razzball.40"), "a blend of espn 60%, razzball 40%");
assert.doesNotMatch(valueContextLine({ basis: engineBasis }, { basis: "blend:espn.60_razzball.40", ov: null }), /object/);
// Where the site applies a link's values (v2.js readTradeHash, league.js) and where it doesn't yet.
assert.equal(siteAppliesValueContext(`${ORIGIN}/#find-trade?mine=1&theirs=2`), true);
assert.equal(siteAppliesValueContext(`${ORIGIN}/#compare-trade?give=1&get=2`), true);
assert.equal(siteAppliesValueContext(`${ORIGIN}/#compare-trade?give=n:Ghost&get=2`), false);
assert.equal(siteAppliesValueContext(`${ORIGIN}/#compare-trade?give=1&get=2&mine=3`), false);
assert.equal(siteAppliesValueContext(`${ORIGIN}/#trade-targets?target=1`), false);
assert.equal(siteAppliesValueContext(`${ORIGIN}/#risers-fallers`), false);
for (const [status, code] of [[400, "value_context_unreadable"], [413, "value_context_too_large"], [422, "basis_unavailable"], [503, "value_context_unavailable"]]) {
  const text = valueContextRefusal(status, { code, error: "why" });
  assert.match(text, /can't be priced here: .* \(why\)\. No values are given/, code);
}
assert.equal(valueContextRefusal(400, { code: "week_unavailable", error: "x" }), null, "a week refusal is not this one");

// ---------- A. the tools, against a stub get-values ----------
const sent = [];
let stubKnowsContext = true;
const row = (player_key, name, pos, value) => ({
  player_key, name, pos, value, tier: "starter",
  chart_values: { usatoday: value, fantasycalc: value, fantasypros: value, cbs: value },
  chart_indexed: { usatoday: value, fantasycalc: value, fantasypros: value, cbs: value },
  ddf_value_charts: value, ddf_value_projections: value,
});
function answer(scoring, teams, superflex, context) {
  // The stub prices "1:58" as get-values would: player 1 at 58, everyone else as before.
  const over = context?.ov === "1:58";
  const data = {
    attribution: "Data Driven Football", as_of: "2026-10-28", setting: { scoring, teams, superflex },
    week: 8, default_week: 8, weeks: [8], missing_sources: [], sources_included: ["fantasycalc"], sources_excluded: [],
    players: [row(1, "Bijan Robinson", "RB", over ? 58 : 71.8), row(2, "Ja'Marr Chase", "WR", 70.2),
      row(3, "Josh Allen", "QB", 40), row(4, "Josh Jacobs", "RB", 39)],
  };
  if (context && stubKnowsContext) {
    data.value_context = { basis: context.basis ? { mode: "single", source: context.basis, weights: null } : null, basis_applied: true, overrides: over ? { 1: 58 } : {},
      overrides_applied: over ? 1 : 0, overrides_not_priced: [] };
  }
  return data;
}
const stub = async (scoring, teams, superflex, league, week, context) => {
  sent.push({ tool: "values", context: context ?? null });
  return answer(scoring, teams, superflex, context);
};
const charts = async (scoring, teams, superflex, league, week, context) => {
  sent.push({ tool: "charts", context: context ?? null });
  return answer(scoring, teams, superflex, context);
};
const call = (name, args, fetchValues = stub, finderDeps = { finder, fetchCharts: charts }) =>
  handleRpc({ jsonrpc: "2.0", id: 1, method: "tools/call", params: { name, arguments: args } }, fetchValues, deps, finderDeps);
const text = (r) => r.result.content[0].text;

const LINK = `${ORIGIN}/#compare-trade?give=1&get=2&${LEAGUE}&basis=fantasycalc&ov=1:58`;

// M1: read_state on a link with a basis and an override prices under them and says so.
let r = await call("read_state", { state: LINK });
assert.ok(!r.result.isError, text(r));
assert.deepEqual(sent.at(-1).context, { basis: "fantasycalc", ov: "1:58" }, "the link's own text goes to get-values");
assert.match(text(r), /Bijan Robinson \(RB\): 58\b/, "priced at the override, not 71.8");
assert.match(text(r), /^Values: priced under the link's basis fantasycalc, with 1 player override from the link\.$/m);
assert.deepEqual(r.result.structuredContent.value_context.overrides_applied, 1);
assert.equal(r.result.structuredContent.value_context.basis, "fantasycalc", "the link's text, not the engine's object");
assert.equal(r.result.structuredContent.value_context.overrides, undefined, "the overrides map stays out of the answer");
assert.doesNotMatch(text(r), /doesn't apply a link's own values/, "a key-only Compare link opens on the same values");

// M2: the link back keeps the value context exactly, and the site's strict reader reads it back the same.
let url = r.result.structuredContent.site_url;
let q = queryOf(url);
assert.equal(q.get("valuecontext"), "1");
assert.equal(q.get("basis"), "fantasycalc");
assert.equal(q.get("ov"), "1:58");
const back = ValueLink.readValueContext(q, { strict: true });
assert.deepEqual(back.unread, []);
assert.deepEqual(back.basis, { mode: "single", source: "fantasycalc" });
assert.deepEqual(back.overrides, { 1: 58 });
assert.ok(text(r).includes(url), "the reply's link is the one with the value context");

// M3: make_state keeps it in the block's link, and the block pasted back asks for the same values.
r = await call("make_state", { state: LINK, target: "Josh Allen" });
assert.ok(!r.result.isError, text(r));
assert.equal(queryOf(r.result.structuredContent.site_url).get("ov"), "1:58");
const block = text(r).slice(text(r).indexOf("```ddf-state"));
assert.match(block, /Open on the site: .*valuecontext=1&basis=fantasycalc&ov=1%3A58/);
r = await call("read_state", { state: block });
assert.deepEqual(sent.at(-1).context, { basis: "fantasycalc", ov: "1:58" }, "a pasted block's link carries the values back");
assert.match(text(r), /Josh Allen \(QB\): 40/);

// Every pricing tool sends it: values, charts (the finders) and the trade readout.
for (const [name, args, tool] of [
  ["get_values", { limit: 2 }, "values"],
  ["get_player_value", { names: ["Bijan Robinson"] }, "values"],
  ["compare_trade", { side_a: ["Bijan Robinson"], side_b: ["Ja'Marr Chase"] }, "values"],
  ["find_trades", { mine: "Bijan Robinson, Josh Allen", theirs: "Ja'Marr Chase, Josh Jacobs" }, "charts"],
]) {
  r = await call(name, { ...args, state: LINK });
  assert.ok(!r.result.isError, `${name}: ${text(r)}`);
  assert.equal(sent.at(-1).tool, tool, name);
  assert.deepEqual(sent.at(-1).context, { basis: "fantasycalc", ov: "1:58" }, name);
  assert.equal(queryOf(r.result.structuredContent.site_url).get("valuecontext"), "1", `${name}: link back`);
  assert.match(text(r), /^Values: priced under the link's basis fantasycalc/m, name);
}
r = await call("get_player_value", { names: ["Bijan Robinson"], state: LINK });
assert.match(text(r), /Bijan Robinson \(RB\): value 58\b/);
// Trade targets doesn't apply a link's values on the site yet (JEG-1224 S2): the reply says the link opens on defaults.
assert.match(r.result.structuredContent.site_url, /#trade-targets/);
assert.match(text(r), /^Values: .* The site doesn't apply a link's own values on this view yet, so the link opens on the default values\.$/m);
assert.equal(r.result.structuredContent.site_applies_value_context, false);

// A link with 2,000 overrides (the most get-values reads) fits a trade reply: the answer keeps counts, not the map.
const many = Array.from({ length: 2000 }, (_, i) => [String(5000 + i), 50.5]);
const manyStub = async (scoring, teams, superflex, league, week, context) => ({ ...answer(scoring, teams, superflex, null),
  value_context: { basis: null, basis_applied: false, overrides: Object.fromEntries(many), overrides_applied: 0,
    overrides_not_priced: many.map(([k]) => Number(k)) } });
r = await call("find_trades", { mine: "Bijan Robinson, Josh Allen", theirs: "Ja'Marr Chase, Josh Jacobs",
  state: `${ORIGIN}/#find-trade?${LEAGUE}&valuecontext=1&ov=${encodeURIComponent(many.map(([k, v]) => `${k}:${v}`).join(","))}` },
  manyStub, { finder, fetchCharts: manyStub });
assert.ok(!r.result.isError, `2,000 overrides: ${text(r)}`);
assert.equal(r.result.structuredContent.value_context.overrides_not_priced_count, 2000);
assert.equal(r.result.structuredContent.value_context.overrides_not_priced.length, 25);
assert.match(text(r), /2000 overrides for players with no value this week left out/);

// The value context is added after a trade reply's rows are trimmed to its budget, so it never turns a reply that
// fit into "too large" (review of #1219): the final size check leaves it out like the site link.
const fitted = { content: [{ type: "text", text: `Settings: ppr, 12 teams\n${"x".repeat(6000)}` }],
  structuredContent: { limit: 10, site_url: `${ORIGIN}/#find-trade?mine=1` } };
checkTradeReplySize("find_trades", fitted);
const withContextLine = { ...fitted, content: [{ type: "text", text: fitted.content[0].text.replace("Settings: ppr, 12 teams",
  `Settings: ppr, 12 teams\nValues: priced under the link's basis a blend of espn 60%, razzball 40%, ${"y".repeat(400)}.`) }],
  structuredContent: { ...fitted.structuredContent, value_context: { basis: "blend:espn.60_razzball.40",
    overrides_not_priced: Array.from({ length: 25 }, (_, i) => 100000 + i), overrides_not_priced_count: 900 } } };
checkTradeReplySize("find_trades", withContextLine);
assert.throws(() => checkTradeReplySize("find_trades", { ...fitted, content: [{ type: "text", text: "z".repeat(7000) }] }),
  /too large/, "the budget itself still holds");
// A tool that prices nothing (explain) gets no value context on its link.
r = await call("explain", { topic: "methodology", state: LINK });
assert.ok(!/valuecontext=/.test(JSON.stringify(r.result)), "explain's link is left alone");

// The league finder and the analyses send it too.
r = await call("find_trades_league", { mine: "Bijan Robinson, Josh Allen",
  opponents: [{ name: "Rival", roster: "Ja'Marr Chase, Josh Jacobs" }], state: LINK });
assert.ok(!r.result.isError, `find_trades_league: ${text(r)}`);
assert.deepEqual(sent.at(-1).context, { basis: "fantasycalc", ov: "1:58" }, "find_trades_league");
const analysisDeps = { finder, fetchCharts: charts, analysis: {
  modules: { movers: {}, trade: {}, auditPie: {}, auditSource: {} },
  fetchAnalysis: async (scoring, teams, superflex, league, week, includes, context) => {
    sent.push({ tool: "analysis", context: context ?? null });
    throw new ToolInputError("analysis stub: context recorded");
  } } };
for (const [name, args] of [["risers_fallers", {}], ["audit_values", {}],
  ["compare_trade", { side_a: ["Bijan Robinson"], side_b: ["Ja'Marr Chase"], by_source: true }]]) {
  await call(name, { ...args, state: LINK }, stub, analysisDeps);
  assert.equal(sent.at(-1).tool, "analysis", name);
  assert.deepEqual(sent.at(-1).context, { basis: "fantasycalc", ov: "1:58" }, name);
}

// No value context: nothing sent, nothing added (the answers are as before).
r = await call("read_state", { state: `${ORIGIN}/#compare-trade?give=1&get=2&${LEAGUE}` });
assert.equal(sent.at(-1).context, null);
assert.equal(r.result.structuredContent.value_context, undefined);
assert.doesNotMatch(r.result.structuredContent.site_url, /valuecontext|basis=|ov=/);
assert.doesNotMatch(text(r), /^Values:/m);
assert.match(text(r), /Bijan Robinson \(RB\): 71\.8/);

// A get-values from before JEG-1225 ignores basis and ov: the tool gives no numbers, not the default values.
stubKnowsContext = false;
r = await call("read_state", { state: LINK });
stubKnowsContext = true;
assert.equal(r.result.isError, true);
assert.equal(text(r), VALUE_CONTEXT_NOT_SUPPORTED);
// A bare valuecontext=1 link asks for our methodology, which any build prices: values as before, and the link
// back keeps the marker so the site still reads it as complete (no override of the reader's saved values).
stubKnowsContext = false;
r = await call("read_state", { state: `${ORIGIN}/#compare-trade?give=1&get=2&${LEAGUE}&valuecontext=1` });
stubKnowsContext = true;
assert.ok(!r.result.isError, text(r));
assert.match(text(r), /Bijan Robinson \(RB\): 71\.8/);
assert.equal(queryOf(r.result.structuredContent.site_url).get("valuecontext"), "1");
assert.equal(queryOf(r.result.structuredContent.site_url).get("ov"), null);
assert.doesNotMatch(text(r), /^Values:/m);

// A refusal reaches the reply as the tool's message, with no numbers.
const refuse = (status, code) => async () => {
  return await readValuesResponse(new Response(JSON.stringify({ error: `refused (${code})`, code }), { status }));
};
for (const [status, code] of [[400, "value_context_unreadable"], [413, "value_context_too_large"], [422, "basis_unavailable"], [503, "value_context_unavailable"]]) {
  r = await call("read_state", { state: LINK }, refuse(status, code));
  assert.equal(r.result.isError, true, code);
  assert.match(text(r), /^This link's own values can't be priced here: /, code);
  assert.doesNotMatch(text(r), /Bijan|Robinson|\b58\b|71\.8/, `${code}: no values`);
}
// A 503 that is not about the link reader stays the generic "temporarily unavailable" error.
await assert.rejects(readValuesResponse(new Response("{}", { status: 503 })), (e) => e.constructor.name === "Error");

// The request: a GET as before without a context, a POST with the link's text with one.
const requests = [];
const record = async (input, init) => { requests.push({ url: String(input), init: init ?? {} }); return new Response("{}"); };
await requestValuesWith(record, "https://fn.test/get-values", "ppr", 12, 0, undefined, 8, "charts", null);
assert.equal(requests[0].init.method, undefined);
assert.match(requests[0].url, /\?scoring=ppr&teams=12&superflex=0&week=8&include=charts$/);
await requestValuesWith(record, "https://fn.test/get-values", "ppr", 12, 1, { roster: { QB: 1 } }, null, null,
  { basis: "fantasycalc", ov: "1:58" });
assert.equal(requests[1].init.method, "POST");
assert.deepEqual(JSON.parse(requests[1].init.body),
  { scoring: "ppr", teams: 12, superflex: 1, league: { roster: { QB: 1 } }, basis: "fantasycalc", ov: "1:58" });

// ---------- B. against the get-values handler itself ----------
let handler = null;
globalThis.Deno = { env: { get: () => undefined }, serve: (h) => { handler = h; } };
globalThis.fetch = async (input) => {
  const path = new URL(String(input)).pathname.replace(/^\/fantasy-tools/, "");
  const file = path === "/v2/ddf-value-link.js" ? join(ROOT, "app/v2/ddf-value-link.js")
    : join(dist, path === "/" || path === "" ? "index.html" : path);
  try { return new Response(readFileSync(file), { status: 200 }); } catch { return new Response("not found", { status: 404 }); }
};
await import("../../supabase/functions/get-values/index.ts?mcp-vc");
assert.equal(typeof handler, "function");
let ip = 0;
const toHandler = (input, init) => handler(new Request(String(input), {
  ...init, headers: { ...(init?.headers ?? {}), "x-forwarded-for": `10.9.0.${++ip}` } }));
const real = async (scoring, teams, superflex, league, week, context) =>
  await readValuesResponse(await requestValuesWith(toHandler, "https://fn.test/functions/v1/get-values",
    scoring, teams, superflex, league, week, null, context));

r = await call("get_values", { limit: 3 }, real, undefined);
const top = r.result.structuredContent.players[0];
const plain = await real("ppr", 12, 0, undefined, null, null);
const key = plain.players.find((p) => p.name === top.name).player_key;
r = await call("get_player_value", { names: [top.name], state: `${ORIGIN}/#compare-trade?give=${key}&${LEAGUE}&valuecontext=1&ov=${key}%3A58` }, real, undefined);
assert.ok(!r.result.isError, text(r));
assert.match(text(r), new RegExp(`${top.name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")} \\(${top.pos}\\): value 58\\b`), "the real endpoint prices the override");
assert.notEqual(top.value, 58);
assert.equal(r.result.structuredContent.value_context.overrides_applied, 1);
assert.equal(queryOf(r.result.structuredContent.site_url).get("ov"), `${key}:58`);
// A basis through the real endpoint: named from the link, not as the engine's object (review of #1219).
r = await call("get_player_value", { names: [top.name], state: `${ORIGIN}/#compare-trade?give=${key}&${LEAGUE}&valuecontext=1&basis=fantasycalc` }, real, undefined);
assert.ok(!r.result.isError, text(r));
assert.match(text(r), /^Values: priced under the link's basis fantasycalc\./m);
assert.doesNotMatch(text(r), /\[object Object\]/);
r = await call("get_player_value", { names: [top.name], state: `${ORIGIN}/#compare-trade?give=${key}&${LEAGUE}&valuecontext=1&basis=blend%3Aespn.60_fantasycalc.40` }, real, undefined);
assert.ok(!r.result.isError, text(r));
assert.match(text(r), /^Values: priced under the link's basis a blend of espn 60%, fantasycalc 40%\./m);
// The real endpoint's refusals reach the reply with no numbers.
for (const bad of ["basis=notasource", `ov=${key}%3Agarbage`]) {
  r = await call("get_player_value", { names: [top.name], state: `${ORIGIN}/#compare-trade?give=${key}&${LEAGUE}&${bad}` }, real, undefined);
  assert.equal(r.result.isError, true, bad);
  assert.match(text(r), /^This link's own values can't be priced here: part of the link's basis or overrides can't be read/, bad);
  assert.doesNotMatch(text(r), /value \d/, `${bad}: no values`);
}

console.log("ok");
