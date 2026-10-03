// Live-page synthetic gate (JEG-136; JEG-263 fix).
//
// Usage:
//   node live.mjs --url <url> --expected-build <tag> [--expected-build <tag2> ...] --out report.json
//
// Fetches the live page in headless Chromium, reads the trade-chart-build meta
// tag (stamped by `make sync` in the deploy pipeline), and compares it against
// the expected tag(s). The workflow passes the tag computed from HEAD's commit
// time plus HEAD~1's tag, so a deploy still in flight (live serving the
// previous build) does not false-fail. Exit 0 when the live tag matches ANY
// expected tag and the page loads without uncaught errors; exit 1 otherwise.
// A JSON report is always written to --out (fail-closed: an unwritable or
// missing --out is itself exit 1).
//
// JEG-263: the expected tag must be computed from the commit (deterministic:
// tv-YYYYMMDD-HHMM-<sha> from HEAD's commit time), NEVER grepped from the
// repo's committed dist/index.html -- the deploy pipeline rebuilds dist/ in CI
// and never commits it back, so the committed copy's tag is stale by
// construction and the gate could never pass.
import { chromium } from "playwright-core";
import fs from "node:fs";
import path from "node:path";

function usage() {
  console.error("usage: node live.mjs --url <url> --expected-build <tag> [--expected-build <tag2> ...] --out report.json");
  process.exit(2);
}

function parseArgs(argv) {
  const args = { url: null, expectedBuilds: [], out: null };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === "--url") args.url = argv[++i];
    else if (a === "--expected-build") args.expectedBuilds.push(argv[++i]);
    else if (a === "--out") args.out = argv[++i];
    else usage();
  }
  if (!args.url || !args.expectedBuilds.length || !args.out) usage();
  return args;
}

function writeReport(outPath, report) {
  const dir = path.dirname(path.resolve(outPath));
  fs.mkdirSync(dir, { recursive: true });
  fs.writeFileSync(outPath, JSON.stringify(report, null, 2) + "\n");
}

async function check(url, expectedBuilds) {
  const report = {
    generatedAt: new Date().toISOString(),
    url,
    expectedBuilds,
    liveTag: null,
    buildStamp: null,
    httpStatus: null,
    pageErrors: [],
    problems: [],
    passed: false,
  };
  const browser = await chromium.launch({
    executablePath: process.env.CHROMIUM_PATH || undefined,
    args: ["--no-sandbox"],
  });
  try {
    const page = await browser.newPage({ viewport: { width: 1400, height: 1000 } });
    page.on("pageerror", (e) => report.pageErrors.push(String(e).slice(0, 240)));
    let response = null;
    try {
      response = await page.goto(url, { waitUntil: "networkidle", timeout: 60000 });
    } catch (e) {
      report.problems.push(`page did not load: ${String(e).slice(0, 240)}`);
      return report;
    }
    report.httpStatus = response ? response.status() : null;
    if (report.httpStatus !== 200) {
      report.problems.push(`HTTP ${report.httpStatus} (expected 200)`);
      return report;
    }
    await page.waitForTimeout(2000);
    const tags = await page.evaluate(() => ({
      meta: document.querySelector('meta[name="trade-chart-build"]')?.getAttribute("content") || null,
      stamp: document.querySelector("#buildStamp")?.textContent?.trim() || null,
    }));
    report.liveTag = tags.meta;
    report.buildStamp = tags.stamp;
    if (!report.liveTag) {
      report.problems.push("no trade-chart-build meta tag found in live HTML");
      return report;
    }
    if (report.buildStamp && !report.buildStamp.includes(report.liveTag)) {
      report.problems.push(`#buildStamp ${JSON.stringify(report.buildStamp)} disagrees with meta tag ${report.liveTag}`);
    }
    if (expectedBuilds.includes(report.liveTag)) {
      // Deploy race note: live may legitimately serve HEAD~1 while a deploy
      // is in flight. That is a pass, not a failure.
      if (report.liveTag !== expectedBuilds[0]) {
        report.problems.push(`live serves previous build ${report.liveTag} (deploy in flight?) -- accepted`);
      }
    } else {
      report.problems.push(
        `live build tag ${report.liveTag} matches none of expected ${expectedBuilds.join(", ")}`
      );
      return report;
    }
    if (report.pageErrors.length) {
      report.problems.push(`${report.pageErrors.length} uncaught page error(s) on live page`);
      return report;
    }
    report.passed = true;
    return report;
  } finally {
    await browser.close();
  }
}

// Self-test discrimination: a gate that cannot fail exits 1 here. Run with
// --self-test <url> to require the gate to FAIL on a bogus expected tag.
async function selfTest(url) {
  const bogus = "tv-19700101-0000-deadbee";
  const report = await check(url, [bogus]);
  if (report.passed) {
    console.error("SELF-TEST FAILED: gate passed on a bogus expected tag");
    process.exit(1);
  }
  console.error("self-test ok: gate correctly failed on bogus expected tag");
}

const argv = process.argv.slice(2);
if (argv[0] === "--self-test") {
  const url = argv[1];
  if (!url) usage();
  await selfTest(url);
  process.exit(0);
}

const args = parseArgs(argv);
let report;
try {
  report = await check(args.url, args.expectedBuilds);
} catch (e) {
  report = {
    generatedAt: new Date().toISOString(),
    url: args.url,
    expectedBuilds: args.expectedBuilds,
    liveTag: null,
    problems: [`gate crashed: ${String(e).slice(0, 240)}`],
    passed: false,
  };
}
try {
  writeReport(args.out, report);
} catch (e) {
  console.error(`could not write report to ${args.out}: ${String(e).slice(0, 200)}`);
  process.exit(1);
}
for (const p of report.problems) console.error("problem:", p);
console.error(report.passed ? "GATE PASSED" : "GATE FAILED");
process.exit(report.passed ? 0 : 1);
