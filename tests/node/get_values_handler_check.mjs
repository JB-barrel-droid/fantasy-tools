// JEG-1031: runs the deployed handler itself (supabase/functions/get-values/index.ts) in node, with a
// stub Deno and a fetch that serves the built dist/, so a syntax slip or a wrong wiring in index.ts
// fails here and not on the first live call. Values are compared with the parity runner, which the
// page-parity test (tests/test_endpoint_parity.py) ties to the page.
// Usage: node --experimental-strip-types tests/node/get_values_handler_check.mjs <dist dir>
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { join, resolve } from "node:path";

const dist = resolve(process.argv[2] || "dist");
let handler = null;
globalThis.Deno = { env: { get: () => undefined }, serve: (h) => { handler = h; } };
globalThis.fetch = async (url) => {
  const path = new URL(String(url)).pathname.replace(/^\/fantasy-tools/, "");
  const file = join(dist, path === "/" || path === "" ? "index.html" : path);
  let body;
  try { body = readFileSync(file); } catch { return new Response("not found", { status: 404 }); }
  return new Response(body, { status: 200 });
};
await import("../../supabase/functions/get-values/index.ts");
assert.equal(typeof handler, "function", "index.ts registered a Deno.serve handler");

const ask = (body, ip) => handler(new Request("https://fn.test/functions/v1/get-values", {
  method: "POST", headers: { "content-type": "application/json", "x-forwarded-for": ip }, body: JSON.stringify(body) }));
const runner = (league) => JSON.parse(execFileSync("node", ["--experimental-strip-types", "--no-warnings",
  "tests/_edge_pipeline_runner.cjs", "--league", JSON.stringify(league), "--dist", dist], { maxBuffer: 1 << 28 }));
const same = (resp, expected) => {
  assert.ok(resp.players.length > 50);
  const bad = resp.players.filter((p) => Math.abs(p.value - (expected[p.player_key] ?? 0)) > 0.06);
  assert.equal(bad.length, 0, `${bad.length} values differ from the runner: ${JSON.stringify(bad.slice(0, 3))}`);
};

// Default league: no league_custom, same values as the runner.
let res = await ask({ scoring: "ppr", teams: 12 }, "1.1.1.1");
assert.equal(res.status, 200);
let body = await res.json();
assert.deepEqual(body.league_custom, []);
same(body, runner({ scoring: "ppr", teams: 12 }));

// Custom league: priced, flagged, and equal to the runner (which the parity test ties to the page).
const league = { roster: { WR: 3, BENCH: 6 }, shares: { QB: 0.2, RB: 0.4, WR: 0.3, TE: 0.1 }, bso: 0.2,
  inj: "all", conf: 1.5, weeks: { regend: 13, playoffs: [14, 16], optimize: "playoffs" } };
res = await ask({ scoring: "half_ppr", teams: 10, superflex: 1, league }, "2.2.2.2");
assert.equal(res.status, 200);
body = await res.json();
assert.deepEqual(body.league_custom.sort(), ["bso", "conf", "inj", "optimize", "roster", "shares", "weeks"]);
assert.equal(body.setting.superflex, 1);
same(body, runner({ ...league, scoring: "half_ppr", teams: 10, roster: { ...league.roster, SUPERFLEX: 1 } }));

// JEG-1129: include=charts sends each chart's Indexed value (chart_indexed) next to its Adjusted value
// (chart_values). The Adjusted values average to DDF Value itself, so the finder judges the other team
// on chart_indexed; at least some players must differ between the two, or the rival check is DDF again.
res = await ask({ scoring: "half_ppr", teams: 12, include: "charts" }, "6.6.6.6");
assert.equal(res.status, 200);
body = await res.json();
if (body.players.length) {
  const CH = ["usatoday", "fantasycalc", "fantasypros", "cbs"];
  for (const p of body.players) {
    assert.ok(p.chart_indexed && CH.every((k) => k in p.chart_indexed), `chart_indexed on ${p.name}`);
    assert.ok(p.chart_values && CH.every((k) => k in p.chart_values), `chart_values on ${p.name}`);
  }
  const differs = body.players.filter((p) => CH.some((k) => p.chart_indexed[k] !== null && p.chart_values[k] !== null
    && Math.abs(p.chart_indexed[k] - p.chart_values[k]) > 0.5));
  assert.ok(differs.length > body.players.length / 4,
    `Indexed and Adjusted chart values differ for most players (${differs.length} of ${body.players.length})`);
}

// GET with a JSON league string works; garbage league is ignored, not a 500.
res = await handler(new Request("https://fn.test/functions/v1/get-values?scoring=ppr&teams=12&league=" +
  encodeURIComponent(JSON.stringify({ bso: 0.2 })), { headers: { "x-forwarded-for": "3.3.3.3" } }));
assert.deepEqual((await res.json()).league_custom, ["bso"]);
res = await handler(new Request("https://fn.test/functions/v1/get-values?league=%7Bnot-json", { headers: { "x-forwarded-for": "4.4.4.4" } }));
assert.equal(res.status, 200);

// A repeated league is answered from memory; fresh custom runs are rate limited per IP (10/min).
let limited = 0;
for (let i = 0; i < 12; i += 1) {
  const r = await ask({ scoring: "ppr", teams: 12, league: { bso: 0.01 + i * 0.01 } }, "5.5.5.5");
  if (r.status === 429) limited += 1;
}
assert.ok(limited >= 1, "custom-league compute is rate limited");
console.log("ok");
