// JEG-1061: pins the get-values compute rate limiter's SINGLE-INSTANCE behavior. The limiter in
// supabase/functions/get-values/index.ts is an in-memory Map per function instance, keyed by the
// first x-forwarded-for entry — a soft guard only (live traffic spreads across instances, so the
// 10/min compute limit did not fire in the 2026-10-24 live check). What this test pins: on ONE
// instance, the 11th fresh custom-league compute within a minute from one key gets a 429, and a
// different key has its own bucket. If the limiter stops returning 429 on one instance, this fails.
// Runs the deployed handler itself in node, same harness as get_values_handler_check.mjs.
// Usage: node --experimental-strip-types tests/node/get_values_rate_limit_check.mjs <dist dir>
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
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

// Each league differs (bso), so each request is a fresh compute that consumes the key's budget:
// the first 10 pass, the 11th within the minute is a 429.
const ip = "7.7.7.7";
for (let i = 0; i < 10; i += 1) {
  const r = await ask({ scoring: "ppr", teams: 12, league: { bso: 0.02 + i * 0.01 } }, ip);
  assert.equal(r.status, 200, `compute ${i + 1} from one key should pass, got ${r.status}`);
}
const eleventh = await ask({ scoring: "ppr", teams: 12, league: { bso: 0.12 } }, ip);
assert.equal(eleventh.status, 429, "11th compute within a minute from one key must be a 429");
assert.equal((await eleventh.json()).error, "rate limited");

// A different key has its own bucket: its first compute still passes.
const other = await ask({ scoring: "ppr", teams: 12, league: { bso: 0.13 } }, "8.8.8.8");
assert.equal(other.status, 200, `first compute from a different key should pass, got ${other.status}`);
console.log("ok");
