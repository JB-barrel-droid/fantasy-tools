// Rendered-gate test for JEG-312: c3_supabase cell renders the
// supabase_table name as a second line under the row count, and falls back
// to the existing single-line reason when the table is not parseable.
//
// Usage: node source-import-health-table.mjs <dist-dir> [--out report.json]
//
// Loads the built dashboard, asserts (a) every source with a c3_supabase
// checkpoint whose reason embeds "rows landed in <table>" renders a
// .cp-table second line with the correct table name, and (b) sources whose
// c3 reason does not embed a table name (e.g. "N/A by design: ...") do NOT
// render a .cp-table line -- the cell falls back to the original single-line
// reason text.
//
// Discrimination: a self-test copies dist once with the JEG-312 logic
// removed (forces tableLine always empty) and requires this gate to catch
// the regression. A gate that always passes exits 1 ("self-test").

import { chromium } from "playwright-core";
import http from "node:http";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

const MIME = { ".html": "text/html", ".js": "text/javascript",
  ".json": "application/json", ".css": "text/css" };

function serve(dir) {
  const server = http.createServer((req, res) => {
    const rel = decodeURIComponent(new URL(req.url, "http://x").pathname);
    let file = path.join(dir, rel.endsWith("/") ? rel + "index.html" : rel);
    if (!file.startsWith(dir) || !fs.existsSync(file) || fs.statSync(file).isDirectory()) {
      res.writeHead(404).end("not found"); return;
    }
    res.writeHead(200, { "content-type": MIME[path.extname(file)] || "application/octet-stream" });
    fs.createReadStream(file).pipe(res);
  });
  return new Promise(resolve => server.listen(0, "127.0.0.1", () => resolve(server)));
}

// Pull the live c3_supabase rows out of the embedded JSON. The dashboard
// inlines pipeline-checkpoints.json into the page via fetch+main(); rather
// than re-implement that, we read it from disk and use it to drive the
// expectations.
function loadC3Rows(dist) {
  const p = path.join(dist, "modules", "pipeline-checkpoints.json");
  if (!fs.existsSync(p)) {
    throw new Error(`pipeline-checkpoints.json not found at ${p}`);
  }
  const json = JSON.parse(fs.readFileSync(p, "utf8"));
  const rows = [];
  for (const [src, sdata] of Object.entries(json.sources || {})) {
    const cp = sdata.checkpoints && sdata.checkpoints.c3_supabase;
    if (!cp) continue;
    const m = (cp.reason || "").match(/rows landed in (\S+)/);
    rows.push({ src, reason: cp.reason, table: m ? m[1] : null });
  }
  return rows;
}

async function probe(dist) {
  // Serve from the project root (parent of `modules/` and `dist/`) so the
  // dashboard at /modules/dashboard.html can resolve ../dist/modules/*.json.
  const root = path.resolve(dist, "..");
  const server = await serve(root);
  const browser = await chromium.launch({
    executablePath: process.env.CHROMIUM_PATH || undefined,
    args: ["--no-sandbox"],
  });
  const report = { rows: [], pageErrors: [], problems: [] };
  try {
    const page = await browser.newPage({ viewport: { width: 1400, height: 1000 } });
    page.on("pageerror", e => report.pageErrors.push(String(e).slice(0, 240)));
    await page.goto(`http://127.0.0.1:${server.address().port}/dashboard.html`,
      { waitUntil: "networkidle" });
    await page.waitForTimeout(2000);
    // Open every source card so the cp-grid is in the DOM.
    await page.evaluate(() => {
      document.querySelectorAll(".src").forEach(el => el.classList.add("open"));
    });
    await page.waitForTimeout(300);
    const expected = loadC3Rows(dist);
    for (const row of expected) {
      const got = await page.evaluate((src) => {
        const card = document.querySelector(`#src-${src} .cp-grid`);
        if (!card) return { found: false, cells: 0, tableLines: [], tableTexts: [], c3reason: null };
        const cells = Array.from(card.querySelectorAll(".cp"));
        const c3 = cells.find(c => /C3\s*·/.test(c.querySelector(".cp-name")?.textContent || ""));
        const tableLines = c3 ? Array.from(c3.querySelectorAll(".cp-table")).map(t => t.textContent.trim()) : [];
        return {
          found: !!c3,
          cells: cells.length,
          tableLines,
          tableTexts: tableLines.map(t => t.trim()),
          c3reason: c3 ? (c3.querySelector(".cp-reason")?.textContent?.trim() || null) : null,
        };
      }, row.src);
      report.rows.push({ src: row.src, expectedTable: row.table, ...got });
    }
  } finally {
    await browser.close(); server.close();
  }
  return report;
}

