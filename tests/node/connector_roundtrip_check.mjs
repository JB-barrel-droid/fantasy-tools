// JEG-1030: state -> connector tool -> get-values -> site link round trips, offline (no network, no
// browser). Run by tests/test_connector_roundtrip.py.
//
// For every connector tool that reads a pasted DDF state, and for custom leagues covering 3-WR /
// 6-bench, all three scorings, 8/10/12/14 teams, superflex, position shares, the bench-share
// override, injury history, projection confidence and season weeks (including a reader week):
//   A. the answer priced the pasted league: the settings the tool sent to get-values, merged the way
//      get-values merges them, map (league.ts mapLeague) to the same engine inputs as the pasted league;
//   B. the site link opens what the answer priced: the link's league maps to the same engine inputs as
//      what the tool sent (also when an explicit argument overrides the pasted state);
//   C. the link loses no league field: it decodes to the pasted league, field for field;
//   D. the link is a fixed point: pasting it back into read_state sends the same settings and returns
//      the same link; work lists (give/get/mine/theirs/target) survive.
// Engine-input equality is the offline half of parity. The page half (the page applies a league the
// same way league.ts maps it) is tests/test_endpoint_parity.py, which needs a browser and a build.
//
// Discrimination: the same checks run against deliberately broken codecs and a tool call that drops
// the pasted league, and each must report failures (exit 1 otherwise).
//
// KNOWN_GAPS are real defects found by this check that need a runtime fix outside this test's ticket
// (JEG-1030 is tests only); each is written up with its repro on JEG-1030 for the connector owner. They must still fail today: a gap that starts passing makes this script exit 1 so
// the fixer removes it. --strict treats them as failures ("failing before, passing after").
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { readFileSync } from "node:fs";
import { handleRpc } from "../../supabase/functions/mcp/rpc.ts";
import { leagueKey, mapLeague } from "../../supabase/functions/get-values/league.ts";

const require = createRequire(import.meta.url);
const codec = require("../../app/v2/ddf-state.js");
const finder = require("../../app/v2/finder.js");
const STRICT = process.argv.includes("--strict");
const ORIGIN = "https://site.test";

// Lineup config for mapLeague, as in tests/node/league_mapping_check.mjs. Both sides of every
// comparison map through it, so its values do not decide a pass.
const CFG = { content_week: 6, defaults: { objective: "season", injury_history: "recent",
  league_weeks: { regular_season_end: 14, playoff_weeks: [15, 17] }, projection_confidence: 1 } };

// ---------- leagues (the normalized DDF league form) ----------
const LEAGUES = {
  // The ticket's 3-WR / 6-bench league with every field set.
  wr3_bn6_all_fields: {
    scoring: "half_ppr", teams: 10,
    roster: { QB: 1, RB: 2, WR: 3, TE: 1, FLEX: 1, SUPERFLEX: 1, BENCH: 6 },
    shares: { QB: 0.2, RB: 0.4, WR: 0.3, TE: 0.1 }, bso: 0.2, inj: "all", conf: 1.5,
    weeks: { regend: 13, playoffs: [14, 16], optimize: "playoffs", week: 5 },
  },
  ppr_14_roster_shares: {
    scoring: "ppr", teams: 14, roster: { QB: 2, FLEX: 2, BENCH: 10 },
    shares: { QB: 0.05, RB: 0.5, WR: 0.4, TE: 0.05 },
  },
  standard_8_weeks_bench: {
    scoring: "standard", teams: 8, bso: 0.05, conf: 0.5,
    weeks: { regend: 12, playoffs: [13, 15], optimize: "regular" },
  },
  ppr_12_default: { scoring: "ppr", teams: 12 },
};

// What the engine must be given for the 3-WR / 6-bench league, written out rather than derived, so
// a mapping that drifts from the ticket's league fails even if both sides drift together.
const WR3_ENGINE = {
  scoring: "half_ppr", teams: 10,
  setting: { teams: 10, slots: { QB: 1, RB: 2, WR: 3, TE: 1 }, flex: 1, superflex: 1, bench_per_team: 6,
    bench_share: 0.2, bench_share_override: 0.2 },
  lineupArgs: { objective: "playoffs", injury_history: "all",
    league_weeks: { regular_season_end: 13, playoff_weeks: [14, 16] }, projection_confidence: 1.5, content_week: 5 },
};

