// Live-page synthetic gate (JEG-136; JEG-263 fix).
//
// Usage:
//   node live.mjs --url <url> --expected-build <tag> [--expected-build <tag2> ...] --out report.json
//
// GAP-038 (2026-10-08): after the root build-tag check, the same run renders
// every page a reader can reach: since JEG-1539 every redesigned page at the root
// (ROOT_PAGES), the old addresses that redirect (LEGACY_REDIRECTS, /v2/ included),
// /classic/ (a redirect to the root since JEG-453), and the 404 page. Each page must answer 200, carry the
// root's build tag, show its section with content, and raise no uncaught page
// error. Results land in report.pages[]; any failing page fails the run.
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
    report.pages = await checkPages(browser, url, report.liveTag);
    const badPages = report.pages.filter(p => !p.passed);
    if (badPages.length) {
      for (const p of badPages) report.problems.push(`${p.name}: ${p.problems.join("; ")}`);
      return report;
    }
    report.passed = true;
    return report;
  } finally {
    await browser.close();
  }
}

// JEG-1539: the redesigned pages at the root replace the v2 tabs (the v2 shell is no longer published). Each page
// must answer 200, carry the root's build tag, show <main> with content and raise no uncaught page error.
export const ROOT_PAGES = ["", "values.html", "learn.html", "build.html", "team.html", "explore.html", "partners.html",
  "find.html", "waivers.html", "settings.html", "ai.html", "connect.html"];
// Old addresses (chat links, bookmarks) must land on the page that does that job now (app/next/legacy-routes.js).
export const LEGACY_REDIRECTS = [
  { from: "v2/", to: "" },
  { from: "#player-values", to: "values.html" },
  { from: "v2/#find-trade", to: "find.html" },
  { from: "#compare-trade", to: "build.html" },
  { from: "#waivers", to: "waivers.html" },
  { from: "#writing/manifesto", to: "learn.html" },
  { from: "#s=AAAA", to: "connect.html" },
];

function siteRoot(url) {
  const u = new URL(url);
  u.hash = ""; u.search = "";
  if (!u.pathname.endsWith("/")) u.pathname = u.pathname.replace(/[^/]*$/, "");
  return u.toString();
}

async function loadPage(browser, url, expectedTag) {
  const result = { url, httpStatus: null, liveTag: null, pageErrors: [], problems: [] };
  const page = await browser.newPage({ viewport: { width: 1400, height: 1000 } });
  page.on("pageerror", (e) => result.pageErrors.push(String(e).slice(0, 240)));
  let response = null;
  try {
    response = await page.goto(url, { waitUntil: "networkidle", timeout: 60000 });
  } catch (e) {
    result.problems.push(`did not load: ${String(e).slice(0, 200)}`);
    return { page, result };
  }
  result.httpStatus = response ? response.status() : null;
  if (result.httpStatus !== 200) result.problems.push(`HTTP ${result.httpStatus} (expected 200)`);
  await page.waitForTimeout(2000);
  result.liveTag = await page.evaluate(() =>
    document.querySelector('meta[name="trade-chart-build"]')?.getAttribute("content") || null);
  if (result.liveTag !== expectedTag) {
    result.problems.push(`build tag ${result.liveTag} differs from the root's ${expectedTag}`);
  }
  return { page, result };
}

function finish(result) {
  if (result.pageErrors.length) result.problems.push(`${result.pageErrors.length} uncaught page error(s)`);
  result.passed = result.problems.length === 0;
  return result;
}

