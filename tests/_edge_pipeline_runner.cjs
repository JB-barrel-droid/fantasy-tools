#!/usr/bin/env node
// JEG-616: headless runner for the edge function's pipeline logic.
// Loads value-model.js (no browser), reads the bundle from dist/, and runs
// ValueModel.runValuePipeline() with the same logic as the Supabase edge
// function. Outputs {player_key: blended_value} as JSON to stdout.
//
// Replicates the engine page's source eligibility logic:
// - Chart sources are excluded if their vintage week < the values week (weeks.ts: the newest
//   published chart week, capped at the content week; JEG-1156)
// - Held sources (validation != "live") are included but hidden
// - Source holds (validationHold, promotionHold) override eligibility
//
// Usage:
//   node tests/_edge_pipeline_runner.cjs \
//     --scoring ppr --teams 12 --superflex 0 --dist dist/
//     [--bench 6] [--league '<normalized DDF league JSON>']
//   Needs `node --experimental-strip-types` (it loads the edge function's league.ts).

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
const leagueArg = args.league ? JSON.parse(args.league) : null;
const legacyLeague = { scoring: args.scoring || "ppr", teams: Number(args.teams) || 12,
  ...(Number(args.superflex) ? { roster: { SUPERFLEX: 1 } } : {}) };
let mapped = null; // set once the lineup config is read (the mapping needs its defaults)
const scoring = leagueArg ? leagueArg.scoring : legacyLeague.scoring;
const teams = leagueArg ? Number(leagueArg.teams) : legacyLeague.teams;
const superflex = leagueArg ? (Number(leagueArg.roster && leagueArg.roster.SUPERFLEX) > 0 ? 1 : 0)
  : Number(args.superflex) || 0;
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

// --- Source freshness / eligibility (mirrors product-data.js + curve-widget.js)

// JEG-1156: the week rule is the edge function's own module (supabase/functions/get-values/weeks.ts).
// --today (YYYY-MM-DD) or TRADE_VALUE_TODAY pins the content day; otherwise the New York date.
const { chartWeekPlan, todayIso } = require("../supabase/functions/get-values/weeks.ts");
const contentDay = args.today || process.env.TRADE_VALUE_TODAY || todayIso();

// Hold fields on source sections (validationHold, promotionHold).
const HOLD_FIELDS = ["validationHold", "promotionHold"];

function sectionHold(sourceSection) {
  if (!sourceSection || typeof sourceSection !== "object") return null;
  for (const field of HOLD_FIELDS) {
    const hold = sourceSection[field];
    if (hold && typeof hold === "object" && hold.reason) {
      // JEG-726 / JEG-787 (as in get-values/index.ts): an amber validationHold labels the source but
      // does not hide it from DDF Value. Only red holds (hold_level absent) and promotionHolds hide.
      const isAmber = field === "validationHold" && hold.hold_level === "amber";
      return { reason: hold.reason, field, source: hold.source || null, week: hold.week || null, hidden: !isAmber };
    }
  }
  return null;
}

// --- Pipeline source keys (must match curve-widget.js) ----------------------
const PIPELINE_SOURCE_KEYS = [
  "espn", "cbsros", "razzball", "fantasycalc", "usatoday", "fantasypros", "cbs",
];
const PROJECTION_SOURCE_KEYS = ["espn", "cbsros", "razzball"];
const PPG_FIELD_OF = { espn: "espn_ppg", cbsros: "cbsros_ppg", razzball: "rz_ppg" };

function scoringField(s) {
  return s === "ppr" ? "ppr" : s === "half_ppr" ? "half_ppr" : "standard";
}

// Replicates product-data.js espnProjectsZero(): ESPN considers this player
// listed at 0 (injured/out) even though espn_ppg is absent.
function espnProjectsZero(player) {
  if (player.espn_status === "ineligible") return true;
  if (player.espn_status === "absent") return false;
  if (player.espn_zeroed === true) return true;
  const ppg = player.espn_ppg;
  if (!ppg || typeof ppg !== "object") return false;
  const values = Object.values(ppg);
  return values.length > 0 && values.every(function (v) { return typeof v === "number" && v === 0; });
}

// --- Build pipeline input ---------------------------------------------------
const field = scoringField(scoring);
// The engine page always looks up chart combos at qb1 (qbVariant: "qb1" in
// product-data.js). Superflex values are overlaid separately via
// native_superflex, so the combo key is always qbSlots=1.
const comboQbSlots = 1;

const playerMap = {};
for (const p of players) {
  playerMap[p.player_key] = { pos: p.pos, name: p.name };
}

const sourceValidation = detail.source_validation || {};
const sources = {};
const included = [];
const hiddenKeys = [];

// Which week of charts counts (JEG-1156 option A, weeks.ts).
const weekPlan = chartWeekPlan(detail.sources, PIPELINE_SOURCE_KEYS, contentDay);
const notPublished = new Set(weekPlan.not_published.map((row) => row.key));