// ---------- tools ----------
// Each state-reading tool, its own arguments, the route its link must open and the work it must carry.
const TOOLS = [
  { name: "get_values", args: { limit: 1 }, route: "#trade-targets" },
  { name: "get_player_value", args: { names: "Josh Allen" }, route: "#trade-targets" },
  { name: "trade_targets", args: { player_name: "Josh Allen" }, route: "#trade-targets", work: { target: { key: "3" } } },
  { name: "compare_trade", args: { side_a: "Josh Allen", side_b: "Bijan Robinson" }, route: "#compare-trade",
    work: { give: [{ key: "3" }], get: [{ key: "1" }] } },
  { name: "read_state", args: {}, route: "#find-trade", work: { mine: [{ key: "4" }], theirs: [{ key: "2" }] } },
  { name: "make_state", args: { mine: "Josh Allen, Josh Jacobs", theirs: "Bijan Robinson" }, route: "#find-trade",
    work: { mine: [{ key: "3" }, { key: "4" }], theirs: [{ key: "1" }] } },
  { name: "find_trades", args: { mine: "Josh Allen, Josh Jacobs", theirs: "Bijan Robinson, Ja'Marr Chase" }, route: "#find-trade" },
  { name: "find_trades_league", args: { mine: "Josh Allen, Josh Jacobs",
    opponents: [{ name: "Opp", roster: "Bijan Robinson, Ja'Marr Chase" }] }, route: "#find-trade" },
];
// A pasted work section every tool receives; read_state must hand it back unchanged.
const PASTED_WORK = { mine: [{ key: "4" }], theirs: [{ key: "2" }] };

// Explicit arguments win over the pasted state. The link must then open the overridden league.
const OVERRIDES = [
  { id: "explicit superflex false over pasted SF1", league: "wr3_bn6_all_fields", args: { superflex: false } },
  { id: "explicit superflex true over pasted SF0", league: "sf0", args: { superflex: true } },
  { id: "explicit scoring and teams", league: "wr3_bn6_all_fields", args: { scoring: "standard", teams: 12 } },
];
LEAGUES.sf0 = { scoring: "ppr", teams: 12, roster: { QB: 1, RB: 2, WR: 3, TE: 1, FLEX: 1, SUPERFLEX: 0, BENCH: 6 } };

const KNOWN_GAPS = {
  // state.ts finish() rebuilds the link's league from the pasted league and adds SUPERFLEX only when
  // the pasted roster has none, so an explicit superflex argument prices one league and links another.
  "explicit superflex false over pasted SF1": "JEG-1030 finding F1",
  "explicit superflex true over pasted SF0": "JEG-1030 finding F1",
};

// ---------- stub get-values (prices nothing; records what it was asked for) ----------
const chart = (v) => ({ usatoday: v, fantasycalc: v, fantasypros: v, cbs: v });
const PLAYERS = [
  { player_key: 1, name: "Bijan Robinson", pos: "RB", value: 71.8 },
  { player_key: 2, name: "Ja'Marr Chase", pos: "WR", value: 70.2 },
  { player_key: 3, name: "Josh Allen", pos: "QB", value: 40 },
  { player_key: 4, name: "Josh Jacobs", pos: "RB", value: 39 },
].map((p) => ({ ...p, tier: "starter", chart_values: chart(p.value), chart_indexed: chart(p.value),
  ddf_value_charts: p.value, ddf_value_projections: p.value }));

function makeRecorder() {
  const sent = [];
  const answer = (scoring, teams, superflex, league) => {
    sent.push({ scoring, teams, superflex, league });
    return { attribution: "Data Driven Football", as_of: "2026-10-24", setting: { scoring, teams, superflex },
      players: PLAYERS, sources_included: ["espn", "usatoday", "fantasycalc", "fantasypros", "cbs"], sources_excluded: [],
      bench_share: { QB: 0.2, RB: 0.3, WR: 0.3, TE: 0.25, overall: 0.28, input: 0.15 } };
  };
  return { sent, values: async (...a) => answer(...a), charts: async (...a) => answer(...a) };
}

