// JEG-103 regression guard: the bench-share slider must keep the Weights
// readout in sync with its own value. The slider writes through
// setBenchShareFraction(...); before the fix, the slider's input/change
// handlers called setBenchShareFraction and publishShared only, so the
// #weightsReadout caption stayed at "Bench 15.0% (default 15%)" while the
// slider's own label and the table values updated.
//
// Usage: node bench_share_readout_harness.mjs <dist-dir>
// Output JSON:
//   {
//     ok: bool,                         // all three sources match
//     storedBench: number,               // what the widget recorded (via window state)
//     sliderValue: number,              // <input type=range>.value
//     sliderLabel: string,              // .bench-share-value.textContent
//     readoutBench: number | null,      // Bench X.X% from #weightsReadout
//     readoutText: string,              // full readout text
//     mismatch: string | null,          // which assertion failed
//   }
import { chromium } from "playwright-core";
import { isMain } from "./is_main.mjs";
import { enginePageFor } from "./engine_page.mjs";
import http from "node:http";
import fs from "node:fs";
import path from "node:path";

const DIST = path.resolve(process.argv[2] || "dist");
const MIME = { ".html": "text/html", ".js": "text/javascript", ".json": "application/json",
  ".css": "text/css", ".jpg": "image/jpeg", ".png": "image/png", ".svg": "image/svg+xml" };

// Programmatic move that triggers every code path the user can hit
// (mouse drag, keyboard arrows, fill). The slider's input handler is the
// binding under test; the change handler must also repaint on commit.
async function moveSliderTo(page, value) {
  await page.evaluate(v => {
    const input = document.querySelector("#weightsBenchSlot input[type=range]");
    if (!input) throw new Error("bench-share slider not found");
    input.value = String(v);
    input.dispatchEvent(new Event("input", { bubbles: true }));
    input.dispatchEvent(new Event("change", { bubbles: true }));
  }, value);
  // Let the handler run and the DOM repaint.
  await page.waitForTimeout(120);
}

async function snapshot(page) {
  return await page.evaluate(() => {
    const input = document.querySelector("#weightsBenchSlot input[type=range]");
    const labelEl = document.querySelector("#weightsBenchSlot .bench-share-value");
    const readoutEl = document.querySelector("#weightsReadout");
    const t = (readoutEl?.textContent || "").replace(/\s+/g, " ").trim();
    const m = t.match(/Bench (\d+(?:\.\d+)?)%/);
    // The widget exposes its state via window.TradeValueCurveControls.getState().
    // If absent (older builds), storedBench falls back to null -- the slider's
    // own value is the source of truth on the input side.
    const stored = (window.TradeValueCurveControls &&
                    typeof window.TradeValueCurveControls.getState === "function")
      ? window.TradeValueCurveControls.getState().benchShare
      : null;
    return {
      sliderValue: input ? Number(input.value) : null,
      sliderLabel: labelEl ? labelEl.textContent.trim() : null,
      readoutText: t,
      readoutBench: m ? Number(m[1]) : null,
      storedBench: typeof stored === "number" ? stored : null,
    };
  });
}

function expected(value) {
  // The widget renders benchShare * 100 with one decimal (see benchSharePct).
  return Number((value * 100).toFixed(1));
}

function check(label, expectedPct, snap, mismatchSink) {
  const tol = 0.05;
  const fail = (msg) => { mismatchSink.push(`${label}: ${msg}`); };
  if (snap.sliderValue == null) return fail("slider input missing");
  const got = expected(snap.sliderValue);
  if (snap.readoutBench == null) return fail("readout 'Bench X.X%' segment missing");
  if (Math.abs(snap.readoutBench - got) > tol) {
    return fail(`readout Bench ${snap.readoutBench}% vs slider value ${snap.sliderValue} (${got}%)`);
  }
  if (snap.sliderLabel && Math.abs(parseFloat(snap.sliderLabel) - got) > tol) {
    return fail(`slider label '${snap.sliderLabel}' vs value ${got}%`);
  }
}

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

async function main() {
  const server = await serve(DIST);
  const browser = await chromium.launch({
    executablePath: process.env.CHROMIUM_PATH || undefined, args: ["--no-sandbox",
      // Hermetic (2026-10-08): no request leaves the machine; external
      // fonts made networkidle waits flaky.
      "--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1, EXCLUDE localhost"] });
  const report = { ok: true, steps: [], mismatch: null };
  try {
    const page = await browser.newPage({ viewport: { width: 1400, height: 1000 } });
    const pageErrors = [];
    page.on("pageerror", e => pageErrors.push(String(e).slice(0, 240)));
    await page.goto(`http://127.0.0.1:${server.address().port}/classic/`, { waitUntil: "networkidle" });
    await page.waitForTimeout(1500);

    const moves = [0.18, 0.10, 0.20, 0.07];
    const initial = await snapshot(page);
    report.initial = initial;
    const mismatch = [];
    check("initial", 0.15, initial, mismatch);
    for (const v of moves) {
      await moveSliderTo(page, v);
      const snap = await snapshot(page);
      const step = { target: v, ...snap };
      report.steps.push(step);
      check(`move-to-${v}`, v, snap, mismatch);
    }
    // Reset paths (Roman 2026-10-02): the caption must also follow the
    // "Reset to 15%" button and slider dblclick, which funnel through
    // setBenchShareFraction without touching the slider handlers.
    await moveSliderTo(page, 0.20);
    await page.evaluate(() => {
      const btn = document.querySelector("#weightsBenchSlot .bench-share-reset");
      if (!btn) throw new Error("bench-share reset button not found");
      btn.click();
    });
    await page.waitForTimeout(120);
    check("reset-button", 0.15, await snapshot(page), mismatch);
    await moveSliderTo(page, 0.18);
    await page.evaluate(() => {
      const input = document.querySelector("#weightsBenchSlot input[type=range]");
      if (!input) throw new Error("bench-share slider not found");
      input.dispatchEvent(new MouseEvent("dblclick", { bubbles: true }));
    });
    await page.waitForTimeout(120);
    check("slider-dblclick", 0.15, await snapshot(page), mismatch);
    if (pageErrors.length) mismatch.push(`${pageErrors.length} uncaught page error(s): ${pageErrors[0]}`);
    if (mismatch.length) {
      report.ok = false;
      report.mismatch = mismatch.join("; ");
    }
  } finally {
    await browser.close();
    server.close();
  }
  process.stdout.write(JSON.stringify(report, null, 2));
  if (!report.ok) process.exit(1);
}

if (isMain(import.meta.url)) {
  main().catch(e => { console.error(e); process.exit(2); });
}