async function checkPages(browser, url, rootTag) {
  const base = siteRoot(url);
  const pages = [];
  for (const name of ROOT_PAGES) {
    const { page, result } = await loadPage(browser, new URL(name, base).toString(), rootTag);
    result.name = name || "root";
    if (!result.problems.length) {
      const main = await page.evaluate(() => {
        const el = document.querySelector("main");
        return { visible: !!el && el.getBoundingClientRect().height > 0, text: el ? (el.innerText || "").trim().length : 0 };
      });
      if (!main.visible) result.problems.push("<main> not visible");
      if (main.text < 40) result.problems.push(`<main> has almost no text (${main.text} chars)`);
      if (name === "values.html") {
        // A deploy where every DDF Value reads missing must fail: the Chart table needs 10+ rows with a number.
        // The DDF column (the first value column after Player), not any number: CBS columns stay priced alone.
        const valued = await page.waitForFunction(() => [...document.querySelectorAll("#rows tr")]
          .filter(tr => /^\d+(\.\d+)?/.test((tr.querySelector("td:nth-child(2)")?.textContent || "").trim())).length >= 10
          && window.DDF && DDF.engine && DDF.engine.players().filter(p => Number.isFinite(p.ddf)).length >= 10,
          null, { timeout: 30000 }).then(() => true, () => false);
        if (!valued) result.problems.push("values.html: fewer than 10 players with a DDF Value");
      }
    }
    await page.close();
    pages.push(finish(result));
  }
  for (const r of LEGACY_REDIRECTS) {
    const from = new URL(r.from, base).toString(), want = new URL(r.to, base).toString();
    const result = { name: `redirect ${r.from}`, url: from, landedAt: null, pageErrors: [], problems: [] };
    const page = await browser.newPage({ viewport: { width: 1400, height: 1000 } });
    page.on("pageerror", (e) => result.pageErrors.push(String(e).slice(0, 240)));
    const landed = (u) => { const x = new URL(String(u)); x.hash = ""; x.search = ""; return x.toString() === want; };
    try {
      await page.goto(from, { waitUntil: "commit", timeout: 60000 });
      await page.waitForURL(landed, { timeout: 20000 }).catch(() => {});
      result.landedAt = page.url();
      if (!landed(result.landedAt)) result.problems.push(`landed at ${result.landedAt} (expected ${want})`);
    } catch (e) {
      result.problems.push(`did not load: ${String(e).slice(0, 200)}`);
    }
    await page.close();
    pages.push(finish(result));
  }
  {
    // JEG-453: the old chart dashboard is retired. /classic/ must answer 200
    // and send the reader on to the root page, which must carry the root's
    // build (an old dashboard still served there fails here).
    const classicUrl = new URL("classic/", base).toString();
    const result = { name: "classic-redirect", url: classicUrl, httpStatus: null, liveTag: null,
                     landedAt: null, pageErrors: [], problems: [] };
    const page = await browser.newPage({ viewport: { width: 1400, height: 1000 } });
    page.on("pageerror", (e) => result.pageErrors.push(String(e).slice(0, 240)));
    try {
      const response = await page.goto(classicUrl, { waitUntil: "commit", timeout: 60000 });
      result.httpStatus = response ? response.status() : null;
      if (result.httpStatus !== 200) result.problems.push(`HTTP ${result.httpStatus} (expected 200)`);
      const atRoot = (u) => String(u).split("#")[0] === base;
      await page.waitForURL(atRoot, { timeout: 15000 }).catch(() => {});
      result.landedAt = page.url();
      if (!atRoot(result.landedAt)) {
        result.problems.push(`stayed at ${result.landedAt} (expected a redirect to ${base})`);
      } else {
        await page.waitForLoadState("networkidle", { timeout: 60000 }).catch(() => {});
        await page.waitForTimeout(2000);
        result.liveTag = await page.evaluate(() =>
          document.querySelector('meta[name="trade-chart-build"]')?.getAttribute("content") || null);
        if (result.liveTag !== rootTag) {
          result.problems.push(`landed on build ${result.liveTag}, not the root's ${rootTag}`);
        }
      }
    } catch (e) {
      result.problems.push(`did not load: ${String(e).slice(0, 200)}`);
    }
    await page.close();
    pages.push(finish(result));
  }
  {
    // An unknown address must answer 404 with the site's own not-found page
    // (a link back to the main page), not a GitHub default or a 200.
    const missing = new URL("ddf-synthetic-missing-page/", base).toString();
    const result = { name: "not-found", url: missing, httpStatus: null, pageErrors: [], problems: [] };
    const page = await browser.newPage();
    try {
      const response = await page.goto(missing, { waitUntil: "load", timeout: 60000 });
      result.httpStatus = response ? response.status() : null;
      if (result.httpStatus !== 404) result.problems.push(`HTTP ${result.httpStatus} (expected 404)`);
      const ok = await page.evaluate((root) => {
        const h1 = (document.querySelector("h1")?.textContent || "").trim();
        const back = [...document.querySelectorAll("a[href]")].some(a => a.href === root);
        return h1 === "Page not found" && back;
      }, base);
      if (!ok) result.problems.push("not the site's 404 page (no 'Page not found' heading linking to the main page)");
    } catch (e) {
      result.problems.push(`did not load: ${String(e).slice(0, 200)}`);
    }
    await page.close();
    pages.push(finish(result));
  }
  return pages;
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
