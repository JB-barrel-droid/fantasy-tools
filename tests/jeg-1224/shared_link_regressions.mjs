// JEG-1224: failing-before regression specs for value basis and override loss across
// Copy link, read_state and return-to-site. Isolated harness: it loads the shipped
// modules read-only (no production code is patched) and is not wired into make.
//
//   node --experimental-strip-types --no-warnings tests/jeg-1224/shared_link_regressions.mjs
//   node ... shared_link_regressions.mjs --strict    exit 1 while any spec still fails
//   node ... shared_link_regressions.mjs --json      machine-readable results
//   node ... tests/jeg-1224/harness_mutations.mjs    proves each guard rejects a broken input (JEG-1254)
//
// Each case declares `today`: "fail" (a regression spec that fails on main until fixed)
// or "pass" (a guard on behaviour that is already right). Without --strict the run
// exits 0 only when every case matches its declaration, so a fix that lands shows up
// as "now passes: flip to pass" instead of silently changing the record.
//
// JEG-1254: an unmet contract and a broken harness are told apart. Only the shipped call
// under test (wrapped in underTest) may fail a spec, by returning a wrong result or by
// throwing. Anything else that throws (module load, fixture, a precondition, a writer the
// harness can no longer find, a malformed case result) is a HARNESS ERROR: every mode,
// --strict and --json included, exits 2, and it is never counted as a failing spec.
// Exit codes: 0 matches the record, 1 differs from it (or --strict with a spec failing), 2 harness error.
// Spec and contract: docs/qa/jeg-1224/README.md.
import { createRequire } from "node:module";
import { readFileSync } from "node:fs";
import { isDeepStrictEqual } from "node:util";
import vm from "node:vm";
import { fileURLToPath } from "node:url";
import { dirname, join, resolve } from "node:path";

const require = createRequire(import.meta.url);
const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
const read = rel => readFileSync(join(ROOT, rel), "utf8");
// Values built inside a vm context have that context's prototypes, which isDeepStrictEqual
// would count as a difference; compare their plain JSON shape instead.
const plain = v => (v === undefined ? undefined : JSON.parse(JSON.stringify(v)));
const same = (a, b) => isDeepStrictEqual(plain(a), plain(b));

// ---------- failure classes ----------
// The harness itself is broken: setup, fixtures, preconditions, extraction.
export class HarnessError extends Error {}
// The shipped call under test threw or answered with an error: the contract is unmet.
export class ContractUnmet extends Error {}
export const precondition = (ok, message) => { if (!ok) throw new HarnessError(`precondition: ${message}`); };
// Wrap only the shipped call a case is about. Its throw is the runtime's, not the harness's.
export function underTest(label, fn) {
  const unmet = error => { throw new ContractUnmet(`${label} threw: ${error && error.message}`); };
  let out;
  try { out = fn(); } catch (error) { unmet(error); }
  return out && typeof out.then === "function" ? out.catch(unmet) : out;
}

// ---------- shipped sources (read-only) ----------
// The harness reads each module once; a mutation run (harness_mutations.mjs) passes edited copies.
export async function shippedEnv() {
  try {
    const DDFState = require(join(ROOT, "app/v2/ddf-state.js"));
    const { handleRpc } = await import(join(ROOT, "supabase/functions/mcp/rpc.ts"));
    return {
      DDFState, handleRpc,
      overridesSrc: read("app/v2/overrides.js"), linkSrc: read("app/v2/ddf-value-link.js"), stateSrc: read("app/v2/ddf-state.js"),
      assistSrc: read("app/v2/ddf-assist.js"), v2Src: read("app/v2/v2.js"),
    };
  } catch (error) { throw new HarnessError(`loading shipped modules: ${error.message}`); }
}

