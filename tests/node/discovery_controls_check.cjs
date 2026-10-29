// JEG-1320: one stored record for the finders' discovery controls (app/v2/discovery-controls.js).
// Run: node tests/node/discovery_controls_check.cjs   (prints one line per case; exits non-zero if any case fails)
//
// Normalizing each route's stored shape gives the values that route uses today, and a case fails when either route's
// default would change (the workspace defaults, the finder page's starting state, or the league finder's search call).
"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const V2 = path.join(__dirname, "..", "..", "app", "v2");
const D = require(path.join(V2, "discovery-controls.js"));
const W = require(path.join(V2, "workspace.js"));
const T = require(path.join(V2, "trade-context.js"));
const F = require(path.join(V2, "finder.js"));

const cases = [];
const test = (name, fn) => cases.push([name, fn]);

// Today's defaults, written out (docs/specs/trade-page-parity.md 2.2): size 2, keep flags on, guardrails off,
// viable only off, filters all / all / 0 / 0, force fits shown.
const TODAY = {version: 1, maxSize: 2, keepMine: true, keepTheirs: true, protectedPositions: [],
  minBackups: {QB: 0, RB: 0, WR: 0, TE: 0}, minDdfEdge: 0, minUserLineupGain: null, minTheirLineupGain: null,
  viableOnly: false, filters: {fit: "all", opponent: "all", minCapture: 0, minCharts: 0}, hideForce: false};
const QUERY = "scoring=half_ppr&teams=12&roster=QB1.RB2.WR2.TE1.FLEX1.SF0.BN6";
const env = () => ({common: T.commonFromPage({leagueQuery: QUERY}), provenance: "saved"});
function workspace(ui) {
  let ws = W.newWorkspace({id: "lg", name: "League", now: 1});
  ws = W.ops.addTeam(ws, "Alpha", {id: "tA", entries: [{key: "101", name: "Qa", pos: "QB"}], now: 1, mine: true});
  ws = W.ops.addTeam(ws, "Bravo", {id: "tB", entries: [{key: "201", name: "Qb", pos: "QB"}], now: 1});
  return ui ? W.ops.setUi(ws, ui) : ws;
}
const plain = value => JSON.parse(JSON.stringify(value));
const SET_GUARDRAILS = {maxSize: 4, keepMine: false, keepTheirs: true, protectedPositions: ["RB", "TE"],
  minBackups: {QB: 0, RB: 2, WR: 1, TE: 0}, minDdfEdge: 1.5, minUserLineupGain: 0, minTheirLineupGain: 2.5};
const SET_LEAGUE = {maxSize: 3, hideForce: true, filters: {fit: "naturalMarket", opponent: "tB", minCapture: 3, minCharts: 2}};

// ---------- defaults: a change on either route fails here ----------
test("the shared defaults are today's defaults", () => {
  assert.deepEqual(plain(D.DEFAULTS), TODAY);
  assert.ok(Object.isFrozen(D.DEFAULTS) && Object.isFrozen(D.DEFAULTS.filters) && Object.isFrozen(D.DEFAULTS.minBackups));
});
test("your-team finder: a new league's saved settings normalize to today's defaults", () => {
  const ws = W.newWorkspace({id: "lg", now: 1});
  assert.deepEqual(plain(D.fromPair(ws.ui.finderSettings)), TODAY);
  assert.deepEqual(plain(D.fromPair(W.normalizeFinderSettings(null))), TODAY);
  // Same values the TradeContext adapter hands the pair route (trade-context.js routeControls).
  const finder = T.fromPair(env(), ws, {}, ws.ui.finderSettings).controls.finder;
  const record = D.fromPair(finder);
  Object.keys(finder).forEach(key => assert.deepEqual(record[key], finder[key], key));
});
test("your-team finder: the page's starting state (no saved league) is today's default", () => {
  // finder.js starts from this literal when no workspace store is loaded. Changing it is a default change.
  const src = fs.readFileSync(path.join(V2, "finder.js"), "utf8");
  const start = src.match(/const S = \{mine: \[\], theirs: \[\],[\s\S]*?viableOnly: (true|false)\};/);
  assert.ok(start, "finder.js page state literal not found");
  const text = start[0];
  assert.ok(text.includes("maxSize: 2, keepMine: true, keepTheirs: true"), "package size 2 and both keep flags on");
  assert.ok(text.includes("guardrails: {protectedPositions: [], minBackups: {QB: 0, RB: 0, WR: 0, TE: 0}, minDdfEdge: 0, minUserLineupGain: null, minTheirLineupGain: null}"),
    "guardrails off");
  assert.equal(start[1], "false", "viable only starts off");
});
test("league finder: a new league's ui normalizes to today's defaults", () => {
  const ws = W.newWorkspace({id: "lg", now: 1});
  assert.deepEqual(plain(D.fromLeague(ws.ui)), TODAY);
  const ctl = T.fromLeague(env(), workspace()).controls;
  const record = D.fromLeague(workspace().ui);
  ["maxSize", "keepMine", "keepTheirs", "hideForce", "filters"].forEach(key => assert.deepEqual(record[key], ctl[key], key));
});
test("league finder: its search still runs at ui.maxSize || 2 with both keep flags on", () => {
  // league.js pairs every opponent with this call. Changing it is a default change for the league route.
  const src = fs.readFileSync(path.join(V2, "league.js"), "utf8");
  assert.ok(src.includes("const maxSize = ws.ui.maxSize || 2;"), "league size read");
  assert.ok(/market: ctx\.market, maxSize, keepMine: true, keepTheirs: true\}/.test(src), "league keep flags hard-coded on");
  assert.ok(src.includes('[[2, "Up to 2-for-2"], [3, "Up to 3-for-3"], [4, "Up to 4-for-4"]], ws.ui.maxSize || 2'), "league size menu 2 to 4, default 2");
  assert.deepEqual(D.LEAGUE_SIZES, [2, 3, 4]);
});

