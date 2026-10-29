// JEG-1240: the USO-shape trade journey, as a contract on the real page modules. Pure Node, no browser.
//
//   node tests/node/uso_site_journey_contract.cjs check <dir with workspace.js, finder.js, opportunities.js, ddf-state.js> <league.json>
//       Runs the journey on modeled values and prints {ran, failures, facts}.
//   node tests/node/uso_site_journey_contract.cjs diff <origin.json> <destination.json> [tolerance]
//       Compares two trade-context envelopes (the render test reads them off the page) and prints {differences}.
//
// The journey: load the USO-shape league, read both sides' starters and bench by position, run the league-wide
// search with no candidate cap, find the trades that send Jaxon Smith-Njigba (key 3247), pick an exact candidate and
// an unequal one, then carry each one to Compare (the site's DDF state link) and to the pair finder (its own link) and
// require the same players, values, sources, settings and gains on arrival. Nothing here asserts a fit label: JSN only
// has to be discoverable. Values are MODELED (a deterministic hash per player key, the same scheme as
// tests/league_harness.cjs), never published or USO numbers; the render test does the same journey on the built page.
// tests/test_uso_site_journey_render.py runs this on the real modules and, for each mutation, on a broken copy that must
// fail for the named reason.
"use strict";
const path = require("path");
const fs = require("fs");
const assert = require("assert");

const CH = ["usatoday", "fantasycalc", "fantasypros", "cbs"];
const OUR_KEY = "ddf_value";
const MARKET_KEY = "chart_avg";
const PROJ_KEY = "ddf_value_projections";
const SKILL = ["QB", "RB", "WR", "TE"];

// ---------- the envelope: everything a trade must keep between screens ----------
// ctx: {settings, basis, level, charts, market, shape, rowsByKey}. teams: {mine, theirs}, each {id, entries}.
// give / get: player keys. A view a player has no value in is null, never 0.
const num = v => (typeof v === "number" && Number.isFinite(v) ? v : null);
function envelope(F, ctx, teams, give, get) {
  const rowsOf = team => team.entries.map(e => ctx.rowsByKey.get(String(e.key))).filter(Boolean);
  const market = ctx.market && ctx.market.length >= F.MIN_CHARTS ? ctx.market : null;
  const wide = rows => (market ? F.withChartAverage(rows, market) : rows);
  const byKey = new Map(wide([...ctx.rowsByKey.values()]).map(r => [String(r.player_key), r]));
  const pick = keys => keys.map(k => byKey.get(String(k))).filter(Boolean);
  // Priced players by key; K, DEF and anything that does not resolve to a row are counted, not valued.
  const priced = e => !F.isNotEvaluated(e) && ctx.rowsByKey.has(String(e.key));
  const side = team => ({id: team.id, keys: team.entries.filter(priced).map(e => String(e.key)).sort(),
    notEvaluated: team.entries.filter(e => !priced(e)).length});
  const values = {};
  give.concat(get).forEach(k => {
    const r = byKey.get(String(k));
    values[k] = r ? {ddf: num(r.values[OUR_KEY]), market: market ? num(r.values[MARKET_KEY]) : null, proj: num(r.values[PROJ_KEY])} : null;
  });
  const gains = {};
  if (ctx.shape) {
    const g = (team, leaving, arriving, key) => F.rosterImpact(wide(rowsOf(team)), pick(leaving), pick(arriving), ctx.shape, key);
    const us = g(teams.mine, give, get, OUR_KEY);
    const them = g(teams.theirs, get, give, OUR_KEY);
    gains.us = {ddf: num(us.starterDelta), ddfBefore: num(us.before.starterValue)};
    gains.them = {ddf: num(them.starterDelta)};
    if (market) {
      gains.us.market = num(g(teams.mine, give, get, MARKET_KEY).starterDelta);
      gains.them.market = num(g(teams.theirs, get, give, MARKET_KEY).starterDelta);
    }
  }
  return {settings: ctx.settings, basis: ctx.basis === undefined ? null : ctx.basis, level: ctx.level === undefined ? null : ctx.level,
    sources: {charts: (ctx.charts || []).slice().sort(), market: market ? market.slice().sort() : null},
    mine: side(teams.mine), theirs: side(teams.theirs), give: give.map(String), get: get.map(String), values, gains};
}

