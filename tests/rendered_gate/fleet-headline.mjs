// JEG-319: dashboard headline fleet tally must include vorp_view_status and
// adj_view_status from the per-view artifacts (vorp-view.json / adj-view.json).
//
// Why this test exists: prior to JEG-319 the dashboard's #okCount / #totalCount
// tally summed per-source checkpoints + methodology_consistency + scale_agreement
// + vorp_translation + adj_curve_pipeline, but the VORP / Adj view statuses were
// counted only on their own cards (vorpCard / adjCard). A bad view therefore
// showed "0 broken" in the headline while a downstream view section rendered a
// fail badge. This gate pins the new contract.
//
// Usage: node fleet-headline.mjs [--out report.json]
//
// Discrimination: every scenario also runs against a BROKEN tally block that
// does NOT include vorp_view_status / adj_view_status, and asserts that
// regression guard catches the bug it names. A guard that passes both the
// fixed AND the broken implementation exits 1 ("self-test").
//
// (a) both views ok     -> total +2, ok fraction still 100%
// (b) one view bad      -> bad count +1
// (c) vorp-view.json={view:'vorp',status:'bad',sources:{}}
//                      -> bad count = 1

import fs from "node:fs";
import path from "node:path";
import url from "node:url";

const HERE = path.dirname(url.fileURLToPath(import.meta.url));
const DASHBOARD = path.resolve(HERE, "..", "..", "modules", "dashboard.html");

// The tally block runs inside a larger async IIFE in dashboard.html. We pull
// just the lines we want to exercise (the same window the line-boundary edit
// touched) and evaluate them in a sandbox with a mocked `fetch` and a mocked
// `data` object. This means the test exercises the EXACT production code path,
// not a re-implementation -- a drift in the tally is caught immediately.
function extractTallyBlock(html) {
  const startRe = /\/\/ Count all checkpoints\b/;
  // Stop at the `const total = ...` line so we capture the full tally (incl.
  // JEG-319 view reads) but NOT the DOM write that follows it (Node has no
  // `document`). The DOM writes live on the next two lines in dashboard.html.
  const endRe = /const total\s*=\s*counts\.ok\s*\+\s*counts\.warn\s*\+\s*counts\.bad\s*\+\s*counts\.unk\s*;/;
  const start = html.search(startRe);
  const endMatch = endRe.exec(html);
  if (start < 0 || !endMatch) throw new Error("tally block markers not found in dashboard.html");
  return html.slice(start, endMatch.index + endMatch[0].length);
}

function makeFetch(artifacts) {
  // artifacts: { "vorp-view.json": "...json text...", "adj-view.json": "...", ... }
  return async (file) => {
    if (!(file in artifacts)) {
      return { ok: false, status: 404, text: async () => "" };
    }
    const body = artifacts[file];
    return {
      ok: true,
      status: 200,
      text: async () => body,
    };
  };
}

