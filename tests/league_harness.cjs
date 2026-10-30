// Unit checks for the league workspace modules (JEG-1021, spec section 9.1). Pure Node, no browser.
//   node league_harness.cjs <dir with workspace.js, table-sort.js, team-summary.js, opportunities.js, finder.js> <fixtures dir>
// Prints one JSON object: {ran: [names], failures: [{name, message}]}. tests/test_v2_league_units.py runs it on the real
// modules and, for every mutation, on a broken copy that it requires to fail.
"use strict";
const path = require("path");
const fs = require("fs");
const assert = require("assert");

const dir = path.resolve(process.argv[2]);
const fixDir = path.resolve(process.argv[3]);
const W = require(path.join(dir, "workspace.js"));
const S = require(path.join(dir, "table-sort.js"));
const T = require(path.join(dir, "team-summary.js"));
const O = require(path.join(dir, "opportunities.js"));
const F = require(path.join(dir, "finder.js"));
const fx = name => JSON.parse(fs.readFileSync(path.join(fixDir, `fixture-${name}.json`), "utf8"));

// ---------- synthetic engine rows from fixture players (deterministic; the real values come from the engine in the render tests) ----------
const CH = ["usatoday", "fantasycalc", "fantasypros", "cbs"];
function hash(text) { let h = 2166136261; for (const c of String(text)) { h ^= c.charCodeAt(0); h = Math.imul(h, 16777619) >>> 0; } return h >>> 0; }
const unit = (key, salt) => (hash(`${key}:${salt}`) % 10000) / 10000;
function makeRows(players) {
  const map = new Map();
  players.forEach(p => {
    if (String(p.key).startsWith("x:") || map.has(String(p.key))) return;
    const ddf = Math.round((4 + 36 * Math.pow(unit(p.key, "d"), 1.6)) * 10) / 10;
    const values = {ddf_value: ddf};
    const market = 0.62 + 0.76 * unit(p.key, "m");   // what the market thinks of him, shared by the four charts, plus a little chart-to-chart noise
    CH.forEach(k => { values[k] = Math.round(ddf * market * (0.9 + 0.2 * unit(p.key, k)) * 10) / 10; });
    map.set(String(p.key), {player_key: String(p.key), name: p.name, pos: p.pos, team: p.team || "", values});
  });
  return map;
}
const SHAPE = {QB: 1, RB: 2, WR: 2, TE: 1, FLEX: 1, SUPERFLEX: 0};
const ALLOCATION = [{pos: "QB", rostered: 30, lineup: 12, bench: 18}, {pos: "RB", rostered: 60, lineup: 36, bench: 24}, {pos: "WR", rostered: 66, lineup: 36, bench: 30}, {pos: "TE", rostered: 24, lineup: 12, bench: 12}];
const EXPECTED = F.expectedDepth(ALLOCATION, 12);
const WEIGHTS = {overall: 0.3, QB: 0.2, RB: 0.3, WR: 0.3, TE: 0.25};
function playersOf(fixture) { return [].concat(...fixture.teams.map(t => t.players)); }
function teamsOf(fixture, mineIndex) {
  return fixture.teams.map((t, i) => ({id: `t${i}`, name: t.name, isMine: i === (mineIndex === undefined ? 0 : mineIndex), entries: t.players.map(p => ({key: String(p.key), name: p.name, pos: p.pos, team: p.team}))}));
}
function ctxFor(rowsByKey, extra) {
  return {rowsByKey, shape: SHAPE, expected: EXPECTED, weights: WEIGHTS, charts: CH.slice(), market: CH.slice(), chartKeys: CH.slice(), maxSize: 2, keepMine: true, keepTheirs: true, ...(extra || {})};
}
const cache = {};
function load(name) {
  if (!cache[name]) { const f = fx(name); cache[name] = {f, rows: makeRows(playersOf(f)), teams: teamsOf(f)}; }
  return cache[name];
}

const ran = [];
const failures = [];
const queue = [];
function t(name, fn) { ran.push(name); queue.push({name, fn}); }
const memStorage = (initial) => { const d = initial === undefined ? {} : {[W.STORAGE_KEY]: initial}; let writes = 0; return {d, get writes() { return writes; }, getItem: k => (k in d ? d[k] : null), setItem(k, v) { writes += 1; d[k] = v; }}; };

