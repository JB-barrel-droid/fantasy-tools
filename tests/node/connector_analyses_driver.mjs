// JEG-1029: runs the connector's analyses (risers_fallers, compare_trade by_source, audit_values) on
// get-values' analysis blocks, and the page's own modules (app/v2/movers.js, trade.js, audit-pie.js,
// audit-source.js) on an independent pricing of the same league, and prints both in one shape for
// tests/test_connector_analyses.py to compare. No network, no browser.
//
//   node --experimental-strip-types --no-warnings tests/node/connector_analyses_driver.mjs \
//     --edge <edge runner output with --include series,prior,audit> \
//     --reference <{rows, prior}: value_reference's page rows and prior week>
//     --scoring ppr --teams 12 --superflex 0 [--swap 1]
//
// tools: what the endpoint answers (handleRpc -> tools.ts -> analyses.ts), its structuredContent.
// page:  the page modules run directly on the reference rows, slimmed the way the tools slim them.
// --swap 1 (a broken variant): the compare tool is called with its sides swapped.
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { handleRpc } from "../../supabase/functions/mcp/rpc.ts";
import {
  COMPARE_SERIES, evalPageModule, PAGE_MODULE_FILES, slimDisagreement, slimMover,
} from "../../supabase/functions/mcp/analyses.ts";

const require = createRequire(import.meta.url);
const args = {};
for (let i = 2; i < process.argv.length; i += 2) args[process.argv[i].replace(/^--/, "")] = process.argv[i + 1];
const edge = JSON.parse(readFileSync(args.edge, "utf8"));
const reference = JSON.parse(readFileSync(args.reference, "utf8"));
const modules = Object.fromEntries(Object.entries(PAGE_MODULE_FILES)
  .map(([name, m]) => [name, evalPageModule(readFileSync(new URL(`../../app/${m.file}`, import.meta.url), "utf8"), name)]));
for (const [name, api] of Object.entries(modules)) if (!api) throw new Error(`page module ${name} did not load`);

// get-values' player list: DDF Value best first (rounded to 0.1 as the endpoint returns it), names from
// the audit block's rows (the engine's own rows).
const r1 = (n) => Math.round(n * 10) / 10;
const players = Object.entries(edge.values)
  .map(([pk, v]) => ({ player_key: Number(pk), name: edge.audit.rows[pk].name, pos: edge.audit.rows[pk].pos, value: r1(v), tier: "starter" }))
  .sort((a, b) => b.value - a.value || a.player_key - b.player_key);
const base = (scoring, teams, superflex) => ({ attribution: "Data Driven Football", as_of: "fixture",
  setting: { scoring, teams, superflex }, players, sources_included: [], sources_excluded: [], week: edge.week.week,
  default_week: edge.week.default_week, weeks: edge.week.weeks, missing_sources: edge.week.missing_sources });
const fetchValues = async (...a) => base(...a);
const fetchAnalysis = async (s, t, sf, league, week, includes) => ({
  ...base(s, t, sf), ...(includes.includes("series") ? { series: edge.series } : {}),
  ...(includes.includes("prior") ? { prior: edge.prior } : {}), ...(includes.includes("audit") ? { audit: edge.audit } : {}),
});
const deps = { codec: require("../../app/v2/ddf-state.js"), siteOrigin: "https://site.test" };
const finderDeps = { finder: require("../../app/v2/finder.js"), fetchCharts: fetchValues, analysis: { fetchAnalysis, modules } };
const [scoring, teams, superflex] = [args.scoring ?? "ppr", Number(args.teams ?? 12), Number(args.superflex ?? 0)];
async function tool(name, extra) {
  const r = await handleRpc({ jsonrpc: "2.0", id: 1, method: "tools/call",
    params: { name, arguments: { scoring, teams, superflex: Boolean(superflex), ...extra } } }, fetchValues, deps, finderDeps);
  if (r.error || r.result.isError) throw new Error(`${name}: ${JSON.stringify(r.error ?? r.result.content)}`);
  return r.result.structuredContent;
}

// The page's rows from the reference: the same players in the same order, the reference's series values.
const refRows = players.map((p) => ({ player_key: p.player_key, name: p.name, pos: p.pos,
  values: Object.fromEntries(Object.entries(reference.rows[String(p.player_key)] ?? {}).filter(([, v]) => typeof v === "number")) }));
const refPrior = (key) => reference.prior[key] ?? { available: false, reason: "no prior week" };

