// JEG-1254: negative mutations for the JEG-1224 harness. Each mutation edits an in-memory
// copy of a shipped module (or the harness input) and checks the harness answers the way
// it should, so every guard is shown to reject the broken input it exists for.
//
//   node --experimental-strip-types --no-warnings tests/jeg-1224/harness_mutations.mjs [--json]
//
// Exit 0 when every mutation gets its expected answer, 1 when one does not, 2 when a
// mutation cannot be built (its anchor text is gone from the shipped source).
// Nothing on disk is changed: shipped files are read once and edited as strings.
import {
  shippedEnv, makeHarness, makeCases, runCases, exitCode, HarnessError, precondition, FIXTURES,
} from "./shared_link_regressions.mjs";

const shipped = await shippedEnv();
// Replace one exact anchor in a shipped source; a missing anchor means the mutation is stale.
function edit(src, from, to, label) {
  if (src.split(from).length !== 2) throw new HarnessError(`mutation ${label}: anchor not found exactly once: ${from}`);
  return src.replace(from, to);
}
const cases = env => makeCases(makeHarness({ ...shipped, ...env }));
const pick = (list, ids) => ids.map(id => { const c = list.find(x => x.id === id); if (!c) throw new HarnessError(`no case ${id}`); return c; });
const byId = results => Object.fromEntries(results.map(r => [r.id, r]));
// A read_state answer whose site_url is replaced, as a broken or fixed MCP writer would return it.
const siteUrl = url => async (rpc, name, args) => {
  const r = await rpc(name, args);
  if (name === "read_state") r.result.structuredContent = { ...r.result.structuredContent, site_url: url };
  return r;
};
const { ORIGIN, LEAGUE } = FIXTURES;
const FINDER = `${ORIGIN}/#find-trade?mine=101,303&theirs=202,404&${LEAGUE}&v=1`;

