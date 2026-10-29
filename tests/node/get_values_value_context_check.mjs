// JEG-1225 (slice 4b): get-values prices under a share link's value basis and player overrides.
// Runs the deployed handler (supabase/functions/get-values/index.ts) in node with a stub Deno and a fetch that
// serves the built dist/ plus the site's link reader (app/v2/ddf-value-link.js at /v2/), as
// get_values_week_check.mjs does, and compares it with the parity runner given the same basis and ov.
// tests/test_endpoint_parity.py (test_value_context_parity) ties the runner to the page.
// Usage: node --experimental-strip-types tests/node/get_values_value_context_check.mjs <dist dir>
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { createRequire } from "node:module";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import vm from "node:vm";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
const dist = resolve(process.argv[2] || join(ROOT, "dist"));
const require = createRequire(import.meta.url);
const ValueLink = require("../../app/v2/ddf-value-link.js");
const { canonicalBasis } = await import("../../supabase/functions/get-values/value-context.ts");

// One handler instance per scenario (the bundle and the link reader are cached per instance).
let scenario = 0;
async function handlerFor({ drop = [], bundle: patchBundle = null } = {}) {
  let handler = null;
  globalThis.Deno = { env: { get: () => undefined }, serve: (h) => { handler = h; } };
  delete globalThis.DDFValueLink;
  globalThis.fetch = async (url) => {
    const path = new URL(String(url)).pathname.replace(/^\/fantasy-tools/, "");
    if (drop.some((d) => path.endsWith(d))) return new Response("not found", { status: 404 });
    const file = path === "/v2/ddf-value-link.js" ? join(ROOT, "app/v2/ddf-value-link.js")
      : join(dist, path === "/" || path === "" ? "index.html" : path);
    let body;
    try { body = readFileSync(file); } catch { return new Response("not found", { status: 404 }); }
    if (patchBundle && path === "/assets/comparison-sources-data.json") {
      const doc = JSON.parse(String(body));
      patchBundle(doc);
      body = JSON.stringify(doc);
    }
    return new Response(body, { status: 200 });
  };
  scenario += 1;
  await import(`../../supabase/functions/get-values/index.ts?vc=${scenario}`);
  assert.equal(typeof handler, "function", "index.ts registered a Deno.serve handler");
  let ip = 0;
  const post = (body) => handler(new Request("https://fn.test/functions/v1/get-values", {
    method: "POST", headers: { "content-type": "application/json", "x-forwarded-for": `10.1.${scenario}.${++ip}` },
    body: JSON.stringify(body) }));
  const get = (query) => handler(new Request(`https://fn.test/functions/v1/get-values?${query}`, {
    headers: { "x-forwarded-for": `10.1.${scenario}.${++ip}` } }));
  return { post, get };
}

function runner(scoring, basis, ov) {
  const args = ["--experimental-strip-types", "--no-warnings", join(ROOT, "tests/_edge_pipeline_runner.cjs"),
    "--dist", dist, "--scoring", scoring, "--teams", "12", "--superflex", "0", "--with-week", "1"];
  if (basis) args.push("--basis", basis);
  if (ov) args.push("--ov", ov);
  return JSON.parse(execFileSync("node", args, { maxBuffer: 1 << 28 }));
}

const byKey = (body) => Object.fromEntries(body.players.map((p) => [String(p.player_key), p]));
function sameValues(body, expected, label) {
  assert.ok(body.players.length > 50, `${label}: priced players`);
  const bad = body.players.filter((p) => Math.abs(p.value - (expected[p.player_key] ?? 0)) > 0.06);
  assert.equal(bad.length, 0, `${label}: ${bad.length} values differ from the runner: ${JSON.stringify(bad.slice(0, 3))}`);
  const missing = Object.entries(expected).filter(([pk, v]) => Math.round(v * 10) / 10 !== 0 && !(pk in byKey(body)));
  assert.equal(missing.length, 0, `${label}: runner prices players the endpoint leaves out: ${missing.slice(0, 3)}`);
}

const { post, get } = await handlerFor();

// 1. Our methodology: the top players, by key, to override.
const ours = {};
for (const scoring of ["standard", "half_ppr", "ppr"]) {
  const res = await post({ scoring, teams: 12 });
  assert.equal(res.status, 200);
  ours[scoring] = await res.json();
  assert.deepEqual(ours[scoring].value_context, { basis: null, basis_applied: true, basis_members: [],
    basis_fell_back_to_default: false, overrides: {}, overrides_applied: 0, overrides_not_priced: [] }, scoring);
  assert.ok(!ours[scoring].players.some((p) => "override" in p), `${scoring}: no override fields without overrides`);
}
const [a, b, c] = ours.ppr.players.slice(0, 3).map((p) => p.player_key);
const UNPRICED = 16777000; // a player key no source prices

