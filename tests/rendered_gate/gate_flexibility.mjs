// JEG-135 rendered-input sweep: the four input classes the JEG-47 gate does NOT
// cover (best-practices §6 / BH-4). For each one, change the input AWAY from its
// default with a real user gesture, then BACK, and require the comparison table
// to be byte-identical to the starting hash (BH-4: changing a setting away and
// back returns identical values; the page evaluates the REQUESTED configuration).
//
// The gate (tests/rendered_gate/gate.mjs) sweeps scoring x league size (12 shapes)
// and the DDF fixed-pie readout. It uses programmatic value movement; this harness
// uses real mouse + keyboard + real DOM events so it catches the same class of
// regressions the JEG-103 slider guard caught (input handler missing on the user
// event, not just the programmatic one).
//
//   (a) Bench share  -- real mouse drag (page.mouse.down/move/up) and real
//                     keyboard arrows (page.keyboard.press('ArrowRight')).
//                     Assert the Weights readout segment "Bench X.X%" matches
//                     the slider value at every step. Move away and back; assert
//                     the table hash is byte-identical to the starting hash.
//   (b) Roster shape -- type "3" into the RB input and "2" into the FLEX input
//                     via real keystrokes. Assert the table changes; assert
//                     away-and-back returns the original hash.
//   (c) Source toggle-- click a source checkbox off and on with a real click.
//                     Assert the checkbox state, the #legend entry count, and
//                     getState().activeSources all track the toggle. The
//                     comparison table is independent of curve toggles, so its
//                     hash must STAY at baseline (the toggle must not corrupt
//                     table state).
//   (d) Lock order   -- choose a non-default order from #curveLockOrder, then
//                     back; assert the table hash round-trips.
//
// Discrimination: the bench-share readout assertion (Bench X.X% in the Weights
// panel must equal the slider value) is the same shape as the JEG-103 guard.
// On a build where the slider's input/change handler forgets to call
// syncWeightsReadout(), the readout segment stays at the old value (e.g. 15.0)
// while the slider value is, say, 22.0 -- the assertion fails. The away-and-back
// table-hash assertion is its own discrimination: on a build that caches the
// table under a stale settings object, toggling away and back leaves a different
// hash, and the assert fails.
//
// Usage: node gate_flexibility.mjs <dist-dir>
// Output JSON: { ok: bool, steps: [...], mismatches: [...], pageErrors: [...] }
import { chromium } from "playwright-core";
import { enginePageFor } from "./engine_page.mjs";
import crypto from "node:crypto";
import http from "node:http";
import fs from "node:fs";
import path from "node:path";

const DIST = path.resolve(process.argv[2] || "dist");
const MIME = { ".html": "text/html", ".js": "text/javascript", ".json": "application/json",
  ".css": "text/css", ".jpg": "image/jpeg", ".png": "image/png", ".svg": "image/svg+xml" };

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

// The "table" is the comparison dashboard's #tableWrap .all-table. We hash the
// ordered concatenation of every cell's textContent -- this catches value drift
// AND reordering while staying independent of any per-cell style of the order.
// We deliberately hash only .row-main rows (the player values) so the
// "expanded" player detail rows don't perturb the hash when the user clicks
// a name; expand state is owned by the dashboard, not by the widget.
async function readTableHash(page) {
  return await page.evaluate(() => {
    const tbody = document.querySelector("#tableWrap table.all-table tbody");
    if (!tbody) return null;
    const parts = [];
    for (const tr of tbody.querySelectorAll("tr.row-main")) {
      for (const td of tr.querySelectorAll("td")) {
        parts.push(td.textContent.replace(/\s+/g, " ").trim());
      }
    }
    return parts.join("|");
  });
}