// SOURCE_ORDER must mirror the production array exactly -- the tally iterates it
// for per-source cells. Pulled from dashboard.html, not hardcoded.
function extractSourceOrder(html) {
  const m = html.match(/const SOURCE_ORDER\s*=\s*\[([^\]]+)\]/);
  if (!m) throw new Error("SOURCE_ORDER not found");
  return m[1].split(",").map(s => s.trim().replace(/^["']|["']$/g, ""));
}

// Run the extracted tally block against (data, artifacts) and return the
// resulting counts + total. The block is wrapped in an async function so the
// `await Promise.all([...])` in production resolves identically here.
async function runTally(html, data, artifacts) {
  const block = extractTallyBlock(html);
  const SOURCE_ORDER = extractSourceOrder(html);
  // Wrap the block in an async IIFE. It uses `tally`, `counts`, `fetch`,
  // `JSON.parse`, and `data` -- all we provide.
  // eslint-disable-next-line no-new-func
  const fn = new Function(
    "data", "SOURCE_ORDER", "fetch",
    `return (async () => { ${block} return { counts, total }; })();`,
  );
  return await fn(data, SOURCE_ORDER, makeFetch(artifacts));
}

// Build a clean pipeline-checkpoints fixture: every section ok, every per-source
// checkpoint ok. The only knob we turn per scenario is the view artifacts and
// any specific section we deliberately break.
function cleanData() {
  const SOURCE_ORDER = ["espn", "cbs", "cbsros", "razzball", "fantasycalc", "fantasypros", "usatoday"];
  const sources = {};
  for (const src of SOURCE_ORDER) {
    sources[src] = { checkpoints: { a: { status: "ok" }, b: { status: "ok" } } };
  }
  return {
    sources,
    methodology_consistency: { status: "ok" },
    scale_agreement: { status: "ok" },
    vorp_translation: { status: "ok" },
    adj_curve_pipeline: { stage1: { status: "ok" } },
  };
}

// Build a broken tally block: the SAME logic but with the JEG-319 additions
// removed. Used to prove the guard fails on the pre-fix code path.
function brokenTallySource(html) {
  const block = extractTallyBlock(html);
  // Strip everything from the JEG-319 marker up to (but not including) the
  // `const total = ...` line, then re-append the total line: the broken block
  // must still define `total` or the self-test crashes with ReferenceError
  // instead of proving the guard is vacuous.
  const cutAt = block.indexOf("// JEG-319:");
  if (cutAt <= 0) return block;
  const totalIdx = block.indexOf("const total");
  const totalLine = totalIdx >= 0 ? block.slice(totalIdx) : "";
  return block.slice(0, cutAt) + totalLine;
}

async function runBrokenTally(html, data, artifacts) {
  const block = brokenTallySource(html);
  const SOURCE_ORDER = extractSourceOrder(html);
  // eslint-disable-next-line no-new-func
  const fn = new Function(
    "data", "SOURCE_ORDER", "fetch",
    `return (async () => { ${block} return { counts, total }; })();`,
  );
  return await fn(data, SOURCE_ORDER, makeFetch(artifacts));
}

const VORP_OK = JSON.stringify({
  view: "vorp",
  status: "ok",
  sources: {
    espn: { status: "ok" },
    cbs: { status: "ok" },
  },
});
const ADJ_OK = JSON.stringify({
  view: "adj",
  status: "ok",
  sources: {
    espn: { status: "ok" },
    cbs: { status: "ok" },
  },
});
const ADJ_BAD = JSON.stringify({
  view: "adj",
  status: "bad",
  sources: {
    espn: { status: "bad", reasons: ["forced bad"] },
  },
});
const VORP_BAD = JSON.stringify({
  view: "vorp",
  status: "bad",
  sources: {},
});

function assertEq(label, got, want, sink) {
  if (got !== want) sink.push(`${label}: got ${JSON.stringify(got)}, want ${JSON.stringify(want)}`);
}

async function main() {
  const html = fs.readFileSync(DASHBOARD, "utf8");
  const outIdx = process.argv.indexOf("--out");
  const outPath = outIdx > 0 ? process.argv[outIdx + 1] : null;

  const report = { passed: true, problems: [], scenarios: [] };

  // ---- (a) both views ok -> total goes up by 2, ok fraction still 100% ----
  // Baseline is the pre-JEG-319 tally (views not counted); the fixed tally
  // must add exactly the two OK views. (Production counts missing view
  // artifacts as "bad", so an empty-artifact baseline would not be clean.)
  {
    const artifacts = { "vorp-view.json": VORP_OK, "adj-view.json": ADJ_OK };
    const baseline = await runBrokenTally(html, cleanData(), artifacts);
    const withViews = await runTally(html, cleanData(), artifacts);
    const a = withViews;
    const okFraction = a.total === 0 ? 0 : (a.counts.ok / a.total) * 100;
    const step = {
      name: "a_both_views_ok",
      baseline: baseline.total,
      withViewsTotal: a.total,
      delta: a.total - baseline.total,
      counts: a.counts,
      okFraction: Number(okFraction.toFixed(2)),
    };
    report.scenarios.push(step);
    assertEq("(a) total adds 2", a.total - baseline.total, 2, report.problems);
    assertEq("(a) ok count adds 2", a.counts.ok - baseline.counts.ok, 2, report.problems);
    assertEq("(a) bad count unchanged", a.counts.bad - baseline.counts.bad, 0, report.problems);
    assertEq("(a) ok fraction is 100%", okFraction, 100, report.problems);
  }

  // ---- (b) one view bad -> bad count +1 ----
  {
    const artifacts = { "vorp-view.json": VORP_OK, "adj-view.json": ADJ_BAD };
    const baseline = await runBrokenTally(html, cleanData(), artifacts);
    const withOneBad = await runTally(html, cleanData(), artifacts);
    const b = withOneBad;
    const step = {
      name: "b_one_view_bad",
      baselineBad: baseline.counts.bad,
      withOneBadCount: b.counts.bad,
      delta: b.counts.bad - baseline.counts.bad,
      counts: b.counts,
    };
    report.scenarios.push(step);
    assertEq("(b) bad count adds 1", b.counts.bad - baseline.counts.bad, 1, report.problems);
    assertEq("(b) ok count adds 1", b.counts.ok - baseline.counts.ok, 1, report.problems);
  }

  // ---- (c) vorp-view.json = {view:'vorp', status:'bad', sources:{}} -> bad=1 ----
  {
    // The minimal broken artifact: just the three required fields. The fixture
    // uses an empty sources map (the test in the ticket).
    const minimal = JSON.stringify({ view: "vorp", status: "bad", sources: {} });
    const result = await runTally(html, cleanData(), {
      "vorp-view.json": minimal, "adj-view.json": ADJ_OK,
    });
    const step = {
      name: "c_minimal_vorp_bad",
      counts: result.counts,
      bad: result.counts.bad,
    };
    report.scenarios.push(step);
    assertEq("(c) bad count is 1", result.counts.bad, 1, report.problems);
  }

  // ---- self-test: a broken tally block (JEG-319 additions stripped) must
  //      fail (b). If the broken implementation also reports bad+1 in
  //      scenario (b), the guard cannot catch the bug it names.
  {
    const baseline = await runBrokenTally(html, cleanData(), {});
    const withOneBad = await runBrokenTally(html, cleanData(), {
      "vorp-view.json": VORP_OK, "adj-view.json": ADJ_BAD,
    });
    const brokenCatchesBug = (withOneBad.counts.bad - baseline.counts.bad) === 0;
    const step = {
      name: "self_test_broken_tally",
      baselineBad: baseline.counts.bad,
      brokenBadAfter: withOneBad.counts.bad,
      brokenDoesNotDetectBug: brokenCatchesBug,
    };
    report.scenarios.push(step);
    // The broken tally must NOT report the +1 bad that the fixed tally
    // reports. If it does, this regression guard is vacuous.
    if (!brokenCatchesBug) {
      report.problems.push(
        "self-test: broken tally (no view statuses) still reports bad+1 in scenario (b); " +
        "the guard cannot fail and is therefore vacuous",
      );
    }
  }

  if (report.problems.length) report.passed = false;
  if (outPath) {
    fs.mkdirSync(path.dirname(path.resolve(outPath)), { recursive: true });
    fs.writeFileSync(outPath, JSON.stringify(report, null, 2) + "\n");
  }
  for (const p of report.problems) console.error("PROBLEM:", p);
  console.log(`scenarios: ${report.scenarios.length}, problems: ${report.problems.length}`);
  if (!report.passed) { console.error("FLEET HEADLINE GATE FAILED"); process.exit(1); }
  console.log("fleet headline gate passed");
}

main().catch(e => { console.error(e); process.exit(1); });