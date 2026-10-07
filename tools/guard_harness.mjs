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
const EXPECTED_JEG5 = {
  // Re-pointed 2026-10-05 (JEG-392): after JEG-ECR-EXIT ESPN IS the primary
  // leg, so its published tiers equal the DDF training tiers and the ESPN
  // simulation moved the pie by only -1.35 (< tolerance 2) -- the guard could
  // no longer fail. The JEG-5 bug class (live cells partitioned by published
  // tiers instead of DDF training tiers) is now simulated on the CBS
  // adjusted map, where the tiers genuinely differ (22 mismatches) and the
  // broken state misses the fixed pie by ~78 (cf. the original JEG-5 -79.90).
  // The CBS check uses the shared-player basis, so only these fields exist.
  // Re-recorded 2026-10-07 (JEG332-STORED-DRIFT): CBS's 13-22 players at or
  // below the waiver line are now saved as 0 instead of the pie fallback and
  // the adjustment fit was rerun, so the simulated broken state now misses
  // the (unchanged) fixed pie by -38.1 (12/101 tier mismatches) instead of
  // +78.2. Still far outside the tolerance of 2: the guard still fails it.
  source: "cbs_adjusted",
  basis: "shared",
  shared: 114,
  total: 1931.76243,
  target: 1969.895514,
  delta: -38.133085,
};

