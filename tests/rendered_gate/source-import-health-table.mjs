// JEG-312 regression guard: c3_supabase cells in the dashboard's source
// checkpoint cards now render the supabase_table name as a second line
// under the row count, so readers can see which Supabase table each
// verdict refers to (was previously hidden inside the reason text).
//
// Discrimination:
//   (a) Source WITH a supabase_table (CBS): the rendered C3 cell MUST
//       contain a .cp-table child whose text equals the expected table,
//       and that .cp-table MUST appear AFTER the .cp-reason row-count line.
//   (b) Source WITHOUT a supabase_table (razzball in the synthetic fixture
//       -- reason is "N/A by design: file-scraped source." with no table
//       token): the rendered C3 cell MUST NOT contain a .cp-table child,
//       and MUST fall back to the original single-line .cp-reason text.
//
// Usage: node source-import-health-table.mjs <dist-dir>
// Output JSON:
//   {
//     ok: bool,
//     withTable: { source, expectedTable, renderedTable, secondLinePresent },
//     withoutTable: { source, renderedHasTable, reasonText },
//     mismatches: string[],
//     pageErrors: string[],
//   }
// Exits 1 on mismatch or any uncaught page error.
//
// Self-test: re-running with the .cp-table branch REMOVED from
// dashboard.html must flip (a) red (second line missing) while leaving
// (b) green (the fallback path is unaffected). That is the discrimination
// check: the guard asserts behaviour unique to the fix.

import { chromium } from "playwright-core";
import http from "node:http";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

const DIST = path.resolve(process.argv[2] || "dist");
const MIME = {
  ".html": "text/html", ".js": "text/javascript", ".json": "application/json",
  ".css": "text/css", ".jpg": "image/jpeg", ".png": "image/png", ".svg": "image/svg+xml",
};

// Synthetic pipeline-checkpoints.json with two sources:
//   - cbs: c3 reason embeds "rows landed in public.cbs_trade_values 2.5d ago."
//     so the parse-table-from-reason branch fires (no direct supabase_table
//     field -- matches the real pipeline-checkpoints.json shape).
//   - razzball: c3 reason is "N/A by design: file-scraped source." so no
//     table token is present, exercising the fallback to current text.
const SYNTHETIC_CP = {
  generated_at: "2026-10-03T22:00:00+00:00",
  schema: "pipeline-checkpoints-v1",
  nfl_week: 4,
  checkpoints: [
    { key: "c1_publication",  label: "C1 \u00b7 Publication/discovery",     what: "Publisher releases new trade-value data" },
    { key: "c2_collection",   label: "C2 \u00b7 Raw collection",            what: "Pull script fetches publisher HTML" },
    { key: "c3_supabase",      label: "C3 \u00b7 Supabase landing",          what: "Save script writes rows to Supabase" },
    { key: "c4_snapshot",      label: "C4 \u00b7 Snapshot/manifest",         what: "import_supabase_references.py stamps Supabase \u2192 data/raw" },
    { key: "c5_health",        label: "C5 \u00b7 Health verification",       what: "verify_import_health.py checks integrity" },
    { key: "c6_candidate",     label: "C6 \u00b7 Candidate build/review",    what: "build_comparison_source_section.py builds candidate" },
    { key: "c7_promotion",     label: "C7 \u00b7 Fixture promotion",         what: "promote_comparison_section.py promotes reviewed candidate" },
    { key: "c8_sync",          label: "C8 \u00b7 Sync/validation",           what: "Fixture synced app/ \u2192 dist/" },
    { key: "c9_deploy",        label: "C9 \u00b7 Deployment/live artifact",  what: "GitHub Pages deploys dist/" },
    { key: "c10_rendered",     label: "C10 \u00b7 Rendered production output", what: "Live production JSON serves correct week labels" },
  ],
  sources: {
    cbs: {
      label: "CBS",
      checkpoints: {
        c1_publication:  { timestamp: "Week 4",                                  status: "ok",  reason: "Publisher released Week 4 (0.0d ago)." },
        c2_collection:   { timestamp: "2026-10-03T00:00:00+00:00",                status: "ok",  reason: "Pulled 2026-10-03." },
        // Supabase table name embedded in the reason text (no direct field).
        c3_supabase:     { timestamp: "2026-10-01T00:00:00+00:00",                status: "ok",  reason: "342 rows landed in public.cbs_trade_values 2.5d ago." },
        c4_snapshot:     { timestamp: "2026-10-01T00:00:00+00:00",                status: "ok",  reason: "Snapshot stamped (data/raw/sources/cbs/week-4/snapshot.json, vintage Week 4)." },
        c5_health:       { timestamp: "2026-10-03T22:00:00+00:00",                status: "ok",  reason: "Health gate ok (checked just now)." },
        c6_candidate:    { timestamp: null,                                       status: "unk", reason: "" },
        c7_promotion:    { timestamp: null,                                       status: "ok",  reason: "Promoted." },
        c8_sync:         { timestamp: "2026-10-03T22:00:00+00:00",                status: "ok",  reason: "Comparison data fresh." },
        c9_deploy:       { timestamp: "2026-10-03T22:00:00+00:00",                status: "ok",  reason: "Pages deployed successfully." },
        c10_rendered:    { timestamp: "2026-10-03T22:00:00+00:00",                status: "ok",  reason: "Production serves Week 4 labels." },
      },
    },
    razzball: {
      label: "Razzball",
      checkpoints: {
        c1_publication:  { timestamp: "2026-10-01",                              status: "ok",  reason: "Publisher released 2026-10-01." },
        c2_collection:   { timestamp: "2026-10-01T13:22:04+00:00",                status: "ok",  reason: "Pulled 2026-10-01." },
        // No table token -- must fall back to current single-line text.
        c3_supabase:     { timestamp: null,                                       status: "ok",  reason: "N/A by design: file-scraped source." },
        c4_snapshot:     { timestamp: "2026-10-01T13:22:04+00:00",                status: "ok",  reason: "Snapshot stamped (vintage 2026-10-01)." },
        c5_health:       { timestamp: "2026-10-01T12:56:00+00:00",                status: "ok",  reason: "Health gate ok." },
        // c6/c7 deliberately missing -- the JEG-308 pill handles razzball.
        c8_sync:         { timestamp: "2026-10-03T22:00:00+00:00",                status: "ok",  reason: "Comparison data fresh." },
        c9_deploy:       { timestamp: "2026-10-03T22:00:00+00:00",                status: "ok",  reason: "Pages deployed successfully." },
        c10_rendered:    { timestamp: "2026-10-03T22:00:00+00:00",                status: "ok",  reason: "Production serves Week 4 labels." },
      },
    },
  },
};