// GAP-FLAKY-JEG135: the dashboard re-renders asynchronously after load and
// after each input, and fixed waits (1500 ms / 150 ms) were too short when the
// machine was busy (inside `make validate`), so the baseline was sometimes
// read mid-render and every later comparison "mismatched". Read until the
// table hash is unchanged across consecutive reads, so each assertion compares
// settled tables. A table that settles at a different value (the bug these
// checks name) still fails; one that never settles is reported as null.
async function hashTable(page, { interval = 250, stableReads = 3, timeoutMs = 15000 } = {}) {
  const deadline = Date.now() + timeoutMs;
  let last = await readTableHash(page);
  let same = 1;
  while (Date.now() < deadline) {
    await page.waitForTimeout(interval);
    const next = await readTableHash(page);
    if (next !== null && next === last) {
      same += 1;
      if (same >= stableReads) return next;
    } else {
      same = 1;
      last = next;
    }
  }
  return null;
}

async function snapshotWeights(page) {
  return await page.evaluate(() => {
    const readoutEl = document.querySelector("#weightsReadout");
    const t = (readoutEl?.textContent || "").replace(/\s+/g, " ").trim();
    const m = t.match(/Bench (\d+(?:\.\d+)?)%/);
    return { readoutText: t, readoutBench: m ? Number(m[1]) : null };
  });
}

async function sharedState(page) {
  return await page.evaluate(() => window.TradeValueSharedState || null);
}

function sha256(s) {
  return crypto.createHash("sha256").update(s).digest("hex").slice(0, 16);
}

async function ensureWeightsPanelOpen(page) {
  // The bench slider lives inside a closed <details id="weightsSection">.
  // Its body is forced display:block by CSS, which leaves the layout in a
  // half-rendered state where other sections paint over the slider (a real
  // user opens the panel first). Click the summary, exactly as a user would.
  const opened = await page.evaluate(() => {
    const d = document.querySelector("#weightsSection");
    if (!d) throw new Error("weights section missing");
    if (!d.open) { d.querySelector("summary").click(); return true; }
    return false;
  });
  if (opened) await page.waitForTimeout(200);
}

async function sliderGeometry(page) {
  // Playwright's boundingBox() returns 0x0 for this input (appearance:none +
  // pointer-events:none on the input; only the ::-webkit-slider-thumb takes
  // pointer events), so read the real box via getBoundingClientRect and
  // compute the thumb center the way Chrome lays it out.
  return await page.evaluate(() => {
    const i = document.querySelector("#weightsBenchSlot input[type=range]");
    const r = i.getBoundingClientRect();
    const min = parseFloat(i.min), max = parseFloat(i.max), val = parseFloat(i.value);
    const frac = (val - min) / (max - min);
    const thumbW = 17; // matches curve-widget.css ::-webkit-slider-thumb
    return {
      x: r.x, y: r.y, w: r.width, h: r.height,
      thumbCX: r.x + thumbW / 2 + frac * (r.width - thumbW),
      value: val,
    };
  });
}

async function moveBenchViaMouse(page, fraction) {
  // True drag on the thumb: press at the thumb center, drag to the target
  // fraction of the track, release. Fires the stream of input events a real
  // user drag produces (plus change on release).
  const g = await sliderGeometry(page);
  if (!(g.w > 0)) throw new Error("bench-share slider has no layout box");
  const y = g.y + g.h / 2;
  await page.mouse.move(g.thumbCX, y);
  await page.mouse.down();
  await page.mouse.move(g.x + g.w * fraction, y, { steps: 12 });
  await page.mouse.up();
  await page.waitForTimeout(150);
}

async function moveBenchViaKeyboard(page, deltaSteps) {
  // Focus the slider then press ArrowRight/Left. Each arrow fires the input
  // handler (setBenchShareFraction + syncWeightsReadout); the final Tab
  // commits the change event too.
  await page.focus("#weightsBenchSlot input[type=range]");
  for (let i = 0; i < deltaSteps; i++) {
    if (deltaSteps > 0) await page.keyboard.press("ArrowRight");
    else await page.keyboard.press("ArrowLeft");
  }
  // Commit so the change handler fires (the JEG-103 fix path).
  await page.keyboard.press("Tab");
  await page.waitForTimeout(120);
}

