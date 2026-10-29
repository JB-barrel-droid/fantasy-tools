// JEG-1231: opponent inclusion state and the league search adapter. Pure Node, no browser.
//   node tests/node/opponent_inclusion_check.cjs [dir with opponent-inclusion.js, workspace.js, opportunities.js, finder.js]
// Prints one JSON object {ran: [names], failures: [{name, message}]}. tests/test_jeg1231_opponent_inclusion.py runs it on the
// real modules and on broken copies it requires to fail. The DOM component is checked in the browser
// (tests/test_jeg1231_opponent_inclusion_render.py).
"use strict";
const path = require("path");
const fs = require("fs");
const assert = require("assert");

const ROOT = path.resolve(__dirname, "..", "..");
const dir = path.resolve(process.argv[2] || path.join(ROOT, "app", "v2"));
const I = require(path.join(dir, "opponent-inclusion.js"));
const W = require(path.join(dir, "workspace.js"));
const O = require(path.join(dir, "opportunities.js"));
const F = require(path.join(dir, "finder.js"));
const fixture = JSON.parse(fs.readFileSync(path.join(ROOT, "tests", "fixtures", "league", "fixture-4team.json"), "utf8"));

// ---------- synthetic engine rows (the league harness's deterministic builder; values only need to be stable) ----------
const CH = ["usatoday", "fantasycalc", "fantasypros", "cbs"];
function hash(text) { let h = 2166136261; for (const c of String(text)) { h ^= c.charCodeAt(0); h = Math.imul(h, 16777619) >>> 0; } return h >>> 0; }
const unit = (key, salt) => (hash(`${key}:${salt}`) % 10000) / 10000;
function makeRows(players) {
  const map = new Map();
  players.forEach(p => {
    if (String(p.key).startsWith("x:") || map.has(String(p.key))) return;
    const ddf = Math.round((4 + 36 * Math.pow(unit(p.key, "d"), 1.6)) * 10) / 10;
    const values = {ddf_value: ddf};
    const market = 0.62 + 0.76 * unit(p.key, "m");
    CH.forEach(k => { values[k] = Math.round(ddf * market * (0.9 + 0.2 * unit(p.key, k)) * 10) / 10; });
    map.set(String(p.key), {player_key: String(p.key), name: p.name, pos: p.pos, team: p.team || "", values});
  });
  return map;
}
const SHAPE = {QB: 1, RB: 2, WR: 2, TE: 1, FLEX: 1, SUPERFLEX: 0};
const ALLOCATION = [{pos: "QB", rostered: 30, lineup: 12, bench: 18}, {pos: "RB", rostered: 60, lineup: 36, bench: 24}, {pos: "WR", rostered: 66, lineup: 36, bench: 30}, {pos: "TE", rostered: 24, lineup: 12, bench: 12}];
const CTX = {rowsByKey: makeRows([].concat(...fixture.teams.map(t => t.players))), shape: SHAPE, expected: F.expectedDepth(ALLOCATION, 12),
  weights: {overall: 0.3, QB: 0.2, RB: 0.3, WR: 0.3, TE: 0.25}, charts: CH.slice(), market: CH.slice(), chartKeys: CH.slice(), maxSize: 2, keepMine: true, keepTheirs: true};
const entriesOf = t => t.players.map(p => ({key: String(p.key), name: p.name, pos: p.pos, team: p.team}));

// A real workspace (workspace.js ops): the fixture's four teams, the first starred.
function league(names) {
  let ws = W.newWorkspace({name: "Test league", now: 1});
  (names || fixture.teams.map(t => t.name)).forEach((n, i) => {
    const src = fixture.teams[i % fixture.teams.length];
    ws = W.ops.addTeam(ws, n, {entries: entriesOf(src), now: 1});
  });
  return W.ops.setMyTeam(ws, ws.teams[0].id);
}
const withState = (ws, state) => W.ops.setUi(ws, I.patch(state));
const ids = list => list.map(t => String(t.id));
const run = (ws, opponents, cache) => O.runAll({id: ws.myTeamId, name: "mine", entries: ws.teams.find(t => t.id === ws.myTeamId).entries},
  opponents.map(t => ({id: t.id, name: t.name, entries: t.entries})), CTX, {cache: cache || O.createCache(), yieldFn: () => Promise.resolve(), budgetMs: 0});