// 2. In each scoring, a custom basis with an absolute override and an adjustment prices as the runner does,
// and the context moves DDF Value (a context that changed nothing would pass the comparison above).
const CASES = [
  { basis: "fantasycalc", ov: null },
  { basis: "blend:espn.60_razzball.40", ov: `${a}:58,${b}:+5,${c}:-3,${UNPRICED}:40` },
  { basis: null, ov: `${a}:58` },
];
for (const scoring of ["standard", "half_ppr", "ppr"]) {
  for (const { basis, ov } of CASES) {
    const label = `${scoring} basis=${basis} ov=${ov}`;
    const res = await post({ scoring, teams: 12, ...(basis ? { basis } : {}), ...(ov ? { ov } : {}) });
    assert.equal(res.status, 200, label);
    const body = await res.json();
    const expected = runner(scoring, basis, ov);
    sameValues(body, expected.values, label);
    const moved = body.players.filter((p) => Math.abs(p.value - (byKey(ours[scoring])[p.player_key]?.value ?? 0)) > 0.1);
    assert.ok(moved.length >= 1, `${label}: the value context changes DDF Value`);
    const vc = body.value_context;
    assert.deepEqual(vc.basis, expected.value_context.basis, label);
    assert.equal(vc.basis_applied, true, label);
    if (basis) assert.ok(vc.basis_members.length >= 1, `${label}: the basis has members`);
    if (ov) {
      const rows = byKey(body);
      assert.equal(rows[a].value, 58, `${label}: the absolute override is the value`);
      assert.equal(rows[a].override, 58, label);
      assert.equal(typeof rows[a].pipeline_value, "number", label);
      if (basis) {
        assert.deepEqual(rows[b].override, { type: "adjustment", delta: 5 }, label);
        assert.ok(Math.abs(rows[b].value - (rows[b].pipeline_value + 5)) < 0.06, `${label}: +5 on the basis' own value`);
        assert.ok(Math.abs(rows[c].value - (rows[c].pipeline_value - 3)) < 0.06, `${label}: -3`);
        assert.equal(vc.overrides_applied, 3, label);
        assert.deepEqual(vc.overrides_not_priced, [UNPRICED], `${label}: the unpriced override is named, not added`);
        assert.ok(!(String(UNPRICED) in rows), label);
      } else assert.equal(vc.overrides_applied, 1, label);
    }
  }
}

// 3. The same context written another way is the same answer (packed ov, GET query with "+" read as a space),
// and a different ov is a different answer (the cache key carries the context).
{
  const plainOv = `${a}:58,${b}:+5`;
  const packedOv = `z2:${ValueLink.packOverridesWithTypes({ [a]: 58, [b]: { type: "adjustment", delta: 5 } })}`;
  const one = await (await post({ scoring: "ppr", teams: 12, basis: "fantasycalc", ov: plainOv })).json();
  const two = await (await post({ scoring: "ppr", teams: 12, basis: "fantasycalc", ov: packedOv })).json();
  const three = await (await get(`scoring=ppr&teams=12&basis=fantasycalc&ov=${a}:58,${b}:+5`)).json();
  assert.deepEqual(two.players, one.players, "packed ov");
  assert.deepEqual(three.players, one.players, "GET with + read as a space");
  const other = await (await post({ scoring: "ppr", teams: 12, basis: "fantasycalc", ov: `${a}:57` })).json();
  assert.equal(byKey(other)[a].value, 57, "a different ov is not served from the cache");
  const back = await (await post({ scoring: "ppr", teams: 12 })).json();
  assert.deepEqual(back.players, ours.ppr.players, "our methodology again after custom answers");
}

// 4. Unreadable parts are an error that names them, never a silent fall back to our methodology.
for (const [body, unread] of [
  [{ basis: "notasource" }, ["basis"]],
  [{ ov: "x" }, ["ov"]],
  [{ basis: "blend:nope.50", ov: "abc:5" }, ["basis", "ov"]],
]) {
  const res = await post({ scoring: "ppr", teams: 12, ...body });
  assert.equal(res.status, 400, JSON.stringify(body));
  const out = await res.json();
  assert.equal(out.code, "value_context_unreadable");
  assert.deepEqual(out.unread, unread);
}