// Each difference names what was lost or swapped. tol: numbers equal within it (the page shows one decimal).
function diff(a, b, tol) {
  const t = tol === undefined ? 1e-9 : tol;
  const out = [];
  const add = (code, where, message) => out.push({code, where, message});
  const same = (x, y) => (x === null || y === null ? x === y : Math.abs(x - y) <= t);
  const json = v => JSON.stringify(v === undefined ? null : v);
  if (json(a.settings) !== json(b.settings)) add("settings-changed", "settings", `league settings ${json(a.settings)} became ${json(b.settings)}`);
  if (json(a.basis) !== json(b.basis)) add("basis-changed", "basis", `value basis ${json(a.basis)} became ${json(b.basis)}`);
  if (json(a.level) !== json(b.level)) add("level-changed", "level", `bench level ${json(a.level)} became ${json(b.level)}`);
  if (json(a.sources) !== json(b.sources)) add("sources-changed", "sources", `sources ${json(a.sources)} became ${json(b.sources)}`);
  ["mine", "theirs"].forEach(s => {
    const x = a[s] || {}, y = b[s] || {};
    if (!b[s]) add("team-missing", s, `${s} roster did not arrive`);
    else if (json(x.keys) !== json(y.keys) || (x.id && y.id && x.id !== y.id)) {
      add("team-substituted", s, `${s} roster ${x.id} (${(x.keys || []).length} players) arrived as ${y.id} (${(y.keys || []).length} players)`);
    } else if (x.notEvaluated !== y.notEvaluated) add("not-evaluated-changed", s, `${s} not-evaluated count ${x.notEvaluated} became ${y.notEvaluated}`);
  });
  // A package is a set of players: the order a screen lists them in is not part of it.
  const set = list => json((list || []).slice().sort());
  if (set(a.give) !== set(b.give) || set(a.get) !== set(b.get))
    add("package-changed", "package", `give ${json(a.give)} get ${json(a.get)} arrived as give ${json(b.give)} get ${json(b.get)}`);
  Object.keys(a.values || {}).forEach(k => {
    const x = a.values[k], y = (b.values || {})[k];
    if (y === undefined) { add("value-missing", `values.${k}`, `player ${k} has no value entry on arrival`); return; }
    if (x === null || y === null) { if (x !== y) add("value-changed", `values.${k}`, `player ${k} ${json(x)} became ${json(y)}`); return; }
    ["ddf", "market", "proj"].forEach(v => {
      if (x[v] === undefined) return;
      if (x[v] === null && y[v] !== null) add("value-filled", `values.${k}.${v}`, `player ${k} had no ${v} value and arrived with ${y[v]}`);
      else if (x[v] !== null && y[v] === null) add("value-lost", `values.${k}.${v}`, `player ${k} ${v} ${x[v]} arrived unavailable`);
      else if (!same(x[v], y[v])) add("value-changed", `values.${k}.${v}`, `player ${k} ${v} ${x[v]} became ${y[v]}`);
    });
  });
  ["us", "them"].forEach(s => {
    const x = (a.gains || {})[s], y = (b.gains || {})[s];
    if (!x) return;
    if (!y) { add("gains-missing", `gains.${s}`, `${s} lineup gains did not arrive`); return; }
    Object.keys(x).forEach(v => {
      if (y[v] === undefined || (x[v] !== null && y[v] === null)) add("gains-missing", `gains.${s}.${v}`, `${s} ${v} gain ${x[v]} did not arrive`);
      else if (!same(x[v], y[v])) add("gains-changed", `gains.${s}.${v}`, `${s} ${v} gain ${x[v]} became ${y[v]}`);
    });
  });
  return out;
}

