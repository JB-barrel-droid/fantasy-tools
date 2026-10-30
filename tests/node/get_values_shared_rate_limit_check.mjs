// JEG-1061: the get-values compute limit holds across function instances when the shared count is on.
// Loads the deployed handler (supabase/functions/get-values/index.ts) as TWO separate instances, each with
// its own module state, as live traffic spread over instances does. A fake PostgREST answers
// /rest/v1/rpc/edge_rate_hit from one in-process store (the migration's semantics: fixed window per hashed
// key, true while hits <= limit). Checks:
//   1. shared on: 10 computes from one key spread over both instances pass, the 11th is a 429 (on main each
//      instance kept its own count, so all 11 passed: the 2026-10-24 live finding);
//   2. a different key has its own budget; no key the store sees contains the IP;
//   3. shared on but the RPC fails (500): the in-memory limit still decides, and a fallback line is logged;
//   4. shared on, the database answers for 9 computes and then fails: the 11th in the minute is still a 429
//      (the local count was fed all along, review finding on 858e162);
//   5. shared off (no secret): no RPC is ever called and each instance counts alone, as before;
//   6. rate-limit.ts on its own: a timeout falls back, missing credentials switch it off, and the bucket is
//      an HMAC under the service key (not a plain hash anyone could reverse).
// Usage: node --experimental-strip-types --no-warnings tests/node/get_values_shared_rate_limit_check.mjs <dist dir>
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join, resolve } from "node:path";
import { pathToFileURL } from "node:url";

const dist = resolve(process.argv[2] || "dist");
const INDEX = pathToFileURL(resolve(import.meta.dirname, "../../supabase/functions/get-values/index.ts")).href;
const SUPABASE = "https://proj.supabase.test";

const store = new Map(); // hashed bucket -> { start, hits }
const rpcCalls = [];
let rpcMode = "ok";
const logged = [];
const realLog = console.log;
console.log = (line) => { logged.push(String(line)); };

globalThis.fetch = async (url, init) => {
  const u = new URL(String(url));
  if (u.origin === SUPABASE) {
    assert.equal(u.pathname, "/rest/v1/rpc/edge_rate_hit");
    const body = JSON.parse(init.body);
    rpcCalls.push(body);
    if (rpcMode === "fail") return new Response("{}", { status: 500 });
    const now = Date.now();
    let b = store.get(body.p_bucket);
    if (!b || b.start <= now - body.p_window_s * 1000) b = { start: now, hits: 0 };
    b.hits += 1;
    store.set(body.p_bucket, b);
    return Response.json(b.hits <= body.p_limit);
  }
  const path = u.pathname.replace(/^\/fantasy-tools/, "");
  const file = join(dist, path === "/" || path === "" ? "index.html" : path);
  let data;
  try { data = readFileSync(file); } catch { return new Response("not found", { status: 404 }); }
  return new Response(data, { status: 200 });
};

let n = 0;
async function instance(env) {
  let handler = null;
  globalThis.Deno = { env: { get: (k) => env[k] }, serve: (h) => { handler = h; } };
  await import(`${INDEX}?instance=${n += 1}`);
  assert.equal(typeof handler, "function", "index.ts registered a Deno.serve handler");
  return handler;
}

const ON = { DDF_SHARED_RATE_LIMIT: "1", SUPABASE_URL: SUPABASE, SUPABASE_SERVICE_ROLE_KEY: "test-service-key" };
let bso = 0.02;
const ask = (handler, ip) => handler(new Request("https://fn.test/functions/v1/get-values", {
  method: "POST", headers: { "content-type": "application/json", "x-forwarded-for": ip },
  // Each league differs (bso), so each request is a fresh compute, never an answer-cache hit.
  body: JSON.stringify({ scoring: "ppr", teams: 12, league: { bso: Math.round((bso += 0.001) * 1000) / 1000 } }) }));

// 1. Shared on, two instances, one key: the 11th compute in the minute is a 429 wherever it lands.
{
  const a = await instance(ON), b = await instance(ON);
  for (let i = 0; i < 10; i += 1) {
    const r = await ask(i % 2 ? b : a, "7.7.7.7");
    assert.equal(r.status, 200, `compute ${i + 1} across instances should pass, got ${r.status}`);
  }
  const eleventh = await ask(b, "7.7.7.7");
  assert.equal(eleventh.status, 429, "11th compute from one key across two instances must be a 429");
  assert.equal((await eleventh.json()).error, "rate limited");
  assert.ok(logged.some((l) => l.includes('"get_values.rate_limited"') && l.includes('"compute"')),
    "the shared 429 logs get_values.rate_limited");
  assert.equal(rpcCalls.length, 11, "one shared hit per fresh compute");
  // 2. Another key has its own budget, and no key leaves the function in clear.
  const other = await ask(a, "8.8.8.8");
  assert.equal(other.status, 200, `first compute from a different key should pass, got ${other.status}`);
  for (const call of rpcCalls) {
    assert.match(call.p_bucket, /^[0-9a-f]{64}$/, "bucket is a SHA-256 hex digest");
    assert.ok(!call.p_bucket.includes("7.7.7.7") && !call.p_bucket.includes("8.8.8.8"));
    assert.equal(call.p_limit, 10);
    assert.equal(call.p_window_s, 60);
  }
  assert.equal(store.size, 2);
}