// 5. A site that does not publish the link reader yet: requests without a context still answer; with one, a
// clear 503 (never our methodology under the caller's name).
{
  const old = await handlerFor({ drop: ["/v2/ddf-value-link.js"] });
  assert.equal((await old.post({ scoring: "ppr", teams: 12 })).status, 200);
  const res = await old.post({ scoring: "ppr", teams: 12, basis: "fantasycalc" });
  assert.equal(res.status, 503);
  assert.equal((await res.json()).code, "value_context_unavailable");
}

// 6. What the site writes is what get-values reads: the Overrides module's share link, read back here, is the
// context the runner priced (one reader of the link format).
{
  const win = { document: { getElementById: () => null, querySelector: () => null, addEventListener() {}, dispatchEvent: () => true },
    localStorage: { getItem: () => null, setItem() {}, removeItem() {} },
    sessionStorage: { getItem: () => null, setItem() {}, removeItem() {} },
    addEventListener() {}, dispatchEvent: () => true, matchMedia: () => ({ matches: false, addEventListener() {} }),
    CustomEvent: class {}, URLSearchParams, btoa, atob, console };
  win.window = win; win.self = win;
  vm.createContext(win);
  for (const file of ["app/v2/ddf-value-link.js", "app/v2/overrides.js"]) {
    vm.runInContext(readFileSync(join(ROOT, file), "utf8"), win, { filename: file });
  }
  const engine = { basis: null, getAllRows: () => [], searchPlayers: () => [], setValueOverrides() {},
    setBasis(x) { this.basis = x; return { ok: true }; },
    getBasis() { return this.basis ? { isDefault: false, ...this.basis } : { isDefault: true, mode: "default" }; } };
  win.DDFOverrides.boot(engine);
  assert.equal(win.DDFOverrides.applyLink(new URLSearchParams(
    `valuecontext=1&basis=${encodeURIComponent("blend:espn.60_razzball.40")}&ov=${encodeURIComponent(`${a}:58,${b}:+5`)}`)), true);
  const link = new URLSearchParams(win.DDFOverrides.shareLink("#find-trade?mine=1").hash.split("?")[1]);
  const body = await (await post({ scoring: "half_ppr", teams: 12, basis: link.get("basis"), ov: link.get("ov") })).json();
  sameValues(body, runner("half_ppr", "blend:espn.60_razzball.40", `${a}:58,${b}:+5`).values, "site share link");
}

// 7. The engine form of a basis is the site engine's own (curve-widget.js canonicalBasis, lifted read-only):
// every basis the link reader can return, and an equal-weight blend of our four charts is our methodology.
{
  const src = readFileSync(join(ROOT, "app/trade-value-chart/assets/curve-widget.js"), "utf8");
  const lift = (name) => {
    const start = src.indexOf(`function ${name}(`);
    assert.ok(start > 0, `curve-widget.js has ${name}()`);
    let depth = 0;
    for (let i = src.indexOf("{", start); i < src.length; i++) {
      if (src[i] === "{") depth++;
      else if (src[i] === "}" && --depth === 0) return src.slice(start, i + 1);
    }
    throw new Error(`no end of ${name}()`);
  };
  const constOf = (name) => {
    const m = src.match(new RegExp(`const ${name} = ([^;]+);`));
    assert.ok(m, `curve-widget.js has ${name}`);
    return `const ${name} = ${m[1]};`;
  };
  const site = vm.runInNewContext(`(() => {
    ${constOf("COMPOSITE_INPUT_KEYS")} ${constOf("BASIS_SOURCE_KEYS")} ${constOf("BASIS_MAX_WEIGHT")}
    const normalizeInputKey = key => key;
    ${lift("canonicalBasis")}
    return canonicalBasis;
  })()`);
  const keys = ValueLink.BASIS_KEYS;
  const texts = [...keys, "blend:fantasycalc.25_usatoday.25_fantasypros.25_cbs.25", "blend:cbs.1_fantasypros.1_usatoday.1_fantasycalc.1",
    "blend:fantasycalc.25_usatoday.25_fantasypros.25_cbs.24", "blend:cbs.40_espn.60"];
  let seed = 7;
  const rand = (n) => { seed = (seed * 1103515245 + 12345) % 2147483648; return seed % n; };
  for (let i = 0; i < 2000; i++) {
    const parts = Array.from({ length: 1 + rand(7) }, () => `${keys[rand(keys.length)]}.${[1, 5, 25, 25, 60, 100, 140][rand(7)]}`);
    texts.push(`blend:${parts.join("_")}`);
  }
  for (const t of texts) {
    const parsed = ValueLink.parseBasisParam(t);
    // overrides.js hands the engine its basis record (setBasisState -> basisRecord), which the site canonicalises.
    const record = parsed.mode === "single" ? { mode: "single", source: parsed.source }
      : { mode: "blend", sources: keys.filter((k) => parsed.sources.includes(k)), weights: parsed.weights };
    const want = site(record);
    assert.ok(want.ok, t);
    assert.deepEqual(JSON.parse(JSON.stringify(canonicalBasis(ValueLink, parsed))), JSON.parse(JSON.stringify(want.value)), t);
  }
}