// get-values' own merge of the top-level fields and the league section (get-values/index.ts). It
// lives inside Deno.serve, so it is restated here; GET_VALUES_MERGE pins the source so a change there
// fails this check until it is restated.
const GET_VALUES_MERGE = [
  "const merged: League = { ...league, scoring, teams };",
  "if (superflex && merged.roster?.SUPERFLEX === undefined) {",
  "merged.roster = { ...(merged.roster ?? {}), SUPERFLEX: 1 };",
];
function getValuesMerge({ scoring, teams, superflex, league }) {
  const merged = { ...(league ?? {}), scoring, teams };
  if (superflex && merged.roster?.SUPERFLEX === undefined) merged.roster = { ...(merged.roster ?? {}), SUPERFLEX: 1 };
  return merged;
}
const engine = (league) => mapLeague(league, CFG);
const key = (league) => leagueKey(engine(league));
const linkOf = (result) => result.structuredContent?.site_url ?? "";
const linkState = (url) => codec.decodeQuery(url.split("?")[1] ?? "").state;
const routeOf = (url) => (/\/(#[a-z-]+)/.exec(url) || [])[1];

async function call(deps, rec, name, args) {
  const msg = { jsonrpc: "2.0", id: 1, method: "tools/call", params: { name, arguments: args } };
  const r = await handleRpc(msg, rec.values, deps, { finder, fetchCharts: rec.charts });
  return r.result;
}

// Run every check against `deps` (a codec and origin). Returns {failures: [{id, msg}]}.
async function runChecks(deps, opts = {}) {
  const failures = [];
  const fail = (id, msg) => failures.push({ id, msg });
  for (const [leagueName, league] of Object.entries(LEAGUES)) {
    if (leagueName === "sf0") continue;
    const pasted = codec.normalize({ league }).state.league;
    const block = codec.encodeBlock({ league, work: PASTED_WORK });
    for (const tool of TOOLS) {
      const id = `${tool.name} / ${leagueName}`;
      const rec = makeRecorder();
      const args = opts.dropState ? { ...tool.args } : { state: block, ...tool.args };
      const result = await call(deps, rec, tool.name, args);
      if (result.isError) { fail(id, `tool error: ${result.content[0].text}`); continue; }
      const sent = rec.sent.at(-1);
      if (!sent) { fail(id, "no get-values call"); continue; }
      const priced = getValuesMerge(sent);
      const url = linkOf(result);
      const back = linkState(url);
      if (routeOf(url) !== tool.route) fail(id, `link route ${routeOf(url)} != ${tool.route}: ${url}`);
      if (!back || !back.league) { fail(id, `link carries no league: ${url}`); continue; }
      if (key(priced) !== key(pasted)) fail(id, `A: priced ${key(priced)} != pasted ${key(pasted)}`);
      if (key(back.league) !== key(priced)) fail(id, `B: link ${key(back.league)} != priced ${key(priced)}`);
      try { assert.deepEqual(back.league, pasted); } catch { fail(id, `C: link league ${JSON.stringify(back.league)} != pasted ${JSON.stringify(pasted)}`); }
      for (const [list, want] of Object.entries(tool.work ?? {})) {
        try { assert.deepEqual(back.work?.[list], want); } catch { fail(id, `work.${list} ${JSON.stringify(back.work?.[list])} != ${JSON.stringify(want)}`); }
      }
      if (leagueName === "wr3_bn6_all_fields") {
        const m = engine(priced);
        const got = { scoring: m.scoring, teams: m.teams, setting: { ...m.setting }, lineupArgs: m.lineupArgs };
        delete got.setting.position_shares;
        try { assert.deepEqual(got, WR3_ENGINE); } catch { fail(id, `engine inputs ${JSON.stringify(got)}`); }
        const sh = m.setting.position_shares;
        if (!sh || Math.abs(sh.WR - 0.3) > 0.02 || Math.abs(sh.RB - 0.4) > 0.02) fail(id, `position shares ${JSON.stringify(sh)}`);
      }
      // D: the link pasted back is a fixed point.
      const rec2 = makeRecorder();
      const again = await call(deps, rec2, "read_state", { state: url });
      if (again.isError) { fail(id, `D: read_state on the link: ${again.content[0].text}`); continue; }
      const sent2 = rec2.sent.at(-1);
      if (!sent2 || key(getValuesMerge(sent2)) !== key(priced)) fail(id, `D: link re-read prices ${sent2 && key(getValuesMerge(sent2))}`);
      try { assert.deepEqual(linkState(linkOf(again)).league, back.league); } catch { fail(id, `D: link re-read league ${linkOf(again)}`); }
    }
  }
  // explain links to the site's front page without a league (nothing was priced).
  {
    const rec = makeRecorder();
    const r = await call(deps, rec, "explain", { topic: "tiers", state: codec.encodeBlock({ league: LEAGUES.wr3_bn6_all_fields }) });
    if (linkOf(r) !== `${ORIGIN}/` || r.structuredContent.state !== null) fail("explain", `explain link ${linkOf(r)}`);
  }
  for (const o of OVERRIDES) {
    const rec = makeRecorder();
    const r = await call(deps, rec, "get_values", { state: codec.encodeBlock({ league: LEAGUES[o.league] }), limit: 1, ...o.args });
    const priced = getValuesMerge(rec.sent.at(-1));
    const back = linkState(linkOf(r));
    if (!back?.league || key(back.league) !== key(priced)) {
      fail(o.id, `B: priced ${key(priced)} but the link opens ${back?.league ? key(back.league) : "no league"}`);
    }
  }
  return { failures };
}

// ---------- run ----------
const src = readFileSync(new URL("../../supabase/functions/get-values/index.ts", import.meta.url), "utf8");
for (const line of GET_VALUES_MERGE) assert.ok(src.includes(line), `get-values merge changed; restate getValuesMerge: ${line}`);

const deps = { codec, siteOrigin: ORIGIN };
const { failures } = await runChecks(deps);
const gapIds = new Set(Object.keys(KNOWN_GAPS));
const real = failures.filter((f) => !gapIds.has(f.id));
const failedGaps = new Set(failures.filter((f) => gapIds.has(f.id)).map((f) => f.id));
let bad = false;
for (const f of real) { console.log(`FAIL ${f.id}: ${f.msg}`); bad = true; }
for (const [id, ticket] of Object.entries(KNOWN_GAPS)) {
  if (!failedGaps.has(id)) { console.log(`FIXED? known gap ${id} (${ticket}) now passes: remove it from KNOWN_GAPS`); bad = true; }
  else {
    const f = failures.find((x) => x.id === id);
    console.log(`${STRICT ? "FAIL" : "known gap"} ${id} (${ticket}): ${f.msg}`);
    if (STRICT) bad = true;
  }
}
const cases = Object.keys(LEAGUES).length - 1;
console.log(`round trips: ${TOOLS.length} tools x ${cases} leagues, ${OVERRIDES.length} override cases, ${real.length} failures, ${failedGaps.size} known gaps`);

// Discrimination: each broken variant must be caught by the checks above.
const strip = (q, re) => q.split("&").filter((p) => !re.test(p)).join("&");
const MUTATIONS = {
  "link drops bso": { ...codec, encodeQuery: (s) => strip(codec.encodeQuery(s), /^bso=/) },
  "link drops shares": { ...codec, encodeQuery: (s) => strip(codec.encodeQuery(s), /^shares=/) },
  "link drops season weeks": { ...codec, encodeQuery: (s) => strip(codec.encodeQuery(s), /^(regend|playoffs|optimize|week)=/) },
  "link drops advanced": { ...codec, encodeQuery: (s) => strip(codec.encodeQuery(s), /^(inj|conf)=/) },
  "link rewrites roster to default": { ...codec, encodeQuery: (s) => codec.encodeQuery(s).replace(/roster=[^&]*/, "roster=QB1.RB2.WR2.TE1.FLEX1.SF0.BN7") },
  "link loses team count": { ...codec, encodeQuery: (s) => strip(codec.encodeQuery(s), /^teams=/) },
};
for (const [name, broken] of Object.entries(MUTATIONS)) {
  const r = await runChecks({ codec: broken, siteOrigin: ORIGIN });
  if (!r.failures.some((f) => !gapIds.has(f.id))) { console.log(`MUTATION NOT CAUGHT: ${name}`); bad = true; }
}
// A tool that ignores the pasted league prices the default league (the JEG-1070 bug shape).
const dropped = await runChecks(deps, { dropState: true });
if (!dropped.failures.some((f) => /^A: /.test(f.msg))) { console.log("MUTATION NOT CAUGHT: pasted league ignored"); bad = true; }
console.log(`mutations: ${Object.keys(MUTATIONS).length + 1} broken variants checked`);

if (bad) process.exit(1);
console.log("ok");