// ---------- synthetic, non-private fixtures ----------
// Made-up players and keys; no real league or roster.
const ROWS = [
  { player_key: 101, name: "Alpha Back", pos: "RB", team: "AAA", value: 40 },
  { player_key: 202, name: "Bravo Wide", pos: "WR", team: "BBB", value: 30 },
  { player_key: 303, name: "Charlie Arm", pos: "QB", team: "CCC", value: 20 },
  { player_key: 404, name: "Delta End", pos: "TE", team: "DDD", value: 10 },
];
const ORIGIN = "https://site.test";
const LEAGUE = "scoring=half_ppr&teams=10&roster=QB1.RB2.WR3.TE1.FLEX1.SF0.BN6";
// A Compare link in the legacy shape older tradeHash() writers produced (no valuecontext=1).
// Links already shared carry it, so the reader keeps its unmarked behaviour for them (O1L).
const COMPARE_LEGACY_CUSTOM = `${ORIGIN}/#compare-trade?give=101&get=202&${LEAGUE}&basis=fantasycalc&ov=101:58`;
// A Find a trade link as finder shareLink() writes it for a sender on our methodology (explicit default).
const FINDER_DEFAULT = `${ORIGIN}/#find-trade?mine=101,303&theirs=202,404&${LEAGUE}&v=1&valuecontext=1`;
// The same with a custom blend and an adjustment.
const FINDER_CUSTOM = `${ORIGIN}/#find-trade?mine=101,303&theirs=202,404&${LEAGUE}&v=1&valuecontext=1&basis=blend%3Aespn.60_razzball.40&ov=202%3A%2B5`;
// What the shipped reader decodes FINDER_CUSTOM to (pinned by guard O4).
export const FINDER_CUSTOM_CONTEXT = {
  basis: { mode: "blend", sources: ["espn", "razzball"], weights: { espn: 60, razzball: 40 } },
  overrides: { 202: { type: "adjustment", delta: 5 } },
};
export const FIXTURES = { ORIGIN, LEAGUE, ROWS, COMPARE_LEGACY_CUSTOM, FINDER_DEFAULT, FINDER_CUSTOM };

// ---------- page module loaders (read-only, in a fresh context each time) ----------
function memoryStorage(seed) {
  const m = new Map(Object.entries(seed || {}));
  return { getItem: k => (m.has(k) ? m.get(k) : null), setItem: (k, v) => m.set(k, String(v)), removeItem: k => m.delete(k), dump: () => Object.fromEntries(m) };
}
function fakeEngine() {
  const E = { basis: null, overrides: {} };
  E.getAllRows = () => ROWS;
  E.searchPlayers = () => [];
  E.setBasis = b => { E.basis = b; };
  E.setValueOverrides = v => { E.overrides = { ...v }; };
  E.getBasis = () => {
    const b = E.basis;
    if (!b) return { isDefault: true, mode: "default", label: "our methodology" };
    return b.mode === "single" ? { isDefault: false, mode: "single", source: b.source, label: b.source }
      : { isDefault: false, mode: "blend", sources: b.sources, weights: b.weights, label: "blend" };
  };
  return E;
}
function pageContext({ local, session } = {}) {
  const doc = { getElementById: () => null, querySelector: () => null, dispatchEvent: () => true, addEventListener() {} };
  const win = {
    document: doc, localStorage: memoryStorage(local), sessionStorage: memoryStorage(session),
    location: { href: `${ORIGIN}/`, hash: "" }, addEventListener() {}, dispatchEvent: () => true,
    matchMedia: () => ({ matches: false, addEventListener() {} }), console, CustomEvent, URLSearchParams, btoa, atob,
    navigator: {}, setTimeout, clearTimeout,
  };
  win.window = win; win.self = win; win.globalThis = win;
  vm.createContext(win);
  return win;
}
// A writer is lifted out of v2.js by name and run beside the real Overrides module.
// Brace matching is enough: the lifted writer has no unbalanced brace inside a string.
function liftFunction(src, name) {
  const start = src.indexOf(`function ${name}(`);
  if (start < 0) throw new HarnessError(`writer ${name}() not found in app/v2/v2.js; point the harness at the new writer`);
  let depth = 0;
  for (let i = src.indexOf("{", start); i > 0 && i < src.length; i++) {
    if (src[i] === "{") depth++;
    else if (src[i] === "}" && --depth === 0) return src.slice(start, i + 1);
  }
  throw new HarnessError(`writer ${name}() in app/v2/v2.js has no closing brace`);
}