for (const key of PIPELINE_SOURCE_KEYS) {
  const family = PROJECTION_SOURCE_KEYS.includes(key) ? "projection" : "chart";
  const sourceSection = detail.sources && detail.sources[key];

  // Check source hold.
  const hold = sectionHold(sourceSection);

  // Check source validation (string, e.g. "live", "stale").
  const svStatus = sourceValidation[key];
  const isValidationHeld = svStatus !== undefined && svStatus !== "live";

  // Not yet published: a weekly chart older than the values week.
  const isOlderWeek = notPublished.has(key);

  // JEG-610 item 2: divergence 'exclude' resolution -> held semantics.
  const divergenceExclusions = (detail.snapshot && Array.isArray(detail.snapshot.divergence_exclusions))
    ? detail.snapshot.divergence_exclusions : [];
  const isDivergenceExcluded = divergenceExclusions.indexOf(key) !== -1;

  // Determine eligibility (mirrors curve-widget.js eligibilityReason).
  // sourceMissingFromData: no source section at all.
  if (!sourceSection) continue;

  // Hold: runs in pipeline but hidden.
  if (hold) {
    // heldBy hold -> run:true, hidden:true
    // (unless not published: compositeKeyOlderWeek + hold is still hidden)
    // Fall through to include but mark hidden.
  }

  // Validation held: run:true, hidden:true.
  if (isValidationHeld && !hold) {
    // validation held sources run in pipeline but are hidden
  }

  // Divergence excluded: run:true, hidden:true (JEG-610).
  if (isDivergenceExcluded && !hold && !isValidationHeld) {
    // Falls through to include but mark hidden.
  }

  // Not yet published for current week: excluded (run:false for chart sources).
  if (isOlderWeek && !hold && !isValidationHeld && !isDivergenceExcluded) {
    continue; // Not eligible
  }

  let values;

  if (family === "chart") {
    const comboKeyStr = ValueModel.sourceComboKey(key, scoring, 12, comboQbSlots);
    const combos = sourceSection && sourceSection.combos;
    const combo = comboKeyStr && combos ? combos[comboKeyStr] : null;
    if (!combo || !combo.native) continue;

    values = {};
    const native = combo.native;
    const pkMap = detail.player_keys;
    for (const [sourceId, val] of Object.entries(native)) {
      const playerKey = pkMap && pkMap[sourceId];
      if (playerKey !== undefined && Number.isFinite(val)) {
        values[playerKey] = val;
      }
    }
    if (superflex && combo.native_superflex) {
      for (const [sourceId, val] of Object.entries(combo.native_superflex)) {
        const playerKey = pkMap && pkMap[sourceId];
        if (playerKey !== undefined && Number.isFinite(val)) {
          values[playerKey] = val;
        }
      }
    }
  } else {
    values = {};
    const ppgField = PPG_FIELD_OF[key];
    for (const p of players) {
      if (key === "espn" && espnProjectsZero(p) && !p.espn_ppg) {
        values[p.player_key] = 0;
        continue;
      }
      const ppgObj = p[ppgField];
      const ppg = ppgObj && ppgObj[field];
      if (ppg !== null && ppg !== undefined && Number.isFinite(ppg)) {
        values[p.player_key] = ppg;
      }
    }
  }

  if (Object.keys(values).length === 0) continue;

  sources[key] = { family: family, status: "included", values: values, label: key };
  included.push(key);

  // Mark as hidden if held, validation-held, or divergence-excluded.
  if ((hold && hold.hidden) || isValidationHeld || isDivergenceExcluded) {
    hiddenKeys.push(key);
  }
}

// --- Load lineup parameters (expected-starts model) -------------------------
let lineupConfig = null;
try {
  lineupConfig = JSON.parse(readFileSync(join(distDir, "assets/lineup-parameters.json"), "utf8"));
} catch (e) {
  // No lineup parameters; fall back to slices mode.
}
mapped = mapLeague(leagueArg || legacyLeague, lineupConfig);
let resolvedLineup = null;
if (lineupConfig && lineupConfig.schema === "lineup-parameters-config/2") {
  resolvedLineup = ValueModel.resolveLineupParameters(lineupConfig, mapped.lineupArgs);
}

// --bench overrides bench_per_team (the negative test's deliberately wrong value).
const setting = { ...mapped.setting };
if (benchOverride !== null) setting.bench_per_team = benchOverride;

const input = {
  setting,
  players: playerMap,
  sources: sources,
  included: included,
  hidden: hiddenKeys,
  lineup: resolvedLineup,
};

// --- Run pipeline -----------------------------------------------------------
const pipeline = ValueModel.runValuePipeline(input);

// --- Output DDF blended values ----------------------------------------------
const output = {};
for (const [pk, row] of Object.entries(pipeline.rows || {})) {
  const blended = row.ddfByVersion && row.ddfByVersion.blended && row.ddfByVersion.blended.value;
  if (typeof blended === "number" && Number.isFinite(blended)) {
    output[pk] = blended;
  }
}

process.stdout.write(JSON.stringify(output));
