#!/usr/bin/env node
// Test harness: loads curve-widget.js in Node (no DOM) and evaluates the
// anchorScaleCorrectedCheck scale-aware guard predicate from
// globalThis.TradeValueCurveGuards.
// Usage: node scale_guard_harness.js < payload.json
// payload: {displayTotal, pieSum, displayScale, tolerance}
// Output: {total, target, delta, ok}
"use strict";
const fs = require("fs");
const path = require("path");

// Headless (JEG-29): alias window -> globalThis before loading the widget.
globalThis.window = globalThis;

require(path.join(__dirname, "..", "app", "trade-value-chart", "assets", "value-model.js"));
require(path.join(__dirname, "..", "app", "trade-value-chart", "assets", "curve-widget.js"));

const G = globalThis.TradeValueCurveGuards;
if (!G || typeof G.anchorScaleCorrectedCheck !== "function") {
  console.error("anchorScaleCorrectedCheck test surface missing");
  process.exit(1);
}

const payload = JSON.parse(fs.readFileSync(0, "utf8"));
const out = G.anchorScaleCorrectedCheck(
  payload.displayTotal,
  payload.pieSum,
  payload.displayScale,
  payload.tolerance
);
process.stdout.write(JSON.stringify(out));
