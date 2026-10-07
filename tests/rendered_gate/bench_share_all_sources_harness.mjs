// Decision feasible-bench-003 guard: no position is withheld for ANY
// two-tier source at ANY 0.001 step of the bench-share slider, in all 12
// league setups (3 scorings x 8/10/12/14 teams).
//
// Usage: node bench_share_all_sources_harness.mjs <dist-dir>
// The slider range is bounded on the ESPN pool (feasible-bench/1). CBS ROS
// and Razzball calibrate their OWN projection pools with the same share, so
// near the floor they used to withhold positions (blank curve segments).
// They now step to their nearest feasible share. Checks, on the built page:
//   espn       TradeValueTwoTierLive.calibration(s) withholds nothing;
//   sources    ddfTwoTierValuesForSource(cbsros|razzball, s) has no
//              invalidPositions and a calibration for all four positions;
//   note       with CBS ROS and Razzball shown at a share where one of them
//              steps, the chart status carries the plain-language note
//              (positions spelled out, no "QB"/"RB"/"WR"/"TE"/"VORP"), and
//              it disappears at a share where nothing steps;
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
    await page.waitForFunction(() => window.TradeValueCurveHarness && window.TradeValueTwoTierLive
      && window.TradeValueCurveHarness.ddfTwoTierValuesForSource, null, { timeout: 30000 });

    const sweep = await page.evaluate(() => {
      const C = window.TradeValueCurveControls, L = window.TradeValueTwoTierLive, H = window.TradeValueCurveHarness;
      const combos = [];
      for (const sc of ["standard", "half", "full"]) for (const t of [8, 10, 12, 14]) {
        C.setScoring(sc); C.setTeams(t);
        const b = L.bounds();
        const row = { scoring: sc, teams: t, bounds: b, steps: 0, withheld: [], stepped: 0 };
        if (!b) { row.withheld.push("no slider bounds"); combos.push(row); continue; }
        for (let m = Math.round(b[0] * 1000); m <= Math.round(b[1] * 1000); m += 1) {
          const s = m / 1000;
          row.steps += 1;
          const cal = L.calibration(s);
          ["QB", "RB", "WR", "TE"].forEach(p => { if (!cal[p] || cal[p].invalid) row.withheld.push(`${s}:espn:${p}`); });
          for (const key of ["cbsros", "razzball"]) {
            const v = H.ddfTwoTierValuesForSource(key, s);
            if (!v) { row.withheld.push(`${s}:${key}:unavailable`); continue; }
            const bad = ["QB", "RB", "WR", "TE"].filter(p => (v.invalidPositions && v.invalidPositions.has(p)) || !v.calibration[p]);
            bad.forEach(p => row.withheld.push(`${s}:${key}:${p}`));
            if (["QB", "RB", "WR", "TE"].some(p => v.calibration[p] && v.calibration[p].stepped === "up")) row.stepped += 1;
          }
        }
        combos.push(row);
      }
      C.setScoring("full"); C.setTeams(12);
      return combos;
    });
    report.checks.sweep = sweep.map(r => ({ ...r, withheld: r.withheld.length, first: r.withheld.slice(0, 4) }));
    const bad = sweep.filter(r => r.withheld.length);
    if (sweep.length !== 12) fail("sources", `swept ${sweep.length} setups, expected 12`);
    bad.forEach(r => fail("sources", `${r.scoring}/${r.teams}: ${r.withheld.length} withheld, e.g. ${r.withheld.slice(0, 3).join(", ")}`));

    // note: 8 teams, half PPR, CBS ROS + Razzball shown, slider at its floor.
    const note = await page.evaluate(async () => {
      const C = window.TradeValueCurveControls, L = window.TradeValueTwoTierLive, H = window.TradeValueCurveHarness;
      C.setScoring("half"); C.setTeams(8);
      for (const key of ["cbsros", "razzball"]) {
        const box = document.querySelector(`input[type=checkbox][data-source-key="${key}"]`)
          || [...document.querySelectorAll("input[type=checkbox]")].find(i => i.value === key || i.dataset.source === key);
        if (box && !box.checked) { box.checked = true; box.dispatchEvent(new Event("change", { bubbles: true })); }
      }
      const [lo] = L.bounds();
      L.setBenchShareFraction(lo, false);
      const atFloor = document.getElementById("benchShareSourceNote");
      const sourcesAtFloor = H.nearestShareSources();
      const out = { floor: lo, text: atFloor ? atFloor.textContent.trim() : null,
        moved: sourcesAtFloor.map(s => ({ key: s.key, moved: s.moved })) };
      L.setBenchShareFraction(0.15, false);
      const at15 = H.nearestShareSources();
      out.movedAt15 = at15.map(s => ({ key: s.key, moved: s.moved }));
      const n15 = document.getElementById("benchShareSourceNote");
      out.textAt15 = n15 ? n15.textContent.trim() : null;
      return out;
    });
    report.checks.note = note;
    if (!note.moved.length) fail("note", "no source steps at the 8-team half-PPR floor on committed data -- the note check cannot run");
    else if (!note.text) fail("note", "a source steps at the floor but the chart shows no note");
    else {
      if (/\b(QB|RB|WR|TE)\b|VORP/.test(note.text)) fail("note", `note uses codes: ${note.text}`);
      if (!/nearest workable bench share/.test(note.text)) fail("note", `note does not say nearest share: ${note.text}`);
      if (!/(quarterbacks|running backs|wide receivers|tight ends)/.test(note.text)) fail("note", `note does not name positions: ${note.text}`);
    }
    if (!note.movedAt15.length && note.textAt15) fail("note", `note shown when nothing moved: ${note.textAt15}`);
    if (note.movedAt15.length && !note.textAt15) fail("note", "a source moved at 15% but no note");

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
