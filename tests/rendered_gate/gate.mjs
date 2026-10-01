// Rendered-page gate for the built dist/ (JEG-47, approved by Muse with bound scope).
//
// Usage: node gate.mjs <dist-dir> [--out report.json]
//
// BLOCKING (exit 1):  any uncaught page error (`pageerror`) on load or while stepping
//                     through the 12 scoring x league-size shapes (JEG-44).
// REPORT-ONLY:        the DDF fixed pie. The Pie readout's labels must sum to 100.0 in
//                     every shape (JEG-24). It covers the DDF pie only: as-published
//                     source curves are deliberately NOT checked (their totals differ
//                     by design; see the FantasyCalc note in docs/claude-log.md).
//                     Promote to blocking once JEG-24 is fixed.
// Not gated: console errors (ChartHealth messages, failed resource loads).
//
// Discrimination: every run also copies dist, injects a throw into the page script and
// requires this gate to catch it. A gate that cannot fail exits 1 here ("self-test").
import { chromium } from "playwright-core";
import http from "node:http";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

const SCORINGS = ["Standard", "Half", "Full"];
const TEAMS = ["8", "10", "12", "14"];
const MIME = { ".html": "text/html", ".js": "text/javascript", ".json": "application/json",
  ".css": "text/css", ".jpg": "image/jpeg", ".png": "image/png", ".svg": "image/svg+xml" };
const INJECT_FILE = "assets/comparison-dashboard.js";

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

export function verdict(report) {
  const problems = [];
  if (report.pageErrors.length) problems.push(`${report.pageErrors.length} uncaught page error(s)`);
  if (!report.shapesVisited) problems.push("no league shapes were exercised (page did not render controls)");
  return problems;
}

async function check(dir) {
  const server = await serve(dir);
  const browser = await chromium.launch({
    executablePath: process.env.CHROMIUM_PATH || undefined, args: ["--no-sandbox"] });
  const report = { pageErrors: [], shapesVisited: 0, pie: [], pieBad: [] };
  try {
    const page = await browser.newPage({ viewport: { width: 1400, height: 1000 } });
    page.on("pageerror", e => report.pageErrors.push(String(e).slice(0, 240)));
    await page.goto(`http://127.0.0.1:${server.address().port}/`, { waitUntil: "networkidle" });
    await page.waitForTimeout(1500);
    const click = async text => {
      const b = page.locator("button", { hasText: new RegExp(`^${text}$`) }).first();
      if (!(await b.count())) return false;
      await b.click(); await page.waitForTimeout(500); return true;
    };
    for (const scoring of SCORINGS) for (const teams of TEAMS) {
      if (!(await click(scoring)) || !(await click(teams))) continue;
      report.shapesVisited++;
      const labels = await page.evaluate(() => {
        const t = (document.querySelector("#weightsReadout")?.textContent || "").replace(/\s+/g, " ");
        const shown = {};
        for (const m of t.matchAll(/(QB|RB|WR|TE) (\d+(?:\.\d+)?)%/g)) shown[m[1]] = Number(m[2]);
        return shown;
      });
      const sum = Object.values(labels).reduce((a, b) => a + b, 0);
      const row = { shape: `${scoring}/${teams}`, labels, sum: Number(sum.toFixed(1)) };
      report.pie.push(row);
      if (Math.abs(sum - 100) > 0.05) report.pieBad.push(row);
    }
  } finally {
    await browser.close(); server.close();
  }
  return report;
}

function injectedCopy(dist) {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "gate-selftest-"));
  fs.cpSync(dist, tmp, { recursive: true });
  const f = path.join(tmp, INJECT_FILE);
  fs.appendFileSync(f, "\nsetTimeout(() => { throw new Error('gate self-test injected error'); }, 0);\n");
  return tmp;
}

async function main() {
  const dist = path.resolve(process.argv[2] || "dist");
  const outIdx = process.argv.indexOf("--out");
  const out = outIdx > 0 ? process.argv[outIdx + 1] : null;
  const real = await check(dist);
  const broken = await check(injectedCopy(dist));
  const selfTestCaught = verdict(broken).length > 0;
  const problems = verdict(real);
  if (!selfTestCaught) problems.push("self-test: an injected page error was NOT caught, so the gate cannot fail");
  const summary = { ...real, selfTestCaught, blocking: problems };
  if (out) fs.writeFileSync(out, JSON.stringify(summary, null, 2));
  console.log(`shapes exercised: ${real.shapesVisited}/12`);
  console.log(`uncaught page errors: ${real.pageErrors.length}`, real.pageErrors);
  console.log(`DDF fixed pie (report-only): ${real.pieBad.length} of ${real.pie.length} shapes do not sum to 100.0`,
    real.pieBad.map(r => `${r.shape}=${r.sum}`).join(", "));
  console.log(`self-test caught injected error: ${selfTestCaught}`);
  if (problems.length) { console.error("RENDERED GATE FAILED:", problems.join("; ")); process.exit(1); }
  console.log("rendered gate passed");
}

if (import.meta.url === `file://${process.argv[1]}`) main().catch(e => { console.error(e); process.exit(1); });
