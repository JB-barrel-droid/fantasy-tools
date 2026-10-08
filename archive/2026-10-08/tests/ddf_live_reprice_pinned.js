#!/usr/bin/env node
// Pinned regression test: the browser's live two-tier repricing at the 0.15
// reference share must reproduce the pipeline-baked DDF leg values.
//
// Usage: node ddf_live_reprice_pinned.js
// Exit 0 if all sources reproduce their baked legs within tolerance.
"use strict";
const fs = require("fs");
const path = require("path");

// Headless (JEG-29): alias window -> globalThis before loading the widget.
globalThis.window = globalThis;

const ROOT = path.join(__dirname, "..");
require(path.join(ROOT, "app", "trade-value-chart", "assets", "value-model.js"));
require(path.join(ROOT, "app", "trade-value-chart", "assets", "curve-widget.js"));

const TwoTier = globalThis.TradeValueTwoTier;
const POSITIONS = ["QB", "RB", "WR", "TE"];
const SHARE = 0.15;
const TOL = 1e-6;

const SPECS = [
  {source: "cbsros", legPath: "data/ddf-two-tier/ddf-20260930-cbsros-ppr-12t-0p15/ddf_leg_cbsros.json", tol: 1e-6},
  {source: "razzball", legPath: "data/ddf-two-tier/ddf-20261001-razzball-ppr-12t-0p15/ddf_leg_razzball.json", tol: 1e-6},
  // ESPN anchor: the live twoTierConfig path (legacy bench mix, surplus
  // pies, feasible-share fallback). Tolerance is 0.1, not 1e-6, because
  // the fixture's espn natives are rounded to 2 decimals while the leg
  // carries full precision -- the observed rounding-only residual is
  // ~0.03. A logic regression (wrong pool/mix/pie/share) errs by >> 0.1.
  {source: "espn", legPath: "data/ddf-two-tier/ddf-20260930-espn-ppr-12t-0p15/ddf_leg.json", tol: 0.1},
];

function main() {
  const fixture = JSON.parse(fs.readFileSync(
    path.join(ROOT, "data", "fixtures", "current", "comparison-sources-data.json"), "utf8"));
  const slugToKey = fixture.player_keys || {};
  let failed = false;

  for (const spec of SPECS) {
    const leg = JSON.parse(fs.readFileSync(path.join(ROOT, spec.legPath), "utf8"));
    const combo = fixture.sources?.[spec.source]?.combos?.["full_12"];
    if (!combo) {
      console.error(`${spec.source}: fixture combo missing`);
      failed = true;
      continue;
    }

    const legByKey = new Map();
    for (const v of leg.values) legByKey.set(v.player_key, v);

    const lists = {QB: [], RB: [], WR: [], TE: []};
    for (const [slug, ppg] of Object.entries(combo.native || {})) {
      const key = slugToKey[slug];
      const lv = legByKey.get(key);
      if (key == null || !lv || !Number.isFinite(ppg)) continue;
      if (!POSITIONS.includes(lv.pos)) continue;
      lists[lv.pos].push({id: key, x: ppg});
    }

    const pies = {};
    POSITIONS.forEach(pos => {
      pies[pos] = Number(combo.index_total?.[pos]?.target_total);
    });

    let pool;
    try {
      // Legacy fixed bench mix, teams-scaled (matches the pipeline legs).
      const benchMix = TwoTier.legacyBenchMixFor(12);
      pool = TwoTier.buildPositionTiers(lists, {
        teams: 12,
        slots: {...TwoTier.REF_SLOTS},
        flexCount: TwoTier.REF_FLEX_COUNT,
        flexEligible: [...TwoTier.REF_FLEX_ELIGIBLE],
        benchMix,
      });
    } catch (e) {
      console.error(`${spec.source}: buildPositionTiers threw: ${e.message}`);
      failed = true;
      continue;
    }

    const shares = TwoTier.skillBenchShares(SHARE);
    const raw = new Map();
    POSITIONS.forEach(pos => {
      // Pie is the tier surplus (same as the pipeline legs). Calibration
      // uses the shared feasible-share fallback -- the test exercises the
      // real TwoTier.calibratePositionFeasible, not a replication.
      const pie = pool.tiers[pos]?.surplus;
      const cal = TwoTier.calibratePositionFeasible(pool.tiers[pos], pie,
        TwoTier.skillBenchShare(shares, pos), pos);
      (lists[pos] || []).forEach(d => {
        raw.set(d.id, TwoTier.priceForProjection(d.x, cal));
      });
    });
    let mx = 0;
    raw.forEach(v => { if (v > mx) mx = v; });
    const scale = mx > 0 ? 70 / mx : 1;

    let maxAbsErr = 0, nCompared = 0;
    const errs = [];
    const tol = spec.tol || TOL;
    for (const v of leg.values) {
      const live = raw.get(v.player_key);
      if (live == null) continue;
      const err = Math.abs(live * scale - v.value);
      if (err > maxAbsErr) maxAbsErr = err;
      nCompared++;
      if (err > tol && errs.length < 5) {
        errs.push(`key=${v.player_key} baked=${v.value} live=${(live*scale).toFixed(6)} err=${err.toExponential(1)}`);
      }
    }
    console.log(`${spec.source}: n=${nCompared} maxAbsErr=${maxAbsErr.toExponential(2)} (tol ${tol})`);
    if (errs.length) {
      console.error(`  FAILURES:\n  ${errs.join("\n  ")}`);
      failed = true;
    }
  }

  if (failed) {
    console.error("PINNED REPRICE FAILED");
    process.exit(1);
  }
  console.log("PINNED: browser live two-tier at 0.15 reproduces baked legs.");
}

main();
