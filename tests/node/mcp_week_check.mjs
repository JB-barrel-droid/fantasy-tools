// JEG-1179: the week the MCP tools price. A stub get-values records the week each tool asks for and
// answers with the week fields the real endpoint returns; the deployed entry point (mcp/index.ts) is then
// run with a stub Deno and fetch to check the week reaches get-values and a week with no published
// sources comes back as a clear tool error. Run by tests/test_mcp_week.py.
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { readFileSync } from "node:fs";
import { handleRpc } from "../../supabase/functions/mcp/rpc.ts";
import { askedWeek, linkWeek, weekLine } from "../../supabase/functions/mcp/week.ts";

const require = createRequire(import.meta.url);
const codec = require("../../app/v2/ddf-state.js");
const finder = require("../../app/v2/finder.js");
const ORIGIN = "https://site.test";
const deps = { codec, siteOrigin: ORIGIN };

// The stub endpoint: week 8 is the default (cbs has not published it), week 7 is the week before.
const WEEKS = { 8: { missing: ["cbs"] }, 7: { missing: [] } };
const player = (player_key, name, pos, value, chart) => ({
  player_key, name, pos, value, tier: "starter",
  chart_values: { usatoday: chart, fantasycalc: chart, fantasypros: chart, cbs: chart },
  chart_indexed: { usatoday: chart, fantasycalc: chart, fantasypros: chart, cbs: chart },
  ddf_value_charts: value, ddf_value_projections: value,
});
const asked = [];
function answer(scoring, teams, superflex, week) {
  const w = week ?? 8;
  if (!WEEKS[w]) {
    const e = new Error(`Week ${w} has no published sources at this setting. Weeks available: 8, 7 (default 8).`);
    e.name = "WeekUnavailable";
    throw e;
  }
  const bump = w === 7 ? -5 : 0;
  return {
    attribution: "Data Driven Football", as_of: "2026-10-28", setting: { scoring, teams, superflex },
    league_custom: [], week: w, default_week: 8, weeks: [8, 7], missing_sources: WEEKS[w].missing,
    sources_included: ["espn", "usatoday", "fantasycalc", "fantasypros", ...(w === 7 ? ["cbs"] : [])],
    sources_excluded: [],
    players: [
      player(1, "Bijan Robinson", "RB", 71.8 + bump, 66), player(2, "Ja'Marr Chase", "WR", 70.2 + bump, 65),
      player(3, "Josh Allen", "QB", 40 + bump, 36), player(4, "Josh Jacobs", "RB", 39 + bump, 35),
    ],
  };
}
const stub = async (scoring, teams, superflex, league, week) => {
  asked.push({ tool: "values", week: week ?? null });
  return answer(scoring, teams, superflex, week);
};
const charts = async (scoring, teams, superflex, league, week) => {
  asked.push({ tool: "charts", week: week ?? null });
  return answer(scoring, teams, superflex, week);
};
const call = (name, args) =>
  handleRpc({ jsonrpc: "2.0", id: 1, method: "tools/call", params: { name, arguments: args } }, stub, deps,
    { finder, fetchCharts: charts });
const last = () => asked.at(-1).week;