export function makeHarness(env) {
  const { DDFState, handleRpc } = env;
  // The Overrides module (basis + player overrides), booted with a reader's saved record.
  function loadOverrides(saved) {
    const win = pageContext({ local: saved ? { "ddf-v2-value-overrides": JSON.stringify(saved) } : {} });
    if (env.linkSrc) vm.runInContext(env.linkSrc, win, { filename: "app/v2/ddf-value-link.js" });
    vm.runInContext(env.overridesSrc, win, { filename: "app/v2/overrides.js" });
    precondition(win.DDFOverrides && typeof win.DDFOverrides.applyLink === "function", "overrides.js exposes DDFOverrides.applyLink");
    const engine = fakeEngine();
    win.DDFOverrides.boot(engine);
    return { win, O: win.DDFOverrides, engine };
  }
  // The Copy link module, with the Overrides module beside it holding the sender's context.
  function loadAssist({ view, give = [], get = [], mine = [], theirs = [], saved }) {
    const { win, O } = loadOverrides(saved);
    vm.runInContext(env.stateSrc, win, { filename: "app/v2/ddf-state.js" });
    win.TradeValueFinder = { normName: n => String(n || "").toLowerCase().trim(), ui: { getMine: () => mine, getTheirs: () => theirs, setSides: () => ({ bothSides: [] }) } };
    vm.runInContext(env.assistSrc, win, { filename: "app/v2/ddf-assist.js" });
    win.DDFAssist.attach({
      engine: { getAllRows: () => ROWS }, view: () => view, getTrade: () => ({ give, get }),
      getTarget: () => "", sources: () => ["fantasycalc"], leagueQuery: () => LEAGUE, leagueText: () => "10 teams, Half PPR",
    });
    return { win, O, A: win.DDFAssist };
  }
  // The Compare a trade writer (v2.js tradeHash) as the sender's page runs it: the real
  // Overrides module supplies shareParams/shareLink; the trade and league parts are fixtures.
  function compareWriter(sender, { give, receive }) {
    const src = liftFunction(env.v2Src, "tradeHash");
    sender.win.__TR = { give, receive };
    sender.win.__LEAGUE_PARTS = LEAGUE.split("&");
    const tradeHash = vm.runInContext(`(function () { let shareDroppedOverrides = false; const TR = window.__TR;
      const leagueLinkParts = () => window.__LEAGUE_PARTS.slice(); ${src}; return tradeHash; })()`, sender.win, { filename: "app/v2/v2.js#tradeHash" });
    return underTest("tradeHash()", () => tradeHash());
  }
  const p = query => new URLSearchParams(query);
  const queryOf = link => String(link || "").split("?")[1] || "";
  const sideKeys = list => list.map(r => ({ key: String(r.player_key), name: r.name }));

  // ---------- MCP ----------
  // JEG-1343: the stub prices a sent value context as get-values does since JEG-1225 (plain ov only: key:value
  // sets, key:+n / key:-n adjusts) and says so in value_context; without one it answers as before.
  const stubValues = async (scoring, teams, superflex, _league, _week, context) => {
    const overrides = {};
    for (const part of String((context && context.ov) || "").split(",").filter(Boolean)) {
      const [key, raw] = part.split(":");
      overrides[key] = /^[+-]/.test(raw) ? { delta: Number(raw) } : Number(raw);
    }
    const price = (r) => {
      const o = overrides[r.player_key];
      return o === undefined ? r.value : typeof o === "number" ? o : r.value + o.delta;
    };
    return {
      attribution: "Data Driven Football", as_of: "2026-10-28", setting: { scoring, teams, superflex },
      players: ROWS.map(r => ({ ...r, value: price(r), tier: "starter" })), sources_included: ["fantasycalc"], sources_excluded: [],
      ...(context ? { value_context: { basis: context.basis, basis_applied: Boolean(context.basis), overrides,
        overrides_applied: Object.keys(overrides).length, overrides_not_priced: [] } } : {}),
    };
  };
  const rpc = (name, args) => handleRpc({ jsonrpc: "2.0", id: 1, method: "tools/call", params: { name, arguments: args } },
    stubValues, { codec: DDFState, siteOrigin: ORIGIN });
  // A JSON-RPC error or an empty result is the runtime's answer, so it fails the spec, not the harness.
  async function mcp(name, args) {
    const r = await underTest(name, () => (env.mcpCall ? env.mcpCall(rpc, name, args) : rpc(name, args)));
    if (!r || r.error || !r.result || !Array.isArray(r.result.content) || typeof (r.result.content[0] || {}).text !== "string") {
      throw new ContractUnmet(`${name} returned ${JSON.stringify(r && (r.error || r.result || r)).slice(0, 200)}`);
    }
    return r;
  }
  const mcpText = r => r.result.content[0].text;

  // JEG-1254 finding 3: a value-context link counts only when every expected value comes back
  // exactly. The marker must be exactly valuecontext=1, and the shipped reader must decode the
  // link to exactly the expected basis and overrides (nothing missing, extra or changed), so a
  // marker-only link, a dropped ov or a changed weight all fail. How the writer encodes them
  // (ov plain or z:/z2: packed, %3A or :) is its choice; the decoded values are the contract.
  function valueContextMismatches(link, expected) {
    const params = p(queryOf(link));
    const misses = [];
    if (params.get("valuecontext") !== "1") misses.push(`valuecontext=${JSON.stringify(params.get("valuecontext"))}, expected "1"`);
    if (expected.basis && !params.get("basis")) misses.push("basis= missing");
    if (Object.keys(expected.overrides || {}).length && !params.get("ov")) misses.push("ov= missing");
    const reader = loadOverrides();
    const applied = underTest("applyLink(site_url)", () => reader.O.applyLink(params));
    if (applied !== true) misses.push(`reader applyLink returned ${applied}`);
    if (!same(reader.engine.basis, expected.basis)) misses.push(`basis decoded ${JSON.stringify(reader.engine.basis)}, expected ${JSON.stringify(expected.basis)}`);
    if (!same(reader.engine.overrides, expected.overrides)) misses.push(`overrides decoded ${JSON.stringify(reader.engine.overrides)}, expected ${JSON.stringify(expected.overrides)}`);
    return misses;
  }

  return { DDFState, loadOverrides, loadAssist, compareWriter, mcp, mcpText, p, queryOf, sideKeys, valueContextMismatches };
}