// 8. JEG-1288 (review of #1124): get-values answers only under the exact context it was asked for.
// 8a. A requested basis source that is not available here (ESPN held) is refused, never priced under the fallback.
{
  const held = await handlerFor({ bundle: (doc) => { doc.source_validation = { ...(doc.source_validation || {}), espn: "held" }; } });
  for (const basis of ["espn", "blend:espn.50_fantasycalc.50"]) {
    for (const time of ["first", "again"]) {
      const res = await held.post({ scoring: "ppr", teams: 12, basis });
      const out = await res.json();
      assert.equal(res.status, 422, `${basis} (${time}): an unavailable basis is refused, got ${res.status}`);
      assert.equal(out.code, "basis_unavailable", basis);
      assert.deepEqual(out.unavailable, ["espn"], basis);
      assert.ok(!("players" in out), `${basis}: no prices under another basis`);
      assert.ok(!out.available.includes("espn") && out.available.includes("fantasycalc"), `${basis}: names what is available`);
    }
  }
  const fine = await held.post({ scoring: "ppr", teams: 12, basis: "fantasycalc" });
  assert.equal(fine.status, 200, "an available basis still answers");
  assert.equal((await fine.json()).value_context.basis_applied, true);
  assert.equal((await held.post({ scoring: "ppr", teams: 12 })).status, 200, "no context still answers");
}
// 8b. A part with any entry that cannot be read is refused as a whole (the review's three cases).
for (const [body, unread, why] of [
  [{ basis: "blend:espn.50_nope.50" }, ["basis"], /nope/],
  [{ ov: "101:58,202:garbage" }, ["ov"], /202:garbage/],
  [{ ov: "z2:AAABAgJEAQ" }, ["ov"], /z2/],
]) {
  const res = await post({ scoring: "ppr", teams: 12, ...body });
  const out = await res.json();
  assert.equal(res.status, 400, `${JSON.stringify(body)}: partly unreadable is refused, got ${res.status}`);
  assert.equal(out.code, "value_context_unreadable", JSON.stringify(body));
  assert.deepEqual(out.unread, unread, JSON.stringify(body));
  assert.match(out.error, why, JSON.stringify(body));
}
// 8c. Size bounds, checked before the link is read or anything is cached or priced: the reader is dropped here, so
// a bounded request that got as far as reading would be a 503, not a 413.
{
  const { MAX_BASIS_TEXT, MAX_OV_TEXT, MAX_OVERRIDES } = await import("../../supabase/functions/get-values/value-context.ts");
  assert.ok(MAX_OVERRIDES >= 2000 && MAX_OV_TEXT >= 32768 && MAX_BASIS_TEXT >= 256, "bounds have headroom over the site's player list");
  const noReader = await handlerFor({ drop: ["/v2/ddf-value-link.js"] });
  const big = Array.from({ length: 10001 }, (_, i) => `${i + 1}:50`).join(",");
  for (const [body, label] of [[{ ov: big }, "10,001 plain overrides"], [{ basis: `blend:${"cbs.1_".repeat(60)}` }, "a long basis"]]) {
    for (const h of [noReader, { post }]) {
      const res = await h.post({ scoring: "ppr", teams: 12, ...body });
      assert.equal(res.status, 413, `${label}: refused before reading, got ${res.status}`);
      assert.equal((await res.json()).code, "value_context_too_large", label);
    }
  }
  const pack = (n) => `z2:${ValueLink.packOverridesWithTypes(Object.fromEntries(Array.from({ length: n }, (_, i) => [String(i + 1), 50])))}`;
  const over = await post({ scoring: "ppr", teams: 12, ov: pack(MAX_OVERRIDES + 1) });
  assert.equal(over.status, 413, `${MAX_OVERRIDES + 1} packed overrides (short text) are refused by count`);
  assert.equal((await over.json()).code, "value_context_too_large");
  const most = await post({ scoring: "ppr", teams: 12, ov: pack(MAX_OVERRIDES) });
  assert.equal(most.status, 200, `${MAX_OVERRIDES} overrides, the most allowed, still answer`);
}

console.log("ok");
