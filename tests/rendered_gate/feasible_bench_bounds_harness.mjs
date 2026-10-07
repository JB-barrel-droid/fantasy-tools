// JEG-432 R2 guard: the chart's bench controls clamp to the feasible-bench
// rule (ValueModel.feasibleBenchBounds), not to fixed ranges.
//
// Usage: node feasible_bench_bounds_harness.mjs <dist-dir>
// Checks, on the built page:
//   share-bounds   the bench-share slider's min/max equal the rule's bounds;
//   share-clamp    asking for 0.1% lands on the rule's min, and the live
//                  calibration there withholds NO position (the old fixed 1%
//                  floor withheld QB -- the defect this rule fixes);
//   slots-bounds   the Bench stepper's min/max equal the rule's bench range;
//   slots-clamp    at 14 teams, typing 14 into the stepper lands on the max;
//   slots-league   bench 13 at 12 teams, then switching to 14 teams, pulls
//                  the bench back to the 14-team max;
//   slots-blocked  5 quarterback slots at 12 teams (60 starters, more than
//                  the projected quarterbacks): the Bench stepper is disabled
//                  and blank, a one-line reason names quarterbacks in plain
//                  words (no "QB"/"VORP"), typing into it changes nothing, and
//                  going back to 1 quarterback re-enables it with a number
//                  (decision feasible-bench-001);
//   no page errors.
// Prints a JSON report; exits 1 when any check fails.
import { chromium } from "playwright-core";
import http from "node:http";
import fs from "node:fs";
import path from "node:path";

const DIST = path.resolve(process.argv[2] || "dist");
const MIME = { ".html": "text/html", ".js": "text/javascript", ".json": "application/json",
  ".css": "text/css", ".jpg": "image/jpeg", ".png": "image/png", ".svg": "image/svg+xml" };

