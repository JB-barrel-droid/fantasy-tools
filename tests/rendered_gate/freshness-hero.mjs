// JEG-310 regression guard: the dashboard hero must show a freshness
// indicator colored by the age of pipeline-checkpoints.json's generated_at.
// Synthetic inputs prove each branch:
//   *  5 min ago  -> default color (var(--dim))
//   * 90 min ago  -> amber    (var(--yellow))
//   * 150 min ago -> red      (var(--red))
//
// Usage: node freshness-hero.mjs <dist-dir>
// Output JSON (process exit 1 on failure):
//   {
//     ok: bool,
//     cases: [{name, ageMin, expected, colorSlot, gotText, gotColorHex,
//              colorSlot, mismatch}],
//     mismatches: string[]
//   }
import { chromium } from "playwright-core";
import http from "node:http";
import fs from "node:fs";
import path from "node:path";
import os from "node:os";

const DIST = path.resolve(process.argv[2] || "dist");
const MIME = {
  ".html": "text/html", ".js": "text/javascript", ".json": "application/json",
  ".css": "text/css", ".jpg": "image/jpeg", ".png": "image/png", ".svg": "image/svg+xml",
};

// CSS variable -> expected hex (computed at test-time, see resolveColorHex()).
// The slot is what we compare against; the hex is reported for transparency.
const SLOTS = {
  "--dim":    { hex: null },  // resolved at runtime from the live page
  "--yellow": { hex: null },
  "--red":    { hex: null },
  "--grey":   { hex: null },
};

function makeSynthetic(generatedAtIso) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "freshness-hero-"));
  const cpPath = path.join(dir, "pipeline-checkpoints.json");
  // Minimal but valid: matches schema: "pipeline-checkpoints-v1" and the
  // shape main() expects (sources object is non-empty so we don't bail early).
  const data = {
    schema: "pipeline-checkpoints-v1",
    generated_at: generatedAtIso,
    nfl_week: 4,
    sources: { espn: { status: "ok" } },
    checkpoints: [],
  };
  fs.writeFileSync(cpPath, JSON.stringify(data));
  return { dir, cpPath };
}

// Serve dist/ but rewrite any path that ends in pipeline-checkpoints.json
// (or /output/pipeline-checkpoints.json) to the synthetic file. This avoids
// touching dist/ on disk.
function makeServer(syntheticCpPath) {
  return new Promise((resolve) => {
    const server = http.createServer((req, res) => {
      const rel = decodeURIComponent(new URL(req.url, "http://x").pathname);
      const isCpReq = /(^|\/)pipeline-checkpoints\.json$/.test(rel);
      let file = isCpReq ? syntheticCpPath : path.join(DIST, rel);
      if (!file.startsWith(DIST) && file !== syntheticCpPath) {
        res.writeHead(404).end("not found");
        return;
      }
      if (!fs.existsSync(file) || fs.statSync(file).isDirectory()) {
        res.writeHead(404).end("not found");
        return;
      }
      res.writeHead(200, {
        "content-type": MIME[path.extname(file)] || "application/octet-stream",
      });
      fs.createReadStream(file).pipe(res);
    });
    server.listen(0, "127.0.0.1", () => resolve(server));
  });
}

// Resolve the live computed RGB for each CSS variable the dashboard defines,
// so the test compares like-for-like without hard-coding brand hex values.
async function resolveSlotColors(page) {
  return await page.evaluate(() => {
    function rgbOf(name) {
      const probe = document.createElement("span");
      probe.style.color = `var(${name})`;
      document.body.appendChild(probe);
      const c = getComputedStyle(probe).color;
      probe.remove();
      return c;
    }
    return {
      "--dim": rgbOf("--dim"),
      "--yellow": rgbOf("--yellow"),
      "--red": rgbOf("--red"),
      "--grey": rgbOf("--grey"),
    };
  });
}

function closestSlot(rgb, slotRgb) {
  // Both rgb strings are computed-style 'rgb(R G,B)'. We pick exact match
  // first; if none, find the nearest by sum-of-squares.
  const parsed = (s) => {
    const m = s.match(/rgba?\(([^)]+)\)/);
    if (!m) return null;
    const parts = m[1].split(",").map(p => Number(p.trim()));
    return parts.slice(0, 3);
  };
  const a = parsed(rgb);
  if (!a) return null;
  let best = null, bestDist = Infinity;
  for (const [name, hex] of Object.entries(slotRgb)) {
    const b = parsed(hex);
    if (!b) continue;
    if (a[0] === b[0] && a[1] === b[1] && a[2] === b[2]) return name;
    const d = (a[0]-b[0])**2 + (a[1]-b[1])**2 + (a[2]-b[2])**2;
    if (d < bestDist) { bestDist = d; best = name; }
  }
  // rgb match must be tight enough (within ~4/channel). Otherwise we may be
  // resolving against a different rule.
  return bestDist <= 16 ? best : null;
}