// ---------- workspace ----------
t("test_workspace_create", () => {
  let ws = W.newWorkspace({name: "Dynasty"});
  ws = W.ops.addTeam(ws, "Alex", {entries: [{key: "1", name: "A", pos: "QB"}]});
  ws = W.ops.addTeam(ws, "Nic", {entries: [{key: "2", name: "B", pos: "RB", team: "DAL", slot: "Bench"}]});
  ws = W.ops.setMyTeam(ws, ws.teams[0].id);
  const back = W.parseStored(W.serialize(ws));
  assert.strictEqual(back.status, "ok");
  assert.deepStrictEqual(back.workspace, ws);
});
t("test_workspace_corrupt", () => {
  assert.strictEqual(W.parseStored("{").status, "corrupt");
  assert.strictEqual(W.parseStored("[1,2]").status, "corrupt");
  assert.strictEqual(W.parseStored('{"v":1,"workspaces":"x"}').status, "corrupt");
  const mem = memStorage("{");
  const store = W.createStore({storage: mem, delay: 0});
  assert.strictEqual(store.load(), "corrupt");
  assert.deepStrictEqual(store.getMyRoster(), []);
  assert.strictEqual(mem.writes, 0, "corrupt data must not be overwritten on load");
  store.setMyRoster([{key: "5", name: "Z", pos: "WR"}]);
  assert.strictEqual(mem.writes, 1);
  assert.strictEqual(W.parseStored(mem.d[W.STORAGE_KEY]).status, "ok");
});
t("test_workspace_versioned", () => {
  const good = W.serialize(W.ops.addTeam(W.newWorkspace(), "A"));
  assert.strictEqual(W.parseStored(good).status, "ok");
  assert.strictEqual(W.parseStored(good.replace('"v":1', '"v":2')).status, "version");
  assert.strictEqual(W.parseStored(good.replace('"v":1,', "")).status, "version");
  assert.strictEqual(W.parseStored(null).status, "empty");
});
t("test_team_add_remove", () => {
  let ws = W.newWorkspace();
  ["A", "B", "C"].forEach(n => { ws = W.ops.addTeam(ws, n); });
  assert.deepStrictEqual(ws.teams.map(x => x.name), ["A", "B", "C"]);
  ws = W.ops.setMyTeam(ws, ws.teams[1].id);
  const removed = ws.teams[1].id;
  ws = W.ops.removeTeam(ws, removed);
  assert.deepStrictEqual(ws.teams.map(x => x.name), ["A", "C"]);
  assert.strictEqual(ws.myTeamId, null, "removing my team clears the mark");
  ws = W.ops.removeTeam(ws, "nope");
  assert.strictEqual(ws.teams.length, 2);
  let big = W.newWorkspace();
  for (let i = 0; i < W.MAX_TEAMS + 5; i++) big = W.ops.addTeam(big, `T${i}`);
  assert.strictEqual(big.teams.length, W.MAX_TEAMS);
  assert.strictEqual(W.ops.addTeam(W.newWorkspace(), "x".repeat(100)).teams[0].name.length, W.MAX_NAME);
  assert.strictEqual(W.ops.renameTeam(ws, ws.teams[0].id, "   ").teams[0].name, "A", "a blank name keeps the old one");
});
t("test_team_reorder", () => {
  let ws = W.newWorkspace();
  ["A", "B", "C"].forEach(n => { ws = W.ops.addTeam(ws, n); });
  ws = W.ops.moveTeam(ws, ws.teams[2].id, -1);
  assert.deepStrictEqual(ws.teams.map(x => x.name), ["A", "C", "B"]);
  assert.strictEqual(W.ops.moveTeam(ws, ws.teams[0].id, -1), ws, "first team cannot move up");
  assert.strictEqual(W.ops.moveTeam(ws, ws.teams[2].id, 1), ws, "last team cannot move down");
});
// JEG-1190: Clear league drops every team and the mark, and keeps the league's settings and name.
t("test_clear_league", () => {
  let ws = W.ops.rename(W.newWorkspace(), "Sunday league");
  ["A", "B"].forEach(n => { ws = W.ops.addTeam(ws, n, {entries: [{key: "1", name: "X", pos: "WR"}]}); });
  ws = W.ops.setSettings(W.ops.setMyTeam(ws, ws.teams[0].id), {teams: 12});
  const cleared = W.ops.clearLeague(ws);
  assert.deepStrictEqual(cleared.teams, []);
  assert.strictEqual(cleared.myTeamId, null, "clearing the league clears the mark");
  assert.deepStrictEqual(cleared.settings, {teams: 12});
  assert.strictEqual(cleared.name, "Sunday league");
  assert.strictEqual(ws.teams.length, 2, "the old workspace is untouched, so Undo can put it back");
  const empty = W.newWorkspace();
  assert.strictEqual(W.ops.clearLeague(empty), empty, "an empty league is returned as is");
});
t("test_share_link_encode", () => {
  const f = fx("20team");
  const ws = teamsOf(f).slice(0, 12).reduce((w, team, i) => W.ops.addTeam(w, team.name, {entries: team.entries.slice(0, 15)}), W.newWorkspace());
  const enc = W.encodeShare(ws);
  assert.ok(enc.text.length <= 2000, `share text is ${enc.text.length} chars`);
  assert.strictEqual(enc.full, true);
  const huge = teamsOf(f).reduce((w, team) => W.ops.addTeam(w, team.name + " with a very long team name to push past the limit", {entries: team.entries}), W.newWorkspace());
  const withMine = W.ops.setMyTeam(huge, huge.teams[3].id);
  const big = W.encodeShare(withMine);
  assert.strictEqual(big.full, false, "an oversized league falls back to my team only");
  assert.strictEqual(W.decodeShare(big.text).length, 1);
});
t("test_share_link_decode", () => {
  const { f, rows } = load("4team");
  const ws = teamsOf(f).reduce((w, team) => W.ops.addTeam(w, team.name, {entries: team.entries.concat([{key: "x:DEF:SF", name: "49ers D/ST", pos: "DEF", team: "SF"}])}), W.newWorkspace());
  const back = W.decodeShare(W.encodeShare(ws).text, rows);
  assert.strictEqual(back.length, ws.teams.length);
  back.forEach((team, i) => {
    assert.strictEqual(team.name, ws.teams[i].name);
    assert.deepStrictEqual(team.entries.filter(e => !e.key.startsWith("x:")).map(e => e.key), ws.teams[i].entries.filter(e => !e.key.startsWith("x:")).map(e => e.key));
    assert.ok(team.entries.some(e => e.pos === "DEF"), "a defense travels by name");
  });
});
t("test_export_import", () => {
  const ws = W.ops.addTeam(W.newWorkspace({name: "L"}), "A", {entries: [{key: "1", name: "A", pos: "QB"}]});
  const back = W.importJson(W.exportJson(ws));
  assert.ok(back.workspace, back.error);
  assert.deepStrictEqual(back.workspace.teams, ws.teams);
  assert.ok(W.importJson("not json").error);
  assert.ok(W.importJson(JSON.stringify({id: "x", name: "y"})).error);
  assert.ok(W.importJson(JSON.stringify({id: "x", name: "y", teams: [{entries: [{name: "no key"}]}]})).error);
});
t("test_store_my_roster", () => {
  const mem = memStorage();
  const store = W.createStore({storage: mem, delay: 0});
  store.load();
  const events = [];
  const off = store.subscribe(e => events.push(e));
  assert.deepStrictEqual(store.getMyRoster(), []);
  store.update(w => W.ops.addTeam(w, "Other"), "x");
  assert.strictEqual(events.length, 0, "an unrelated team change is not a my-roster event");
  store.setMyRoster([{key: "1", name: "A", pos: "QB"}, {key: "1", name: "A again", pos: "QB"}]);
  assert.strictEqual(events.length, 1);
  assert.deepStrictEqual(store.getMyRoster().map(e => e.key), ["1"], "entries are de-duplicated by key");
  assert.strictEqual(store.getMyTeam().name, "My team");
  const copy = store.getMyRoster();
  copy.push({key: "9"});
  assert.strictEqual(store.getMyRoster().length, 1, "getMyRoster returns a copy");
  store.setMyRoster([{key: "2", name: "B", pos: "RB"}]);
  assert.strictEqual(store.get().teams.length, 2, "the second call reuses my team");
  off();
  store.setMyRoster([]);
  assert.strictEqual(events.length, 2, "an unsubscribed listener is not called");
  const again = W.createStore({storage: mem, delay: 0});
  assert.strictEqual(again.load(), "ok");
  assert.strictEqual(again.get().teams.length, 2);
});
t("test_store_status_and_debounce", () => {
  const timers = [];
  const mem = memStorage();
  const store = W.createStore({storage: mem, delay: 1000, setTimer: (fn, ms) => { timers.push({fn, ms}); return timers.length; }, clearTimer: () => {}});
  store.load();
  store.update(w => W.ops.addTeam(w, "A"));
  assert.strictEqual(store.status(), "saving");
  assert.strictEqual(mem.writes, 0, "nothing is written before the delay");
  assert.strictEqual(timers[0].ms, 1000);
  timers[timers.length - 1].fn();
  assert.strictEqual(store.status(), "saved");
  const full = W.createStore({storage: {getItem: () => null, setItem() { const e = new Error("full"); e.name = "QuotaExceededError"; throw e; }}, delay: 0});
  full.load();
  full.update(w => W.ops.addTeam(w, "A"));
  assert.strictEqual(full.status(), "full");
  const none = W.createStore({storage: null, delay: 0});
  assert.strictEqual(none.load(), "unavailable");
  none.update(w => W.ops.addTeam(w, "A"));
  assert.strictEqual(none.status(), "unavailable");
  assert.strictEqual(none.get().teams.length, 1, "without storage the league still lives in memory");
});

// ---------- sorting ----------
const sample = [{n: "b", v: 3}, {n: "a", v: 3}, {n: "c", v: null}, {n: "d", v: 9}, {n: "e", v: 1}, {n: "f", v: null}];
const SC = [{id: "v", label: "V", type: "number", first: "desc", get: r => r.v}, {id: "n", label: "N", type: "text", first: "asc", get: r => r.n}];
t("test_sort_core", () => {
  const asc = S.sortRows(sample, SC, {col: "v", dir: "asc"}, [{get: r => r.n, type: "text", dir: "asc"}]).map(r => r.n);
  assert.deepStrictEqual(asc, ["e", "a", "b", "d", "c", "f"]);
  const desc = S.sortRows(sample, SC, {col: "v", dir: "desc"}, [{get: r => r.n, type: "text", dir: "asc"}]).map(r => r.n);
  assert.deepStrictEqual(desc, ["d", "a", "b", "e", "c", "f"], "blanks stay last descending; ties use the chain");
  assert.deepStrictEqual(S.sortRows(sample, SC, {col: "v", dir: "asc"}).map(r => r.n), ["e", "b", "a", "d", "c", "f"], "stable without a chain");
  assert.deepStrictEqual(S.nextState({col: "v", dir: "desc"}, "v", SC), {col: "v", dir: "asc"});
  assert.deepStrictEqual(S.nextState({col: "v", dir: "desc"}, "n", SC), {col: "n", dir: "asc"});
  assert.deepStrictEqual(S.nextState(null, "v", SC), {col: "v", dir: "desc"});
  assert.strictEqual(S.ariaSort({col: "v", dir: "asc"}, "v"), "ascending");
  assert.strictEqual(S.ariaSort({col: "v", dir: "asc"}, "n"), "none");
});

