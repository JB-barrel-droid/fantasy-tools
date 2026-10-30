#!/usr/bin/env node
// JEG-616: headless runner for the edge function's pipeline logic.
// Loads value-model.js (no browser), reads the bundle and the week history from dist/, and runs
// ValueModel.runValuePipeline() on the input the Supabase edge function builds: the source
// eligibility and the week view are the function's own module (supabase/functions/get-values/pipeline.ts,
// JEG-1179), not a copy. Outputs {player_key: blended_value} as JSON to stdout, or
// {values, week} with --with-week 1 (week: the week priced, its sources and missing_sources).
//
// Usage:
//   node tests/_edge_pipeline_runner.cjs \
//     --scoring ppr --teams 12 --superflex 0 --dist dist/
//     [--bench 6] [--league '<normalized DDF league JSON>'] [--week 8]
//     [--history-index <index.json in place of dist's>] [--with-week 1]
//     [--basis <basis= text>] [--ov <ov= text>]
//   JEG-1225: --basis and --ov are a share link's value context, read by app/v2/ddf-value-link.js and applied by
//   supabase/functions/get-values/value-context.ts, the modules the deployed function uses. The values are then DDF
//   Value after the overrides, and --with-week 1 adds `value_context` (the basis and the overrides applied).
//     [--include series,prior,audit]   (JEG-1029: adds get-values' analysis blocks, analysis.ts)
//     [--mutate two-weeks-back]        (test only: a deliberately broken prior week)
//     [--drop-entry 7:fantasycalc]     (test only: that week's saved entry for that source is absent)
//   Needs `node --experimental-strip-types` (it loads the edge function's .ts modules).

"use strict";

const { readFileSync } = require("fs");
const { resolve, join } = require("path");

// --- Parse args -------------------------------------------------------------
const args = {};
for (let i = 2; i < process.argv.length; i += 2) {
  args[process.argv[i].replace(/^--/, "")] = process.argv[i + 1];
}
// JEG-1031: with --league the setting and lineup come from the edge function's own mapping module
// (supabase/functions/get-values/league.ts), so the parity test exercises the shipped mapping.
const { mapLeague } = require("../supabase/functions/get-values/league.ts");
// JEG-1179: source eligibility and the week view come from the function's own pipeline.ts.
const { buildPipelineInput, excludedSources, parseWeek, planWeek, todayIso } = require("../supabase/functions/get-values/pipeline.ts");
// JEG-1225: the caller's basis and overrides, through the function's own value-context.ts and the site's link reader.
const { applyOverrides, basisConfigOf, overrideSeries, readValueContext } = require("../supabase/functions/get-values/value-context.ts");
const ValueLink = require("../app/v2/ddf-value-link.js");
const read = readValueContext(ValueLink, args.basis ?? null, args.ov ?? null);
if (!read.ok) {
  process.stderr.write(read.error + "\n");
  process.exit(1);
}
const context = read.context;
// JEG-1029: the opt-in analysis blocks come from the function's own analysis.ts.
const { auditBlock, parseIncludes, priorBlock, seriesBlock } = require("../supabase/functions/get-values/analysis.ts");
const leagueArg = args.league ? JSON.parse(args.league) : null;
const legacyLeague = { scoring: args.scoring || "ppr", teams: Number(args.teams) || 12,
  ...(Number(args.superflex) ? { roster: { SUPERFLEX: 1 } } : {}) };
let mapped = null; // set once the lineup config is read (the mapping needs its defaults)
const distDir = resolve(args.dist || "dist");
const benchOverride = args.bench !== undefined ? Number(args.bench) : null;

// --- Load value-model.js via require (CJS, works with UMD pattern) ----------
const ValueModel = require(join(distDir, "assets/value-model.js"));
if (!ValueModel || typeof ValueModel.runValuePipeline !== "function") {
  process.stderr.write("ValueModel.runValuePipeline not found\n");
  process.exit(1);
}

// --- Load bundle ------------------------------------------------------------
const detail = JSON.parse(
  readFileSync(join(distDir, "assets/comparison-sources-data.json"), "utf8"),
);

// Extract players-data from index.html.
const html = readFileSync(join(distDir, "index.html"), "utf8");
const match = html.match(/id="players-data"[^>]*>([\s\S]*?)<\/script>/);
if (!match) {
  process.stderr.write("players-data island not found in dist/index.html\n");
  process.exit(1);
}
const playersDoc = JSON.parse(match[1]);
const players = playersDoc.players;

