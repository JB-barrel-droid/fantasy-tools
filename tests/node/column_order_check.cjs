// JEG-1232: saved column order for the league tables. Pure Node, no browser.
//   node tests/node/column_order_check.cjs <dir with column-order.js, workspace.js, opportunities.js, team-summary.js, table-sort.js>
// Prints one JSON object {ran, failures}; tests/test_jeg1232_column_order.py runs it on the real modules and on broken copies.
"use strict";
const path = require("path");
const assert = require("assert");

const dir = path.resolve(process.argv[2] || path.join(__dirname, "..", "..", "app", "v2"));
const C = require(path.join(dir, "column-order.js"));
const W = require(path.join(dir, "workspace.js"));
const O = require(path.join(dir, "opportunities.js"));
const T = require(path.join(dir, "team-summary.js"));
const S = require(path.join(dir, "table-sort.js"));

const ran = [];
const failures = [];
function t(name, fn) {
  ran.push(name);
  try { fn(); } catch (error) { failures.push({name, message: String(error && error.message || error)}); }
}
const deepFreeze = v => { if (v && typeof v === "object") { Object.values(v).forEach(deepFreeze); Object.freeze(v); } return v; };

const fields = T.summaryFields("fund");
const optionalOf = keys => keys.map(key => {
  const [side, id] = key.split(":");
  const f = fields.find(x => x.id === id);
  return {id: `summary:${key}`, label: `${side === "mine" ? "Our" : "Their"} ${f.label}`};
});
const BASE = C.OPP_BASE;
const units = optional => C.opportunityUnits(O.OPP_COLUMNS, optional || []);
const known = C.opportunityKnown(fields);
const ids = list => list.map(u => u.id);

t("test_untouched_keeps_baseline", () => {
  const u = units();
  const r = C.reconcile(undefined, u, known);
  assert.deepStrictEqual(r.order, BASE);
  assert.strictEqual(r.explicit, false);
  assert.strictEqual(r.full, null, "nothing to store for an untouched league");
  assert.ok(C.isBaseline(r.order, u));
  // A new workspace carries no saved order, so the table draws exactly what it draws today.
  const ws = W.newWorkspace({now: 1});
  assert.strictEqual(C.savedOf(ws.ui, "opps"), undefined);
  assert.deepStrictEqual(C.reconcile(C.savedOf(ws.ui, "opps"), u, known).order, BASE);
});

t("test_catalog_matches_table_columns", () => {
  // Every sortable column of the opportunities table is a unit or a grouped sub-column, so no column is lost or defined twice.
  const u = units();
  const covered = new Set(u.flatMap(x => [x.id].concat(x.sub || [])));
  O.OPP_COLUMNS.forEach(c => assert.ok(covered.has(c.id), `${c.id} is drawn`));
  assert.deepStrictEqual(u.find(x => x.id === "market").sub, ["market", "fair"], "Market perception moves with Edge and Charts fair");
  O.OPP_COLUMNS.forEach(c => { const x = u.find(y => y.id === c.id); if (x) assert.strictEqual(x.label, c.label, "labels come from OPP_COLUMNS"); });
  assert.ok(u.every(x => x.required), "every base column is required");
  assert.strictEqual(new Set(ids(u)).size, u.length, "unique ids");
});

t("test_move_save_reload", () => {
  const u = units();
  let r = C.reconcile(undefined, u, known);
  let full = r.full || r.order;
  let m = C.move(full, r.order, "capture", -1);
  m = C.move(m.full, m.order, "capture", -1);
  assert.deepStrictEqual(m.order.slice(0, 3), ["capture", "opponent", "trade"]);
  assert.strictEqual(C.moveMessage(u, m, "capture", -1), "DDF Value capture moved to position 1 of 9.");
  let ws = W.newWorkspace({now: 1});
  ws = W.ops.setUi(ws, {summaryColumns: ["theirs:rosterF"], sort: {opps: {col: "capture", dir: "desc"}}, filters: {fit: "natural"}});
  const before = JSON.parse(JSON.stringify(ws.ui));
  ws = W.ops.setUi(ws, C.savePatch(ws.ui, "opps", m.full));
  // Only ui.columnOrder changed: sort, filters, summary columns, basis and finder settings are as they were.
  const after = JSON.parse(JSON.stringify(ws.ui));
  delete after.columnOrder;
  assert.deepStrictEqual(after, before, "no other setting changes");
  // Through the stored text and back (what a reload reads).
  const reloaded = W.parseStored(W.serialize(ws)).workspace;
  assert.ok(reloaded, "stored workspace parses");
  r = C.reconcile(C.savedOf(reloaded.ui, "opps"), u, known);
  assert.strictEqual(r.explicit, true);
  assert.deepStrictEqual(r.order, m.order, "same order after reload");
  assert.deepStrictEqual(reloaded.ui.sort.opps, {col: "capture", dir: "desc"}, "saved sort unchanged");
});