// ---------- team summary ----------
function summaryFor(name, basis) {
  const d = load(name);
  return {d, s: T.summarize(d.teams, {rowsByKey: d.rows, shape: SHAPE, expected: EXPECTED, chartKeys: CH}, {basis})};
}
t("test_summary_roster_value", () => {
  ["2team", "4team", "20team", "partial"].forEach(name => {
    summaryFor(name).s.teams.filter(x => x.hasRoster).forEach(x => {
      ["fund", "market"].forEach(v => assert.ok(Math.abs(x[v].starterValue + x[v].benchValue - x[v].rosterValue) < 1e-9, `${name} ${x.name} ${v}`));
      // recomputed independently from the rows
      const rows = x.fund.lineup.starters.concat(x.fund.lineup.bench);
      assert.ok(Math.abs(rows.reduce((n, r) => n + r.values.ddf_value, 0) - x.fund.rosterValue) < 1e-9);
    });
  });
});
const indepRank = (values) => { const d = [...new Set(values.map(v => Math.round(v * 10) / 10))].sort((a, b) => b - a); return values.map(v => d.indexOf(Math.round(v * 10) / 10) + 1); };
t("test_summary_ranks_fund", () => {
  const { s } = summaryFor("20team");
  const ranked = s.teams.filter(x => x.hasRoster);
  const expect = indepRank(ranked.map(x => ranked.length ? x.fund.rosterValue : 0));
  ranked.forEach((x, i) => assert.strictEqual(x.rank.fund, expect[i], x.name));
  assert.ok(ranked.some(x => x.rank.fund === 1));
});
t("test_summary_ranks_market", () => {
  const { s } = summaryFor("20team");
  const ranked = s.teams.filter(x => x.hasRoster);
  const expect = indepRank(ranked.map(x => x.market.rosterValue));
  ranked.forEach((x, i) => assert.strictEqual(x.rank.market, expect[i], x.name));
  assert.ok(ranked.some(x => x.rank.market !== x.rank.fund), "fixture should have a team whose two ranks differ");
});
t("test_summary_ranks_dense", () => {
  const { d } = summaryFor("4team");
  const base = T.summarize(d.teams, {rowsByKey: d.rows, shape: SHAPE, expected: EXPECTED, chartKeys: CH}, {});
  const top = base.teams.reduce((a, b) => (b.fund.rosterValue > a.fund.rosterValue ? b : a));
  const other = d.teams.findIndex(x => x.id !== top.id);
  const topEntries = d.teams.find(x => x.id === top.id).entries;
  const twin = d.teams.map((x, i) => (i === other ? {...x, entries: topEntries.map(e => ({...e}))} : x));
  const s = T.summarize(twin, {rowsByKey: d.rows, shape: SHAPE, expected: EXPECTED, chartKeys: CH}, {});
  const ranks = s.teams.map(x => x.rank.fund).sort((a, b) => a - b);
  assert.strictEqual(s.teams[other].rank.fund, s.teams.find(x => x.id === top.id).rank.fund, "equal rosters share a rank");
  assert.strictEqual(s.teams.find(x => x.id === top.id).rank.fund, 1);
  const distinct = [...new Set(ranks)];
  assert.deepStrictEqual(distinct, distinct.map((_, i) => i + 1), `dense: ${ranks}`);
});
t("test_summary_strengths", () => {
  const { s, d } = summaryFor("20team");
  const ranked = s.teams.filter(x => x.hasRoster);
  T.POSITIONS.forEach(pos => {
    const sums = ranked.filter(x => x.fund.starterCountByPos[pos] > 0).map(x => x.fund.startersByPos[pos]).sort((a, b) => a - b);
    const mid = sums.length >> 1;
    const median = sums.length % 2 ? sums[mid] : (sums[mid - 1] + sums[mid]) / 2;
    ranked.forEach(x => {
      const b = F.rosterBalance(x.fund.lineup.starters.concat(x.fund.lineup.bench), EXPECTED, "ddf_value", SHAPE).positions[pos];
      const strong = x.strengths.some(i => i.pos === pos);
      const want = b.status !== "under" && Math.round(x.fund.startersByPos[pos] * 10) / 10 >= Math.round(median * 10) / 10;
      assert.strictEqual(strong, want, `${x.name} ${pos} strength`);
    });
  });
});
t("test_summary_weaknesses", () => {
  const { s } = summaryFor("20team");
  const ranked = s.teams.filter(x => x.hasRoster);
  T.POSITIONS.forEach(pos => {
    ranked.forEach(x => {
      const strong = x.strengths.some(i => i.pos === pos);
      const weak = x.weaknesses.some(i => i.pos === pos);
      assert.notStrictEqual(strong, weak, `${x.name} ${pos} is exactly one of strength / weakness with a league median`);
      const b = x.fund.balance.positions[pos];
      if (b.status === "under") assert.ok(weak, `${x.name} ${pos} under depth must be a weakness`);
    });
  });
  const benches = ranked.map(x => x.fund.benchValue).sort((a, b) => a - b);
  const mid = benches.length >> 1;
  const med = benches.length % 2 ? benches[mid] : (benches[mid - 1] + benches[mid]) / 2;
  ranked.forEach(x => assert.strictEqual(Boolean(x.thinBench), Math.round(x.fund.benchValue * 10) / 10 < Math.round(med * 10) / 10, `${x.name} thin bench`));
});
t("test_summary_undervalued", () => {
  const { s } = summaryFor("4team");
  s.teams.forEach(x => {
    const rows = x.fund.lineup.starters.concat(x.fund.lineup.bench);
    const avg = r => CH.reduce((n, k) => n + r.values[k], 0) / CH.length;   // the Trade chart average, computed here independently
    const want = rows.map(r => ({n: r.name, gap: r.values.ddf_value - avg(r)})).filter(g => g.gap > 2.0).sort((a, b) => b.gap - a.gap || a.n.localeCompare(b.n));
    assert.deepStrictEqual(x.under.map(i => [i.name]), want.map(g => [g.n]));
    x.under.forEach(i => assert.ok(Math.abs(i.gap - (i.ddf - i.chart)) < 1e-9));
  });
  assert.ok(s.teams.some(x => x.under.length), "fixture has at least one undervalued player");
});
t("test_summary_overvalued", () => {
  ["4team", "20team"].forEach(name => summaryFor(name).s.teams.forEach(x => {
    const under = new Set(x.under.map(i => i.key));
    x.over.forEach(i => { assert.ok(i.gap < -2.0); assert.ok(!under.has(i.key), `${x.name}: ${i.name} in both lists`); });
    x.under.forEach(i => assert.ok(i.gap > 2.0));
  }));
  assert.ok(summaryFor("20team").s.teams.some(x => x.over.length));
});
t("test_summary_gap_noise", () => {
  const rows = [{player_key: "1", name: "Edge", pos: "RB", values: {ddf_value: 12.0, chart_avg: 10.0}},
    {player_key: "2", name: "Small", pos: "RB", values: {ddf_value: 11.5, chart_avg: 10.0}},
    {player_key: "3", name: "Big", pos: "RB", values: {ddf_value: 14.0, chart_avg: 10.0}},
    {player_key: "4", name: "NoChart", pos: "RB", values: {ddf_value: 30.0, chart_avg: null}},
    {player_key: "5", name: "Neg", pos: "RB", values: {ddf_value: 7.0, chart_avg: 10.0}}];
  const g = T.marketGaps(rows, T.NOISE_FLOOR);
  assert.deepStrictEqual(g.under.map(i => i.name), ["Big"], "a gap of exactly 2.0 and one of 1.5 are not listed; a missing chart value is not listed");
  assert.deepStrictEqual(g.over.map(i => i.name), ["Neg"]);
});
t("test_summary_1_team", () => {
  const d = load("4team");
  const one = [{...d.teams[0], isMine: true}];
  const s = T.summarize(one, {rowsByKey: d.rows, shape: SHAPE, expected: EXPECTED, chartKeys: CH}, {});
  assert.strictEqual(s.teams[0].rank.fund, null);
  assert.strictEqual(s.league.median.RB, null);
  s.teams[0].strengths.concat(s.teams[0].weaknesses).forEach(i => assert.ok(!/median/.test(i.text), i.text));
  assert.ok(/^Your team: starters/.test(T.headline(s)), T.headline(s));
});
t("test_summary_2team_equals_20team", () => {
  const big = load("20team");
  const pair = big.teams.slice(0, 2);
  const a = T.summarize(pair, {rowsByKey: big.rows, shape: SHAPE, expected: EXPECTED, chartKeys: CH}, {});
  const b = T.summarize(big.teams, {rowsByKey: big.rows, shape: SHAPE, expected: EXPECTED, chartKeys: CH}, {});
  pair.forEach((team, i) => {
    const x = a.teams[i];
    const y = b.teams.find(z => z.id === team.id);
    assert.strictEqual(x.fund.rosterValue, y.fund.rosterValue);
    assert.strictEqual(x.market.rosterValue, y.market.rosterValue);
    assert.deepStrictEqual(x.under.map(g => [g.key, g.gap]), y.under.map(g => [g.key, g.gap]));
    assert.deepStrictEqual(x.over.map(g => [g.key, g.gap]), y.over.map(g => [g.key, g.gap]));
  });
});
t("test_summary_partial", () => {
  const { s } = summaryFor("partial");
  assert.strictEqual(s.teams.length, 4);
  const empty = s.teams.find(x => x.size === 0);
  assert.strictEqual(empty.hasRoster, false);
  assert.strictEqual(empty.rank.fund, null, "an empty team is not ranked");
  const small = s.teams.find(x => x.size === 3);
  assert.strictEqual(small.partial, true);
  assert.ok(Number.isFinite(small.rank.fund));
  assert.strictEqual(s.league.rankedCount, 3);
});
t("test_summary_k_def_counted", () => {
  const d = load("4team");
  const withKd = d.teams.map((x, i) => (i === 0 ? {...x, entries: x.entries.concat([{key: "x:DEF:SF", name: "49ers D/ST", pos: "DEF"}, {key: "x:K:k", name: "A Kicker", pos: "K"}])} : x));
  const s = T.summarize(withKd, {rowsByKey: d.rows, shape: SHAPE, expected: EXPECTED, chartKeys: CH}, {});
  const base = T.summarize(d.teams, {rowsByKey: d.rows, shape: SHAPE, expected: EXPECTED, chartKeys: CH}, {});
  assert.strictEqual(s.teams[0].size, base.teams[0].size + 2, "K and DEF count in the player count");
  assert.strictEqual(s.teams[0].fund.rosterValue, base.teams[0].fund.rosterValue, "K and DEF add no value");
});
t("test_summary_headline_independent_of_sort", () => {
  const { s } = summaryFor("4team");
  const before = T.headline(s);
  const cols = T.summaryColumns("fund");
  S.sortRows(s.teams, cols, {col: "benchF", dir: "asc"}, T.SUMMARY_TIES);
  assert.strictEqual(T.headline(s), before);
  assert.ok(/ranks \d+(st|nd|rd|th) of 4 on DDF Value/.test(before), before);
});

