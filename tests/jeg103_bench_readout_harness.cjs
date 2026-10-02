#!/usr/bin/env node
// JEG-103: Bench-share slider must update the Weights panel readout.
// Test harness: stubs a minimal DOM (just the elements the slider and
// syncWeightsReadout() touch), intercepts fetch() to serve the dist's data
// files locally, loads value-model.js and curve-widget.js, waits for init
// to complete, then fires a real slider 'input' event and asserts the
// #weightsReadout textContent reflects the new bench share.
//
// Output: JSON on stdout: {initialReadout, afterSliderReadout, afterDblclickReadout,
//                          afterResetButtonReadout, matches: {slider, dblclick, resetBtn}}
"use strict";
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const REPO = path.join(__dirname, "..");
const DIST_ASSETS = path.join(REPO, "dist", "assets");
// Canonical player records normally arrive as an embedded JSON blob in the
// page (#players-data). Serve the current chart fixture the same way.
const PLAYERS_JSON = path.join(REPO, "data", "fixtures", "current", "players.json");
const playersPayloadText = fs.readFileSync(PLAYERS_JSON, "utf8");
const playersDataEl = { textContent: playersPayloadText };
const WIDGET = path.join(REPO, "app", "trade-value-chart", "assets", "curve-widget.js");
const VALUE_MODEL = path.join(REPO, "app", "trade-value-chart", "assets", "value-model.js");

