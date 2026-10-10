#!/usr/bin/env node
"use strict";

import fs from "node:fs";
import path from "node:path";
import {fileURLToPath} from "node:url";
import {createRequire} from "node:module";

const require = createRequire(import.meta.url);
const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const REAL_CONSOLE_ERROR = console.error.bind(console);
const REAL_CONSOLE_WARN = console.warn.bind(console);
const POSITIONS = ["QB", "RB", "WR", "TE"];
const SIM_DEFAULT_SOURCE = "cbs";
// JEG-508: the guard is the fixed-pie invariant of the value pipeline (VP-5):
// every source's Adjusted values sum to the league pie and each of its eight
// groups to its budget, pie x DDF weight. The simulated broken state is the
// retired ESPN-anchor rule ("ESPN group totals as DDF weights", VP-10):
// the source's groups are paid at ESPN's own weights instead of the averaged
// DDF weights. Its total still equals the pie (both weight sets sum to 1), so
// a total-only guard cannot see it; the group check must, by a margin of at
// least MIN_GROUP_MISS points in some group.
const MIN_GROUP_MISS = 1;

function parseArgs(argv) {
  const args = {
    json: false,
    assertGood: false,
    assertBad: false,
    simulate: null,
    scoring: "ppr",
    teams: 12,
    source: SIM_DEFAULT_SOURCE,
    minGroupMiss: MIN_GROUP_MISS,
    fixtureDir: path.join(ROOT, "data", "fixtures", "current"),
  };
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === "--json") args.json = true;
    else if (arg === "--assert-good") args.assertGood = true;
    else if (arg === "--assert-bad") args.assertBad = true;
    else if (arg === "--simulate") args.simulate = argv[++i];
    else if (arg === "--scoring") args.scoring = argv[++i];
    else if (arg === "--teams") args.teams = Number(argv[++i]);
    else if (arg === "--source") args.source = argv[++i];
    else if (arg === "--min-group-miss") args.minGroupMiss = Number(argv[++i]);
    else if (arg === "--fixture-dir") args.fixtureDir = path.resolve(argv[++i]);
    else if (arg === "--help" || arg === "-h") {
      usage();
      process.exit(0);
    } else {
      throw new Error(`Unknown argument: ${arg}`);
    }
  }
  return args;
}

function usage() {
  console.log(`Usage: node tools/guard_harness.mjs [--json] [--assert-good] [--simulate espn-anchor --assert-bad]

Runs the browser curve-widget guard math in Node against data/fixtures/current.

Options:
  --assert-good              fail unless the current fixedPieIndexed guard passes
  --simulate espn-anchor     price one source's groups at ESPN's own weights
                             (the retired anchor rule) instead of the DDF weights
  --assert-bad               fail unless the simulated state fails the guard by
                             at least --min-group-miss points in some group
  --min-group-miss N         default ${MIN_GROUP_MISS}
  --fixture-dir PATH         read comparison-sources-data.json and players.json from PATH
  --scoring KEY              standard, half_ppr, or ppr (default ppr)
  --teams N                  8, 10, 12, or 14 (default 12)
  --source KEY               source for the simulation (default cbs)
  --json                     print machine-readable JSON`);
}

class FakeClassList {
  constructor(owner) {
    this.owner = owner;
    this.values = new Set();
  }
  add(...names) {
    names.forEach(name => this.values.add(name));
    this.owner._className = [...this.values].join(" ");
  }
  remove(...names) {
    names.forEach(name => this.values.delete(name));
    this.owner._className = [...this.values].join(" ");
  }
  toggle(name, force) {
    const enabled = force === undefined ? !this.values.has(name) : Boolean(force);
    if (enabled) this.add(name);
    else this.remove(name);
    return enabled;
  }
  contains(name) {
    return this.values.has(name);
  }
}

