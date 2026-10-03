// JEG-318 regression guard: the Trade QA card must surface an "Open QA findings"
// sub-row that names each open finding's OWNER LANE and links to its finding
// section. This is a sub-row of the Trade QA section, not a new card.
//
// Usage: node trade-qa-open-findings.mjs <dist-dir>
// Output JSON (stdout):
//   {
//     ok: bool,                 // all assertions pass
//     subRowPresent: bool,      // #tradeQaOpenFindings was rendered
//     subRowText: string,       // textContent of the sub-row container
//     findings: [{id, owner, linkHref}],   // parsed from the rendered HTML
//     expected: [{id, owner}],  // what the guard requires
//     mismatch: string | null,  // which assertion failed
//   }
// Exit 0 on ok=true, exit 1 otherwise. The harness runs against the built
// dist/ via a local static server.
import { chromium } from "playwright-core";
import http from "node:http";
import fs from "node:fs";
import path from "node:path";

const DIST = path.resolve(process.argv[2] || "dist");
const MIME = { ".html": "text/html", ".js": "text/javascript", ".json": "application/json",
  ".css": "text/css", ".jpg": "image/jpeg", ".png": "image/png", ".svg": "image/svg+svg" };

// What the brief requires: every open finding must appear with its owner lane named
// and a link to its finding section (qa-qaFinding-<id>). The lanes are fixed by the
// JEG-318 brief (chart-build lane for QA-004; data-pipeline lane for QA-007).
const EXPECTED = [
  { id: "QA-004", owner: "chart-build lane" },
  { id: "QA-007", owner: "data-pipeline lane" },
];

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

async function snapshot(page) {
  return await page.evaluate(() => {
    const root = document.getElementById("tradeQaOpenFindings");
    if (!root) return { present: false, text: "", items: [] };
    const text = (root.textContent || "").replace(/\s+/g, " ").trim();
    const items = Array.from(root.querySelectorAll("li")).map((li) => {
      const a = li.querySelector("a");
      const ownerSpan = Array.from(li.querySelectorAll("span")).find((s) =>
        /owner/i.test(s.textContent || "")
      );
      // Owners live in a sibling span after the "owner:" label; find by structure.
      const spans = Array.from(li.querySelectorAll("span"));
      const ownerValue = spans.length
        ? (spans[spans.length - 1].textContent || "").trim()
        : "";
      return {
        id: a ? (a.getAttribute("href") || "").replace(/^#qaFinding-/, "") : "",
        owner: ownerValue,
        linkHref: a ? a.getAttribute("href") : "",
        text: (li.textContent || "").replace(/\s+/g, " ").trim(),
      };
    });
    return { present: true, text, items };
  });
}

async function run() {
  const server = await serve(DIST);
  const browser = await chromium.launch({
    executablePath: process.env.CHROMIUM_PATH || undefined,
    args: ["--no-sandbox"],
  });
  const report = {
    subRowPresent: false,
    subRowText: "",
    findings: [],
    expected: EXPECTED,
    mismatch: null,
    ok: false,
  };
  try {
    const page = await browser.newPage({ viewport: { width: 1400, height: 1000 } });
    // The Trade QA card lives on the monitor dashboard, not the chart index.
    await page.goto(`http://127.0.0.1:${server.address().port}/modules/dashboard.html`, { waitUntil: "networkidle" });
    await page.waitForTimeout(800);
    const snap = await snapshot(page);
    report.subRowPresent = snap.present;
    report.subRowText = snap.text;
    report.findings = snap.items;

    if (!snap.present) {
      report.mismatch = "#tradeQaOpenFindings not rendered";
      return report;
    }
    const byId = Object.fromEntries(snap.items.map((i) => [i.id, i]));
    for (const exp of EXPECTED) {
      const got = byId[exp.id];
      if (!got) {
        report.mismatch = `missing finding ${exp.id} in sub-row`;
        return report;
      }
      if (!got.owner || !got.owner.toLowerCase().includes(exp.owner.toLowerCase())) {
        report.mismatch = `${exp.id} owner not named (expected '${exp.owner}', got '${got.owner}')`;
        return report;
      }
      if (!got.linkHref || !got.linkHref.startsWith(`#qaFinding-${exp.id}`)) {
        report.mismatch = `${exp.id} link does not target its finding section (got '${got.linkHref}')`;
        return report;
      }
    }
    report.ok = true;
    return report;
  } finally {
    await browser.close();
    server.close();
  }
}

run()
  .then((report) => {
    console.log(JSON.stringify(report, null, 2));
    process.exit(report.ok ? 0 : 1);
  })
  .catch((e) => {
    console.error("harness crashed:", e);
    process.exit(2);
  });