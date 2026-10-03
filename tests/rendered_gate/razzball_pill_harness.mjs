// JEG-308 regression guard: razzball's dashboard source card has ten checkpoint
// cells, but c6/c7 are honestly "by design empty" for that source (direct
// fixture updates bypass the candidate/promotion stage). The fix replaces the
// two missing cells with a single pill that documents the vintage date
// pulled from the razzball entry in pipeline-checkpoints.json.
//
// IMPORTANT — dist sync: this harness reads <dist-dir>/modules/dashboard.html,
// NOT modules/dashboard.html. The repo's published contract (AGENTS.md,
// "make sync is the single publish path") requires dist/modules/dashboard.html
// to be rebuilt from modules/dashboard.html after every edit. If you change
// modules/dashboard.html without rebuilding dist/, this harness will run
// against STALE code and silently pass green (or red, but for the wrong
// reason). Always run `make sync` (or equivalent dist mirror) BEFORE this
// guard in either verification mode below:
//   * branch verify (PASS expected): dist/modules/dashboard.html reflects
//     the pill branch — pill present, c6/c7 absent.
//   * main verify (RED expected): dist/modules/dashboard.html mirrors
//     origin/main's modules/dashboard.html — pill absent, c6/c7 render.
// Negative-testing this guard against a stale dist is a false-pass.
//
// Discrimination:
//   (a) Razzball source: the rendered card MUST contain a .razzball-pill cell
//       with the text "Direct fixture update · vintage YYYY-MM-DD" matching
//       the vintage extracted from the razzball c4_snapshot reason, and MUST
//       NOT contain any cell whose .cp-name starts with "C6" or "C7".
//   (b) Non-razzball source (CBS): the rendered card MUST still contain its
//       C6 cell (the pill is razzball-only -- a missing CBS C6 is a separate
//       defect, not a JEG-308 regression), and MUST NOT contain a
//       .razzball-pill.
//
// Usage: node razzball_pill_harness.mjs <dist-dir>
// Output JSON:
//   {
//     ok: bool,
//     razzball: { vintage: string|null, pillText: string|null, c6Cell: bool, c7Cell: bool },
//     cbs:      { pillPresent: bool, c6Cell: bool, c6Name: string|null },
//     mismatches: string[],
//     pageErrors: string[],
//   }
// Exits 1 on mismatch or any uncaught page error.
//
// Self-test: re-running with the pill branch REMOVED from dashboard.html must
// flip (a) red (pill missing on razzball). That is the discrimination check:
// the guard asserts behaviour unique to the fix, not behaviour that would
// pass before the fix too.

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

// Synthetic pipeline-checkpoints.json with exactly the two sources we need.
// Razzball has a real vintage in c4_snapshot.reason (parsed for the pill).
// CBS has c6_candidate present but with a null timestamp + "unk" status, so
// the dashboard still renders an "empty" C6 cell (the cp object is truthy).
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
        c3_supabase:     { timestamp: "2026-10-01T00:00:00+00:00",                status: "ok",  reason: "342 rows landed 2.5d ago." },
        c4_snapshot:     { timestamp: "2026-10-01T00:00:00+00:00",                status: "ok",  reason: "Snapshot stamped (data/raw/sources/cbs/week-4/snapshot.json, vintage Week 4)." },
        c5_health:       { timestamp: "2026-10-03T22:00:00+00:00",                status: "ok",  reason: "Health gate ok (checked just now)." },
        // Empty-but-present C6: cell must still render (cp object is truthy).
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
        c3_supabase:     { timestamp: null,                                       status: "ok",  reason: "N/A by design: file-scraped source." },
        // Vintage date lives in this reason string -- the pill must parse it.
        c4_snapshot:     { timestamp: "2026-10-01T13:22:04+00:00",                status: "ok",  reason: "Snapshot stamped (data/ddf-two-tier/ddf-20261001-razzball-ppr-12t-0p15/ddf_leg_razzball.json, vintage 2026-10-01)." },
        c5_health:       { timestamp: "2026-10-01T12:56:00+00:00",                status: "ok",  reason: "Health gate ok." },
        // c6/c7 present with "unk" status — before JEG-308 the dashboard
        // rendered these as two empty "unk" cells. After JEG-308 they MUST
        // NOT render (the explicit razzball skip on c6_candidate/c7_promotion
        // keys fires regardless of payload status). This exercises the
        // belt-and-suspenders guard, not just the `if(!cp) return ""` guard.
        c6_candidate:    { timestamp: null,                                       status: "unk", reason: "" },
        c7_promotion:    { timestamp: null,                                       status: "unk", reason: "" },
        c8_sync:         { timestamp: "2026-10-03T22:00:00+00:00",                status: "ok",  reason: "Comparison data fresh." },
        c9_deploy:       { timestamp: "2026-10-03T22:00:00+00:00",                status: "ok",  reason: "Pages deployed successfully." },
        c10_rendered:    { timestamp: "2026-10-03T22:00:00+00:00",                status: "ok",  reason: "Production serves Week 4 labels." },
      },
    },
  },
};

