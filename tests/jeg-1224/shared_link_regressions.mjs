// JEG-1224: failing-before regression specs for value basis and override loss across
// Copy link, read_state and return-to-site. Isolated harness: it loads the shipped
// modules read-only (no production code is patched) and is not wired into make.
//
//   node --experimental-strip-types --no-warnings tests/jeg-1224/shared_link_regressions.mjs
//   node ... shared_link_regressions.mjs --strict    exit 1 while any spec still fails
//   node ... shared_link_regressions.mjs --json      machine-readable results
//
// Each case declares `today`: "fail" (a regression spec that fails on main until fixed)
// or "pass" (a guard on behaviour that is already right). Without --strict the run
// exits 0 only when every case matches its declaration, so a fix that lands shows up
// as "now passes: flip to pass" instead of silently changing the record.
// Spec and contract: docs/qa/jeg-1224/README.md.
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { readFileSync } from "node:fs";
import vm from "node:vm";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const require = createRequire(import.meta.url);
const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
const read = rel => readFileSync(join(ROOT, rel), "utf8");
const DDFState = require(join(ROOT, "app/v2/ddf-state.js"));
const { handleRpc } = await import(join(ROOT, "supabase/functions/mcp/rpc.ts"));

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
// The Overrides module (basis + player overrides), booted with a reader's saved record.
function loadOverrides(saved) {
  const win = pageContext({ local: saved ? { "ddf-v2-value-overrides": JSON.stringify(saved) } : {} });
  vm.runInContext(read("app/v2/overrides.js"), win, { filename: "app/v2/overrides.js" });
  const engine = fakeEngine();
  win.DDFOverrides.boot(engine);
  return { win, O: win.DDFOverrides, engine };
}
// The Copy link module, with the Overrides module beside it holding the sender's context.
function loadAssist({ view, give = [], get = [], mine = [], theirs = [], saved }) {
  const { win, O } = loadOverrides(saved);
  vm.runInContext(read("app/v2/ddf-state.js"), win, { filename: "app/v2/ddf-state.js" });
  win.TradeValueFinder = { normName: n => String(n || "").toLowerCase().trim(), ui: { getMine: () => mine, getTheirs: () => theirs, setSides: () => ({ bothSides: [] }) } };
  vm.runInContext(read("app/v2/ddf-assist.js"), win, { filename: "app/v2/ddf-assist.js" });
  win.DDFAssist.attach({
    engine: { getAllRows: () => ROWS }, view: () => view, getTrade: () => ({ give, get }),
    getTarget: () => "", sources: () => ["fantasycalc"], leagueQuery: () => LEAGUE, leagueText: () => "10 teams, Half PPR",
  });
  return { win, O, A: win.DDFAssist };
}
const p = query => new URLSearchParams(query);
const sideKeys = list => list.map(r => ({ key: String(r.player_key), name: r.name }));

// ---------- MCP ----------
const stubValues = async (scoring, teams, superflex) => ({
  attribution: "Data Driven Football", as_of: "2026-10-28", setting: { scoring, teams, superflex },
  players: ROWS.map(r => ({ ...r, tier: "starter" })), sources_included: ["fantasycalc"], sources_excluded: [],
});
const mcp = (name, args) => handleRpc({ jsonrpc: "2.0", id: 1, method: "tools/call", params: { name, arguments: args } },
  stubValues, { codec: DDFState, siteOrigin: ORIGIN });
const mcpText = r => r.result.content[0].text;

// A Compare link as tradeHash() writes it for a sender on a custom basis with one override.
const COMPARE_CUSTOM = `${ORIGIN}/#compare-trade?give=101&get=202&${LEAGUE}&basis=fantasycalc&ov=101:58`;
// A Find a trade link as finder shareLink() writes it for a sender on our methodology (explicit default).
const FINDER_DEFAULT = `${ORIGIN}/#find-trade?mine=101,303&theirs=202,404&${LEAGUE}&v=1&valuecontext=1`;
// The same with a custom blend and an adjustment.
const FINDER_CUSTOM = `${ORIGIN}/#find-trade?mine=101,303&theirs=202,404&${LEAGUE}&v=1&valuecontext=1&basis=blend%3Aespn.60_razzball.40&ov=202%3A%2B5`;
const valueContextIn = q => /(^|[?&])(valuecontext|basis|ov)=/.test(q);

