// JEG-1188: where league-wide Trade opportunities are gained or lost, stage by stage, on frozen engine contexts.
//   node tests/node/jeg1188_opportunity_stages.cjs [modules dir (default app/v2)] [--assert] [--json] [--mutant <name>]
//
// tests/fixtures/jeg1188/*.json are engine contexts dumped from the built league page (tools/jeg1188/dump_context.py) at
// five revisions, all on the 20-team fixture league with team 0 as you: the page's own count at that revision and the
// engine rows the search ran on. This replays the real opportunities.runAll / findTrades / tradeFit from the modules dir
// on each context and splits the count into stages:
//   pass gates   packages you win on DDF Value that every compared chart prices as break-even or better for them
//                (findTrades without the lineup boxes; throw-ins added and judged again)
//   lineup drop  of those, left out by the keep-lineup boxes
//   qualified    what is left (findTrades with the boxes, no cap)
//   top 10       what a per-opponent cap of findTrades' LIMIT would keep (the pre-#1072 page)
//   shown        runAll's rows, and their fit labels
// Point the modules dir at an older checkout's app/v2 to replay a context with the code of its own day; the row ids then
// match the page's (`page` in the fixture) exactly.
//
// --assert pins what the diagnosis rests on (see docs/claude-log/2026-10-29-jeg-1188-opportunity-count.md):
//   1. every shown row has one of the three fit labels;
//   2. shown = qualified on every context (no trade lost before ranking; JEG-1072 baseline);
//   3. every shown row, throw-ins included, passes the DDF Value edge and the chart gate when judged here, independently;
//   4. the gate stage is a function of the engine rows only: swapping the bench allocation and bench-share weights
//      between the contexts before and after #957 leaves it unchanged, swapping the rows moves it;
//   5. of the packages that passed on the day before #957, every one lost after it fails on the DDF Value edge, none on
//      the chart gate alone.
// --mutant cap-per-opponent | no-lineup-boxes | weaker-chart-gate wraps findTrades the way a regression would; --assert
// must then fail (tests/test_jeg1188_opportunity_count.py checks that it does).
"use strict";
const path = require("path");
const fs = require("fs");
const assert = require("assert");

const args = process.argv.slice(2);
const doAssert = args.includes("--assert");
const asJson = args.includes("--json");
const mutantAt = args.indexOf("--mutant");
const mutant = mutantAt === -1 ? null : args[mutantAt + 1];
const positional = args.filter((a, i) => !a.startsWith("--") && (mutantAt === -1 || i !== mutantAt + 1));
const dir = path.resolve(positional[0] || path.join(__dirname, "..", "..", "app", "v2"));
const O = require(path.join(dir, "opportunities.js"));
const F = require(path.join(dir, "finder.js"));
const FIXTURES = path.join(__dirname, "..", "fixtures", "jeg1188");
const NAMES = ["oct26-a-fit-rewrite", "oct26-b-throw-ins", "oct27-c-before-957", "oct27-d-after-957", "oct29-e-main"];
const load = name => JSON.parse(fs.readFileSync(path.join(FIXTURES, `${name}.json`), "utf8"));
const finite = v => typeof v === "number" && Number.isFinite(v);
const asShown = n => (Math.abs(n) < 0.05 ? 0 : n);
const SIZE = 2;

// The page's mathContext (app/v2/league.js), from a dump. rowsFrom / benchFrom take another dump's rows or bench numbers.
function contextOf(base, rowsFrom, benchFrom) {
  const rows = (rowsFrom || base).rows;
  const bench = benchFrom || base;
  const available = new Set(base.sources.filter(s => s.available).map(s => s.key));
  const charts = F.CHART_KEYS.filter(k => available.has(k));
  const readout = bench.benchShareReadout;
  const overall = readout && finite(readout.overall) ? readout.overall : bench.benchShare;
  const weights = {overall: finite(overall) ? overall : 0};
  F.DEPTH_POS.forEach(pos => { if (readout && finite(readout[pos])) weights[pos] = readout[pos]; });
  return {rowsByKey: new Map(rows.map(r => [String(r.player_key), r])), shape: base.shape, expected: F.expectedDepth(bench.allocation, bench.teams),
    weights, charts, market: charts.length >= F.MIN_CHARTS ? charts : null, maxSize: SIZE, keepMine: true, keepTheirs: true};
}