const ran = [];
const failures = [];
const queue = [];
function t(name, fn) { ran.push(name); queue.push({name, fn}); }

t("test_baseline_every_opponent_included", () => {
  const ws = league();
  const m = I.describe(ws, I.read(ws));
  assert.strictEqual(m.status, "ok");
  assert.deepStrictEqual(m.state, {v: 1, excluded: []});
  assert.deepStrictEqual(m.rows.map(r => r.id), ids(ws.teams.slice(1)), "every other team, league order, my team left out");
  assert.ok(m.rows.every(r => r.included && r.searched));
  assert.deepStrictEqual(ids(I.searchOpponents(ws, I.read(ws))), ids(ws.teams.slice(1)), "the search runs against every opponent, as today");
  assert.strictEqual(I.summary(m), "Searching 3 of 3 opponents.");
});

t("test_explicit_exclude_and_include", () => {
  const ws = league();
  const b = ws.teams[2].id;
  const s1 = I.setIncluded(I.read(ws), ws, b, false);
  assert.deepStrictEqual(s1.excluded, [b]);
  assert.strictEqual(I.setIncluded(s1, ws, b, false), s1, "no change returns the same state");
  const m = I.describe(withState(ws, s1), undefined);
  assert.strictEqual(m.rows.find(r => r.id === b).included, false);
  assert.strictEqual(m.counts.searched, 2);
  assert.strictEqual(I.summary(m), "Searching 2 of 3 opponents. 1 left out here.");
  const s2 = I.setIncluded(s1, ws, b, true);
  assert.deepStrictEqual(s2.excluded, []);
  assert.deepStrictEqual(I.toggle(I.toggle(s2, ws, b), ws, b).excluded, [], "toggle twice is a no-op");
  assert.deepStrictEqual(I.setIncluded(s2, ws, ws.myTeamId, false).excluded, [], "my own team is not an opponent");
  assert.deepStrictEqual(I.setIncluded(s2, ws, "team_unknown", false).excluded, [], "an id that is not in the league is ignored");
});

t("test_duplicate_names_keyed_by_id", () => {
  const ws = league(["Mine", "Sharks", "Sharks", "Jets"]);
  const [, a, b] = ws.teams;
  const s = I.setIncluded(null, ws, b.id, false);
  const m = I.describe(ws, s);
  const ra = m.rows.find(r => r.id === a.id);
  const rb = m.rows.find(r => r.id === b.id);
  assert.strictEqual(ra.included, true, "excluding one Sharks leaves the other in");
  assert.strictEqual(rb.included, false);
  assert.deepStrictEqual([ra.label, rb.label], ["Sharks · team 2", "Sharks · team 3"], "labels tell repeated names apart by league position");
  assert.ok(ra.duplicate && rb.duplicate && !m.rows.find(r => r.name === "Jets").duplicate);
  assert.deepStrictEqual(ids(I.searchOpponents(ws, s)), [a.id, ws.teams[3].id]);
  assert.ok(I.describe(league(["Mine", "Sharks", " sharks "]), null).rows.every(r => r.duplicate), "case and spacing do not hide a repeat");
});

t("test_rename_keeps_choice", () => {
  let ws = league();
  const b = ws.teams[2].id;
  ws = withState(ws, I.setIncluded(null, ws, b, false));
  const before = I.selectionKey(ws);
  ws = W.ops.renameTeam(ws, b, "Brand new name");
  assert.deepStrictEqual(I.read(ws).excluded, [b], "a rename keeps the id, so it keeps the choice");
  assert.strictEqual(I.describe(ws).rows.find(r => r.id === b).name, "Brand new name");
  assert.strictEqual(I.selectionKey(ws), before, "a rename is not a selection change");
});