// ---------- sort over the real columns ----------
function independentOrder(items, column, dir) {
  const real = items.filter(i => !S.isBlank(column.get(i)));
  const blank = items.filter(i => S.isBlank(column.get(i)));
  real.sort((a, b) => (column.type === "text" ? String(column.get(a)).toLowerCase().localeCompare(String(column.get(b)).toLowerCase()) : column.get(a) - column.get(b)) * (dir === "asc" ? 1 : -1));
  return real.map(i => column.get(i)).concat(blank.map(i => column.get(i)));
}
t("test_sort_numeric_asc_desc", async () => {
  const { s } = summaryFor("20team");
  T.summaryColumns("fund").forEach(col => ["asc", "desc"].forEach(dir => {
    const got = S.sortRows(s.teams, T.summaryColumns("fund"), {col: col.id, dir}, T.SUMMARY_TIES).map(x => col.get(x));
    assert.deepStrictEqual(got, independentOrder(s.teams, col, dir), `summary ${col.id} ${dir}`);
  }));
  const d = await opportunityRows("4team");
  O.OPP_COLUMNS.forEach(col => ["asc", "desc"].forEach(dir => {
    const got = S.sortRows(d.rows, O.OPP_COLUMNS, {col: col.id, dir}, O.OPP_TIES).map(x => col.get(x));
    assert.deepStrictEqual(got, independentOrder(d.rows, col, dir), `opportunities ${col.id} ${dir}`);
  }));
});
t("test_sort_blanks_last", () => {
  const d = load("20team");
  const rows = new Map(d.rows);
  // two players on one team with no chart value: that team's market numbers shrink, a team with no chart data at all is blank
  const noChart = new Map([...d.rows].map(([k, r]) => [k, {...r, values: {...r.values, usatoday: null}}]));
  const s = T.summarize(d.teams, {rowsByKey: noChart, shape: SHAPE, expected: EXPECTED, chartKeys: CH}, {});
  const cols = T.summaryColumns("fund");
  ["asc", "desc"].forEach(dir => {
    const out = S.sortRows(s.teams, cols, {col: "rosterM", dir}, T.SUMMARY_TIES);
    const vals = out.map(x => cols.find(c => c.id === "rosterM").get(x));
    const firstBlank = vals.findIndex(v => S.isBlank(v));
    assert.ok(vals.slice(firstBlank === -1 ? vals.length : firstBlank).every(v => S.isBlank(v)), `blanks last ${dir}`);
  });
  void rows;
  const withBlank = s.teams.map((x, i) => (i < 2 ? {...x, market: null, rank: {...x.rank, market: null}} : x));
  ["asc", "desc"].forEach(dir => {
    const out = S.sortRows(withBlank, cols, {col: "rosterM", dir}, T.SUMMARY_TIES);
    assert.ok(out.slice(-2).every(x => x.market === null), `two blank teams are last, ${dir}`);
  });
});
t("test_sort_rank_unchanged", async () => {
  const { s } = summaryFor("20team");
  const before = new Map(s.teams.map(x => [x.id, x.rank.fund]));
  const out = S.sortRows(s.teams, T.summaryColumns("fund"), {col: "benchF", dir: "asc"}, T.SUMMARY_TIES);
  out.forEach(x => assert.strictEqual(x.rank.fund, before.get(x.id)));
  assert.notDeepStrictEqual(out.map(x => x.id), S.sortRows(s.teams, T.summaryColumns("fund"), T.SUMMARY_DEFAULT, T.SUMMARY_TIES).map(x => x.id), "the order did change");
  const d = await opportunityRows("4team");
  const rb = new Map(d.rows.map(r => [r.id, r.rank]));
  S.sortRows(d.rows, O.OPP_COLUMNS, {col: "capture", dir: "asc"}, O.OPP_TIES).forEach(r => assert.strictEqual(r.rank, rb.get(r.id)));
});
t("test_sort_tiebreak", () => {
  const rows = [{id: "a", name: "Zed", fund: {starterValue: 10, rosterValue: 50}}, {id: "b", name: "Amy", fund: {starterValue: 10, rosterValue: 50}}, {id: "c", name: "Bob", fund: {starterValue: 12, rosterValue: 50}}];
  const col = [{id: "r", label: "R", type: "number", first: "desc", get: r => r.fund.rosterValue}];
  assert.deepStrictEqual(S.sortRows(rows, col, {col: "r", dir: "desc"}, T.SUMMARY_TIES).map(r => r.name), ["Bob", "Amy", "Zed"], "tie: starter value, then name");
  assert.deepStrictEqual(S.sortRows(rows, col, {col: "r", dir: "asc"}, T.SUMMARY_TIES).map(r => r.name), ["Bob", "Amy", "Zed"], "the tie chain does not flip with direction");
});

// ---------- opportunities ----------
const oppCache = {};
function opportunityRows(name, opts) {
  const key = name + JSON.stringify(Object.keys(opts || {}));
  if (oppCache[key]) return oppCache[key];
  const d = load(name);
  const mineIdx = Math.max(0, d.teams.findIndex(x => x.isMine));
  const ctx = ctxFor(d.rows, (opts && opts.ctx) || {});
  const calls = {n: 0};
  const counting = (...args) => { calls.n += 1; return F.findTrades(...args); };
  const cacheMap = (opts && opts.cache) || O.createCache();
  const mine = d.teams[mineIdx];
  const opps = d.teams.filter((_, i) => i !== mineIdx);
  oppCache[key] = O.runAll(mine, opps, {...ctx, findTrades: counting}, {cache: cacheMap, yieldFn: () => Promise.resolve(), budgetMs: 0})
    .then(out => ({rows: out.rows, out, calls, d, mine, opps, ctx, cache: cacheMap}));
  return oppCache[key];
}

