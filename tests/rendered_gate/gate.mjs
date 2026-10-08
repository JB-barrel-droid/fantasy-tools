// Rendered-page gate for the built dist/ (JEG-47, approved by Muse with bound scope).
//
// Usage: node gate.mjs <dist-dir> [--out report.json]
//
// BLOCKING (exit 1):  any uncaught page error (`pageerror`) on load or while stepping
//                     through the 12 scoring x league-size shapes (JEG-44).
//                     Also BLOCKING since JEG-24 was fixed: the DDF pie. The Pie readout's
//                     four labels must sum to 100.0 in every shape. It covers the DDF
//                     pie only: as-published source curves are deliberately NOT checked
//                     (their totals differ by design; see the FantasyCalc note in
//                     docs/claude-log.md).
// Not gated: console errors (ChartHealth messages, failed resource loads).
//
// Discrimination: every run also copies dist twice, once injecting a throw and once
// forcing a pie readout that sums to 100.1, and requires this gate to catch both. A
// gate that cannot fail exits 1 here ("self-test").
import { chromium } from "playwright-core";
import { enginePageFor } from "./engine_page.mjs";
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
    const engine = enginePageFor(rel);
    let file = engine || path.join(dir, rel.endsWith("/") ? rel + "index.html" : rel);
    if ((!engine && !file.startsWith(dir)) || !fs.existsSync(file) || fs.statSync(file).isDirectory()) {
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
  if (report.pieBad.length) problems.push(`DDF pie does not sum to 100.0 in ${report.pieBad.length} shape(s): ${report.pieBad.map(r => `${r.shape}=${r.sum}`).join(", ")}`);
  if (!report.shapesVisited) problems.push("no league shapes were exercised (page did not render controls)");
  return problems;
}

async function check(dir) {
  const server = await serve(dir);
  const browser = await chromium.launch({
    executablePath: process.env.CHROMIUM_PATH || undefined, args: ["--no-sandbox",
      // Hermetic (2026-10-08): no request leaves the machine; external
      // fonts made networkidle waits flaky.
      "--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1, EXCLUDE localhost"] });
  const report = { pageErrors: [], shapesVisited: 0, pie: [], pieBad: [] };
  try {
    const page = await browser.newPage({ viewport: { width: 1400, height: 1000 } });
    page.on("pageerror", e => report.pageErrors.push(String(e).slice(0, 240)));
    await page.goto(`http://127.0.0.1:${server.address().port}/classic/`, { waitUntil: "networkidle" });
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

const THROW = "\nsetTimeout(() => { throw new Error('gate self-test injected error'); }, 0);\n";
const BAD_PIE = "\nsetInterval(() => { const r = document.getElementById('weightsReadout'); " +
  "if (r) r.textContent = 'Pie: QB 25.1% \u00b7 RB 25.0% \u00b7 WR 25.0% \u00b7 TE 25.0%'; }, 20);\n";

function injectedCopy(dist, snippet) {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "gate-selftest-"));
  fs.cpSync(dist, tmp, { recursive: true });
  fs.appendFileSync(path.join(tmp, INJECT_FILE), snippet);
  return tmp;
}

async function main() {
  const dist = path.resolve(process.argv[2] || "dist");
  const outIdx = process.argv.indexOf("--out");
  const out = outIdx > 0 ? process.argv[outIdx + 1] : null;
  const real = await check(dist);
  const brokenThrow = await check(injectedCopy(dist, THROW));
  const brokenPie = await check(injectedCopy(dist, BAD_PIE));
  const caughtThrow = brokenThrow.pageErrors.length > 0 && verdict(brokenThrow).length > 0;
  const caughtPie = brokenPie.pieBad.length > 0 && verdict(brokenPie).length > 0;
  const selfTestCaught = caughtThrow && caughtPie;
  const problems = verdict(real);
  if (!caughtThrow) problems.push("self-test: an injected page error was NOT caught, so the gate cannot fail");
  if (!caughtPie) problems.push("self-test: an injected bad pie sum was NOT caught, so the pie check cannot fail");
  const summary = { ...real, selfTestCaught, blocking: problems };
  if (out) fs.writeFileSync(out, JSON.stringify(summary, null, 2));
  console.log(`shapes exercised: ${real.shapesVisited}/12`);
  console.log(`uncaught page errors: ${real.pageErrors.length}`, real.pageErrors);
  console.log(`DDF fixed pie (blocking): ${real.pieBad.length} of ${real.pie.length} shapes do not sum to 100.0`,
    real.pieBad.map(r => `${r.shape}=${r.sum}`).join(", "));
  console.log(`self-test caught injected page error: ${caughtThrow}, bad pie: ${caughtPie}`);
  if (problems.length) { console.error("RENDERED GATE FAILED:", problems.join("; ")); process.exit(1); }
  console.log("rendered gate passed");
}

if (import.meta.url === `file://${process.argv[1]}`) main().catch(e => { console.error(e); process.exit(1); });
