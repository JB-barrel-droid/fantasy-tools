// JEG-1229: shared trade preferences and the immutable TradeContext (app/v2/trade-context.js).
// Run: node tests/node/trade_context_check.cjs   (exits non-zero on the first failure; prints one line per case)
"use strict";
const assert = require("node:assert/strict");
const path = require("node:path");
const V2 = path.join(__dirname, "..", "..", "app", "v2");
const T = require(path.join(V2, "trade-context.js"));
const W = require(path.join(V2, "workspace.js"));
const F = require(path.join(V2, "finder.js"));

const cases = [];
const test = (name, fn) => cases.push([name, fn]);

// ---------- fixture: one league, three teams, the same explicit settings everywhere ----------
const entry = (key, name, pos) => ({key, name, pos});
const A = [entry("101", "Qa", "QB"), entry("102", "Ra1", "RB"), entry("103", "Ra2", "RB"), entry("104", "Wa1", "WR"),
  entry("105", "Wa2", "WR"), entry("106", "Ta", "TE"), entry("107", "Ra3", "RB"), entry("x:K:kicker a", "Kicker A", "K")];
const B = [entry("201", "Qb", "QB"), entry("202", "Rb1", "RB"), entry("203", "Rb2", "RB"), entry("204", "Wb1", "WR"),
  entry("205", "Wb2", "WR"), entry("206", "Tb", "TE"), entry("207", "Wb3", "WR")];
const C = [entry("301", "Qc", "QB"), entry("302", "Rc1", "RB")];
function workspace() {
  let ws = W.newWorkspace({id: "lg", name: "League", now: 1});
  ws = W.ops.addTeam(ws, "Alpha", {id: "tA", entries: A, now: 1, mine: true});
  ws = W.ops.addTeam(ws, "Bravo", {id: "tB", entries: B, now: 1});
  ws = W.ops.addTeam(ws, "Charlie", {id: "tC", entries: C, now: 1});
  return ws;
}
const QUERY = "scoring=half_ppr&teams=12&roster=QB1.RB2.WR2.TE1.FLEX1.SF0.BN6";
const VALUE = {basis: {mode: "blend", sources: ["fantasycalc", "espn"], weights: {fantasycalc: 60, espn: 40}}, values: {"102": 55.5, "204": {type: "adjustment", delta: -3}}};
const SOURCES = {fantasycalc: {available: true}, espn: {available: true}, cbsros: {available: false, reason: "not published this week"}, razzball: {held: true, reason: "held"}};
const common = () => T.commonFromPage({leagueQuery: QUERY, valueContext: VALUE, sources: SOURCES});
const env = () => ({common: common(), provenance: "saved"});
const deal = {give: ["102"], get: ["204"]};
// Engine-like rows for the real finder lineup math (values are fixture numbers, not site values).
const VALUES = {"101": 20, "102": 18, "103": 15, "104": 19, "105": 16, "106": 12, "107": 9, "201": 21, "202": 17, "203": 14,
  "204": 22, "205": 13, "206": 11, "207": 8};
const rows = roster => roster.filter(e => !e.key.startsWith("x:")).map(e => ({player_key: e.key, name: e.name, pos: e.pos, values: {ddf_value: VALUES[e.key]}}));
const SHAPE = {QB: 1, RB: 2, WR: 2, TE: 1, FLEX: 1, SUPERFLEX: 0};
function impact(context) {
  const mine = rows(context.teams.mine.roster);
  const theirs = rows((context.teams.theirs || context.teams.opponents.find(o => o.id === "tB")).roster);
  const by = new Map(mine.concat(theirs).map(r => [r.player_key, r]));
  const give = context.deal.give.map(k => by.get(k));
  const get = context.deal.get.map(k => by.get(k));
  return {mine: F.rosterImpact(mine, give, get, SHAPE, "ddf_value"), theirs: F.rosterImpact(theirs, get, give, SHAPE, "ddf_value")};
}

// ---------- cross-route common preferences ----------
test("the same explicit settings reach every route", () => {
  const ws = workspace();
  const e = env();
  const pair = T.fromPair(e, ws, {mineId: "tA", theirId: "tB", deal}, ws.ui.finderSettings);
  const league = T.fromLeague({...e, deal}, ws);
  const compare = T.fromCompare(e, ws, {give: deal.give, receive: deal.get}, {mineId: "tA", theirId: "tB"});
  assert.deepEqual(pair.common, league.common);
  assert.deepEqual(pair.common, compare.common);
  assert.equal(T.commonKey(pair), T.commonKey(league));
  assert.equal(T.commonKey(pair), T.commonKey(compare));
  assert.equal(pair.common.league.scoring, "half_ppr");
  assert.equal(pair.common.league.teams, 12);
  assert.deepEqual(pair.common.league.roster, {QB: 1, RB: 2, WR: 2, TE: 1, FLEX: 1, SUPERFLEX: 0, BENCH: 6});
  assert.deepEqual(pair.teams.mine.roster, compare.teams.mine.roster);
  assert.deepEqual(league.teams.mine.roster, compare.teams.mine.roster);
  // The readout key for the same explicit deal is the same on the pair finder and Compare (same two rosters).
  assert.equal(T.cacheKey(pair, "readout"), T.cacheKey(compare, "readout"));
  // On the league finder the deal's partner is the one opponent holding the received players; the rest do not count.
  assert.equal(T.dealPartner(league).id, "tB");
  assert.equal(T.cacheKey(league, "readout"), T.cacheKey(pair, "readout"));
  const noPartner = T.fromLeague({...e, deal: {give: ["102"], get: ["204", "302"]}}, ws);
  assert.equal(T.dealPartner(noPartner), null, "keys from two opponents have no single partner");
});
test("the real finder lineup math gives identical numbers on every route's context", () => {
  const ws = workspace();
  const e = env();
  const pair = T.fromPair(e, ws, {mineId: "tA", theirId: "tB", deal}, ws.ui.finderSettings);
  const league = T.fromLeague({...e, deal}, ws);
  const compare = T.fromCompare(e, ws, {give: deal.give, receive: deal.get}, {mineId: "tA", theirId: "tB"});
  const direct = {mine: F.rosterImpact(rows(A), [rows(A)[1]], [rows(B)[3]], SHAPE, "ddf_value"),
    theirs: F.rosterImpact(rows(B), [rows(B)[3]], [rows(A)[1]], SHAPE, "ddf_value")};
  assert.ok(Number.isFinite(direct.mine.starterDelta) && direct.mine.starterDelta !== 0, "the fixture trade moves starter value");
  assert.ok(Number.isFinite(direct.theirs.totalDelta) && direct.theirs.totalDelta !== 0);
  [pair, league, compare].forEach(ctx => {
    const got = impact(ctx);
    ["starterDelta", "benchDelta", "totalDelta", "spotsOpened"].forEach(field => {
      assert.equal(got.mine[field], direct.mine[field], `${ctx.route} mine ${field}`);
      assert.equal(got.theirs[field], direct.theirs[field], `${ctx.route} theirs ${field}`);
    });
    assert.equal(got.mine.after.total, direct.mine.after.total, ctx.route);
  });
});
test("Standard, Half PPR and PPR all read; an unknown scoring drops the whole league", () => {
  ["standard", "half_ppr", "ppr"].forEach(scoring => {
    assert.equal(T.commonFromPage({leagueQuery: `scoring=${scoring}&teams=10`}).league.scoring, scoring);
  });
  const bad = T.commonFromPage({leagueQuery: "scoring=superppr&teams=12"});
  assert.equal(bad.league, null);
  const badTeams = T.commonFromPage({leagueQuery: "scoring=ppr&teams=11"});
  assert.equal(badTeams.league, null, "an unsupported team count is not half-applied");
  assert.ok(badTeams.warnings.some(w => /teams/.test(w)));
});

