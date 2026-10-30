// JEG-1029: the opt-in analysis blocks of a get-values answer (`include=series`, `prior`, `audit`), read
// by the connector's risers_fallers, compare_trade by_source and audit_values tools. Pure functions, no
// Deno APIs: index.ts and the parity runner (tests/_edge_pipeline_runner.cjs) both import this file.
//
// No value math here. series reads the engine's rows the way the page's Player values rows read them
// (curve-widget.js seriesField in the Indexed tab: a published chart's Indexed value, a projection's
// Adjusted value, the three DDF Value versions). prior is curve-widget.js pipelinePrior (VP-8): the same
// league, included set and pie run on the week before's saved inputs, read per series as getPriorWeek
// reads it. audit is the part of getInspection() the two Values auditing sub-tabs read.

import { type Bundle, PIPELINE_SOURCE_KEYS, savedNatives } from "./pipeline.ts";

// deno-lint-ignore no-explicit-any
type Any = any;

/** The include values get-values accepts (a comma list). */
export const INCLUDES = ["charts", "series", "prior", "audit"] as const;
export type Include = typeof INCLUDES[number];

/** Parse `include`: a comma list of INCLUDES; an unknown value is an error, empty means none. */
export function parseIncludes(raw: unknown): { includes: Set<Include>; error?: string } {
  const includes = new Set<Include>();
  if (raw === undefined || raw === null || raw === "") return { includes };
  for (const part of String(raw).split(",").map((s) => s.trim()).filter(Boolean)) {
    if (!(INCLUDES as readonly string[]).includes(part)) {
      return { includes, error: `invalid include: ${part}. Use a comma list of ${INCLUDES.join(", ")}` };
    }
    includes.add(part as Include);
  }
  return { includes };
}

// The published charts, whose page series is the Indexed value (curve-widget.js AS_PUBLISHED_KEYS).
export const CHART_SERIES = ["fantasycalc", "usatoday", "fantasypros", "cbs"];
export const PROJECTION_SERIES = ["espn", "cbsros", "razzball"];
// The DDF Value versions: series key -> the engine's ddfByVersion field (v2.js DDF_VERSIONS).
export const DDF_SERIES: Record<string, string> = {
  ddf_value: "blended",
  ddf_value_charts: "charts",
  ddf_value_projections: "projections",
};

const finite = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v);

// One series' values over a pipeline result: {player_key: value} for every row with a number (zeros
// included), as curve-widget.js seriesValuesFrom / ddfValuesOf.
function seriesValues(result: Any, key: string): Record<string, number> {
  const out: Record<string, number> = {};
  const field = DDF_SERIES[key];
  if (!field && !result?.sources?.[key]) return out;
  for (const [pk, row] of Object.entries((result?.rows ?? {}) as Record<string, Any>)) {
    const value = field ? row.ddfByVersion?.[field]?.value
      : CHART_SERIES.includes(key) ? row.indexed?.[key] : row.adjusted?.[key];
    if (finite(value)) out[pk] = value;
  }
  return out;
}

/** The series a reader can see: the DDF Value versions and every source the run prices that is not held. */
export function visibleSeries(result: Any, hidden: string[]): string[] {
  const sources = PIPELINE_SOURCE_KEYS.filter((key) => result?.sources?.[key] && !hidden.includes(key));
  return [...Object.keys(DDF_SERIES), ...sources];
}

/** include=series: each player's page row values in the Indexed tab, unrounded. {player_key: {key: value}}. */
export function seriesBlock(result: Any, hidden: string[]): Record<string, Record<string, number>> {
  const out: Record<string, Record<string, number>> = {};
  for (const key of visibleSeries(result, hidden)) {
    for (const [pk, value] of Object.entries(seriesValues(result, key))) (out[pk] ??= {})[key] = value;
  }
  return out;
}

export interface PriorSeries {
  available: boolean;
  reason: string | null;
  values?: Record<string, number>;
  /** This week's side over the same included set (getPriorWeek's currentValues): every DDF Value
   *  version, and a source series when some included source has no Week N-1. */
  current_values?: Record<string, number>;
}

export interface PriorBlock {
  available: boolean;
  reason: string | null;
  current_week: number | null;
  prior_week: number | null;
  series: Record<string, PriorSeries>;
}

/**
 * include=prior: the VP-8 prior week. input: buildPipelineInput's result (the run that priced `result`).
 * week: the week priced (null without a week history). served: each source's served week.
 * The page's composite pair needs at least one included source with Week N-1 saved (VP-1.2); a source
 * series needs its own Week N-1 entry and to serve the priced week (frame 22's exact pair).
 * I is the included sources with Week N-1 saved. When that is fewer than `result` counts, this week is
 * re-run on I (curve-widget.js computePipeline runs the current week on I) and every series' current
 * side is read from that run, so a Δ never comes from a source joining or leaving the set.
 */