// Regression: a valid sell-side player must not disappear before league ranking/filtering.
// Synthetic values are coherent four-chart means, not a replay of the user's league.
t("test_opportunities_preserve_qualified_candidates", async () => {
  const row = (key, charts, projection) => ({player_key: key, name: key, pos: "WR", values: {
    ddf_value: charts.reduce((a, b) => a + b, 0) / charts.length, ddf_value_projections: projection,
    ...Object.fromEntries(CH.map((k, i) => [k, charts[i]]))}});
  const jsn = row("JSN", [20, 20, 20, 20], 9.1);
  const mineRows = [jsn, ...Array.from({length: 3}, (_, i) => row(`other WR ${i}`, [19, 19, 19, 19], 15))];
  const theirRows = Array.from({length: 4}, (_, i) => row(`target ${i}`, [19, 19, 19, 28], 14));
  const team = (id, rows) => ({id, name: id, entries: rows.map(r => ({key: r.player_key}))});
  const mine = team("mine", mineRows), opp = team("opp", theirRows);
  const ctx = {charts: CH, maxSize: 2, rowsByKey: new Map([...mineRows, ...theirRows].map(r => [r.player_key, r]))};
  const direct = F.findTrades(mineRows, theirRows, {chartKeys: CH, maxSize: 2, limit: Infinity});
  const jsnCount = rows => rows.filter(t => t.give.some(r => r.player_key === "JSN")).length;
  assert.strictEqual(direct.total, 52);
  assert.strictEqual(jsnCount(direct.trades), 22);
  assert.strictEqual(jsnCount(direct.trades.slice(0, F.LIMIT)), 0, "fixture exposes premature truncation");
  const pair = O.computePairing(mine, opp, ctx);
  assert.strictEqual(pair.rows.length, direct.total, "every qualified candidate reaches league fit/ranking");
  assert.strictEqual(jsnCount(pair.rows), 22, "default-size search preserves qualified JSN trades");
  const result = await O.runAll(mine, [opp], ctx, {yieldFn: () => Promise.resolve()});
  assert.strictEqual(result.rows.length, direct.total);
  const filtered = O.filterRows(result.rows, {opponent: "opp", minCharts: 3, minCapture: 1});
  assert.strictEqual(jsnCount(filtered), 22, "final filters can still see lower-score candidates");
  assert.deepStrictEqual(new Set(filtered.map(r => r.id)), new Set(pair.rows.map(r => r.id)));
  const capped = O.capPerCore(result.rows, r => r.core.player_key, O.CAP_PER_CORE);
  assert.strictEqual(capped.list.length + [...capped.folds.values()].reduce((n, rows) => n + rows.length, 0), direct.total,
    "presentation folds preserve all candidates for expansion");
});

t("test_opportunities_fit_after_full_search", async () => {
  // JEG-1324: Natural fit 1a reads both sides' DDF Value (projections), so the rows carry it, as engine rows do.
  const base = load("4team"), d = {...base, rows: withProjections(base.rows, spread)}, mine = d.teams[0], opp = d.teams[1];
  const ctx = ctxFor(d.rows);
  const pair = O.computePairing(mine, opp, ctx);
  assert.ok(pair.rows.length > F.LIMIT, "judged fixture exceeds the former cap");
  for (const row of pair.rows) {
    const full = O.fullFit(row);
    const wide = rows => F.withChartAverage(rows, CH);
    const mineRows = mine.entries.map(e => d.rows.get(e.key)).filter(Boolean);
    const oppRows = opp.entries.map(e => d.rows.get(e.key)).filter(Boolean);
    const expected = F.tradeFit({mine: {roster: wide(mineRows), leaving: wide(row.give), arriving: wide(row.receive)},
      theirs: {roster: wide(oppRows), leaving: wide(row.receive), arriving: wide(row.give)}},
      {shape: SHAPE, expected: EXPECTED, weights: WEIGHTS, ourKey: F.OUR_KEY, marketKey: F.MARKET_KEY, chartKeys: CH, z: F.FIT_Z});
    assert.deepStrictEqual(full, expected, "lazy details exactly match direct fit math");
    assert.strictEqual(full.label, row.overall);
    assert.strictEqual(full.variant, row.fit.variant);
    assert.strictEqual(row.fit.us.starterDelta, full.us.starterDelta, "compact summary preserves current-main starter-gain copy");
    assert.deepStrictEqual(O.ourFitOf(full), row.ours);
    assert.deepStrictEqual(O.theirFitOf(full), row.theirs);
  }
  const natural = pair.rows.find((r, i) => i >= F.LIMIT && r.overall === "natural");
  assert.ok(natural, "natural fit beyond old pre-fit cap exists");
  const ranked = O.rankRows(pair.rows);
  const filtered = O.filterRows(ranked, {fit: "natural"});
  assert.ok(filtered.some(r => r.id === natural.id), "natural filter preserves beyond-cap fit");
  assert.deepStrictEqual(O.fullFit(ranked.find(r => r.id === natural.id)), O.fullFit(natural), "rank copy retains detail context");
});
// JEG-1324: "Our fit" is your side of the shared Natural fit predicate and never says "natural" (Natural means both
// sides). The overall Natural fit is exactly both sides passing it.
t("test_opportunities_our_fit_both_sides", () => {
  const base = load("4team"), rows = withProjections(base.rows, spread);
  const pair = O.computePairing(base.teams[0], base.teams[1], ctxFor(rows));
  assert.ok(pair.rows.length > 0, "the fixture pairing produces trades");
  const seen = new Set();
  pair.rows.forEach(row => {
    const full = O.fullFit(row);
    assert.notStrictEqual(row.ours.label, "natural", "a one-side check never says natural");
    assert.strictEqual(row.ours.label === "works", full.natural.us.ok, `works iff your side passes: ${row.id}`);
    assert.strictEqual(row.overall === "natural", full.natural.us.ok && full.natural.them.ok, `natural iff both sides pass: ${row.id}`);
    seen.add(row.ours.label);
  });
  assert.ok(seen.has("works") && seen.size > 1, `the fixture separates our-fit labels: ${[...seen]}`);
});
t("test_opportunities_cancel_during_pairing", async () => {
  const d = load("4team"), ctx = ctxFor(d.rows), cache = O.createCache();
  let yields = 0;
  const result = await O.runAll(d.teams[0], d.teams.slice(1), ctx, {
    cache, budgetMs: -1, yieldFn: async () => { yields += 1; }, isCancelled: () => yields > 0});
  assert.strictEqual(result.cancelled, true);
  assert.strictEqual(result.computed, 0, "cancel before the first pairing finishes");
  assert.strictEqual(cache.size, 0, "partial pairing must not contaminate cache");
  assert.strictEqual(result.rows.length, 0, "interrupted candidates never publish");
  const resumed = await O.runAll(d.teams[0], [d.teams[1]], ctx, {cache, yieldFn: async () => {}});
  assert.deepStrictEqual(resumed.rows.map(r => r.id), O.rankRows(O.computePairing(d.teams[0], d.teams[1], ctx).rows).map(r => r.id));
});

t("test_opportunities_cache_row_budget", async () => {
  const d = load("4team"), ctx = ctxFor(d.rows), cache = O.createCache();
  const many = Array(Math.floor(O.CACHE_MAX_ROWS / 2) + 1).fill(null);
  cache.set("oldest", {rows: many}); cache.set("newer", {rows: many});
  const result = await O.runAll(d.teams[0], [d.teams[1]], ctx, {cache, yieldFn: async () => {}});
  assert.ok(!cache.has("oldest"), "evict old cached rows, not qualified active candidates");
  assert.ok([...cache.values()].reduce((n, entry) => n + entry.rows.length, 0) <= O.CACHE_MAX_ROWS);
  assert.strictEqual(result.rows.length, O.computePairing(d.teams[0], d.teams[1], ctx).total);
});