t("test_removal_and_import_collision", () => {
  let ws = league();
  const b = ws.teams[2];
  ws = withState(ws, I.setIncluded(null, ws, b.id, false));
  // Re-import that matches the team (league.js keeps the id when a pasted team matches by name): the choice stays.
  ws = W.ops.setEntries(ws, b.id, b.entries.slice(0, 3), {sourceText: "", sourceTeam: null, removed: []});
  assert.deepStrictEqual(I.read(ws).excluded, [b.id]);
  // Removed, then a team with the same name added back: a new id, so it arrives included like any new team.
  ws = W.ops.removeTeam(ws, b.id);
  assert.deepStrictEqual(I.read(ws).excluded, [], "a removed team's id drops out");
  ws = W.ops.addTeam(ws, b.name, {entries: b.entries});
  const back = ws.teams[ws.teams.length - 1];
  assert.notStrictEqual(back.id, b.id);
  assert.strictEqual(I.describe(ws).rows.find(r => r.id === back.id).included, true, "never inherited by name");
  // A stale stored id never attaches to a different team.
  const stale = {v: 1, excluded: [b.id, ws.teams[1].id, ws.teams[1].id, 7, null]};
  assert.deepStrictEqual(I.normalize(stale, ws).excluded, [ws.teams[1].id]);
});

t("test_no_opponents_and_all_excluded", () => {
  let ws = W.ops.setMyTeam(W.ops.addTeam(W.newWorkspace({name: "Solo"}), "Mine", {entries: entriesOf(fixture.teams[0])}), null);
  ws = W.ops.setMyTeam(ws, ws.teams[0].id);
  const none = I.describe(ws);
  assert.strictEqual(none.status, "none");
  assert.deepStrictEqual(none.rows, []);
  assert.strictEqual(I.summary(none), "Add another team to choose which opponents to search.");
  assert.strictEqual(I.describe(W.newWorkspace({}), null).status, "none", "an empty league");
  ws = league();
  const all = I.excludeAll(null, ws);
  assert.deepStrictEqual(all.excluded, ids(ws.teams.slice(1)));
  assert.strictEqual(I.excludeAll(all, ws), all);
  const m = I.describe(ws, all);
  assert.strictEqual(m.status, "allExcluded");
  assert.deepStrictEqual(I.searchOpponents(ws, all), []);
  assert.match(I.summary(m), /^No opponents are included/);
  const back = I.includeAll(all, ws);
  assert.deepStrictEqual(back.excluded, []);
  assert.strictEqual(I.includeAll(back, ws), back);
});

t("test_profile_exclusion_is_preserved", () => {
  const ws = league();
  const p = ws.teams[1].id;
  const opts = {profileExcluded: id => id === p};
  const m = I.describe(ws, null, opts);
  const row = m.rows.find(r => r.id === p);
  assert.deepStrictEqual([row.included, row.profileExcluded, row.viewExcluded], [false, true, false]);
  assert.strictEqual(I.summary(m), "Searching 2 of 3 opponents. 1 marked won't trade in Managers.");
  const s = I.setIncluded(I.excludeAll(null, ws), ws, p, true);
  assert.strictEqual(I.describe(ws, s, opts).rows.find(r => r.id === p).included, false, "ticking here never re-includes a won't-trade manager");
  assert.strictEqual(I.describe(ws, I.includeAll(s, ws), opts).rows.find(r => r.id === p).included, false, "Select all leaves a won't-trade manager out");
  assert.ok(!ids(I.searchOpponents(ws, I.includeAll(s, ws), opts)).includes(p));
  assert.strictEqual(I.describe(ws, null, {profileExcluded: () => "yes"}).counts.profileExcluded, 0, "only a strict true counts");
});

t("test_view_selection_writes_nothing_else", () => {
  const ws = league();
  const frozen = JSON.stringify(ws);
  const book = {v: 1, leagues: {[ws.id]: {[ws.teams[1].id]: {teamId: ws.teams[1].id, excluded: true}}}};
  const frozenBook = JSON.stringify(book);
  const opts = {profileExcluded: id => Boolean(book.leagues[ws.id][id] && book.leagues[ws.id][id].excluded)};
  let s = I.setIncluded(null, ws, ws.teams[2].id, false);
  s = I.excludeAll(s, ws);
  s = I.includeAll(s, ws);
  I.describe(ws, s, opts);
  I.searchOpponents(ws, s, opts);
  assert.strictEqual(JSON.stringify(ws), frozen, "no star, roster or name changes");
  assert.strictEqual(JSON.stringify(book), frozenBook, "manager profiles are read, never written");
  const saved = withState(ws, I.setIncluded(null, ws, ws.teams[2].id, false));
  assert.strictEqual(saved.myTeamId, ws.myTeamId);
  assert.deepStrictEqual(saved.teams, ws.teams);
  assert.deepStrictEqual({...saved.ui, opponentInclusion: undefined}, {...ws.ui, opponentInclusion: undefined}, "other view state is kept");
});

