// Trade Value v2 — Find a trade (JEG-481: first slice, then league import and roster sanity).
//
// You type in your roster and a rival's. The search lists packages (1-for-1 up to N-for-N)
// where the published trade charts say the rival breaks even or wins, and DDF Value says you win.
//
// No value math of its own: every number is an engine row value (TradeValueCurveControls
// .getAllRows()); the search only adds and compares them, as Compare a trade does. A missing
// value stays missing, never 0.
//
// Decisions (Jeremy, 2026-10-09 / 2026-10-10, recorded on JEG-481):
//   * rosters are typed in with player search; the second slice (2026-10-16) adds import from a Sleeper league,
//     a public ESPN league, or pasted names. Direct fetches need no key and no account; a private league is
//     refused by the host, and the card says to paste the roster instead;
//   * default 1-for-1 up to 2-for-2, a toggle raises the maximum players per side;
//   * "fair to the rival" = at least 3 of the 4 trade charts say the rival breaks even or wins;
//   * ranking prefers simpler trades.
// Defaults chosen here, listed in docs/math-review-agenda.md: the simplicity weight (EXTRA_PLAYER_WEIGHT)
// and the cap on subsets searched per side (MAX_SUBSETS).
(function (root) {
  "use strict";

  const OUR_KEY = "ddf_value";
  const CHART_KEYS = ["usatoday", "fantasycalc", "fantasypros", "cbs"];
  const MIN_CHARTS = 3;
  const MAX_SIZE_CHOICES = [2, 3, 4];
  const MAX_SUBSETS = 6000;          // per side; larger rosters search the top players by DDF Value
  const EXTRA_PLAYER_WEIGHT = 0.1;   // each player beyond a 1-for-1 takes 10% off the ranking score
  const LIMIT = 10;
  const finite = value => typeof value === "number" && Number.isFinite(value);
  const pointsAsShown = net => (Math.abs(net) < 0.05 ? 0 : net);   // 0.0 as shown points neither way

  // Every subset of 1..maxSize items, as arrays of indices.
  function subsets(count, maxSize) {
    const out = [];
    const walk = (start, picked) => {
      if (picked.length) out.push(picked.slice());
      if (picked.length === maxSize) return;
      for (let i = start; i < count; i++) { picked.push(i); walk(i + 1, picked); picked.pop(); }
    };
    walk(0, []);
    return out;
  }
  const choose = (n, k) => { let r = 1; for (let i = 1; i <= k; i++) r = r * (n - k + i) / i; return Math.round(r); };
  const subsetCount = (n, maxSize) => { let total = 0; for (let k = 1; k <= Math.min(n, maxSize); k++) total += choose(n, k); return total; };

  // The most players to search on one side so the subsets stay under the cap: the top by DDF Value.
  function pool(rows, ourKey, maxSize) {
    const priced = rows.filter(row => row.values && finite(row.values[ourKey]))
      .sort((a, b) => b.values[ourKey] - a.values[ourKey] || String(a.player_key).localeCompare(String(b.player_key)));
    let n = priced.length;
    while (n > maxSize && subsetCount(n, maxSize) > MAX_SUBSETS) n -= 1;
    return {rows: priced.slice(0, n), unpriced: rows.length - priced.length, searched: n, of: priced.length};
  }

  // ---------- judging one package (JEG-972): the single place a trade is checked ----------
  // Sums of a package in each series ([ourKey, ...charts]); null when any player lacks that series.
  function sumsOf(rows, keys) {
    return keys.map(key => {
      let total = 0;
      for (const row of rows) { const v = row.values && row.values[key]; if (!finite(v)) return null; total += v; }
      return total;
    });
  }
  // give / get: sums arrays. The edge is get - give for you; the rival is happy on a chart when its net is <= 0 as shown.
  // A chart that does not price every player in the package is left out of the count (net null).
  function judgeSums(give, get, chartKeys, minCharts) {
    const edge = give[0] === null || get[0] === null ? null : get[0] - give[0];
    let priced = 0;
    let ok = 0;
    const charts = [];
    for (let c = 0; c < chartKeys.length; c++) {
      const g = give[c + 1];
      const r = get[c + 1];
      if (g === null || r === null) { charts.push({key: chartKeys[c], net: null, rivalOk: null}); continue; }
      const net = r - g;
      const rivalOk = pointsAsShown(net) <= 0;
      priced += 1;
      if (rivalOk) ok += 1;
      charts.push({key: chartKeys[c], net, rivalOk});
    }
    return {edge, charts, pricedCharts: priced, rivalOkCount: ok,
      passes: {edge: edge !== null && pointsAsShown(edge) > 0, charts: priced >= minCharts && ok >= minCharts}};
  }
  // Roster sanity for a package: {mine, theirs} issue lists, and whether the keep-lineup boxes reject it.
  function judgeLineup(giveRows, getRows, sanity) {
    if (!sanity) return {issues: null, passes: true};
    const issues = {mine: lineupIssues(sanity.mineCounts, giveRows, getRows, sanity.shape),
      theirs: lineupIssues(sanity.theirCounts, getRows, giveRows, sanity.shape)};
    return {issues, passes: !((sanity.keepMine && issues.mine.length) || (sanity.keepTheirs && issues.theirs.length))};
  }
  const scoreOf = (edge, players) => edge * (1 - EXTRA_PLAYER_WEIGHT * (players - 2));
  // Any package, judged exactly as the search judges it. ctx comes from findTrades (result.ctx).
  function evaluateCombo(giveRows, receiveRows, ctx) {
    const keys = [ctx.ourKey].concat(ctx.chartKeys);
    const judged = judgeSums(sumsOf(giveRows, keys), sumsOf(receiveRows, keys), ctx.chartKeys, ctx.minCharts);
    const lineup = judgeLineup(giveRows, receiveRows, ctx.sanity);
    const edge = judged.edge;
    return {edge, charts: judged.charts, pricedCharts: judged.pricedCharts, rivalOkCount: judged.rivalOkCount, issues: lineup.issues,
      score: edge === null ? null : scoreOf(edge, giveRows.length + receiveRows.length),
      passes: {edge: judged.passes.edge, charts: judged.passes.charts, lineup: lineup.passes}};
  }

  // mine / theirs: engine rows. opts: {ourKey, chartKeys, maxSize, minCharts, limit}.
  // Each trade: {give, receive, edge, charts: [{key, net, rivalOk}], pricedCharts, rivalOkCount, score, throwIns}.
  // edge and net are receive - give for you; the rival is happy when a chart's net is <= 0 as shown.
  // Rows that differ only by a player worth 0.0 everywhere are one row (the simpler trade), see collapseThrowIns.
  function findTrades(mine, theirs, opts) {
    const o = opts || {};
    const ourKey = o.ourKey || OUR_KEY;
    const maxSize = Math.max(1, o.maxSize || 2);
    const chartKeys = (o.chartKeys || CHART_KEYS).slice();
    const minCharts = o.minCharts || Math.min(MIN_CHARTS, chartKeys.length);
    const limit = o.limit || LIMIT;
    // Optional roster sanity: {shape, mine, theirs (all the side's rows), keepMine, keepTheirs}.
    const sanity = o.sanity ? {...o.sanity, mineCounts: countByPos(o.sanity.mine || []), theirCounts: countByPos(o.sanity.theirs || [])} : null;
    let sanityDropped = 0;
    const mineP = pool(mine, ourKey, maxSize);
    const theirsP = pool(theirs, ourKey, maxSize);
    const keys = [ourKey].concat(chartKeys);
    const describe = (rows, combo) => ({combo, sums: sumsOf(combo.map(i => rows[i]), keys)});
    const mineSubs = subsets(mineP.rows.length, maxSize).map(c => describe(mineP.rows, c));
    const theirSubs = subsets(theirsP.rows.length, maxSize).map(c => describe(theirsP.rows, c))
      .sort((a, b) => a.sums[0] - b.sums[0]);
    const found = [];
    for (const give of mineSubs) {
      // DDF Value: you must win, so only their packages worth more than yours (sorted: binary search).
      let lo = 0; let hi = theirSubs.length;
      while (lo < hi) {
        const mid = (lo + hi) >> 1;
        if (pointsAsShown(theirSubs[mid].sums[0] - give.sums[0]) > 0) hi = mid; else lo = mid + 1;
      }
      for (let t = lo; t < theirSubs.length; t++) {
        const get = theirSubs[t];
        const judged = judgeSums(give.sums, get.sums, chartKeys, minCharts);
        if (!judged.passes.edge || !judged.passes.charts) continue;
        const giveRows = give.combo.map(i => mineP.rows[i]);
        const getRows = get.combo.map(i => theirsP.rows[i]);
        const lineup = judgeLineup(giveRows, getRows, sanity);
        if (!lineup.passes) { sanityDropped += 1; continue; }
        found.push({give: giveRows, receive: getRows, edge: judged.edge, charts: judged.charts, issues: lineup.issues,
          pricedCharts: judged.pricedCharts, rivalOkCount: judged.rivalOkCount, score: scoreOf(judged.edge, giveRows.length + getRows.length)});
      }
    }
    found.sort((a, b) => b.score - a.score || b.edge - a.edge
      || (a.give.length + a.receive.length) - (b.give.length + b.receive.length)
      || idOf(a).localeCompare(idOf(b)));
    const collapsed = collapseThrowIns(found, chartKeys, ourKey);
    return {trades: collapsed.slice(0, limit), total: collapsed.length, foldedThrowIns: found.length - collapsed.length, sanityDropped, ourKey, chartKeys, minCharts, maxSize,
      mine: mineP, theirs: theirsP, ctx: {ourKey, chartKeys, minCharts, sanity}};
  }
  const idOf = trade => `${trade.give.map(r => r.player_key)}|${trade.receive.map(r => r.player_key)}`;

  // ---------- JEG-972 / JEG-885: throw-ins and groups ----------
  // A throw-in is a player worth 0.0 as shown on DDF Value and on every compared chart.
  const isZeroValue = (row, keys) => keys.every(k => finite(row.values && row.values[k]) && Math.abs(row.values[k]) < 0.05);
  // Trades that differ only by throw-ins are one row: the one with the fewest players (ties: the better-ranked, as
  // given). The dropped players are named on it as throwIns {give, receive}. If the simpler trade is not in the list
  // (it failed a gate), the variant stays: a trade the search did not list is never invented.
  function collapseThrowIns(trades, chartKeys, ourKey) {
    const keys = [ourKey].concat(chartKeys);
    const canon = list => list.filter(r => !isZeroValue(r, keys)).map(r => String(r.player_key)).sort().join(",");
    const classes = new Map();
    trades.forEach(t => {
      const id = `${canon(t.give)}|${canon(t.receive)}`;
      if (!classes.has(id)) classes.set(id, []);
      classes.get(id).push(t);
    });
    const size = t => t.give.length + t.receive.length;
    const kept = new Map();
    classes.forEach(members => {
      let rep = members[0];
      for (const m of members) if (size(m) < size(rep)) rep = m;
      const extra = side => {
        const have = new Set(rep[side].map(r => String(r.player_key)));
        const out = new Map();
        members.forEach(m => m[side].forEach(r => { const k = String(r.player_key); if (!have.has(k) && isZeroValue(r, keys)) out.set(k, r); }));
        return [...out.values()];
      };
      const throwIns = {give: extra("give"), receive: extra("receive")};
      kept.set(rep, throwIns.give.length || throwIns.receive.length ? throwIns : null);
    });
    return trades.filter(t => kept.has(t)).map(t => (kept.get(t) ? {...t, throwIns: kept.get(t)} : t));
  }

  // The player with the highest DDF Value on a side; ties by lower player_key (the order pool() uses).
  function coreOf(rows, ourKey) {
    const sorted = rows.slice().sort((a, b) => b.values[ourKey] - a.values[ourKey] || String(a.player_key).localeCompare(String(b.player_key)));
    return sorted[0];
  }
  const HEAVY_SHARE = 0.5;   // a received player worth this share of the core, or more, is part of the group's identity
  const byValueDesc = ourKey => (a, b) => b.values[ourKey] - a.values[ourKey] || String(a.player_key).localeCompare(String(b.player_key));
  // Groups by the player you receive (Jeremy 2026-10-23). opts: {ourKey}. trades: findTrades output, ranked.
  // Group: {key, core, heavy (core first among the received players worth >= 50% of it), giveCandidates, receiveSide
  // (smaller received players seen in the group, selectable), trades, best (top score), bestEdge}.
  function groupTrades(trades, opts) {
    const ourKey = (opts && opts.ourKey) || OUR_KEY;
    const order = byValueDesc(ourKey);
    const map = new Map();
    trades.forEach(t => {
      const core = coreOf(t.receive, ourKey);
      const heavy = t.receive.filter(r => r === core || r.values[ourKey] >= HEAVY_SHARE * core.values[ourKey]).sort(order);
      const key = heavy.map(r => String(r.player_key)).join(",");
      if (!map.has(key)) map.set(key, {key, core, heavy, trades: []});
      map.get(key).trades.push(t);
    });
    const groups = [...map.values()].map(g => {
      const pick = (list, skip) => {
        const seen = new Map();
        list.forEach(r => { if (!skip.has(String(r.player_key))) seen.set(String(r.player_key), r); });
        return [...seen.values()].sort(order);
      };
      const heavyKeys = new Set(g.heavy.map(r => String(r.player_key)));
      const best = g.trades.slice().sort((a, b) => b.score - a.score || b.edge - a.edge || idOf(a).localeCompare(idOf(b)))[0];
      return {...g, best, bestEdge: best.edge,
        giveCandidates: pick([].concat(...g.trades.map(t => t.give)), new Set()),
        receiveSide: pick([].concat(...g.trades.map(t => t.receive)), heavyKeys)};
    });
    groups.sort((a, b) => b.bestEdge - a.bestEdge || b.best.score - a.best.score || a.key.localeCompare(b.key));
    return groups;
  }

  // ---------- roster sanity (JEG-481, second slice) ----------
  // Slots that need a named position. FLEX and SUPERFLEX are not counted, so the check is conservative toward the
  // positions a lineup cannot do without. A side is "thin" at a position when the trade leaves it with fewer players
  // there than the league starts (and fewer than it had), or fewer DDF starter-tier players than it had, short of
  // the slots (ddfTier is the engine's own tier, read, not recomputed).
  const SLOT_POSITIONS = ["QB", "RB", "WR", "TE"];
  const countByPos = rows => {
    const out = {};
    SLOT_POSITIONS.forEach(pos => { out[pos] = {all: 0, starter: 0}; });
    rows.forEach(row => {
      const bucket = out[row.pos];
      if (!bucket) return;
      bucket.all += 1;
      if (row.ddfTier === "starter") bucket.starter += 1;
    });
    return out;
  };
  // roster: the side's engine rows; leaving / arriving: the rows moving out of / into it; shape: the league's slots.
  function lineupIssues(roster, leaving, arriving, shape) {
    const before = Array.isArray(roster) ? countByPos(roster) : roster;
    const gone = countByPos(leaving);
    const came = countByPos(arriving);
    const issues = [];
    SLOT_POSITIONS.forEach(pos => {
      const need = (shape && shape[pos]) || 0;
      if (!need) return;
      const all = before[pos].all - gone[pos].all + came[pos].all;
      const starters = before[pos].starter - gone[pos].starter + came[pos].starter;
      if (all < need && all < before[pos].all) issues.push({pos, have: all, need, kind: "count"});
      else if (starters < Math.min(before[pos].starter, need)) issues.push({pos, have: starters, need, kind: "starter"});
    });
    return issues;
  }
  const issueText = issue => (issue.kind === "count"
    ? `${issue.have} ${issue.pos} left for ${issue.need} starting slot${issue.need === 1 ? "" : "s"}`
    : `${issue.have} ${issue.pos} starter${issue.have === 1 ? "" : "s"} left for ${issue.need} slot${issue.need === 1 ? "" : "s"}`);

  // The roster as typed in, before any search: positions the league starts that the roster does not have at all.
  function rosterGaps(rows, shape) {
    const counts = countByPos(rows);
    return SLOT_POSITIONS.filter(pos => shape && shape[pos] && counts[pos].all < shape[pos])
      .map(pos => ({pos, have: counts[pos].all, need: shape[pos]}));
  }

  // ---------- league import (JEG-481, second slice) ----------
  // Rosters come from a public league (Sleeper or ESPN) or pasted names; they become the same typed-in lists the
  // search card already uses. Names are matched to the engine's own rows, never invented.
  const SUFFIX = /\b(jr|sr|ii|iii|iv|v)\b\.?$/;
  const normName = name => String(name || "").toLowerCase().replace(/[.'’`]/g, "").replace(/[^a-z0-9 ]+/g, " ")
    .replace(/\s+/g, " ").trim().replace(SUFFIX, "").trim();
  // entries: [{name, pos}]; rows: engine rows. A name shared by two players is told apart by position, else left
  // unmatched (never guessed).
  function matchNames(entries, rows) {
    const byName = new Map();
    rows.forEach(row => {
      if (!row.name) return;
      const key = normName(row.name);
      if (!byName.has(key)) byName.set(key, []);
      byName.get(key).push(row);
    });
    const matched = [];
    const unmatched = [];
    const seen = new Set();
    entries.forEach(entry => {
      let hits = byName.get(normName(entry.name)) || [];
      if (hits.length > 1 && entry.pos) hits = hits.filter(row => row.pos === entry.pos);
      if (hits.length !== 1) { unmatched.push({...entry, reason: hits.length ? "more than one player has this name" : "not in the values"}); return; }
      const key = String(hits[0].player_key);
      if (seen.has(key)) return;
      seen.add(key);
      matched.push(hits[0]);
    });
    return {matched, unmatched};
  }
  const SLEEPER_POS = {DEF: "DEF"};
  // Sleeper: league rosters + league users + the player directory. Returns [{id, label, entries}].
  function parseSleeper(rosters, users, directory) {
    const owners = new Map((users || []).map(u => [String(u.user_id), (u.metadata && u.metadata.team_name) || u.display_name || u.username]));
    return (rosters || []).map(r => ({
      id: String(r.roster_id),
      label: owners.get(String(r.owner_id)) || `Team ${r.roster_id}`,
      entries: (r.players || []).map(id => {
        const p = (directory || {})[id];
        if (!p) return null;
        const name = p.full_name || [p.first_name, p.last_name].filter(Boolean).join(" ");
        return name ? {name, pos: SLEEPER_POS[p.position] || p.position || ""} : null;
      }).filter(Boolean)
    }));
  }
  const ESPN_POS = {1: "QB", 2: "RB", 3: "WR", 4: "TE", 5: "K", 16: "DEF"};
  // ESPN (public league, view=mRoster&view=mTeam). Returns [{id, label, entries}].
  function parseEspn(json) {
    return ((json && json.teams) || []).map(team => ({
      id: String(team.id),
      label: team.name || [team.location, team.nickname].filter(Boolean).join(" ") || `Team ${team.id}`,
      entries: (((team.roster || {}).entries) || []).map(entry => {
        const player = (entry.playerPoolEntry || {}).player || {};
        return player.fullName ? {name: player.fullName, pos: ESPN_POS[player.defaultPositionId] || ""} : null;
      }).filter(Boolean)
    }));
  }
  // Pasted names: one per line or comma-separated; a trailing "(QB - TEN)" style note is dropped.
  function parsePasted(text) {
    return String(text || "").split(/[\n,;]+/).map(s => s.replace(/\(.*?\)/g, "").replace(/\s+-\s+.*$/, "").trim())
      .filter(Boolean).map(name => ({name, pos: ""}));
  }

  const api = {findTrades, evaluateCombo, collapseThrowIns, groupTrades, coreOf, lineupIssues, issueText, rosterGaps, matchNames, normName, parseSleeper, parseEspn, parsePasted, subsets, subsetCount, OUR_KEY, CHART_KEYS, MIN_CHARTS, MAX_SIZE_CHOICES, MAX_SUBSETS, EXTRA_PLAYER_WEIGHT, LIMIT};
  if (typeof module !== "undefined" && module.exports) { module.exports = api; return; }
  root.TradeValueFinder = api;

  // ---------- page (browser only) ----------
  const CHART_NAMES = {usatoday: "USA Today", fantasycalc: "FantasyCalc", fantasypros: "FantasyPros", cbs: "CBS Sports"};
  const $ = id => document.getElementById(id);
  const engine = () => root.TradeValueCurveControls;
  // mine / theirs: [{key, name, pos}]; sel: keys ticked for "Move selected"; undo: the rosters before the last swap or move (JEG-854).
  const S = {mine: [], theirs: [], maxSize: 2, keepMine: true, keepTheirs: true, sel: new Set(), undo: null, label: {mine: "", theirs: ""}};
  const renders = {};

  function el(tag, props, ...kids) {
    const node = document.createElement(tag);
    Object.entries(props || {}).forEach(([k, v]) => { if (k === "text") node.textContent = v; else node.setAttribute(k, v); });
    node.append(...kids.filter(Boolean));
    return node;
  }
  const clearOutput = () => { const out = $("v2FindOut"); out.hidden = true; out.replaceChildren(); };

  // JEG-854: fixing which team is which must be one tap. Swap and Move change the rosters wholesale, so the shown
  // results are recomputed from the new rosters (never left standing from the old assignment); Undo restores the last one.
  function arrangeSay(text) { const p = $("v2FindArrangeNote"); if (p) p.textContent = text; }
  function updateArrange() {
    const undo = $("v2FindUndo");
    if (undo) undo.disabled = !S.undo;
    ["mine", "theirs"].forEach(side => {
      const button = $(`v2Find${side[0].toUpperCase()}${side.slice(1)}MoveSel`);
      if (!button) return;
      const n = S[side].filter(p => S.sel.has(p.key)).length;
      button.disabled = !n;
      button.textContent = n ? `Move ${n} selected to the other team` : "Move selected to the other team";
    });
  }
  function renderBoth() { renders.mine && renders.mine(); renders.theirs && renders.theirs(); updateArrange(); }
  function rerun() {
    const out = $("v2FindOut");
    const had = out && !out.hidden && out.childElementCount > 0;
    clearOutput();
    if (had) run();
  }
  function snapshot() { S.undo = {mine: S.mine.slice(), theirs: S.theirs.slice()}; }
  function afterArrange(text) { S.sel.clear(); renderBoth(); rerun(); arrangeSay(text); }
  function swapTeams() {
    snapshot();
    [S.mine, S.theirs] = [S.theirs, S.mine];
    [S.label.mine, S.label.theirs] = [S.label.theirs, S.label.mine];
    afterArrange("Swapped: your roster is now the one that was theirs. Undo puts them back.");
  }
  function moveKeys(keys) {
    const set = new Set(keys);
    const going = S.mine.concat(S.theirs).filter(p => set.has(p.key));
    if (!going.length) return;
    snapshot();
    const toTheirs = S.mine.filter(p => set.has(p.key));
    const toMine = S.theirs.filter(p => set.has(p.key));
    S.mine = S.mine.filter(p => !set.has(p.key)).concat(toMine);
    S.theirs = S.theirs.filter(p => !set.has(p.key)).concat(toTheirs);
    afterArrange(`Moved ${going.map(p => p.name).join(", ")} to the other team. Undo puts them back.`);
  }
  function undoArrange() {
    if (!S.undo) return;
    S.mine = S.undo.mine;
    S.theirs = S.undo.theirs;
    S.undo = null;
    afterArrange("Undone.");
  }

  // Public league endpoints. Both answer cross-origin requests; a private ESPN league answers 401/403.
  let sleeperDirectory = null;
  async function getJson(url, what) {
    let response;
    try { response = await root.fetch(url); } catch (error) { throw new Error(`Could not reach ${what}.`); }
    if (response.status === 401 || response.status === 403) throw new Error(`${what} says that league is private.`);
    if (response.status === 404) throw new Error(`${what} has no league with that ID.`);
    if (!response.ok) throw new Error(`${what} answered with an error (${response.status}).`);
    return response.json();
  }
  async function loadSleeper(leagueId) {
    const base = "https://api.sleeper.app/v1";
    const [rosters, users] = await Promise.all([getJson(`${base}/league/${leagueId}/rosters`, "Sleeper"), getJson(`${base}/league/${leagueId}/users`, "Sleeper")]);
    if (!sleeperDirectory) sleeperDirectory = await getJson(`${base}/players/nfl`, "Sleeper");
    return parseSleeper(rosters, users, sleeperDirectory);
  }
  async function loadEspn(leagueId) {
    const now = new Date();
    const season = now.getMonth() < 2 ? now.getFullYear() - 1 : now.getFullYear();
    const json = await getJson(`https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/${season}/segments/0/leagues/${leagueId}?view=mRoster&view=mTeam`, "ESPN");
    return parseEspn(json);
  }

  // ---------- JEG-853: a whole page pasted in (Jeremy, 2026-10-22: "control all, copy the whole page, drop the text in") ----------
  // roster-paste.js reads the page deterministically in the browser (no LLM, no network) against the engine's own rows.
  // A sure match (confidence 1: name, team and position agree) goes on the roster; a lesser one (nickname or
  // "D. Henry" form) waits for a tap; an unmatched line gets a one-tap search. Too few matches adds nothing unless asked.
  // A matchup page carries two teams: the user taps which is theirs; Swap teams (JEG-854) fixes a wrong pick.
  const MIN_MATCHED = 3;
  const MIN_SHARE = 0.5;
  const SIDE_NAME = {mine: "Your roster", theirs: "Their roster"};
  const otherSide = side => (side === "mine" ? "theirs" : "mine");
  const sideId = side => `v2Find${side[0].toUpperCase()}${side.slice(1)}`;
  const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;
  // The page's slot label as a word: ESPN "Bench"/"IR", Yahoo "BN"/"IR", the ESPN matchup's injured and bye lists;
  // anything else (QB, FLEX, W/R/T, or no slot column at all, as on a matchup page) is a starter.
  function slotWord(slot) {
    const s = String(slot || "").toUpperCase();
    if (s === "BN" || s === "BENCH") return "Bench";
    if (s === "IR") return "IR";
    if (s === "INJURED") return "Injured";
    if (s === "BYE") return "Bye";
    return "Starter";
  }
  const siteWord = site => (site === "espn" ? " on the ESPN page" : site === "yahoo" ? " on the Yahoo page" : "");
  const rowMap = () => new Map((engine() ? engine().getAllRows() : []).map(r => [String(r.player_key), r]));
  const parsePage = text => (root.DDFRosterPaste && engine() ? root.DDFRosterPaste.parse(text, engine().getAllRows()) : null);
  // A pasted line as a search query: Yahoo's glued "Player Note", ESPN's "D/ST", a bye line's "PIT, K".
  const cleanLine = line => (root.DDFRosterPaste ? root.DDFRosterPaste.cleanYahooName(String(line || "")) : String(line || ""))
    .replace(/\s+[A-Z]{2,4},\s*(QB|RB|WR|TE|K|DEF|D\/ST)$/, "").replace(/\s*D\/?ST$/i, "").trim();

  // Parser players onto a side. Sure ones are added now (a player already on the other roster is left there and
  // named); unsure ones are returned for a tap. replace: the side starts empty (a whole team page is the whole team).
  function placePlayers(side, players, replace) {
    const map = rowMap();
    const other = new Set(S[otherSide(side)].map(p => p.key));
    const keep = replace ? [] : S[side].slice();
    const have = new Set(keep.map(p => p.key));
    const added = [];
    const onOther = [];
    const unsure = [];
    players.forEach(p => {
      const row = map.get(String(p.id));
      if (!row) return;
      const key = String(row.player_key);
      if (!(p.confidence >= 1)) { unsure.push({...p, row}); return; }
      if (other.has(key)) { onOther.push(row.name); return; }
      if (have.has(key)) return;
      have.add(key);
      added.push({key, name: row.name, pos: row.pos, team: row.team, slot: p.slot});
    });
    S[side] = keep.concat(added);
    return {added, onOther, unsure};
  }
  function addOne(side, row) {
    const key = String(row.player_key);
    if (S.mine.concat(S.theirs).some(p => p.key === key)) return false;
    S[side].push({key, name: row.name, pos: row.pos});
    renderBoth();
    clearOutput();
    return true;
  }
  // One tap from an unmatched line to the side's own name search (JEG-861 matcher), query filled in and open.
  function searchFor(side, line) {
    const input = $(`${sideId(side)}Search`);
    if (!input) return;
    input.value = cleanLine(line);
    input.dispatchEvent(new Event("input", {bubbles: true}));
    input.focus();
    if (input.scrollIntoView) input.scrollIntoView({block: "center"});
  }
  const put = (box, ...kids) => box.append(...kids.filter(Boolean));
  const slotChip = slot => el("span", {class: "v2-find-slot", "data-slot": slotWord(slot), text: slotWord(slot)});
  const matchedList = added => el("ul", {class: "v2-find-matched"}, ...added.map(p =>
    el("li", {}, el("b", {text: p.name}), el("span", {class: "v2-meta", text: ` ${p.pos || ""} ${p.team || ""}`.trimEnd()}), slotChip(p.slot))));
  function unsureItem(side, p) {
    const li = el("li", {class: "v2-find-unsure"});
    const yes = el("button", {type: "button", class: "v2-btn v2-find-confirm", text: "Yes, add", "aria-label": `Yes, add ${p.row.name}`});
    const no = el("button", {type: "button", class: "v2-btn v2-find-search-add", text: "No, search", "aria-label": `No, search for ${cleanLine(p.sourceLine)}`});
    li.append(el("span", {text: `Pasted “${cleanLine(p.sourceLine)}”: is this `}), el("b", {text: p.row.name}),
      el("span", {class: "v2-meta", text: ` ${p.row.pos || ""} ${p.row.team || ""}`.trimEnd()}), el("span", {text: "?"}), yes, no);
    yes.addEventListener("click", () => { const ok = addOne(side, p.row); li.replaceChildren(el("span", {text: ok ? `Added ${p.row.name}.` : `${p.row.name} is already on a roster.`})); });
    no.addEventListener("click", () => { li.remove(); searchFor(side, p.sourceLine); });
    return li;
  }
  const unsureBlock = (side, unsure) => (unsure.length ? [
    el("p", {class: "v2-find-paste-note", text: `Check ${plural(unsure.length, "match")}: not added until you say so.`}),
    el("ul", {class: "v2-find-unsure-list"}, ...unsure.map(p => unsureItem(side, p)))] : []);
  const unmatchedBlock = (side, unmatched) => (unmatched.length ? [
    el("p", {class: "v2-find-paste-note", text: `Not matched (${unmatched.length}): add them by search.`}),
    el("ul", {class: "v2-find-unmatched"}, ...unmatched.map(u => {
      const search = el("button", {type: "button", class: "v2-btn v2-find-search-add", text: "Search to add", "aria-label": `Search to add ${cleanLine(u.line)}`});
      search.addEventListener("click", () => searchFor(side, u.line));
      return el("li", {}, el("span", {text: cleanLine(u.line)}), el("span", {class: "v2-meta", text: ` (${u.reason})`}), search);
    }))] : []);
  const benchNote = res => (res.benchIncluded === false
    ? el("p", {class: "v2-find-paste-note v2-find-bench-note", text: "Bench players are not on this page: expand Show Bench / Show Bench Players on the matchup page and copy again, or paste each team page."})
    : null);
  // What a matchup page did list: ESPN adds injured and bye players to the starters.
  function foundNote(res) {
    const counts = {};
    res.players.forEach(p => { const w = slotWord(p.slot); counts[w] = (counts[w] || 0) + 1; });
    const words = {Starter: n => plural(n, "starter"), Injured: n => `${n} injured`, Bye: n => `${n} on bye`, Bench: n => `${n} on the bench`, IR: n => `${n} on IR`};
    const parts = Object.keys(words).filter(w => counts[w]).map(w => words[w](counts[w]));
    const missing = ["Injured", "Bye"].filter(w => res.site === "espn" && !counts[w]).map(w => (w === "Injured" ? "no injured players" : "no bye players"));
    return el("p", {class: "v2-meta v2-find-found-note", text: `Found ${parts.join(", ")}${missing.length ? `; ${missing.join(", ")} listed` : ""}.`});
  }
  const countLine = (res, bad) => el("p", {class: `v2-find-paste-count ${bad ? "is-bad" : res.matched && res.matched === res.total ? "is-ok" : "is-warn"}`,
    text: `Matched ${res.matched} of ${res.total} players${siteWord(res.site)}.`});

  // text: the pasted page; side: where it was pasted; box: the side's result panel; done(): the paste was used.
  function readPage(text, side, box, done) {
    box.replaceChildren();
    if (!String(text || "").trim()) { put(box, el("p", {class: "v2-meta", text: "Nothing pasted yet."})); return; }
    const res = parsePage(text);
    if (!res) { put(box, el("p", {class: "v2-meta", text: "Values are still loading. Try again in a moment."})); return; }
    if (res.mode === "matchup" && res.teams && res.teams.length === 2) return readMatchup(res, side, box, done);
    if (!res.matched) {
      put(box, el("p", {class: "v2-find-paste-count is-bad", text: "No players recognised in that text. Nothing was added."}),
        el("p", {class: "v2-meta", text: "Paste the whole ESPN or Yahoo team page (Ctrl+A, Ctrl+C on the page), or search and add players by name below."}));
      return;
    }
    if (res.matched < MIN_MATCHED || res.matched / res.total < MIN_SHARE) {
      const anyway = el("button", {type: "button", class: "v2-btn", id: `${sideId(side)}PasteAnyway`, text: `Add these ${res.matched} anyway`});
      anyway.addEventListener("click", () => { box.replaceChildren(); placeTeam(side, res, box); done(); });
      put(box, countLine(res, true), el("p", {class: "v2-meta", text: "That is too few to trust, so nothing was added. Paste the whole team page, or search and add players by name below."}),
        anyway, ...unmatchedBlock(side, res.unmatched));
      return;
    }
    placeTeam(side, res, box);
    done();
  }
  function placeTeam(side, res, box) {
    const {added, onOther, unsure} = placePlayers(side, res.players, true);
    renderBoth();
    clearOutput();
    put(box, countLine(res),
      el("p", {class: "v2-meta", text: `${SIDE_NAME[side]} now has ${plural(S[side].length, "player")}.${onOther.length ? ` Left out because they are on the other roster: ${onOther.join(", ")}.` : ""}`}),
      matchedList(added), ...unsureBlock(side, unsure), ...unmatchedBlock(side, res.unmatched), benchNote(res));
  }
  const teamLabel = (res, i) => res.teams[i].teamName || `Team ${i + 1} (listed ${i ? "second" : "first"})`;
  function readMatchup(res, side, box, done) {
    const cards = res.teams.map((t, i) => {
      const pick = el("button", {type: "button", class: "v2-btn v2-find-pick-team", id: `${sideId(side)}PickTeam${i + 1}`, text: `${teamLabel(res, i)} is mine`});
      pick.addEventListener("click", () => assignMatchup(res, i, box, done));
      return el("div", {class: "v2-find-team"}, el("h4", {text: teamLabel(res, i)}),
        el("p", {class: "v2-meta", text: `${t.matched} of ${t.total} matched: ${t.players.map(p => p.name).join(", ") || "none"}.`}), pick);
    });
    put(box, el("p", {class: "v2-find-paste-count is-ok", text: `This is a matchup page with two teams. Matched ${res.matched} of ${res.total} players${siteWord(res.site)}.`}),
      el("p", {class: "v2-find-which", text: "Which team is yours?"}), el("div", {class: "v2-find-teams"}, ...cards), foundNote(res), benchNote(res));
  }
  function assignMatchup(res, mineIdx, box, done) {
    const sides = [mineIdx === 0 ? "mine" : "theirs", mineIdx === 0 ? "theirs" : "mine"];
    snapshot();
    S.mine = []; S.theirs = []; S.sel.clear();
    S.label = {mine: res.teams[mineIdx].teamName || "", theirs: res.teams[1 - mineIdx].teamName || ""};
    const placed = res.teams.map((t, i) => placePlayers(sides[i], t.players, true));
    renderBoth();
    clearOutput();
    box.replaceChildren();
    put(box, countLine(res),
      el("p", {class: "v2-find-assigned", text: `Your roster: ${teamLabel(res, mineIdx)} (${plural(S.mine.length, "player")}). Their roster: ${teamLabel(res, 1 - mineIdx)} (${plural(S.theirs.length, "player")}). Wrong way round? Use Swap teams above; Undo puts back what was there before.`}),
      ...res.teams.flatMap((t, i) => [el("h4", {text: `${teamLabel(res, i)}: ${SIDE_NAME[sides[i]].toLowerCase()}`}), matchedList(placed[i].added),
        ...unsureBlock(sides[i], placed[i].unsure), ...unmatchedBlock(sides[i], t.unmatched)]),
      foundNote(res), benchNote(res));
    arrangeSay(`Filled both rosters from the matchup page: ${teamLabel(res, mineIdx)} is yours.`);
    done();
  }

  function sideCard(side, title) {
    const id = `v2Find${side[0].toUpperCase()}${side.slice(1)}`;
    const list = el("ul", {class: "v2-trade-players", id: `${id}Players`});
    const results = el("ul", {class: "v2-trade-results", id: `${id}Results`, hidden: ""});
    const input = el("input", {type: "search", id: `${id}Search`, placeholder: "Search and add a player…", autocomplete: "off", "aria-controls": `${id}Results`});
    const label = el("label", {class: "v2-search"}, el("span", {class: "v2-sr", text: `Search and add a player to ${title.toLowerCase()}`}), input);
    const moveSel = el("button", {type: "button", class: "v2-btn v2-find-movesel", id: `${id}MoveSel`, text: "Move selected to the other team", disabled: ""});
    moveSel.addEventListener("click", () => moveKeys(S[side].filter(p => S.sel.has(p.key)).map(p => p.key)));
    const wrap = el("div", {class: "v2-trade-side v2-find-side", id}, el("h3", {text: title}), pasteBox(), label, results, list, moveSel, importBox());
    const render = () => {
      list.replaceChildren(...S[side].map(p => {
        const remove = el("button", {type: "button", class: "v2-link v2-find-remove", "aria-label": `Remove ${p.name}`, text: "Remove"});
        remove.addEventListener("click", () => { S[side] = S[side].filter(q => q.key !== p.key); S.sel.delete(p.key); render(); updateArrange(); clearOutput(); });
        const pick = el("input", {type: "checkbox", class: "v2-find-pick", "aria-label": `Select ${p.name} to move`});
        pick.checked = S.sel.has(p.key);
        pick.addEventListener("change", () => { if (pick.checked) S.sel.add(p.key); else S.sel.delete(p.key); updateArrange(); });
        const move = el("button", {type: "button", class: "v2-link v2-find-move", "aria-label": `Move ${p.name} to the other team`, text: "Move"});
        move.addEventListener("click", () => moveKeys([p.key]));
        return el("li", {class: "v2-find-row"}, el("label", {class: "v2-find-tick"}, pick), el("div", {}, el("b", {text: p.name}), el("span", {class: "v2-meta", text: p.pos ? ` ${p.pos}` : ""})), move, remove);
      }));
    };
    renders[side] = render;
    // JEG-853: the default input is the whole page copied from ESPN or Yahoo (Ctrl+A, Ctrl+C), read by
    // roster-paste.js in the browser. A matchup page fills both rosters; the user taps which team is theirs.
    function pasteBox() {
      const other = side === "mine" ? "theirs" : "mine";
      const area = el("textarea", {id: `${id}PastePage`, rows: "4", autocomplete: "off", spellcheck: "false",
        "aria-describedby": `${id}PasteHelp`,
        placeholder: side === "mine"
          ? "On your ESPN or Yahoo team page press Ctrl+A, Ctrl+C, then paste here. Paste the matchup page to fill both rosters."
          : "On the other manager's ESPN or Yahoo team page press Ctrl+A, Ctrl+C, then paste here."});
      const help = el("p", {class: "v2-meta v2-find-paste-help", id: `${id}PasteHelp`, text: "Pasted text stays in this browser; nothing is sent anywhere. Players are matched to the values by name, team and position."});
      const read = el("button", {type: "button", class: "v2-btn", id: `${id}PasteGo`, text: "Read the pasted page"});
      const result = el("div", {class: "v2-find-paste-result", id: `${id}PasteResult`, role: "status", "aria-live": "polite"});
      const run = () => readPage(area.value, side, result, () => { area.value = ""; });
      read.addEventListener("click", run);
      area.addEventListener("paste", () => setTimeout(run, 0));
      return el("div", {class: "v2-find-paste"}, el("label", {class: "v2-field-label", for: `${id}PastePage`, text: `Paste ${side === "mine" ? "your" : "their"} team page`}),
        area, help, read, result);
    }
    // Import: a Sleeper league, a public ESPN league, or pasted names. Names are matched to the engine's rows.
    function importBox() {
      const sel = el("select", {id: `${id}Source`, "aria-label": "Where the roster comes from"},
        el("option", {value: "sleeper", text: "Sleeper league ID"}), el("option", {value: "espn", text: "ESPN public league ID"}),
        el("option", {value: "paste", text: "Pasted names"}));
      const leagueId = el("input", {type: "text", id: `${id}League`, placeholder: "League ID", autocomplete: "off", inputmode: "numeric", "aria-label": "League ID"});
      const paste = el("textarea", {id: `${id}Paste`, rows: "4", placeholder: "One player per line", hidden: "", "aria-label": "Pasted player names"});
      const load = el("button", {type: "button", class: "v2-btn", id: `${id}Load`, text: "Load teams"});
      const team = el("select", {id: `${id}Team`, hidden: "", "aria-label": "Team to import"});
      const use = el("button", {type: "button", class: "v2-btn", id: `${id}Use`, text: "Use this team", hidden: ""});
      const status = el("p", {class: "v2-meta", id: `${id}Status`, role: "status"});
      let teams = [];
      const say = text => { status.textContent = text; };
      sel.addEventListener("change", () => {
        const isPaste = sel.value === "paste";
        paste.hidden = !isPaste;
        leagueId.hidden = isPaste;
        load.textContent = isPaste ? "Add players" : "Load teams";
        team.hidden = true; use.hidden = true; say("");
      });
      // entries -> engine rows; replace (a team) or add (pasted names). A player on the other roster is not moved.
      function apply(entries, from, replace) {
        const rows = engine() ? engine().getAllRows() : [];
        const {matched, unmatched} = matchNames(entries, rows);
        const other = new Set(S[side === "mine" ? "theirs" : "mine"].map(p => p.key));
        const keep = replace ? [] : S[side];
        const have = new Set(keep.map(p => p.key));
        const added = [];
        const onOther = [];
        matched.forEach(row => {
          const key = String(row.player_key);
          if (other.has(key)) onOther.push(row.name);
          else if (!have.has(key)) { have.add(key); added.push({key, name: row.name, pos: row.pos}); }
        });
        S[side] = keep.concat(added);
        render();
        updateArrange();
        clearOutput();
        const parts = [`Added ${added.length} player${added.length === 1 ? "" : "s"}${from ? ` from ${from}` : ""}.`];
        if (onOther.length) parts.push(`Left out because they are on the other roster: ${onOther.join(", ")}.`);
        if (unmatched.length) parts.push(`Not matched (${unmatched.length}): ${unmatched.slice(0, 8).map(u => u.name).join(", ")}${unmatched.length > 8 ? ", …" : ""}.`);
        say(parts.join(" "));
      }
      load.addEventListener("click", async () => {
        if (sel.value === "paste") { apply(parsePasted(paste.value), "", false); paste.value = ""; return; }
        const idText = leagueId.value.trim();
        if (!/^[A-Za-z0-9_-]+$/.test(idText)) { say("Enter the league ID: the number in your league's web address."); return; }
        say(sel.value === "sleeper" ? "Loading the league and Sleeper's player names (about 15 MB the first time)…" : "Loading the league…");
        try {
          teams = await (sel.value === "sleeper" ? loadSleeper(idText) : loadEspn(idText));
        } catch (error) {
          teams = [];
          say(`${error.message} You can paste the roster instead.`);
          team.hidden = true; use.hidden = true;
          return;
        }
        team.replaceChildren(...teams.map((t, i) => el("option", {value: String(i), text: `${t.label} (${t.entries.length} players)`})));
        team.hidden = !teams.length; use.hidden = !teams.length;
        say(teams.length ? `Found ${teams.length} teams. Pick yours and choose Use this team.` : "That league has no teams.");
      });
      use.addEventListener("click", () => { const t = teams[Number(team.value)]; if (t) apply(t.entries, t.label, true); });
      return el("details", {class: "v2-find-import"}, el("summary", {text: "Other ways to add players: a Sleeper or ESPN league ID, or a list of names"}),
        el("div", {class: "v2-find-import-body"}, el("label", {class: "v2-field"}, el("span", {class: "v2-field-label", text: "From:"}), sel),
          leagueId, paste, load, team, use, status));
    }
    window.TradeValueNameSearch.combobox(input, results);   // JEG-900
    input.addEventListener("input", () => {
      const q = input.value.trim();
      results.replaceChildren();
      results.hidden = !q;
      if (!q || !engine()) return;
      const taken = new Set(S.mine.concat(S.theirs).map(p => p.key));
      // JEG-861: the page's one name matcher (reversed names, suffixes, typos), never a plain "contains".
      const hits = window.TradeValueNameSearch.search(engine().getAllRows(), q).slice(0, 8);
      if (!hits.length) results.append(el("li", {class: "is-empty v2-meta", text: `No player name matches “${q}”.`}));
      hits.forEach(row => {
        const key = String(row.player_key);
        const added = taken.has(key);
        const button = el("button", {type: "button", text: `${`${row.name} · ${row.pos || ""} ${row.team || ""}`.trim()}${added ? " ✓ Added" : ""}`});
        if (added) button.disabled = true;
        button.addEventListener("click", () => {
          S[side].push({key, name: row.name, pos: row.pos});
          input.value = "";
          results.replaceChildren();
          results.hidden = true;
          render();
          clearOutput();
          input.focus();
        });
        results.append(el("li", {}, button));
      });
    });
    return wrap;
  }

  const fmt = n => (Math.abs(n) < 0.05 ? "0.0" : (n > 0 ? "+" : "") + n.toFixed(1));
  const names = rows => rows.map(r => r.name).join(" + ");

  function run() {
    const out = $("v2FindOut");
    out.hidden = false;
    out.replaceChildren();
    const note = text => out.append(el("p", {class: "v2-meta", text}));
    const C = engine();
    if (!C) return note("Values are still loading.");
    if (!S.mine.length || !S.theirs.length) return note("Add at least one player to each roster.");
    const all = C.getAllRows();
    const byKey = new Map(all.map(r => [String(r.player_key), r]));
    const rowsOf = list => list.map(p => byKey.get(p.key)).filter(Boolean);
    // JEG-819: use only charts the engine says are available (not held or missing), matching Compare and Targets.
    const sourceInfo = C.getSourceInfo ? C.getSourceInfo() : [];
    const availableKeys = new Set(sourceInfo.filter(item => item.available).map(item => item.key));
    const charts = CHART_KEYS.filter(key => availableKeys.has(key));
    if (!charts.length) return note("No trade chart is available this week.");
    if (charts.length < MIN_CHARTS) note(`Only ${charts.length} trade chart${charts.length === 1 ? " is" : "s are"} available this week. Not enough charts to judge acceptance.`);
    const shape = C.getRosterShape ? C.getRosterShape() : null;
    const mineRows = rowsOf(S.mine);
    const theirRows = rowsOf(S.theirs);
    // Roster sanity on what was typed in: a position the league starts that the roster does not cover.
    [["Your", mineRows], ["Their", theirRows]].forEach(([who, rows]) => {
      rosterGaps(rows, shape).forEach(g => note(`${who} roster has ${g.have} ${g.pos} for ${g.need} starting slot${g.need === 1 ? "" : "s"} in this league.`));
    });
    const res = findTrades(mineRows, theirRows, {chartKeys: charts, maxSize: S.maxSize, limit: 1e7,
      sanity: shape ? {shape, mine: mineRows, theirs: theirRows, keepMine: S.keepMine, keepTheirs: S.keepTheirs} : null});
    if (res.sanityDropped) note(`${res.sanityDropped} trade${res.sanityDropped === 1 ? "" : "s"} left out because ${res.sanityDropped === 1 ? "it leaves" : "they leave"} a starting lineup short at a position. Untick the boxes below to see ${res.sanityDropped === 1 ? "it" : "them"}.`);
    const skipped = res.mine.unpriced + res.theirs.unpriced;
    if (skipped) note(`${skipped} player${skipped === 1 ? " has" : "s have"} no DDF Value and ${skipped === 1 ? "is" : "are"} left out, not counted as 0.`);
    if (res.mine.searched < res.mine.of || res.theirs.searched < res.theirs.of) {
      note(`Packages of up to ${S.maxSize} are searched among your top ${res.mine.searched} and their top ${res.theirs.searched} players by DDF Value.`);
    }
    if (!res.trades.length) {
      return note(`No trade found where DDF Value says you win and at least ${res.minCharts} of ${charts.length} available trade chart${charts.length === 1 ? "s say" : "s say"} they break even or win. Try a larger package.`);
    }
    const groups = groupTrades(res.trades, {ourKey: res.ourKey});
    const shown = Math.min(GROUP_LIMIT, groups.length);
    note(`${res.total} trade${res.total === 1 ? "" : "s"} found in ${plural(groups.length, "group")}; ${groups.length > shown ? `the top ${shown} groups are listed` : "all are listed"}, ranked by the best DDF Value edge in each, with simpler trades first.`
      + (res.foldedThrowIns ? ` ${plural(res.foldedThrowIns, "trade")} folded into a simpler one that only adds a player worth 0.0.` : ""));
    const list = el("ol", {class: "v2-find-list", id: "v2FindList"});
    const ctx = {...res.ctx, maxSize: res.maxSize};
    groups.slice(0, shown).forEach(g => list.append(groupCard(g, ctx)));
    out.append(list);
    if (groups.length > shown) {
      const more = el("button", {type: "button", class: "v2-btn", id: "v2FindMoreGroups", text: `Show ${plural(groups.length - shown, "more group")}`});
      more.addEventListener("click", () => { groups.slice(shown).forEach(g => list.append(groupCard(g, ctx))); more.remove(); });
      out.append(more);
    }
  }

  // One group: the player you receive, the best package for him preselected, side players selectable.
  // Each toggle re-judges the package with evaluateCombo, the function the search itself uses.
  const GROUP_LIMIT = 10;
  const valueText = (row, key) => (finite(row.values[key]) ? row.values[key].toFixed(1) : "no value");
  function groupCard(group, ctx) {
    const ourKey = ctx.ourKey;
    const order = byValueDesc(ourKey);
    const heavyKeys = new Set(group.heavy.map(r => String(r.player_key)));
    const giveSel = new Set(group.best.give.map(r => String(r.player_key)));
    const recvSel = new Set(group.best.receive.map(r => String(r.player_key)).filter(k => !heavyKeys.has(k)));
    const keyOf = r => String(r.player_key);
    const tradeLabel = el("b", {class: "v2-find-trade"});
    const meta = el("span", {class: "v2-meta v2-find-edge"});
    const notes = el("span", {class: "v2-meta v2-find-notes"});
    const open = el("a", {class: "v2-link", text: "Open in Compare a trade"});
    const li = el("li", {class: "v2-find-group"});
    const target = el("span", {class: "v2-find-target"});
    target.append(el("span", {class: "v2-find-target-label", text: "Target: "}), el("span", {class: "v2-find-target-name", text: names(group.heavy)}),
      el("span", {class: "v2-meta", text: ` ${[group.core.pos, group.core.team].filter(Boolean).join(" · ")} · ${valueText(group.core, ourKey)} DDF Value`}));
    const boxes = [];
    const sideSet = (title, rows, sel, fixed) => {
      const box = el("fieldset", {class: "v2-find-side-pick"}, el("legend", {text: title}));
      rows.forEach(r => {
        const input = el("input", {type: "checkbox", "aria-label": `Include ${r.name} (value ${valueText(r, ourKey)})`});
        input.checked = sel.has(keyOf(r));
        if (fixed) input.disabled = true;
        input.addEventListener("change", () => { if (input.checked) sel.add(keyOf(r)); else sel.delete(keyOf(r)); refresh(); });
        const label = el("label", {class: "v2-find-pick-row"}, input, el("span", {text: `${r.name} `}), el("span", {class: "v2-meta", text: `(${valueText(r, ourKey)} DDF Value)`}));
        box.append(label);
        if (!fixed) boxes.push({input, row: r, sel, side: title});
      });
      return box;
    };
    const selectable = group.giveCandidates.length > 1 || group.receiveSide.length > 0;
    const giveBox = selectable ? sideSet("You give", group.giveCandidates, giveSel, false) : null;
    const recvBox = group.receiveSide.length ? sideSet("You also receive (core stays)", group.receiveSide, recvSel, false) : null;
    const capNote = el("span", {class: "v2-meta v2-find-cap", hidden: ""});
    li.append(...[target, tradeLabel, meta, notes, giveBox, recvBox, capNote, open].filter(Boolean));

    function refresh() {
      const giveRows = group.giveCandidates.filter(r => giveSel.has(keyOf(r))).sort(order);
      const recvRows = group.heavy.concat(group.receiveSide.filter(r => recvSel.has(keyOf(r)))).sort(order);
      // Selection limits: the package size searched, and at least one player given.
      let capped = false;
      boxes.forEach(b => {
        const give = b.sel === giveSel;
        const full = give ? giveSel.size >= ctx.maxSize : group.heavy.length + recvSel.size >= ctx.maxSize;
        const last = give && giveSel.size <= 1;
        const block = !b.input.checked && full;
        b.input.disabled = block || (b.input.checked && last);
        if (block) capped = true;
      });
      capNote.hidden = !capped;
      capNote.textContent = capped ? `Package is capped at ${ctx.maxSize}-for-${ctx.maxSize}; untick a player to pick another.` : "";
      const e = evaluateCombo(giveRows, recvRows, ctx);
      const favor = e.charts.filter(c => c.rivalOk).map(c => CHART_NAMES[c.key] || c.key);
      const unpriced = e.charts.filter(c => c.net === null).length;
      const thin = e.issues ? [["you", e.issues.mine], ["them", e.issues.theirs]].filter(([, l]) => l.length)
        .map(([who, l]) => `Leaves ${who} thin: ${l.map(issueText).join("; ")}.`) : [];
      const ids = rows => rows.map(r => encodeURIComponent(r.player_key)).join(",");
      tradeLabel.textContent = `You give ${names(giveRows)}; you receive ${names(recvRows)}`;
      meta.textContent = `DDF Value edge ${fmt(e.edge)} for you. ${favor.length} of ${e.pricedCharts} trade chart${e.pricedCharts === 1 ? "" : "s"} have them winning or even${favor.length ? `: ${favor.join(", ")}` : ""}.`
        + (e.pricedCharts < MIN_CHARTS ? " Not enough charts to judge acceptance." : "")
        + (unpriced ? ` ${unpriced} chart${unpriced === 1 ? " does" : "s do"} not price every player and ${unpriced === 1 ? "is" : "are"} not counted.` : "")
        + (thin.length ? ` ${thin.join(" ")}` : "");
      const warn = [];
      if (!e.passes.edge) warn.push("DDF Value does not say you win this package.");
      if (!e.passes.charts) warn.push(`Only ${e.rivalOkCount} of ${e.pricedCharts} trade charts have them winning or even, so they may say no.`);
      if (!e.passes.lineup) warn.push("It leaves a starting lineup short at a position.");
      const same = group.trades.find(t => idOf(t) === `${giveRows.map(r => r.player_key)}|${recvRows.map(r => r.player_key)}`);
      const throwIns = same && same.throwIns ? [].concat(same.throwIns.give.map(r => `${r.name} (${valueText(r, ourKey)})`), same.throwIns.receive.map(r => `${r.name} (${valueText(r, ourKey)})`)) : [];
      notes.textContent = `${warn.join(" ")}${warn.length && throwIns.length ? " " : ""}${throwIns.length ? `Can add ${throwIns.join(", ")} as a throw-in.` : ""}`;
      notes.classList.toggle("is-warn", warn.length > 0);
      open.setAttribute("href", `v2/#compare-trade?give=${ids(giveRows)}&get=${ids(recvRows)}`);
      li.dataset.findEdge = String(e.edge);
    }
    refresh();
    return li;
  }

  // ---------- JEG-972: collapsible roster input ----------
  // After every Find trades press the roster input folds into one summary row per team (name, first three players,
  // position counts); "Edit rosters" opens it again. The package size, lineup boxes and Find button stay visible.
  const POS_ORDER = ["QB", "RB", "WR", "TE", "K", "DEF"];
  function positionCounts(list) {
    const counts = {};
    list.forEach(p => { const pos = p.pos || "?"; counts[pos] = (counts[pos] || 0) + 1; });
    const known = POS_ORDER.filter(pos => counts[pos]);
    const rest = Object.keys(counts).filter(pos => !POS_ORDER.includes(pos)).sort();
    return known.concat(rest).map(pos => `${counts[pos]} ${pos}`).join(", ");
  }
  function summaryText(list) {
    if (!list.length) return {names: "No players yet", counts: ""};
    const first = list.slice(0, 3).map(p => p.name).join(", ");
    const more = list.length - 3;
    return {names: more > 0 ? `${first} + ${more} more` : first, counts: `${plural(list.length, "player")}: ${positionCounts(list)}`};
  }
  function updateSummary() {
    const box = $("v2FindSummary");
    if (!box) return;
    ["mine", "theirs"].forEach(side => {
      const t = summaryText(S[side]);
      const node = $(`${sideId(side)}Summary`);
      node.replaceChildren(el("b", {text: S.label[side] ? `${SIDE_NAME[side]}: ${S.label[side]}` : SIDE_NAME[side]}), el("span", {class: "v2-find-sum-names", text: t.names}), el("span", {class: "v2-meta", text: t.counts}));
    });
    $("v2FindEdit").setAttribute("aria-label", `Edit rosters: your roster has ${plural(S.mine.length, "player")}, their roster has ${plural(S.theirs.length, "player")}`);
  }
  function setCollapsed(collapsed, focus) {
    const input = $("v2FindInput");
    const summary = $("v2FindSummary");
    const edit = $("v2FindEdit");
    if (!input || !summary) return;
    if (collapsed) updateSummary();
    input.hidden = collapsed;
    summary.hidden = !collapsed;
    edit.setAttribute("aria-expanded", String(!collapsed));
    if (focus === "input") { const first = $("v2FindMinePastePage"); if (first) first.focus(); }
    else if (focus === "edit") edit.focus();
  }
  const hasResults = () => { const out = $("v2FindOut"); return Boolean(out) && !out.hidden && out.childElementCount > 0; };
  function findPressed() {
    run();
    if (!S.mine.length || !S.theirs.length) return;
    setCollapsed(true);
    const out = $("v2FindOut");
    if (out && out.scrollIntoView && root.innerWidth < 768) out.scrollIntoView({block: "start", behavior: "instant"});
  }

  function build() {
    const host = $("v2FindTrade");
    if (!host || $("v2Find")) return;
    const size = el("select", {id: "v2FindSize"}, ...MAX_SIZE_CHOICES.map(n => el("option", {value: String(n), text: `Up to ${n}-for-${n}`})));
    size.addEventListener("change", () => { S.maxSize = Number(size.value); clearOutput(); });
    const keep = (id, label, field) => {
      const box = el("input", {type: "checkbox", id});
      box.checked = S[field];
      box.addEventListener("change", () => { S[field] = box.checked; clearOutput(); });
      return el("label", {class: "v2-field"}, box, el("span", {text: ` ${label}`}));
    };
    const go = el("button", {type: "button", class: "v2-btn", id: "v2FindGo", text: "Find trades"});
    go.addEventListener("click", findPressed);
    const swap = el("button", {type: "button", class: "v2-btn", id: "v2FindSwap", text: "Swap teams"});
    swap.addEventListener("click", swapTeams);
    const undo = el("button", {type: "button", class: "v2-btn", id: "v2FindUndo", text: "Undo", disabled: ""});
    undo.addEventListener("click", undoArrange);
    const edit = el("button", {type: "button", class: "v2-btn", id: "v2FindEdit", text: "Edit rosters", "aria-expanded": "true", "aria-controls": "v2FindInput"});
    edit.addEventListener("click", () => setCollapsed(false, "input"));
    const summaryRow = el("div", {class: "v2-find-summary", id: "v2FindSummary", hidden: ""},
      el("div", {class: "v2-find-sumrow", id: "v2FindMineSummary"}), el("div", {class: "v2-find-sumrow", id: "v2FindTheirsSummary"}), edit);
    // Escape inside the opened input folds it back once there are results to read.
    const card = el("section", {class: "v2-card", id: "v2Find", "aria-labelledby": "v2FindTitle"},
      el("div", {class: "v2-card-head"}, el("div", {},
        el("h2", {id: "v2FindTitle", text: "Your roster and theirs"}),
        el("p", {class: "v2-meta", text: "Paste in your roster and another manager's (or one matchup page for both), or search names. Lists trades where DDF Value says you win and the available trade charts say the other manager breaks even or wins."}))),
      summaryRow,
      el("div", {id: "v2FindInput"},
        el("div", {class: "v2-ctoolbar v2-find-arrange"}, swap, undo, el("p", {class: "v2-meta", id: "v2FindArrangeNote", role: "status"})),
        el("div", {class: "v2-trade-sides"}, sideCard("mine", "Your roster"), sideCard("theirs", "Their roster"))),
      el("div", {class: "v2-ctoolbar"}, el("label", {class: "v2-field"}, el("span", {class: "v2-field-label", text: "Package size:"}), size),
        keep("v2FindKeepMine", "Keep my starting lineup filled", "keepMine"), keep("v2FindKeepTheirs", "Keep theirs filled", "keepTheirs"), go),
      el("div", {id: "v2FindOut", "aria-live": "polite", hidden: ""}));
    card.addEventListener("keydown", event => {
      if (event.key === "Escape" && !$("v2FindInput").hidden && hasResults() && S.mine.length && S.theirs.length) { setCollapsed(true, "edit"); }
    });
    host.insertBefore(card, host.querySelector(".v2-footnote"));
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", build);
  else build();
})(typeof window !== "undefined" ? window : globalThis);