const M = modules.movers;
const out = { tools: { risers: {}, compare: [], health: null, source: {} }, page: { risers: {}, compare: [], health: null, source: {} } };
const LIMIT = 25;
const slimMovers = (v) => (v.available
  ? { available: true, current_week: v.currentWeek, prior_week: v.priorWeek, risers: v.risers.slice(0, LIMIT).map(slimMover),
    fallers: v.fallers.slice(0, LIMIT).map(slimMover), counts: { compared: v.compared, unchanged: v.unchanged, no_prior: v.noPrior,
      no_current: v.noCurrent, risers: v.risers.length, fallers: v.fallers.length } }
  : { available: false });
for (const series of M.SERIES) {
  const t = await tool("risers_fallers", { series, limit: LIMIT, disagreements: series === "ddf_value" });
  out.tools.risers[series] = t.available
    ? { available: true, current_week: t.current_week, prior_week: t.prior_week, risers: t.risers, fallers: t.fallers, counts: t.counts }
    : { available: false };
  out.page.risers[series] = slimMovers(M.buildMovers(refRows, series, refPrior(series)));
  if (series === "ddf_value") {
    out.tools.disagreements = t.disagreements;
    const d = M.buildDisagreements(refRows, refPrior("ddf_value_charts"), refPrior("ddf_value_projections"));
    out.page.disagreements = d.available
      ? { available: true, compared: d.compared, market: d.market.slice(0, LIMIT).map(slimDisagreement),
        projections: d.projections.slice(0, LIMIT).map(slimDisagreement), market_total: d.market.length, projections_total: d.projections.length }
      : { available: false, reason: d.reason };
  }
}

// Trades: picked by rank so each fixture has them; one includes a player a projection does not price.
const at = (i) => players[i];
const noCbsros = players.find((p) => p.value > 5 && edge.series[String(p.player_key)]?.cbsros === undefined);
const TRADES = [
  [[at(0)], [at(1), at(6)]],
  [[at(3), at(12)], [at(2)]],
  [[at(20), at(40)], [at(15)]],
  ...(noCbsros ? [[[noCbsros], [at(30)]]] : []),
];
const T = modules.trade;
for (const [give, get] of TRADES) {
  const [a, b] = args.swap ? [get, give] : [give, get];
  const t = await tool("compare_trade", { side_a: a.map((p) => p.name).join(", "), side_b: b.map((p) => p.name).join(", "), by_source: true });
  out.tools.compare.push({ rows: t.rows.map(({ series, give, get, net }) => ({ series, give, get, net })), verdict: t.verdict });
  const rowsOf = (list) => list.map((p) => refRows.find((r) => r.player_key === p.player_key));
  const { rows } = T.compareTrade(rowsOf(give), rowsOf(get), COMPARE_SERIES);
  const v = T.tradeVerdict(rows, "ddf_value");
  const n = (x) => (x === null || x === undefined ? null : r1(x));
  out.page.compare.push({ rows: rows.map((r) => ({ series: r.key, give: n(r.give), get: n(r.receive), net: n(r.net) })),
    verdict: { kind: v.kind, series: "ddf_value", net: n(v.net), agree: v.agreeKeys ?? [], against: v.againstKeys ?? [], incomplete: v.incompleteKeys ?? [] } });
}

// Audit: the tool against the page modules on the same inspection (the reference side of the audit is the
// diagnostics comparison in the Python test).
const inspection = { setting: edge.audit.setting, valuePipeline: edge.audit.valuePipeline, players: edge.audit.players,
  rows: edge.audit.rows, excluded: edge.audit.excluded };
out.tools.health = (await tool("audit_values", { view: "health" })).checks.map(({ id, status, detail }) => ({ id, status, detail }));
const P = modules.auditPie;
const model = P.extract(inspection);
P.computeFlags(model);
out.page.health = P.computeChecks(model).map((c) => ({ id: c.id, status: c.status, detail: c.reason ?? null }));
for (const source of modules.auditSource.SOURCES.map((s) => s.key)) {
  const t = await tool("audit_values", { view: "source", source, limit: 15 });
  out.tools.source[source] = { totals: t.totals, shown: t.shown, rows: t.rows.map(({ player_key, published, indexed, adjusted }) => ({ player_key, published, indexed, adjusted })) };
  const m = modules.auditSource.build(inspection, source, "ALL");
  const n = (x) => (x === null ? null : r1(x));
  out.page.source[source] = { totals: { published: r1(m.totals.published), indexed: m.stages.indexed.exists ? r1(m.totals.indexed) : null, adjusted: r1(m.totals.adjusted) },
    shown: m.shown, rows: m.rows.slice(0, 15).map((r) => ({ player_key: Number(r.key), published: n(r.published), indexed: n(r.indexed), adjusted: n(r.adjusted) })) };
}
console.log(JSON.stringify(out));