export function priorBlock(bundle: Bundle, input: Any, result: Any, week: number | null,
  served: Record<string, number | null>, scoring: string): PriorBlock {
  const ValueModel = bundle.ValueModel as Any;
  const hidden: string[] = input.hidden ?? [];
  const keys = visibleSeries(result, hidden);
  const none = (reason: string, current: number | null = week): PriorBlock => ({
    available: false, reason, current_week: current, prior_week: current === null ? null : current - 1,
    series: Object.fromEntries(keys.map((k) => [k, { available: false, reason }])),
  });
  if (week === null || !bundle.history?.index) return none("no week history for this build", null);
  const prior = week - 1;
  const natives: Record<string, Record<number, number>> = {};
  const reasons: Record<string, string> = {};
  for (const key of Object.keys(input.sources ?? {})) {
    const got = savedNatives(bundle, key, prior, scoring);
    if (got.values) natives[key] = got.values;
    else reasons[key] = got.reason!;
  }
  const included = (input.included as string[]).filter((key) => natives[key]);
  if (!included.length) {
    const why = (input.included as string[]).map((key) => `${key}: ${reasons[key] ?? "not run"}`).join("; ");
    return none(`no source has a prior week at this setting (${why})`);
  }
  // This week on I: `result` when every included source has Week N-1; else the same input with the
  // unpaired sources shown, never counted, and its own pie (the page's runPipeline(natives, I)).
  const paired = included.length === (input.included as string[]).length;
  let current = result;
  if (!paired) {
    const now: Record<string, unknown> = {};
    for (const [key, src] of Object.entries((input.sources ?? {}) as Record<string, Any>)) {
      now[key] = { ...src, status: included.includes(key) ? "included" : "excluded" };
    }
    current = ValueModel.runValuePipeline({ ...input, sources: now, included, hidden });
  }
  const sources: Record<string, unknown> = {};
  for (const key of PIPELINE_SOURCE_KEYS) {
    if (!natives[key]) continue;
    const src = (input.sources as Any)[key];
    sources[key] = { ...src, status: included.includes(key) ? "included" : "excluded", values: natives[key] };
  }
  const run = ValueModel.runValuePipeline({ ...input, sources, included, pie: current.pie, hidden });
  const series: Record<string, PriorSeries> = {};
  for (const key of keys) {
    if (DDF_SERIES[key]) {
      series[key] = { available: true, reason: null, values: seriesValues(run, key), current_values: seriesValues(current, key) };
      continue;
    }
    if (Number.isInteger(served[key]) && served[key] !== week) {
      series[key] = { available: false, reason: `serves Week ${served[key]}, not Week ${week}` };
    } else if (!natives[key]) {
      series[key] = { available: false, reason: reasons[key] ?? `not priced in Week ${prior}` };
    } else if (!run.sources?.[key]) {
      series[key] = { available: false, reason: `${key} is not priced on Week ${prior}` };
    } else {
      const values = seriesValues(run, key);
      // Unpaired, `result`'s rows (the series block) are not this week on I: give the current side too.
      series[key] = !Object.keys(values).length
        ? { available: false, reason: `no ${scoring} values for Week ${prior} at this setting` }
        : paired ? { available: true, reason: null, values }
        : { available: true, reason: null, values, current_values: seriesValues(current, key) };
    }
  }
  return { available: true, reason: null, current_week: week, prior_week: prior, series };
}

/**
 * include=audit: what audit-pie.js (Health check) and audit-source.js (Single source) read from
 * getInspection(): the pipeline diagnostics, each source's per-player stages, the rows' per-source
 * values and reasons, and the excluded sources. Nothing is computed here.
 */
export function auditBlock(bundle: Bundle, result: Any, excluded: Array<{ key: string; reason: string }>) {
  const ValueModel = bundle.ValueModel as Any;
  const players: Record<string, Record<string, Any>> = {};
  for (const [key, src] of Object.entries((result.sources ?? {}) as Record<string, Any>)) {
    const out: Record<string, Any> = {};
    for (const [pk, p] of Object.entries((src.players ?? {}) as Record<string, Any>)) {
      out[pk] = { pos: p.pos, role: p.role, rank: p.rank, native: p.native, estimated: !!p.estimated, adjusted: p.adjusted };
    }
    players[key] = out;
  }
  const rows: Record<string, Any> = {};
  for (const [pk, r] of Object.entries((result.rows ?? {}) as Record<string, Any>)) {
    rows[pk] = {
      name: r.name, pos: r.pos, indexed: r.indexed, adjusted: r.adjusted, estimated: r.estimated, reasons: r.reasons,
      ddf: finite(r.ddfByVersion?.blended?.value) ? r.ddfByVersion.blended.value : null,
    };
  }
  return {
    valuePipeline: ValueModel.valuePipelineDiagnostics(result),
    setting: result.setting ?? null,
    excluded,
    players,
    rows,
  };
}