// ---------- route-only controls ----------
test("route-only controls stay on their route", () => {
  let ws = workspace();
  ws = W.ops.setUi(ws, {maxSize: 4, rankBasis: "market", keepMine: false, filters: {fit: "natural", minCapture: 2}});
  ws = W.ops.setUi(ws, {finderSettings: W.normalizeFinderSettings({maxSize: 1, keepMine: false, protectedPositions: ["RB"], minBackups: {RB: 2}})});
  const e = env();
  const pair = T.fromPair(e, ws, {mineId: "tA", theirId: "tB"}, ws.ui.finderSettings);
  const league = T.fromLeague(e, ws);
  const compare = T.fromCompare(e, ws, {give: ["102"], receive: ["204"]}, {mineId: "tA", theirId: "tB"});
  assert.equal(pair.controls.finder.maxSize, 1);
  assert.equal(pair.controls.finder.keepMine, false);
  assert.equal(pair.controls.rankBasis, undefined);
  assert.equal(league.controls.maxSize, 4);
  assert.equal(league.controls.keepMine, true, "the league finder always keeps both lineups");
  assert.equal(league.controls.finder, undefined);
  assert.deepEqual(compare.controls, {});
  assert.equal(compare.capabilities.discovery, false);
  assert.equal(T.cacheKey(compare, "discovery"), null, "Compare has no discovery search");
  const withControls = T.createContext({route: "compare", common: e.common, controls: {maxSize: 3}});
  assert.deepEqual(withControls.controls, {});
  assert.ok(withControls.warnings.includes("compare: discovery controls ignored"));
});
test("a changed control changes only its own route's discovery key", () => {
  const ws = workspace();
  const e = env();
  const pair = T.fromPair(e, ws, {mineId: "tA", theirId: "tB", deal}, ws.ui.finderSettings);
  const pair3 = T.fromPair(e, ws, {mineId: "tA", theirId: "tB", deal}, {...ws.ui.finderSettings, maxSize: 3});
  assert.notEqual(T.cacheKey(pair, "discovery"), T.cacheKey(pair3, "discovery"));
  assert.equal(T.cacheKey(pair, "readout"), T.cacheKey(pair3, "readout"), "a search control never changes the explicit readout");
  const league = T.fromLeague(e, ws);
  const leagueFiltered = T.fromLeague(e, W.ops.setUi(ws, {filters: {minCharts: 3}}));
  assert.notEqual(T.cacheKey(league, "discovery"), T.cacheKey(leagueFiltered, "discovery"));
  assert.equal(T.cacheKey(pair, "discovery"), T.cacheKey(T.fromPair(e, W.ops.setUi(ws, {filters: {minCharts: 3}}), {mineId: "tA", theirId: "tB", deal}, ws.ui.finderSettings), "discovery"),
    "a league filter does not reach the pair finder");
  assert.notEqual(T.cacheKey(pair, "discovery"), T.cacheKey(T.fromLeague(e, ws), "discovery"), "routes never share a discovery cache entry");
});
test("route discrepancies are reported, not unified", () => {
  const ids = T.ROUTE_DISCREPANCIES.map(d => d.id);
  assert.deepEqual(ids, ["package-size-storage", "keep-starters", "guardrails", "opponent-default", "ranking-basis"]);
  const ws = workspace();
  assert.ok(T.fromCompare(env(), ws, {}, {}).discrepancies.includes("opponent-default"));
  assert.ok(T.fromLeague(env(), ws).discrepancies.includes("package-size-storage"));
  assert.ok(Object.isFrozen(T.ROUTE_DISCREPANCIES[0]));
});

// ---------- zero, missing, unavailable ----------
test("zero is a value, missing is not, unavailable and held stay distinct", () => {
  const c = T.normalizeCommon({league: {scoring: "ppr", shares: {QB: 0, RB: 0.5, WR: 0.4, TE: 0.1}},
    overrides: {"101": 0, "102": null, "103": {type: "adjustment", delta: 0}, "104": {type: "adjustment", delta: 2.5}, abc: 4},
    sources: {fantasycalc: {available: true}, espn: {available: false, reason: "not loaded"}, cbsros: {held: true}, usatoday: "?"}});
  assert.deepEqual(c.valuation.overrides, {"101": 0, "104": {type: "adjustment", delta: 2.5}});
  assert.equal(c.warnings.filter(w => /overrides/.test(w)).length, 3);
  assert.deepEqual(c.league.shares, {QB: 0, RB: 0.5, WR: 0.4, TE: 0.1});
  assert.equal(c.sources.fantasycalc.status, "available");
  assert.deepEqual(c.sources.espn, {status: "unavailable", reason: "not loaded", version: null});
  assert.equal(T.normalizeCommon({sources: {fantasycalc: {available: true, version: "2026-10-29"}}}).sources.fantasycalc.version, "2026-10-29",
    "a source's own data version is kept, so a rebuilt source is a different source state");
  assert.equal(c.sources.cbsros.status, "held");
  assert.equal(c.sources.usatoday.status, "unknown");
  assert.equal(c.sources.razzball, undefined, "a source the page did not report is absent, not assumed available");
  const none = T.normalizeCommon({});
  assert.equal(none.league, null);
  assert.equal(none.valuation.basis, null, "no basis stated is different from an explicit default");
  assert.equal(none.valuation.overrides, null);
  assert.deepEqual(T.normalizeCommon({basis: {mode: "default"}, overrides: {}}).valuation, {basis: {mode: "default"}, overrides: {}});
});
test("empty and missing teams are explicit", () => {
  let ws = W.ops.addTeam(workspace(), "Empty", {id: "tE", entries: [], now: 1});
  const ctx = T.fromPair(env(), ws, {mineId: "tA", theirId: "tE"}, null);
  assert.deepEqual(ctx.teams.theirs.roster, []);
  assert.equal(ctx.teams.theirs.missing, false);
  const none = T.fromPair(env(), ws, {}, null);
  assert.equal(none.teams.mine, null);
  assert.equal(none.teams.theirs, null, "no guessed opponent");
});