function serve(distDir, inject) {
  // Build a temp dir whose pipeline-checkpoints.json is the synthetic payload
  // and whose other files (if any) are pass-through to the real dist via a
  // small HTTP server that prefers the temp file. We only need the dashboard
  // HTML and the synthetic CP to render correctly.
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "razzball-pill-"));
  // Stage pipeline-checkpoints.json at every path the dashboard tries.
  const cpPaths = ["output/pipeline-checkpoints.json", "pipeline-checkpoints.json"];
  for (const p of cpPaths) {
    const full = path.join(tmp, p);
    fs.mkdirSync(path.dirname(full), { recursive: true });
    fs.writeFileSync(full, JSON.stringify(SYNTHETIC_CP));
  }
  // The dashboard also fetches comparison-chain-status.json and several
  // diagnostics from dist/modules/. Stage an empty object so the load does
  // not crash on missing files (firstOk() tolerates 404s by design).
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
  // Stage dashboard.html (read from the real dist). The dashboard lives at
  // dist/modules/dashboard.html in the built tree.
  const dashHtml = fs.readFileSync(path.join(distDir, "modules", "dashboard.html"), "utf8");
  // Write dashboard.html into the temp under both the root path and the
  // modules/ path the dashboard might be served at. The injected snippet
  // (if any) runs once the page DOM is parsed.
  fs.writeFileSync(path.join(tmp, "dashboard.html"), dashHtml + (inject || ""));
  fs.mkdirSync(path.join(tmp, "modules"), { recursive: true });
  fs.writeFileSync(path.join(tmp, "modules", "dashboard.html"), dashHtml + (inject || ""));
  // Server resolves from temp first, then falls back to real dist (so any
  // auxiliary asset not staged is still served).
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