// ---------- cases ----------
export function makeCases(H) {
  const { DDFState, loadOverrides, loadAssist, compareWriter, mcp, mcpText, p, queryOf, sideKeys, valueContextMismatches } = H;
  return [
    // DDFState codec (shared by the page's Copy link and the MCP tools)
    { id: "C1", surface: "codec", today: "fail", observed: "executed locally",
      title: "decodeQuery of a Compare link keeps or warns about basis and ov",
      expected: "state carries the value context, or a warning names basis/ov as not carried",
      run() {
        const r = underTest("decodeQuery", () => DDFState.decodeQuery(queryOf(COMPARE_LEGACY_CUSTOM)));
        const kept = JSON.stringify(r.state).match(/fantasycalc|58/);
        const warned = r.warnings.some(w => /basis|override|ov\b/i.test(w));
        return { pass: Boolean(kept || warned), actual: `state keys ${Object.keys(r.state).join(",")}; warnings ${JSON.stringify(r.warnings)}` };
      } },
    { id: "C2", surface: "codec", today: "fail", observed: "executed locally",
      title: "decodeQuery of a finder link keeps the explicit-default marker valuecontext=1",
      expected: "state records that the sender used our methodology on purpose",
      run() {
        const r = underTest("decodeQuery", () => DDFState.decodeQuery(queryOf(FINDER_DEFAULT)));
        const kept = /valuecontext|"basis"|"value"/.test(JSON.stringify(r.state));
        return { pass: kept || r.warnings.length > 0, actual: `normalized: ${JSON.stringify(r.state)}; warnings ${JSON.stringify(r.warnings)}` };
      } },
    { id: "C3", surface: "codec", today: "fail", observed: "executed locally",
      title: "decode then encode a custom-basis link keeps basis and ov",
      expected: "re-encoded query still has basis=, ov= and valuecontext=1",
      run() {
        const q = underTest("decodeQuery+encodeQuery", () => DDFState.encodeQuery(DDFState.decodeQuery(queryOf(FINDER_CUSTOM)).state));
        return { pass: /basis=/.test(q) && /ov=/.test(q) && /valuecontext=1/.test(q), actual: q };
      } },
    { id: "C4", surface: "codec", today: "pass", observed: "executed locally",
      title: "old link without any value context still decodes unchanged (backward compatibility)",
      expected: "give/get/league read, no warnings",
      run() {
        const r = underTest("decodeQuery", () => DDFState.decodeQuery("give=101&get=202&scoring=ppr&roster=QB1.RB2.WR3.TE1.FLEX1.SF0.BN6&bench=0.150"));
        const ok = r.warnings.length === 0 && r.state.work.give[0].key === "101" && r.state.league.scoring === "ppr";
        return { pass: ok, actual: JSON.stringify(r.state) };
      } },

    // Copy link (header overflow menu, ddf-assist.js)
    ...["compare", "finder", "targets"].map((view, i) => ({
      id: `L${i + 1}`, surface: "Copy link", today: "fail", observed: "executed locally",
      title: `Copy link on ${view} carries the sender's custom basis and override`,
      expected: "link has basis=fantasycalc, ov=101:58 and valuecontext=1",
      run() {
        const { O, A } = loadAssist({ view, give: view === "compare" ? sideKeys([ROWS[0]]) : [], get: view === "compare" ? sideKeys([ROWS[1]]) : [],
          mine: view === "finder" ? sideKeys([ROWS[0], ROWS[2]]) : [], theirs: view === "finder" ? sideKeys([ROWS[1], ROWS[3]]) : [] });
        O.applyLink(p("valuecontext=1&basis=fantasycalc&ov=101:58"));   // the sender's context, as a link sets it
        const share = O.shareParams();
        precondition(share.basis === "fantasycalc" && share.ov === "101:58", `the sender holds basis fantasycalc and ov 101:58 (got ${JSON.stringify(share)})`);
        const link = (underTest("linkText()", () => A.linkText()) || {}).text || "";
        return { pass: /basis=fantasycalc/.test(link) && /ov=101(%3A|:)58/.test(link) && /valuecontext=1/.test(link), actual: link.replace(ORIGIN, "") };
      } })),
    { id: "L4", surface: "Copy link", today: "fail", observed: "executed locally",
      title: "Copy link from a sender on our methodology marks the explicit default",
      expected: "link has valuecontext=1 so a reader with a saved custom basis sees ours",
      run() {
        const { O, A } = loadAssist({ view: "finder", mine: sideKeys([ROWS[0]]), theirs: sideKeys([ROWS[1]]) });
        const share = O.shareParams();
        precondition(share.basis === null && share.ov === null, `the sender is on our methodology with no overrides (got ${JSON.stringify(share)})`);
        const link = (underTest("linkText()", () => A.linkText()) || {}).text || "";
        return { pass: /valuecontext=1/.test(link), actual: link.replace(ORIGIN, "") };
      } },

    // Compare a trade, writer to reader. JEG-1254 finding 1: these run the writer as it ships
    // (v2.js tradeHash) and open its link in the shipped reader. The approved fix (D2: A) has
    // the writer add valuecontext=1; the reader is not asked to change how it treats unmarked
    // links, which O1L/O2L pin.
    { id: "O1", surface: "writer+reader", today: "fail", observed: "executed locally",
      title: "Compare link from tradeHash with a sender override, over a reader's own saved overrides",
      expected: "the writer marks the link complete, so the visit uses the sender's basis and only the sender's override (101:58)",
      run() {
        const sender = loadOverrides();
        sender.O.applyLink(p("valuecontext=1&basis=fantasycalc&ov=101:58"));
        const share = sender.O.shareParams();
        precondition(share.basis === "fantasycalc" && share.ov === "101:58", `the sender holds basis fantasycalc and ov 101:58 (got ${JSON.stringify(share)})`);
        const link = compareWriter(sender, { give: sideKeys([ROWS[0]]), receive: sideKeys([ROWS[1]]) });
        precondition(typeof link === "string" && link.startsWith("#compare-trade?give=101&get=202"), `tradeHash() returns the Compare hash for the trade (got ${JSON.stringify(link)})`);
        const reader = loadOverrides({ v: 2, basis: { mode: "default" }, values: { 202: 30 }, names: { 202: "Bravo Wide" } });
        const applied = underTest("applyLink", () => reader.O.applyLink(p(queryOf(link))));
        const ok = same(reader.engine.overrides, { 101: 58 }) && same(reader.engine.basis, { mode: "single", source: "fantasycalc" });
        return { pass: ok, actual: `link ${link}; applyLink ${applied}; reader basis ${JSON.stringify(reader.engine.basis)}, overrides ${JSON.stringify(reader.engine.overrides)}` };
      } },
    { id: "O2", surface: "writer+reader", today: "fail", observed: "executed locally",
      title: "Compare link from tradeHash for a sender on our methodology, reader saved a custom basis",
      expected: "the writer marks the explicit default, so the visit uses our methodology and no overrides",
      run() {
        const sender = loadOverrides();
        const share = sender.O.shareParams();
        precondition(share.basis === null && share.ov === null, `the sender is on our methodology with no overrides (got ${JSON.stringify(share)})`);
        const link = compareWriter(sender, { give: sideKeys([ROWS[0]]), receive: sideKeys([ROWS[1]]) });
        precondition(typeof link === "string" && link.startsWith("#compare-trade?give=101&get=202"), `tradeHash() returns the Compare hash for the trade (got ${JSON.stringify(link)})`);
        const reader = loadOverrides({ v: 2, basis: { mode: "single", source: "espn" }, values: { 202: 30 }, names: {} });
        precondition(same(reader.engine.basis, { mode: "single", source: "espn" }), "the reader boots on its saved ESPN basis");
        const applied = underTest("applyLink", () => reader.O.applyLink(p(queryOf(link))));
        const ok = reader.engine.basis === null && same(reader.engine.overrides, {});
        return { pass: ok, actual: `link ${link}; applyLink ${applied}; reader basis ${JSON.stringify(reader.engine.basis)}, overrides ${JSON.stringify(reader.engine.overrides)}` };
      } },
    // Legacy-reader guards: an unmarked link keeps today's behaviour (applyLink reads only
    // valuecontext=1 as a complete context). Changing that is a policy call nobody has made,
    // so these fail if a fix changes it anyway.
    { id: "O1L", surface: "legacy reader", today: "pass", observed: "executed locally",
      title: "unmarked legacy Compare link with basis and ov still merges into the reader's saved overrides",
      expected: "basis fantasycalc for the visit; overrides 101:58 from the link plus the reader's saved 202:30",
      run() {
        const reader = loadOverrides({ v: 2, basis: { mode: "default" }, values: { 202: 30 }, names: { 202: "Bravo Wide" } });
        const applied = underTest("applyLink", () => reader.O.applyLink(p(queryOf(COMPARE_LEGACY_CUSTOM))));
        const ok = applied === true && same(reader.engine.overrides, { 101: 58, 202: 30 })
          && same(reader.engine.basis, { mode: "single", source: "fantasycalc" });
        return { pass: ok, actual: `applyLink ${applied}; basis ${JSON.stringify(reader.engine.basis)}, overrides ${JSON.stringify(reader.engine.overrides)}` };
      } },
    { id: "O2L", surface: "legacy reader", today: "pass", observed: "executed locally",
      title: "unmarked legacy link with no basis or ov leaves the reader's own saved settings",
      expected: "applyLink returns false; the reader keeps ESPN and its saved 202:30",
      run() {
        const reader = loadOverrides({ v: 2, basis: { mode: "single", source: "espn" }, values: { 202: 30 }, names: {} });
        const applied = underTest("applyLink", () => reader.O.applyLink(p(`give=101&get=202&${LEAGUE}`)));
        const ok = applied === false && same(reader.engine.basis, { mode: "single", source: "espn" })
          && same(reader.engine.overrides, { 202: 30 });
        return { pass: ok, actual: `applyLink ${applied}; basis ${JSON.stringify(reader.engine.basis)}, overrides ${JSON.stringify(reader.engine.overrides)}` };
      } },

    // Overrides reader (overrides.js applyLink), the path every site route uses
    { id: "O3", surface: "reader", today: "pass", observed: "executed locally",
      title: "finder link with valuecontext=1 over a saved custom reader (guards the #1062 repair)",
      expected: "our methodology and no overrides for the visit; saved record untouched",
      run() {
        const saved = { v: 2, basis: { mode: "single", source: "espn" }, values: { 202: 30 }, names: {} };
        const { win, O, engine } = loadOverrides(saved);
        underTest("applyLink", () => O.applyLink(p(queryOf(FINDER_DEFAULT))));
        const still = JSON.parse(win.localStorage.getItem("ddf-v2-value-overrides"));
        return { pass: engine.basis === null && Object.keys(engine.overrides).length === 0 && still.basis.source === "espn",
          actual: `engine basis ${JSON.stringify(engine.basis)}, overrides ${JSON.stringify(engine.overrides)}, saved ${still.basis.source}` };
      } },
    { id: "O4", surface: "reader", today: "pass", observed: "executed locally",
      title: "custom blend and adjustment survive the reader round trip",
      expected: "basis blend espn 60 / razzball 40; override 202 is +5 adjustment; shareParams writes them back",
      run() {
        const { O, engine } = loadOverrides();
        underTest("applyLink", () => O.applyLink(p(queryOf(FINDER_CUSTOM))));
        const s = underTest("shareParams", () => O.shareParams());
        const ok = same(engine.basis, FINDER_CUSTOM_CONTEXT.basis) && same(engine.overrides, FINDER_CUSTOM_CONTEXT.overrides)
          && s.basis === "blend:espn.60_razzball.40" && s.ov === "202:+5";
        return { pass: Boolean(ok), actual: `basis ${JSON.stringify(engine.basis)}; ov ${JSON.stringify(engine.overrides)}; share ${JSON.stringify(s)}` };
      } },
    { id: "O5", surface: "reader", today: "pass", observed: "executed locally",
      title: "repeated use: the same link opened twice applies once",
      expected: "second applyLink returns false and changes nothing",
      run() {
        const { O, engine } = loadOverrides();
        const first = underTest("applyLink", () => O.applyLink(p(queryOf(FINDER_CUSTOM))));
        const before = JSON.stringify(engine.overrides);
        const second = underTest("applyLink", () => O.applyLink(p(queryOf(FINDER_CUSTOM))));
        return { pass: first === true && second === false && JSON.stringify(engine.overrides) === before, actual: `first ${first}, second ${second}` };
      } },
    { id: "O6", surface: "reader", today: "pass", observed: "executed locally",
      title: "undo: restoreContext puts back the context from before an accepted import",
      expected: "reader's saved custom basis and overrides return",
      run() {
        const { O, engine } = loadOverrides({ v: 2, basis: { mode: "single", source: "espn" }, values: { 202: 30 }, names: {} });
        const snap = underTest("snapshotContext", () => O.snapshotContext());
        O.applyLink(p(queryOf(FINDER_CUSTOM)));
        underTest("restoreContext", () => O.restoreContext(snap));
        return { pass: Boolean(engine.basis && engine.basis.source === "espn" && engine.overrides["202"] === 30), actual: `basis ${JSON.stringify(engine.basis)}; ov ${JSON.stringify(engine.overrides)}` };
      } },
    { id: "O7", surface: "reader", today: "fail", observed: "executed locally",
      title: "a malformed basis in a complete link is rejected with a warning",
      expected: "applyLink rejects and leaves a note the page can show (not a silent no-op)",
      run() {
        const { O } = loadOverrides({ v: 2, basis: { mode: "single", source: "espn" }, values: {}, names: {} });
        const applied = underTest("applyLink", () => O.applyLink(p("valuecontext=1&basis=notasource&ov=101:58")));
        const note = O.state.linkNote || O.state.notice;
        return { pass: applied === false && Boolean(note), actual: `applyLink ${applied}; linkNote ${JSON.stringify(O.state.linkNote)}; notice ${JSON.stringify(O.state.notice)}` };
      } },
    { id: "O8", surface: "reader", today: "fail", observed: "executed locally",
      title: "missing value: an override for a player not in this week's values is reported",
      expected: "the link note counts only overrides that apply, or names the one that does not",
      run() {
        const { O } = loadOverrides();
        underTest("applyLink", () => O.applyLink(p("valuecontext=1&ov=101:58,999999:12")));
        const note = O.state.linkNote || "";
        return { pass: /1 player override\b/.test(note) || /not (in|found)|left out/i.test(note), actual: note };
      } },

    // MCP read_state / make_state and the return-to-site link
    { id: "M1", surface: "read_state", today: "pass", observed: "executed locally (stub get-values)",
      title: "read_state on a custom-basis link prices under the link's basis and override",
      expected: "Alpha Back priced with the override (58, not 40) and the reply names the basis (D1: B)",
      async run() {
        const t = mcpText(await mcp("read_state", { state: COMPARE_LEGACY_CUSTOM }));
        return { pass: /Alpha Back \(RB\): 58\b/.test(t) && /fantasycalc|basis/i.test(t), actual: t.split("\n").slice(0, 6).join(" | ") };
      } },
    { id: "M2", surface: "return-to-site", today: "pass", observed: "executed locally (stub get-values)",
      title: "read_state's site_url keeps every value-context value exactly",
      expected: "valuecontext=1, and the reader decodes exactly blend espn 60 / razzball 40 and 202 +5 adjustment",
      async run() {
        const r = await mcp("read_state", { state: FINDER_CUSTOM });
        const url = (r.result.structuredContent || {}).site_url;
        if (typeof url !== "string") throw new ContractUnmet(`read_state returned no site_url (${JSON.stringify(r.result.structuredContent)})`);
        const misses = valueContextMismatches(url, FINDER_CUSTOM_CONTEXT);
        return { pass: misses.length === 0, actual: `${url.replace(ORIGIN, "")}${misses.length ? ` | ${misses.join("; ")}` : ""}` };
      } },
    { id: "M3", surface: "make_state", today: "pass", observed: "executed locally (stub get-values)",
      title: "make_state from a pasted custom-basis state keeps the value context in the block and link",
      expected: "block and link carry basis/ov, or the reply says they were dropped",
      async run() {
        const r = await mcp("make_state", { state: FINDER_CUSTOM, target: "Alpha Back" });
        const t = mcpText(r);
        return { pass: /basis|valuecontext|override/i.test(t), actual: ((r.result.structuredContent || {}).site_url || "").replace(ORIGIN, "") };
      } },
    { id: "M4", surface: "read_state", today: "pass", observed: "executed locally (stub get-values)",
      title: "read_state applies the link's league settings (guard)",
      expected: "header names Half PPR and 10 teams",
      async run() {
        const r = await mcp("read_state", { state: FINDER_DEFAULT });
        const s = (r.result.structuredContent || {}).setting || {};
        return { pass: s.scoring === "half_ppr" && s.teams === 10, actual: JSON.stringify(s) };
      } },
  ];
}

