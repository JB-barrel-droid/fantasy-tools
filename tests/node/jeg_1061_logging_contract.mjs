// JEG-1258 (part of JEG-1061): logging contract for get-values. Jeremy, Oct 25: keep the in-memory
// limiter as a soft per-instance guard, and log fresh custom-league computes and rate-limited requests.
// This harness runs the handler itself (supabase/functions/get-values/index.ts, read only) in node with
// a stub Deno, a fetch that serves the built dist/ and refuses every other host, a frozen clock the
// harness moves by hand, and an output recorder (every console method and raw stdout/stderr write, from
// just before the module import to the end of the scenario). Each scenario imports a fresh module
// instance, so its limiter buckets and answer cache start empty.
//
// The contract (spec and hook proposal in tests/fixtures/jeg_1061_logging/README.md):
// - one `get_values.compute` event per fresh custom-league computation, none for a cached answer or the
//   default league;
// - one `get_values.rate_limited` event per 429, `limit` "general" (30/min) or "compute" (10/min);
// - events are one console call whose argument is a JSON object string (or the object), with only the
//   whitelisted fields below. The recorded output must not contain any value of the request headers the
//   harness sends (forwarded-for, authorization, apikey, cookie) or any player name from any answer the
//   harness received in the run (numeric player keys are kept off events by the whitelist only).
// The existing statuses (11th fresh compute in a minute from one key is a 429, 31st request is a 429,
// cached answers and other keys still served) are checked too; a change there is a harness failure.
//
// Usage:
//   node --experimental-strip-types --no-warnings tests/node/jeg_1061_logging_contract.mjs <dist dir>
//     [--target <get-values dir>]     run a copy of the function instead of the repo's (read only)
//     [--expect-failures <json file>] strict expected-failure mode: exit 0 only if the contract
//                                     violations are exactly the recorded list ([] = must fully pass)
//   node ... tests/node/jeg_1061_logging_contract.mjs --self-test
//     checks the checker: a correct log passes and each mutation (missing, extra, misclassified,
//     leaking or malformed events) is caught. Needs no dist and no handler.
// Exit codes: 0 pass, 1 contract violations (or a mismatch with the expected list), 2 harness failure
// (handler did not load, a status changed, a scenario threw).
import { readFileSync } from "node:fs";
import { join, resolve } from "node:path";
import { pathToFileURL } from "node:url";

const SITE_HOST = "jb-barrel-droid.github.io";
const SENTINEL = "jeg1258-"; // every header value the harness sends contains this; it must never be logged
const HEADERS = {
  "x-forwarded-for": "", // set per client below
  authorization: "Bearer jeg1258-token-sentinel",
  apikey: "jeg1258-apikey-sentinel",
  cookie: "sb-access-token=jeg1258-cookie-sentinel",
};
const client = (name) => `jeg1258-client-${name}, jeg1258-proxy-hop`;

// --- The contract -----------------------------------------------------------------------------------

const SCORINGS = ["standard", "half_ppr", "ppr"];
const isInt = (v) => Number.isInteger(v);
const FIELD_TYPES = {
  event: (v) => typeof v === "string",
  scoring: (v) => SCORINGS.includes(v),
  teams: (v) => [8, 10, 12, 14].includes(v),
  superflex: (v) => isInt(v) && v >= 0,
  custom: (v) => Array.isArray(v) && v.every((k) => typeof k === "string"),
  charts: (v) => typeof v === "boolean",
  ms: (v) => typeof v === "number" && Number.isFinite(v) && v >= 0,
  week: (v) => v === null || isInt(v), // JEG-1179 (#1024) adds the priced week; optional
  limit: (v) => v === "general" || v === "compute",
  max: (v) => isInt(v) && v > 0,
  window_s: (v) => isInt(v) && v > 0,
};
const SCHEMAS = {
  "get_values.compute": {
    required: ["event", "scoring", "teams", "superflex", "custom", "charts", "ms"],
    optional: ["week"],
  },
  "get_values.rate_limited:general": { required: ["event", "limit", "max", "window_s"], optional: [] },
  "get_values.rate_limited:compute": {
    required: ["event", "limit", "max", "window_s", "scoring", "teams", "superflex", "custom", "charts"],
    optional: ["week"],
  },
};
const EVENT_NAMES = ["get_values.compute", "get_values.rate_limited"];