async function ensureRosterPanelOpen(page) {
  // The roster inputs live inside a closed <details class="roster-shape-panel">.
  // Playwright's actionability checks treat content of a closed <details> as
  // hidden (a real user must expand it first), so click the summary open once.
  const open = await page.evaluate(() => {
    const d = document.querySelector(".roster-shape-panel");
    if (!d) throw new Error("roster-shape panel missing");
    if (!d.open) { d.querySelector("summary").click(); return true; }
    return false;
  });
  if (open) await page.waitForTimeout(150);
}

async function typeIntoRoster(page, key, newValue) {
  // Real typing path: expand the panel, focus, clear, type the number, Tab to
  // commit the change event the widget listens for.
  await ensureRosterPanelOpen(page);
  const sel = `#rosterShapeControls input[type=number][data-roster-key="${key}"]`;
  await page.focus(sel);
  await page.locator(sel).selectText();
  await page.keyboard.press("Delete");
  await page.keyboard.type(String(newValue));
  await page.keyboard.press("Tab");
  await page.waitForTimeout(150);
}

async function toggleSource(page, sourceKey, wantChecked) {
  const sel = `#sourceToggles input[type=checkbox][data-source="${sourceKey}"]`;
  const isChecked = await page.locator(sel).evaluate(el => el.checked);
  if (isChecked !== wantChecked) {
    // Click the wrapping <label> (the input itself is small/hidden in CSS);
    // user.toggle() performs a real click on the rendered control.
    await page.locator(sel).click({ force: true });
    await page.waitForTimeout(120);
  }
  return await page.locator(sel).evaluate(el => el.checked);
}

// NOTE (Roman, review 2026-10-02): #sourceCards exists NOWHERE in the served
// page -- comparison-dashboard.js renderSourceCards() always no-ops
// (`if (!container) return`). The source-card label is therefore not an
// observable surface on this page; the toggle checkbox, the #legend entries,
// and getState().activeSources are. If the cards are meant to render, that's
// a separate product defect; the dead function should otherwise be removed.
async function topOrdering(page) {
  return await page.evaluate(() => {
    const rows = [...document.querySelectorAll("#tableWrap table.all-table tbody tr.row-main")];
    return rows.slice(0, 5).map(r => r.dataset.playerKey).join(",");
  });
}

async function legendState(page) {
  // The #legend div holds one <span> per ACTIVE curve source; the widget also
  // exposes the active set via getState().activeSources. Both must track the
  // toggle. (The comparison TABLE is intentionally independent of curve
  // toggles -- comparison-dashboard.js never reads activeSources -- so the
  // table hash must stay put, not change.)
  return await page.evaluate(() => {
    const legend = document.querySelectorAll("#legend > span").length;
    const st = (window.TradeValueCurveControls &&
                typeof window.TradeValueCurveControls.getState === "function")
      ? window.TradeValueCurveControls.getState().activeSources : null;
    return { legendCount: legend, activeSources: st };
  });
}

async function chooseLockOrder(page, value) {
  await page.selectOption("#curveLockOrder", value);
  await page.waitForTimeout(120);
}

async function currentBenchFraction(page) {
  return await page.evaluate(() => Number(document.querySelector("#weightsBenchSlot input[type=range]").value));
}

function expectClose(label, got, want, tol, sink) {
  if (got == null || Math.abs(got - want) > tol) {
    sink.push(`${label}: got ${got}, want ~${want} (tol ${tol})`);
  }
}

function expectChanged(label, before, after, sink) {
  // Guards against vacuous gestures: if the control never moved, the
  // follow-on assertions would pass trivially. Fail loudly instead.
  if (before === after) {
    sink.push(`${label}: control did not move (before=${before} after=${after}) -- gesture missed`);
  }
}