// Each mutation: what it breaks, the cases to run, and the answer each case must give
// ("pass", "fail" for an unmet contract, "error" for a harness error) plus the exit code.
// JEG-1343: M1-M3 are recorded as passing since the MCP tools honor the link's value context, so a
// mutation that breaks them now differs from the record (exit 1) and the exact positive control keeps it (exit 0).
const MUTATIONS = [
  // ----- finding 1: O1/O2 exercise the writer; legacy guards keep unmarked behaviour -----
  { id: "W1", finding: 1, label: "approved writer fix: tradeHash adds valuecontext=1 (D2: A); reader unchanged",
    env: () => ({ v2Src: edit(shipped.v2Src, "parts.push(...leagueLinkParts());", "parts.push(...leagueLinkParts()); parts.push(\"valuecontext=1\");", "W1") }),
    ids: ["O1", "O2", "O1L", "O2L"], expect: { O1: "pass", O2: "pass", O1L: "pass", O2L: "pass" } },
  { id: "W2", finding: 1, label: "unapproved legacy policy change: reader treats every link as complete",
    env: () => ({ linkSrc: edit(shipped.linkSrc, 'const complete = get("valuecontext") === "1";', "const complete = true;", "W2") }),
    ids: ["O1L", "O2L"], expect: { O1L: "fail", O2L: "fail" } },
  { id: "W3", finding: 1, label: "writer marks the link but drops the sender's override",
    env: () => ({ v2Src: edit(edit(shipped.v2Src, "parts.push(...leagueLinkParts());", "parts.push(...leagueLinkParts()); parts.push(\"valuecontext=1\");", "W3"),
      "else parts.push(`ov=${ov.ov}`);", "else {}", "W3") }),
    ids: ["O1", "O2"], expect: { O1: "fail", O2: "pass" } },
  { id: "W4", finding: 1, label: "writer renamed or gone: O1/O2 are a harness error, never a recorded spec failure",
    env: () => ({ v2Src: edit(shipped.v2Src, "function tradeHash()", "function tradeHashRenamed()", "W4") }),
    ids: ["O1", "O2"], expect: { O1: "error", O2: "error" }, exit: 2 },

  // ----- finding 2: setup and precondition failures fail the default run -----
  { id: "E1", finding: 2, label: "precondition breaks: sender's Overrides module loses the single basis in shareParams",
    env: () => ({ linkSrc: edit(shipped.linkSrc, "if (rec.mode === \"single\") return rec.source ? String(rec.source) : null;", "if (rec.mode === \"single\") return null;", "E1") }),
    ids: ["L1", "O1"], expect: { L1: "error", O1: "error" }, exit: 2 },
  { id: "E2", finding: 2, label: "module fails to load: overrides.js throws on evaluation",
    env: () => ({ overridesSrc: `throw new Error("boom");\n${shipped.overridesSrc}` }),
    ids: ["O3", "L4"], expect: { O3: "error", L4: "error" }, exit: 2 },
  { id: "E3", finding: 2, label: "fixture broken: Copy link module missing (attach is not a function)",
    env: () => ({ assistSrc: "/* emptied */" }),
    ids: ["L2"], expect: { L2: "error" }, exit: 2 },
  { id: "E4", finding: 2, label: "malformed case result and a bare setup TypeError",
    custom: () => [
      { id: "X1", today: "fail", surface: "synthetic", title: "returns no result", run() { return {}; } },
      { id: "X2", today: "fail", surface: "synthetic", title: "setup TypeError", run() { const fixture = null; return fixture.rows; } },
      { id: "X3", today: "fail", surface: "synthetic", title: "precondition", run() { precondition(false, "synthetic"); } },
    ], expect: { X1: "error", X2: "error", X3: "error" }, exit: 2 },
  { id: "E5", finding: 2, label: "control: the call under test throws or errors, which stays an unmet contract",
    env: () => ({ mcpCall: async (rpc, name, args) => { if (name === "read_state") throw new Error("edge function crashed"); return rpc(name, args); } }),
    ids: ["M1", "M2"], expect: { M1: "fail", M2: "fail" }, exit: 1 },
  { id: "E6", finding: 2, label: "control: a JSON-RPC error answer is an unmet contract, not a harness error",
    env: () => ({ mcpCall: async () => ({ jsonrpc: "2.0", id: 1, error: { code: -32000, message: "bad state" } }) }),
    ids: ["M2"], expect: { M2: "fail" }, exit: 1 },

  // ----- finding 3: M2 checks every value exactly -----
  { id: "V1", finding: 3, label: "marker-only site_url (valuecontext=1, basis and ov lost)",
    env: () => ({ mcpCall: siteUrl(`${FINDER}&valuecontext=1`) }), ids: ["M2"], expect: { M2: "fail" }, exit: 1 },
  { id: "V2", finding: 3, label: "basis only: ov dropped",
    env: () => ({ mcpCall: siteUrl(`${FINDER}&valuecontext=1&basis=blend%3Aespn.60_razzball.40`) }), ids: ["M2"], expect: { M2: "fail" }, exit: 1 },
  { id: "V3", finding: 3, label: "ov only: basis dropped",
    env: () => ({ mcpCall: siteUrl(`${FINDER}&valuecontext=1&ov=202%3A%2B5`) }), ids: ["M2"], expect: { M2: "fail" }, exit: 1 },
  { id: "V4", finding: 3, label: "basis and ov without the marker",
    env: () => ({ mcpCall: siteUrl(`${FINDER}&basis=blend%3Aespn.60_razzball.40&ov=202%3A%2B5`) }), ids: ["M2"], expect: { M2: "fail" }, exit: 1 },
  { id: "V5", finding: 3, label: "changed value: adjustment +4 instead of +5",
    env: () => ({ mcpCall: siteUrl(`${FINDER}&valuecontext=1&basis=blend%3Aespn.60_razzball.40&ov=202%3A%2B4`) }), ids: ["M2"], expect: { M2: "fail" }, exit: 1 },
  { id: "V6", finding: 3, label: "changed value: absolute 5 instead of a +5 adjustment",
    env: () => ({ mcpCall: siteUrl(`${FINDER}&valuecontext=1&basis=blend%3Aespn.60_razzball.40&ov=202%3A5`) }), ids: ["M2"], expect: { M2: "fail" }, exit: 1 },
  { id: "V7", finding: 3, label: "changed weights: espn 50 / razzball 50",
    env: () => ({ mcpCall: siteUrl(`${FINDER}&valuecontext=1&basis=blend%3Aespn.50_razzball.50&ov=202%3A%2B5`) }), ids: ["M2"], expect: { M2: "fail" }, exit: 1 },
  { id: "V8", finding: 3, label: "extra override the sender did not set",
    env: () => ({ mcpCall: siteUrl(`${FINDER}&valuecontext=1&basis=blend%3Aespn.60_razzball.40&ov=202%3A%2B5,101%3A58`) }), ids: ["M2"], expect: { M2: "fail" }, exit: 1 },
  { id: "V9", finding: 3, label: "wrong marker value: valuecontext=true",
    env: () => ({ mcpCall: siteUrl(`${FINDER}&valuecontext=true&basis=blend%3Aespn.60_razzball.40&ov=202%3A%2B5`) }), ids: ["M2"], expect: { M2: "fail" }, exit: 1 },
  { id: "V10", finding: 3, label: "positive control: a complete exact site_url (as a fixed MCP writer returns) passes",
    env: () => ({ mcpCall: siteUrl(`${FINDER}&valuecontext=1&basis=blend%3Aespn.60_razzball.40&ov=202%3A%2B5`) }), ids: ["M2"], expect: { M2: "pass" }, exit: 0 },
];

