#!/usr/bin/env node
// JEG-616: headless runner for the edge function's pipeline logic.
// Loads value-model.js (no browser), reads the bundle from dist/, and runs
// ValueModel.runValuePipeline() with the same logic as the Supabase edge
// function. Outputs {player_key: blended_value} as JSON to stdout.
//
// Replicates the engine page's source eligibility logic:
// - Chart sources are excluded if their vintage week < current content week
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

// Content-week calendar (product-data.js).
const CONTENT_WEEK_1_START_UTC = Date.UTC(2026, 8, 8); // Tue 2026-09-08
const CONTENT_WEEK_MAX = 18;
const DAY_MS = 86400000;

function contentWeekForDay(day) {
  if (!day) return null;
  const [y, m, d] = day.split("-").map(Number);
  const days = Math.round((Date.UTC(y, m - 1, d) - CONTENT_WEEK_1_START_UTC) / DAY_MS);
  if (days < 0) return 1;
  return Math.min(Math.max(Math.floor(days / 7) + 1, 1), CONTENT_WEEK_MAX);
}

function todayIso() {
  // The test pins the content-week clock to the served data's week (JEG-982), as the page's
  // window.TRADE_VALUE_TODAY does; the deployed function has no such override and uses the real date.
  if (process.env.TRADE_VALUE_TODAY) return process.env.TRADE_VALUE_TODAY;
  // ET-aware date.
  try {
    return new Intl.DateTimeFormat("en-CA", {
      timeZone: "America/New_York", year: "numeric", month: "2-digit", day: "2-digit",
    }).format(new Date());
  } catch (e) {
    return new Date().toISOString().slice(0, 10);
  }
}

function isoDay(v) {
  if (!v || typeof v !== "string") return null;
  const m = v.match(/^(\d{4}-\d{2}-\d{2})/);
  return m ? m[1] : null;
}

function parseWeekLabel(value) {
  const m2 = String(value || "").match(/week\s*(\d+)|wk\s*(\d+)/i);
  return m2 ? Number(m2[1] || m2[2]) : null;
}

function sourceVintage(meta) {
  const m = meta && typeof meta === "object" ? meta : {};
  const designated = parseWeekLabel(m.week_designated);
  if (designated) return { week: designated, basis: "week_designated" };
  const vintageWeek = parseWeekLabel(m.content_vintage);
  if (vintageWeek) return { week: vintageWeek, basis: "content_vintage" };
  const dated = [
    ["content_vintage", m.content_vintage],
    ["vintage", m.vintage],
    ["espn_snapshot", m.espn_snapshot],
    ["lineage.raw_vintage", m.lineage && m.lineage.raw_vintage],
    ["fetched_at", m.fetched_at],
  ].find(([, value]) => isoDay(value));
  if (dated) return { week: contentWeekForDay(isoDay(dated[1])), basis: dated[0] };
  return { week: null, basis: null };
}

// Weekly chart sources (curve-widget.js WEEKED_SOURCE_KEYS base set).
const WEEKED_SOURCES = new Set(["usatoday", "fantasycalc", "fantasypros", "cbs"]);

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

// Compute current content week and source freshness.
const currentContentWeek = contentWeekForDay(todayIso());

// Build freshness per source and determine first_load_excluded set.
const freshnessRows = {};
for (const key of PIPELINE_SOURCE_KEYS) {
  const sourceMeta = detail.sources && detail.sources[key];
  if (!sourceMeta) continue;
  const vintage = sourceVintage(sourceMeta);
  const isWeekly = WEEKED_SOURCES.has(key);
  const status = vintage.week === null ? "unknown" : (vintage.week >= currentContentWeek ? "current" : "older");
  freshnessRows[key] = { week: vintage.week, status, isWeekly };
}

// first_load_reference_week: newest vintage among weekly sources, capped at current week.
const weeklyWeeks = Object.entries(freshnessRows)
  .filter(([, r]) => r.isWeekly && r.week !== null)
  .map(([, r]) => r.week);
const referenceWeek = weeklyWeeks.length ? Math.min(Math.max(...weeklyWeeks), currentContentWeek) : null;

// first_load_excluded: weekly sources older than reference week.
const firstLoadExcluded = new Set();
for (const [key, row] of Object.entries(freshnessRows)) {
  if (row.isWeekly && referenceWeek !== null && row.week !== null && row.week < referenceWeek) {
    firstLoadExcluded.add(key);
  }
}

for (const key of PIPELINE_SOURCE_KEYS) {
  const family = PROJECTION_SOURCE_KEYS.includes(key) ? "projection" : "chart";
  const sourceSection = detail.sources && detail.sources[key];

  // Check source hold.
  const hold = sectionHold(sourceSection);

  // Check source validation (string, e.g. "live", "stale").
  const svStatus = sourceValidation[key];
  const isValidationHeld = svStatus !== undefined && svStatus !== "live";

  // Check staleness (chart is older than current content week).
  const isStale = WEEKED_SOURCES.has(key) && freshnessRows[key]?.status === "older";
  const isFirstLoadExcluded = firstLoadExcluded.has(key);
  const isOlderWeek = isStale || isFirstLoadExcluded;

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