// ---- Minimal DOM stub ----
// Proxy-based elements: any unknown method is a no-op, property sets stick,
// addEventListener stores handlers (firable via _fire), and querySelector /
// querySelectorAll do a real deep search over appended children, so the
// widget-built bench-share block is queryable exactly like in a browser.
const _noopFn = () => undefined;
function matchesSel(node, sel) {
  if (!node || (typeof node !== "object" && typeof node !== "function")) return false;
  let v;
  const get = (k) => { try { v = node[k]; } catch (e) { v = undefined; } return (typeof v === "function" && !String(v).includes("[native")) ? undefined : v; };
  let m = sel.match(/^#([\w-]+)$/);
  if (m) return get("id") === m[1];
  m = sel.match(/^\.([\w-]+)$/);
  if (m) return String(get("className") || "").split(/\s+/).includes(m[1]);
  m = sel.match(/^(\w+)\[type=(\w+)\]$/);
  if (m) return String(get("tagName") || "").toUpperCase() === m[1].toUpperCase() && String(get("type") || "") === m[2];
  m = sel.match(/^(\w+)$/);
  if (m) return String(get("tagName") || "").toUpperCase() === m[1].toUpperCase();
  return false;
}
function deepFindAll(root, sel) {
  const out = [];
  const walk = (node) => {
    let kids = [];
    try { kids = node.children; } catch (e) { kids = []; }
    if (!Array.isArray(kids)) return;
    for (const c of kids) {
      if (matchesSel(c, sel)) out.push(c);
      walk(c);
    }
  };
  walk(root);
  return out;
}
function proxiedNoop(id, tagName) {
  const state = {
    id: id || "", tagName: (tagName || "div").toUpperCase(),
    innerHTML: "", textContent: "", title: "", value: "", checked: false,
    disabled: false, dataset: {}, style: {}, children: [], _listeners: {},
    classList: { add() {}, remove() {}, toggle() {}, contains() { return false; } },
  };
  return new Proxy(state, {
    get(t, prop) {
      if (prop in t) return t[prop];
      if (prop === "querySelector") return (sel) => deepFindAll(t, sel)[0] || null;
      if (prop === "querySelectorAll" || prop === "getElementsByTagName") return (sel) => deepFindAll(t, sel);
      if (prop === "closest") return () => null;
      if (prop === "getContext") return () => proxiedNoop(id + ".ctx", "canvasctx");
      if (prop === "addEventListener") return (type, fn) => { (t._listeners[type] = t._listeners[type] || []).push(fn); };
      if (prop === "removeEventListener") return () => {};
      if (prop === "_fire") return (type, ev) => { (t._listeners[type] || []).forEach(fn => fn(ev)); };
      if (prop === "appendChild" || prop === "append" || prop === "prepend") {
        return (...kids) => { t.children.push(...kids); return kids[0]; };
      }
      if (prop === "replaceChildren") return (...kids) => { t.children = [...kids]; };
      if (prop === Symbol.toPrimitive) return () => "";
      if (typeof prop === "string") return _noopFn;
      return undefined;
    },
    set(t, prop, v) { t[prop] = v; return true; },
  });
}
function createReadoutEl() {
  return { textContent: "", _value: 0, dataset: {} };
}
function createRangeInput(min, max, step, value) {
  const el = {
    tagName: "INPUT", type: "range", min: String(min), max: String(max), step: String(step),
    value: String(value), disabled: false, title: "", dataset: {},
    setAttribute(k, v) { el[k] = v; },
    addEventListener(type, fn) { (el._listeners[type] = el._listeners[type] || []).push(fn); },
    _listeners: {},
    _fire(type) { (el._listeners[type] || []).forEach(fn => fn()); },
  };
  return el;
}

// Static page elements the widget expects to exist. The widget's internal
// $("#...") resolves through the #curve-widget root stub, which consults
// this map first so identity is stable across queries.
const weightsReadout = createReadoutEl();
const weightsBenchSlot = proxiedNoop("weightsBenchSlot", "div");
weightsBenchSlot.appendChild = function (child) { this._child = child; this.children.push(child); return child; };
const curveStatus = { innerHTML: "", querySelector() { return null; }, querySelectorAll() { return []; },
  classList: { add() {}, remove() {}, toggle() {}, contains() { return false; } } };
const staticStub = (id) => proxiedNoop(id, "div");
const elements = new Map([
  ["#weightsReadout", weightsReadout],
  ["#weightsBenchSlot", weightsBenchSlot],
  ["#curve-status", curveStatus],
  ["#positionWeightControls", staticStub("positionWeightControls")],
  ["#rosterShapeControls", staticStub("rosterShapeControls")],
]);
function fillMissingElements() {
  // window.$ backs document.getElementById. Unknown ids get a stable
  // registered stub; the #curve-widget root consults the static map first
  // so the widget's own $("#weightsReadout") hits OUR readout object.
  const rootQuery = (rootEl) => (sel) => {
    if (elements.has(sel)) return elements.get(sel);
    const found = deepFindAll(rootEl, sel)[0];
    if (found) return found;
    const el = proxiedNoop(sel.replace(/^#/, ""), "div");
    elements.set(sel, el);
    return el;
  };
  globalThis.window.$ = (sel) => {
    if (elements.has(sel)) return elements.get(sel);
    const el = proxiedNoop(sel.replace(/^#/, ""), "div");
    elements.set(sel, el);
    if (sel === "#curve-widget") el.querySelector = rootQuery(el);
    return el;
  };
  // Mount the static page elements under the widget root so the widget's
  // own $("#benchShareBlock") deep search finds the REAL block the widget
  // appended to #weightsBenchSlot (same as in the browser).
  const root = globalThis.window.$("#curve-widget");
  for (const el of elements.values()) {
    if (el && el !== root && !root.children.includes(el)) root.children.push(el);
  }
}

// document stub: createElement returns a fresh noop element; the benchShare
// block is built imperatively in makeRosterControls and appended to
// #weightsBenchSlot — we need that to be OUR block so the slider events fire
// on our input and the block querySelector returns our valueEl/readout/fill.
const documentStub = {
  getElementById(id) {
    if (id === "players-data") return playersDataEl;
    return globalThis.window.$("#" + id);
  },
  createElement(tag) {
    if (tag === "input") return createRangeInput(0, 1, 0.001, 0.15);
    return proxiedNoop(tag, tag);
  },
  activeElement: null,
  querySelector() { return null; },
  querySelectorAll() { return []; },
};

// fetch() interception: serve the dist's data files so the widget's init
// can populate `comparison data` and `adjustmentInputs`.
async function fetchStub(url) {
  let file;
  if (url.includes("comparison-sources-data.json")) file = path.join(DIST_ASSETS, "comparison-sources-data.json");
  else if (url.includes("adjustment-inputs.json")) file = path.join(DIST_ASSETS, "adjustment-inputs.json");
  else return { ok: false, status: 404, json: async () => null };
  const text = fs.readFileSync(file, "utf8");
  return { ok: true, status: 200, json: async () => JSON.parse(text) };
}

// ---- Load value-model.js and curve-widget.js in a shared VM context ----
// Using vm.runInThisContext so window/globalThis aliases are honored.
function loadWidget() {
  const sources = [
    fs.readFileSync(VALUE_MODEL, "utf8"),
    fs.readFileSync(WIDGET, "utf8"),
  ];
  for (const src of sources) {
    vm.runInThisContext(src, { filename: "curve-widget.js" });
  }
}

async function waitForReady(timeoutMs = 10000) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    if (window.TradeValueTwoTierLive && typeof window.TradeValueTwoTierLive.setBenchShareFraction === "function") return true;
    await new Promise(r => setTimeout(r, 50));
  }
  return false;
}

async function main() {
  // Set up globals BEFORE loading the widget.
  globalThis.window = globalThis;
  globalThis.document = documentStub;
  globalThis.fetch = fetchStub;
  fillMissingElements();
  // requestAnimationFrame / setTimeout exist natively in Node.
  globalThis.CustomEvent = class CustomEvent { constructor(name, init) { this.type = name; this.detail = init && init.detail; } };
  if (typeof globalThis.dispatchEvent !== "function") {
    globalThis.dispatchEvent = () => true;
  }
  if (typeof globalThis.addEventListener !== "function") {
    globalThis.addEventListener = () => {};
  }
  if (typeof globalThis.removeEventListener !== "function") {
    globalThis.removeEventListener = () => {};
  }
  if (typeof globalThis.matchMedia !== "function") {
    globalThis.matchMedia = () => ({ matches: false, addEventListener() {}, removeEventListener() {} });
  }

  loadWidget();
  const ready = await waitForReady();
  if (!ready) {
    process.stdout.write(JSON.stringify({ error: "widget init did not expose setBenchShareFraction; check curve-status: " + (curveStatus.innerHTML || "") }));
    process.exit(1);
  }

  // After init, #weightsBenchSlot should hold the benchShareBlock built by
  // makeRosterControls. Grab the slider input from that block.
  const block = weightsBenchSlot._child;
  if (!block || !block.querySelector) {
    process.stdout.write(JSON.stringify({ error: "weightsBenchSlot has no block after init" }));
    process.exit(1);
  }
  const slider = block.querySelector("input[type=range]");
  const blockReadout = block.querySelector(".bench-share-readout");
  const resetBtn = block.querySelector(".bench-share-reset");
  const blockValue = block.querySelector(".bench-share-value");

  // Capture initial readout (should be 15.0%).
  const initialReadout = weightsReadout.textContent;

  // ---- TEST 1: slider input event updates #weightsReadout ----
  // Move slider to 0.20 (20%) and fire the input event.
  slider.value = "0.20";
  slider._fire("input");
  // Also fire 'change' (matches the production handler which listens to both).
  slider._fire("change");
  const afterSliderReadout = weightsReadout.textContent;
  const afterSliderBlockValue = blockValue.textContent;
  const sliderText = afterSliderReadout;
  const sliderMatches = /Bench 20\.0%/.test(sliderText);

  // ---- TEST 2: dblclick resets to 15% and syncs the readout ----
  slider._fire("dblclick");
  const afterDblclickReadout = weightsReadout.textContent;
  const dblclickMatches = /Bench 15\.0%/.test(afterDblclickReadout);

  // ---- TEST 3: Reset-to-15% button updates readout ----
  // Move slider away first, then click reset.
  slider.value = "0.25";
  slider._fire("input");
  resetBtn._fire("click");
  const afterResetButtonReadout = weightsReadout.textContent;
  const resetBtnMatches = /Bench 15\.0%/.test(afterResetButtonReadout);

  process.stdout.write(JSON.stringify({
    initialReadout,
    afterSliderReadout,
    afterDblclickReadout,
    afterResetButtonReadout,
    afterSliderBlockValue,
    matches: { slider: sliderMatches, dblclick: dblclickMatches, resetBtn: resetBtnMatches },
  }));
}

main().catch(e => {
  process.stdout.write(JSON.stringify({ error: String(e && e.stack || e) }));
  process.exit(1);
});