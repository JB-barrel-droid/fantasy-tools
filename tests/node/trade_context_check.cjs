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
  assert.deepEqual(c.sources.espn, {status: "unavailable", reason: "not loaded"});
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

let failed = 0;
cases.forEach(([name, fn]) => {
  try { fn(); console.log(`PASS ${name}`); }
  catch (error) { failed += 1; console.log(`FAIL ${name}\n  ${error && error.stack ? error.stack.split("\n").slice(0, 3).join("\n  ") : error}`); }
});
console.log(`${cases.length - failed} passed, ${failed} failed`);
process.exit(failed ? 1 : 0);
