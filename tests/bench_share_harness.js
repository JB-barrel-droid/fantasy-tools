#!/usr/bin/env node
// Test harness: loads curve-widget.js in Node (no DOM) and tests that
// setBenchShareFraction updates the benchShare variable, which is required
// for the weights readout to stay in sync.
// Usage: node bench_share_harness.js < payload.json
// payload: { benchShare: number }
// Output: { benchShare: number, success: bool }
"use strict";
const path = require("path");

// Headless: alias window -> globalThis before loading the widget.
globalThis.window = globalThis;

// Load dependencies first, then the widget.
require(path.join(__dirname, "..", "app", "trade-value-chart", "assets", "value-model.js"));
require(path.join(__dirname, "..", "app", "trade-value-chart", "assets", "curve-widget.js"));

const P = globalThis.TradeValueCurveDebug;
if (!P || typeof P.benchShare !== "function") {
  console.error("benchShare test surface missing");
  process.exit(1);
}

const payload = JSON.parse(require("fs").readFileSync(0, "utf8"));
const setBenchShareFraction = globalThis.setBenchShareFraction;
if (!setBenchShareFraction) {
  console.error("setBenchShareFraction not exposed");
  process.exit(1);
}

// Call setBenchShareFraction to change the bench share.
setBenchShareFraction(payload.benchShare, false);

// Read back the benchShare value.
const actualBenchShare = P.benchShare();

const out = {
  benchShare: actualBenchShare,
  inputBenchShare: payload.benchShare,
  success: Math.abs(actualBenchShare - payload.benchShare) < 1e-9
};
process.stdout.write(JSON.stringify(out));