test("a deal keeps explicit keys: no duplicates, a key on both sides stays on give", () => {
  assert.deepEqual(T.normalizeDeal({give: ["1", {key: "2"}, "1", "bad key!"], receive: ["2", "3", 3]}), {give: ["1", "2"], get: ["3"]});
  assert.equal(T.normalizeDeal({give: [], get: []}), null);
  assert.equal(T.normalizeDeal(null), null);
});

// ---------- deterministic keys ----------
test("cache keys are deterministic and only follow what changes a result", () => {
  const ws = workspace();
  const e = env();
  const base = T.fromCompare(e, ws, {give: ["102", "103"], receive: ["204"]}, {mineId: "tA", theirId: "tB"});
  // Same content built in a different order: query parameters, blend sources, override keys, roster order, deal order.
  const sameCommon = T.commonFromPage({leagueQuery: "roster=QB1.RB2.WR2.TE1.FLEX1.SF0.BN6&teams=12&scoring=half_ppr",
    valueContext: {basis: {mode: "blend", sources: ["espn", "fantasycalc"], weights: {espn: 40, fantasycalc: 60}}, values: {"204": {type: "adjustment", delta: -3}, "102": 55.5}},
    sources: SOURCES});
  const reordered = T.fromCompare({common: sameCommon}, W.ops.setEntries(ws, "tA", A.slice().reverse()), {give: ["103", "102"], receive: ["204"]}, {mineId: "tA", theirId: "tB"});
  assert.equal(T.cacheKey(base, "readout"), T.cacheKey(reordered, "readout"));
  assert.equal(T.cacheKey(base, "readout"), T.cacheKey(base, "readout"));
  assert.match(T.cacheKey(base, "readout"), /^tc1:r:[0-9a-z]+$/);
  const renamed = T.fromCompare(e, W.ops.renameTeam(ws, "tA", "Alpha prime"), {give: ["102", "103"], receive: ["204"]}, {mineId: "tA", theirId: "tB"});
  assert.equal(T.cacheKey(base, "readout"), T.cacheKey(renamed, "readout"), "a name is a label, not an input");
  const scoring = T.fromCompare({common: T.commonFromPage({leagueQuery: QUERY.replace("half_ppr", "ppr"), valueContext: VALUE, sources: SOURCES})}, ws,
    {give: ["102", "103"], receive: ["204"]}, {mineId: "tA", theirId: "tB"});
  assert.notEqual(T.cacheKey(base, "readout"), T.cacheKey(scoring, "readout"));
  const override = T.fromCompare({common: T.commonFromPage({leagueQuery: QUERY, valueContext: {...VALUE, values: {"102": 55.6}}, sources: SOURCES})}, ws,
    {give: ["102", "103"], receive: ["204"]}, {mineId: "tA", theirId: "tB"});
  assert.notEqual(T.cacheKey(base, "readout"), T.cacheKey(override, "readout"));
  const roster = T.fromCompare(e, W.ops.setEntries(ws, "tB", B.slice(0, 6)), {give: ["102", "103"], receive: ["204"]}, {mineId: "tA", theirId: "tB"});
  assert.notEqual(T.cacheKey(base, "readout"), T.cacheKey(roster, "readout"));
  const unavailable = T.fromCompare({common: T.commonFromPage({leagueQuery: QUERY, valueContext: VALUE, sources: {...SOURCES, fantasycalc: {available: false}}})}, ws,
    {give: ["102", "103"], receive: ["204"]}, {mineId: "tA", theirId: "tB"});
  assert.notEqual(T.cacheKey(base, "readout"), T.cacheKey(unavailable, "readout"), "a source going unavailable changes the result");
});

// ---------- immutable snapshots ----------
test("contexts are frozen snapshots, independent of later workspace edits", () => {
  const ws = workspace();
  const raw = JSON.parse(JSON.stringify(ws));
  const ctx = T.fromPair(env(), raw, {mineId: "tA", theirId: "tB", deal}, raw.ui.finderSettings);
  const key = T.cacheKey(ctx, "readout");
  raw.teams[0].entries.push(entry("999", "Late", "WR"));
  raw.teams[0].name = "Changed";
  raw.ui.finderSettings.maxSize = 4;
  assert.equal(ctx.teams.mine.roster.length, A.length);
  assert.equal(ctx.teams.mine.name, "Alpha");
  assert.equal(ctx.controls.finder.maxSize, 2);
  assert.equal(T.cacheKey(ctx, "readout"), key);
  assert.throws(() => { ctx.teams.mine.roster.push(entry("1", "x", "QB")); }, TypeError);
  assert.throws(() => { ctx.common.league.scoring = "ppr"; }, TypeError);
  assert.throws(() => { ctx.deal.give[0] = "1"; }, TypeError);
  assert.ok(Object.isFrozen(ctx.common.valuation.overrides["204"]));
});
test("selecting a team is view state: the workspace, its rosters and its star are untouched", () => {
  const ws = workspace();
  const before = JSON.stringify(ws);
  const ctx = T.fromPair(env(), ws, {mineId: "tA"}, null);
  const picked = T.selectTeam(ctx, "theirs", ws, "tC");
  const swapped = T.selectTeam(picked, "mine", ws, "tB");
  assert.equal(JSON.stringify(ws), before);
  assert.equal(ws.myTeamId, "tA");
  assert.equal(picked.teams.theirs.id, "tC");
  assert.equal(swapped.teams.mine.id, "tB");
  assert.equal(ctx.teams.theirs, null, "the earlier context is unchanged");
  assert.throws(() => T.selectTeam(ctx, "both", ws, "tB"), /Unknown side/);
});