// JEG-1108: three overall labels; Value fit is retired, so "value" is not a label any more.
const LABELS = ["natural", "market", "force"];
function assertRowShape(r) {
  assert.strictEqual(typeof r.opponent, "string");
  assert.ok(Array.isArray(r.give) && r.give.length && Array.isArray(r.receive) && r.receive.length, "trade");
  assert.ok(r.core && r.receive.includes(r.core), "core player is in the receive set");
  assert.ok(Number.isFinite(r.edge) && r.edge > 0, "fundamentals capture");
  assert.ok(r.edgePct === null || Number.isFinite(r.edgePct), "capture percent");
  // JEG-1324: our side never carries "natural" (Natural means both sides, Jeremy 2026-10-28); JEG-1221 S5 labels.
  assert.ok(["works", "gains, roster issue", "gains, projections fall", "gains, projections not checked", "doesn't work"].includes(r.ours.label), "our team fit");
  assert.ok(Number.isFinite(r.chartEdge), "market perception edge");
  assert.ok(Number.isInteger(r.rivalOkCount) && r.chartCount >= r.rivalOkCount, "charts fair");
  assert.ok(["favorable", "neutral", "hurts"].includes(r.theirs.label), "their team fit");
  assert.ok(LABELS.includes(r.overall), "overall fit");
  assert.ok(Number.isInteger(r.rank) && r.rank >= 1, "rank");
}
t("test_opportunities_columns", async () => {
  const d = await opportunityRows("4team");
  assert.ok(d.rows.length > 0, "the 4-team fixture produces opportunities");
  d.rows.forEach(assertRowShape);
  assert.ok(new Set(d.rows.map(r => r.opponentId)).size >= 2, "rows from more than one opponent");
});
t("test_opportunities_fit_label", () => {
  // JEG-1108: when the finder's tradeFit result is present its label is the overall fit, whatever the sub-signals say.
  ["natural", "market", "force"].forEach(label => assert.strictEqual(O.overallFit("force", false, -9, "hurts", {label}), label, `tradeFit label ${label} is used as is`));
  // Without a tradeFit result (older callers): force when our side fails or the charts are not priced; market when the charts favor them.
  const table = [
    ["natural", true, 3.8, "favorable", "market"], ["natural", true, -1.2, "hurts", "force"], ["natural", false, 2, "favorable", "force"],
    ["partial", true, 0.0, "neutral", "market"], ["force", true, 5, "favorable", "force"], ["force", false, -1, "hurts", "force"]];
  table.forEach(([ours, ok, edge, theirs, want]) => assert.strictEqual(O.overallFit(ours, ok, edge, theirs), want, JSON.stringify([ours, ok, edge, theirs])));
  assert.strictEqual(O.overallFit("natural", true, -0.04, "neutral"), "market", "a chart edge of -0.04 shows as 0.0, not negative");
});
t("test_opportunities_fit_label_rows", async () => {
  const d = await opportunityRows("20team");
  assert.ok(d.rows.length > 0);
  d.rows.forEach(r => assert.strictEqual(r.overall, r.fit.label, `row ${r.id}`));
  const seen = new Set(d.rows.map(r => r.overall));
  assert.ok(seen.size >= 2, `the 20-team fixture shows more than one fit label: ${[...seen]}`);
  assert.ok(!seen.has("value"), "Value fit is retired");
});
t("test_opportunities_rank", async () => {
  const d = await opportunityRows("20team");
  const ranks = d.rows.map(r => r.rank).sort((a, b) => a - b);
  assert.deepStrictEqual(ranks, ranks.map((_, i) => i + 1), "dense 1..N");
  const byRank = d.rows.slice().sort((a, b) => a.rank - b.rank);
  for (let i = 1; i < byRank.length; i++) {
    const a = byRank[i - 1]; const b = byRank[i];
    assert.ok(a.tier <= b.tier, `tier never falls: rank ${a.rank} ${a.overall} then ${b.overall}`);
    if (a.tier === b.tier) assert.ok(Math.round(a.edge * 10) >= Math.round(b.edge * 10), `edge never rises within a tier: ${a.edge} then ${b.edge}`);
  }
});
t("test_opportunities_tier_before_edge", () => {
  const mk = (id, overall, edge) => ({id, opponent: "A", overall, tier: O.TIERS[overall], edge, score: edge, size: 2});
  const out = O.rankRows([mk("a", "force", 20), mk("b", "natural", 1), mk("c", "market", 9), mk("d", "market", 3), mk("e", "natural", 4)]);
  assert.deepStrictEqual(out.map(r => r.id), ["e", "b", "c", "d", "a"]);
  assert.deepStrictEqual(out.map(r => r.rank), [1, 2, 3, 4, 5]);
});
// ---------- JEG-885: at most CAP_PER_CORE rows for one received core player, the rest folded ----------
t("test_opportunities_cap_per_core", () => {
  const rows = [{key: "a", core: {player_key: "A"}}, {key: "b", core: {player_key: "A"}}, {key: "c", core: {player_key: "A"}},
    {key: "d", core: {player_key: "A"}}, {key: "e", core: {player_key: "B"}}];
  const out = O.capPerCore(rows, r => r.core.player_key, O.CAP_PER_CORE);
  assert.strictEqual(O.CAP_PER_CORE, 2);
  assert.deepStrictEqual(out.list.map(r => r.key), ["a", "b", "e"], "at most two rows per received core player, in the order given");
  assert.deepStrictEqual([...out.folds].map(([k, v]) => [k, v.map(r => r.key)]), [["A", ["c", "d"]]], "the rest fold under the core player");
  // Selection only: the very same row objects, in the very same order, and a core with no overflow has no fold.
  assert.strictEqual(out.list[0], rows[0]);
  assert.strictEqual(out.list[2], rows[4]);
  assert.strictEqual(out.folds.has("B"), false, "a core with rows under the cap has no fold");
  // A core with exactly the cap keeps both rows and folds nothing.
  const exact = O.capPerCore(rows.slice(0, 2), r => r.core.player_key, 2);
  assert.deepStrictEqual(exact.list.map(r => r.key), ["a", "b"]);
  assert.strictEqual(exact.folds.size, 0);
  // The key is matched as a string: 7 and "7" are the same core player.
  const mixed = O.capPerCore([{core: {player_key: 7}}, {core: {player_key: "7"}}, {core: {player_key: 7}}], r => r.core.player_key, 2);
  assert.deepStrictEqual(mixed.list.map(r => r.core.player_key), [7, "7"]);
  assert.strictEqual(mixed.folds.get("7").length, 1);
});
t("test_opportunities_cap_on_a_fixture", async () => {
  const d = await opportunityRows("2team");
  const key = r => r.core.player_key;
  // All candidates now survive pairing; isolate one core rather than assuming the old top ten were the entire result.
  const rows = d.rows.filter(r => key(r) === key(d.rows[0]));
  assert.ok(rows.length >= 4, `the core player has 4 or more rows (${rows.length})`);
  const out = O.capPerCore(rows, key, O.CAP_PER_CORE);
  assert.strictEqual(out.list.length, 2, "two rows stay visible");
  assert.strictEqual(out.folds.get(String(rows[0].core.player_key)).length, rows.length - 2, "the rest fold under that player");
  assert.deepStrictEqual(out.list.map(r => r.id), rows.slice(0, 2).map(r => r.id), "the two best stay, in rank order");
});
t("test_opportunities_1_opponent", async () => {
  const d = await opportunityRows("2team");
  assert.strictEqual(d.opps.length, 1);
  assert.ok(d.rows.length > 0, "the 2-team fixture produces opportunities");
  d.rows.forEach(assertRowShape);
  // The same pairing inside the 4-team run gives the same rows: no special case for one opponent.
  const four = await opportunityRows("4team");
  const opp = four.opps[0];
  const alone = await O.runAll(four.mine, [opp], four.ctx, {yieldFn: () => Promise.resolve(), budgetMs: 0});
  const within = four.rows.filter(r => r.opponentId === opp.id);
  assert.deepStrictEqual(alone.rows.map(r => r.id).sort(), within.map(r => r.id).sort());
  assert.deepStrictEqual(alone.rows.map(r => r.overall).sort(), within.map(r => r.overall).sort());
  // And it is the two-team finder's list: same trades, same edges.
  const direct = F.findTrades([...four.mine.entries].map(e => four.d.rows.get(e.key)).filter(Boolean), opp.entries.map(e => four.d.rows.get(e.key)).filter(Boolean),
    {chartKeys: CH, maxSize: 2, limit: Infinity, sanity: {shape: SHAPE, mine: four.mine.entries.map(e => four.d.rows.get(e.key)).filter(Boolean), theirs: opp.entries.map(e => four.d.rows.get(e.key)).filter(Boolean), keepMine: true, keepTheirs: true}});
  assert.deepStrictEqual(within.map(r => Math.round(r.edge * 1000)).sort((a, b) => a - b), direct.trades.map(x => Math.round(x.edge * 1000)).sort((a, b) => a - b), "edges come straight from findTrades");
});
t("test_opportunities_partial", async () => {
  const d = await opportunityRows("partial");
  const small = d.out.perOpponent.find(p => p.partial);
  assert.ok(small, "a partial opponent is flagged");
  assert.strictEqual(d.out.skipped, 1, "the empty team is skipped");
  assert.ok(!d.out.perOpponent.some(p => p.evaluated === 0));
  d.rows.forEach(assertRowShape);
});
t("test_multi_trade_cache", async () => {
  const d = load("4team");
  const mine = d.teams[0];
  const opps = d.teams.slice(1);
  const ctx = ctxFor(d.rows);
  let calls = 0;
  const counting = (...a) => { calls += 1; return F.findTrades(...a); };
  const cache = O.createCache();
  const run = (m, o, c) => O.runAll(m, o, {...(c || ctx), findTrades: counting}, {cache, yieldFn: () => Promise.resolve(), budgetMs: 0});
  const first = await run(mine, opps);
  assert.strictEqual(calls, opps.length);
  assert.strictEqual(first.computed, opps.length);
  const second = await run(mine, opps);
  assert.strictEqual(calls, opps.length, "nothing changed: nothing recomputed");
  assert.strictEqual(second.reused, opps.length);
  assert.deepStrictEqual(second.rows.map(r => r.id), first.rows.map(r => r.id));
  const edited = opps.map((o, i) => (i === 1 ? {...o, entries: o.entries.slice(0, -1)} : o));
  const third = await run(mine, edited);
  assert.strictEqual(calls, opps.length + 1, "one opponent changed: only its pairing is recomputed");
  assert.strictEqual(third.reused, opps.length - 1);
  const renamed = opps.map((o, i) => (i === 0 ? {...o, name: "Renamed"} : o));
  const fourth = await run(mine, renamed);
  assert.strictEqual(calls, opps.length + 1, "a rename recomputes nothing");
  assert.ok(fourth.rows.some(r => r.opponent === "Renamed") && !fourth.rows.some(r => r.opponent === opps[0].name), "and the cached rows carry the new name");
  const mineEdited = {...mine, entries: mine.entries.slice(1)};
  await run(mineEdited, opps);
  assert.strictEqual(calls, opps.length + 1 + opps.length, "my roster changed: every pairing is recomputed");
  const rescaled = new Map([...d.rows].map(([k, r]) => [k, {...r, values: {...r.values, ddf_value: r.values.ddf_value * 1.07}}]));
  const fifth = await run(mine, opps, ctxFor(rescaled));
  assert.strictEqual(fifth.reused, 0, "new values (a settings change) never reuse old answers");
});
t("test_opportunities_filters", async () => {
  const d = await opportunityRows("20team");
  const natural = O.filterRows(d.rows, {fit: "natural"}, false);
  assert.ok(natural.every(r => r.overall === "natural"));
  assert.ok(natural.length < d.rows.length);
  const nv = O.filterRows(d.rows, {fit: "naturalMarket"}, false);
  assert.ok(nv.every(r => r.overall === "natural" || r.overall === "market"));
  assert.strictEqual(nv.length, d.rows.filter(r => r.overall !== "force").length, "Natural and market supported = everything but force");
  const noForce = O.filterRows(d.rows, {}, true);
  assert.strictEqual(noForce.length, d.rows.filter(r => r.overall !== "force").length);
  assert.ok(d.rows.some(r => r.overall === "force"), "the 20-team fixture has force fits to hide");
  const opp = d.rows[0].opponentId;
  assert.ok(O.filterRows(d.rows, {opponent: opp}, false).every(r => r.opponentId === opp));
  assert.ok(O.filterRows(d.rows, {minCapture: 5}, false).every(r => r.edge >= 5));
  assert.ok(O.filterRows(d.rows, {minCharts: 4}, false).every(r => r.rivalOkCount >= 4));
});
t("test_opportunities_cap_and_headline", async () => {
  const d = load("20team");
  const mine = d.teams[0];
  const many = [];
  for (let i = 0; i < 24; i++) many.push({...d.teams[1 + (i % 19)], id: `c${i}`, name: `Copy ${i}`});
  const out = await O.runAll(mine, many, ctxFor(d.rows), {cache: O.createCache(), yieldFn: () => Promise.resolve(), budgetMs: 0});
  assert.strictEqual(out.perOpponent.length, O.MAX_OPPONENTS);
  assert.strictEqual(out.capped, true);
  const head = O.leagueHeadline(out, null);
  assert.ok(head.startsWith(`${out.rows.length} trade opportunities across ${O.MAX_OPPONENTS} opponents.`), head);
  const one = await O.runAll(mine, [many[0]], ctxFor(d.rows), {yieldFn: () => Promise.resolve(), budgetMs: 0});
  assert.ok(/across 1 opponent\./.test(O.leagueHeadline(one, null)), "same sentence for one opponent");
});

