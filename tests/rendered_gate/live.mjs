// Live-page synthetic gate for remote URL testing (JEG-136).
//
// Usage: node live.mjs --url <url> --expected-build <tag> --out <path>
//
// BLOCKING (exit 1): any uncaught page error, missing controls, JS errors,
//                    bad DDF pie, absent/mismatched build tag, navigation errors.
// Exercises all 12 scoring x league-size shapes (Standard/Half/Full x 8/10/12/14).
//
// Not gated: console errors (ChartHealth messages, failed resource loads).
// playwright-core is imported lazily inside check() so --help and arg
// parsing work without the package installed.
import fs from "node:fs";
import path from "node:path";
import https from "node:https";
import http from "node:http";

const SCORINGS = ["Standard", "Half", "Full"];
const TEAMS = ["8", "10", "12", "14"];

function httpGet(url) {
  return new Promise((resolve, reject) => {
    const client = url.startsWith("https") ? https : http;
    client.get(url, { timeout: 30000 }, res => {
      let data = "";
      res.on("data", chunk => data += chunk);
      res.on("end", () => resolve({ status: res.statusCode, body: data }));
    }).on("error", reject);
  });
}

function extractBuildTag(html) {
  const match = html.match(/<meta name="trade-chart-build" content="([^"]+)"/);
  return match ? match[1] : null;
}

export function verdict(report) {
  const problems = [];
  if (report.pageErrors.length) problems.push(`${report.pageErrors.length} uncaught page error(s)`);
  if (report.pieBad.length) {
    const badShapes = report.pieBad.map(r => `${r.shape}=${r.sum}`).join(", ");
    problems.push(`DDF pie does not sum to 100.0 in ${report.pieBad.length} shape(s): ${badShapes}`);
  }
  if (!report.shapesVisited) problems.push("no league shapes were exercised (page did not render controls)");
  if (report.missingControls.length) {
    problems.push(`missing controls: ${report.missingControls.join(", ")}`);
  }
  if (report.buildMismatch) {
    problems.push(`build tag mismatch: expected ${report.expectedBuild}, got ${report.observedBuild}`);
  }
  if (report.navigationError) {
    problems.push(`navigation error: ${report.navigationError}`);
  }
  return problems;
}

async function check(url, expectedBuild) {
  const { chromium } = await import("playwright-core");
  const browser = await chromium.launch({
    executablePath: process.env.CHROMIUM_PATH || undefined,
    args: ["--no-sandbox"]
  });
  const report = {
    url,
    expectedBuild,
    observedBuild: null,
    buildMismatch: false,
    pageErrors: [],
    shapesVisited: 0,
    pie: [],
    pieBad: [],
    missingControls: [],
    navigationError: null,
    generatedAt: new Date().toISOString()
  };

  try {
    // First verify the page loads and extract build tag
    const fetchResult = await httpGet(url);
    if (fetchResult.status !== 200) {
      report.navigationError = `HTTP ${fetchResult.status}`;
      return report;
    }
    report.observedBuild = extractBuildTag(fetchResult.body);
    if (expectedBuild && report.observedBuild !== expectedBuild) {
      report.buildMismatch = true;
    }

    // Now test with Playwright
    const page = await browser.newPage({ viewport: { width: 1400, height: 1000 } });
    page.on("pageerror", e => report.pageErrors.push(String(e).slice(0, 240)));

    try {
      await page.goto(url, { waitUntil: "networkidle", timeout: 30000 });
    } catch (e) {
      report.navigationError = String(e).slice(0, 200);
      return report;
    }

    await page.waitForTimeout(1500);

    // Check that required controls exist
    const availableControls = await page.evaluate(() => {
      const buttons = Array.from(document.querySelectorAll("button")).map(b => b.textContent.trim());
      return buttons;
    });

    for (const scoring of SCORINGS) {
      if (!availableControls.includes(scoring)) {
        report.missingControls.push(`scoring: ${scoring}`);
      }
    }
    for (const teams of TEAMS) {
      if (!availableControls.includes(teams)) {
        report.missingControls.push(`teams: ${teams}`);
      }
    }

    // Click through all shapes
    const click = async text => {
      const b = page.locator("button", { hasText: new RegExp(`^${text}$`) }).first();
      if (!(await b.count())) return false;
      await b.click();
      await page.waitForTimeout(500);
      return true;
    };

    for (const scoring of SCORINGS) {
      for (const teams of TEAMS) {
        if (!(await click(scoring)) || !(await click(teams))) continue;
        report.shapesVisited++;
        const labels = await page.evaluate(() => {
          const t = (document.querySelector("#weightsReadout")?.textContent || "").replace(/\s+/g, " ");
          const shown = {};
          for (const m of t.matchAll(/(QB|RB|WR|TE) (\d+(?:\.\d+)?)%/g)) {
            shown[m[1]] = Number(m[2]);
          }
          return shown;
        });
        const sum = Object.values(labels).reduce((a, b) => a + b, 0);
        const row = { shape: `${scoring}/${teams}`, labels, sum: Number(sum.toFixed(1)) };
        report.pie.push(row);
        if (Math.abs(sum - 100) > 0.05) report.pieBad.push(row);
      }
    }
  } finally {
    await browser.close();
  }
  return report;
}

async function main() {
  const args = process.argv.slice(2);
  let url = null;
  let expectedBuild = null;
  let outPath = null;

  for (let i = 0; i < args.length; i++) {
    if (args[i] === "--url" && i + 1 < args.length) {
      url = args[i + 1];
      i++;
    } else if (args[i] === "--expected-build" && i + 1 < args.length) {
      expectedBuild = args[i + 1];
      i++;
    } else if (args[i] === "--out" && i + 1 < args.length) {
      outPath = args[i + 1];
      i++;
    }
  }

  if (!url) {
    console.error("Usage: node live.mjs --url <url> --expected-build <tag> --out <path>");
    process.exit(1);
  }

  console.log(`Testing remote URL: ${url}`);
  if (expectedBuild) {
    console.log(`Expected build tag: ${expectedBuild}`);
  }

  const report = await check(url, expectedBuild);

  // Write output JSON
  if (outPath) {
    fs.writeFileSync(outPath, JSON.stringify(report, null, 2));
    console.log(`Report written to: ${outPath}`);
  }

  // Console output
  console.log(`\n--- Results ---`);
  console.log(`Shapes exercised: ${report.shapesVisited}/12`);
  console.log(`Expected shapes: 12`);
  console.log(`Uncaught page errors: ${report.pageErrors.length}`);
  if (report.pageErrors.length) {
    console.log(`  Errors:`, report.pageErrors);
  }
  console.log(`DDF fixed pie (blocking): ${report.pieBad.length} of ${report.pie.length} shapes do not sum to 100.0`);
  if (report.pieBad.length) {
    console.log(`  Bad shapes:`, report.pieBad.map(r => `${r.shape}=${r.sum}`).join(", "));
  }
  console.log(`Missing controls: ${report.missingControls.length ? report.missingControls.join(", ") : "none"}`);
  console.log(`Build tag: observed=${report.observedBuild}, expected=${expectedBuild || "none"}`);
  console.log(`Navigation: ${report.navigationError || "OK"}`);

  const problems = verdict(report);
  if (problems.length) {
    console.error("\nRENDERED GATE FAILED:", problems.join("; "));
    process.exit(1);
  }

  console.log("\nRendered gate passed");
  process.exit(0);
}

if (import.meta.url === `file://${process.argv[1]}`) {
  main().catch(e => {
    console.error(e);
    process.exit(1);
  });
}