// ---------- legacy state ----------
test("legacy workspaces, links and filter values still read", () => {
  // A workspace saved before finder settings existed.
  const legacy = W.normalizeWorkspace({id: "old", name: "Old", teams: [{id: "tA", name: "Alpha", entries: A}], myTeamId: "tA", ui: {filters: {fit: "naturalValue"}}});
  const pair = T.fromPair(env(), legacy, {mineId: "tA"}, legacy.ui.finderSettings);
  assert.deepEqual(pair.controls.finder, W.normalizeFinderSettings(null));
  assert.equal(T.fromLeague(env(), legacy).controls.filters.fit, "naturalMarket", "old naturalValue means natural + market supported");
  // An old link: bench=0.150 was the old default (no override); any other bench= is the sender's override.
  assert.equal(T.commonFromPage({leagueQuery: "scoring=ppr&bench=0.150"}).league.bso, undefined);
  assert.equal(T.commonFromPage({leagueQuery: "scoring=ppr&bench=0.200"}).league.bso, 0.2);
  // A Find a trade link without guardrails reads with the stored defaults.
  const decoded = F.decodeFinderHash("#find-trade?mine=101&theirs=201&size=3", null);
  const fromLink = T.fromPair(env(), legacy, {mine: [entry("101", "Qa", "QB")], theirs: [entry("201", "Qb", "QB")], mineProvenance: "link", theirsProvenance: "link"},
    {...decoded.guardrails, maxSize: decoded.size, keepMine: decoded.keepMine, keepTheirs: decoded.keepTheirs});
  assert.equal(fromLink.controls.finder.maxSize, 3);
  assert.deepEqual(fromLink.controls.finder.minBackups, {QB: 0, RB: 0, WR: 0, TE: 0});
  // A league query with leading punctuation (a hash tail) reads the same as a bare one.
  assert.deepEqual(T.commonFromPage({leagueQuery: `&${QUERY}`}).league, T.commonFromPage({leagueQuery: QUERY}).league);
});

// ---------- link precedence ----------
test("link beats local beats saved, section by section", () => {
  const saved = T.normalizeCommon({league: {scoring: "ppr", teams: 10, roster: {QB: 1, RB: 2, WR: 3, TE: 1, FLEX: 1, SUPERFLEX: 0, BENCH: 7}},
    basis: {mode: "single", source: "fantasycalc"}, overrides: {"101": 40}, sources: {fantasycalc: {available: true}}});
  const local = T.normalizeCommon({league: {scoring: "standard", teams: 12}});
  const r1 = T.resolveCommon({saved, local});
  assert.equal(r1.common.league.scoring, "standard");
  assert.deepEqual(r1.provenance, {league: "local", basis: "saved", overrides: "saved"});
  // A complete link value context replays an explicit default over the reader's custom basis and overrides.
  const link = {common: T.normalizeCommon({league: {scoring: "half_ppr", roster: {WR: 2}}, sources: {fantasycalc: {available: false}}}), complete: true};
  const r2 = T.resolveCommon({link, saved});
  assert.deepEqual(r2.common.valuation, {basis: {mode: "default"}, overrides: {}});
  assert.deepEqual(r2.provenance, {league: "link", basis: "link", overrides: "link"});
  assert.equal(r2.common.league.scoring, "half_ppr");
  assert.equal(r2.common.league.teams, 10, "a link without a team count keeps the reader's");
  assert.equal(r2.common.league.roster.WR, 2);
  assert.equal(r2.common.league.roster.BENCH, 7, "a roster slot the link leaves out keeps the reader's");
  assert.deepEqual(r2.common.sources, saved.sources, "availability is the reader's page, never the link");
  // An incomplete (older) link replaces only what it carries.
  const partial = {common: T.normalizeCommon({overrides: {"202": 30}}), complete: false};
  const r3 = T.resolveCommon({link: partial, saved});
  assert.deepEqual(r3.common.valuation.basis, {mode: "single", source: "fantasycalc"});
  assert.deepEqual(r3.common.valuation.overrides, {"202": 30});
  assert.deepEqual(r3.provenance, {league: "saved", basis: "saved", overrides: "link"});
  // Link and visit context may never be written back as the reader's saved preferences.
  const ctx = T.createContext({route: "compare", common: r2.common, commonProvenance: r2.provenance});
  assert.equal(T.maySave(ctx, "basis"), false);
  assert.equal(T.maySave(T.createContext({route: "compare", common: r1.common, commonProvenance: r1.provenance}), "basis"), true);
  assert.equal(T.maySave(T.createContext({route: "compare", common: r1.common, commonProvenance: r1.provenance}), "league"), false);
});

// ---------- cancel / undo ----------
test("cancel and undo return the earlier context exactly", () => {
  const ws = workspace();
  const current = T.fromCompare(env(), ws, {give: ["102"], receive: ["204"]}, {mineId: "tA", theirId: "tB"});
  const key = T.cacheKey(current, "readout");
  const incoming = T.fromCompare({common: T.commonFromPage({leagueQuery: "scoring=standard&teams=8"}), provenance: "link"}, ws,
    {give: ["103"], receive: ["205"]}, {});
  const visit = T.beginVisit(current, incoming);
  assert.equal(visit.context, incoming);
  assert.equal(visit.cancel(), current);
  assert.equal(T.cacheKey(visit.cancel(), "readout"), key);
  const changed = T.withChanges(current, {deal: {give: ["103"], get: ["204"]}});
  assert.notEqual(T.cacheKey(changed, "readout"), key);
  assert.deepEqual(current.deal, {give: ["102"], get: ["204"]}, "Undo is the old snapshot; it was never edited");
});

// ---------- renamed and deleted IDs ----------
test("a renamed team keeps its ID; a deleted ID is an explicit missing selection", () => {
  let ws = workspace();
  const ctx = T.fromCompare(env(), ws, {give: ["102"], receive: ["204"]}, {mineId: "tA", theirId: "tB"});
  const renamed = W.ops.renameTeam(ws, "tB", "Bravo renamed");
  const after = T.selectTeam(ctx, "theirs", renamed, "tB");
  assert.equal(after.teams.theirs.id, "tB");
  assert.equal(after.teams.theirs.name, "Bravo renamed");
  assert.equal(T.cacheKey(after, "readout"), T.cacheKey(ctx, "readout"));
  // Delete Bravo and add a new team that reuses its old name: the selection must not jump to it.
  ws = W.ops.addTeam(W.ops.removeTeam(ws, "tB"), "Bravo", {id: "tB2", entries: B, now: 2});
  const gone = T.selectTeam(ctx, "theirs", ws, "tB");
  assert.deepEqual({id: gone.teams.theirs.id, missing: gone.teams.theirs.missing, roster: gone.teams.theirs.roster.length}, {id: "tB", missing: true, roster: 0});
  assert.notEqual(T.cacheKey(gone, "readout"), T.cacheKey(ctx, "readout"));
  assert.equal(T.maySave(gone, "theirs"), false);
  assert.deepEqual(T.unresolvedDeal(gone), {give: [], get: ["204"]});
  // A league whose star was deleted has no "my team"; its opponents are still listed by ID.
  const noStar = W.ops.removeTeam(workspace(), "tA");
  const league = T.fromLeague(env(), noStar);
  assert.equal(league.teams.mine, null);
  assert.deepEqual(league.teams.opponents.map(o => o.id), ["tB", "tC"]);
  // A saved opponent filter that names a deleted team is reported, not rewritten.
  const stale = T.fromLeague(env(), W.ops.setUi(workspace(), {filters: {opponent: "tZ"}}));
  assert.equal(stale.controls.filters.opponent, "tZ");
  assert.ok(stale.warnings.some(w => /opponent filter tZ/.test(w)));
});