function verdict(report) {
  const problems = [];
  if (report.pageErrors.length) problems.push(`${report.pageErrors.length} uncaught page error(s)`);
  for (const r of report.rows) {
    if (!r.found) { problems.push(`${r.src}: c3_supabase cell not rendered`); continue; }
    if (r.expectedTable) {
      // Source has a parseable table -> second line MUST show the table name.
      if (r.tableLines.length !== 1) {
        problems.push(`${r.src}: expected exactly 1 .cp-table line under c3 row count, got ${r.tableLines.length}`);
      } else if (r.tableTexts[0] !== r.expectedTable) {
        problems.push(`${r.src}: .cp-table text ${JSON.stringify(r.tableTexts[0])} != expected ${JSON.stringify(r.expectedTable)}`);
      }
    } else {
      // No parseable table -> cell MUST fall back to single-line reason
      // (no .cp-table second line).
      if (r.tableLines.length !== 0) {
        problems.push(`${r.src}: c3 has no parseable table but ${r.tableLines.length} .cp-table line(s) leaked through (fallback broken)`);
      }
    }
  }
  return problems;
}

// Self-test injection: strip the JEG-312 second-line logic so the gate must
// fail when the regression guard has lost its discrimination.
function stripJEG312(dist) {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "jeg312-selftest-"));
  fs.cpSync(dist, tmp, { recursive: true });
  const p = path.join(tmp, "modules", "dashboard.html");
  if (!fs.existsSync(p)) throw new Error(`dashboard.html not found at ${p}`);
  let html = fs.readFileSync(p, "utf8");
  // Replace the JEG-312 conditional with an unconditional empty tableLine so
  // every c3 cell renders without the second line.
  const stripped = html
    .replace(/\/\/ JEG-312: c3 cell renders[\s\S]*?let tableLine = "";\s*if\(cpDef\.key === "c3_supabase"\)\{[\s\S]*?\}\s*\{/, "/* JEG-312 stripped */ let tableLine = \"\";")
    .replace(/let tableLine = "";[\s\S]*?\}\s*\n\s*return `<div class="cp">/, "let tableLine = \"\";\n      return `<div class=\"cp\">");
  if (stripped === html) {
    throw new Error("JEG-312 self-test: could not locate tableLine block to strip");
  }
  fs.writeFileSync(p, stripped);
  return tmp;
}

async function main() {
  const dist = path.resolve(process.argv[2] || "dist");
  const outIdx = process.argv.indexOf("--out");
  const out = outIdx > 0 ? process.argv[outIdx + 1] : null;
  const real = await probe(dist);
  const realProblems = verdict(real);
  const strippedDir = stripJEG312(dist);
  let selfProblems = ["self-test: probe did not run"];
  let selfReport = null;
  try {
    selfReport = await probe(strippedDir);
    selfProblems = verdict(selfReport);
  } catch (e) {
    selfProblems = [`self-test: ${String(e).slice(0, 200)}`];
  } finally {
    fs.rmSync(strippedDir, { recursive: true, force: true });
  }
  // Self-test contract: with JEG-312 stripped, sources that DO have a
  // parseable table must lose their second line -- the gate must catch it.
  const selfCaughtRegression = selfProblems.some(p => /expected exactly 1 \.cp-table line/.test(p));
  const passed = realProblems.length === 0 && selfCaughtRegression;
  const summary = {
    generatedAt: new Date().toISOString(),
    dist,
    rows: real.rows,
    realProblems,
    selfProblems,
    selfCaughtRegression,
    passed,
  };
  if (out) {
    fs.mkdirSync(path.dirname(path.resolve(out)), { recursive: true });
    fs.writeFileSync(out, JSON.stringify(summary, null, 2) + "\n");
  }
  if (!passed) {
    if (realProblems.length) {
      console.error("FAIL:");
      for (const p of realProblems) console.error("  " + p);
    }
    if (!selfCaughtRegression) {
      console.error("FAIL: self-test did not catch the JEG-312 regression (guard is toothless).");
      for (const p of selfProblems) console.error("  self: " + p);
    }
    process.exit(1);
  }
  console.log("ok: c3_supabase cells render supabase_table second line; fallback intact for unparseable reasons.");
}

main().catch(e => { console.error(e); process.exit(2); });