t("test_boundaries_announce", () => {
  const u = units();
  const r = C.reconcile(undefined, u, known);
  const first = C.move(r.order, r.order, "opponent", -1);
  assert.strictEqual(first.moved, false);
  assert.deepStrictEqual(first.order, BASE);
  assert.strictEqual(C.moveMessage(u, first, "opponent", -1), "Opponent is already first.");
  const last = C.move(r.order, r.order, "rank", 1);
  assert.strictEqual(C.moveMessage(u, last, "rank", 1), "Opportunity rank is already last.");
  const unknown = C.move(r.order, r.order, "nope", 1);
  assert.strictEqual(unknown.moved, false);
});

t("test_corrupt_and_legacy_saved_state", () => {
  const u = units();
  for (const bad of ["opponent,trade", 7, {opps: BASE}, true]) {
    const r = C.reconcile(bad, u, known);
    assert.deepStrictEqual(r.order, BASE, `${JSON.stringify(bad)} falls back to the default`);
    assert.strictEqual(r.explicit, false);
  }
  const r = C.reconcile(["rank", "rank", {id: "capture"}, null, 3, "gone:column", "opponent"], u, known);
  // Kept: rank, capture, opponent ({id} objects read; duplicates, bad entries and unknown ids dropped). Each missing column
  // follows its nearest earlier baseline neighbour: Trade after Opponent, Projections agree after DDF Value capture, and so on.
  assert.deepStrictEqual(r.order, ["rank", "capture", "proj", "ours", "market", "theirs", "overall", "opponent", "trade"]);
  assert.ok(r.issues.includes("duplicate:rank") && r.issues.includes("unknown:gone:column") && r.issues.includes("bad-entry"));
  assert.strictEqual(new Set(r.order).size, r.order.length);
  assert.deepStrictEqual([...r.order].sort(), [...BASE].sort(), "every required column is back");
  // A whole corrupt stored league still loads with the default order.
  const text = JSON.stringify({v: W.VERSION, activeId: "a", workspaces: [{id: "a", name: "L", teams: [], ui: {columnOrder: "garbage"}}]});
  const ws = W.parseStored(text).workspace;
  assert.deepStrictEqual(C.reconcile(C.savedOf(ws.ui, "opps"), u, known).order, BASE);
  const ws2 = W.parseStored(JSON.stringify({v: W.VERSION, activeId: "a", workspaces: [{id: "a", name: "L", teams: [], ui: {columnOrder: {opps: 5}}}]})).workspace;
  assert.deepStrictEqual(C.reconcile(C.savedOf(ws2.ui, "opps"), u, known).order, BASE);
});

t("test_required_columns_return_in_place", () => {
  const u = units();
  // A saved order from a build that lacked Projections agree and Our team fit: both come back next to their baseline neighbour.
  const r = C.reconcile(["rank", "opponent", "trade", "capture", "market", "theirs", "overall"], u, known);
  assert.deepStrictEqual(r.order, ["rank", "opponent", "trade", "capture", "proj", "ours", "market", "theirs", "overall"]);
  // Nothing saved but one id: the rest follow it in baseline order.
  assert.deepStrictEqual(C.reconcile(["overall"], u, known).order, ["opponent", "trade", "capture", "proj", "ours", "market", "theirs", "overall", "rank"],
    "a missing first column goes before its later neighbour, deterministic");
  assert.deepStrictEqual(C.reconcile([], u, known).order, BASE, "an empty saved list draws the baseline");
});

t("test_catalog_change_new_column", () => {
  const u = units();
  const r = C.reconcile(["capture", "opponent", "trade", "proj", "ours", "market", "theirs", "overall", "rank"], u, known);
  // A later build adds a base column between Our team fit and Market perception.
  const grown = u.slice(0, 5).concat([{id: "newcol", label: "New", required: true}], u.slice(5));
  const g = C.reconcile(r.full, grown, known.concat(["newcol"]));
  assert.deepStrictEqual(g.order, ["capture", "opponent", "trade", "proj", "ours", "newcol", "market", "theirs", "overall", "rank"]);
  // And when a later build removes a column the saved order named, it is dropped, not drawn.
  const shrunk = u.filter(x => x.id !== "proj");
  const s = C.reconcile(r.full, shrunk, known.filter(id => id !== "proj"));
  assert.ok(!s.order.includes("proj"));
  assert.deepStrictEqual(s.order, ["capture", "opponent", "trade", "ours", "market", "theirs", "overall", "rank"]);
  // Same input, same output.
  assert.deepStrictEqual(C.reconcile(r.full, grown, known.concat(["newcol"])).order, g.order);
});