// A console call is an event when its single argument is an object (or a JSON object string) whose
// `event` starts with "get_values.". Anything else is free text, which only the leak scan reads.
function parseEvent(args) {
  if (args.length !== 1) return null;
  let v = args[0];
  if (typeof v === "string") {
    const s = v.trim();
    if (!s.startsWith("{")) return null;
    try { v = JSON.parse(s); } catch { return null; }
  }
  if (!v || typeof v !== "object" || Array.isArray(v)) return null;
  return typeof v.event === "string" && v.event.startsWith("get_values.") ? v : null;
}

const text = (a) => {
  if (typeof a === "string") return a;
  if (a instanceof Error) return `${a.name}: ${a.message}\n${a.stack || ""}`;
  try { return JSON.stringify(a); } catch { return String(a); }
};
const sameList = (a, b) => JSON.stringify([...a].sort()) === JSON.stringify([...b].sort());

// Returns the violations (stable strings) for one scenario's console calls against its expectations.
// expected = { compute: [fields...], rate_limited: [fields...], forbidden: [strings] }
export function checkScenario(name, calls, expected) {
  const out = [];
  const v = (check, detail) => out.push(`${name}/${check}: ${detail}`);

  const all = calls.map((c) => c.args.map(text).join(" ")).join("\n");
  for (const f of [SENTINEL, ...(expected.forbidden || [])]) {
    if (f && all.includes(f)) v("leak", `console output contains ${f === SENTINEL ? "a request header value" : "player data"}`);
  }

  const events = calls.filter((c) => c.level !== "stdout" && c.level !== "stderr")
    .map((c) => parseEvent(c.args)).filter(Boolean);
  const byName = { "get_values.compute": [], "get_values.rate_limited": [] };
  events.forEach((e) => {
    if (!EVENT_NAMES.includes(e.event)) v("unknown-event", `event name ${JSON.stringify(e.event)}`);
    else byName[e.event].push(e);
  });

  for (const [evName, key] of [["get_values.compute", "compute"], ["get_values.rate_limited", "rate_limited"]]) {
    const got = byName[evName];
    const want = expected[key] || [];
    if (got.length !== want.length) v(`${key}.count`, `expected ${want.length}, got ${got.length}`);
    got.forEach((e, i) => {
      const schemaKey = evName === "get_values.compute" ? evName : `${evName}:${e.limit}`;
      const schema = SCHEMAS[schemaKey];
      if (!schema) { v(`${key}[${i}].limit`, `unknown limit ${JSON.stringify(e.limit)}`); return; }
      for (const f of schema.required) if (!(f in e)) v(`${key}[${i}].fields`, `missing ${f}`);
      for (const f of Object.keys(e)) {
        if (!schema.required.includes(f) && !schema.optional.includes(f)) v(`${key}[${i}].fields`, `field not allowed: ${f}`);
        else if (!FIELD_TYPES[f](e[f])) v(`${key}[${i}].fields`, `bad ${f}: ${JSON.stringify(e[f])}`);
      }
      const w = want[i];
      if (!w) return;
      for (const [f, wv] of Object.entries(w)) {
        const ok = Array.isArray(wv) ? Array.isArray(e[f]) && sameList(e[f], wv) : e[f] === wv;
        if (!ok) v(`${key}[${i}].${f}`, `expected ${JSON.stringify(wv)}, got ${JSON.stringify(e[f])}`);
      }
    });
  }
  return out;
}

// --- Self-test: the checker catches a broken log ----------------------------------------------------

