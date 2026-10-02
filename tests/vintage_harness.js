#!/usr/bin/env node
// Test harness: tests the vintage display logic from comparison-dashboard.js
// without requiring the full dashboard module (which has DOM dependencies).
// Usage: node vintage_harness.js < payload.json
// payload: {sourceKey: string, sources: {...}}
// Output: {sourceKey, isDateUnavailable, vintageDisplay}
"use strict";
const fs = require("fs");

// Read payload from stdin
const payload = JSON.parse(fs.readFileSync(0, "utf8"));

// This is the vintage display logic extracted from comparison-dashboard.js
// function sourceDate(key) {
//   const vorpSource = PURE_VORP_KEYS.includes(key) ? VORP_SOURCE_DEFS[key].validationKey : null;
//   const source = data.sources[key] || (key === "cbs_adjusted" ? data.sources.cbs : vorpSource ? data.sources[vorpSource] : {}) || {};
//   if (key.endsWith("_adjusted")) {
//     const match = String(source.fit_bake_id || "").match(/(\d{4}-\d{2}-\d{2})/);
//     return match ? `fit ${new Intl.DateTimeFormat("en-US", {month:"short", day:"numeric", timeZone:"UTC"}).format(new Date(`${match[1]}T00:00:00Z`))}` : "fit date unavailable";
//   }
//   const raw = source.published || source.espn_snapshot || source.fetched_at || source.vintage;
//   if (!raw) return "date unavailable";
//   const date = new Date(String(raw).slice(0, 10) + "T00:00:00Z");
//   return Number.isNaN(date.getTime()) ? "date unavailable" : `content ${new Intl.DateTimeFormat("en-US", {month:"short", day:"numeric", timeZone:"UTC"}).format(date)}`;
// }

function sourceDate(sourceKey, sources) {
  const source = sources[sourceKey] || {};
  const raw = source.published || source.espn_snapshot || source.fetched_at || source.vintage;

  if (!raw) return "date unavailable";
  const date = new Date(String(raw).slice(0, 10) + "T00:00:00Z");
  return Number.isNaN(date.getTime()) ? "date unavailable" : `content ${new Intl.DateTimeFormat("en-US", {month: "short", day: "numeric", timeZone: "UTC"}).format(date)}`;
}

// Execute the function
const vintageDisplay = sourceDate(payload.sourceKey, payload.sources || {});
const isDateUnavailable = vintageDisplay === "date unavailable";

const result = {
  sourceKey: payload.sourceKey,
  isDateUnavailable: isDateUnavailable,
  vintageDisplay: vintageDisplay
};

process.stdout.write(JSON.stringify(result, null, 2));