// ---------- cases ----------
const CASES = [
  // DDFState codec (shared by the page's Copy link and the MCP tools)
  { id: "C1", surface: "codec", today: "fail", observed: "executed locally",
    title: "decodeQuery of a Compare link keeps or warns about basis and ov",
    expected: "state carries the value context, or a warning names basis/ov as not carried",
    run() {
      const r = DDFState.decodeQuery(COMPARE_CUSTOM.split("?")[1]);
      const kept = JSON.stringify(r.state).match(/fantasycalc|58/);
      const warned = r.warnings.some(w => /basis|override|ov\b/i.test(w));
      return { pass: Boolean(kept || warned), actual: `state keys ${Object.keys(r.state).join(",")}; warnings ${JSON.stringify(r.warnings)}` };
    } },
  { id: "C2", surface: "codec", today: "fail", observed: "executed locally",
    title: "decodeQuery of a finder link keeps the explicit-default marker valuecontext=1",
    expected: "state records that the sender used our methodology on purpose",
    run() {
      const r = DDFState.decodeQuery(FINDER_DEFAULT.split("?")[1]);
      const kept = /valuecontext|"basis"|"value"/.test(JSON.stringify(r.state));
      return { pass: kept || r.warnings.length > 0, actual: `normalized: ${JSON.stringify(r.state)}; warnings ${JSON.stringify(r.warnings)}` };
    } },
  { id: "C3", surface: "codec", today: "fail", observed: "executed locally",
    title: "decode then encode a custom-basis link keeps basis and ov",
    expected: "re-encoded query still has basis=, ov= and valuecontext=1",
    run() {
      const q = DDFState.encodeQuery(DDFState.decodeQuery(FINDER_CUSTOM.split("?")[1]).state);
      return { pass: /basis=/.test(q) && /ov=/.test(q) && /valuecontext=1/.test(q), actual: q };
    } },
  { id: "C4", surface: "codec", today: "pass", observed: "executed locally",
    title: "old link without any value context still decodes unchanged (backward compatibility)",
    expected: "give/get/league read, no warnings",
    run() {
      const r = DDFState.decodeQuery("give=101&get=202&scoring=ppr&roster=QB1.RB2.WR3.TE1.FLEX1.SF0.BN6&bench=0.150");
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
      assert.equal(share.basis, "fantasycalc", "precondition: the Overrides module holds the custom basis");
      const link = (A.linkText() || {}).text || "";
      return { pass: /basis=fantasycalc/.test(link) && /ov=101(%3A|:)58/.test(link) && /valuecontext=1/.test(link), actual: link.replace(ORIGIN, "") };
    } })),
  { id: "L4", surface: "Copy link", today: "fail", observed: "executed locally",
    title: "Copy link from a sender on our methodology marks the explicit default",
    expected: "link has valuecontext=1 so a reader with a saved custom basis sees ours",
    run() {
      const { A } = loadAssist({ view: "finder", mine: sideKeys([ROWS[0]]), theirs: sideKeys([ROWS[1]]) });
      const link = (A.linkText() || {}).text || "";
      return { pass: /valuecontext=1/.test(link), actual: link.replace(ORIGIN, "") };
    } },

  // Overrides reader (overrides.js applyLink), the path every site route uses
  { id: "O1", surface: "reader", today: "fail", observed: "executed locally",
    title: "Compare link with sender overrides over a reader's own saved overrides",
    expected: "the visit uses the sender's overrides only (101), as finder/league links do",
    run() {
      const { O, engine } = loadOverrides({ v: 2, basis: { mode: "default" }, values: { 202: 30 }, names: { 202: "Bravo Wide" } });
      O.applyLink(p(COMPARE_CUSTOM.split("?")[1]));
      const keys = Object.keys(engine.overrides).sort();
      return { pass: keys.join(",") === "101", actual: `engine overrides ${JSON.stringify(engine.overrides)}` };
    } },
  { id: "O2", surface: "reader", today: "fail", observed: "executed locally",
    title: "Compare link from a sender on our methodology, reader saved a custom basis",
    expected: "the visit uses our methodology (sender's view)",
    run() {
      const { O, engine } = loadOverrides({ v: 2, basis: { mode: "single", source: "espn" }, values: {}, names: {} });
      // tradeHash() writes no basis= for our methodology and never writes valuecontext=1.
      const applied = O.applyLink(p(`give=101&get=202&${LEAGUE}`));
      return { pass: engine.basis === null, actual: `applyLink returned ${applied}; engine basis ${JSON.stringify(engine.basis)}` };
    } },
  { id: "O3", surface: "reader", today: "pass", observed: "executed locally",
    title: "finder link with valuecontext=1 over a saved custom reader (guards the #1062 repair)",
    expected: "our methodology and no overrides for the visit; saved record untouched",
    run() {
      const saved = { v: 2, basis: { mode: "single", source: "espn" }, values: { 202: 30 }, names: {} };
      const { win, O, engine } = loadOverrides(saved);
      O.applyLink(p(FINDER_DEFAULT.split("?")[1]));
      const still = JSON.parse(win.localStorage.getItem("ddf-v2-value-overrides"));
      return { pass: engine.basis === null && Object.keys(engine.overrides).length === 0 && still.basis.source === "espn",
        actual: `engine basis ${JSON.stringify(engine.basis)}, overrides ${JSON.stringify(engine.overrides)}, saved ${still.basis.source}` };
    } },
  { id: "O4", surface: "reader", today: "pass", observed: "executed locally",
    title: "custom blend and adjustment survive the reader round trip",
    expected: "basis blend espn 60 / razzball 40; override 202 is +5 adjustment; shareParams writes them back",
    run() {
      const { O, engine } = loadOverrides();
      O.applyLink(p(FINDER_CUSTOM.split("?")[1]));
      const s = O.shareParams();
      const ok = engine.basis && engine.basis.mode === "blend" && engine.overrides["202"] && engine.overrides["202"].delta === 5
        && s.basis === "blend:espn.60_razzball.40" && s.ov === "202:+5";
      return { pass: Boolean(ok), actual: `basis ${JSON.stringify(engine.basis)}; ov ${JSON.stringify(engine.overrides)}; share ${JSON.stringify(s)}` };
    } },
  { id: "O5", surface: "reader", today: "pass", observed: "executed locally",
    title: "repeated use: the same link opened twice applies once",
    expected: "second applyLink returns false and changes nothing",
    run() {
      const { O, engine } = loadOverrides();
      const first = O.applyLink(p(FINDER_CUSTOM.split("?")[1]));
      const before = JSON.stringify(engine.overrides);
      const second = O.applyLink(p(FINDER_CUSTOM.split("?")[1]));
      return { pass: first === true && second === false && JSON.stringify(engine.overrides) === before, actual: `first ${first}, second ${second}` };
    } },
  { id: "O6", surface: "reader", today: "pass", observed: "executed locally",
    title: "undo: restoreContext puts back the context from before an accepted import",
    expected: "reader's saved custom basis and overrides return",
    run() {
      const { O, engine } = loadOverrides({ v: 2, basis: { mode: "single", source: "espn" }, values: { 202: 30 }, names: {} });
      const snap = O.snapshotContext();
      O.applyLink(p(FINDER_CUSTOM.split("?")[1]));
      O.restoreContext(snap);
      return { pass: engine.basis && engine.basis.source === "espn" && engine.overrides["202"] === 30, actual: `basis ${JSON.stringify(engine.basis)}; ov ${JSON.stringify(engine.overrides)}` };
    } },
  { id: "O7", surface: "reader", today: "fail", observed: "executed locally",
    title: "a malformed basis in a complete link is rejected with a warning",
    expected: "applyLink rejects and leaves a note the page can show (not a silent no-op)",
    run() {
      const { O } = loadOverrides({ v: 2, basis: { mode: "single", source: "espn" }, values: {}, names: {} });
      const applied = O.applyLink(p("valuecontext=1&basis=notasource&ov=101:58"));
      const note = O.state.linkNote || O.state.notice;
      return { pass: applied === false && Boolean(note), actual: `applyLink ${applied}; linkNote ${JSON.stringify(O.state.linkNote)}; notice ${JSON.stringify(O.state.notice)}` };
    } },
  { id: "O8", surface: "reader", today: "fail", observed: "executed locally",
    title: "missing value: an override for a player not in this week's values is reported",
    expected: "the link note counts only overrides that apply, or names the one that does not",
    run() {
      const { O } = loadOverrides();
      O.applyLink(p("valuecontext=1&ov=101:58,999999:12"));
      const note = O.state.linkNote || "";
      return { pass: /1 player override\b/.test(note) || /not (in|found)|left out/i.test(note), actual: note };
    } },

  // MCP read_state / make_state and the return-to-site link
  { id: "M1", surface: "read_state", today: "fail", observed: "executed locally (stub get-values)",
    title: "read_state on a custom-basis link says the basis and override were not applied",
    expected: "a note that the pasted basis/overrides are not used, or values priced under them",
    async run() {
      const r = await mcp("read_state", { state: COMPARE_CUSTOM });
      const t = mcpText(r);
      return { pass: /basis|override/i.test(t), actual: t.split("\n").slice(0, 6).join(" | ") };
    } },
  { id: "M2", surface: "return-to-site", today: "fail", observed: "executed locally (stub get-values)",
    title: "read_state's site_url keeps basis, ov and valuecontext",
    expected: "the link back to the site opens the sender's value context",
    async run() {
      const r = await mcp("read_state", { state: FINDER_CUSTOM });
      const url = r.result.structuredContent.site_url;
      return { pass: valueContextIn(url.split("?")[1] || ""), actual: url.replace(ORIGIN, "") };
    } },
  { id: "M3", surface: "make_state", today: "fail", observed: "executed locally (stub get-values)",
    title: "make_state from a pasted custom-basis state keeps the value context in the block and link",
    expected: "block and link carry basis/ov, or the reply says they were dropped",
    async run() {
      const r = await mcp("make_state", { state: FINDER_CUSTOM, target: "Alpha Back" });
      const t = mcpText(r);
      return { pass: /basis|valuecontext|override/i.test(t), actual: (r.result.structuredContent.site_url || "").replace(ORIGIN, "") };
    } },
  { id: "M4", surface: "read_state", today: "pass", observed: "executed locally (stub get-values)",
    title: "read_state applies the link's league settings (guard)",
    expected: "header names Half PPR and 10 teams",
    async run() {
      const r = await mcp("read_state", { state: FINDER_DEFAULT });
      const s = r.result.structuredContent.setting;
      return { pass: s.scoring === "half_ppr" && s.teams === 10, actual: JSON.stringify(s) };
    } },
];

