// JEG-1265: checks for the Values page Fieldnotes view logic (app/v2/values-fieldnotes.js). Pure Node, no browser.
// Usage: node tests/values_fieldnotes_harness.cjs <modules dir>. Prints {check: true | "why it failed"} as JSON.
//
// Parity is against the unchanged page: fmt(), sortedRows(), the header click rule, aria-sort, TABLE_GROUPS and the
// SERIES_GROUPS notes are read out of app/v2/v2.js itself and run beside this module on the same fixture.
"use strict";

const fs = require("fs");
const path = require("path");

const dir = path.resolve(process.argv[2] || path.join(__dirname, "..", "app", "v2"));
const V = require(path.join(dir, "values-fieldnotes.js"));
const SV = require(path.join(dir, "source-views.js"));
const FIXTURE = JSON.parse(fs.readFileSync(path.join(__dirname, "fixtures", "values-fieldnotes", "synthetic-values.json"), "utf8"));
const MODULE_SRC = fs.readFileSync(path.join(dir, "values-fieldnotes.js"), "utf8");
const V2 = fs.readFileSync(path.join(dir, "v2.js"), "utf8");

// ---------- the page's own code, read from v2.js ----------
function block(src, start) {
  const at = src.indexOf(start);
  if (at < 0) return null;
  let depth = 0;
  for (let i = src.indexOf("{", at); i < src.length; i += 1) {
    if (src[i] === "{") depth += 1;
    else if (src[i] === "}") { depth -= 1; if (depth === 0) return src.slice(at, i + 1); }
  }
  return null;
}
const fmtSrc = (V2.match(/\n\s*const fmt = (v => \{[^\n]+\});\n/) || [])[1];
const sortedRowsSrc = block(V2, "function sortedRows(cols) {");
const clickSrc = (V2.match(/(const current = state\.sort \? state\.sort\.key : view\.rankKey;\s*const dir = [^\n]+\n\s*state\.sort = [^\n]+)/) || [])[1];
const ariaSrc = (V2.match(/(const sortKey = state\.sort \? state\.sort\.key : view\.rankKey;\s*if \(sortKey === col\.id\) th\.setAttribute\("aria-sort"[^\n]+)/) || [])[1];
const tableGroupsSrc = (V2.match(/const TABLE_GROUPS = (\[[\s\S]*?\]\]);/) || [])[1];
const seriesGroupsSrc = (V2.match(/const SERIES_GROUPS = (\[[\s\S]*?\n\s*\]);/) || [])[1];
/* eslint-disable no-eval */
const pageFmt = fmtSrc ? eval(fmtSrc) : null;
const pageSorted = sortedRowsSrc ? eval(`(function (view, state) { ${sortedRowsSrc}; return sortedRows; })`) : null;
const pageClick = clickSrc ? eval(`(function (state, view, col) { ${clickSrc}; return state.sort; })`) : null;
const pageAria = ariaSrc ? eval(`(function (state, view, col) { const th = {setAttribute: (k, v) => { th[k] = v; }}; ${ariaSrc}; return th["aria-sort"] || null; })`) : null;
const pageTableGroups = tableGroupsSrc ? eval(tableGroupsSrc) : null;
const pageSeriesGroups = seriesGroupsSrc ? eval(seriesGroupsSrc) : null;
/* eslint-enable no-eval */

// The page's column objects for the same columns, as tableColumns() builds them (get / text / order).
const TIER_ORDER_DEFAULT = 3;
function pageCols(cols) {
  return cols.map(col => {
    if (col.kind === "rank") return {id: col.id, get: row => row.rank};
    if (col.kind === "name") return {id: col.id, text: true, get: row => row.name};
    if (col.kind === "value") return {id: col.id, get: row => row.values[col.source]};
    if (col.kind === "spread") return {id: col.id, get: row => row.spread};
    if (col.id === "team") return {id: col.id, text: true, get: row => row.team || "Free agent"};
    if (col.id === "tier") return {id: col.id, text: true, get: row => row.tier, order: row => row.tierOrder ?? TIER_ORDER_DEFAULT};
    return {id: col.id, text: true, get: row => row[col.id]};
  });
}