// Expected table name for the CBS case (parsed from the reason).
const EXPECTED_TABLE = (SYNTHETIC_CP.sources.cbs.checkpoints.c3_supabase.reason
  .match(/rows landed in (\S+)\s+\d/) || [])[1] || null;

function serve(distDir, inject) {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "sih-table-"));
  const cpPaths = ["output/pipeline-checkpoints.json", "pipeline-checkpoints.json"];
  for (const p of cpPaths) {
    const full = path.join(tmp, p);
    fs.mkdirSync(path.dirname(full), { recursive: true });
    fs.writeFileSync(full, JSON.stringify(SYNTHETIC_CP));
  }
  const noop = "{}";
  for (const p of [
    "output/comparison-chain-status.json",
    "output/methodology-consistency.json",
    "output/scale-agreement.json",
    "output/vorp-translation.json",
    "output/adj-curve-pipeline.json",
    "modules/methodology-consistency.json",
    "modules/scale-agreement.json",
    "modules/vorp-translation.json",
    "modules/adj-curve-pipeline.json",
    "modules/comparison-chain-status.json",
  ]) {
    const full = path.join(tmp, p);
    fs.mkdirSync(path.dirname(full), { recursive: true });
    if (!fs.existsSync(full)) fs.writeFileSync(full, noop);
  }
  const dashHtml = fs.readFileSync(path.join(distDir, "modules", "dashboard.html"), "utf8");
  fs.writeFileSync(path.join(tmp, "dashboard.html"), dashHtml + (inject || ""));
  fs.mkdirSync(path.join(tmp, "modules"), { recursive: true });
  fs.writeFileSync(path.join(tmp, "modules", "dashboard.html"), dashHtml + (inject || ""));
  const server = http.createServer((req, res) => {
    const rel = decodeURIComponent(new URL(req.url, "http://x").pathname);
    const candidates = [
      path.join(tmp, rel.endsWith("/") ? rel + "index.html" : rel),
      path.join(distDir, rel.endsWith("/") ? rel + "index.html" : rel),
    ];
    for (const file of candidates) {
      if (file.startsWith(tmp) && fs.existsSync(file) && !fs.statSync(file).isDirectory()) {
        res.writeHead(200, { "content-type": MIME[path.extname(file)] || "application/octet-stream" });
        fs.createReadStream(file).pipe(res);
        return;
      }
    }
    res.writeHead(404).end("not found");
  });
  return new Promise(resolve => server.listen(0, "127.0.0.1", () => resolve({ server, tmp })));
}