// --- Week history (JEG-1179): the index and every saved week the build published ---------------
// --history-index replaces assets/history/index.json (the parity test's synthetic week transition).
let history = null;
try {
  const indexPath = args["history-index"] || join(distDir, "assets/history/index.json");
  const index = JSON.parse(readFileSync(indexPath, "utf8"));
  const docs = {};
  for (const [week, meta] of Object.entries(index.weeks || {})) {
    try {
      const doc = JSON.parse(readFileSync(join(distDir, meta.file), "utf8"));
      if (doc.week === Number(week)) docs[week] = doc;
    } catch (e) {
      // A week the build did not publish stays unloaded, as a failed fetch does in the function.
    }
  }
  // --drop-entry WEEK:SOURCE: the history saved no entry for SOURCE in WEEK (JEG-1029's unpaired prior week).
  if (args["drop-entry"]) {
    const [week, key] = args["drop-entry"].split(":");
    if (!docs[week]?.sources?.[key]) throw new Error(`--drop-entry: no Week ${week} ${key} entry to drop`);
    delete docs[week].sources[key];
  }
  history = { index, docs };
} catch (e) {
  if (args["drop-entry"]) throw e;
  // No week history: the calendar rule applies, as on the page.
}

// --- Load lineup parameters (expected-starts model) -------------------------
let lineupConfig = null;
try {
  lineupConfig = JSON.parse(readFileSync(join(distDir, "assets/lineup-parameters.json"), "utf8"));
} catch (e) {
  // No lineup parameters; fall back to slices mode.
}
mapped = mapLeague(leagueArg || legacyLeague, lineupConfig);

// --- Build pipeline input with the function's own module (supabase/functions/get-values/pipeline.ts)
// The test pins the content-week clock to the served data's week (JEG-982), as the page's
// window.TRADE_VALUE_TODAY does; the deployed function reads the real date (or DDF_TODAY).
const today = process.env.TRADE_VALUE_TODAY || todayIso();
const bundle = { detail, players, ValueModel, lineupConfig, history };
const requestedWeek = parseWeek(args.week);
if (Number.isNaN(requestedWeek)) {
  process.stderr.write(`invalid --week ${args.week}\n`);
  process.exit(1);
}
const plan = planWeek(bundle, mapped, requestedWeek, today);
if (!plan.ok) {
  if (args["with-week"]) {
    process.stdout.write(JSON.stringify({ error: plan.error, weeks: plan.weeks, default_week: plan.default_week }));
    process.exit(0);
  }
  process.stderr.write(plan.error + "\n");
  process.exit(1);
}
const built = buildPipelineInput(bundle, mapped, plan);

// --bench overrides bench_per_team (the negative test's deliberately wrong value).
const setting = { ...built.setting };
if (benchOverride !== null) setting.bench_per_team = benchOverride;
const input = { ...built, setting, basisConfig: basisConfigOf(context) };

// --- Run pipeline -----------------------------------------------------------
const pipeline = ValueModel.runValuePipeline(input);

// --- Output DDF blended values (after the caller's overrides) -----------------
const own = applyOverrides(ValueModel, pipeline, context);
const output = {};
for (const [pk, { value }] of Object.entries(own.values)) {
  if (typeof value === "number" && Number.isFinite(value)) {
    output[pk] = value;
  }
}

const valueContext = {
  basis: context.basis, basis_applied: context.basis ? Boolean(pipeline.basis && pipeline.basis.applied) : true,
  overrides_applied: own.applied.length, overrides_not_priced: own.not_priced.map(Number),
};
// JEG-1029: --include adds the analysis blocks the function adds (series, prior, audit).
const parsedInclude = parseIncludes(args.include);
if (parsedInclude.error) {
  process.stderr.write(parsedInclude.error + "\n");
  process.exit(1);
}
const analysis = {};
const includes = parsedInclude.includes;
if (includes.has("series")) analysis.series = overrideSeries(seriesBlock(pipeline, input.hidden || []), own);
// --mutate two-weeks-back (tests/test_connector_analyses.py's broken variant): the "prior week" priced on
// Week N-2's inputs but labelled Week N-1, so the parity check must fail on the values, not the label.
if (includes.has("prior")) {
  if (args.mutate === "two-weeks-back") {
    const prior = priorBlock(bundle, input, pipeline, plan.week - 1, plan.served || {}, mapped.scoring);
    analysis.prior = { ...prior, current_week: plan.week, prior_week: plan.week - 1 };
  } else {
    analysis.prior = priorBlock(bundle, input, pipeline, plan.week, plan.served || {}, mapped.scoring);
  }
}
if (includes.has("audit")) {
  const excluded = excludedSources(pipeline, input);
  analysis.audit = auditBlock(bundle, pipeline, excluded);
}
const withWeek = args["with-week"] || includes.size;
process.stdout.write(JSON.stringify(withWeek
  ? { values: output, week: built.week, ...(args["with-week"] ? { value_context: valueContext } : {}), ...analysis }
  : output));