function selfTest() {
  const c = (fields) => ({ level: "log", args: [JSON.stringify(fields)] });
  const compute = { event: "get_values.compute", scoring: "ppr", teams: 12, superflex: 0, custom: ["bso"], charts: false, ms: 312 };
  const cached = { ...compute, custom: ["bso"], ms: 290 };
  const limited = { event: "get_values.rate_limited", limit: "compute", max: 10, window_s: 60, scoring: "ppr", teams: 12, superflex: 0, custom: ["bso"], charts: false };
  const general = { event: "get_values.rate_limited", limit: "general", max: 30, window_s: 60 };
  const exp = {
    compute: [{ scoring: "ppr", teams: 12, superflex: 0, custom: ["bso"], charts: false }, { custom: ["bso"] }],
    rate_limited: [{ limit: "compute", max: 10, window_s: 60, custom: ["bso"] }, { limit: "general", max: 30 }],
    forbidden: ["Josh Allen", "Ja'Marr Chase"],
  };
  const good = [c(compute), { level: "info", args: ["unrelated text is fine"] }, c(cached), c(limited), c(general)];
  const failures = [];
  const base = checkScenario("self", good, exp);
  if (base.length) failures.push(`a correct log was rejected: ${base.join("; ")}`);
  // Object arguments count as events too (console.log({...})).
  const asObjects = checkScenario("self", good.map((g) => ({ ...g, args: [parseEvent(g.args) || g.args[0]] })), exp);
  if (asObjects.length) failures.push(`object-form events were rejected: ${asObjects.join("; ")}`);

  const mutations = [
    ["missing fresh-compute event", [good[0], good[3], good[4]], "compute.count"],
    ["extra compute event for a cached answer", [...good, c(cached)], "compute.count"],
    ["compute rejection logged as general", [good[0], good[2], c({ ...general }), good[4]], "rate_limited[0].limit"],
    ["rejection logged as a compute", [good[0], good[2], c({ ...compute }), good[4]], "compute.count"],
    ["missing rate-limited event", [good[0], good[2], good[4]], "rate_limited.count"],
    ["full IP field on the event", [c({ ...compute, ip: "1.2.3.4" }), good[2], good[3], good[4]], "compute[0].fields"],
    ["header value leaked in free text", [...good, { level: "log", args: ["key", "jeg1258-client-a"] }], "leak"],
    ["token leaked in an error", [...good, { level: "error", args: [new Error("Bearer jeg1258-token-sentinel")] }], "leak"],
    ["player name in the log", [c({ ...compute }), { level: "log", args: [{ top: "Josh Allen" }] }, good[2], good[3], good[4]], "leak"],
    ["late-listed player name in the log", [...good, { level: "warn", args: ["slow league for Ja'Marr Chase"] }], "leak"],
    ["player name via console.table", [...good, { level: "table", args: [[{ who: "Ja'Marr Chase" }]] }], "leak"],
    ["header value in a raw stderr write", [...good, { level: "stderr", args: ["jeg1258-apikey-sentinel\n"] }], "leak"],
    ["event only as a raw stdout write", [{ level: "stdout", args: [JSON.stringify(compute)] }, good[2], good[3], good[4]], "compute.count"],
    ["missing required field", [c({ ...compute, custom: undefined }), good[2], good[3], good[4]], "compute[0].fields"],
    ["wrong field type", [c({ ...compute, teams: "12" }), good[2], good[3], good[4]], "compute[0].fields"],
    ["charts misreported", [c({ ...compute, charts: true }), good[2], good[3], good[4]], "compute[0].charts"],
    ["custom keys misreported", [c({ ...compute, custom: [] }), good[2], good[3], good[4]], "compute[0].custom"],
    ["plain-text log line instead of an event", [{ level: "log", args: ["fresh compute ppr 12"] }, good[2], good[3], good[4]], "compute.count"],
    ["event split over two arguments", [{ level: "log", args: ["get-values", compute] }, good[2], good[3], good[4]], "compute.count"],
    ["unknown event name", [...good, c({ event: "get_values.computed" })], "unknown-event"],
    ["unknown limit kind", [good[0], good[2], c({ ...limited, limit: "global" }), good[4]], "rate_limited[0].limit"],
  ];
  for (const [label, calls, check] of mutations) {
    const found = checkScenario("self", calls, exp);
    if (!found.some((f) => f.startsWith(`self/${check}:`))) {
      failures.push(`mutation not caught (${label}); wanted ${check}, got ${JSON.stringify(found)}`);
    }
  }
  if (failures.length) {
    for (const f of failures) console.log(`FAIL ${f}`);
    process.exit(1);
  }
  console.log(`self-test: correct log accepted; ${mutations.length} mutations caught`);
  console.log("ok");
  process.exit(0);
}