// Pull the C3 cell + its children out of a source card.
function c3CellScript(srcId) {
  return `(() => {
    const card = document.getElementById(${JSON.stringify(srcId)});
    if (!card) return null;
    const cells = [...card.querySelectorAll(".cp:not(.razzball-pill)")];
    const c3 = cells.find(c => {
      const name = (c.querySelector(".cp-name")?.textContent || "").trim();
      return name.startsWith("C3");
    });
    if (!c3) return null;
    const reason = c3.querySelector(".cp-reason");
    const tableEl = c3.querySelector(".cp-table");
    const reasonText = reason ? (reason.textContent || "").replace(/\\s+/g, " ").trim() : null;
    const tableText = tableEl ? (tableEl.textContent || "").replace(/\\s+/g, " ").trim() : null;
    // DOM order: which child comes first inside the .cp card?
    const children = [...c3.children];
    const reasonIdx = children.indexOf(reason);
    const tableIdx = tableEl ? children.indexOf(tableEl) : -1;
    return {
      reasonText,
      tableText,
      reasonIdx,
      tableIdx,
      tablePresent: Boolean(tableEl),
    };
    })()`;
}

async function loadAndAssert(distDir) {
  const { server, tmp } = await serve(distDir, "");
  const browser = await chromium.launch({
    executablePath: process.env.CHROMIUM_PATH || undefined, args: ["--no-sandbox"] });
  const report = {
    ok: true,
    mismatches: [],
    pageErrors: [],
    withTable: { source: "cbs", expectedTable: EXPECTED_TABLE,
                renderedTable: null, secondLinePresent: false, reasonAfterTable: null },
    withoutTable: { source: "razzball", renderedHasTable: false, reasonText: null },
  };
  try {
    const page = await browser.newPage({ viewport: { width: 1400, height: 1000 } });
    page.on("pageerror", e => report.pageErrors.push(String(e).slice(0, 240)));
    await page.goto(`http://127.0.0.1:${server.address().port}/dashboard.html`, { waitUntil: "networkidle", timeout: 60000 });
    await page.waitForTimeout(800);
    await page.evaluate(() => {
      for (const id of ["src-cbs", "src-razzball"]) {
        const el = document.getElementById(id);
        if (el) el.classList.add("open");
      }
    });
    await page.waitForTimeout(200);

    // --- (a) CBS: .cp-table present with expected table name, AFTER the row count ---
    const cbs = await page.evaluate(c3CellScript("src-cbs"));
    if (!cbs) {
      report.mismatches.push("cbs: C3 cell missing in DOM");
    } else {
      report.withTable.renderedTable = cbs.tableText;
      report.withTable.secondLinePresent = cbs.tablePresent;
      report.withTable.reasonAfterTable = cbs.tableIdx > cbs.reasonIdx;
      if (!cbs.tablePresent) {
        report.mismatches.push("cbs C3: .cp-table missing (supabase_table second line not rendered)");
      }
      if (cbs.tableText !== EXPECTED_TABLE) {
        report.mismatches.push(`cbs C3: .cp-table text ${JSON.stringify(cbs.tableText)} != expected ${JSON.stringify(EXPECTED_TABLE)}`);
      }
      if (cbs.tablePresent && cbs.tableIdx <= cbs.reasonIdx) {
        report.mismatches.push("cbs C3: .cp-table must appear AFTER .cp-reason (row count line)");
      }
      // The row-count reason line must remain intact (the second line is additive).
      if (!cbs.reasonText || !cbs.reasonText.includes("342 rows landed")) {
        report.mismatches.push(`cbs C3: .cp-reason lost its row-count text: ${JSON.stringify(cbs.reasonText)}`);
      }
    }

    // --- (b) Razzball: no .cp-table, fallback to current text ---
    const razzball = await page.evaluate(c3CellScript("src-razzball"));
    if (!razzball) {
      report.mismatches.push("razzball: C3 cell missing in DOM");
    } else {
      report.withoutTable.renderedHasTable = razzball.tablePresent;
      report.withoutTable.reasonText = razzball.reasonText;
      if (razzball.tablePresent) {
        report.mismatches.push(`razzball C3: .cp-table rendered (${JSON.stringify(razzball.tableText)}) but no supabase_table was resolvable -- fallback expected`);
      }
      if (!razzball.reasonText || !razzball.reasonText.includes("N/A by design")) {
        report.mismatches.push(`razzball C3: .cp-reason fallback text wrong: ${JSON.stringify(razzball.reasonText)}`);
      }
    }

    if (report.pageErrors.length) {
      report.mismatches.push(`${report.pageErrors.length} uncaught page error(s): ${report.pageErrors[0]}`);
    }
    if (report.mismatches.length) report.ok = false;
  } finally {
    await browser.close();
    server.close();
    try { fs.rmSync(tmp, { recursive: true, force: true }); } catch {}
  }
  return report;
}

async function main() {
  const report = await loadAndAssert(DIST);
  process.stdout.write(JSON.stringify(report, null, 2));
  if (!report.ok) process.exit(1);
}

if (import.meta.url === `file://${process.argv[1]}`) {
  main().catch(e => { console.error(e); process.exit(2); });
}