// 3. Shared on but the database fails: the in-memory limit decides (one instance: 11th is a 429).
{
  rpcMode = "fail";
  const before = logged.length;
  const c = await instance(ON);
  for (let i = 0; i < 10; i += 1) {
    const r = await ask(c, "9.9.9.9");
    assert.equal(r.status, 200, `compute ${i + 1} with the database down should pass, got ${r.status}`);
  }
  assert.equal((await ask(c, "9.9.9.9")).status, 429, "with the database down the in-memory limit still applies");
  const fallbacks = logged.slice(before).filter((l) => l.includes('"get_values.rate_limit_fallback"'));
  // The 11th is refused by the local count before any shared call, so 10 failed calls, 10 fallback lines.
  assert.equal(fallbacks.length, 10, "each failed shared call logs one fallback line");
  assert.ok(fallbacks.every((l) => !l.includes("9.9.9.9")), "no IP in the fallback line");
  rpcMode = "ok";
}

// 4. The database answers, then fails mid-minute: the local count was fed, so the 11th is still a 429.
{
  const f = await instance(ON);
  for (let i = 0; i < 9; i += 1) assert.equal((await ask(f, "5.5.5.5")).status, 200, `compute ${i + 1}, database up`);
  rpcMode = "fail";
  assert.equal((await ask(f, "5.5.5.5")).status, 200, "10th compute, database down, passes");
  assert.equal((await ask(f, "5.5.5.5")).status, 429, "11th compute in the minute is a 429 even after the database failed");
  rpcMode = "ok";
}

// 5. Shared off: no database call, and each instance counts alone (the soft guard as before).
{
  const calls = rpcCalls.length;
  const d = await instance({}), e = await instance({});
  for (let i = 0; i < 11; i += 1) {
    const r = await ask(i % 2 ? e : d, "6.6.6.6");
    assert.equal(r.status, 200, `off: compute ${i + 1} spread over two instances passes, got ${r.status}`);
  }
  assert.equal(rpcCalls.length, calls, "off: no shared call");
}

// 6. rate-limit.ts on its own.
{
  const { computeLimiter, sharedCheck } = await import(
    pathToFileURL(resolve(import.meta.dirname, "../../supabase/functions/get-values/rate-limit.ts")).href);
  const env = (vars) => (k) => vars[k];
  assert.equal(sharedCheck({ env: env({ DDF_SHARED_RATE_LIMIT: "1", SUPABASE_URL: SUPABASE }) }), null,
    "no service key: off");
  assert.equal(sharedCheck({ env: env({ DDF_SHARED_RATE_LIMIT: "1", SUPABASE_SERVICE_ROLE_KEY: "k" }) }), null,
    "no URL: off");
  assert.equal(sharedCheck({ env: env({ ...ON, DDF_SHARED_RATE_LIMIT: "true" }) }), null, "only \"1\" turns it on");
  // A database that never answers: the 50 ms timeout aborts the call and the local count decides.
  const hang = (_url, init) => new Promise((_, reject) => init.signal.addEventListener("abort", () => reject(init.signal.reason)));
  const lines = [];
  const slow = computeLimiter(() => true, sharedCheck({ env: env(ON), fetchFn: hang, timeoutMs: 50 }), (l) => lines.push(l));
  const t0 = Date.now();
  const alive = setTimeout(() => {}, 5000); // AbortSignal.timeout's timer does not keep node running on its own
  assert.equal(await slow("compute:1.2.3.4", 10, 60), true, "a timed-out shared call falls back to the local count");
  clearTimeout(alive);
  assert.ok(Date.now() - t0 < 2000, "the timeout bounds the wait");
  assert.equal(lines[0]?.event, "get_values.rate_limit_fallback");
  // The bucket is keyed by the service key: another key gives another bucket for the same IP.
  const seen = [];
  const capture = async (_url, init) => { seen.push(JSON.parse(init.body).p_bucket); return Response.json(true); };
  for (const secret of ["key-one", "key-two"]) {
    await sharedCheck({ env: env({ ...ON, SUPABASE_SERVICE_ROLE_KEY: secret }), fetchFn: capture })("compute:1.2.3.4", 10, 60);
  }
  assert.notEqual(seen[0], seen[1], "the bucket depends on the service key (HMAC), not the IP alone");
  const { createHash } = await import("node:crypto");
  assert.notEqual(seen[0], createHash("sha256").update("get-values:compute:1.2.3.4").digest("hex"),
    "not a plain SHA-256 of the key");
}

console.log = realLog;
console.log("ok");