function mutantFind(name) {
  if (!name) return null;
  if (name === "cap-per-opponent") return (m, t, o) => { const r = F.findTrades(m, t, o); return {...r, trades: r.trades.slice(0, F.LIMIT)}; };
  if (name === "no-lineup-boxes") return (m, t, o) => F.findTrades(m, t, {...o, sanity: null});
  if (name === "weaker-chart-gate") return (m, t, o) => F.findTrades(m, t, {...o, minCharts: Math.max(1, Math.min(F.MIN_CHARTS, o.chartKeys.length) - 1)});
  throw new Error(`unknown mutant ${name}`);
}

const pairing = (doc, ctx) => {
  const teams = doc.workspace.teams;
  const mine = teams[doc.workspace.mine];
  return {mine, opponents: teams.filter(t => t.id !== mine.id), rowsOf: team => team.entries.map(e => ctx.rowsByKey.get(String(e.key))).filter(Boolean)};
};

// Stages up to the cap, from findTrades alone (the real one, never the mutant).
function gateStages(doc, ctx) {
  const {mine, opponents, rowsOf} = pairing(doc, ctx);
  const mineRows = rowsOf(mine);
  const st = {passGates: 0, lineupDropped: 0, qualified: 0, top10: 0, opponentsOverCap: 0};
  const packages = [];
  opponents.forEach(opp => {
    const theirRows = rowsOf(opp);
    const sanity = {shape: ctx.shape, mine: mineRows, theirs: theirRows, keepMine: true, keepTheirs: true};
    const open = F.findTrades(mineRows, theirRows, {chartKeys: ctx.charts, maxSize: SIZE, limit: Infinity, sanity: null});
    const boxed = F.findTrades(mineRows, theirRows, {chartKeys: ctx.charts, maxSize: SIZE, limit: Infinity, sanity});
    st.passGates += open.total;
    st.lineupDropped += boxed.sanityDropped;
    st.qualified += boxed.total;
    st.top10 += Math.min(boxed.total, F.LIMIT);
    if (boxed.total > F.LIMIT) st.opponentsOverCap += 1;
    open.trades.forEach(t => packages.push({give: t.give.map(r => String(r.player_key)), receive: t.receive.map(r => String(r.player_key))}));
  });
  return {st, packages};
}

async function shownRows(doc, ctx, find) {
  const {mine, opponents} = pairing(doc, ctx);
  const out = await O.runAll(mine, opponents, find ? {...ctx, findTrades: find} : ctx, {cache: O.createCache(), yieldFn: () => Promise.resolve(), budgetMs: 0});
  return out.rows;
}

// The two gates judged here from the rows' own values, not by finder.js: DDF Value receive - give above 0.0 as shown, and
// at least min(MIN_CHARTS, charts) charts priced with the other team's net at 0.0 or better as shown.
function judgeHere(ctx, giveKeys, receiveKeys) {
  const sum = (keys, k) => keys.reduce((s, key) => { const r = ctx.rowsByKey.get(key); const v = r && r.values ? r.values[k] : null; return s === null || !finite(v) ? null : s + v; }, 0);
  const edge = sum(receiveKeys, F.OUR_KEY) - sum(giveKeys, F.OUR_KEY);
  let priced = 0;
  let ok = 0;
  ctx.charts.forEach(c => {
    const g = sum(giveKeys, c);
    const r = sum(receiveKeys, c);
    if (g === null || r === null) return;
    priced += 1;
    if (asShown(r - g) <= 0) ok += 1;
  });
  const need = Math.min(F.MIN_CHARTS, ctx.charts.length);
  return {edge: finite(edge) && asShown(edge) > 0, charts: priced >= need && ok >= need};
}
const keysOf = list => list.map(r => String(r.player_key));