class FakeElement {
  constructor(tagName = "div", id = null, documentRef = null) {
    this.tagName = String(tagName).toUpperCase();
    this.id = id || "";
    this.ownerDocument = documentRef;
    this.children = [];
    this.parentNode = null;
    this.dataset = {};
    this.style = {};
    this.attributes = {};
    this._className = "";
    this.classList = new FakeClassList(this);
    this.textContent = "";
    this._innerHTML = "";
    this.value = "";
    this.checked = false;
    this.disabled = false;
    this.type = "";
    this.title = "";
    this.clientWidth = this.tagName === "CANVAS" ? 960 : 0;
    this.clientHeight = this.tagName === "CANVAS" ? 520 : 0;
    this.width = this.clientWidth;
    this.height = this.clientHeight;
  }
  get className() {
    return this._className;
  }
  set className(value) {
    this._className = String(value || "");
    this.classList.values = new Set(this._className.split(/\s+/).filter(Boolean));
  }
  get innerHTML() {
    return this._innerHTML;
  }
  set innerHTML(value) {
    this._innerHTML = String(value || "");
    this.children = [];
  }
  append(...nodes) {
    nodes.flat().forEach(node => this.appendChild(node));
  }
  appendChild(node) {
    if (node == null || typeof node === "string") return node;
    node.parentNode = this;
    this.children.push(node);
    return node;
  }
  replaceChildren(...nodes) {
    this.children = [];
    this.append(...nodes);
  }
  remove() {
    if (!this.parentNode) return;
    this.parentNode.children = this.parentNode.children.filter(child => child !== this);
    this.parentNode = null;
  }
  setAttribute(name, value) {
    this.attributes[name] = String(value);
    if (name === "id") this.id = String(value);
    if (name === "type") this.type = String(value);
  }
  getAttribute(name) {
    return this.attributes[name] ?? null;
  }
  removeAttribute(name) {
    delete this.attributes[name];
  }
  toggleAttribute(name, force) {
    const enabled = force === undefined ? !(name in this.attributes) : Boolean(force);
    if (enabled) this.attributes[name] = "";
    else delete this.attributes[name];
    return enabled;
  }
  addEventListener() {}
  removeEventListener() {}
  focus() {}
  click() {}
  closest() {
    return null;
  }
  getBoundingClientRect() {
    return {left: 0, top: 0, width: this.clientWidth, height: this.clientHeight};
  }
  getContext() {
    return new Proxy({}, {
      get(target, prop) {
        if (prop in target) return target[prop];
        return () => {};
      },
      set(target, prop, value) {
        target[prop] = value;
        return true;
      },
    });
  }
  matches(selector) {
    if (selector === "button") return this.tagName === "BUTTON";
    if (selector === "input[type=checkbox]") return this.tagName === "INPUT" && this.type === "checkbox";
    if (selector.startsWith(".")) return this.classList.contains(selector.slice(1));
    if (selector.startsWith("#")) return this.id === selector.slice(1);
    return this.tagName.toLowerCase() === selector.toLowerCase();
  }
  querySelectorAll(selector) {
    const out = [];
    const visit = node => {
      if (node.matches?.(selector)) out.push(node);
      node.children?.forEach(visit);
    };
    this.children.forEach(visit);
    return out;
  }
  querySelector(selector) {
    if (selector.startsWith("#") && this.ownerDocument) {
      return this.ownerDocument.getElementById(selector.slice(1));
    }
    return this.querySelectorAll(selector)[0] || null;
  }
}

class FakeDocument {
  constructor(playersPayload) {
    this.elements = new Map();
    this.documentElement = new FakeElement("html", null, this);
    this.body = new FakeElement("body", null, this);
    this.playersPayload = playersPayload;
  }
  createElement(tagName) {
    return new FakeElement(tagName, null, this);
  }
  getElementById(id) {
    if (!this.elements.has(id)) {
      const tag = id === "chart" ? "canvas" : id === "players-data" ? "script" : "div";
      const el = new FakeElement(tag, id, this);
      if (id === "players-data") el.textContent = JSON.stringify(this.playersPayload);
      this.elements.set(id, el);
    }
    return this.elements.get(id);
  }
  querySelector(selector) {
    if (selector.startsWith("#")) return this.getElementById(selector.slice(1));
    return null;
  }
  querySelectorAll() {
    return [];
  }
}

function readJson(file) {
  return JSON.parse(fs.readFileSync(file, "utf8"));
}