// ---------- the journey on the real modules ----------
function hash(text) { let h = 2166136261; for (const c of String(text)) { h ^= c.charCodeAt(0); h = Math.imul(h, 16777619) >>> 0; } return h >>> 0; }
const unit = (key, salt) => (hash(`${key}:${salt}`) % 10000) / 10000;
// MODELED values: deterministic, coherent DDF / four charts / projections per key. Not published, not USO's.
function modeledRows(players, holes) {
  const map = new Map();
  players.forEach(p => {
    if (String(p.key).startsWith("x:") || map.has(String(p.key))) return;
    const ddf = Math.round((4 + 36 * Math.pow(unit(p.key, "d"), 1.6)) * 10) / 10;
    const values = {[OUR_KEY]: ddf, [PROJ_KEY]: Math.round(ddf * (0.8 + 0.4 * unit(p.key, "p")) * 10) / 10};
    const market = 0.62 + 0.76 * unit(p.key, "m");
    CH.forEach(k => { values[k] = Math.round(ddf * market * (0.9 + 0.2 * unit(p.key, k)) * 10) / 10; });
    (holes && holes[p.key] || []).forEach(k => { delete values[k]; });
    map.set(String(p.key), {player_key: String(p.key), name: p.name, pos: p.pos, team: p.team || "", values});
  });
  return map;
}

