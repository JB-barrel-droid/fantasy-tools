// JEG-1156 / JEG-1157: the deployed get-values handler on a pinned day (DDF_TODAY), never the real clock.
// Serves the built dist/ (optionally with the bundle's chart weeks rewritten) and checks:
//   current week published -> no fallback; current week missing -> week-N values, labeled, with the
//   fallback charts named; no chart published -> no players, and sources_excluded says why.
// Usage: node --experimental-strip-types tests/node/get_values_week_check.mjs <dist dir>
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join, resolve } from "node:path";

const dist = resolve(process.argv[2] || "dist");
const CHARTS = ["usatoday", "fantasycalc", "fantasypros", "cbs"];
const bundleText = readFileSync(join(dist, "assets/comparison-sources-data.json"), "utf8");
const week = Math.max(...CHARTS.map((k) => Number(String(JSON.parse(bundleText).sources[k]?.week_designated || "").match(/\d+/)?.[0] || 0)));
assert.ok(week > 0, "the built bundle has a dated weekly chart");
// The Tuesday content week `n` opens (pipelines/nfl_week.py content_week_start).
const weekStart = (n, plusDays = 0) => new Date(Date.UTC(2026, 8, 8) + ((n - 1) * 7 + plusDays) * 86400000).toISOString().slice(0, 10);

let instance = 0;
async function handlerFor(today, editBundle) {
  let handler = null;
  globalThis.Deno = { env: { get: (k) => (k === "DDF_TODAY" ? today : undefined) }, serve: (h) => { handler = h; } };
  globalThis.fetch = async (url) => {
    const path = new URL(String(url)).pathname.replace(/^\/fantasy-tools/, "");
    if (path === "/assets/comparison-sources-data.json" && editBundle) {
      const bundle = JSON.parse(bundleText);
      editBundle(bundle);
      return new Response(JSON.stringify(bundle), { status: 200 });
    }
    try { return new Response(readFileSync(join(dist, path === "/" || path === "" ? "index.html" : path)), { status: 200 }); }
    catch { return new Response("not found", { status: 404 }); }
  };
  // A fresh module instance per case: the bundle and answer caches are module-level.
  instance += 1;
  await import(`../../supabase/functions/get-values/index.ts?case=${instance}`);
  assert.equal(typeof handler, "function");
  const res = await handler(new Request("https://fn.test/functions/v1/get-values?scoring=ppr&teams=12",
    { headers: { "x-forwarded-for": `9.9.9.${instance}` } }));
  assert.equal(res.status, 200);
  return await res.json();
}

// 1. Current week published (a day in the charts' own week): no fallback.
let body = await handlerFor(weekStart(week, 3));
assert.ok(body.players.length > 50, `priced ${body.players.length} players`);
assert.equal(body.values_week, week);
assert.equal(body.current_week, week);
assert.equal(body.values_week_note, `Week ${week} values`);
assert.deepEqual(body.sources_fallback, []);
assert.ok(CHARTS.every((k) => body.sources_included.includes(k)), `charts included: ${body.sources_included}`);
const normal = Object.fromEntries(body.players.map((p) => [p.player_key, p.value]));

// 2. Current week missing (the Tuesday flip): the same week-N values, labeled.
body = await handlerFor(weekStart(week + 1));
assert.ok(body.players.length > 50, `priced ${body.players.length} players on the flip day`);
assert.equal(body.values_week, week);
assert.equal(body.current_week, week + 1);
assert.equal(body.values_week_note, `Week ${week} values, week ${week + 1} not published yet`);
assert.deepEqual(body.sources_fallback.map((r) => r.key).sort(), [...CHARTS].sort());
assert.ok(body.sources_fallback.every((r) => r.reason.includes(`week ${week + 1} not published yet`)));
const moved = body.players.filter((p) => normal[p.player_key] !== p.value);
assert.equal(moved.length, 0, "the fallback prices exactly the week-N values (no value math change)");

// 2b. One chart a week further behind on the flip day: it is dropped, with its reason.
body = await handlerFor(weekStart(week + 1), (b) => { b.sources.usatoday.week_designated = `Week ${week - 1}`; });
assert.ok(body.players.length > 50);
assert.ok(!body.sources_included.includes("usatoday"));
const usat = body.sources_excluded.find((e) => e.key === "usatoday");
assert.ok(usat && usat.reason.includes(`not yet published for week ${week}`), JSON.stringify(body.sources_excluded));

// 3. No chart published at all: DDF Value (charts only, JEG-1073) is empty, and the answer says why.
body = await handlerFor(weekStart(week + 1), (b) => { CHARTS.forEach((k) => { delete b.sources[k]; }); });
assert.equal(body.players.length, 0);
assert.equal(body.values_week, null);
assert.equal(body.values_week_note, "No trade chart published yet");
assert.deepEqual(body.sources_fallback, []);

console.log("ok");