const report = [];
let broken = false;
for (const m of MUTATIONS) {
  let results, problem = null;
  try {
    const list = m.custom ? m.custom() : pick(cases(m.env ? m.env() : {}), m.ids);
    results = await runCases(list);
  } catch (error) {
    broken = true;
    report.push({ id: m.id, finding: m.finding, label: m.label, ok: false, detail: `could not build: ${error.message}` });
    continue;
  }
  const got = byId(results);
  const wrong = Object.entries(m.expect).filter(([id, want]) => !got[id] || got[id].now !== want)
    .map(([id, want]) => `${id} expected ${want}, got ${got[id] ? got[id].now : "missing"} (${got[id] ? got[id].actual : ""})`);
  // The default recording run's exit code for this set: 1 when a case differs from its record,
  // 0 when every case keeps it, 2 on a harness error.
  const wantExit = m.exit ?? 1;
  const code = exitCode(results);
  if (code !== wantExit) problem = `default-run exit ${code}, expected ${wantExit}`;
  // A harness error must fail --strict too, not read as "a spec is still failing".
  else if (wantExit === 2 && exitCode(results, { strict: true }) !== 2) problem = `--strict exit ${exitCode(results, { strict: true })}, expected 2`;
  const ok = !wrong.length && !problem;
  report.push({ id: m.id, finding: m.finding, label: m.label, ok, exit: code,
    detail: ok ? results.map(r => `${r.id} ${r.now} (${r.status})`).join("; ") : [...wrong, problem].filter(Boolean).join("; "),
    results: results.map(r => ({ id: r.id, now: r.now, status: r.status, actual: r.actual })) });
}

if (process.argv.includes("--json")) console.log(JSON.stringify(report, null, 2));
else {
  for (const r of report) console.log(`${r.id.padEnd(4)} ${r.ok ? "ok      " : "WRONG   "} finding ${r.finding}  ${r.label}\n       ${r.detail}`);
  const bad = report.filter(r => !r.ok).length;
  console.log(`\n${report.length} mutations: ${report.length - bad} answered as expected, ${bad} did not`);
}
process.exit(broken ? 2 : report.every(r => r.ok) ? 0 : 1);