t("test_hidden_and_shown_columns", () => {
  const opt = optionalOf(["mine:rosterF", "theirs:rosterF"]);
  let u = units(opt);
  let r = C.reconcile(undefined, u, known);
  assert.deepStrictEqual(r.order, BASE.concat(["summary:mine:rosterF", "summary:theirs:rosterF"]), "shown optional columns follow the base columns, as today");
  // Move Their roster value to the front, then hide it: the order stores it, the table does not draw it.
  let m = { full: r.order, order: r.order };
  for (let i = 0; i < 10; i += 1) m = C.move(m.full, m.order, "summary:theirs:rosterF", -1);
  assert.strictEqual(m.order[0], "summary:theirs:rosterF");
  const hidden = units(optionalOf(["mine:rosterF"]));
  const h = C.reconcile(m.full, hidden, known);
  assert.ok(!h.order.includes("summary:theirs:rosterF"), "a hidden column is not drawn");
  assert.ok(h.full.includes("summary:theirs:rosterF"), "but keeps its saved place");
  // A move while it is hidden passes over it: one press moves one visible place.
  const step = C.move(h.full, h.order, "opponent", -1);
  assert.strictEqual(step.moved, false, "Opponent is first among the shown columns");
  const step2 = C.move(h.full, h.order, "trade", -1);
  assert.deepStrictEqual(step2.order.slice(0, 2), ["trade", "opponent"]);
  // Shown again: back at the front.
  const back = C.reconcile(step2.full, u, known);
  assert.strictEqual(back.order[0], "summary:theirs:rosterF");
  // A newly shown column the saved order never named goes next to its baseline neighbour (after Our roster value).
  u = units(optionalOf(["mine:rosterF", "mine:starterF", "theirs:rosterF"]));
  const added = C.reconcile(step2.full, u, known);
  assert.strictEqual(added.order[added.order.indexOf("summary:mine:rosterF") + 1], "summary:mine:starterF");
});

t("test_reset_to_default", () => {
  let ws = W.newWorkspace({now: 1});
  ws = W.ops.setUi(ws, C.savePatch(ws.ui, "summary", ["team", "rank"]));
  ws = W.ops.setUi(ws, C.savePatch(ws.ui, "opps", ["rank"].concat(BASE.slice(0, -1))));
  ws = W.ops.setUi(ws, C.savePatch(ws.ui, "opps", null));
  assert.strictEqual(C.savedOf(ws.ui, "opps"), undefined, "Reset removes the saved order");
  assert.deepStrictEqual(C.savedOf(ws.ui, "summary"), ["team", "rank"], "other tables keep theirs");
  assert.deepStrictEqual(C.reconcile(C.savedOf(ws.ui, "opps"), units(), known).order, BASE);
});

t("test_no_mutation_of_inputs", () => {
  const u = deepFreeze(units(optionalOf(["mine:rosterF"])));
  const saved = deepFreeze(["rank", "capture"]);
  const r = C.reconcile(saved, u, deepFreeze(known.slice()));
  const m = C.move(deepFreeze(r.full.slice()), deepFreeze(r.order.slice()), "capture", 1);
  assert.ok(m.moved);
  const ui = deepFreeze({columnOrder: {summary: ["team"]}, sort: {opps: {col: "rank", dir: "asc"}}});
  const patch = C.savePatch(ui, "opps", m.full);
  assert.deepStrictEqual(Object.keys(patch), ["columnOrder"], "the patch only names columnOrder");
  // The order is presentation: sorting the same rows gives the same rows whatever order the columns are drawn in.
  const rows = deepFreeze([{rank: 2, opponent: "B", edge: 1, id: "b"}, {rank: 1, opponent: "A", edge: 3, id: "a"}]);
  const state = {col: "capture", dir: "desc"};
  const a = S.sortRows(rows, O.OPP_COLUMNS, state, O.OPP_TIES).map(x => x.id);
  C.applyOrder(u, m.order);
  assert.deepStrictEqual(S.sortRows(rows, O.OPP_COLUMNS, state, O.OPP_TIES).map(x => x.id), a);
  assert.deepStrictEqual(ids(C.applyOrder(u, m.order)), m.order);
});

process.stdout.write(JSON.stringify({ran, failures}));
