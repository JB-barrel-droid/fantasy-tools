// JEG-1030: prints the connector's tool and route inventory as JSON for tests/test_connector_inventory.py
// (no network: get-values is a stub). For each tool, the site route its result links to, observed by
// calling it, so the inventory test checks what the tools do and not what a list says they do.
import { createRequire } from "node:module";
import { handleRpc } from "../../supabase/functions/mcp/rpc.ts";
import { ROUTES } from "../../supabase/functions/mcp/state.ts";
import { evalPageModule, PAGE_MODULE_FILES } from "../../supabase/functions/mcp/analyses.ts";
import { readFileSync } from "node:fs";

const require = createRequire(import.meta.url);
const deps = { codec: require("../../app/v2/ddf-state.js"), siteOrigin: "https://site.test" };
const chart = (v) => ({ usatoday: v, fantasycalc: v, fantasypros: v, cbs: v });
const players = [
  { player_key: 1, name: "Bijan Robinson", pos: "RB", value: 71.8 },
  { player_key: 3, name: "Josh Allen", pos: "QB", value: 40 },
].map((p) => ({ ...p, tier: "starter", chart_values: chart(p.value), chart_indexed: chart(p.value),
  ddf_value_charts: p.value, ddf_value_projections: p.value }));
const answer = async (scoring, teams, superflex) => ({ attribution: "Data Driven Football", as_of: "2026-10-24",
  setting: { scoring, teams, superflex }, players, sources_included: ["espn"], sources_excluded: [],
  bench_share: { QB: 0.2, RB: 0.3, WR: 0.3, TE: 0.25, overall: 0.28, input: 0.15 } });
// JEG-1029: the analyses' page modules and an empty analysis answer (the route is all this reads).
const modules = Object.fromEntries(Object.entries(PAGE_MODULE_FILES)
  .map(([name, m]) => [name, evalPageModule(readFileSync(new URL(`../../app/${m.file}`, import.meta.url), "utf8"), name)]));
const fetchAnalysis = async (...a) => ({ ...(await answer(...a)), series: {}, audit: {},
  prior: { available: false, reason: "stub", current_week: null, prior_week: null, series: {} } });
const finderDeps = { finder: require("../../app/v2/finder.js"), fetchCharts: answer, analysis: { fetchAnalysis, modules } };
const rpc = (method, params) => handleRpc({ jsonrpc: "2.0", id: 1, method, params }, answer, deps, finderDeps);

// The smallest valid arguments for each tool. A tool missing here is reported with route null.
const ARGS = {
  get_values: { limit: 1 },
  get_player_value: { names: "Josh Allen" },
  trade_targets: { player_name: "Josh Allen" },
  compare_trade: { side_a: "Josh Allen", side_b: "Bijan Robinson" },
  read_state: { state: '{"league":{"scoring":"ppr"},"work":{"give":[{"key":"3"}]}}' },
  make_state: { mine: "Josh Allen" },
  find_trades: { mine: "Josh Allen", theirs: "Bijan Robinson" },
  find_trades_league: { mine: "Josh Allen", opponents: [{ name: "Opp", roster: "Bijan Robinson" }] },
  explain: { topic: "tiers" },
  risers_fallers: {},
  audit_values: {},
};

const tools = (await rpc("tools/list")).result.tools.map((t) => t.name);
const routes = {};
for (const name of tools) {
  if (!ARGS[name]) { routes[name] = null; continue; }
  const r = (await rpc("tools/call", { name, arguments: ARGS[name] })).result;
  const url = r.structuredContent?.site_url ?? "";
  routes[name] = r.isError ? `error: ${r.content[0].text}` : ((/\/(#[a-z-]+)/.exec(url) || [])[1] ?? (url.endsWith("/") ? "/" : url));
}
console.log(JSON.stringify({ tools, routes, connector_routes: ROUTES }));
