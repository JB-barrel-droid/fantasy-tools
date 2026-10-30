// JEG-1332: the USO journey's starters-and-bench reader (lineup() in tests/test_uso_site_journey_render.py COMMON) on
// a lineup table drawn by app/v2/lineup-comparison.js renderTable, placed the way the league page places it: inside a
// row of the opportunities table (league.js oppPanel sits in a <tr> of #v2LgOppsTable's <tbody>).
//
// Usage: node uso_journey_lineup_reader.cjs <repo root> <common.json>
// Prints {nested: {slots, bench}, alone: {slots, bench}} as one JSON line.
//
// The DOM below is the smallest that renderTable and lineup() use. Its querySelectorAll follows the DOM rule that a
// selector is matched against the whole document and only the results are limited to the subtree: "tbody tr" from a
// table matches its header row too when the table itself sits inside another table's tbody.
"use strict";
const fs = require("fs");
const path = require("path");

class Node_ {
  constructor() { this.childNodes = []; this.parentNode = null; }
  get firstChild() { return this.childNodes[0] || null; }
  get children() { return this.childNodes.filter(c => c instanceof Element_); }
  append(...xs) {
    xs.forEach(x => {
      if (x === null || x === undefined) return;
      if (typeof x === "string") x = new Text_(x);
      x.parentNode = this;
      this.childNodes.push(x);
    });
  }
  appendChild(x) { this.append(x); return x; }
  get textContent() { return this.childNodes.map(c => c.textContent).join(""); }
  set textContent(v) { this.childNodes = []; this.append(String(v)); }
}
class Text_ extends Node_ {
  constructor(t) { super(); this.t = t; }
  get textContent() { return this.t; }
}
class Element_ extends Node_ {
  constructor(tag) { super(); this.tagName = tag.toUpperCase(); this.attrs = {}; this.dataset = {}; this.hidden = false; }
  setAttribute(k, v) {
    this.attrs[k] = String(v);
    if (k.startsWith("data-")) this.dataset[k.slice(5).replace(/-([a-z])/g, (_, c) => c.toUpperCase())] = String(v);
  }
  getAttribute(k) { return k in this.attrs ? this.attrs[k] : null; }
  addEventListener() {}
  descendants() { return this.children.flatMap(c => [c, ...c.descendants()]); }
  ancestors() { const out = []; for (let n = this.parentNode; n; n = n.parentNode) out.push(n); return out; }
  querySelectorAll(sel) {
    const all = this.descendants();
    if (sel === "tbody tr") return all.filter(e => e.tagName === "TR" && e.ancestors().some(a => a.tagName === "TBODY"));
    if (sel === ":scope > tbody > tr") return all.filter(e => e.tagName === "TR" && e.parentNode.tagName === "TBODY" && e.parentNode.parentNode === this);
    if (sel === "table") return all.filter(e => e.tagName === "TABLE");
    throw new Error(`selector not modeled here: ${sel}`);
  }
  querySelector(sel) { return this.querySelectorAll(sel)[0] || null; }
}

const [root, commonPath] = process.argv.slice(2);
global.document = {createElement: tag => new Element_(tag)};
global.window = {TradeValueCurveControls: {getAllRows: () => []}};
const L = require(path.resolve(root, "app/v2/lineup-comparison.js"));
const COMMON = JSON.parse(fs.readFileSync(commonPath, "utf8"));
// eslint-disable-next-line no-eval
const reader = eval(`(() => {${COMMON} return {lineup, starters}; })`)();

const p = (key, name, v) => ({player_key: key, name, values: {ddf_value: v}});
const lineupValue = bench => ({slots: {QB: [p("1", "Q One", 20)], RB: [p("2", "R Two", 30), p("3", "R Three", 25)],
  WR: [p("4", "W Four", 40), p("5", "W Five", 35), p("6", "W Six", 30)], TE: [p("7", "T Seven", 15)], FLEX: [p("8", "F Eight", 12)]},
  bench, unvalued: [], starterValue: 207, benchValue: 5});
const shape = {QB: 1, RB: 2, WR: 3, TE: 1, FLEX: 1, SUPERFLEX: 0, BENCH: 5};
const draw = () => L.renderTable({before: lineupValue([p("9", "B Nine", 5)]), after: lineupValue([p("9", "B Nine", 5), p("10", "B Ten", 4)])},
  shape, "ddf_value", "Best starting lineup in DDF Value").querySelector("table");

// As Compare draws it: the table in a section, no table around it.
const alone = draw();
document.createElement("section").append(alone);
// As the league page draws it: opportunities table > tbody > tr > td > panel > table.
const nested = draw();
const outer = document.createElement("table"), body = document.createElement("tbody"), row = document.createElement("tr"), cell = document.createElement("td");
outer.append(body); body.append(row); row.append(cell); cell.append(nested);

const read = t => ({before: reader.lineup(t, 1), after: reader.lineup(t, 2), starters: reader.starters(t)});
process.stdout.write(JSON.stringify({nested: read(nested), alone: read(alone)}) + "\n");