async function main() {
  const server = await serve(DIST);
  const browser = await chromium.launch({
    executablePath: process.env.CHROMIUM_PATH || undefined, args: ["--no-sandbox",
      // Hermetic (2026-10-08): no request leaves the machine; external
      // fonts made networkidle waits flaky.
      "--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1, EXCLUDE localhost"] });
  const report = { ok: true, steps: [], mismatches: [], pageErrors: [] };
  try {
    const page = await browser.newPage({ viewport: { width: 1400, height: 1000 } });
    page.on("pageerror", e => report.pageErrors.push(String(e).slice(0, 240)));
    await page.goto(`http://127.0.0.1:${server.address().port}/classic/`, { waitUntil: "networkidle" });
    await page.waitForTimeout(1500);

    // ---- Baseline table hash + readout (JEG-103 default is 15.0%) ----
    // Baseline needs a longer quiet window than the per-step reads: late async
    // loads after first paint (registry, adjustment inputs) re-render the table
    // once more, and a baseline taken before that made every later step
    // "mismatch" (GAP-FLAKY-JEG135 recurrence, 2026-10-07).
    await page.waitForLoadState("networkidle");
    const baselineHash = await hashTable(page, { stableReads: 8, timeoutMs: 30000 });
    const baselineWeights = await snapshotWeights(page);
    const baselineState = await sharedState(page);
    report.baseline = {
      tableHash: baselineHash ? sha256(baselineHash) : null,
      tableLen: baselineHash ? baselineHash.split("|").length : 0,
      ...baselineWeights,
      sharedState: baselineState,
    };
    if (!baselineHash) report.mismatches.push("baseline: comparison table not rendered");

    // ===== (a) Bench share: real mouse + real keyboard =====
    // Open the weights panel first (see ensureWeightsPanelOpen).
    await ensureWeightsPanelOpen(page);
    const benchBefore = await currentBenchFraction(page);
    // Mouse drag: thumb -> 70% of the track.
    await moveBenchViaMouse(page, 0.7);
    const afterMouse = await snapshotWeights(page);
    const mouseFraction = await currentBenchFraction(page);
    report.steps.push({ phase: "bench-mouse", fraction: mouseFraction, ...afterMouse });
    expectChanged("bench-mouse gesture", benchBefore, mouseFraction, report.mismatches);
    expectClose("bench-mouse readout", afterMouse.readoutBench, mouseFraction * 100, 0.05, report.mismatches);

    // Keyboard arrows: 2 right from current value.
    await moveBenchViaKeyboard(page, 2);
    const afterKey = await snapshotWeights(page);
    const keyFraction = await currentBenchFraction(page);
    report.steps.push({ phase: "bench-keyboard", fraction: keyFraction, ...afterKey });
    expectChanged("bench-keyboard gesture", mouseFraction, keyFraction, report.mismatches);
    expectClose("bench-keyboard readout", afterKey.readoutBench, keyFraction * 100, 0.05, report.mismatches);

    // Back to default via the published "Reset to 15%" button (the same path
    // an away-and-back round-trip takes when the user re-enters the default).
    await page.evaluate(() => {
      const btn = document.querySelector("#weightsBenchSlot .bench-share-reset");
      if (!btn) throw new Error("bench-share reset button not found");
      btn.click();
    });
    await page.waitForTimeout(150);
    const afterBenchReturn = await snapshotWeights(page);
    const benchReturnFraction = await currentBenchFraction(page);
    const hashAfterBenchReturn = await hashTable(page);
    report.steps.push({
      phase: "bench-return", fraction: benchReturnFraction,
      readoutBench: afterBenchReturn.readoutBench,
      tableHash: hashAfterBenchReturn ? sha256(hashAfterBenchReturn) : null,
    });
    expectClose("bench-return readout", afterBenchReturn.readoutBench, 15.0, 0.05, report.mismatches);
    if (!baselineHash || !hashAfterBenchReturn || sha256(hashAfterBenchReturn) !== report.baseline.tableHash) {
      report.mismatches.push("bench-return: table hash does not match baseline");
    }

    // ===== (b) Roster shape: real typing =====
    // Default in curve-widget.js: {QB:1,RB:2,WR:2,TE:1,FLEX:1,BENCH:6,K:1,DST:1}.
    await typeIntoRoster(page, "RB", 3);
    const afterRbUp = await sharedState(page);
    const hashAfterRbUp = await hashTable(page);
    report.steps.push({
      phase: "roster-rb-up", roster: afterRbUp?.rosterShape,
      tableHash: hashAfterRbUp ? sha256(hashAfterRbUp) : null,
    });
    if (!hashAfterRbUp || sha256(hashAfterRbUp) === report.baseline.tableHash) {
      report.mismatches.push("roster RB 2->3 did not change the table");
    }

    await typeIntoRoster(page, "FLEX", 2);
    const afterFlexUp = await sharedState(page);
    const hashAfterFlexUp = await hashTable(page);
    report.steps.push({
      phase: "roster-flex-up", roster: afterFlexUp?.rosterShape,
      tableHash: hashAfterFlexUp ? sha256(hashAfterFlexUp) : null,
    });
    if (!hashAfterFlexUp || sha256(hashAfterFlexUp) === sha256(hashAfterRbUp)) {
      report.mismatches.push("roster FLEX 1->2 did not change the table vs RB-only step");
    }

    // Back to default: RB 2, FLEX 1.
    await typeIntoRoster(page, "RB", 2);
    await typeIntoRoster(page, "FLEX", 1);
    const hashAfterRosterReturn = await hashTable(page);
    const afterRosterReturn = await sharedState(page);
    report.steps.push({
      phase: "roster-return", roster: afterRosterReturn?.rosterShape,
      tableHash: hashAfterRosterReturn ? sha256(hashAfterRosterReturn) : null,
    });
    if (!hashAfterRosterReturn || sha256(hashAfterRosterReturn) !== report.baseline.tableHash) {
      report.mismatches.push("roster-return: table hash does not match baseline");
    }

    // ===== (c) Source toggle =====
    // Pick the first non-default checkbox -- the one that is currently CHECKED.
    const firstChecked = await page.evaluate(() => {
      const inputs = [...document.querySelectorAll('#sourceToggles input[type=checkbox][data-source]')];
      const target = inputs.find(i => i.checked && !i.disabled);
      return target ? target.dataset.source : null;
    });
    if (!firstChecked) {
      report.mismatches.push("source-toggle: no available checked source to toggle");
    } else {
      // The toggle drives CURVES, not the comparison table (the table never
      // reads activeSources -- verified in comparison-dashboard.js). So the
      // correct contract is: checkbox + #legend + getState().activeSources
      // track the toggle, and the table hash STAYS at baseline throughout.
      const legendBefore = await legendState(page);
      const checkedAfterOff = await toggleSource(page, firstChecked, false);
      const legendAfterOff = await legendState(page);
      const hashAfterToggleOff = await hashTable(page);
      report.steps.push({
        phase: "source-off", source: firstChecked,
        checkboxChecked: checkedAfterOff,
        legendBefore: legendBefore.legendCount, legendAfterOff: legendAfterOff.legendCount,
        activeSourcesAfterOff: legendAfterOff.activeSources,
        tableHash: hashAfterToggleOff ? sha256(hashAfterToggleOff) : null,
      });
      if (checkedAfterOff !== false) {
        report.mismatches.push(`source-off (${firstChecked}): checkbox did not uncheck`);
      }
      if (legendAfterOff.legendCount !== legendBefore.legendCount - 1) {
        report.mismatches.push(`source-off (${firstChecked}): legend entries ${legendBefore.legendCount} -> ${legendAfterOff.legendCount}, want -1`);
      }
      if (legendAfterOff.activeSources && legendAfterOff.activeSources.includes(firstChecked)) {
        report.mismatches.push(`source-off (${firstChecked}): still in getState().activeSources`);
      }
      if (!hashAfterToggleOff || sha256(hashAfterToggleOff) !== report.baseline.tableHash) {
        report.mismatches.push(`source-off (${firstChecked}): table hash moved (toggles must not touch the table)`);
      }
      const checkedAfterOn = await toggleSource(page, firstChecked, true);
      const legendAfterOn = await legendState(page);
      const hashAfterToggleOn = await hashTable(page);
      report.steps.push({
        phase: "source-on", source: firstChecked,
        checkboxChecked: checkedAfterOn,
        legendAfterOn: legendAfterOn.legendCount,
        activeSourcesAfterOn: legendAfterOn.activeSources,
        tableHash: hashAfterToggleOn ? sha256(hashAfterToggleOn) : null,
      });
      if (checkedAfterOn !== true) {
        report.mismatches.push(`source-on (${firstChecked}): checkbox did not re-check`);
      }
      if (legendAfterOn.legendCount !== legendBefore.legendCount) {
        report.mismatches.push(`source-on (${firstChecked}): legend entries ${legendAfterOn.legendCount}, want baseline ${legendBefore.legendCount}`);
      }
      if (legendAfterOn.activeSources && !legendAfterOn.activeSources.includes(firstChecked)) {
        report.mismatches.push(`source-on (${firstChecked}): missing from getState().activeSources`);
      }
      if (!hashAfterToggleOn || sha256(hashAfterToggleOn) !== report.baseline.tableHash) {
        report.mismatches.push(`source-toggle return: table hash does not match baseline (${firstChecked})`);
      }
    }

    // ===== (d) Lock order =====
    // Read all lock options; pick any that is not the current value.
    const lockOptions = await page.evaluate(() => {
      const sel = document.querySelector("#curveLockOrder");
      if (!sel) return [];
      return [...sel.querySelectorAll("option")].map(o => o.value);
    });
    const currentLock = await page.evaluate(() => document.querySelector("#curveLockOrder")?.value);
    const altLock = lockOptions.find(v => v && v !== currentLock);
    if (!altLock) {
      report.mismatches.push("lock-order: no alternate value available");
    } else {
      // Capture the true baseline ordering BEFORE mutating (Roman, review
      // 2026-10-02: the worker's version captured it post-mutation, which
      // proved nothing).
      const orderingBefore = await topOrdering(page);
      await chooseLockOrder(page, altLock);
      const hashAfterLock = await hashTable(page);
      const orderingAfter = await topOrdering(page);
      report.steps.push({
        phase: "lock-change", from: currentLock, to: altLock,
        tableHash: hashAfterLock ? sha256(hashAfterLock) : null,
        orderingBefore, orderingAfterLock: orderingAfter,
      });

      await chooseLockOrder(page, currentLock);
      const hashAfterLockReturn = await hashTable(page);
      report.steps.push({
        phase: "lock-return", to: currentLock,
        tableHash: hashAfterLockReturn ? sha256(hashAfterLockReturn) : null,
      });
      if (!hashAfterLockReturn || sha256(hashAfterLockReturn) !== report.baseline.tableHash) {
        report.mismatches.push("lock-return: table hash does not match baseline");
      }
    }

    if (report.pageErrors.length) {
      report.mismatches.push(`${report.pageErrors.length} uncaught page error(s): ${report.pageErrors[0]}`);
    }
    report.ok = report.mismatches.length === 0;
  } finally {
    await browser.close();
    server.close();
  }
  process.stdout.write(JSON.stringify(report, null, 2));
  if (!report.ok) process.exit(1);
}

if (import.meta.url === `file://${process.argv[1]}`) {
  main().catch(e => { console.error(e); process.exit(2); });
}