// ---------- each route's stored shape gives today's values ----------
test("your-team finder: set guardrails, size and keep flags come through unchanged", () => {
  const ws = workspace({finderSettings: W.normalizeFinderSettings(SET_GUARDRAILS)});
  const record = D.fromPair(ws.ui.finderSettings, {viableOnly: true});
  assert.equal(record.maxSize, 4);
  assert.equal(record.keepMine, false);
  assert.equal(record.keepTheirs, true);
  assert.deepEqual(plain(record.protectedPositions), ["RB", "TE"]);
  assert.deepEqual(plain(record.minBackups), {QB: 0, RB: 2, WR: 1, TE: 0});
  assert.equal(record.minDdfEdge, 1.5);
  assert.equal(record.minUserLineupGain, 0, "a real 0 minimum stays 0, not off");
  assert.equal(record.minTheirLineupGain, 2.5);
  assert.equal(record.viableOnly, true, "viable only comes from the page's session state");
  // The pair finder has no list filters today: they stay at their defaults even if the league ui holds some.
  assert.deepEqual(plain(record.filters), TODAY.filters);
  assert.equal(record.hideForce, false);
  const finder = T.fromPair(env(), ws, {}, ws.ui.finderSettings).controls.finder;
  Object.keys(finder).forEach(key => assert.deepEqual(plain(record[key]), plain(finder[key]), key));
});
test("your-team finder: size 1 (1-for-1) is kept; out-of-range sizes fall back to 2", () => {
  assert.equal(D.fromPair({maxSize: 1}).maxSize, 1);
  [0, 5, "3", null, 2.5].forEach(size => assert.equal(D.fromPair({maxSize: size}).maxSize, 2, String(size)));
});
test("league finder: size, filters and force come through; it ignores the pair finder's guardrails and keep flags", () => {
  const ws = workspace({...SET_LEAGUE, finderSettings: W.normalizeFinderSettings(SET_GUARDRAILS)});
  const record = D.fromLeague(ws.ui);
  assert.equal(record.maxSize, 3);
  assert.equal(record.hideForce, true);
  assert.deepEqual(plain(record.filters), SET_LEAGUE.filters);
  // Today the league finder searches with both keep flags on and never reads ui.finderSettings.
  assert.equal(record.keepMine, true);
  assert.equal(record.keepTheirs, true);
  assert.deepEqual(plain(D.searchOf(record).guardrails), {protectedPositions: [], minBackups: TODAY.minBackups, minDdfEdge: 0,
    minUserLineupGain: null, minTheirLineupGain: null});
  assert.equal(record.viableOnly, false);
  const ctl = T.fromLeague(env(), ws).controls;
  ["maxSize", "keepMine", "keepTheirs", "hideForce", "filters"].forEach(key => assert.deepEqual(plain(record[key]), plain(ctl[key]), key));
});
test("league finder: an older saved naturalValue fit reads as naturalMarket; bad filters reset", () => {
  assert.equal(D.fromLeague({filters: {fit: "naturalValue"}}).filters.fit, "naturalMarket");
  const bad = D.fromLeague({maxSize: 7, hideForce: 0, filters: {fit: "best", opponent: null, minCapture: -3, minCharts: "x"}});
  assert.deepEqual(plain(bad.filters), TODAY.filters);
  assert.equal(bad.maxSize, 2);
  assert.equal(bad.hideForce, false);
});