// Helpers: wk= in a site link, the week argument, and the text line.
assert.equal(linkWeek(`${ORIGIN}/#compare-trade?give=3&wk=7`), 7);
assert.equal(linkWeek(`${ORIGIN}/#compare-trade?give=3&wk=23`), null, "a link week outside 1 to 22 is ignored");
assert.equal(linkWeek(`${ORIGIN}/#compare-trade?give=3&wk=0`), null, "wk=0 is ignored");
assert.equal(askedWeek({ state: "x?wk=99" }), null, "a bad link week falls back to the default week");
assert.equal(linkWeek("week=5&regend=14"), null, "the league's week= is not the data week");
assert.equal(askedWeek({ week: "7", state: "x?wk=8" }), 7, "an explicit week wins over the link");
assert.ok(Number.isNaN(askedWeek({ week: 0 })));
assert.match(weekLine({ week: 8, default_week: 8, weeks: [8, 7], missing_sources: ["cbs"] }),
  /Week: 8 \(the site's default\); week 7 can also be asked for; not yet published for week 8, left out: cbs\./);

// Every pricing tool offers `week`.
const list = await handleRpc({ jsonrpc: "2.0", id: 1, method: "tools/list" }, stub);
for (const t of list.result.tools.filter((t) => t.name !== "explain")) {
  assert.equal(t.inputSchema.properties.week?.type, "integer", `${t.name} takes week`);
}

// get_values: no week = the default week, named with what it leaves out; the link carries no wk=.
let r = await call("get_values", { limit: 2 });
assert.equal(last(), null);
let sc = r.result.structuredContent;
assert.equal(sc.week, 8);
assert.equal(sc.default_week, 8);
assert.deepEqual(sc.weeks, [8, 7]);
assert.deepEqual(sc.missing_sources, ["cbs"]);
assert.ok(!sc.sources_included.includes("cbs"), "a lagging source is not carried forward");
assert.match(r.result.content[0].text, /^Settings: .*\nWeek: 8 \(the site's default\).*left out: cbs\./m);
assert.doesNotMatch(sc.site_url, /wk=/);

// An explicit week is sent to get-values, and the link opens the site on that week.
r = await call("get_values", { week: 7, limit: 2 });
assert.equal(last(), 7);
sc = r.result.structuredContent;
assert.equal(sc.week, 7);
assert.deepEqual(sc.missing_sources, []);
assert.equal(sc.players[0].value, 66.8);
assert.match(sc.site_url, /[?&]wk=7$/);
assert.ok(r.result.content[0].text.includes(sc.site_url), "the text's link is the one with wk=");
assert.match(r.result.content[0].text, /Week: 7, asked for \(the site's default is 8\)/);

// get_player_value, find_trades and find_trades_league price the asked week too.
r = await call("get_player_value", { names: "Josh Allen", week: "7" });
assert.equal(last(), 7);
assert.equal(r.result.structuredContent.results[0].player.value, 35);
assert.equal(r.result.structuredContent.week, 7);
r = await call("find_trades", { mine: "Josh Allen, Josh Jacobs", theirs: "Bijan Robinson, Ja'Marr Chase", week: 7 });
assert.notEqual(r.result.isError, true, JSON.stringify(r.result));
assert.deepEqual(asked.at(-1), { tool: "charts", week: 7 });
assert.equal(r.result.structuredContent.week, 7);
r = await call("find_trades_league", {
  mine: "Josh Allen, Josh Jacobs", opponents: [{ name: "Rival", roster: "Bijan Robinson, Ja'Marr Chase" }],
});
assert.notEqual(r.result.isError, true, JSON.stringify(r.result));
assert.deepEqual(asked.at(-1), { tool: "charts", week: null });
assert.equal(r.result.structuredContent.week, 8);
assert.deepEqual(r.result.structuredContent.missing_sources, ["cbs"]);

// read_state honours wk= from a site link; an explicit week still wins.
const link = `${ORIGIN}/#compare-trade?v=1&scoring=ppr&teams=12&give=3&get=1&wk=7`;
r = await call("read_state", { state: link });
assert.notEqual(r.result.isError, true, JSON.stringify(r.result));
assert.equal(last(), 7);
assert.equal(r.result.structuredContent.week, 7);
assert.match(r.result.structuredContent.site_url, /wk=7/);
r = await call("read_state", { state: link, week: 8 });
assert.equal(last(), 8);

// A bad week is a tool error, not a protocol error.
r = await call("get_values", { week: "next" });
assert.equal(r.result.isError, true);
assert.match(r.result.content[0].text, /invalid week/);

// The deployed entry point: the week reaches get-values as ?week=, and a week with no published
// sources (get-values answers 400 week_unavailable) is shown to the caller as that message.
let serve = null;
const env = { DDF_API_URL: "https://fn.test/functions/v1/get-values", DDF_SITE_ORIGIN: ORIGIN };
globalThis.Deno = { env: { get: (k) => env[k] }, serve: (h) => { serve = h; } };
const seen = [];
globalThis.fetch = async (url) => {
  const u = new URL(String(url));
  if (u.origin === ORIGIN) {
    const file = { "/v2/ddf-state.js": "app/v2/ddf-state.js", "/v2/finder.js": "app/v2/finder.js" }[u.pathname];
    return file ? new Response(readFileSync(file, "utf8")) : new Response("no", { status: 404 });
  }
  const week = u.searchParams.get("week");
  seen.push(week);
  if (week === "9") {
    return Response.json({ error: "Week 9 has no published sources at this setting. Weeks available: 8, 7 (default 8).",
      code: "week_unavailable", weeks: [8, 7], default_week: 8 }, { status: 400 });
  }
  return Response.json(answer(u.searchParams.get("scoring"), Number(u.searchParams.get("teams")),
    Number(u.searchParams.get("superflex")), week ? Number(week) : null));
};
await import("../../supabase/functions/mcp/index.ts");
assert.equal(typeof serve, "function");
const post = async (args) => (await serve(new Request("https://fn.test/functions/v1/mcp", {
  method: "POST", headers: { "content-type": "application/json", "x-forwarded-for": "9.9.9.9" },
  body: JSON.stringify({ jsonrpc: "2.0", id: 1, method: "tools/call", params: { name: "get_values", arguments: args } }),
}))).json();
let out = await post({ limit: 1 });
assert.equal(seen.at(-1), null, "no week asked: get-values picks the default");
assert.equal(out.result.structuredContent.week, 8);
out = await post({ limit: 1, week: 7 });
assert.equal(seen.at(-1), "7");
assert.equal(out.result.structuredContent.week, 7);
out = await post({ limit: 1, week: 9 });
assert.equal(seen.at(-1), "9");
assert.equal(out.result.isError, true);
assert.match(out.result.content[0].text, /Week 9 has no published sources at this setting\. Weeks available: 8, 7 \(default 8\)\./);

console.log("ok");