function serve(dir) {
  const server = http.createServer((req, res) => {
    const rel = decodeURIComponent(new URL(req.url, "http://x").pathname);
    const file = path.join(dir, rel.endsWith("/") ? rel + "index.html" : rel);
    if (!file.startsWith(dir) || !fs.existsSync(file) || fs.statSync(file).isDirectory()) {
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
    executablePath: process.env.CHROMIUM_PATH || undefined, args: ["--no-sandbox"] });
  const report = { ok: true, checks: {}, mismatches: [] };
  const fail = (name, msg) => { report.mismatches.push(`${name}: ${msg}`); };
  try {
    const page = await browser.newPage({ viewport: { width: 1400, height: 1000 } });
    const pageErrors = [];
    page.on("pageerror", e => pageErrors.push(String(e).slice(0, 240)));
    await page.goto(`http://127.0.0.1:${server.address().port}/`, { waitUntil: "networkidle" });
    await page.waitForFunction(() => window.TradeValueTwoTierLive && window.TradeValueTwoTierLive.feasibleBench,
      null, { timeout: 30000 });

    // share-bounds
    const share = await page.evaluate(() => {
      const L = window.TradeValueTwoTierLive;
      const f = L.feasibleBench();
      const input = document.querySelector("#benchShareBlock input[type=range]");
      return { rule: f && f.benchShare, bounds: L.bounds(),
        inputMin: input ? Number(input.min) : null, inputMax: input ? Number(input.max) : null };
    });
    report.checks.shareBounds = share;
    if (!share.rule) fail("share-bounds", "rule returned no bench-share bounds");
    else if (share.inputMin !== share.rule.min || share.inputMax !== share.rule.max)
      fail("share-bounds", `slider ${share.inputMin}-${share.inputMax} vs rule ${share.rule.min}-${share.rule.max}`);

    // share-clamp
    const clamp = await page.evaluate(() => {
      const L = window.TradeValueTwoTierLive;
      L.setBenchShareFraction(0.001, false);
      const s = window.TradeValueCurveControls.getState().benchShare;
      const cal = L.calibration(s);
      const withheld = Object.keys(cal).filter(p => !cal[p] || cal[p].invalid);
      L.setBenchShareFraction(0.15, false);
      return { landed: s, withheld };
    });
    report.checks.shareClamp = clamp;
    if (share.rule && clamp.landed !== share.rule.min)
      fail("share-clamp", `0.001 landed on ${clamp.landed}, rule min ${share.rule.min}`);
    if (clamp.withheld.length) fail("share-clamp", `withheld at the slider floor: ${clamp.withheld.join(",")}`);

    // slots-bounds
    const slots = await page.evaluate(() => {
      const L = window.TradeValueTwoTierLive;
      const b = L.benchSlotBounds();
      const input = document.querySelector('input[data-roster-key="BENCH"]');
      return { rule: b, inputMin: input ? Number(input.min) : null, inputMax: input ? Number(input.max) : null };
    });
    report.checks.slotsBounds = slots;
    if (!slots.rule) fail("slots-bounds", "rule returned no bench-slot bounds");
    else if (slots.inputMin !== slots.rule.min || slots.inputMax !== slots.rule.max)
      fail("slots-bounds", `stepper ${slots.inputMin}-${slots.inputMax} vs rule ${slots.rule.min}-${slots.rule.max}`);

    // slots-clamp (14 teams, type 14 into the stepper)
    const typed = await page.evaluate(() => {
      const L = window.TradeValueTwoTierLive;
      window.TradeValueCurveControls.setTeams(14);
      const input = document.querySelector('input[data-roster-key="BENCH"]');
      input.value = "14";
      input.dispatchEvent(new Event("change", { bubbles: true }));
      return { bench: L.rosterShape().BENCH, rule: L.benchSlotBounds() };
    });
    report.checks.slotsClamp = typed;
    if (!typed.rule || typed.rule.max >= 14) fail("slots-clamp", `14-team rule max ${typed.rule && typed.rule.max} should be < 14 on committed data`);
    else if (typed.bench !== typed.rule.max) fail("slots-clamp", `typed 14 -> bench ${typed.bench}, rule max ${typed.rule.max}`);

    // slots-league (bench 13 at 12 teams, then 14 teams)
    const league = await page.evaluate(() => {
      const L = window.TradeValueTwoTierLive;
      window.TradeValueCurveControls.setTeams(12);
      L.setRosterSpot("BENCH", 13, false);
      const at12 = L.rosterShape().BENCH;
      window.TradeValueCurveControls.setTeams(14);
      const at14 = L.rosterShape().BENCH;
      const rule = L.benchSlotBounds();
      const input = document.querySelector('input[data-roster-key="BENCH"]');
      const shown = input ? Number(input.value) : null;
      L.setRosterSpot("BENCH", 6, false);
      window.TradeValueCurveControls.setTeams(12);
      return { at12, at14, rule, shown };
    });
    report.checks.slotsLeague = league;
    if (league.at12 !== 13) fail("slots-league", `could not set bench 13 at 12 teams (got ${league.at12})`);
    if (!league.rule || league.at14 !== league.rule.max || league.shown !== league.rule.max)
      fail("slots-league", `after 14 teams bench=${league.at14} shown=${league.shown}, rule max ${league.rule && league.rule.max}`);

    // slots-blocked (5 QB slots at 12 teams -> no feasible bench size)
    const blocked = await page.evaluate(() => {
      const L = window.TradeValueTwoTierLive;
      window.TradeValueCurveControls.setTeams(12);
      const before = L.rosterShape().BENCH;
      L.setRosterSpot("QB", 5, false);
      const rule = L.benchSlotBounds();
      const input = document.querySelector('input[data-roster-key="BENCH"]');
      const note = document.getElementById("benchStepperBlocked");
      const state = { rule, disabled: input ? input.disabled : null, value: input ? input.value : null,
        note: note ? note.textContent : null };
      L.setRosterSpot("BENCH", 3, false);
      state.afterType = L.rosterShape().BENCH;
      state.before = before;
      L.setRosterSpot("QB", 1, false);
      const back = document.querySelector('input[data-roster-key="BENCH"]');
      state.restored = { disabled: back ? back.disabled : null, value: back ? back.value : null,
        note: !!document.getElementById("benchStepperBlocked") };
      return state;
    });
    report.checks.slotsBlocked = blocked;
    if (!blocked.rule || !blocked.rule.blocked) fail("slots-blocked", `rule not blocked at 5 QB / 12 teams: ${JSON.stringify(blocked.rule)}`);
    if (blocked.disabled !== true) fail("slots-blocked", `stepper not disabled (disabled=${blocked.disabled})`);
    if (blocked.value !== "") fail("slots-blocked", `disabled stepper shows a number: "${blocked.value}"`);
    if (!blocked.note || !/quarterbacks/.test(blocked.note) || /\bQB\b|VORP/.test(blocked.note) || /\n/.test(blocked.note))
      fail("slots-blocked", `reason line missing or not plain words: ${JSON.stringify(blocked.note)}`);
    if (blocked.afterType !== blocked.before) fail("slots-blocked", `typing into the disabled stepper moved bench ${blocked.before} -> ${blocked.afterType}`);
    if (blocked.restored.disabled !== false || blocked.restored.value === "" || blocked.restored.note)
      fail("slots-blocked", `stepper not restored after 1 QB: ${JSON.stringify(blocked.restored)}`);

    if (pageErrors.length) fail("page", `${pageErrors.length} uncaught page error(s): ${pageErrors[0]}`);
  } finally {
    await browser.close();
    server.close();
  }
  report.ok = report.mismatches.length === 0;
  process.stdout.write(JSON.stringify(report, null, 2));
  if (!report.ok) process.exit(1);
}

if (import.meta.url === `file://${process.argv[1]}`) {
  main().catch(e => { console.error(e); process.exit(2); });
}