t("test_star_moves", () => {
  let ws = league();
  const b = ws.teams[2].id;
  ws = withState(ws, I.setIncluded(null, ws, b, false));
  ws = W.ops.setMyTeam(ws, b);
  assert.ok(!I.describe(ws).rows.some(r => r.id === b), "the starred team is never an opponent");
  ws = W.ops.setMyTeam(ws, ws.teams[0].id);
  assert.strictEqual(I.describe(ws).rows.find(r => r.id === b).included, false, "moving the star back keeps the earlier choice");
});

t("test_saved_with_the_workspace", () => {
  let ws = league();
  ws = withState(ws, I.setIncluded(null, ws, ws.teams[3].id, false));
  const back = W.parseStored(W.serialize(ws));
  assert.strictEqual(back.status, "ok");
  assert.deepStrictEqual(I.read(back.workspace), I.read(ws), "the existing workspace store saves and reloads it");
  assert.deepStrictEqual(W.ops.setUi(back.workspace, {filters: {fit: "natural"}}).ui.opponentInclusion, I.read(ws), "other filter changes keep it");
  assert.deepStrictEqual(I.normalize({v: 2, excluded: [ws.teams[3].id]}, ws).excluded, [], "an unknown version reads as nothing left out");
  assert.deepStrictEqual(I.normalize("junk", ws), {v: 1, excluded: []});
});

t("test_filters_and_selection_key", () => {
  const ws = league();
  const b = ws.teams[2].id;
  const s = I.setIncluded(null, ws, b, false);
  const rows = [{opponentId: ws.teams[1].id}, {opponentId: b}, {opponentId: ws.teams[3].id}];
  assert.deepStrictEqual(I.filterRows(rows, ws, s).map(r => r.opponentId), [ws.teams[1].id, ws.teams[3].id], "stale rows against a left-out team never show");
  assert.deepStrictEqual(I.opponentFilter({fit: "all", opponent: b}, ws, s), {fit: "all", opponent: "all"});
  const keep = {fit: "all", opponent: ws.teams[1].id};
  assert.strictEqual(I.opponentFilter(keep, ws, s), keep);
  assert.notStrictEqual(I.selectionKey(ws, s), I.selectionKey(ws, null), "a selection change changes the key");
  assert.strictEqual(I.selectionKey(ws, I.setIncluded(s, ws, b, true)), I.selectionKey(ws, null));
});

t("test_search_excludes_offers_without_changing_values", async () => {
  const ws = league();
  const b = ws.teams[2].id;
  const cache = O.createCache();
  const full = await run(ws, I.searchOpponents(ws, null), cache);
  assert.ok(full.rows.some(r => r.opponentId === b), "the fixture has offers against the team we leave out");
  const s = I.setIncluded(null, ws, b, false);
  const part = await run(ws, I.searchOpponents(ws, s), cache);
  assert.ok(!part.rows.some(r => r.opponentId === b), "no offer from a left-out team");
  assert.ok(!part.perOpponent.some(o => o.id === b));
  assert.strictEqual(part.computed, 0, "every remaining pairing is reused from the cache");
  const strip = r => JSON.stringify({...r, rank: undefined});
  const expected = full.rows.filter(r => r.opponentId !== b);
  assert.deepStrictEqual(part.rows.map(strip), expected.map(strip), "same rows, values, fits and order; only the list position renumbers");
  const fresh = await run(ws, I.searchOpponents(ws, s));
  assert.deepStrictEqual(fresh.rows.map(strip), part.rows.map(strip), "a cold run agrees with the cached one");
  const none = await run(ws, I.searchOpponents(ws, I.excludeAll(null, ws)));
  assert.deepStrictEqual(none.rows, [], "all excluded finds nothing");
});

(async () => {
  for (const {name, fn} of queue) {
    try { await fn(); } catch (error) { failures.push({name, message: String(error && error.message || error).slice(0, 600)}); }
  }
  process.stdout.write(JSON.stringify({ran, failures}) + "\n");
})();