// --- Harness ----------------------------------------------------------------------------------------

class HarnessError extends Error {}
const must = (cond, msg) => { if (!cond) throw new HarnessError(msg); };

function parseArgs(argv) {
  const o = { dist: null, target: null, expect: null, selfTest: false };
  for (let i = 0; i < argv.length; i += 1) {
    const a = argv[i];
    if (a === "--self-test") o.selfTest = true;
    else if (a === "--target") o.target = argv[++i];
    else if (a === "--expect-failures") o.expect = argv[++i];
    else if (!o.dist) o.dist = a;
    else throw new HarnessError(`unknown argument ${a}`);
  }
  return o;
}

async function main() {
  const opts = parseArgs(process.argv.slice(2));
  if (opts.selfTest) selfTest();
  const dist = resolve(opts.dist || "dist");
  const fnDir = resolve(opts.target || new URL("../../supabase/functions/get-values", import.meta.url).pathname);
  const expected = opts.expect ? JSON.parse(readFileSync(resolve(opts.expect), "utf8")) : null;
  must(!expected || Array.isArray(expected), "--expect-failures file must hold a JSON array of strings");

  // Frozen clock (no real clock read, JEG-1158): a fixed instant that moves only when a scenario says so.
  // Date.now() and new Date() both read it. The results were the same with it set anywhere from
  // 2026-09-10 to 2027-02-10, since only statuses and log events are judged, not values.
  const RealDate = Date;
  const clock = { t: RealDate.UTC(2026, 9, 29, 15) };
  globalThis.Date = class extends RealDate {
    constructor(...a) { super(...(a.length ? a : [clock.t])); }
    static now() { return clock.t; }
  };

  // No network: the published site's files come from dist/, every other host throws.
  globalThis.fetch = async (url) => {
    const u = new URL(String(url));
    if (u.host !== SITE_HOST) throw new HarnessError(`network blocked: ${u.host}`);
    const path = u.pathname.replace(/^\/fantasy-tools/, "");
    const file = join(dist, path === "/" || path === "" ? "index.html" : path);
    let body;
    try { body = readFileSync(file); } catch { return new Response("not found", { status: 404 }); }
    return new Response(body, { status: 200 });
  };
  globalThis.Deno = { env: { get: () => undefined }, serve: (h) => { globalThis.__jeg1258Handler = h; } };

  // Output capture, from just before each module import to the end of its scenario: every function on
  // console (log, info, warn, error, debug, trace, dir, table, assert, ...) and every raw stdout/stderr
  // write is recorded and kept off the real output. Console calls can be events; raw writes are only
  // read by the leak scan.
  const methods = Object.keys(console).filter((k) => typeof console[k] === "function");
  const real = Object.fromEntries(methods.map((m) => [m, console[m]]));
  const realWrite = { stdout: process.stdout.write, stderr: process.stderr.write };
  let calls = null;
  const capture = () => {
    calls = [];
    for (const m of methods) console[m] = (...args) => { calls.push({ level: m, args }); };
    for (const s of ["stdout", "stderr"]) {
      process[s].write = (chunk, ...rest) => {
        calls.push({ level: s, args: [String(chunk)] });
        const cb = rest.find((r) => typeof r === "function");
        if (cb) cb();
        return true;
      };
    }
  };
  const release = () => {
    for (const m of methods) console[m] = real[m];
    for (const s of ["stdout", "stderr"]) process[s].write = realWrite[s];
    const c = calls; calls = null; return c;
  };

  const indexUrl = pathToFileURL(join(fnDir, "index.ts")).href;
  async function freshHandler(name) {
    globalThis.__jeg1258Handler = null;
    await import(`${indexUrl}?jeg1258=${name}`);
    must(typeof globalThis.__jeg1258Handler === "function", `${name}: index.ts registered no Deno.serve handler`);
    return globalThis.__jeg1258Handler;
  }

  const fnUrl = "https://fn.test/functions/v1/get-values";
  const headers = (who) => ({ ...HEADERS, "x-forwarded-for": client(who) });
  const post = (h, who, body) => h(new Request(fnUrl, {
    method: "POST", headers: { ...headers(who), "content-type": "application/json" }, body: JSON.stringify(body) }));
  const get = (h, who, query) => h(new Request(`${fnUrl}?${query}`, { headers: headers(who) }));
  // Every player name in every answer; none may reach the output. player_key is a bare number, so a
  // substring scan for it would trip on ordinary numbers (ms, limits); the field whitelist keeps it off
  // events, but a numeric key in free text is not detected.
  const forbidden = new Set();
  const expectStatus = async (label, res, status) => {
    must(res.status === status, `${label}: expected HTTP ${status}, got ${res.status}`);
    if (status === 204) return null;
    const body = await res.json();
    for (const p of Array.isArray(body.players) ? body.players : []) {
      if (typeof p.name === "string" && p.name.length >= 4) forbidden.add(p.name);
    }
    return body;
  };
  const limitedBody = (label, body) => must(body.error === "rate limited" && body.retry_after_seconds === 60,
    `${label}: 429 body changed: ${JSON.stringify(body)}`);
  // What the compute event must say, from the answer itself (existing request semantics).
  const computeOf = (body, charts) => {
    must(Array.isArray(body.players) && body.players.length > 50, `answer priced ${body.players?.length} players`);
    return { scoring: body.setting.scoring, teams: body.setting.teams, superflex: body.setting.superflex,
      custom: body.league_custom, charts };
  };

  const scenarios = [
    ["fresh-custom", async (h) => {
      // Two fresh custom-league computes: one plain, one with include=charts and superflex.
      let b = await expectStatus("custom ppr", await post(h, "a", { scoring: "ppr", teams: 12, league: { bso: 0.2 } }), 200);
      must(sameList(b.league_custom, ["bso"]), `custom ppr: league_custom ${JSON.stringify(b.league_custom)}`);
      const compute = [computeOf(b, false)];
      b = await expectStatus("custom charts", await post(h, "a",
        { scoring: "half_ppr", teams: 10, superflex: 1, include: "charts", league: { bso: 0.2, conf: 1.5 } }), 200);
      must(b.league_custom.length > 0, "custom charts: league_custom is empty");
      compute.push(computeOf(b, true));
      return { compute, rate_limited: [] };
    }],
    ["cache", async (h) => {
      // The same custom league again (POST, then GET with the league as a JSON string) is answered from
      // memory: no compute event. After the 5-minute TTL it is computed again: a second event.
      const league = { bso: 0.25, inj: "all" };
      const b = await expectStatus("first", await post(h, "b", { scoring: "ppr", teams: 12, league }), 200);
      await expectStatus("repeat POST", await post(h, "b", { scoring: "ppr", teams: 12, league }), 200);
      await expectStatus("repeat GET", await get(h, "b", `scoring=ppr&teams=12&league=${encodeURIComponent(JSON.stringify(league))}`), 200);
      clock.t += 5 * 60 * 1000 + 1000;
      const again = await expectStatus("after TTL", await post(h, "b", { scoring: "ppr", teams: 12, league }), 200);
      return { compute: [computeOf(b, false), computeOf(again, false)], rate_limited: [] };
    }],
    ["default", async (h) => {
      // The default league is never a custom compute, cached or not; bad input is a 400 with no event.
      let b = await expectStatus("default POST", await post(h, "c", { scoring: "ppr", teams: 12 }), 200);
      must(b.league_custom.length === 0, "default POST: league_custom not empty");
      await expectStatus("default GET", await get(h, "c", "scoring=half_ppr&teams=10"), 200);
      b = await expectStatus("garbage league GET", await get(h, "c", "league=%7Bnot-json"), 200);
      must(b.league_custom.length === 0, "garbage league GET: league_custom not empty");
      await expectStatus("default charts", await post(h, "c", { scoring: "standard", teams: 14, include: "charts" }), 200);
      await expectStatus("invalid teams", await post(h, "c", { scoring: "ppr", teams: 9 }), 400);
      await expectStatus("OPTIONS", await h(new Request(fnUrl, { method: "OPTIONS", headers: headers("c") })), 204);
      return { compute: [], rate_limited: [] };
    }],
    ["compute-limit", async (h) => {
      // Ten fresh computes pass, the 11th in the minute from one key is a 429 (one rate_limited event,
      // no compute event), a cached league is still served to that key, another key has its own
      // budget, and the window resets after a minute.
      const compute = [];
      for (let i = 0; i < 10; i += 1) {
        const b = await expectStatus(`compute ${i + 1}`, await post(h, "d", { scoring: "ppr", teams: 12, league: { bso: 0.02 + i * 0.01 } }), 200);
        compute.push(computeOf(b, false));
      }
      const r = await post(h, "d", { scoring: "ppr", teams: 12, league: { bso: 0.12 } });
      limitedBody("11th compute", await expectStatus("11th compute", r, 429));
      const rate_limited = [{ limit: "compute", max: 10, window_s: 60, scoring: "ppr", teams: 12, superflex: 0,
        custom: compute[0].custom, charts: false }];
      await expectStatus("cached after limit", await post(h, "d", { scoring: "ppr", teams: 12, league: { bso: 0.02 + 9 * 0.01 } }), 200);
      let b = await expectStatus("other key", await post(h, "e", { scoring: "ppr", teams: 12, league: { bso: 0.13 } }), 200);
      compute.push(computeOf(b, false));
      clock.t += 61 * 1000;
      b = await expectStatus("after window", await post(h, "d", { scoring: "ppr", teams: 12, league: { bso: 0.14 } }), 200);
      compute.push(computeOf(b, false));
      return { compute, rate_limited };
    }],
    ["general-limit", async (h) => {
      // 30 requests a minute per key (here cheap 400s), the 31st is a 429 with a general event; a
      // preflight is never limited and another key is unaffected.
      for (let i = 0; i < 30; i += 1) await expectStatus(`request ${i + 1}`, await get(h, "f", "scoring=bogus"), 400);
      limitedBody("31st request", await expectStatus("31st request", await get(h, "f", "scoring=bogus"), 429));
      await expectStatus("OPTIONS after limit", await h(new Request(fnUrl, { method: "OPTIONS", headers: headers("f") })), 204);
      await expectStatus("other key", await get(h, "g", "scoring=bogus"), 400);
      return { compute: [], rate_limited: [{ limit: "general", max: 30, window_s: 60 }] };
    }],
  ];

  const results = [];
  for (const [name, run] of scenarios) {
    capture();
    let exp;
    try { exp = await run(await freshHandler(name)); } finally { results.push({ name, calls: release(), exp }); }
  }
  globalThis.Date = RealDate;

  const violations = [];
  for (const r of results) violations.push(...checkScenario(r.name, r.calls, { ...r.exp, forbidden: [...forbidden] }));
  for (const r of results) {
    const mine = violations.filter((x) => x.startsWith(`${r.name}/`));
    console.log(`${mine.length ? "FAIL" : "PASS"} ${r.name} (${r.calls.length} output calls)`);
  }
  for (const x of violations) console.log(`  ${x}`);

  if (expected) {
    const unexpected = violations.filter((x) => !expected.includes(x));
    const fixed = expected.filter((x) => !violations.includes(x));
    for (const x of unexpected) console.log(`UNEXPECTED FAILURE ${x}`);
    for (const x of fixed) console.log(`UNEXPECTED PASS ${x} (update the expected-failures file)`);
    if (unexpected.length || fixed.length) process.exit(1);
    console.log(`statuses unchanged; contract violations match the ${expected.length} recorded`);
    console.log("ok");
    process.exit(0);
  }
  if (violations.length) {
    console.log(`${violations.length} contract violation(s)`);
    process.exit(1);
  }
  console.log("ok");
  process.exit(0);
}

main().catch((e) => {
  // Harness failures are never folded into the contract result.
  process.stdout.write(`HARNESS FAILURE ${e instanceof HarnessError ? e.message : e?.stack || e}\n`);
  process.exit(2);
});