// ---------- D3 pick A: the your-team finder's package size wins ----------
test("D3 A: finderSettings.maxSize wins and the league's ui.maxSize is dropped and reported", () => {
  const ws = workspace({...SET_LEAGUE, finderSettings: W.normalizeFinderSettings({...SET_GUARDRAILS, maxSize: 1})});
  const record = D.fromWorkspace(ws.ui);
  assert.equal(record.maxSize, 1);
  assert.deepEqual(plain(D.droppedOnMigration(ws.ui)), [{field: "maxSize", from: "ui.maxSize", value: 3, kept: 1, keptFrom: "ui.finderSettings.maxSize"}]);
  // Guardrails and keep flags from finderSettings; filters and force from the league's ui. Viable only is never saved.
  assert.equal(record.keepMine, false);
  assert.deepEqual(plain(record.protectedPositions), ["RB", "TE"]);
  assert.deepEqual(plain(record.filters), SET_LEAGUE.filters);
  assert.equal(record.hideForce, true);
  assert.equal(record.viableOnly, false);
});
test("D3 A: nothing is reported when both stored sizes agree, or on a new league", () => {
  assert.deepEqual(plain(D.droppedOnMigration(W.newWorkspace({now: 1}).ui)), []);
  assert.deepEqual(plain(D.droppedOnMigration(workspace({maxSize: 3, finderSettings: W.normalizeFinderSettings({maxSize: 3})}).ui)), []);
  assert.deepEqual(plain(D.fromWorkspace(W.newWorkspace({now: 1}).ui)), TODAY);
});
test("D3 A: an older saved league with only ui.maxSize loads at size 2 (the league value is dropped)", () => {
  // A workspace saved before finderSettings existed: normalizeWorkspace fills the default finderSettings.
  const old = W.normalizeWorkspace({id: "old", name: "Old", teams: [], ui: {maxSize: 4, hideForce: true}});
  assert.equal(D.fromWorkspace(old.ui).maxSize, 2);
  assert.equal(D.fromWorkspace(old.ui).hideForce, true);
  assert.deepEqual(plain(D.droppedOnMigration(old.ui)), [{field: "maxSize", from: "ui.maxSize", value: 4, kept: 2, keptFrom: "ui.finderSettings.maxSize"}]);
  // A raw ui with no finderSettings at all reads the same way.
  assert.equal(D.fromWorkspace({maxSize: 4}).maxSize, 2);
});

// ---------- the record out ----------
test("searchOf with the defaults leaves findTrades' guardrails inactive", () => {
  const search = D.searchOf(D.DEFAULTS);
  assert.deepEqual(Object.keys(search).sort(), ["guardrails", "keepMine", "keepTheirs", "maxSize"]);
  assert.deepEqual(Object.keys(search.guardrails), D.GUARDRAIL_KEYS);
  const keys = [F.OUR_KEY].concat(F.CHART_KEYS);
  const row = (key, pos, n) => ({player_key: key, name: key, pos, values: Object.fromEntries(keys.map(k => [k, n]))});
  const mine = [row("1", "RB", 10), row("2", "WR", 8)];
  const theirs = [row("3", "RB", 11), row("4", "WR", 7)];
  const res = F.findTrades(mine, theirs, {maxSize: search.maxSize, guardrails: search.guardrails, limit: 50});
  assert.ok(!("guardrailDropped" in res), "default guardrails are off, so findTrades applies none");
  const set = F.findTrades(mine, theirs, {maxSize: 2, guardrails: D.searchOf(D.fromPair({protectedPositions: ["RB"]})).guardrails, limit: 50});
  assert.ok("guardrailDropped" in set, "a set guardrail is active");
});
test("listingOf carries what only narrows the list", () => {
  const listing = D.listingOf(D.fromWorkspace(workspace(SET_LEAGUE).ui, {viableOnly: true}));
  assert.deepEqual(plain(listing), {filters: SET_LEAGUE.filters, hideForce: true, viableOnly: true});
});
test("toUiPatch saves through setUi and reads back as the same record (less session-only viable only)", () => {
  const record = D.normalize({...SET_GUARDRAILS, maxSize: 1, viableOnly: true, ...SET_LEAGUE, maxSize: 1});
  const patch = D.toUiPatch(record);
  assert.ok(!("maxSize" in patch), "D3 A: ui.maxSize is not written");
  assert.ok(!("viableOnly" in patch.finderSettings), "viable only is not saved");
  const ws = W.ops.setUi(W.newWorkspace({now: 1}), plain(patch));
  const back = D.fromWorkspace(W.normalizeWorkspace(plain(ws)).ui);
  assert.deepEqual(plain(back), {...plain(record), viableOnly: false});
});
test("normalize is idempotent and returns frozen records", () => {
  const record = D.normalize({...SET_GUARDRAILS, ...SET_LEAGUE});
  assert.deepEqual(plain(D.normalize(record)), plain(record));
  assert.ok(Object.isFrozen(record) && Object.isFrozen(record.protectedPositions));
  assert.throws(() => { "use strict"; record.maxSize = 3; });
  assert.deepEqual(plain(D.normalize("junk")), TODAY);
});

let failed = 0;
cases.forEach(([name, fn]) => {
  try { fn(); console.log(`ok   ${name}`); } catch (err) { failed += 1; console.log(`FAIL ${name}\n     ${err.message}`); }
});
console.log(`${cases.length - failed} passed, ${failed} failed`);
process.exit(failed ? 1 : 0);
