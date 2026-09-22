#!/usr/bin/env node
// Test harness: loads curve-widget.js in Node (no DOM) and runs two-tier
// commands. Usage: node two_tier_harness.js <command> < payload.json
// The widget's IIFE assigns globalThis.TradeValueTwoTier before its root
// early-return, so requiring it here only exercises the pure helpers.
"use strict";
const fs = require("fs");
const path = require("path");

require(path.join(__dirname, "..", "app", "trade-value-chart", "assets", "curve-widget.js"));

const T = globalThis.TradeValueTwoTier;
if (!T) {
  console.error("TradeValueTwoTier test surface missing");
  process.exit(1);
}
const P = globalThis.TradeValueCurvePause;

const cmd = process.argv[2];
const input = JSON.parse(fs.readFileSync(0, "utf8"));
let out;

const trySolve = v => {
  try {
    const r = T.solveTierPrices(v.a_b, v.b_b, v.a_s, v.b_s, v.pie, v.pos || "?", v.bench_share);
    return {pb: r.pb, ps: r.ps};
  } catch (e) {
    return {error: String((e && e.message) || e)};
  }
};

switch (cmd) {
  case "solve":
    out = input.vectors.map(trySolve);
    break;
  case "slice":
    out = input.vectors.map(v => T.sliceExposures(v.x, v.rw, v.rs, v.tau));
    break;
  case "interval":
    out = input.vectors.map(v =>
      T.feasibleBenchShareInterval(v.a_b, v.b_b, v.a_s, v.b_s, v.pie, v.pos || "?"));
    break;
  case "slider":
    out = T.sliderBounds(input.intervals);
    break;
  case "display": {
    const raw = new Map(Object.entries(input.raw));
    const above = input.above ? k => !!input.above[k] : () => true;
    const {values, scale} = T.normalizeThenRound(raw, above);
    out = {values: Object.fromEntries(values), scale};
    break;
  }
  case "benchmixdetail": {
    const teams = input.teams, slots = input.slots || {...T.REF_SLOTS};
    const flexEligible = input.flexEligible || [...T.REF_FLEX_ELIGIBLE];
    const flexCount = input.flexCount === undefined ? T.REF_FLEX_COUNT : input.flexCount;
    const ranked = {};
    for (const pos of T.POSITIONS) ranked[pos] = (input.pools[pos] || []).slice().sort((a,b)=>b-a);
    const taken = {}, flexHits = {};
    for (const pos of T.POSITIONS) { taken[pos] = teams * (slots[pos] || 0); flexHits[pos] = 0; }
    const fp = [];
    for (const pos of T.POSITIONS) {
      if (!flexEligible.includes(pos)) continue;
      for (const x of ranked[pos].slice(taken[pos])) fp.push([x, pos]);
    }
    fp.sort((a,b)=>b[0]-a[0]);
    for (const [, pos] of fp.slice(0, teams*flexCount)) flexHits[pos] += 1;
    const starters = {}, floor = {};
    for (const pos of T.POSITIONS) {
      starters[pos] = taken[pos] + flexHits[pos];
      floor[pos] = T.tailFloor(ranked[pos]);
    }
    out = {mix: T.benchMixFor(teams,
             input.benchSlots === undefined ? T.REF_BENCH_SLOTS : input.benchSlots,
             slots, flexCount, flexEligible, input.pools),
           starters, floor};
    break;
  }
  case "benchmix":
    out = T.benchMixFor(
      input.teams,
      input.benchSlots === undefined ? T.REF_BENCH_SLOTS : input.benchSlots,
      input.slots || {...T.REF_SLOTS},
      input.flexCount === undefined ? T.REF_FLEX_COUNT : input.flexCount,
      input.flexEligible || [...T.REF_FLEX_ELIGIBLE],
      input.pools);
    break;
  case "tailfloor":
    out = T.tailFloor(input.xs);
    break;
  case "multipool":
    // configs: [{name, lists, cfg, pies, shares}]
    // Verifies 0.15 feasibility per config plus slider/slider-rounding math.
    out = input.configs.map(c => {
      let pool = null, poolError = null;
      try {
        pool = T.buildPositionTiers(c.lists, c.cfg);
      } catch (e) {
        poolError = String((e && e.message) || e);
      }
      const intervals = {}, cals = {};
      if (pool) {
        for (const pos of T.POSITIONS) {
          const t = pool.tiers[pos];
          intervals[pos] = t
            ? T.feasibleBenchShareInterval(t.aBench, t.bBench, t.aStart, t.bStart, c.pies[pos], pos)
            : null;
        }
      }
      const bounds = T.sliderBounds(intervals);
      let rounded = null, endpointsFeasible = null, recInside = null;
      if (bounds) {
        rounded = T.inwardBounds(bounds[0], bounds[1]);
        endpointsFeasible = rounded.map(s =>
          T.POSITIONS.every(pos => {
            const t = pool.tiers[pos];
            return T.feasibleAt(t.aBench, t.bBench, t.aStart, t.bStart, c.pies[pos], s, pos);
          }));
        recInside = rounded[0] <= T.DEFAULT_BENCH_SHARE && T.DEFAULT_BENCH_SHARE <= rounded[1];
      }
      for (const share of (c.shares || [T.DEFAULT_BENCH_SHARE])) {
        cals[String(share)] = {};
        for (const pos of T.POSITIONS) {
          const cal = pool ? T.calibratePosition(pool.tiers[pos], c.pies[pos], share) : null;
          cals[String(share)][pos] = cal
            ? {pb: cal.pb, ps: cal.ps, invalid: cal.invalid, reason: cal.invalidReason}
            : null;
        }
      }
      return {name: c.name, poolError, intervals, bounds, rounded, endpointsFeasible, recInside, cals};
    });
    break;
  case "pooltier": {
    // Test-only: expose buildPositionTiers tier internals (rw/rs/tau and
    // slice exposures) so the Python port can be checked bit-exact on
    // real inputs. input: {lists, cfg}. Returns {tiers, error}.
    let tiers = null, error = null;
    try {
      tiers = T.buildPositionTiers(input.lists, input.cfg).tiers;
    } catch (e) {
      error = String((e && e.message) || e);
    }
    out = {tiers, error};
    break;
  }
  case "shares": {
    // share object written by the global slider, plus per-position lookup
    // with default fallback (K/DST excluded: fall back to default).
    const obj = T.skillBenchShares(input.share);
    out = {object: obj,
           lookups: {QB: T.skillBenchShare(obj, "QB"), RB: T.skillBenchShare(obj, "RB"),
                     WR: T.skillBenchShare(obj, "WR"), TE: T.skillBenchShare(obj, "TE"),
                     K: T.skillBenchShare(obj, "K"), DST: T.skillBenchShare(obj, "DST")},
           sparse: T.skillBenchShare({default: 0.2}, "RB")};
    break;
  }
  case "calibrate": {
    // Direct calibratePosition probe for degenerate tiers.
    const cal = T.calibratePosition(input.tier, input.pie, input.share);
    out = {
      pb: cal.pb, ps: cal.ps, invalid: cal.invalid, reason: cal.invalidReason,
      withheldFlag: T.WITHHELD_FLAG,
      priceAt: T.priceForProjection(input.probeX === undefined ? 20 : input.probeX, cal)
    };
    break;
  }
  case "pause": {
    // Fixture-transition Option B: pause predicate over (key, inputs) cases.
    // Each case: {key, inputs} where inputs may be null/undefined (fail-closed: paused).
    if (!P) {
      console.error("TradeValueCurvePause test surface missing");
      process.exit(1);
    }
    out = input.cases.map(c => P.adjustedCurvePaused(c.key, c.inputs === undefined ? undefined : c.inputs));
    break;
  }
  case "defaultset": {
    // Default active set over (inputs) cases: ESPN adjusted plus every
    // *_adjusted curve with live stage-2 cells. Empty/null inputs fail
    // closed to ["espn"].
    if (!P || typeof P.defaultIndexedSourceKeys !== "function") {
      console.error("TradeValueCurvePause.defaultIndexedSourceKeys test surface missing");
      process.exit(1);
    }
    out = input.cases.map(c => P.defaultIndexedSourceKeys(c.inputs === undefined ? undefined : c.inputs));
    break;
  }
  case "collapse": {
    // Collapse guard over (peaks) cases. Each case: {peaks, floor?}.
    // Answers the question the module dashboard flags as untested: does the
    // guard still trip on genuinely broken data after being loosened?
    const G = globalThis.TradeValueCurveGuards;
    if (!G || typeof G.peaksAboveCollapseFloor !== "function") {
      console.error("TradeValueCurveGuards.peaksAboveCollapseFloor test surface missing");
      process.exit(1);
    }
    out = {
      floor: G.CURVE_COLLAPSE_FLOOR,
      results: input.cases.map(c => G.peaksAboveCollapseFloor(
        c.peaks, c.floor === undefined ? undefined : c.floor)),
    };
    break;
  }
  default:
    console.error(`unknown command: ${cmd}`);
    process.exit(2);
}

process.stdout.write(JSON.stringify(out));