const clone = x => JSON.parse(JSON.stringify(x));
const freeze = x => { if (x && typeof x === "object") { Object.values(x).forEach(freeze); Object.freeze(x); } return x; };
const ctx = edit => { const c = clone(FIXTURE); if (edit) edit(c); return freeze(c); };
function eq(a, b, what) { if (JSON.stringify(a) !== JSON.stringify(b)) throw new Error(`${what}: got ${JSON.stringify(a)}, want ${JSON.stringify(b)}`); }
function ok(v, what) { if (!v) throw new Error(what); }
const valueCols = c => c.columns.filter(col => col.kind === "value" || col.kind === "spread");
const keysOf = rows => rows.map(r => r.player_key || r.key);
// A fixture with meta columns and tiers too, so every column kind is sorted.
function withMeta(c) {
  c.columns.splice(2, 0, {id: "pos", kind: "meta", label: "Pos", text: true}, {id: "team", kind: "meta", label: "Team", text: true},
    {id: "tier", kind: "meta", label: "Tier", text: true, order: true});
  const tiers = [["Starter", 0], ["Bench", 1], ["Waiver", 2], [null, null]];
  c.rows.forEach((r, i) => { const [t, o] = tiers[i % 4]; r.tier = t; r.tierOrder = o; });
}

const checks = {
  test_page_code_found() {
    ok(pageFmt, "v2.js fmt not found"); ok(pageSorted, "v2.js sortedRows not found"); ok(pageClick, "v2.js header click rule not found");
    ok(pageAria, "v2.js aria-sort rule not found"); ok(pageTableGroups, "v2.js TABLE_GROUPS not found"); ok(pageSeriesGroups, "v2.js SERIES_GROUPS not found");
  },
  test_fmt_matches_page() {
    [0, -0, 0.04, -0.04, 0.05, -0.05, 1.25, 12.25, -1.25, 78.4, 99.95, -3.3333, 1e-9, NaN, null, undefined, Infinity, -Infinity, 1e6]
      .forEach(v => eq(V.fmt(v), pageFmt(v), `fmt(${v})`));
  },
  test_every_number_displayed_as_page() {
    const c = ctx();
    const vm = V.viewModel(c);
    const byKey = Object.fromEntries(c.rows.map(r => [r.player_key, r]));
    let numbers = 0;
    vm.rows.forEach(r => {
      const row = byKey[r.key];
      r.cells.forEach((cell, i) => {
        const col = c.columns[i];
        const v = col.kind === "value" ? row.values[col.source] : col.kind === "spread" ? row.spread : null;
        if (!(col.kind === "value" || col.kind === "spread")) return;
        if (Number.isFinite(v)) { eq(cell.text, pageFmt(v), `${row.player_key} ${col.id}`); ok(!cell.missing, `${row.player_key} ${col.id} finite but missing`); numbers += 1; }
        else { eq(cell.text, "—", `${row.player_key} ${col.id} missing shows a dash`); ok(cell.missing, "missing flag"); }
      });
    });
    ok(numbers > 150, `too few numbers compared: ${numbers}`);
  },
  test_missing_is_not_zero() {
    const vm = V.viewModel(ctx());
    const zero = vm.rows.find(r => r.key === "syn-09").cells.find(cell => cell.col === "espn");
    eq([zero.text, zero.missing], ["0.0", false], "a finite 0 is a value");
    const gone = vm.rows.find(r => r.key === "syn-04").cells.find(cell => cell.col === "usatoday");
    eq([gone.text, gone.missing, gone.reason], ["—", true, "USA Today has no value for this player"], "missing keeps the page's reason");
    ["asc", "desc"].forEach(dir => {
      const sorted = V.sortRows(FIXTURE.rows, FIXTURE.columns, {key: "usatoday", dir});
      eq(sorted[sorted.length - 1].player_key, "syn-04", `missing sorts last (${dir})`);
    });
  },
  test_sort_matches_page() {
    const c = clone(FIXTURE);
    withMeta(c);
    const pcols = pageCols(c.columns);
    const sorts = [null].concat(...c.columns.filter(col => col.kind !== "rank").map(col => [{key: col.id, dir: "asc"}, {key: col.id, dir: "desc"}]),
      [{key: "no-such-column", dir: "asc"}]);
    // In rank order (as view.visible is) and reversed, so ties must fall back to the rank, not to the input order.
    [c.rows, c.rows.slice().reverse()].forEach((rows, n) => sorts.forEach(sort => {
      const page = pageSorted({visible: rows}, {sort})(pcols);
      eq(keysOf(V.sortRows(rows, c.columns, sort)), keysOf(page), `order for ${JSON.stringify(sort)}${n ? " (reversed input)" : ""}`);
    }));
    const tie = V.sortRows(c.rows.slice().reverse(), c.columns, {key: "fantasycalc", dir: "desc"}).map(r => r.player_key);
    ok(tie.indexOf("syn-05") < tie.indexOf("syn-06"), "equal values keep the ranking order");
    // and through the view model, as shown
    const vm = V.viewModel(freeze(Object.assign(clone(FIXTURE), {sort: {key: "fantasycalc", dir: "asc"}, shown: 999})));
    eq(keysOf(vm.rows), keysOf(pageSorted({visible: FIXTURE.rows}, {sort: {key: "fantasycalc", dir: "asc"}})(pageCols(FIXTURE.columns))), "view model order");
  },
  test_next_sort_matches_page() {
    const c = clone(FIXTURE);
    withMeta(c);
    const starts = [null, {key: "ddf_value", dir: "desc"}, {key: "ddf_value", dir: "asc"}, {key: "name", dir: "asc"}, {key: "espn", dir: "desc"}, {key: "tier", dir: "asc"}];
    starts.forEach(sort => c.columns.filter(col => col.kind !== "rank").forEach(col => {
      const pageCol = pageCols([col])[0];
      eq(V.nextSort(sort, c.rankKey, col), pageClick({sort}, {rankKey: c.rankKey}, pageCol), `click ${col.id} from ${JSON.stringify(sort)}`);
    }));
  },
  test_aria_sort_matches_page() {
    const sorts = [null, {key: "espn", dir: "asc"}, {key: "espn", dir: "desc"}, {key: "name", dir: "asc"}];
    sorts.forEach(sort => FIXTURE.columns.forEach(col => eq(V.ariaSort(sort, FIXTURE.rankKey, col), pageAria({sort}, {rankKey: FIXTURE.rankKey}, col),
      `aria-sort ${col.id} under ${JSON.stringify(sort)}`)));
    const vm = V.viewModel(ctx());
    eq(vm.head.filter(h => h.ariaSort).map(h => [h.id, h.ariaSort]), [["ddf_value", "descending"]], "unsorted: the ranking series is the sort");
  },
  test_groups_match_page() {
    eq(V.GROUP_ORDER, pageTableGroups.map(([id]) => id), "group order is TABLE_GROUPS");
    eq(FIXTURE.groups.map(g => [g.id, g.label]), pageTableGroups, "fixture group labels are TABLE_GROUPS");
    const notes = Object.fromEntries(pageSeriesGroups.map(g => [g.id, g.note]));
    const seriesId = {ddf: "ddf", projections: "proj", published: "pub", observed: "observed", vorp: "vorp"};
    FIXTURE.groups.filter(g => seriesId[g.id]).forEach(g => eq(g.note, notes[seriesId[g.id]], `${g.id} note is the page's SERIES_GROUPS note`));
  },
  test_source_categories_stay_distinct() {
    FIXTURE.columns.filter(col => col.kind === "value" && !/^ddf_/.test(col.source)).forEach(col =>
      eq(col.group, SV.categoryOf(col.source).id, `${col.source} sits in its JEG-1212 category`));
    const vm = V.viewModel(ctx());
    eq(vm.runs.map(r => [r.id, r.span]), [["", 2], ["rank-series", 1], ["projections", 3], ["published", 3], ["observed", 1], ["spread", 1]], "header runs");
    eq(vm.groupedCols.map(g => g.id), ["ddf", "projections", "published", "observed", "spread"], "phone groups keep the three kinds apart");
    ok(!vm.groupedCols.some(g => g.id === "published" && g.cols.includes("fantasycalc")), "observed trades are not a published chart");
  },
  test_unavailable_source_column() {
    const vm = V.viewModel(ctx());
    const h = vm.head.find(x => x.id === "cbsros");
    ok(h.unavailable, "header marked unavailable");
    vm.rows.forEach(r => { const cell = r.cells.find(x => x.col === "cbsros"); eq([cell.text, cell.missing], ["—", true], `${r.key} cbsros`); });
  },
  test_states() {
    eq(V.viewModel(ctx(c => { c.status = "loading"; })).state, "loading", "loading");
    const un = V.viewModel(ctx(c => { c.status = "unavailable"; c.reason = "synthetic: no values loaded"; }));
    eq([un.state, un.rows.length, un.text], ["unavailable", 0, "synthetic: no values loaded"], "unavailable shows no numbers");
    eq(V.viewModel(ctx(c => { delete c.status; })).state, "unavailable", "no status is not ready");
    const empty = V.viewModel(ctx(c => { c.rows = []; }));
    eq([empty.state, empty.heading, empty.meta], ["empty", "No players match.", "0 players · ranks 1–30"], "empty");
    eq(V.viewModel(ctx()).state, "ready", "ready");
  },
  test_weekly_never_blended() {
    const vm = V.viewModel(ctx(c => { c.columns.find(col => col.id === "espn").horizon = "weekly"; }));
    eq([vm.state, vm.rows.length], ["mixed", 0], "a weekly column beside rest-of-season ones withholds the table");
    eq(V.viewModel(ctx(c => c.columns.forEach(col => { if (col.horizon) col.horizon = "weekly"; }))).state, "ready", "one horizon shows");
  },
  test_shown_and_meta() {
    const vm = V.viewModel(ctx());
    eq([vm.rows.length, vm.total, vm.more, vm.meta], [25, 30, true, "30 players · ranks 1–30"], "first 25 of 30");
    eq(V.viewModel(ctx(c => { c.shown = 30; })).more, false, "all shown");
    eq(V.viewModel(ctx(c => { c.rows = c.rows.slice(0, 1); })).meta, "1 player · ranks 1–30", "one player");
  },
  test_ranking_and_labels() {
    const vm = V.viewModel(ctx());
    eq(vm.rankLabel, "★ DDF Value", "ranking series named");
    eq(vm.rows[0].ranking.text, pageFmt(FIXTURE.rows[0].values.ddf_value), "phone card leads with the ranking value");
    eq(vm.rows[0].sub, "RB · SYA", "position and team");
    eq(vm.rows[4].sub, "WR · Free agent", "no team reads Free agent");
    eq(vm.rankOptions.filter(o => o.reason).map(o => o.key), ["cbsros"], "a source that cannot be picked keeps its reason");
    eq(vm.rows[4].cells.find(x => x.col === "ddf_value").notes, ["Your override"], "cell notes passed through");
  },
  test_context_not_mutated() {
    const c = clone(FIXTURE);
    c.sort = {key: "espn", dir: "asc"};
    const before = JSON.stringify(c);
    V.viewModel(c);
    V.sortRows(c.rows, c.columns, c.sort);
    eq(JSON.stringify(c), before, "context unchanged");
  },
  test_fixture_labelled() {
    const vm = V.viewModel(ctx());
    eq(vm.fixture.kind, "synthetic", "fixture kind");
    ok(/not live/i.test(vm.fixture.label), "fixture label says not live");
    ok(FIXTURE.rows.every(r => /^Synthetic /.test(r.name)), "every player is synthetic");
    ok(!/week \d|updated|as of|fresh/i.test(JSON.stringify(FIXTURE)), "no source dates or freshness in the fixture");
    eq(V.viewModel(ctx(c => { delete c.fixture; })).fixture, null, "a live context has no label");
  },
  test_module_writes_nothing() {
    ["localStorage", "sessionStorage", "indexedDB", "fetch(", "XMLHttpRequest", "innerHTML", "document.cookie", "history.push", "location.hash ="]
      .forEach(word => ok(!MODULE_SRC.includes(word), `module uses ${word}`));
  }
};

const out = {};
Object.entries(checks).forEach(([name, fn]) => {
  try { fn(); out[name] = true; } catch (error) { out[name] = String(error && error.message || error); }
});
process.stdout.write(JSON.stringify(out, null, 1));