// ---------- the pair finder's shown rosters win over their origin IDs (JEG-1219 handshake on #1086) ----------
test("a shown working copy stays authoritative over its saved origin ID", () => {
  // The exact reproduction: saved team "a" holds [1]; the finder's edited working copy came from "a" and shows [2].
  let ws = W.newWorkspace({id: "w", name: "W", now: 1});
  ws = W.ops.addTeam(ws, "A", {id: "a", entries: [entry("1", "Saved player", "QB")], now: 1});
  const shown = [entry("2", "Working-copy player", "WR")];
  const edited = T.fromPair({common: T.normalizeCommon({}), provenance: "local"}, ws, {mineId: "a", mine: shown, mineProvenance: "local"}, {});
  assert.deepEqual(edited.teams.mine.roster.map(e => e.key), ["2"]);
  assert.deepEqual({id: edited.teams.mine.id, provenance: edited.teams.mine.provenance, missing: edited.teams.mine.missing, matchesSaved: edited.teams.mine.matchesSaved},
    {id: "a", provenance: "local", missing: false, matchesSaved: false});
  assert.equal(edited.teams.mine.name, null, "a saved name is not shown on a roster that no longer matches it");
  assert.equal(T.maySave(edited, "mine"), false);
  // Deleted origin: the shown roster stays, the source ID is marked missing.
  const deleted = T.fromPair({common: T.normalizeCommon({})}, W.ops.removeTeam(ws, "a"), {mineId: "a", mine: shown, mineProvenance: "local"}, {});
  assert.deepEqual(deleted.teams.mine.roster.map(e => e.key), ["2"]);
  assert.equal(deleted.teams.mine.missing, true);
  assert.equal(deleted.teams.mine.id, "a");
  assert.equal(T.cacheKey(deleted, "readout"), T.cacheKey(edited, "readout"), "losing the origin ID does not change what is priced");
  // An emptied working copy is an empty roster, not a reload of the saved one.
  const emptied = T.fromPair({common: T.normalizeCommon({})}, ws, {mineId: "a", mine: [], mineProvenance: "local"}, {});
  assert.deepEqual(emptied.teams.mine.roster, []);
  // The saved team changed after the copy was loaded: the shown copy wins.
  const changedSaved = W.ops.setEntries(ws, "a", [entry("3", "Later", "RB")]);
  assert.deepEqual(T.fromPair({common: T.normalizeCommon({})}, changedSaved, {mineId: "a", mine: shown, mineProvenance: "local"}, {}).teams.mine.roster.map(e => e.key), ["2"]);
  // A foreign workspace: an origin ID from the sender that also exists, with other players, on this reader.
  let reader = W.newWorkspace({id: "r", name: "R", now: 1});
  reader = W.ops.addTeam(reader, "Reader's A", {id: "a", entries: [entry("9", "Reader player", "TE")], now: 1});
  const foreign = T.fromPair({common: T.normalizeCommon({})}, reader, {mineId: "a", mine: shown, mineProvenance: "link"}, {});
  assert.deepEqual(foreign.teams.mine.roster.map(e => e.key), ["2"]);
  assert.equal(foreign.teams.mine.name, null);
  assert.equal(foreign.teams.mine.provenance, "link");
  assert.equal(T.maySave(foreign, "mine"), false);
  // An unedited copy still matches its saved team and keeps saved provenance and name.
  const unedited = T.fromPair({common: T.normalizeCommon({}), provenance: "saved"}, ws, {mineId: "a", mine: [entry("1", "Saved player", "QB")]}, {});
  assert.deepEqual({provenance: unedited.teams.mine.provenance, matchesSaved: unedited.teams.mine.matchesSaved, name: unedited.teams.mine.name},
    {provenance: "saved", matchesSaved: true, name: "A"});
  // An ID with no shown roster reads the saved team.
  assert.deepEqual(T.fromPair({common: T.normalizeCommon({})}, ws, {mineId: "a"}, {}).teams.mine.roster.map(e => e.key), ["1"]);
});

// ---------- a link opened on another device ----------
test("a link opened on a device with different saved teams uses the link's rosters", () => {
  const sender = workspace();
  const senderCtx = T.fromPair(env(), sender, {mineId: "tA", theirId: "tB", deal}, sender.ui.finderSettings);
  // The reader has a team with the same name and ID text but a different roster, and a different star.
  let reader = W.newWorkspace({id: "other", name: "Mine", now: 5});
  reader = W.ops.addTeam(reader, "Alpha", {id: "tA", entries: C, now: 5});
  reader = W.ops.addTeam(reader, "Zulu", {id: "tZ", entries: B, now: 5, mine: true});
  const readerBefore = JSON.stringify(reader);
  const linkCommon = T.resolveCommon({link: {common: env().common, complete: true}, saved: T.normalizeCommon({league: {scoring: "ppr"}, basis: {mode: "single", source: "espn"}, sources: SOURCES})});
  const readerCtx = T.fromPair({common: linkCommon.common, commonProvenance: linkCommon.provenance, provenance: "link"}, reader,
    {mine: A, theirs: B, mineProvenance: "link", theirsProvenance: "link", deal}, reader.ui.finderSettings);
  assert.equal(readerCtx.teams.mine.id, null, "the sender's private team ID is not needed and not used");
  assert.equal(readerCtx.teams.mine.provenance, "link");
  assert.deepEqual(readerCtx.teams.mine.roster, senderCtx.teams.mine.roster);
  assert.equal(T.cacheKey(readerCtx, "readout"), T.cacheKey(senderCtx, "readout"), "both devices price the same explicit trade");
  assert.equal(T.maySave(readerCtx, "mine"), false);
  assert.equal(T.maySave(readerCtx, "overrides"), false);
  assert.equal(JSON.stringify(reader), readerBefore, "nothing was written to the reader's saved league or star");
});