function parseArgs(argv) {
  const args = {
    json: false,
    assertGood: false,
    assertBad: false,
    assertJeg5Recorded: false,
    simulate: null,
    scoring: "ppr",
    teams: 12,
    source: SIM_DEFAULT_SOURCE,
    fixtureDir: path.join(ROOT, "data", "fixtures", "current"),
  };
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === "--json") args.json = true;
    else if (arg === "--assert-good") args.assertGood = true;
    else if (arg === "--assert-bad") args.assertBad = true;
    else if (arg === "--assert-jeg5-recorded") args.assertJeg5Recorded = true;
    else if (arg === "--simulate") args.simulate = argv[++i];
    else if (arg === "--scoring") args.scoring = argv[++i];
    else if (arg === "--teams") args.teams = Number(argv[++i]);
    else if (arg === "--source") args.source = argv[++i];
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
  console.log(`Usage: node tools/guard_harness.mjs [--json] [--assert-good] [--simulate tier-mismatch --assert-bad]

Runs the browser curve-widget guard math in Node against data/fixtures/current.

Options:
  --assert-good              fail unless the current fixedPieIndexed guard passes
  --simulate tier-mismatch   simulate the old JEG-5 published-tier partition bug
  --assert-bad               fail unless the simulated state fails the guard
  --assert-jeg5-recorded     additionally require the recorded JEG-5 numbers
  --fixture-dir PATH         read comparison-sources-data.json and players.json from PATH
  --scoring KEY              standard, half_ppr, or ppr (default ppr)
  --teams N                  8, 10, 12, or 14 (default 12)
  --source KEY               raw source for simulation (default cbs)
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
  const perPos = {};
  for (const pos of POSITIONS) {
    const row = check.perPos?.[pos];
    if (row) perPos[pos] = {total: round(row.total, 2), pie: round(row.pie, 2), n: row.n};
  }
  return {
    source: check.source,
    basis: check.basis,
    shared: check.shared,
    total: round(check.total),
    target: round(check.target),
    delta: round(check.delta),
    ok: check.ok,
    n: check.n,
    rawTotal: check.rawTotal,
    displayScale: check.displayScale,
    scaleIsNull: check.scaleIsNull,
    liveCells: check.liveCells,
    bakedCells: check.bakedCells,
    perPos,
  };
}

function fixedPieSummary(diagnostics) {
  return {
    ok: diagnostics.ok,
    tolerance: diagnostics.tolerance,
    checks: diagnostics.checks.map(normalizeCheck),
  };
}

// The fixedPie check for the simulated source's map (was hard-wired to
// ESPN; see EXPECTED_JEG5). Set from --source in main().
let SIM_KEY = "cbs_adjusted";
function simCheck(summary) {
  return summary.checks.find(check => check && check.source === SIM_KEY);
}

function closeEnough(actual, expected, tolerance) {
  return Math.abs(Number(actual) - Number(expected)) <= tolerance;
}

function assertGood(summary) {
  if (!summary.ok) {
    throw new Error(`expected current fixedPieIndexed guard to pass: ${JSON.stringify(summary.checks)}`);
  }
}

function assertBad(summary, tierComparison) {
  const check = simCheck(summary);
  if (!check || check.ok) {
    throw new Error(`expected simulated state to fail fixedPieIndexed: ${JSON.stringify(check)}`);
  }
  if (!tierComparison || tierComparison.mismatches <= 0) {
    throw new Error(`expected simulated state to include tier mismatches: ${JSON.stringify(tierComparison)}`);
  }
}

function assertJEG5Recorded(summary) {
  const check = simCheck(summary);
  if (!check || check.ok) {
    throw new Error(`expected simulated JEG-5 state to fail fixedPieIndexed: ${JSON.stringify(check)}`);
  }
  const failures = [];
  if (check.source !== EXPECTED_JEG5.source) failures.push(`source ${check.source}`);
  if (check.basis !== EXPECTED_JEG5.basis) failures.push(`basis ${check.basis}`);
  if (check.shared !== EXPECTED_JEG5.shared) failures.push(`shared ${check.shared}`);
  for (const field of ["total", "target", "delta"]) {
    if (!closeEnough(check[field], EXPECTED_JEG5[field], 0.01)) failures.push(`${field} ${check[field]}`);
  }
  if (failures.length) {
    throw new Error(`simulated JEG-5 numbers drifted: ${failures.join("; ")}`);
  }
}

function printText(report) {
  const current = simCheck(report.current.fixedPie);
  console.log("Curve widget guard harness");
  console.log(`fixture: ${report.fixtureDir}`);
  console.log(`state: ${report.state.scoring}/${report.state.teams}, benchShare=${report.state.benchShare}`);
  console.log(`registry-derived source count: ${report.state.sourceCount}; active default count: ${report.state.activeCount}`);
  console.log(`current fixedPieIndexed: ${report.current.fixedPie.ok ? "PASS" : "FAIL"}`);
  if (current) {
    console.log(`  ${SIM_KEY} total=${current.total.toFixed(6)} target=${current.target.toFixed(2)} delta=${current.delta.toFixed(6)} scale=${current.displayScale} n=${current.n} liveCells=${current.liveCells} bakedCells=${current.bakedCells}`);
    for (const pos of POSITIONS) {
      const row = current.perPos[pos];
      if (row) console.log(`    ${pos}: total=${row.total.toFixed(2)} pie=${row.pie.toFixed(2)} n=${row.n}`);
    }
  }
  if (report.simulated) {
    const broken = simCheck(report.simulated.fixedPie);
    console.log(`simulated ${report.simulated.name}: ${report.simulated.fixedPie.ok ? "PASS (unexpected)" : "FAIL (expected)"}`);
    console.log(`  tier mismatches: ${report.simulated.tierComparison.mismatches}/${report.simulated.tierComparison.compared}`);
    if (broken) {
      console.log(`  ${SIM_KEY} total=${broken.total.toFixed(6)} target=${broken.target.toFixed(2)} delta=${broken.delta.toFixed(6)} scale=${broken.displayScale} n=${broken.n} liveCells=${broken.liveCells} bakedCells=${broken.bakedCells}`);
      for (const pos of POSITIONS) {
        const row = broken.perPos[pos];
        if (row) console.log(`    ${pos}: total=${row.total.toFixed(2)} pie=${row.pie.toFixed(2)} n=${row.n}`);
      }
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

  if (args.assertGood) assertGood(currentFixedPie);

  if (args.simulate) {
    if (args.simulate !== "tier-mismatch") throw new Error(`unknown simulation: ${args.simulate}`);
    const source = args.source;
    const mapKey = source === "espn" ? "espn" : `${source}_adjusted`;
    SIM_KEY = mapKey;
    const cells = H.refitLiveCells().filter(cell => cell.source === source);
    const brokenMap = H.buildLiveAdjustedMap(source, cells, {tierPartition: "published"});
    const brokenFixedPie = fixedPieSummary(H.fixedPieDiagnosticsForMap(mapKey, brokenMap));
    const tierComparison = H.tierPartitionComparison(source);
    report.simulated = {
      name: "tier-mismatch",
      description: "JEG-5 old bug: apply live cells with published-value tiers instead of DDF training tiers",
      fixedPie: brokenFixedPie,
      tierComparison,
    };
    if (args.assertBad) assertBad(brokenFixedPie, tierComparison);
    if (args.assertJeg5Recorded) assertJEG5Recorded(brokenFixedPie);
  } else if (args.assertBad || args.assertJeg5Recorded) {
    throw new Error("--assert-bad/--assert-jeg5-recorded require --simulate tier-mismatch");
  }

  if (args.json) console.log(JSON.stringify(report, null, 2));
  else printText(report);
}

main().catch(error => {
  REAL_CONSOLE_ERROR(error?.stack || error?.message || String(error));
  process.exit(1);
});