function setupWidgetEnvironment(fixtureDir) {
  const players = readJson(path.join(fixtureDir, "players.json"));
  const comparisonPath = path.join(fixtureDir, "comparison-sources-data.json");
  const adjustmentPath = path.join(ROOT, "app", "trade-value-chart", "assets", "adjustment-inputs.json");

  globalThis.window = globalThis;
  globalThis.__guardHarnessConsole = {errors: [], warnings: []};
  console.error = (...args) => {
    globalThis.__guardHarnessConsole.errors.push(args.map(String).join(" "));
    if (process.env.GUARD_HARNESS_VERBOSE) REAL_CONSOLE_ERROR(...args);
  };
  console.warn = (...args) => {
    globalThis.__guardHarnessConsole.warnings.push(args.map(String).join(" "));
    if (process.env.GUARD_HARNESS_VERBOSE) REAL_CONSOLE_WARN(...args);
  };
  globalThis.document = new FakeDocument(players);
  globalThis.devicePixelRatio = 1;
  globalThis.visualViewport = {width: 1200, height: 800, offsetLeft: 0, offsetTop: 0};
  globalThis.matchMedia = () => ({matches: false, addEventListener() {}, removeEventListener() {}});
  globalThis.CustomEvent = class CustomEvent {
    constructor(type, options = {}) {
      this.type = type;
      this.detail = options.detail;
    }
  };
  globalThis.addEventListener = () => {};
  globalThis.removeEventListener = () => {};
  globalThis.dispatchEvent = () => true;
  globalThis.fetch = async url => {
    const name = String(url).split("?")[0];
    const file = name.endsWith("comparison-sources-data.json")
      ? comparisonPath
      : name.endsWith("adjustment-inputs.json")
        ? adjustmentPath
        : null;
    if (!file || !fs.existsSync(file)) {
      return {ok: false, status: 404, json: async () => ({})};
    }
    return {ok: true, status: 200, json: async () => readJson(file)};
  };
}

async function loadWidget(fixtureDir) {
  setupWidgetEnvironment(fixtureDir);
  require(path.join(ROOT, "app", "trade-value-chart", "assets", "value-model.js"));
  require(path.join(ROOT, "app", "trade-value-chart", "assets", "product-data.js"));
  require(path.join(ROOT, "app", "trade-value-chart", "assets", "curve-widget.js"));
  for (let i = 0; i < 100; i += 1) {
    if (globalThis.TradeValueCurveHarness) return globalThis.TradeValueCurveHarness;
    await new Promise(resolve => setTimeout(resolve, 25));
  }
  const status = globalThis.document.getElementById("curve-status").innerHTML;
  throw new Error(`curve widget harness surface did not initialize${status ? `: ${status}` : ""}`);
}

function round(value, digits = 6) {
  return Number.isFinite(Number(value)) ? Number(Number(value).toFixed(digits)) : value;
}

function normalizeCheck(check) {
  if (!check) return null;
  const groups = {};
  Object.entries(check.groups || {}).forEach(([g, row]) => {
    groups[g] = {total: round(row.total, 4), budget: round(row.budget, 4), miss: round(row.total - row.budget, 4)};
  });
  return {
    source: check.source,
    basis: check.basis,
    n: check.n,
    total: round(check.total),
    target: round(check.target),
    delta: round(check.delta),
    groupsOk: check.groupsOk,
    ok: check.ok,
    groups,
  };
}

function fixedPieSummary(diagnostics) {
  return {
    ok: diagnostics.ok,
    tolerance: diagnostics.tolerance,
    pie: diagnostics.pie,
    checks: diagnostics.checks.map(normalizeCheck),
    indexed: diagnostics.indexed,
  };
}

let SIM_KEY = SIM_DEFAULT_SOURCE;
function simCheck(summary) {
  return summary.checks.find(check => check && check.source === SIM_KEY);
}

function assertGood(summary) {
  if (!summary.ok) {
    throw new Error(`expected current fixedPieIndexed guard to pass: ${JSON.stringify(summary.checks.filter(c => !c.ok))}`);
  }
}

function largestGroupMiss(check) {
  return Math.max(0, ...Object.values(check?.groups || {}).map(row => Math.abs(row.miss)));
}