// ---------- reviewed blockers on #1086 (Codex, JEG-1229 02:55 and 04:13) ----------
test("a link or local visit never saves common preferences, even without per-section provenance", () => {
  const c = common();
  assert.equal(T.maySave(T.createContext({route: "compare", common: c, provenance: "link"}), "basis"), false, "Codex's exact reproduction");
  assert.equal(T.maySave(T.createContext({route: "compare", common: c, provenance: "local"}), "basis"), false);
  ["league", "basis", "overrides"].forEach(part => {
    assert.equal(T.maySave(T.createContext({route: "pair", common: c, provenance: "link"}), part), false, part);
    assert.equal(T.maySave(T.createContext({route: "league", common: c, provenance: "local"}), part), false, part);
    assert.equal(T.maySave(T.createContext({route: "pair", common: c, provenance: "saved"}), part), true, part);
  });
  // Per-section provenance, when the page resolved it, still decides section by section.
  assert.equal(T.maySave(T.createContext({route: "compare", common: c, provenance: "link", commonProvenance: {league: "saved", basis: "link", overrides: "saved"}}), "basis"), false);
  assert.equal(T.maySave(T.createContext({route: "compare", common: c, provenance: "link", commonProvenance: {league: "saved", basis: "link", overrides: "saved"}}), "league"), true);
});
test("discovery keys keep each team's ID with its roster; readouts stay identity-free", () => {
  const base = W.ops.setUi(workspace(), {filters: {opponent: "tB"}});
  const swapped = W.ops.setEntries(W.ops.setEntries(base, "tB", C), "tC", B);
  const k = ws => T.cacheKey(T.fromLeague(env(), ws), "discovery");
  assert.notEqual(k(base), k(swapped), "Codex's reproduction: filter tB, rosters of tB and tC swapped");
  assert.equal(k(W.ops.renameTeam(base, "tB", "Bravo renamed")), k(base), "a rename keeps the ID and the key");
  assert.notEqual(k(W.ops.setUi(base, {filters: {opponent: "tC"}})), k(base), "a different opponent filter is a different search");
  assert.equal(k(base), k(base), "deterministic");
  // The same swap on the pair finder: mine/theirs IDs follow their rosters.
  const pk = ws => T.cacheKey(T.fromPair(env(), ws, {mineId: "tA", theirId: "tB"}, ws.ui.finderSettings), "discovery");
  assert.notEqual(pk(base), pk(swapped));
  // A readout prices two rosters: the same rosters under other IDs are the same readout.
  const r1 = T.fromPair(env(), base, {mineId: "tA", theirId: "tB", deal}, {});
  const r2 = T.fromPair(env(), base, {mine: A, theirs: B, deal}, {});
  assert.equal(T.cacheKey(r1, "readout"), T.cacheKey(r2, "readout"));
});

// ---------- carrying one trade between pages (JEG-1259) ----------
// Two bench levels as league.js prices them after #1105: DDF Value at the ddf level, the charts at the market level.
// Fixture numbers only (not site values). Compare's modeled bench is a third, different set.
const LEVEL_ROWS = {
  ddf: roster => rows(roster).map(r => ({...r, values: {ddf_value: r.values.ddf_value}})),
  market: roster => rows(roster).map(r => ({...r, values: {ddf_value: r.values.ddf_value + 2, fantasycalc: r.values.ddf_value * 1.1}})),
  modeled: roster => rows(roster).map(r => ({...r, values: {ddf_value: r.values.ddf_value + 5}}))
};
const ALLOCATION = {ddf: [{pos: "RB", bench: 6}], market: [{pos: "RB", bench: 17}], modeled: [{pos: "RB", bench: 12}]};
const WEIGHTS = {ddf: {RB: 0.4}, market: {RB: 0.5}, modeled: {RB: 0.45}};
const ALL = A.concat(B, C);
function levelsFor(mode, mine, theirs, d, tweak) {
  const keys = T.pricingKeys({mine, theirs, deal: d});
  const levels = {};
  (mode === "league" ? ["ddf", "market"] : ["modeled"]).forEach(level => {
    const r = LEVEL_ROWS[level](ALL);
    levels[level] = T.levelIdentity(level, {rows: tweak ? tweak(level, r) : r, allocation: ALLOCATION[level], weights: WEIGHTS[level], keys});
  });
  return {mode, levels, rostered: mode === "league" ? ALL.map(e => e.key) : null, reserve: mode === "league" ? [] : null};
}
// The readout a page shows: each side's DDF Value lineup gain at the ddf level, chart gains at the market level.
function readout(context, mode) {
  const mineRoster = context.teams.mine.roster;
  const theirRoster = T.dealPartner(context).roster;
  const at = (level, key) => {
    const rowsAt = LEVEL_ROWS[level](mineRoster.concat(theirRoster));
    const by = new Map(rowsAt.map(r => [r.player_key, r]));
    const mine = mineRoster.filter(e => by.has(e.key)).map(e => by.get(e.key));
    const theirs = theirRoster.filter(e => by.has(e.key)).map(e => by.get(e.key));
    const give = context.deal.give.map(k => by.get(k));
    const get = context.deal.get.map(k => by.get(k));
    const us = F.rosterImpact(mine, give, get, SHAPE, key);
    const them = F.rosterImpact(theirs, get, give, SHAPE, key);
    return {us: us.starterDelta, usBench: us.benchDelta, them: them.starterDelta, values: context.deal.give.concat(context.deal.get).map(k => [k, by.get(k).values[key]])};
  };
  return mode === "league" ? {ddf: at("ddf", "ddf_value"), market: at("market", "fantasycalc")} : {modeled: at("modeled", "ddf_value")};
}
function origin(d, opts) {
  const ws = (opts && opts.ws) || workspace();
  const mineRoster = ws.teams.find(t => t.id === "tA").entries;
  const partner = ws.teams.find(t => t.id === "tB").entries;
  const pricing = levelsFor("league", mineRoster, partner, d);
  return {ws, pricing, ctx: T.fromLeague({...env(), deal: d, pricing}, ws)};
}
// What Compare does on arrival: apply the carried settings as a complete link over its own, rerun the same level(s)
// with the carried rosters, receive.
function arrive(transfer, opts) {
  const o = opts || {};
  const t = transfer && T.decodeTransfer(T.encodeTransfer(transfer));
  const own = o.own || T.normalizeCommon({league: {scoring: "ppr"}, basis: {mode: "default"}, sources: o.sources || SOURCES});
  const linkCommon = t ? T.normalizeCommon({league: t.settings, basis: t.valuation.basis, overrides: t.valuation.overrides, sources: SOURCES}) : null;
  const resolved = linkCommon ? T.resolveCommon({link: {common: linkCommon, complete: true}, saved: own}) : {common: own, provenance: null};
  const here = {route: o.route || "compare", common: o.common || resolved.common, commonProvenance: resolved.provenance, ws: o.ws || workspace(),
    pricing: "pricing" in o ? o.pricing : t && levelsFor(o.mode || t.pricing.mode, t.mine.roster, t.theirs.roster, t.deal, o.tweak)};
  return T.receive(t, here);
}
// Hand-checked: Alpha's starters 109 → 113 at the ddf level (Ra1 18 out, Wb1 22 in, Wa2 16 moves to FLEX); Bravo 106 → 102.
const GOLDEN_1_FOR_1 = {ddf: {us: 4, usBench: 0, them: -4, values: [["102", 18], ["204", 22]]},
  market: {us: 4.3999999999999915, usBench: 0, them: -4.3999999999999915, values: [["102", 19.8], ["204", 24.200000000000003]]}};