async function loadAndAssert(distDir) {
  const { server, tmp } = await serve(distDir, "");
  const browser = await chromium.launch({
    executablePath: process.env.CHROMIUM_PATH || undefined, args: ["--no-sandbox"] });
  const report = { ok: true, mismatches: [], pageErrors: [],
    razzball: { vintage: null, pillText: null, c6Cell: false, c7Cell: false },
    cbs:      { pillPresent: false, c6Cell: false, c6Name: null } };
  try {
    const page = await browser.newPage({ viewport: { width: 1400, height: 1000 } });
    page.on("pageerror", e => report.pageErrors.push(String(e).slice(0, 240)));
    await page.goto(`http://127.0.0.1:${server.address().port}/dashboard.html`, { waitUntil: "networkidle", timeout: 60000 });
    // Give the async fetch + render a moment.
    await page.waitForTimeout(800);
    // Force-expand both source cards so the cp-grid is in the DOM.
    await page.evaluate(() => {
      for (const id of ["src-razzball", "src-cbs"]) {
        const el = document.getElementById(id);
        if (el) el.classList.add("open");
      }
    });
    await page.waitForTimeout(200);

    // --- (a) Razzball: pill present with vintage, c6/c7 absent ---
    const razzball = await page.evaluate(() => {
      const card = document.getElementById("src-razzball");
      if (!card) return null;
      const grid = card.querySelector(".cp-grid");
      if (!grid) return null;
      const pills = [...grid.querySelectorAll(".razzball-pill")];
      const pillText = pills.length ? (pills[0].textContent || "").replace(/\s+/g, " ").trim() : null;
      const cells = [...grid.querySelectorAll(".cp:not(.razzball-pill)")];
      const c6 = cells.find(c => (c.querySelector(".cp-name")?.textContent || "").trim().startsWith("C6"));
      const c7 = cells.find(c => (c.querySelector(".cp-name")?.textContent || "").trim().startsWith("C7"));
      return {
        pillText,
        pillCount: pills.length,
        c6Cell: Boolean(c6),
        c7Cell: Boolean(c7),
      };
    });
    if (!razzball) {
      report.mismatches.push("razzball source card or cp-grid missing in DOM");
    } else {
      // Extract expected vintage from the synthetic payload (so the test stays
      // honest if someone updates the fixture).
      const expectedVintage = (SYNTHETIC_CP.sources.razzball.checkpoints.c4_snapshot.reason
        .match(/vintage (\d{4}-\d{2}-\d{2})/) || [])[1] || null;
      report.razzball.vintage = expectedVintage;
      report.razzball.pillText = razzball.pillText;
      report.razzball.c6Cell = razzball.c6Cell;
      report.razzball.c7Cell = razzball.c7Cell;
      if (razzball.pillCount !== 1) {
        report.mismatches.push(`razzball: expected exactly 1 .razzball-pill, got ${razzball.pillCount}`);
      }
      if (!razzball.pillText || !razzball.pillText.includes("Direct fixture update")) {
        report.mismatches.push(`razzball pill text missing "Direct fixture update": ${JSON.stringify(razzball.pillText)}`);
      }
      if (expectedVintage && (!razzball.pillText || !razzball.pillText.includes(expectedVintage))) {
        report.mismatches.push(`razzball pill text missing vintage ${expectedVintage}: ${JSON.stringify(razzball.pillText)}`);
      }
      if (razzball.c6Cell) {
        report.mismatches.push("razzball: c6 cell still rendered (must be skipped when pill is applied)");
      }
      if (razzball.c7Cell) {
        report.mismatches.push("razzball: c7 cell still rendered (must be skipped when pill is applied)");
      }
    }

    // --- (b) CBS: pill NOT applied, c6 cell still rendered ---
    const cbs = await page.evaluate(() => {
      const card = document.getElementById("src-cbs");
      if (!card) return null;
      const grid = card.querySelector(".cp-grid");
      if (!grid) return null;
      const pills = [...grid.querySelectorAll(".razzball-pill")];
      const cells = [...grid.querySelectorAll(".cp:not(.razzball-pill)")];
      const c6 = cells.find(c => (c.querySelector(".cp-name")?.textContent || "").trim().startsWith("C6"));
      return {
        pillCount: pills.length,
        c6Cell: Boolean(c6),
        c6Name: c6 ? (c6.querySelector(".cp-name")?.textContent || "").trim() : null,
      };
    });
    if (!cbs) {
      report.mismatches.push("cbs source card or cp-grid missing in DOM");
    } else {
      report.cbs.pillPresent = cbs.pillCount > 0;
      report.cbs.c6Cell = cbs.c6Cell;
      report.cbs.c6Name = cbs.c6Name;
      if (cbs.pillCount !== 0) {
        report.mismatches.push(`cbs: .razzball-pill rendered (${cbs.pillCount}); pill is razzball-only`);
      }
      if (!cbs.c6Cell) {
        report.mismatches.push("cbs: c6 cell missing (empty c6 must still render for non-razzball sources)");
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