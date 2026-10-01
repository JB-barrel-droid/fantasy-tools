#!/usr/bin/env node
// Test harness: loads curve-widget.js in Node (no DOM) and evaluates the
// defaultCurvesSatisfied regression-guard predicate from
// globalThis.TradeValueCurvePause against simulated active/deselected sets.
// Usage: node curve_guard_harness.js < payload.json
// payload: {inputsPath, active: [...keys], deselected: [...keys]}
// Output: {satisfied: bool, defaults: [...keys], oldPredicateWouldThrow: bool}
"use strict";
const fs = require("fs");
const path = require("path");

// Headless (JEG-29): alias window -> globalThis before loading the widget.
globalThis.window = globalThis;

require(path.join(__dirname, "..", "app", "trade-value-chart", "assets", "value-model.js"));
require(path.join(__dirname, "..", "app", "trade-value-chart", "assets", "curve-widget.js"));

const P = globalThis.TradeValueCurvePause;
if (!P || typeof P.defaultCurvesSatisfied !== "function") {
  console.error("defaultCurvesSatisfied test surface missing");
  process.exit(1);
}

const payload = JSON.parse(fs.readFileSync(0, "utf8"));
const inputs = JSON.parse(fs.readFileSync(payload.inputsPath, "utf8"));
const active = new Set(payload.active || []);
const deselected = new Set(payload.deselected || []);
const defaults = P.defaultIndexedSourceKeys(inputs);
// The pre-fix predicate, for proving the test discriminates the old bug.
const oldPredicateWouldThrow = !defaults.every(key => active.has(key));
const out = {
  satisfied: P.defaultCurvesSatisfied(inputs, active, deselected),
  defaults,
  oldPredicateWouldThrow,
};
process.stdout.write(JSON.stringify(out));
