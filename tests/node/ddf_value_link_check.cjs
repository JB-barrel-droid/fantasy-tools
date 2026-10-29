// JEG-1225 (slice 4a): the shared value-context link format (app/v2/ddf-value-link.js), and the site's Overrides
// module reading and writing links through it. Run by tests/test_ddf_value_link.py.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const L = require("../../app/v2/ddf-value-link.js");

const ROOT = path.join(__dirname, "..", "..");
const plain = v => JSON.parse(JSON.stringify(v));

// ---------- basis ----------
assert.deepEqual(L.parseBasisParam("fantasycalc"), {mode: "single", source: "fantasycalc"});
assert.deepEqual(L.parseBasisParam("blend:espn.60_razzball.40"),
  {mode: "blend", sources: ["espn", "razzball"], weights: {espn: 60, razzball: 40}});
// Unknown sources and weights below 1 are left out; weights are whole percents, capped at 100.
assert.deepEqual(L.parseBasisParam("blend:espn.60_nope.20_cbs.0_usatoday.250_fantasypros.7.6"),
  {mode: "blend", sources: ["espn", "usatoday", "fantasypros"], weights: {espn: 60, usatoday: 100, fantasypros: 7}});
for (const bad of ["notasource", "blend:", "blend:nope.50", "blend:espn.0", "", null, undefined]) {
  assert.equal(L.parseBasisParam(bad), null, `basis ${bad}`);
}
assert.equal(L.formatBasisParam({mode: "default"}), null);
assert.equal(L.formatBasisParam(null), null);
assert.equal(L.formatBasisParam({mode: "single", source: "cbs"}), "cbs");
assert.equal(L.formatBasisParam({mode: "blend", sources: ["espn", "razzball"], weights: {espn: 60, razzball: 40}}),
  "blend:espn.60_razzball.40");
// getBasis() carries the same fields plus more; the extra fields are ignored.
assert.equal(L.formatBasisParam({mode: "blend", isDefault: false, sources: ["cbs"], weights: {cbs: 5}, label: "x"}), "blend:cbs.5");
for (const rec of [{mode: "single", source: "usatoday"}, {mode: "blend", sources: ["espn", "cbs", "fantasycalc"], weights: {espn: 10, cbs: 30, fantasycalc: 60}}]) {
  assert.deepEqual(L.parseBasisParam(L.formatBasisParam(rec)), rec, "basis round trip");
}

// ---------- overrides, plain ----------
assert.deepEqual(L.parseOvParam("101:58,202:+5,303:-3.26"),
  {101: 58, 202: {type: "adjustment", delta: 5}, 303: {type: "adjustment", delta: -3.3}});
// URLSearchParams reads "+" as a space: still an adjustment.
assert.deepEqual(L.parseOvParam(new URLSearchParams("ov=202:+5").get("ov")), {202: {type: "adjustment", delta: 5}});
// Put on the scale: an absolute over 100 is capped, below 0 and an adjustment of 0 are refused, junk is skipped.
assert.deepEqual(L.parseOvParam("101:140,202:-0,303:-1x,abc:5,404:,505:12.34"), {101: 100, 505: 12.3});
assert.deepEqual(L.parseOvParam("101:-400"), {101: {type: "adjustment", delta: -100}});
for (const bad of ["", null, "x", "abc:5", "101:", "z:@@@", "z2:%%"]) assert.equal(L.parseOvParam(bad), null, `ov ${bad}`);
assert.equal(L.formatOvParam({}), null);
assert.equal(L.formatOvParam({101: 58, 202: 42.5}), "101:58,202:42.5");
assert.equal(L.formatOvParam({101: 58, 202: {type: "adjustment", delta: 5}, 303: {type: "adjustment", delta: -3}}),
  "101:58,202:+5,303:-3");

// ---------- overrides, packed past PACK_AFTER ----------
const many = {};
for (let i = 0; i <= L.PACK_AFTER; i++) many[String(1000 + i * 7919)] = round(10 + i * 7.3);
function round(v) { return Math.round(v * 10) / 10; }
const packed = L.formatOvParam(many);
assert.ok(packed.startsWith("z:"), packed);
assert.deepEqual(L.parseOvParam(packed), many, "z: round trip");
const manyTyped = {...many, 99: {type: "adjustment", delta: -12.5}, 16777215: {type: "adjustment", delta: 100}};
const packedTyped = L.formatOvParam(manyTyped);
assert.ok(packedTyped.startsWith("z2:"), packedTyped);
assert.deepEqual(L.parseOvParam(packedTyped), manyTyped, "z2: round trip");
// A z: link written before JEG-1058 still reads (frozen bytes: 101 -> 58.0, 202 -> 42.5).
assert.deepEqual(L.parseOvParam("z:AABlAkQAAMoBqQ"), {101: 58, 202: 42.5});
assert.equal(L.formatOvParam({101: 58, 202: 42.5, 3: 1, 4: 2, 5: 3, 6: 4, 7: 5}).length > 2, true);
assert.equal(L.packOverrides({101: 58, 202: 42.5}), "AABlAkQAAMoBqQ");

