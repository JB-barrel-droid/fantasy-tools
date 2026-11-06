// JEG-1029: the connector's risers_fallers, compare_trade by_source and audit_values read the page's own
// modules (app/v2/movers.js, trade.js, audit-pie.js, audit-source.js) on what get-values returns
// (include=series, prior, audit; get-values/analysis.ts). This file loads those modules and turns
// get-values' blocks into the inputs the page hands them. No value math: every number is get-values'
// or the page module's. Pure functions, no Deno APIs, so tests run it under node.

import type { ValuesResponse } from "./tools.ts";

// deno-lint-ignore no-explicit-any
type Any = any;

/** The page modules the analyses read, each the site's own file. */
export interface PageModules {
  movers: Any | null;
  trade: Any | null;
  auditPie: Any | null;
  auditSource: Any | null;
}

/** The files and the global each one publishes. */
export const PAGE_MODULE_FILES: Record<keyof PageModules, { file: string; global: string; check: string }> = {
  movers: { file: "v2/movers.js", global: "TradeValueMovers", check: "buildMovers" },
  trade: { file: "v2/trade.js", global: "TradeValueTrade", check: "compareTrade" },
  auditPie: { file: "v2/audit-pie.js", global: "AuditPie", check: "computeChecks" },
  auditSource: { file: "v2/audit-source.js", global: "DDFAuditSource", check: "build" },
};

/**
 * Run one page module's source with a stand-in window (no DOM: the modules' render code is never called,
 * and their event hooks attach to a no-op). Returns the API the module publishes, or null.
 */
export function evalPageModule(source: string, name: keyof PageModules): Any | null {
  const meta = PAGE_MODULE_FILES[name];
  const sandbox: Any = { addEventListener() {}, removeEventListener() {} };
  try {
    // A body without `module` in scope, so a module's CommonJS branch is skipped and it publishes on the window.
    new Function("window", "globalThis", source)(sandbox, sandbox);
  } catch (e) {
    console.error(`${meta.file} threw while loading:`, String((e as Error)?.message ?? e));
  }
  const api = sandbox[meta.global];
  return api && typeof api[meta.check] === "function" ? api : null;
}

/** get-values with include=series,prior,audit (only the blocks asked for are present). */
export interface AnalysisResponse extends ValuesResponse {
  series?: Record<string, Record<string, number>>;
  prior?: {
    available: boolean;
    reason: string | null;
    current_week: number | null;
    prior_week: number | null;
    series: Record<string, { available: boolean; reason: string | null; values?: Record<string, number>; current_values?: Record<string, number> }>;
  };
  audit?: Any;
}

export type FetchAnalysis = (
  scoring: string,
  teams: number,
  superflex: number,
  league: Record<string, unknown> | undefined,
  week: number | null | undefined,
  includes: string[],
) => Promise<AnalysisResponse>;

export interface AnalysisDeps {
  fetchAnalysis: FetchAnalysis | null;
  modules: PageModules | null;
}

// The page's row for one player: {player_key, name, pos, values} (TradeValueCurveControls.getRows()).
export interface PageRow {
  player_key: number;
  name: string;
  pos: string;
  values: Record<string, number>;
}

/** Page rows in the engine's order (by DDF Value, best first, as get-values orders its players). */
export function pageRows(data: AnalysisResponse): PageRow[] {
  const series = data.series ?? {};
  return data.players.map((p) => ({
    player_key: p.player_key, name: p.name, pos: p.pos, values: { ...(series[String(p.player_key)] ?? {}) },
  }));
}

// The series names a reader sees (v2.js groupSeriesName / plainSeries), short.
export const SERIES_LABELS: Record<string, string> = {
  ddf_value: "DDF Value",
  ddf_value_charts: "DDF Value (charts)",
  ddf_value_projections: "DDF Value (projections)",
  fantasycalc: "FantasyCalc chart (Indexed)",
  usatoday: "USA Today chart (Indexed)",
  fantasypros: "FantasyPros chart (Indexed)",
  cbs: "CBS Sports chart (Indexed)",
  espn: "ESPN · Our value",
  cbsros: "CBS rest of season · Our value",
  razzball: "Razzball · Our value",
};

/** getPriorWeek(series)'s shape, from get-values' prior block (what movers.js deltaFor reads). */
export function priorFor(data: AnalysisResponse, key: string): Any {
  const block = data.prior;
  const entry = block?.series?.[key];
  if (!block || !entry) return { available: false, reason: block?.reason || "no prior week" };
  if (!entry.available) {
    return { available: false, reason: entry.reason, currentWeek: block.current_week, priorWeek: block.prior_week };
  }
  return {
    available: true, values: entry.values ?? {}, ...(entry.current_values ? { currentValues: entry.current_values } : {}),
    currentWeek: block.current_week, priorWeek: block.prior_week,
  };
}

/** getInspection()'s shape, from get-values' audit block (what audit-pie.js / audit-source.js read). */
export function inspectionOf(data: AnalysisResponse): Any {
  const a = data.audit ?? {};
  return { setting: a.setting ?? null, valuePipeline: a.valuePipeline ?? null, players: a.players ?? {},
    rows: a.rows ?? {}, excluded: a.excluded ?? [] };
}

// The page's default Compare a trade series (v2.js pageDefault("compare")): DDF Value, then each
// published chart's Indexed series, in the engine's source order.
export const COMPARE_SERIES = ["ddf_value", "fantasycalc", "usatoday", "fantasypros", "cbs"];

const r1 = (n: number) => Math.round(n * 10) / 10;
export const fmtNet = (n: number) => {
  const text = n.toFixed(1);
  return text === "-0.0" ? "+0.0" : (n >= 0 ? "+" : "") + text;
};

/** Movers rows, slim: what the reply shows and returns. */
export function slimMover(m: Any) {
  return { player_key: m.row.player_key, name: m.row.name, pos: m.row.pos, before: r1(m.before), now: r1(m.current), delta: r1(m.delta) };
}

export function slimDisagreement(d: Any) {
  return {
    player_key: d.row.player_key, name: d.row.name, pos: d.row.pos, moved: d.moved, direction: d.direction,
    market_delta: r1(d.market.delta), projections_delta: r1(d.projections.delta), read: d.read,
  };
}