async function main() {
  const docs = Object.fromEntries(NAMES.map(n => [n, load(n)]));
  const find = mutantFind(mutant);
  const report = {modules: path.relative(process.cwd(), dir) || ".", mutant, contexts: {}};
  for (const name of NAMES) {
    const doc = docs[name];
    const ctx = contextOf(doc);
    const {st} = gateStages(doc, ctx);
    const rows = await shownRows(doc, ctx, find);
    const labels = {};
    rows.forEach(r => { labels[r.overall || "unjudged"] = (labels[r.overall || "unjudged"] || 0) + 1; });
    const failing = rows.filter(r => { const j = judgeHere(ctx, keysOf(r.give), keysOf(r.receive)); return !j.edge || !j.charts; }).length;
    const ids = rows.map(r => r.id).sort();
    report.contexts[name] = {revision: doc.provenance.revision.slice(0, 10), page: {total: doc.page.total, counts: doc.page.counts},
      ...st, shown: rows.length, labels, failingGatesHere: failing, matchesPage: JSON.stringify(ids) === JSON.stringify(doc.page.ids)};
  }
  // The #957 step: rows against bench numbers, and where the lost packages fail.
  const before = docs["oct27-c-before-957"];
  const after = docs["oct27-d-after-957"];
  const cross = {
    rowsBeforeBenchBefore: gateStages(before, contextOf(before)).st,
    rowsBeforeBenchAfter: gateStages(before, contextOf(before, before, after)).st,
    rowsAfterBenchBefore: gateStages(before, contextOf(before, after, before)).st,
    rowsAfterBenchAfter: gateStages(after, contextOf(after)).st,
  };
  const afterCtx = contextOf(after);
  const lost = {passedBefore: 0, stillPass: 0, failEdgeOnly: 0, failChartsOnly: 0, failBoth: 0};
  gateStages(before, contextOf(before)).packages.forEach(p => {
    lost.passedBefore += 1;
    const j = judgeHere(afterCtx, p.give, p.receive);
    if (j.edge && j.charts) lost.stillPass += 1;
    else if (!j.edge && !j.charts) lost.failBoth += 1;
    else if (!j.edge) lost.failEdgeOnly += 1;
    else lost.failChartsOnly += 1;
  });
  report.step957 = {cross, lost};

  if (asJson) console.log(JSON.stringify(report, null, 1));
  else {
    console.log(`League-wide opportunities, 20-team fixture, team 0 = you (modules: ${report.modules}${mutant ? `, mutant ${mutant}` : ""})`);
    console.log("context".padEnd(22) + ["page", "gates", "lineup-", "qualif", "top10", "shown", "nat", "mkt", "force"].map(h => h.padStart(8)).join(""));
    NAMES.forEach(n => {
      const c = report.contexts[n];
      console.log(n.padEnd(22) + [c.page.total, c.passGates, c.lineupDropped, c.qualified, c.top10, c.shown, c.labels.natural || 0, c.labels.market || 0, c.labels.force || 0].map(v => String(v).padStart(8)).join(""));
    });
    const x = report.step957.cross;
    console.log(`#957 cross (pass gates / qualified): rows before + bench before ${x.rowsBeforeBenchBefore.passGates}/${x.rowsBeforeBenchBefore.qualified}, `
      + `rows before + bench after ${x.rowsBeforeBenchAfter.passGates}/${x.rowsBeforeBenchAfter.qualified}, rows after + bench before ${x.rowsAfterBenchBefore.passGates}/${x.rowsAfterBenchBefore.qualified}, `
      + `rows after + bench after ${x.rowsAfterBenchAfter.passGates}/${x.rowsAfterBenchAfter.qualified}`);
    console.log(`#957 lost packages: ${JSON.stringify(report.step957.lost)}`);
  }

  if (doAssert) {
    NAMES.forEach(n => {
      const c = report.contexts[n];
      const known = (c.labels.natural || 0) + (c.labels.market || 0) + (c.labels.force || 0);
      assert.strictEqual(known, c.shown, `${n}: rows without a Natural / Market supported / Force label: ${JSON.stringify(c.labels)}`);
      assert.strictEqual(c.shown, c.qualified, `${n}: ${c.shown} trades shown but ${c.qualified} qualify: trades are lost before ranking, or shown without passing the lineup boxes`);
      assert.strictEqual(c.failingGatesHere, 0, `${n}: ${c.failingGatesHere} shown trades fail the DDF Value edge or the chart gate when judged independently`);
    });
    const x = report.step957.cross;
    assert.strictEqual(x.rowsBeforeBenchAfter.passGates, x.rowsBeforeBenchBefore.passGates, "the gate stage moved with the bench allocation alone");
    assert.strictEqual(x.rowsAfterBenchBefore.passGates, x.rowsAfterBenchAfter.passGates, "the gate stage moved with the bench allocation alone");
    assert.ok(x.rowsAfterBenchAfter.passGates < x.rowsBeforeBenchBefore.passGates, "the #957 rows no longer cut the gate stage: re-diagnose JEG-1188");
    const l = report.step957.lost;
    assert.ok(l.passedBefore - l.stillPass > 0, "no package was lost at #957: re-diagnose JEG-1188");
    assert.strictEqual(l.failChartsOnly, 0, `${l.failChartsOnly} packages lost at #957 fail the chart gate alone`);
    assert.strictEqual(l.failEdgeOnly + l.failBoth, l.passedBefore - l.stillPass, "lost packages that fail neither gate");
    console.log("assertions passed");
  }
}
main().catch(e => { console.error(e.stack || e); process.exit(1); });