function run(appDir, fixturePath) {
  const W = require(path.join(appDir, "workspace.js"));
  const F = require(path.join(appDir, "finder.js"));
  const O = require(path.join(appDir, "opportunities.js"));
  const S = require(path.join(appDir, "ddf-state.js"));
  const fx = JSON.parse(fs.readFileSync(fixturePath, "utf8"));
  const JSN = fx.focus.key;
  const shape = {QB: fx.settings.roster.QB, RB: fx.settings.roster.RB, WR: fx.settings.roster.WR, TE: fx.settings.roster.TE,
    FLEX: fx.settings.roster.FLEX, SUPERFLEX: fx.settings.roster.SUPERFLEX};
  const n = fx.settings.teams;
  const per = pos => fx.teams[0].players.filter(p => p.pos === pos).length;
  // Modeled league-wide seats for the USO shape: the dedicated starters, FLEX split RB/WR, the rest bench.
  const allocation = SKILL.map(pos => {
    const lineup = n * (shape[pos] + (pos === "RB" || pos === "WR" ? shape.FLEX / 2 : 0));
    return {pos, rostered: n * per(pos), lineup, bench: n * per(pos) - lineup};
  });
  const settings = {scoring: fx.settings.scoring, teams: n, roster: {...shape, BENCH: fx.settings.roster.BENCH}};
  const players = [].concat(...fx.teams.map(t => t.players));
  // One received-side player has no FantasyPros value: the Trade chart average must stay unavailable, never 0.
  const rowsByKey = modeledRows(players);
  let ws = W.newWorkspace({name: "USO-shape journey"});
  fx.teams.forEach(t => { ws = W.ops.addTeam(ws, t.name, {entries: t.players}); });
  ws = W.ops.setMyTeam(ws, ws.teams[fx.myTeamIndex].id);
  const teams = ws.teams.map(t => ({id: t.id, name: t.name, entries: t.entries}));
  const mine = teams.find(t => t.id === ws.myTeamId);
  const opps = teams.filter(t => t.id !== ws.myTeamId);
  const ctx = {rowsByKey, shape, expected: F.expectedDepth(allocation, n), weights: {overall: 0.3, QB: 0.2, RB: 0.3, WR: 0.3, TE: 0.25},
    charts: CH.slice(), market: CH.slice(), maxSize: 2, keepMine: true, keepTheirs: true};
  const env = {settings, basis: "default", level: null, charts: CH, market: CH, shape, rowsByKey};
  const facts = {values: "modeled", fixture: fx.fixture, players_as_of: fx.players_as_of, shape: fx.shape_source};

  const ran = [], failures = [], queue = [];
  const t = (name, fn) => { ran.push(name); queue.push({name, fn}); };
  let search = null;
  const searchOnce = async () => {
    if (!search) search = await O.runAll(mine, opps, ctx, {yieldFn: () => Promise.resolve(), budgetMs: 0});
    return search;
  };
  const gives = (r, key) => r.give.some(p => String(p.player_key) === key);
  let picks = null;
  const pickOnce = async () => {
    if (picks) return picks;
    const rows = (await searchOnce()).rows;
    const jsnRows = rows.filter(r => gives(r, JSN));
    const equal = jsnRows.find(r => !r.addedThrowIns && !r.unbalanced) || null;
    // Discovery evens the player counts with throw-ins (JEG-1108), so the unequal case is a package whose core was
    // unequal: the candidate keeps its throw-in, and the explicit deal without it is a true 2-for-1 for Compare.
    const thrownKeys = r => new Set((r.addedThrowIns || []).map(a => String(a.row.player_key)));
    const unequal = jsnRows.find(r => r.addedThrowIns && !thrownKeys(r).has(JSN)) || jsnRows.find(r => r.addedThrowIns)
      || rows.find(r => r.addedThrowIns) || null;
    let explicit = null;
    if (unequal) {
      const thrown = new Set(unequal.addedThrowIns.map(a => String(a.row.player_key)));
      explicit = {id: `${unequal.id}#explicit`, opponentId: unequal.opponentId, opponent: unequal.opponent,
        give: unequal.give.filter(p => !thrown.has(String(p.player_key))), receive: unequal.receive.filter(p => !thrown.has(String(p.player_key)))};
    }
    picks = {equal, unequal, explicit};
    return picks;
  };
  const keysOf = list => list.map(p => String(p.player_key));
  const teamOf = id => teams.find(x => x.id === id);

  t("test_fixture_is_uso_shape_and_synthetic", () => {
    assert.strictEqual(fx.teams.length, 12, "12 teams");
    fx.teams.forEach(team => assert.strictEqual(team.players.length, 15, `${team.name}: 15 players (8 starters, K, DEF, 5 bench)`));
    assert.deepStrictEqual(settings.roster, {QB: 1, RB: 2, WR: 3, TE: 1, FLEX: 1, SUPERFLEX: 0, BENCH: 5});
    assert.strictEqual(settings.scoring, "half_ppr");
    assert.ok(mine.entries.some(e => e.key === JSN), "JSN is on the user's team");
    assert.ok(fx.teams.every(team => /^(My team|Team \d\d)$/.test(team.name)), "anonymized team names only");
    const skill = players.filter(p => !String(p.key).startsWith("x:"));
    assert.strictEqual(skill.filter(p => !rowsByKey.has(String(p.key))).length, 0, "every skill player has a row");
    assert.strictEqual(new Set(skill.map(p => p.key)).size, skill.length, "no player on two rosters");
  });

  t("test_both_sides_starters_and_bench_by_position", () => {
    const market = rows => F.withChartAverage(rows, CH);
    [mine].concat(opps).forEach(team => {
      const rows = team.entries.map(e => rowsByKey.get(String(e.key))).filter(Boolean);
      [[OUR_KEY, rows], [MARKET_KEY, market(rows)]].forEach(([key, list]) => {
        const lv = F.lineupValue(list, shape, key);
        assert.strictEqual(lv.starters.length, 8, `${team.name} ${key}: 8 starters`);
        assert.strictEqual(lv.bench.length, 5, `${team.name} ${key}: 5 bench`);
        assert.deepStrictEqual(lv.empty, {}, `${team.name} ${key}: no empty slot`);
        assert.ok(lv.counts.QB === 1 && lv.counts.TE >= 1 && lv.counts.RB >= 2 && lv.counts.WR >= 3, `${team.name} ${key}: starters by position ${JSON.stringify(lv.counts)}`);
        assert.strictEqual(lv.counts.RB + lv.counts.WR + lv.counts.TE, 7, `${team.name} ${key}: one FLEX`);
        assert.ok(lv.starterValue > 0 && lv.benchValue > 0, `${team.name} ${key}: nonzero values`);
      });
      assert.strictEqual(team.entries.filter(e => F.isNotEvaluated(e)).length, 2, `${team.name}: K and DEF not evaluated`);
    });
  });

  t("test_jsn_discoverable_in_the_uncapped_search", async () => {
    const result = await searchOnce();
    assert.ok(result.rows.length > 0, "the league search found candidates");
    assert.strictEqual(result.perOpponent.length, 11, "every opponent searched");
    result.perOpponent.forEach(p => {
      const theirs = teamOf(p.id).entries.map(e => rowsByKey.get(String(e.key))).filter(Boolean);
      const mineRows = mine.entries.map(e => rowsByKey.get(String(e.key))).filter(Boolean);
      const direct = F.findTrades(mineRows, theirs, {chartKeys: CH, maxSize: 2, limit: Infinity,
        sanity: {shape, mine: mineRows, theirs, keepMine: true, keepTheirs: true}});
      assert.strictEqual(p.count, direct.total, `vs ${p.name}: every qualified candidate kept (${p.count} of ${direct.total}), none truncated`);
    });
    const jsn = result.rows.filter(r => gives(r, JSN));
    facts.candidates = result.rows.length;
    facts.jsnCandidates = jsn.length;
    facts.jsnOpponents = [...new Set(jsn.map(r => r.opponent))].length;
    assert.ok(jsn.length > 0, `JSN is not discoverable: 0 of ${result.rows.length} candidates send him`);
  });

  t("test_selected_candidates_are_exact", async () => {
    const {equal, unequal, explicit} = await pickOnce();
    assert.ok(equal, "a trade sending JSN with no throw-in exists");
    assert.ok(unequal, "a candidate whose core was unequal (a throw-in evens it) exists");
    assert.ok(explicit && explicit.give.length !== explicit.receive.length && explicit.give.length + explicit.receive.length >= 3,
      `the explicit deal without the throw-in is unequal: ${explicit && explicit.give.length}-for-${explicit && explicit.receive.length}`);
    [equal, unequal].forEach(r => {
      const [opp, give, get] = r.id.split("|");
      assert.strictEqual(opp, r.opponentId);
      assert.deepStrictEqual(give.split(","), keysOf(r.give), "row id names the exact give keys");
      assert.deepStrictEqual(get.split(","), keysOf(r.receive), "row id names the exact get keys");
      const own = new Set(mine.entries.map(e => e.key)), their = new Set(teamOf(r.opponentId).entries.map(e => e.key));
      assert.ok(keysOf(r.give).every(k => own.has(k)) && keysOf(r.receive).every(k => their.has(k)), "package comes off the two rosters");
    });
    facts.equal = {id: equal.id, opponent: equal.opponent};
    facts.unequal = {id: unequal.id, opponent: unequal.opponent, throwIns: unequal.addedThrowIns.map(a => `${a.side}:${a.row.player_key}`),
      explicit: [explicit.give.length, explicit.receive.length]};
  });

  t("test_league_row_gains_match_the_lineup_math", async () => {
    const {equal, unequal} = await pickOnce();
    [equal, unequal].forEach(r => {
      const e = envelope(F, env, {mine, theirs: teamOf(r.opponentId)}, keysOf(r.give), keysOf(r.receive));
      assert.ok(Math.abs(e.gains.us.ddf - r.fit.us.starterDelta) < 1e-9, `${r.id}: league row's starter gain ${r.fit.us.starterDelta} equals the lineup math ${e.gains.us.ddf}`);
      const sum = (keys, v) => keys.reduce((s, k) => s + e.values[k][v], 0);
      assert.ok(Math.abs(sum(e.get, "ddf") - sum(e.give, "ddf") - r.edge) < 1e-9, `${r.id}: DDF capture is get minus give`);
      assert.ok(Math.abs(sum(e.give, "market") - sum(e.get, "market") - r.chartEdge) < 1e-9, `${r.id}: market edge is give minus get`);
      assert.ok(Math.abs(sum(e.get, "proj") - sum(e.give, "proj") - r.projEdge) < 1e-9, `${r.id}: projections edge is get minus give`);
    });
  });

  // Compare: the site's DDF state link (view compare, the package, both rosters, the league, the sources).
  const compareLink = (r, theirs) => S.encodeQuery({league: settings, sources: CH,
    work: {view: "compare", give: keysOf(r.give).map(key => ({key})), get: keysOf(r.receive).map(key => ({key})),
      mine: mine.entries.map(e => ({key: e.key, name: e.name})), theirs: theirs.entries.map(e => ({key: e.key, name: e.name}))}});
  const arrive = query => {
    const {state} = S.decodeQuery(query);
    assert.ok(state && state.work, `the link carried no work: ${query.slice(0, 120)}`);
    // A name-only entry (the codec keeps K and DEF by name) arrives unresolved: counted, never valued.
    const entry = p => (p.key !== undefined ? {key: p.key, name: p.name} : {key: `n:${p.name}`, name: p.name});
    const side = (list, id) => ({id, entries: (list || []).map(entry)});
    const l = state.league || {};
    const shapeIn = l.roster ? {QB: l.roster.QB, RB: l.roster.RB, WR: l.roster.WR, TE: l.roster.TE, FLEX: l.roster.FLEX, SUPERFLEX: l.roster.SUPERFLEX} : null;
    return {state, ctx: {settings: state.league ? {scoring: l.scoring, teams: l.teams, roster: l.roster} : null, basis: "default", level: null,
      charts: state.sources || [], market: state.sources || null, shape: shapeIn, rowsByKey},
      mine: side(state.work.mine, mine.id), theirsEntries: state.work.theirs, give: (state.work.give || []).map(p => p.key), get: (state.work.get || []).map(p => p.key)};
  };
  t("test_compare_link_keeps_the_trade_context", async () => {
    const {equal, unequal, explicit} = await pickOnce();
    const problems = [];
    [["equal", equal], ["throw-in", unequal], ["unequal", explicit]].forEach(([label, r]) => {
      const theirs = teamOf(r.opponentId);
      const origin = envelope(F, env, {mine, theirs}, keysOf(r.give), keysOf(r.receive));
      const a = arrive(compareLink(r, theirs));
      const theirsArrived = a.theirsEntries ? {id: theirs.id, entries: a.theirsEntries.map(p => (p.key !== undefined ? {key: p.key} : {key: `n:${p.name}`, name: p.name}))} : null;
      const dest = theirsArrived ? envelope(F, a.ctx.shape ? a.ctx : {...a.ctx, shape: null}, {mine: a.mine, theirs: theirsArrived}, a.give, a.get)
        : {...envelope(F, a.ctx, {mine: a.mine, theirs: {id: null, entries: []}}, a.give, a.get), theirs: null};
      diff(origin, dest).forEach(d => problems.push(`${label} ${r.id}: [${d.code}] ${d.message}`));
    });
    assert.deepStrictEqual(problems, [], problems.join("\n"));
  });

  // Pair finder: its own link carries both rosters; its search must rediscover the exact package with the same numbers.
  t("test_pair_link_rediscovers_the_exact_package", async () => {
    const {equal, unequal} = await pickOnce();
    const problems = [];
    [["equal", equal], ["throw-in", unequal]].forEach(([label, r]) => {
      const theirs = teamOf(r.opponentId);
      const skill = team => team.entries.filter(e => !F.isNotEvaluated(e)).map(e => ({key: e.key}));
      const hash = F.encodeFinderHash({mine: skill(mine), theirs: skill(theirs), maxSize: 2, keepMine: true, keepTheirs: true},
        S.encodeQuery({league: settings}));
      const got = F.decodeFinderHash(hash, [...rowsByKey.keys()]);
      const side = list => (list || []).map(x => rowsByKey.get(String(x.key || x))).filter(Boolean);
      const mineRows = side(got.mine), theirRows = side(got.theirs);
      if (mineRows.length !== skill(mine).length || theirRows.length !== skill(theirs).length) {
        problems.push(`${label} ${r.id}: [team-substituted] pair link carried ${mineRows.length}/${skill(mine).length} and ${theirRows.length}/${skill(theirs).length} roster players`);
        return;
      }
      const res = F.findTrades(mineRows, theirRows, {chartKeys: CH, maxSize: got.size, limit: Infinity,
        sanity: {shape, mine: mineRows, theirs: theirRows, keepMine: got.keepMine, keepTheirs: got.keepTheirs}});
      const id = `${keysOf(r.give)}|${keysOf(r.receive)}`;
      const found = res.trades.find(x => `${keysOf(x.give)}|${keysOf(x.receive)}` === id);
      if (!found) { problems.push(`${label} ${r.id}: [package-changed] the pair finder's search does not contain this package (${res.total} trades)`); return; }
      if (Math.abs(found.edge - r.edge) > 1e-9) problems.push(`${label} ${r.id}: [gains-changed] pair finder capture ${found.edge} vs league ${r.edge}`);
      const origin = envelope(F, env, {mine, theirs}, keysOf(r.give), keysOf(r.receive));
      const dest = envelope(F, env, {mine: {id: mine.id, entries: got.mine.map(x => ({key: String(x.key || x)})).concat(mine.entries.filter(e => F.isNotEvaluated(e)))},
        theirs: {id: theirs.id, entries: got.theirs.map(x => ({key: String(x.key || x)})).concat(theirs.entries.filter(e => F.isNotEvaluated(e)))}}, keysOf(found.give), keysOf(found.receive));
      diff(origin, dest).forEach(d => problems.push(`${label} ${r.id}: [${d.code}] ${d.message}`));
    });
    assert.deepStrictEqual(problems, [], problems.join("\n"));
  });

  t("test_unavailable_stays_unavailable", async () => {
    const {equal} = await pickOnce();
    const hole = keysOf(equal.receive)[0];
    const holed = {...env, rowsByKey: modeledRows(players, {[hole]: ["fantasypros"]})};
    const theirs = teamOf(equal.opponentId);
    const origin = envelope(F, holed, {mine, theirs}, keysOf(equal.give), keysOf(equal.receive));
    assert.strictEqual(origin.values[hole].market, null, "a player one chart does not price has no Trade chart average");
    assert.ok(origin.values[hole].ddf !== null, "but keeps his DDF Value");
    const zero = JSON.parse(JSON.stringify(origin));
    zero.values[hole].market = 0;
    assert.deepStrictEqual(diff(origin, zero).map(d => d.code), ["value-filled"], "0 in place of unavailable is caught");
    assert.deepStrictEqual(diff(origin, JSON.parse(JSON.stringify(origin))), [], "unavailable on both sides is the same context");
  });

  t("test_diff_names_each_loss", async () => {
    const {explicit} = await pickOnce();
    const theirs = teamOf(explicit.opponentId);
    const base = envelope(F, env, {mine, theirs}, keysOf(explicit.give), keysOf(explicit.receive));
    const other = opps.find(o => o.id !== theirs.id);
    const clone = () => JSON.parse(JSON.stringify(base));
    const cases = [
      ["basis-changed", e => { e.basis = null; }],
      ["level-changed", e => { e.level = "market"; }],
      ["settings-changed", e => { e.settings = {...e.settings, scoring: "ppr"}; }],
      ["sources-changed", e => { e.sources.market = null; }],
      ["team-substituted", e => { e.theirs = {id: other.id, keys: other.entries.filter(x => !F.isNotEvaluated(x)).map(x => x.key).sort(), notEvaluated: 2}; }],
      ["package-changed", e => { const long = e.give.length > e.get.length ? "give" : "get"; e[long] = e[long].slice(1); }],
      ["value-changed", e => { const k = e.get[0]; e.values[k].ddf += 1; }],
      ["value-lost", e => { const k = e.give[0]; e.values[k].proj = null; }],
      ["gains-missing", e => { delete e.gains.them; }],
      ["gains-changed", e => { e.gains.us.ddf += 0.5; }],
    ];
    assert.deepStrictEqual(diff(base, clone()), []);
    cases.forEach(([code, mutate]) => {
      const e = clone();
      mutate(e);
      const codes = [...new Set(diff(base, e).map(d => d.code))];
      assert.deepStrictEqual(codes, [code], `${code}: diff reported ${JSON.stringify(codes)}`);
    });
  });

  return (async () => {
    for (const {name, fn} of queue) {
      try { await fn(); } catch (error) { failures.push({name, message: String(error && error.message || error)}); }
    }
    return {ran, failures, facts};
  })();
}

if (require.main === module) {
  const [mode, a, b, tol] = process.argv.slice(2);
  if (mode === "diff") {
    const read = p => JSON.parse(fs.readFileSync(p, "utf8"));
    process.stdout.write(JSON.stringify({differences: diff(read(a), read(b), tol === undefined ? 0.051 : Number(tol))}) + "\n");
  } else if (mode === "check") {
    run(path.resolve(a), path.resolve(b)).then(out => process.stdout.write(JSON.stringify(out) + "\n"),
      error => { process.stdout.write(JSON.stringify({ran: [], failures: [{name: "harness", message: String(error && error.stack || error)}]}) + "\n"); });
  } else {
    process.stderr.write("usage: uso_site_journey_contract.cjs check <app dir> <league.json> | diff <origin.json> <destination.json> [tolerance]\n");
    process.exit(2);
  }
}
module.exports = {envelope, diff, modeledRows, run};