function assertBad(summary, minGroupMiss) {
  const check = simCheck(summary);
  if (!check || check.ok) {
    throw new Error(`expected simulated state to fail fixedPieIndexed: ${JSON.stringify(check)}`);
  }
  const miss = largestGroupMiss(check);
  if (!(miss >= minGroupMiss)) {
    throw new Error(`simulated miss ${miss} < ${minGroupMiss} points in every group`);
  }
}

// The retired anchor rule on one source: its eight groups paid at ESPN's own
// weights (budgets pie x ESPN's weight) at the source's own group totals.
function espnAnchorMap(H, source) {
  const result = H.pipeline();
  const src = result.sources[source];
  const espn = result.sources.espn;
  if (!src || !src.hasWeights) throw new Error(`no priced source ${source} to simulate`);
  if (!espn || !espn.weights) throw new Error("no ESPN weights to simulate the anchor rule with");
  const rate = g => src.groups[g] > 0 ? result.pie * espn.weights[g] / src.groups[g] : 0;
  const map = new Map();
  Object.entries(src.players).forEach(([playerKey, p]) => {
    map.set(Number(playerKey), rate(`${p.pos}|bench`) * p.benchSlice + rate(`${p.pos}|starter`) * p.starterSlice);
  });
  return map;
}

function printText(report) {
  const current = simCheck(report.current.fixedPie);
  console.log("Curve widget guard harness");
  console.log(`fixture: ${report.fixtureDir}`);
  console.log(`state: ${report.state.scoring}/${report.state.teams}, benchShare=${report.state.benchShare}`);
  console.log(`registry-derived source count: ${report.state.sourceCount}; active default count: ${report.state.activeCount}`);
  console.log(`current fixedPieIndexed: ${report.current.fixedPie.ok ? "PASS" : "FAIL"} (pie ${report.current.fixedPie.pie})`);
  if (current) console.log(`  ${SIM_KEY} total=${current.total} target=${current.target} groupsOk=${current.groupsOk}`);
  if (report.simulated) {
    const broken = simCheck(report.simulated.fixedPie);
    console.log(`simulated ${report.simulated.name}: ${report.simulated.fixedPie.ok ? "PASS (unexpected)" : "FAIL (expected)"}`);
    if (broken) {
      console.log(`  ${SIM_KEY} total=${broken.total} target=${broken.target} largest group miss=${largestGroupMiss(broken)}`);
      Object.entries(broken.groups).forEach(([g, row]) => console.log(`    ${g}: total=${row.total} budget=${row.budget}`));
    }
  }
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const H = await loadWidget(args.fixtureDir);
  if (globalThis.TradeValueCurveControls) {
    globalThis.TradeValueCurveControls.setScoring(args.scoring, false);
    globalThis.TradeValueCurveControls.setTeams(args.teams, false);
  }
  const currentFixedPie = fixedPieSummary(H.fixedPieDiagnostics());
  const report = {
    fixtureDir: path.relative(ROOT, args.fixtureDir) || ".",
    state: H.state(),
    chartHealthMessages: globalThis.__guardHarnessConsole,
    current: {fixedPie: currentFixedPie},
  };
  SIM_KEY = args.source;

  if (args.assertGood) assertGood(currentFixedPie);

  if (args.simulate) {
    if (args.simulate !== "espn-anchor") throw new Error(`unknown simulation: ${args.simulate}`);
    const brokenFixedPie = fixedPieSummary(H.fixedPieDiagnosticsForMap(args.source, espnAnchorMap(H, args.source)));
    report.simulated = {
      name: "espn-anchor",
      description: "Retired rule: one source's groups paid at ESPN's own weights instead of the averaged DDF weights",
      fixedPie: brokenFixedPie,
    };
    if (args.assertBad) assertBad(brokenFixedPie, args.minGroupMiss);
  } else if (args.assertBad) {
    throw new Error("--assert-bad requires --simulate espn-anchor");
  }

  if (args.json) console.log(JSON.stringify(report, null, 2));
  else printText(report);
}

main().catch(error => {
  REAL_CONSOLE_ERROR(error?.stack || error?.message || String(error));
  process.exit(1);
});