async function runCase(browser, name, ageMin, expectedSlot, slotRgb) {
  const generatedAt = new Date(Date.now() - ageMin * 60_000).toISOString();
  const { dir, cpPath } = makeSynthetic(generatedAt);
  const server = await makeServer(cpPath);
  const page = await browser.newPage({ viewport: { width: 1400, height: 1000 } });
  const pageErrors = [];
  page.on("pageerror", (e) => pageErrors.push(String(e).slice(0, 240)));
  let report = { name, ageMin, expected: expectedSlot };
  try {
    await page.goto(`http://127.0.0.1:${server.address().port}/modules/dashboard.html`,
                    { waitUntil: "networkidle" });
    // Wait for the inline freshness script to populate the text span.
    await page.waitForFunction(() => {
      const t = document.getElementById("monitorFreshnessText");
      return t && t.textContent && t.textContent !== "…" &&
             t.textContent !== "unavailable";
    }, { timeout: 5000 }).catch(() => {});
    const snap = await page.evaluate(() => {
      const wrap = document.getElementById("monitorFreshness");
      const t = document.getElementById("monitorFreshnessText");
      return {
        wrapText: wrap ? wrap.textContent.replace(/\s+/g, " ").trim() : null,
        text: t ? t.textContent.trim() : null,
        color: t ? getComputedStyle(t).color : null,
      };
    });
    const slot = closestSlot(snap.color, slotRgb);
    report = { ...report, ...snap, colorSlot: slot };
    const mismatch = [];
    if (!snap.text) mismatch.push("monitorFreshnessText not populated");
    if (slot !== expectedSlot) {
      mismatch.push(`expected slot ${expectedSlot} for age ${ageMin}m, got ${slot} (${snap.color})`);
    }
    if (!/monitor last refreshed/i.test(snap.wrapText || "")) {
      mismatch.push(`hero copy missing 'Monitor last refreshed' prefix (got: ${JSON.stringify(snap.wrapText)})`);
    }
    if (pageErrors.length) mismatch.push(`${pageErrors.length} page error(s): ${pageErrors[0]}`);
    report.mismatch = mismatch.length ? mismatch.join("; ") : null;
  } finally {
    await page.close();
    server.close();
    try { fs.rmSync(dir, { recursive: true, force: true }); } catch {}
  }
  return report;
}

async function main() {
  if (!fs.existsSync(path.join(DIST, "modules/dashboard.html"))) {
    console.error(`dashboard.html not found under ${DIST}`);
    process.exit(2);
  }
  const browser = await chromium.launch({
    executablePath: process.env.CHROMIUM_PATH || undefined,
    args: ["--no-sandbox"],
  });
  const report = { ok: true, cases: [], mismatches: [] };
  try {
    // Use a throwaway page to resolve CSS variable colors on the live page.
    const setupPage = await browser.newPage({ viewport: { width: 1400, height: 1000 } });
    await setupPage.goto(`file://${path.join(DIST, "modules/dashboard.html")}`);
    // file:// fetch won't work; we just need the stylesheet to load so the
    // :root variables are defined.
    await setupPage.waitForFunction(() =>
      getComputedStyle(document.documentElement).getPropertyValue("--dim").length > 0,
      { timeout: 5000 },
    ).catch(() => {});
    const slotRgb = await resolveSlotColors(setupPage);
    await setupPage.close();

    const cases = [
      { name: "fresh", ageMin: 5,   expected: "--dim" },
      { name: "amber", ageMin: 90,  expected: "--yellow" },
      { name: "red",   ageMin: 150, expected: "--red" },
    ];
    for (const c of cases) {
      const r = await runCase(browser, c.name, c.ageMin, c.expected, slotRgb);
      report.cases.push(r);
      if (r.mismatch) report.mismatches.push(`${c.name}: ${r.mismatch}`);
    }
    report.ok = report.mismatches.length === 0;
  } finally {
    await browser.close();
  }
  process.stdout.write(JSON.stringify(report, null, 2));
  if (!report.ok) process.exit(1);
}

if (import.meta.url === `file://${process.argv[1]}`) {
  main().catch((e) => { console.error(e); process.exit(2); });
}