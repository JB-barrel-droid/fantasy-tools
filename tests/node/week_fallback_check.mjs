// JEG-1156 / JEG-1157: the values-week fallback (Jeremy, 2026-10-27, option A), with a pinned day.
// The edge function's rule (supabase/functions/get-values/weeks.ts) and the page's
// (app/trade-value-chart/assets/product-data.js buildSourceFreshness) must agree on: the values
// week, whether it is a fallback, the label, and which weekly charts are left out.
// Usage: node --experimental-strip-types tests/node/week_fallback_check.mjs
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import vm from "node:vm";
import { chartWeekPlan, todayIso } from "../../supabase/functions/get-values/weeks.ts";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
const ASSETS = join(ROOT, "app", "trade-value-chart", "assets");
const KEYS = ["espn", "cbsros", "razzball", "fantasycalc", "usatoday", "fantasypros", "cbs"];
const CHARTS = ["fantasycalc", "usatoday", "fantasypros", "cbs"];

const ctx = vm.createContext({ console, Intl, Date, Math, Number, String, Object, Array, Set, Map, JSON, RegExp, Error });
ctx.module = { exports: {} };
vm.runInContext(readFileSync(join(ASSETS, "product-data.js"), "utf8"), ctx, { filename: "product-data.js" });
const PD = ctx.module.exports;
assert.equal(typeof PD.buildSourceFreshness, "function", "product-data.js exports buildSourceFreshness");

const projections = { espn: { content_vintage: "rest of season", fetched_at: "2026-10-25T23:43:15Z" },
  cbsros: { content_vintage: "rest of season" }, razzball: { content_vintage: "rest of season" } };
const charts = (weeks) => Object.fromEntries(CHARTS.map((key, i) => [key, { week_designated: `Week ${weeks[i]}` }]));

// Both sides on one fixture and day; returns the edge plan after checking the page agrees.
function both(sources, today) {
  const plan = chartWeekPlan(sources, KEYS, today);
  const page = PD.buildSourceFreshness(sources, { today, seriesKeys: KEYS });
  assert.equal(page.today, today, "the page read the pinned day, not the clock");
  assert.equal(page.current_content_week, plan.current_week, "content week");
  assert.equal(page.values_week, plan.values_week, "values week");
  assert.equal(page.values_week_fallback, plan.fallback, "fallback flag");
  assert.equal(page.values_week_label, plan.label, "label");
  const pageLeftOut = CHARTS.filter((key) => page.series[key]?.behind_values_week === true);
  assert.deepEqual(pageLeftOut, plan.not_published.map((row) => row.key), "charts left out");
  return plan;
}

const TUESDAY_WEEK_8 = "2026-10-27"; // the flip day of JEG-1156
const SUNDAY_WEEK_7 = "2026-10-25";

// 1. Current week published: no fallback, no label change, nothing dropped.
let plan = both({ ...projections, ...charts([7, 7, 7, 7]) }, SUNDAY_WEEK_7);
assert.equal(plan.current_week, 7);
assert.equal(plan.values_week, 7);
assert.equal(plan.fallback, false);
assert.equal(plan.label, "Week 7 values");
assert.deepEqual(plan.not_published, []);
assert.deepEqual(plan.fallback_charts, []);

// 1b. Some week-8 charts published: normal rule, the week-7 ones are left out with a reason.
plan = both({ ...projections, ...charts([8, 7, 8, 7]) }, TUESDAY_WEEK_8);
assert.equal(plan.values_week, 8);
assert.equal(plan.fallback, false);
assert.deepEqual(plan.not_published.map((row) => row.key), ["usatoday", "cbs"]);
assert.match(plan.not_published[0].reason, /not yet published for week 8/);

// 2. Current week missing (the live case): week-7 charts count, labeled.
plan = both({ ...projections, ...charts([7, 7, 7, 7]) }, TUESDAY_WEEK_8);
assert.equal(plan.current_week, 8);
assert.equal(plan.values_week, 7);
assert.equal(plan.fallback, true);
assert.equal(plan.label, "Week 7 values, week 8 not published yet");
assert.deepEqual(plan.not_published, []);
assert.deepEqual(plan.fallback_charts.map((row) => row.key), CHARTS);
assert.match(plan.fallback_charts[0].reason, /week 8 not published yet; using its week 7 chart/);

// 2b. Fallback with a chart further behind: it is still left out against the values week.
plan = both({ ...projections, ...charts([7, 6, 7, 7]) }, TUESDAY_WEEK_8);
assert.equal(plan.values_week, 7);
assert.equal(plan.fallback, true);
assert.deepEqual(plan.not_published.map((row) => row.key), ["usatoday"]);

// 3. No published chart at all: no values week, nothing to fall back to.
plan = both({ ...projections }, TUESDAY_WEEK_8);
assert.equal(plan.values_week, null);
assert.equal(plan.fallback, false);
assert.equal(plan.label, "No trade chart published yet");
assert.deepEqual(plan.not_published, []);
assert.deepEqual(plan.fallback_charts, []);

// The shipped bundle agrees on the flip day too.
const bundle = JSON.parse(readFileSync(join(ASSETS, "comparison-sources-data.json"), "utf8"));
both(bundle.sources, TUESDAY_WEEK_8);

// todayIso reads the New York day of an injected instant (00:30 ET Oct 27 is still Oct 27, 04:30 UTC).
assert.equal(todayIso(new Date("2026-10-27T04:30:00Z")), "2026-10-27");
assert.equal(todayIso(new Date("2026-10-27T03:30:00Z")), "2026-10-26");

console.log("ok");