// ---------- a whole link ----------
const ctx = L.readValueContext(new URLSearchParams("valuecontext=1&basis=blend%3Aespn.60_razzball.40&ov=202%3A%2B5"));
assert.deepEqual(plain(ctx), {present: true, complete: true, basisText: "blend:espn.60_razzball.40", ovText: "202:+5",
  basis: {mode: "blend", sources: ["espn", "razzball"], weights: {espn: 60, razzball: 40}},
  overrides: {202: {type: "adjustment", delta: 5}}, unread: []});
assert.deepEqual(plain(L.readValueContext({basis: "fantasycalc", ov: "101:58"})),
  {present: true, complete: false, basisText: "fantasycalc", ovText: "101:58",
    basis: {mode: "single", source: "fantasycalc"}, overrides: {101: 58}, unread: []});
assert.deepEqual(L.readValueContext(new URLSearchParams("valuecontext=1&basis=notasource&ov=x")).unread, ["basis", "ov"]);
assert.equal(L.readValueContext(new URLSearchParams("valuecontext=1")).present, true);
assert.equal(L.readValueContext(new URLSearchParams("give=101")).present, false);
assert.equal(L.readValueContext(null).present, false);
assert.equal(L.readValueContext({valuecontext: 1}).complete, true);

// ---------- the site's Overrides module reads and writes links through the shared module ----------
function overridesPage() {
  const storage = () => { const m = new Map(); return {getItem: k => (m.has(k) ? m.get(k) : null), setItem: (k, v) => m.set(k, String(v)), removeItem: k => m.delete(k)}; };
  const win = {document: {getElementById: () => null, querySelector: () => null, addEventListener() {}, dispatchEvent: () => true},
    localStorage: storage(), sessionStorage: storage(), addEventListener() {}, dispatchEvent: () => true,
    matchMedia: () => ({matches: false, addEventListener() {}}), CustomEvent: class {}, URLSearchParams, btoa, atob, console};
  win.window = win; win.self = win;
  vm.createContext(win);
  for (const file of ["app/v2/ddf-value-link.js", "app/v2/overrides.js"]) {
    vm.runInContext(fs.readFileSync(path.join(ROOT, file), "utf8"), win, {filename: file});
  }
  const engine = {basis: null, overrides: {}, getAllRows: () => [], searchPlayers: () => [],
    setBasis(b) { this.basis = b; return {ok: true}; }, setValueOverrides(v) { this.overrides = {...v}; },
    getBasis() {
      const b = this.basis;
      if (!b) return {isDefault: true, mode: "default", label: "our methodology"};
      return b.mode === "single" ? {isDefault: false, mode: "single", source: b.source, sources: [b.source], weights: {[b.source]: 100}, label: b.source}
        : {isDefault: false, mode: "blend", sources: b.sources, weights: b.weights, label: "blend"};
    }};
  win.DDFOverrides.boot(engine);
  return {O: win.DDFOverrides, engine};
}
{
  const {O, engine} = overridesPage();
  assert.equal(O.applyLink(new URLSearchParams("valuecontext=1&basis=blend%3Aespn.60_razzball.40&ov=202%3A%2B5")), true);
  assert.deepEqual(plain(engine.basis), {mode: "blend", sources: ["espn", "razzball"], weights: {espn: 60, razzball: 40}});
  assert.deepEqual(plain(engine.overrides), {202: {type: "adjustment", delta: 5}});
  // What it writes back reads to the same context.
  assert.deepEqual(plain(O.shareParams()), {basis: "blend:espn.60_razzball.40", ov: "202:+5", dropped: false});
  const back = new URLSearchParams(O.shareLink("#find-trade?mine=101").hash.split("?")[1]);
  assert.deepEqual(plain(L.readValueContext(back)), plain(ctx));
  // The same link again applies once.
  assert.equal(O.applyLink(new URLSearchParams("valuecontext=1&basis=blend%3Aespn.60_razzball.40&ov=202%3A%2B5")), false);
}
{
  // A complete link with a part it cannot read is skipped as before (JEG-1224 O7: slice 2 adds the note).
  const {O, engine} = overridesPage();
  assert.equal(O.applyLink(new URLSearchParams("valuecontext=1&basis=notasource")), false);
  assert.equal(engine.basis, null);
  // An unmarked legacy link with a readable basis and a bad ov applies the readable part.
  assert.equal(O.applyLink(new URLSearchParams("basis=fantasycalc&ov=x")), true);
  assert.deepEqual(plain(engine.basis), {mode: "single", source: "fantasycalc"});
  assert.deepEqual(plain(O.shareParams()), {basis: "fantasycalc", ov: null, dropped: false});
}

console.log("ok");
