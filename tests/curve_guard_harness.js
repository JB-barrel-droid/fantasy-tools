#!/usr/bin/env node
// Test harness: loads curve-widget.js in Node (no DOM) and evaluates the
// defaultCurvesSatisfied regression-guard predicate from
// globalThis.TradeValueCurvePause against simulated active/deselected sets.
// Usage: node curve_guard_harness.js < payload.json
// payload: {active: [...keys], deselected: [...keys]}
// Output: {satisfied: bool, defaults: [...keys], oldPredicateWouldThrow: bool}
//
// JEG-211 note: the old indexed-publisher guard branch
// (indexedCurvesSatisfied over available publisher keys) was retired from
// production in 0ca6ab4 (K/DST honest exclusion). The guard now checks the
// computed default set via defaultCurvesSatisfied, so the harness only
// exercises that contract.
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
// The widget ignores its `inputs` argument since JEG-508; the retired adjustment-inputs.json is not read (JEG-539).
const inputs = null;
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
