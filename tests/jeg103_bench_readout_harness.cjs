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
const WIDGET = path.join(REPO, "app", "trade-value-chart", "assets", "curve-widget.js");
const VALUE_MODEL = path.join(REPO, "app", "trade-value-chart", "assets", "value-model.js");

// ---- Minimal DOM stub ----
// Only the elements the slider event path and syncWeightsReadout() actually
// touch. Everything else is a no-op.
function createReadoutEl() {
  return { textContent: "", _value: 0 };
}
function createRangeInput(min, max, step, value) {
  const el = {
    type: "range", min: String(min), max: String(max), step: String(step),
    value: String(value), disabled: false, title: "",
    setAttribute(k, v) { el[k] = v; },
    addEventListener(type, fn) { (el._listeners[type] = el._listeners[type] || []).push(fn); },
    _listeners: {},
    _fire(type) { (el._listeners[type] || []).forEach(fn => fn()); },
  };
  return el;
}
function makeBlock(initialShare) {
  const valueEl = { textContent: "" };
  const readout = { textContent: "", title: "" };
  const tick = { style: {}, title: "" };
  const fill = { style: {} };
  const resetBtn = { disabled: false, title: "", type: "button", textContent: "",
    addEventListener(type, fn) { (resetBtn._listeners[type] = resetBtn._listeners[type] || []).push(fn); },
    _listeners: {},
    _fire(type) { (resetBtn._listeners[type] || []).forEach(fn => fn()); },
  };
  const input = createRangeInput(0.01, 0.30, 0.001, initialShare);
  const block = {
    id: "benchShareBlock",
    querySelector(sel) {
      if (sel === "input[type=range]") return input;
      if (sel === ".bench-share-value") return valueEl;
      if (sel === ".bench-share-readout") return readout;
      if (sel === ".bench-share-tick") return tick;
      if (sel === ".fill") return fill;
      if (sel === ".bench-share-reset") return resetBtn;
      return null;
    },
  };
  return { block, input, valueEl, readout, tick, fill, resetBtn };
}

const weightsReadout = createReadoutEl();
const weightsBenchSlot = {
  innerHTML: "",
  appendChild(child) { this._child = child; },
};
const curveStatus = { innerHTML: "" };
const positionWeightControls = { innerHTML: "", replaceChildren() {}, appendChild() {}, querySelector() { return null; } };
const rosterShapeControls = { innerHTML: "", replaceChildren() {}, appendChild() {}, querySelector() { return null; } };
const elements = new Map([
  ["#weightsReadout", weightsReadout],
  ["#weightsBenchSlot", weightsBenchSlot],
  ["#curve-status", curveStatus],
  ["#positionWeightControls", positionWeightControls],
  ["#rosterShapeControls", rosterShapeControls],
]);
function $(sel) { return elements.get(sel) || null; }

// No-op stubs for everything else curve-widget.js touches during init.
const noopEl = {
  innerHTML: "", textContent: "", title: "", style: {}, value: "", checked: false,
  disabled: false, dataset: {}, classList: { add() {}, remove() {}, toggle() {} },
  replaceChildren() {}, appendChild() {}, addEventListener() {}, removeEventListener() {},
  setAttribute() {}, querySelector() { return null; }, querySelectorAll() { return []; },
};
function fillMissingElements() {
  // Any selector the widget asks for that we haven't stubbed: give it a noopEl.
  // We patch $() to lazily create noop elements for unknown ids so the init
  // doesn't crash on selectors we don't care about.
  const base = $;
  globalThis.window.$ = (sel) => {
    if (elements.has(sel)) return elements.get(sel);
    const el = Object.assign({}, noopEl, { id: sel.replace(/^#/, "") });
    elements.set(sel, el);
    return el;
  };
}

// document stub: createElement returns a fresh noop element; the benchShare
// block is built imperatively in makeRosterControls and appended to
// #weightsBenchSlot — we need that to be OUR block so the slider events fire
// on our input and the block querySelector returns our valueEl/readout/fill.
const documentStub = {
  createElement(tag) {
    if (tag === "input") return createRangeInput(0, 1, 0.001, 0.15);
    if (tag === "label" || tag === "span" || tag === "div" || tag === "p" || tag === "button") {
      const e = Object.assign({}, noopEl, {
        classList: { add() {}, remove() {}, toggle() {} },
        style: {}, dataset: {}, children: [],
        appendChild(child) { (this.children = this.children || []).push(child); return child; },
        append(...children) { (this.children = this.children || []).push(...children); },
      });
      return e;
    }
    return Object.assign({}, noopEl);
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
  globalThis.window.$ = $;
  fillMissingElements();
  // requestAnimationFrame / setTimeout exist natively in Node.
  globalThis.CustomEvent = class CustomEvent { constructor(name, init) { this.type = name; this.detail = init && init.detail; } };
  if (typeof globalThis.dispatchEvent !== "function") {
    globalThis.dispatchEvent = () => true;
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
  const afterSliderBlockValue = blockReadout.textContent;
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