// ---------- JEG-1081 (PR 4): the third view, position allocation wording, the projections-vs-charts disagreement list ----------
// Rows with a projection value per player: ddf_value plus a deterministic offset (the frozen fixtures carry none).
function withProjections(rows, offsetOf) {
  const out = new Map();
  let i = 0;
  rows.forEach((r, k) => { out.set(k, {...r, values: {...r.values, ddf_value_projections: r.values.ddf_value + offsetOf(i++, r)}}); });
  return out;
}
const spread = i => [-3.1, -1.2, 0.4, 2.6, 4.3][i % 5];
function summaryWith(name, rows) {
  const d = load(name);
  return {d, s: T.summarize(d.teams, {rowsByKey: rows, shape: SHAPE, expected: EXPECTED, chartKeys: CH}, {basis: "fund"})};
}
t("test_summary_ranks_proj", () => {
  const d = load("20team");
  const { s } = summaryWith("20team", withProjections(d.rows, spread));
  const ranked = s.teams.filter(x => x.hasRoster);
  ranked.forEach(x => assert.ok(x.proj && x.proj.key === "ddf_value_projections", x.name));
  const expect = indepRank(ranked.map(x => x.proj.rosterValue));
  ranked.forEach((x, i) => assert.strictEqual(x.rank.proj, expect[i], x.name));
  // the projections lineup is its own reading: it differs from the DDF Value one for at least one team
  assert.ok(ranked.some(x => Math.abs(x.proj.rosterValue - x.fund.rosterValue) > 0.5), "projections view should differ");
  // without projection values there is no third view and no third rank (never a zero)
  const none = summaryFor("20team").s;
  none.teams.filter(x => x.hasRoster).forEach(x => { assert.strictEqual(x.proj, null, x.name); assert.strictEqual(x.rank.proj, null, x.name); });
});
t("test_summary_disagree_list", () => {
  const d = load("20team");
  const rowsP = withProjections(d.rows, spread);
  const { s } = summaryWith("20team", rowsP);
  let listed = 0;
  s.teams.filter(x => x.hasRoster).forEach(x => {
    x.higher.forEach(i => { assert.ok(i.gap > 2.0 && Math.abs(i.projections - i.charts - i.gap) < 1e-9, `${x.name} ${i.name}`); listed += 1; });
    x.lower.forEach(i => { assert.ok(i.gap < -2.0, `${x.name} ${i.name}`); listed += 1; });
    // independent recount from the team's rows
    const members = d.teams.find(tm => tm.id === x.id).entries.map(e => rowsP.get(String(e.key))).filter(Boolean);
    assert.strictEqual(x.higher.length, members.filter(r => r.values.ddf_value_projections - r.values.ddf_value > 2.0).length, `${x.name} higher`);
    assert.strictEqual(x.lower.length, members.filter(r => r.values.ddf_value_projections - r.values.ddf_value < -2.0).length, `${x.name} lower`);
    const sizes = x.higher.map(i => Math.abs(i.gap));
    sizes.forEach((g, k) => { if (k) assert.ok(sizes[k - 1] >= g, `${x.name} higher is not in size order`); });
  });
  assert.ok(listed > 0, "the offsets must put some players beyond 2.0");
  // projections equal to the charts: nothing disagrees; just under the floor: nothing listed
  summaryWith("20team", withProjections(d.rows, () => 0)).s.teams.forEach(x => assert.strictEqual(x.higher.length + x.lower.length, 0, x.name));
  summaryWith("20team", withProjections(d.rows, () => 1.99)).s.teams.forEach(x => assert.strictEqual(x.higher.length, 0, `${x.name} under the floor`));
});
t("test_summary_proj_partial", () => {
  // one team has a player with no projection: that team has no projections view or rank (never an understated one); the rest are ranked
  const d = load("20team");
  const rowsP = withProjections(d.rows, spread);
  const victim = d.teams[0].entries.map(e => rowsP.get(String(e.key))).find(r => ["QB", "RB", "WR", "TE"].includes(r.pos));
  const holed = new Map(rowsP);
  holed.set(String(victim.player_key), {...victim, values: {...victim.values, ddf_value_projections: null}});
  const { s } = summaryWith("20team", holed);
  const t0 = s.teams.find(x => x.id === d.teams[0].id);
  assert.strictEqual(t0.proj, null);
  assert.strictEqual(t0.rank.proj, null);
  const others = s.teams.filter(x => x.hasRoster && x.id !== t0.id);
  others.forEach(x => assert.ok(x.rank.proj >= 1, x.name));
  assert.strictEqual(Math.max(...others.map(x => x.rank.proj)) <= others.length, true);
});
t("test_summary_disagree_charts_key", () => {
  // the gap is projections minus ddf_value_charts when the row has it, even when ddf_value was moved by an Overrides basis
  const d = load("4team");
  const rows = new Map();
  d.rows.forEach((r, k) => rows.set(k, {...r, values: {...r.values, ddf_value: r.values.ddf_value + 50, ddf_value_charts: r.values.ddf_value, ddf_value_projections: r.values.ddf_value + 3.5}}));
  const { s } = summaryWith("4team", rows);
  const items = s.teams.flatMap(x => x.higher);
  assert.ok(items.length > 0);
  items.forEach(i => assert.ok(Math.abs(i.gap - 3.5) < 1e-9, `${i.name} gap ${i.gap}`));
  // the column sorts on the signed biggest gap
  const col = T.summaryColumns("fund").find(c => c.id === "disagree");
  s.teams.filter(x => x.higher.length).forEach(x => assert.ok(Math.abs(col.get(x) - 3.5) < 1e-9));
  s.teams.filter(x => !x.higher.length && !x.lower.length).forEach(x => assert.strictEqual(col.get(x), null));
  // a lower gap sorts as a negative number
  const low = summaryWith("4team", withProjections(d.rows, () => -3.5)).s;
  const lowers = low.teams.filter(x => x.lower.length);
  assert.ok(lowers.length > 0);
  lowers.forEach(x => assert.ok(Math.abs(col.get(x) + 3.5) < 1e-9, `${x.name} lower sorts as ${col.get(x)}`));
});
t("test_opportunities_proj_agreement", async () => {
  // JEG-1081 PR 5: projections agree = (received - given) in DDF Value (projections) is a gain (tick), a loss (cross), level or unpriced (null)
  const d = load("4team");
  const rowsP = withProjections(d.rows, i => [-6, 5, -2, 7, 1.5][i % 5]);
  const mine = d.teams[0];
  const opps = d.teams.slice(1);
  const run = rows => O.runAll(mine, opps, ctxFor(rows), {yieldFn: () => Promise.resolve(), budgetMs: 0});
  const out = await run(rowsP);
  assert.ok(out.rows.length > 0);
  const sum = (list) => list.reduce((n, r) => n + r.values.ddf_value_projections, 0);
  out.rows.forEach(r => {
    const want = sum(r.receive) - sum(r.give);
    assert.ok(Math.abs(r.projEdge - want) < 1e-9, `${r.id} projEdge ${r.projEdge} vs ${want}`);
    assert.strictEqual(r.projAgrees, want >= 0.05 ? true : want <= -0.05 ? false : null, `${r.id} agrees for ${want}`);
  });
  assert.ok(out.rows.some(r => r.projAgrees === true) && out.rows.some(r => r.projAgrees === false), "the offsets must give both a tick and a cross");
  // no projection values at all: nothing agrees or disagrees, and nothing is 0
  const none = await run(d.rows);
  none.rows.forEach(r => { assert.strictEqual(r.projEdge, null, r.id); assert.strictEqual(r.projAgrees, null, r.id); });
  // one package player without a projection: null, not a partial sum
  const holed = new Map(rowsP);
  const first = out.rows[0];
  const gone = first.give[0];
  holed.set(String(gone.player_key), {...gone, values: {...gone.values, ddf_value_projections: null}});
  const part = await run(holed);
  part.rows.filter(r => r.give.concat(r.receive).some(p => String(p.player_key) === String(gone.player_key))).forEach(r => assert.strictEqual(r.projAgrees, null, r.id));
  // the boundaries and the column
  assert.strictEqual(O.projAgreement(0.05), true);
  assert.strictEqual(O.projAgreement(0.049), null);
  assert.strictEqual(O.projAgreement(-0.049), null);
  assert.strictEqual(O.projAgreement(-0.05), false);
  assert.strictEqual(O.projAgreement(NaN), null);
  assert.strictEqual(O.projAgreement(null), null);
  const col = O.OPP_COLUMNS.find(c => c.id === "proj");
  assert.deepStrictEqual([true, false, null].map(v => col.get({projAgrees: v})), [1, 0, null]);
});
t("test_summary_allocation_wording", () => {
  const d = load("4team");
  const { s } = summaryWith("4team", withProjections(d.rows, spread));
  s.teams.filter(x => x.hasRoster).forEach(x => x.strengths.concat(x.weaknesses).forEach(i => {
    assert.ok(/ allocation (above|below|at or above) /.test(i.text), i.text);
    if (x.strengths.includes(i)) assert.ok(/ allocation (above|at or above) /.test(i.text), `strength says ${i.text}`);
    if (x.weaknesses.includes(i)) assert.ok(/ allocation below /.test(i.text), `weakness says ${i.text}`);
    assert.ok(!/fundamental|Strongest|Thinnest/.test(i.text), i.text);
  }));
  const head = T.headline(s);
  assert.ok(/^Your team ranks \d+(st|nd|rd|th) of 4 on DDF Value, \d+(st|nd|rd|th) on projections, \d+(st|nd|rd|th) on market\./.test(head), head);
  assert.ok(/Position allocation: (heavy at [A-Z]+|light at [A-Z]+)/.test(head), head);
  assert.ok(!/fundamental|Strongest|Thinnest/.test(head), head);
});

(async () => {
  for (const { name, fn } of queue) {
    try { await fn(); } catch (error) { failures.push({name, message: String((error && error.message) || error).slice(0, 500)}); }
  }
  process.stdout.write(JSON.stringify({ran, failures}));
})();