// ---------- run ----------
export const STATUS = {
  spec: "FAILS (spec, as recorded)", guard: "passes (guard)", flipped: "NOW PASSES: flip today to pass",
  regressed: "REGRESSED: guard fails", harness: "HARNESS ERROR: fix the harness",
};
export async function runCases(cases) {
  const results = [];
  for (const c of cases) {
    let out = null, harnessError = null;
    try {
      out = await c.run();
      if (!out || typeof out.pass !== "boolean" || typeof out.actual !== "string") {
        throw new HarnessError(`case returned ${JSON.stringify(out)}; expected {pass: boolean, actual: string}`);
      }
    } catch (error) {
      if (error instanceof ContractUnmet) out = { pass: false, actual: error.message };
      else harnessError = `${(error && error.constructor && error.constructor.name) || "Error"}: ${error && error.message}`;
    }
    const now = harnessError ? "error" : out.pass ? "pass" : "fail";
    const status = harnessError ? STATUS.harness
      : now === c.today ? (now === "fail" ? STATUS.spec : STATUS.guard)
      : now === "pass" ? STATUS.flipped : STATUS.regressed;
    results.push({ id: c.id, surface: c.surface, title: c.title, observed: c.observed, expected: c.expected,
      actual: harnessError || out.actual, today: c.today, now, status });
  }
  return results;
}
export function exitCode(results, { strict = false } = {}) {
  if (results.some(r => r.now === "error")) return 2;
  if (strict) return results.some(r => r.now === "fail") ? 1 : 0;
  return results.some(r => r.now !== r.today) ? 1 : 0;
}
export function summary(results) {
  const n = now => results.filter(r => r.now === now).length;
  return `${results.length} cases: ${n("fail")} failing specs, ${n("pass")} passing, ${n("error")} harness errors, `
    + `${results.filter(r => r.now !== r.today && r.now !== "error").length} differ from the record`;
}

async function main() {
  const args = new Set(process.argv.slice(2));
  let results;
  try {
    results = await runCases(makeCases(makeHarness(await shippedEnv())));
  } catch (error) {
    console.error(`${STATUS.harness}: ${error.message}`);
    process.exit(2);
  }
  if (args.has("--json")) console.log(JSON.stringify(results, null, 2));
  else {
    for (const r of results) console.log(`${r.id.padEnd(4)} ${r.status.padEnd(30)} ${r.surface.padEnd(14)} ${r.title}\n       actual: ${r.actual}`);
    console.log(`\n${summary(results)}`);
  }
  process.exit(exitCode(results, { strict: args.has("--strict") }));
}
if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) await main();
