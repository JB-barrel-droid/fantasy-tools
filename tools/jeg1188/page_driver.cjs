// JEG-1188: the built league page without a browser. jsdom loads the served v2 page, the same fixture league the render
// tests use is seeded into the workspace, and once league-wide Trade opportunities settle it prints what the page shows
// (window.TradeValueLeague.ui.result.rows by overall fit) and, with an output path, dumps the engine context the search
// ran on: the engine rows, roster shape, bench allocation, bench-share readout and source availability. That dump is what
// tests/node/jeg1188_opportunity_stages.cjs replays with any revision's app/v2 modules.
//
// Used where Playwright's Chromium cannot be downloaded. It is not a render test: no layout, no styles, no clicks.
//   node tools/jeg1188/page_driver.cjs <jsdom package dir> <served .../v2/ url> <fixture.json> <team index> <today> [ctx-out.json]
// <jsdom package dir> holds node_modules/jsdom (jsdom is not a repo dependency; `npm install jsdom@24.1.3` in a scratch dir).
// <today> is the page clock pin (tests/_render_env.pin_data_week_script), as tools/fit_distribution_page.py uses.
"use strict";
const path = require("path");
const fs = require("fs");

const [jsdomDir, base, fxPath, mineArg, today, ctxOut] = process.argv.slice(2);
const {JSDOM, VirtualConsole} = require(path.join(path.resolve(jsdomDir), "node_modules", "jsdom"));
const fx = JSON.parse(fs.readFileSync(fxPath, "utf8"));
const mine = mineArg === "fixture" ? (fx.myTeamIndex || 0) : Number(mineArg);
const errors = [];
const vc = new VirtualConsole();
vc.on("jsdomError", e => errors.push(String((e && (e.stack || e.message)) || e).split("\n")[0]));
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
async function until(fn, ms, what) {
  const started = Date.now();
  while (Date.now() - started < ms) {
    try { if (fn()) return; } catch (error) { /* not ready yet */ }
    await sleep(50);
  }
  throw new Error(`timed out waiting for ${what}; page errors: ${errors.slice(0, 5).join(" | ")}`);
}

(async () => {
  const dom = await JSDOM.fromURL(`${base}#find-league`, {
    runScripts: "dangerously", resources: "usable", pretendToBeVisual: true, virtualConsole: vc,
    beforeParse(w) {
      w.TRADE_VALUE_TODAY = today;
      w.fetch = (url, opts) => fetch(new URL(String(url), w.location.href).href, opts);
      w.matchMedia = q => ({matches: /min-width:\s*(\d+)/.test(q) ? Number(RegExp.$1) <= 1440 : false, media: q,
        addListener() {}, removeListener() {}, addEventListener() {}, removeEventListener() {}});
      w.ResizeObserver = class { observe() {} unobserve() {} disconnect() {} };
      w.IntersectionObserver = class { observe() {} unobserve() {} disconnect() {} };
      w.scrollTo = () => {};
      w.HTMLElement.prototype.scrollIntoView = function () {};
      Object.defineProperty(w, "innerWidth", {value: 1440, configurable: true});
    },
  });
  const w = dom.window;
  await until(() => w.TradeValueV2 && w.TradeValueCurveControls && w.document.getElementById("v2LgCard"), 120000, "the page");
  await until(() => w.TradeValueLeague && w.TradeValueLeague.ui.ready, 60000, "the league view");
  // The same seeding as tests/_league_render.SEED.
  const W = w.TradeValueWorkspace;
  let ws = W.newWorkspace({name: "Test league"});
  fx.teams.forEach(t => { ws = W.ops.addTeam(ws, t.name, {entries: t.players}); });
  ws = W.ops.setMyTeam(ws, ws.teams[mine].id);
  W.store.replace(ws, "replace");
  const L = w.TradeValueLeague;
  await sleep(300);
  await until(() => !L.ui.running && L.ui.result && !L.ui.timer, 600000, "league-wide opportunities");
  const rows = L.ui.result.rows;
  const counts = {};
  rows.forEach(r => { counts[r.overall] = (counts[r.overall] || 0) + 1; });
  const C = w.TradeValueCurveControls;
  const info = C.getSourceInfo ? C.getSourceInfo() : [];
  console.log(JSON.stringify({mine, today, total: rows.length, counts, errors: errors.slice(0, 10)}));
  if (ctxOut) {
    const readout = C.getBenchShareReadout ? C.getBenchShareReadout() : null;
    fs.writeFileSync(ctxOut, JSON.stringify({
      page: {total: rows.length, counts, ids: rows.map(r => r.id).sort()},
      rows: C.getAllRows(), shape: C.getRosterShape ? C.getRosterShape() : null,
      allocation: C.getAdjustmentWeights().allocation, teams: C.getState().teams,
      sources: info.map(i => ({key: i.key, available: Boolean(i.available)})),
      benchShareReadout: readout, benchShare: C.getBenchShare ? C.getBenchShare() : null,
      workspace: {mine, teams: W.store.get().teams.map(t => ({id: t.id, name: t.name, entries: t.entries}))},
    }));
  }
  w.close();
  process.exit(0);
})().catch(error => { console.error(String(error.stack || error)); process.exit(2); });