// ---------- run ----------
const args = new Set(process.argv.slice(2));
const results = [];
for (const c of CASES) {
  let out;
  try { out = await c.run(); } catch (error) { out = { pass: false, actual: `threw: ${error.message}` }; }
  const now = out.pass ? "pass" : "fail";
  results.push({ id: c.id, surface: c.surface, title: c.title, observed: c.observed, expected: c.expected, actual: out.actual, today: c.today, now,
    status: now === c.today ? (now === "fail" ? "FAILS (spec, as recorded)" : "passes (guard)") : now === "pass" ? "NOW PASSES: flip today to pass" : "REGRESSED: guard fails" });
}
if (args.has("--json")) console.log(JSON.stringify(results, null, 2));
else for (const r of results) console.log(`${r.id.padEnd(3)} ${r.status.padEnd(28)} ${r.surface.padEnd(14)} ${r.title}\n      actual: ${r.actual}`);
const mismatched = results.filter(r => r.now !== r.today);
const failing = results.filter(r => r.now === "fail");
if (!args.has("--json")) console.log(`\n${results.length} cases: ${failing.length} failing specs, ${results.length - failing.length} passing, ${mismatched.length} differ from the record`);
process.exit(args.has("--strict") ? (failing.length ? 1 : 0) : (mismatched.length ? 1 : 0));