const GOLDEN_2_FOR_1 = {ddf: {us: -11, usBench: 0, them: -3, values: [["102", 18], ["103", 15], ["204", 22]]},
  market: {us: -12.100000000000009, usBench: 0, them: -3.299999999999997, values: [["102", 19.8], ["103", 16.5], ["204", 24.200000000000003]]}};

test("failing before: today's Compare link prices the reader's own team, not the trade's", () => {
  // The league page today sends saved IDs (mine/theirs) and Compare reads them from the reader's workspace. On another
  // device the same IDs hold other players: the trade is silently repriced on a substituted roster (JEG-1240's
  // team-substituted). The carried transfer keeps the trade's rosters.
  const {ctx} = origin(deal);
  let reader = W.newWorkspace({id: "reader", name: "Mine", now: 5});
  reader = W.ops.addTeam(reader, "Alpha", {id: "tA", entries: C.concat([entry("102", "Ra1", "RB")]), now: 5, mine: true});
  reader = W.ops.addTeam(reader, "Bravo", {id: "tB", entries: [entry("204", "Wb1", "WR")], now: 5});
  const byIds = T.fromCompare(env(), reader, {give: deal.give, receive: deal.get}, {mineId: "tA", theirId: "tB"});
  assert.notDeepEqual(byIds.teams.mine.roster.map(e => e.key).sort(), ctx.teams.mine.roster.map(e => e.key).sort(), "the ID path substitutes a roster");
  const got = arrive(T.toTransfer(ctx), {ws: reader});
  assert.equal(got.status, "ok", JSON.stringify(got.reasons));
  assert.deepEqual(got.context.teams.mine.roster, ctx.teams.mine.roster);
  assert.deepEqual(got.context.teams.theirs.roster, T.dealPartner(ctx).roster);
});
test("league to Compare: the same deal keeps its values and gains at both levels (golden)", () => {
  const {ctx} = origin(deal);
  const before = readout(ctx, "league");
  assert.deepEqual(before, GOLDEN_1_FOR_1);
  const got = arrive(T.toTransfer(ctx));
  assert.equal(got.status, "ok", JSON.stringify(got.reasons));
  assert.deepEqual(readout(got.context, "league"), GOLDEN_1_FOR_1);
  assert.equal(T.cacheKey(got.context, "readout"), T.cacheKey(ctx, "readout"), "same rosters, deal, settings, basis, sources and level identity");
  assert.deepEqual(got.context.pricing, ctx.pricing);
  assert.deepEqual(got.context.versions, ctx.versions);
  assert.deepEqual({route: got.context.origin.route, mineId: got.context.origin.mineId, theirId: got.context.origin.theirId, partnerIds: got.context.origin.partnerIds},
    {route: "league", mineId: "tA", theirId: "tB", partnerIds: ["tB"]});
  assert.ok(Object.isFrozen(got.context.origin) && Object.isFrozen(got.context.pricing.levels.ddf));
  // The pair finder receives the same trade the same way.
  const pair = arrive(T.toTransfer(ctx), {route: "pair"});
  assert.equal(pair.status, "ok");
  assert.equal(T.cacheKey(pair.context, "readout"), T.cacheKey(ctx, "readout"));
});
test("an unequal package (2 for 1) arrives exactly, gains included", () => {
  const two = {give: ["102", "103"], get: ["204"]};
  const {ctx} = origin(two);
  const before = readout(ctx, "league");
  assert.deepEqual(before, GOLDEN_2_FOR_1);
  const got = arrive(T.toTransfer(ctx));
  assert.equal(got.status, "ok");
  assert.deepEqual(got.context.deal, {give: ["102", "103"], get: ["204"]});
  assert.deepEqual(readout(got.context, "league"), before);
  assert.notEqual(T.cacheKey(got.context, "readout"), T.cacheKey(origin(deal).ctx, "readout"));
});
test("reload and share: the encoded transfer reads back to the same context, and a foreign device keeps the carried rosters", () => {
  const {ctx} = origin(deal);
  const text = T.encodeTransfer(T.toTransfer(ctx));
  assert.match(text, /^[A-Za-z0-9_-]+$/);
  assert.deepEqual(T.decodeTransfer(text), JSON.parse(JSON.stringify(T.toTransfer(ctx))), "reload: byte-for-byte the same transfer");
  // A reader whose saved IDs tA/tB hold other players, and a different star.
  let reader = W.newWorkspace({id: "reader", name: "Mine", now: 5});
  reader = W.ops.addTeam(reader, "Alpha", {id: "tA", entries: C, now: 5});
  reader = W.ops.addTeam(reader, "Zulu", {id: "tZ", entries: B, now: 5, mine: true});
  const before = JSON.stringify(reader);
  const got = arrive(T.decodeTransfer(text), {ws: reader});
  assert.equal(got.status, "ok", JSON.stringify(got.reasons));
  assert.equal(got.context.teams.mine.id, null, "a foreign workspace's same-named ID is never used");
  assert.equal(got.context.teams.mine.provenance, "link");
  assert.equal(got.context.provenance, "link");
  assert.deepEqual(readout(got.context, "league"), GOLDEN_1_FOR_1);
  ["mine", "theirs", "league", "basis", "overrides"].forEach(part => assert.equal(T.maySave(got.context, part), false, part));
  assert.equal(JSON.stringify(reader), before, "the reader's saved teams and star are untouched");
  // Same device, saved team edited after the trade was sent: the carried roster stays, and it no longer matches saved.
  const sameDevice = arrive(T.toTransfer(ctx), {ws: W.ops.setEntries(workspace(), "tA", C)});
  assert.equal(sameDevice.status, "ok");
  assert.deepEqual(sameDevice.context.teams.mine.roster, ctx.teams.mine.roster);
  assert.deepEqual({id: sameDevice.context.teams.mine.id, matchesSaved: sameDevice.context.teams.mine.matchesSaved}, {id: "tA", matchesSaved: false});
  assert.equal(T.maySave(sameDevice.context, "mine"), false);
});
test("a page that cannot reproduce the trade holds it with the reason, never reprices it", () => {
  const {ctx} = origin(deal);
  const tr = T.toTransfer(ctx);
  const codes = got => (got.status === "hold" ? got.reasons.map(r => r.code) : ["ok"]);
  const holdOnly = (got, code) => {
    assert.equal(got.status, "hold");
    assert.equal(got.context, null, "a hold has no context to price");
    assert.ok(codes(got).includes(code), `${code} in ${codes(got)}`);
  };
  holdOnly(arrive(tr, {mode: "modeled"}), "level-changed");                      // Compare's modeled bench
  holdOnly(arrive(tr, {pricing: null}), "level-changed");                        // cannot run the league levels
  holdOnly(arrive(tr, {tweak: (level, r) => (level === "market" ? r.map(x => (x.player_key === "204" ? {...x, values: {...x.values, fantasycalc: 30}} : x)) : r)}), "rows-changed");
  holdOnly(arrive(tr, {pricing: {...levelsFor("league", A, B, deal), rostered: A.map(e => e.key)}}), "level-changed");
  const sources = (patch) => T.normalizeCommon({league: tr.settings, basis: tr.valuation.basis, overrides: tr.valuation.overrides, sources: {...SOURCES, ...patch}});
  holdOnly(arrive(tr, {common: sources({espn: {available: false, reason: "not loaded"}})}), "sources-changed");     // missing source
  holdOnly(arrive(tr, {common: sources({fantasycalc: {held: true}})}), "sources-changed");                           // held source
  holdOnly(arrive(tr, {common: sources({fantasycalc: {available: true, version: "rebuilt"}})}), "sources-changed");  // rebuilt source
  holdOnly(arrive(tr, {common: T.normalizeCommon({league: tr.settings, basis: tr.valuation.basis, overrides: {}, sources: SOURCES})}), "overrides-changed");
  holdOnly(arrive(tr, {common: T.normalizeCommon({league: tr.settings, basis: {mode: "default"}, overrides: tr.valuation.overrides, sources: SOURCES})}), "basis-changed");
  holdOnly(arrive(tr, {common: T.normalizeCommon({league: {...tr.settings, scoring: "ppr"}, basis: tr.valuation.basis, overrides: tr.valuation.overrides, sources: SOURCES})}), "settings-changed");
  holdOnly(T.receive(null, {route: "compare"}), "context-missing");
  holdOnly(T.receive(T.decodeTransfer(T.encodeTransfer(tr).slice(0, 40)), {route: "compare"}), "context-missing");
  const tampered = JSON.parse(JSON.stringify(tr));
  tampered.theirs.roster = tampered.theirs.roster.slice(1);
  holdOnly(T.receive(tampered, {route: "compare"}), "context-unreadable");
  holdOnly(T.receive({...tr, v: 2}, {route: "compare"}), "context-unsupported");
  // No partner: on the league finder, a deal whose received players no single opponent holds has no other side.
  const noPartner = T.toTransfer(T.fromLeague({...env(), deal: {give: ["102"], get: ["204", "301"]}, pricing: levelsFor("league", A, B, deal)}, workspace()));
  holdOnly(T.receive(noPartner, {route: "compare", common: common(), pricing: noPartner.pricing}), "team-missing");
  const noDeal = T.toTransfer(T.fromLeague({...env(), pricing: levelsFor("league", A, B, deal)}, workspace()));
  holdOnly(T.receive(noDeal, {route: "compare", common: common(), pricing: noDeal.pricing}), "package-missing");
  // A transfer that never said which level priced it.
  const unpriced = T.toTransfer(T.fromLeague({...env(), deal}, workspace()));
  holdOnly(T.receive(unpriced, {route: "compare", common: common(), pricing: levelsFor("league", A, B, deal)}), "level-missing");
});
test("the bench level and its rows are part of every cache key", () => {
  const {ctx} = origin(deal);
  const modeled = T.withChanges(ctx, {pricing: levelsFor("modeled", A, B, deal)});
  assert.notEqual(T.cacheKey(ctx, "readout"), T.cacheKey(modeled, "readout"));
  assert.notEqual(T.cacheKey(ctx, "discovery"), T.cacheKey(modeled, "discovery"));
  const rebuilt = T.withChanges(ctx, {pricing: levelsFor("league", A, B, deal, (level, r) => r.map(x => ({...x, values: {...x.values, ddf_value: x.values.ddf_value + 0.1}})))});
  assert.notEqual(T.cacheKey(ctx, "readout"), T.cacheKey(rebuilt, "readout"));
  assert.notEqual(ctx.versions.pricing, rebuilt.versions.pricing);
  assert.equal(ctx.versions.settings, rebuilt.versions.settings);
  // A missing row is not a zero.
  const zero = T.levelIdentity("ddf", {rows: [{player_key: "1", values: {ddf_value: 0}}], keys: ["1"]});
  const none = T.levelIdentity("ddf", {rows: [], keys: ["1"]});
  assert.notEqual(zero.rows, none.rows);
  assert.deepEqual([zero.players, none.players], [1, 0]);
});
test("the JEG-1240 journey diff finds no loss between the league envelope and the received one", () => {
  // Consumes #1110's own envelope/diff (tests/node/uso_site_journey_contract.cjs) when it is present on this tree, or at
  // JOURNEY_CONTRACT; reports SKIP when it is not (that file lands with #1110).
  const file = process.env.JOURNEY_CONTRACT || path.join(__dirname, "uso_site_journey_contract.cjs");
  let J;
  try { J = require(file); } catch (error) { console.log(`SKIP journey contract not on this tree (${path.basename(file)})`); return; }
  const {ctx} = origin({give: ["102", "103"], get: ["204"]});
  const got = arrive(T.toTransfer(ctx));
  assert.equal(got.status, "ok");
  const env1240 = context => {
    const partner = T.dealPartner(context);
    const rowsByKey = new Map(LEVEL_ROWS.market(context.teams.mine.roster.concat(partner.roster))
      .map(r => [r.player_key, {...r, values: {...r.values, usatoday: r.values.fantasycalc, fantasypros: r.values.fantasycalc, cbs: r.values.fantasycalc}}]));
    return J.envelope(F, {settings: context.common.league, basis: context.common.valuation.basis, level: context.pricing && context.pricing.mode,
      charts: ["usatoday", "fantasycalc", "fantasypros", "cbs"], market: ["usatoday", "fantasycalc", "fantasypros", "cbs"], shape: SHAPE, rowsByKey},
    {mine: {id: context.teams.mine.id || context.origin && context.origin.mineId, entries: context.teams.mine.roster},
      theirs: {id: partner.id || context.origin && context.origin.theirId, entries: partner.roster}}, context.deal.give, context.deal.get);
  };
  assert.deepEqual(J.diff(env1240(ctx), env1240(got.context)), []);
  // And the diff does see a substituted roster (the failing-before path).
  const subbed = T.withChanges(got.context, {theirs: T.rosterTeam(C, "local")});
  assert.ok(J.diff(env1240(ctx), env1240({...subbed, origin: got.context.origin})).some(d => d.code === "team-substituted"));
});

let failed = 0;
cases.forEach(([name, fn]) => {
  try { fn(); console.log(`PASS ${name}`); }
  catch (error) { failed += 1; console.log(`FAIL ${name}\n  ${error && error.stack ? error.stack.split("\n").slice(0, 3).join("\n  ") : error}`); }
});
console.log(`${cases.length - failed} passed, ${failed} failed`);
process.exit(failed ? 1 : 0);
