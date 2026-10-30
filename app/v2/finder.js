// Trade Value v2 — Find a trade (JEG-481: first slice, then league import and roster sanity).
//
// You choose saved League teams or type in your roster and a rival's. The search lists packages (1-for-1 up to N-for-N)
// where the published trade charts say the rival breaks even or wins, and DDF Value says you win.
//
// No value math of its own: every number is an engine row value (TradeValueCurveControls
// .getAllRows()); the search only adds and compares them, as Compare a trade does. A missing
// value stays missing, never 0.
//
// Decisions (Jeremy, 2026-10-09 / 2026-10-10, recorded on JEG-481):
//   * rosters are typed in with player search; the second slice (2026-10-16) adds pasted names. The Sleeper / ESPN
//     league-ID fetchers were deleted (Jeremy, 2026-10-27, JEG-1131): paste is the only way to load a league;
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
  const MAX_SIZE_CHOICES = [1, 2, 3, 4];
  const MAX_SUBSETS = 6000;          // per side; larger rosters search the top players by DDF Value
  const EXTRA_PLAYER_WEIGHT = 0.1;   // each player beyond a 1-for-1 takes 10% off the ranking score
  const LIMIT = 10;
  const finite = value => typeof value === "number" && Number.isFinite(value);
  // JEG-1125 option A: "even" is Compare's one band, evenBand in trade.js: max(EVEN_FLOOR, EVEN_SHARE x the average
  // side) on each series' own give and receive. SHOWN_EVEN is only how a net prints (0.0) and NET_FLOOR's fit floor.
  // The page loads trade.js first and Node can require it. The MCP edge function evaluates this file on its own, so
  // each number after || is a standalone copy: tests/test_trade_bands.py fails if one differs from trade.js.
  const TRADE = typeof module !== "undefined" && module.exports
    ? (() => { try { return require("./trade.js"); } catch (e) { return null; } })() : root.TradeValueTrade;
  const SHOWN_EVEN = (TRADE && finite(TRADE.SHOWN_EVEN) && TRADE.SHOWN_EVEN) || 0.05;
  const EVEN_FLOOR = (TRADE && finite(TRADE.EVEN_FLOOR) && TRADE.EVEN_FLOOR) || 1;
  const EVEN_SHARE = (TRADE && finite(TRADE.EVEN_SHARE) && TRADE.EVEN_SHARE) || 0.03;
  const evenBand = (give, get) => Math.max(EVEN_FLOOR, EVEN_SHARE * ((give + get) / 2));
  const pointsPastEven = (net, give, get) => (Math.abs(net) < evenBand(give, get) ? 0 : net);   // inside the band: even

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
  // give / get: sums arrays. The edge is get - give for you and must clear the even band; the rival is happy on a chart
  // when its net is even (inside that chart's band) or below.
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
      const rivalOk = pointsPastEven(net, g, r) <= 0;
      priced += 1;
      if (rivalOk) ok += 1;
      charts.push({key: chartKeys[c], net, rivalOk});
    }
    return {edge, charts, pricedCharts: priced, rivalOkCount: ok,
      passes: {edge: edge !== null && pointsPastEven(edge, give[0], get[0]) > 0, charts: priced >= minCharts && ok >= minCharts}};
  }
  // Roster sanity for a package: {mine, theirs} issue lists, and whether the keep-lineup boxes reject it.
  function judgeLineup(giveRows, getRows, sanity) {
    if (!sanity) return {issues: null, passes: true};
    const issues = {mine: lineupIssues(sanity.mineCounts, giveRows, getRows, sanity.shape),
      theirs: lineupIssues(sanity.theirCounts, getRows, giveRows, sanity.shape)};
    return {issues, passes: !((sanity.keepMine && issues.mine.length) || (sanity.keepTheirs && issues.theirs.length))};
  }
  const GUARDRAIL_POSITIONS = ["QB", "RB", "WR", "TE"];
  const activeGuardrails = g => Boolean(g && ((Array.isArray(g.protectedPositions) && g.protectedPositions.length)
    || GUARDRAIL_POSITIONS.some(pos => g.minBackups && g.minBackups[pos] > 0)
    || g.minDdfEdge > 0 || typeof g.minUserLineupGain === "number" || typeof g.minTheirLineupGain === "number"));
  // The starter picker allocates QB/RB/WR/TE, then FLEX and SUPERFLEX once each. Only its remaining valued players
  // count as backups; a real 0 is valued, while a missing DDF value is never silently treated as a player at 0.
  function benchBackups(rows, shape, valueKey) {
    const bench = pickStarters(rows, shape, valueKey).bench;
    return Object.fromEntries(GUARDRAIL_POSITIONS.map(pos => [pos, bench.filter(row => row.pos === pos).length]));
  }
  // Mirrors viability.ts's neverWeaker guardrail using this page's existing starter picker and DDF values.
  function judgeGuardrails(giveRows, getRows, guardrails) {
    if (!guardrails || !guardrails.shape) return true;
    const protectedPositions = Array.isArray(guardrails.protectedPositions) ? guardrails.protectedPositions : [];
    const userMinimum = guardrails.minUserLineupGain;
    const theirMinimum = guardrails.minTheirLineupGain;
    const minimumBackups = guardrails.minBackups || {};
    if (!protectedPositions.length && userMinimum == null && theirMinimum == null
      && !GUARDRAIL_POSITIONS.some(pos => minimumBackups[pos] > 0)) return true;
    const valueKey = guardrails.ourKey || OUR_KEY;
    const after = rosterAfter(guardrails.mine, giveRows, getRows);
    if (GUARDRAIL_POSITIONS.some(pos => minimumBackups[pos] > 0)) {
      const counts = benchBackups(after, guardrails.shape, valueKey);
      if (GUARDRAIL_POSITIONS.some(pos => counts[pos] < (minimumBackups[pos] || 0))) return false;
    }
    if (protectedPositions.length) {
      const beforePicked = pickStarters(guardrails.mine, guardrails.shape, valueKey);
      const afterPicked = pickStarters(after, guardrails.shape, valueKey);
      for (const pos of protectedPositions) {
        if (!GUARDRAIL_POSITIONS.includes(pos)) continue;
        const valueAt = picked => picked.starters.filter(r => r.pos === pos).reduce((sum, r) => sum + r.values[valueKey], 0);
        if (valueAt(afterPicked) < valueAt(beforePicked) - 0.05) return false;
      }
    }
    if (typeof userMinimum === "number" && Number.isFinite(userMinimum)) {
      if (!(rosterImpact(guardrails.mine, giveRows, getRows, guardrails.shape, valueKey).starterDelta > userMinimum)) return false;
    }
    if (typeof theirMinimum === "number" && Number.isFinite(theirMinimum)) {
      const charts = guardrails.chartKeys || CHART_KEYS;
      const theirImpact = rosterImpact(withChartAverage(guardrails.theirs, charts), withChartAverage(getRows, charts),
        withChartAverage(giveRows, charts), guardrails.shape, MARKET_KEY);
      if (!(theirImpact.starterDelta > theirMinimum)) return false;
    }
    return true;
  }
  function rosterAfter(roster, leaving, arriving) {
    const gone = new Set(leaving.map(r => String(r.player_key)));
    return roster.filter(r => !gone.has(String(r.player_key))).concat(arriving);
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
      passes: {edge: judged.passes.edge && (!(ctx.guardrails && ctx.guardrails.minDdfEdge > 0) || edge > ctx.guardrails.minDdfEdge),
        charts: judged.passes.charts, lineup: lineup.passes,
        ...(ctx.guardrails ? {guardrails: judgeGuardrails(giveRows, receiveRows, ctx.guardrails)} : {})}};
  }

  // mine / theirs: engine rows. opts: {ourKey, chartKeys, maxSize, minCharts, limit}.
  // Each trade: {give, receive, edge, charts: [{key, net, rivalOk}], pricedCharts, rivalOkCount, score, throwIns}.
  // edge and net are receive - give for you; the rival is happy when a chart's net is even (inside its band, JEG-1125) or below.
  // Rows that differ only by a player worth 0.0 everywhere are one row (the simpler trade), see collapseThrowIns.
  function findTrades(mine, theirs, opts) {
    const o = opts || {};
    const ourKey = o.ourKey || OUR_KEY;
    const maxSize = Math.max(1, o.maxSize || 2);
    const chartKeys = (o.chartKeys || CHART_KEYS).slice();
    const minCharts = o.minCharts || Math.min(MIN_CHARTS, chartKeys.length);
    const limit = o.limit || LIMIT;
    const guardrails = activeGuardrails(o.guardrails) ? o.guardrails : null;
    // Optional roster sanity: {shape, mine, theirs (all the side's rows), keepMine, keepTheirs}.
    const sanity = o.sanity ? {...o.sanity, mineCounts: countByPos(o.sanity.mine || []), theirCounts: countByPos(o.sanity.theirs || [])} : null;
    let sanityDropped = 0;
    let guardrailDropped = 0;
    const mineP = pool(mine, ourKey, maxSize);
    const theirsP = pool(theirs, ourKey, maxSize);
    const keys = [ourKey].concat(chartKeys);
    const describe = (rows, combo) => ({combo, sums: sumsOf(combo.map(i => rows[i]), keys)});
    const mineSubs = subsets(mineP.rows.length, maxSize).map(c => describe(mineP.rows, c));
    const theirSubs = subsets(theirsP.rows.length, maxSize).map(c => describe(theirsP.rows, c))
      .sort((a, b) => a.sums[0] - b.sums[0]);
    const balanceMine = (o.sanity && o.sanity.mine) || mine;
    const balanceTheirs = (o.sanity && o.sanity.theirs) || theirs;
    const balanceShape = o.sanity ? o.sanity.shape : null;
    const found = [];
    const seen = new Map();
    for (const give of mineSubs) {
      // DDF Value: you must win, so only their packages worth more than yours (sorted: binary search).
      let lo = 0; let hi = theirSubs.length;
      while (lo < hi) {
        const mid = (lo + hi) >> 1;
        const mid0 = theirSubs[mid].sums[0];
        if (pointsPastEven(mid0 - give.sums[0], give.sums[0], mid0) > 0) hi = mid; else lo = mid + 1;
      }
      for (let t = lo; t < theirSubs.length; t++) {
        const get = theirSubs[t];
        const judged = judgeSums(give.sums, get.sums, chartKeys, minCharts);
        if (!judged.passes.edge || !judged.passes.charts) continue;
        let giveRows = give.combo.map(i => mineP.rows[i]);
        let getRows = get.combo.map(i => theirsP.rows[i]);
        let verdict = judged;
        let addedThrowIns = [];
        let unbalanced = false;
        // JEG-1108: the team receiving more players adds its own least valuable bench players (one per missing player) to
        // the other side, so both sides trade the same number of players. The package is then judged again with the
        // throw-ins in it. If the team has no bench player left, balanceCounts adds nothing and the trade is kept as it was, marked unbalanced.
        if (giveRows.length !== getRows.length) {
          let work = {give: giveRows, receive: getRows};
          const added = [];
          while (work.give.length !== work.receive.length) {
            const step = balanceCounts(work, balanceMine, balanceTheirs, balanceShape, ourKey, keys);
            if (!step.balanced) break;
            added.push({side: step.give.length > work.give.length ? "give" : "receive", row: step.throwInPlayer});
            work = {give: step.give, receive: step.receive};
          }
          if (work.give.length === work.receive.length) {
            giveRows = work.give;
            getRows = work.receive;
            addedThrowIns = added;
            verdict = judgeSums(sumsOf(giveRows, keys), sumsOf(getRows, keys), chartKeys, minCharts);
            if (!verdict.passes.edge || !verdict.passes.charts) continue;
          } else unbalanced = true;
        }
        const lineup = judgeLineup(giveRows, getRows, sanity);
        if (!lineup.passes) { sanityDropped += 1; continue; }
        if (guardrails && ((guardrails.minDdfEdge > 0 && !(verdict.edge > guardrails.minDdfEdge))
          || !judgeGuardrails(giveRows, getRows, guardrails))) { guardrailDropped += 1; continue; }
        const entry = {give: giveRows, receive: getRows, edge: verdict.edge, charts: verdict.charts, issues: lineup.issues,
          pricedCharts: verdict.pricedCharts, rivalOkCount: verdict.rivalOkCount, score: scoreOf(verdict.edge, giveRows.length + getRows.length),
          ...(addedThrowIns.length ? {addedThrowIns} : {}), ...(unbalanced ? {unbalanced: true} : {})};
        // A balanced variant can be the same package the search also reached directly: one trade, the throw-in listed.
        const id = idOf(entry);
        if (seen.has(id)) {
          const at = seen.get(id);
          if (entry.addedThrowIns && !found[at].addedThrowIns) found[at] = entry;
          continue;
        }
        seen.set(id, found.length);
        found.push(entry);
      }
    }
    found.sort((a, b) => b.score - a.score || b.edge - a.edge
      || (a.give.length + a.receive.length) - (b.give.length + b.receive.length)
      || idOf(a).localeCompare(idOf(b)));
    const collapsed = collapseThrowIns(found, chartKeys, ourKey);
    return {trades: collapsed.slice(0, limit), total: collapsed.length, foldedThrowIns: found.length - collapsed.length, sanityDropped,
      ...(guardrails ? {guardrailDropped} : {}), ourKey, chartKeys, minCharts, maxSize,
      mine: mineP, theirs: theirsP, ctx: {ourKey, chartKeys, minCharts, sanity, ...(guardrails ? {guardrails} : {})}};
  }
  const idOf = trade => `${trade.give.map(r => r.player_key)}|${trade.receive.map(r => r.player_key)}`;

  // ---------- JEG-1108: client-side viability label ----------
  // Lightweight viability label (High / Med-High / Medium) from data already in tradeFit + rosterImpact.
  // Mirrors the server-side label in viability.ts without the full check suite.
  // Returns null when the data is insufficient, the label string otherwise.
  function viabilityLabel(fit, mineRoster, theirRoster, give, recv, shape, ourKey, chartKeys) {
    if (!fit || !shape) return null;
    const mk = MARKET_KEY;
    // Apply trade to both rosters.
    const goneM = new Set(give.map(r => String(r.player_key)));
    const goneT = new Set(recv.map(r => String(r.player_key)));
    const mineAfter = mineRoster.filter(r => !goneM.has(String(r.player_key))).concat(recv);
    const theirAfter = theirRoster.filter(r => !goneT.has(String(r.player_key))).concat(give);
    // Check: both keep a QB.
    if (!mineAfter.some(r => r.pos === "QB") || !theirAfter.some(r => r.pos === "QB")) return null;
    // Check: no empty starting slots for either team.
    const myPicked = pickStarters(mineAfter, shape, ourKey);
    const theirPicked = pickStarters(theirAfter, shape, mk);
    const myEmpty = Object.values(myPicked.empty).reduce((a, b) => a + b, 0);
    const theirEmpty = Object.values(theirPicked.empty).reduce((a, b) => a + b, 0);
    if (myEmpty > 0 || theirEmpty > 0) return null;
    // DDF edge must be non-negative for user.
    const ddfEdge = recv.reduce((s, r) => s + (r.values && finite(r.values[ourKey]) ? r.values[ourKey] : 0), 0)
      - give.reduce((s, r) => s + (r.values && finite(r.values[ourKey]) ? r.values[ourKey] : 0), 0);
    if (ddfEdge < 0) return null;
    // Their market net.
    const theirMarketNet = give.reduce((s, r) => s + (r.values && finite(r.values[mk]) ? r.values[mk] : 0), 0)
      - recv.reduce((s, r) => s + (r.values && finite(r.values[mk]) ? r.values[mk] : 0), 0);
    // Their lineup delta.
    const theirLineupBefore = pickStarters(theirRoster, shape, mk).starters.reduce((s, r) => s + (r.values && finite(r.values[mk]) ? r.values[mk] : 0), 0);
    const theirLineupAfter = theirPicked.starters.reduce((s, r) => s + (r.values && finite(r.values[mk]) ? r.values[mk] : 0), 0);
    const theirLineupDelta = theirLineupAfter - theirLineupBefore;
    // Label assignment (mirrors viability.ts).
    const tradedPos = new Set(recv.map(r => r.pos));
    const posGetsStronger = [...tradedPos].some(pos => {
      const before = pickStarters(theirRoster, shape, mk).starters.filter(r => r.pos === pos).reduce((s, r) => s + (r.values[mk] || 0), 0);
      const after = theirPicked.starters.filter(r => r.pos === pos).reduce((s, r) => s + (r.values[mk] || 0), 0);
      return after > before + 0.05;
    });
    if (posGetsStronger && theirLineupDelta > 0.5) return "High";
    if (theirLineupDelta > 0.5 || theirMarketNet > 1) return "Med-High";
    return "Medium";
  }

  // ---------- JEG-1108: player-count balancing ----------
  // If one team receives more players, auto-add the receiving-more team's own least valuable bench player (a non-starter)
  // as a throw-in on the other side so counts match. One trade with the throw-in listed. Edge case: a team with no bench
  // player left to add leaves the trade unbalanced.
  function balanceCounts(trade, mineRoster, theirRoster, shape, ourKey, requireKeys) {
    const giveCount = trade.give.length;
    const recvCount = trade.receive.length;
    if (giveCount === recvCount) return {...trade, balanced: true, throwInPlayer: null};
    // The team that receives more must add a player from its roster (the other side gets it).
    const moreOnMySide = recvCount > giveCount;   // I receive more, so I must add from my roster
    const roster = moreOnMySide ? mineRoster : theirRoster;
    const key = moreOnMySide || !roster.some(r => r.values && finite(r.values.chart_avg)) ? ourKey : "chart_avg";
    // Already-involved players cannot be the throw-in.
    const involved = new Set(trade.give.concat(trade.receive).map(r => String(r.player_key)));
    // The search passes requireKeys (DDF Value and every compared chart): a throw-in must be priced everywhere, or the
    // package could not be judged on the charts it is missing.
    const priced = r => r.values && finite(r.values[key]) && (requireKeys || []).every(k => finite(r.values[k]));
    // The throw-in is the supplying team's least valuable BENCH player (Jeremy, 2026-10-26): a non-starter before the trade.
    // Only a team with no bench player left (none unused and priced) leaves the trade unbalanced.
    const starterKeys = shape ? new Set(pickStarters(roster, shape, key).starters.map(r => String(r.player_key))) : new Set();
    const eligible = roster.filter(r => !involved.has(String(r.player_key)) && !starterKeys.has(String(r.player_key)) && priced(r));
    if (!eligible.length) return {...trade, balanced: false, throwInPlayer: null, noBench: true};
    eligible.sort((a, b) => a.values[key] - b.values[key] || String(a.player_key).localeCompare(String(b.player_key)));
    const cheapest = eligible[0];
    // Add the throw-in to the side that must supply it.
    if (moreOnMySide) {
      return {...trade, give: trade.give.concat([cheapest]), throwInPlayer: cheapest, balanced: true};
    }
    return {...trade, receive: trade.receive.concat([cheapest]), throwInPlayer: cheapest, balanced: true};
  }

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


  // ---------- JEG-972 / JEG-890 / JEG-891: best lineup and roster impact (display only; ranking never reads it) ----------
  const FLEX_POS = ["RB", "WR", "TE"];
  const SUPERFLEX_POS = ["QB", "RB", "WR", "TE"];
  const SLOTS = ["QB", "RB", "WR", "TE", "FLEX", "SUPERFLEX"];
  const MARKET_KEY = "chart_avg";
  // The best starting lineup for the league's slots: QB, RB, WR, TE take the highest valueKey at their position, then
  // FLEX from what is left of RB/WR/TE, then SUPERFLEX from what is left of QB/RB/WR/TE. Ties by lower player_key. A
  // player with no value is never a starter (listed in unvalued, not counted as 0); a slot nobody can fill stays
  // empty (empty[slot] = how many), never filled with waiver value.
  function pickStarters(rows, shape, valueKey) {
    const hasValue = r => Boolean(r.values) && finite(r.values[valueKey]);
    const valued = rows.filter(hasValue).sort(byValueDesc(valueKey));
    const unvalued = rows.filter(r => !hasValue(r));
    const taken = new Set();
    const slots = {};
    const empty = {};
    const fill = (slot, allowed) => {
      const want = (shape && shape[slot]) || 0;
      const got = [];
      for (const r of valued) {
        if (got.length >= want) break;
        if (!taken.has(r) && allowed.includes(r.pos)) { got.push(r); taken.add(r); }
      }
      slots[slot] = got;
      if (got.length < want) empty[slot] = want - got.length;
    };
    ["QB", "RB", "WR", "TE"].forEach(pos => fill(pos, [pos]));
    fill("FLEX", FLEX_POS);
    fill("SUPERFLEX", SUPERFLEX_POS);
    return {starters: SLOTS.flatMap(slot => slots[slot]), bench: valued.filter(r => !taken.has(r)), unvalued, slots, empty};
  }
  const countWord = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;
  const sumOf = (rows, key) => rows.reduce((total, r) => total + r.values[key], 0);
  // One team in one point of view: starter, bench and total value, starters per position, empty slots.
  function lineupValue(rows, shape, valueKey) {
    const picked = pickStarters(rows, shape, valueKey);
    const counts = {QB: 0, RB: 0, WR: 0, TE: 0};
    picked.starters.forEach(r => { counts[r.pos] += 1; });
    const starterValue = sumOf(picked.starters, valueKey);
    const benchValue = sumOf(picked.bench, valueKey);
    return {...picked, starterValue, benchValue, total: starterValue + benchValue, counts, size: rows.length};
  }
  // Rows with the mean of the compared charts as one more series (the Trade chart average, as Compare's market read).
  // A player any compared chart does not price has no average (never read as 0).
  function withChartAverage(rows, chartKeys) {
    return rows.map(r => {
      const vals = chartKeys.map(k => (r.values ? r.values[k] : undefined));
      const complete = chartKeys.length > 0 && vals.every(finite);
      return {...r, values: {...r.values, [MARKET_KEY]: complete ? vals.reduce((a, b) => a + b, 0) / vals.length : null}};
    });
  }
  // A team's roster before and after a trade, in one point of view (valueKey).
  function rosterImpact(roster, leaving, arriving, shape, valueKey) {
    const gone = new Set(leaving.map(r => String(r.player_key)));
    const after = roster.filter(r => !gone.has(String(r.player_key))).concat(arriving);
    const before = lineupValue(roster, shape, valueKey);
    const next = lineupValue(after, shape, valueKey);
    return {before, after: next, starterDelta: next.starterValue - before.starterValue, benchDelta: next.benchValue - before.benchValue,
      totalDelta: next.total - before.total, spotsOpened: before.size - next.size};
  }
  // One compact line: where the starter count by position changes, a slot left empty, a roster spot opened.
  function needLine(impact) {
    const parts = [];
    ["QB", "RB", "WR", "TE"].forEach(pos => {
      const b = impact.before.counts[pos];
      const a = impact.after.counts[pos];
      if (a !== b) parts.push(`${pos}: ${countWord(b, "starter")} → ${a}`);
    });
    Object.keys(impact.after.empty).forEach(slot => {
      if (impact.after.empty[slot] > (impact.before.empty[slot] || 0)) parts.push(`${slot} slot left empty`);
    });
    if (impact.spotsOpened > 0) parts.push(`opens ${countWord(impact.spotsOpened, "roster spot")} (fill from waivers)`);
    return parts.length ? parts.join("; ") : "Starters by position unchanged";
  }
  // JEG-1043: a team's starters at each position it gives up, before and after the trade (names in lineup order;
  // FLEX and SUPERFLEX starters count at their own position). One entry per QB/RB/WR/TE among the leaving players.
  function startersAtGivenPositions(impact, leaving) {
    const names = (l, pos) => l.starters.filter(r => r.pos === pos).map(r => r.name);
    return ["QB", "RB", "WR", "TE"].filter(pos => leaving.some(r => r.pos === pos))
      .map(pos => ({pos, before: names(impact.before, pos), after: names(impact.after, pos)}));
  }
  const givenPositionsLine = entries => entries.map(e => `${e.pos} ${e.before.join(", ") || "none"} → ${e.after.join(", ") || "none"}`).join("; ");
  // JEG-1043: "Show viable offers only" keeps the groups whose best package has a viability label, in the same order.
  const viableGroups = (groups, labelOf) => groups.filter(g => Boolean(labelOf(g)));

  // ---------- JEG-890: team value summary for both pasted rosters ----------
  // A team's value by row (Starters, Bench, Total, then QB/RB/WR/TE) in each series, for the Find a trade page. The
  // starters are the ones pickStarters picks once from DDF Value, so Starters and Bench mean the same people in every
  // column. A player a series does not price is missing, never 0: that cell is a partial sum marked incomplete and the
  // missing names are returned (a real 0.0 counts). Held charts are absent from chartKeys; the caller names them.
  // JEG-1246: a player DDF Value does not price cannot be placed as a starter or on the bench (pickStarters never
  // guesses a slot for him), so he sits in his own "unplaced" partition: Starters + Bench + No DDF Value = Total in
  // every series. That row is listed only when someone is in it, and while it is, Starters and Bench carry his names
  // as `unplaced` (their split is not known, never a silent 0 or an invented starter).
  const SUMMARY_ROWS = ["starters", "bench", "unplaced", "total", "QB", "RB", "WR", "TE"];
  // players priced by valueOf: their sum, how many, and who has no value (never counted as 0). An empty row is a real
  // 0.0; a row nobody prices has no number at all (value null).
  function summaryCell(players, valueOf) {
    let sum = 0;
    let priced = 0;
    const missing = [];
    players.forEach(row => {
      const v = valueOf(row);
      if (finite(v)) { sum += v; priced += 1; } else missing.push(row.name);
    });
    return {value: priced || !players.length ? sum : null, priced, count: players.length, missing: missing.filter(Boolean), complete: missing.length === 0};
  }
  // rows: one team's engine rows; shape: the league's slots; chartKeys: the available, non-held charts (the list run()
  // compares); ourKey: DDF Value. series: [{key, id, cells}] with id "ddf", then "market" (the mean of chartKeys, absent
  // as a column when fewer than MIN_CHARTS of them), then one per chart. cells[row] per SUMMARY_ROWS.
  // Kickers and defenses (isNotEvaluated) are left out of every row, as the roster assessment leaves them out.
  function teamSummary(teamRows, shape, chartKeys, ourKey) {
    const rows = (teamRows || []).filter(r => !isNotEvaluated(r));
    const key = ourKey || OUR_KEY;
    const charts = chartKeys || [];
    const picked = pickStarters(rows, shape, key);
    const market = charts.length >= MIN_CHARTS;
    const avg = market ? new Map(withChartAverage(rows, charts).map(r => [String(r.player_key), r.values[MARKET_KEY]])) : null;
    const byPos = pos => rows.filter(r => r.pos === pos);
    const sets = {starters: picked.starters, bench: picked.bench, unplaced: picked.unvalued, total: rows.slice(), QB: byPos("QB"), RB: byPos("RB"), WR: byPos("WR"), TE: byPos("TE")};
    const unplaced = picked.unvalued.map(r => r.name).filter(Boolean);
    const valueOf = seriesKey => (seriesKey === MARKET_KEY
      ? row => (avg ? avg.get(String(row.player_key)) : null)
      : row => (row.values ? row.values[seriesKey] : null));
    const view = seriesKey => {
      const pick = valueOf(seriesKey);
      const cells = {};
      SUMMARY_ROWS.forEach(name => { cells[name] = summaryCell(sets[name], pick); });
      if (unplaced.length) ["starters", "bench"].forEach(name => { cells[name].unplaced = unplaced.slice(); });
      return {key: seriesKey, cells};
    };
    const series = [{...view(key), id: "ddf"}];
    series.push(market ? {...view(MARKET_KEY), id: "market"} : {key: MARKET_KEY, id: "market", available: false});
    charts.forEach(k => series.push({...view(k), id: k}));
    return {rows: SUMMARY_ROWS.filter(name => name !== "unplaced" || unplaced.length), series, picked, market, unplaced, size: rows.length, shape};
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
  // Rosters come from pasted names (JEG-1131: no platform fetchers); they become the same typed-in lists the
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
  // Pasted names: one per line or comma-separated; a trailing "(QB - TEN)" style note is dropped.
  function parsePasted(text) {
    return String(text || "").split(/[\n,;]+/).map(s => s.replace(/\(.*?\)/g, "").replace(/\s+-\s+.*$/, "").trim())
      .filter(Boolean).map(name => ({name, pos: ""}));
  }

  // ---------- JEG-988: one box per side; defenses and kickers kept but not evaluated ----------
  // Text that arrives in a side's one box is a pasted page when it has two or more non-empty lines or is longer than
  // 120 characters (no player name comes near that); anything shorter is a name search.
  const PAGE_MIN_LINES = 2;
  const PAGE_MIN_LENGTH = 121;
  function looksLikePage(text) {
    const value = String(text || "");
    const lines = value.split(/\r?\n/).filter(line => line.trim());
    return lines.length >= PAGE_MIN_LINES || value.trim().length >= PAGE_MIN_LENGTH;
  }
  // Defenses and kickers have no value in any series: they stay on a roster, are shown "Not evaluated", and are left out
  // of every sum (never nulled, never dropped, never counted as 0).
  const NOT_EVALUATED_POS = ["K", "DEF", "DST"];
  const isNotEvaluated = row => Boolean(row) && NOT_EVALUATED_POS.includes(row.pos);

  // ---------- JEG-988: roster balance and the generated evaluation ----------
  // Expected depth per position for one team, from the engine's own seats (adjustment allocation: dedicated, flex and
  // superflex starters plus D'Hondt bench seats by market bench ratios), divided by the teams. A fraction is shown as a
  // range (4.6 -> 4-5). allocation: [{pos, rostered, lineup, bench}] league-wide; teams: the league size.
  const DEPTH_POS = ["QB", "RB", "WR", "TE"];
  function expectedDepth(allocation, teams) {
    if (!Array.isArray(allocation) || !(teams > 0)) return null;
    const out = {};
    for (const pos of DEPTH_POS) {
      const a = allocation.find(item => item.pos === pos);
      if (!a || !finite(a.rostered) || !finite(a.lineup)) return null;
      const expected = a.rostered / teams;
      out[pos] = {starters: a.lineup / teams, bench: (a.bench || 0) / teams, expected, lo: Math.floor(expected + 1e-9), hi: Math.ceil(expected - 1e-9)};
    }
    return out;
  }
  const USABLE_MIN = 0.05;   // a value that shows as 0.0 is no depth: the player is not counted toward a view's depth
  const rangeText = e => (e.lo === e.hi ? String(e.lo) : `${e.lo}-${e.hi}`);
  // Players per position in one view against the expected range. A player counts toward depth in a view only when that
  // view gives him a usable value (DDF Value, or the Trade chart average for the market view); the rest are listed as
  // unusable, never counted as 0 and never dropped. Under: fewer than the low end; over: two or more above the high end
  // (one extra is normal depth). shape: the league's slots; ready: the roster has at least as many QB/RB/WR/TE players
  // as the league has starting slots (a partial roster is not judged).
  function rosterBalance(rows, expected, valueKey, shape) {
    if (!expected) return null;
    const slots = SLOT_KEYS.reduce((n, slot) => n + ((shape && shape[slot]) || 0), 0);
    const out = {positions: {}, ready: rows.filter(r => DEPTH_POS.includes(r.pos)).length >= slots && slots > 0, over: [], under: [], unusable: 0};
    for (const pos of DEPTH_POS) {
      const atPos = rows.filter(r => r.pos === pos);
      const usable = atPos.filter(r => r.values && finite(r.values[valueKey]) && r.values[valueKey] >= USABLE_MIN);
      const e = expected[pos];
      const have = usable.length;
      const status = have < e.lo ? "under" : have > e.hi + 1 ? "over" : "ok";
      out.positions[pos] = {pos, have, rostered: atPos.length, unusable: atPos.length - have, lo: e.lo, hi: e.hi, range: rangeText(e), status};
      out.unusable += atPos.length - have;
      if (status !== "ok") out[status].push(pos);
    }
    return out;
  }
  const SLOT_KEYS = ["QB", "RB", "WR", "TE", "FLEX", "SUPERFLEX"];
  const listJoin = items => (items.length <= 1 ? items.join("") : `${items.slice(0, -1).join(", ")} and ${items[items.length - 1]}`);
  // One short sentence for one team in one view. who: "your" | "their"; view: "fundamentals" | "market pricing";
  // unit: "DDF Value" | "trade chart average"; sums: {starters, bench} in that view.
  function evalSentence(who, view, unit, balance, sums) {
    const phrase = pos => { const b = balance.positions[pos]; return `${pos} (${b.have} counted, ${b.range} expected)`; };
    const bits = [];
    if (balance.over.length) bits.push(`overweight at ${listJoin(balance.over.map(phrase))}`);
    if (balance.under.length) bits.push(`underweight at ${listJoin(balance.under.map(phrase))}`);
    const head = `Based on ${view}, ${who} roster is ${bits.length ? bits.join(" and ") : "balanced by position"}.`;
    const value = sums ? ` ${who[0].toUpperCase()}${who.slice(1)} starting lineup is worth ${sums.starters.toFixed(1)} in ${unit}; the bench adds ${sums.bench.toFixed(1)}.` : "";
    const note = balance.unusable ? ` ${balance.unusable} ${balance.unusable === 1 ? "player has" : "players have"} no usable value in this view and ${balance.unusable === 1 ? "is" : "are"} not counted toward depth.` : "";
    return head + value + note;
  }

  // ---------- JEG-1108: fit labels rewrite ----------
  // Natural fit: roster construction works for both teams (after the trade: no bench player promoted to starter, no
  // starter lost without a starter coming back, no empty starting slot) AND your DDF Value total roster value (starters
  // plus bench at bench weight) rises at all (above 0.05; no noise floor on your side) with starter value not worse AND the other team's Trade chart average change is
  // within the noise floor (max(0.05, FIT_Z x noise)) or positive.
  // Market supported (renamed from Market fit, definition FLIPPED): the Trade chart average says the other team's side
  // is favorable (their change above 0.05, as shown; JEG-1187). Independent of the roster test.
  // Force fit: everything else. The old fourth label (value) is retired (JEG-1108).
  const FIT_Z = 1;
  const NET_FLOOR = SHOWN_EVEN;
  const FIT_TIER = {natural: 0, market: 1, force: 2};
  // The standard error of one player's value in a view: DDF Value, half the gap between its chart-based and
  // projection-based versions (two readings of one value); DDF Value (projections), the standard error of the mean of
  // the projection sources (ESPN, CBS rest of season, Razzball); the Trade chart average, the standard error of the
  // mean of the compared charts. 0 when the sources cannot say (fewer than two readings). JEG-1081.
  const PROJECTION_KEYS = ["espn", "cbsros", "razzball"];
  const PROJECTIONS_KEY = "ddf_value_projections";
  function standardErrorOfMean(vals) {
    if (vals.length < 2) return 0;
    const mean = vals.reduce((a, b) => a + b, 0) / vals.length;
    const variance = vals.reduce((a, b) => a + (b - mean) * (b - mean), 0) / (vals.length - 1);
    return Math.sqrt(variance / vals.length);
  }
  function valueNoise(row, key, chartKeys) {
    const v = (row && row.values) || {};
    if (key === OUR_KEY) return finite(v.ddf_value_charts) && finite(v.ddf_value_projections) ? Math.abs(v.ddf_value_charts - v.ddf_value_projections) / 2 : 0;
    if (key === PROJECTIONS_KEY) return standardErrorOfMean(PROJECTION_KEYS.map(k => v[k]).filter(finite));
    if (key === MARKET_KEY) return standardErrorOfMean((chartKeys || CHART_KEYS).map(k => v[k]).filter(finite));
    return 0;   // one source (a single chart or projection source): nothing to measure a spread against (JEG-1081 PR 6); the net floor decides
  }
  const benchWeight = (weights, pos) => (weights && finite(weights[pos]) ? weights[pos] : weights && finite(weights.overall) ? weights.overall : 0);
  const netOf = (l, key, weights) => l.starterValue + l.bench.reduce((total, r) => total + benchWeight(weights, r.pos) * r.values[key], 0);
  const bandDistance = (have, e) => Math.max(0, e.lo - have, have - (e.hi + 1));
  // Roster construction check (JEG-1108): after the trade, no bench player is promoted to a starting slot, no starter
  // is lost without a starter coming back, and no starting slot is left empty. Uses the same pickStarters logic.
  // Returns {ok, issues: string[]} where ok means all three conditions hold for this team.
  function rosterConstructionOk(team, shape, key) {
    const gone = new Set(team.leaving.map(r => String(r.player_key)));
    const after = team.roster.filter(r => !gone.has(String(r.player_key))).concat(team.arriving);
    const before = pickStarters(team.roster, shape, key);
    const next = pickStarters(after, shape, key);
    const issues = [];
    // No empty starting slot after the trade.
    const emptyAfter = Object.values(next.empty).reduce((a, b) => a + b, 0);
    if (emptyAfter > 0) {
      const slots = Object.entries(next.empty).map(([s, n]) => `${n} ${s}`).join(", ");
      issues.push(`empty starting slot${emptyAfter > 1 ? "s" : ""}: ${slots}`);
    }
    // No bench player promoted to starter: every starter after was either a starter before or is a newly arriving player.
    const beforeStarterKeys = new Set(before.starters.map(r => String(r.player_key)));
    const arrivingKeys = new Set(team.arriving.map(r => String(r.player_key)));
    const promoted = next.starters.filter(r => !beforeStarterKeys.has(String(r.player_key)) && !arrivingKeys.has(String(r.player_key)));
    if (promoted.length > 0) issues.push(`bench promoted to starter: ${promoted.map(r => r.name || r.player_key).join(", ")}`);
    // No starter lost without a starter coming back: every departing starter must be replaced by an arriving starter.
    const leavingKeys = new Set(team.leaving.map(r => String(r.player_key)));
    const startersLost = before.starters.filter(r => leavingKeys.has(String(r.player_key)));
    const startersGained = next.starters.filter(r => arrivingKeys.has(String(r.player_key)));
    if (startersLost.length > 0 && startersGained.length === 0) {
      issues.push(`starter${startersLost.length > 1 ? "s" : ""} lost with no starter arriving: ${startersLost.map(r => r.name || r.player_key).join(", ")}`);
    }
    return {ok: issues.length === 0, issues};
  }
  // One team in one view. team: {roster, leaving, arriving} (rows carrying every series); ctx: {shape, expected, weights, chartKeys, z}.
  function teamFit(team, ctx, key) {
    const gone = new Set(team.leaving.map(r => String(r.player_key)));
    const after = team.roster.filter(r => !gone.has(String(r.player_key))).concat(team.arriving);
    const before = lineupValue(team.roster, ctx.shape, key);
    const next = lineupValue(after, ctx.shape, key);
    const starterDelta = next.starterValue - before.starterValue;
    // A roster's raw total is different from the bench-weighted net used for fit. Only report its change when every
    // moving player has this view: lineupValue omits unpriced rows, which must not turn a missing trade value into zero.
    const totalDelta = team.leaving.concat(team.arriving).every(r => r.values && finite(r.values[key])) ? next.total - before.total : null;
    const net = netOf(next, key, ctx.weights) - netOf(before, key, ctx.weights);
    const noise = Math.sqrt(team.leaving.concat(team.arriving).reduce((total, r) => total + Math.pow(valueNoise(r, key, ctx.chartKeys), 2), 0));
    const tau = Math.max(NET_FLOOR, (finite(ctx.z) ? ctx.z : FIT_Z) * noise);
    const balB = rosterBalance(team.roster, ctx.expected, key, ctx.shape);
    const balA = rosterBalance(after, ctx.expected, key, ctx.shape);
    const ready = Boolean(balB && balB.ready);
    const depth = {};
    let needBefore = 0;
    let needAfter = 0;
    DEPTH_POS.forEach(pos => {
      if (!ready) return;
      const e = ctx.expected[pos];
      const b = balB.positions[pos].have;
      const a = balA.positions[pos].have;
      depth[pos] = {before: b, after: a, range: balB.positions[pos].range, distBefore: bandDistance(b, e), distAfter: bandDistance(a, e), statusBefore: balB.positions[pos].status, statusAfter: balA.positions[pos].status};
      needBefore += depth[pos].distBefore;
      needAfter += depth[pos].distAfter;
    });
    const emptyBefore = Object.values(before.empty).reduce((a, b) => a + b, 0);
    const emptyAfter = Object.values(next.empty).reduce((a, b) => a + b, 0);
    needBefore += emptyBefore;
    needAfter += emptyAfter;
    const up = net > tau;
    const down = net < -tau;
    const toward = needAfter < needBefore;
    const away = needAfter > needBefore;
    const awayAt = DEPTH_POS.filter(pos => depth[pos] && depth[pos].distAfter > depth[pos].distBefore);
    const towardAt = DEPTH_POS.filter(pos => depth[pos] && depth[pos].distAfter < depth[pos].distBefore);
    return {key, net, totalDelta, starterDelta, benchDelta: net - starterDelta, tau, up, down, flat: !up && !down, toward, away, awayAt, towardAt, depth, ready,
      needBefore, needAfter, emptyBefore, emptyAfter, ok: (up && !away) || (!up && !down && toward)};
  }
  // JEG-1108: rewritten fit labels. Three labels: natural, market, force (value retired).
  // Natural: roster construction OK for both teams AND your DDF Value total rises (starters not worse) AND their Trade
  // chart average change is within the noise floor or positive.
  // Market supported: the Trade chart average says the other team's side is favorable (independent of roster test).
  // Force: everything else.
  // sides: {mine, theirs: {roster, leaving, arriving}}; ctx adds ourKey and marketKey (and optionally projectionsKey). null when the market view is not available.
  const FIT_VARIANTS = ["natural", "market", "force"];
  // JEG-1324: Natural fit 1a (Jeremy, 2026-10-29: "1a"; and "Natural means both sides, not just 1 side"). This is the one
  // predicate every route uses to call a trade Natural: tradeFit here, ourFitOf (opportunities.js) through tradeFit's
  // `natural` field, and the connector, which evaluates this file. Each side passes three tests: its value test (yours: DDF
  // Value total up past 0.05 with starters no worse; theirs: Trade chart average up or within its noise floor), its own
  // roster construction, and its DDF Value (projections) not declining.
  // "Not declining" (Jeremy, 2026-10-29, D2 "A"): a fall that shows as 0.0 (under 0.05) holds, so a Natural trade never
  // shows a negative projections change. A side's projections are judged only when every moving player has a DDF Value
  // (projections); otherwise the side is not judged (null), and a side that is not judged is not Natural (Jeremy,
  // 2026-10-29, "A" on JEG-1324): a missing projection is never read as 0.
  const PROJ_FLOOR = NET_FLOOR;
  const projectionsHold = net => (finite(net) ? net >= 0 || Math.abs(net) < PROJ_FLOOR : null);
  // The bench-weighted change of one team in one view (the same measure as teamFit's net), without the depth readout.
  function viewNet(team, ctx, key) {
    const gone = new Set(team.leaving.map(r => String(r.player_key)));
    const after = team.roster.filter(r => !gone.has(String(r.player_key))).concat(team.arriving);
    return netOf(lineupValue(after, ctx.shape, key), key, ctx.weights) - netOf(lineupValue(team.roster, ctx.shape, key), key, ctx.weights);
  }
  // parts: {yourValueOk, theirValueOk, myConstruction, theirConstruction, usProjNet, themProjNet} (a net is null when not judged).
  function naturalFit(parts) {
    const side = (value, construction, projNet) => {
      const projections = projectionsHold(projNet);
      return {value: Boolean(value), construction: Boolean(construction && construction.ok), projections, projNet: finite(projNet) ? projNet : null,
        ok: Boolean(value) && Boolean(construction && construction.ok) && projections === true};
    };
    const us = side(parts.yourValueOk, parts.myConstruction, parts.usProjNet);
    const them = side(parts.theirValueOk, parts.theirConstruction, parts.themProjNet);
    return {ok: us.ok && them.ok, us, them};
  }
  function tradeFit(sides, ctx) {
    if (!ctx || !ctx.marketKey) return null;
    const projKey = ctx.projectionsKey || PROJECTIONS_KEY;
    const us = teamFit(sides.mine, ctx, ctx.ourKey);
    const them = teamFit(sides.theirs, ctx, ctx.marketKey);
    const usOther = teamFit(sides.mine, ctx, ctx.marketKey);
    const themOther = teamFit(sides.theirs, ctx, ctx.ourKey);
    const moving = sides.mine.leaving.concat(sides.mine.arriving);
    const projected = projKey !== ctx.ourKey && moving.length > 0 && moving.every(r => r && r.values && finite(r.values[projKey]));
    const usProj = projected ? teamFit(sides.mine, ctx, projKey) : null;
    // Roster construction check (JEG-1108): both teams must pass.
    const myConstruction = rosterConstructionOk(sides.mine, ctx.shape, ctx.ourKey);
    const theirConstruction = rosterConstructionOk(sides.theirs, ctx.shape, ctx.marketKey);
    const constructionOk = myConstruction.ok && theirConstruction.ok;
    // Your DDF Value total rises at all (above the 0.05 display floor, not the noise floor; Jeremy, 2026-10-26) and
    // starters not worse. The noise floor still applies to the other team's side below.
    const yourTotalUp = us.net > NET_FLOOR;
    const yourStartersOk = us.starterDelta >= -NET_FLOOR;
    const yourValueOk = yourTotalUp && yourStartersOk;
    // Their Trade chart average change: within the noise floor or positive.
    const theirNet = them.net;
    const theirTau = them.tau;
    const theirOk = theirNet >= -theirTau;
    // Market supported: the Trade chart average says the other team's side is favorable (they gain). Any gain the page
    // shows (above the 0.05 display floor), not the noise floor (JEG-1187): the finder only lists trades you win on DDF
    // Value, so on real charts the other team's gain never cleared its noise floor and the label could not appear. The
    // noise floor stays where Jeremy put it (2026-10-25): the tolerance for a loss on their side of Natural fit.
    const marketSupported = theirNet > NET_FLOOR;
    // Natural: both sides pass the 1a predicate (JEG-1324), which adds both sides' projections to the tests above.
    const natural = naturalFit({yourValueOk, theirValueOk: theirOk, myConstruction, theirConstruction,
      usProjNet: projected ? usProj.net : null, themProjNet: projected ? viewNet(sides.theirs, ctx, projKey) : null});
    const isNatural = natural.ok;
    const label = isNatural ? "natural" : marketSupported ? "market" : "force";
    // Keep variant for backward compat; no projections variant now (simplified).
    const variant = label;
    const qualifier = null;
    const usServing = us;
    const fillsNeed = us.toward || them.toward;
    return {label, variant, qualifier, us, usProj, usServing, usOther, them, themOther, fillsNeed, projected,
      constructionOk, myConstruction, theirConstruction, yourValueOk, theirOk, marketSupported, natural};
  }
  const fitFmt = n => (Math.abs(n) < 0.05 ? "0.0" : (n > 0 ? "+" : "−") + Math.abs(n).toFixed(1));
  const VIEW_NAME = {ddf_value: "DDF Value", chart_avg: "the trade chart average", ddf_value_projections: "DDF Value (projections)"};
  function stateText(t) {
    const short = DEPTH_POS.filter(pos => t.depth[pos] && t.depth[pos].statusBefore === "under");
    const deep = DEPTH_POS.filter(pos => t.depth[pos] && t.depth[pos].statusBefore === "over");
    const parts = [];
    if (short.length) parts.push(`short at ${listJoin(short)}`);
    if (deep.length) parts.push(`deep at ${listJoin(deep)}`);
    return parts.length ? parts.join(" and ") : "balanced by position";
  }
  // The one-line reading of a fit, built from the numbers above. Both teams' depth and net appear in it.
  function fitText(fit) {
    const {us, them} = fit;
    const net = (t, who) => (t.up ? `${who} gain ${fitFmt(t.net)} on ${VIEW_NAME[t.key]}`
      : t.down ? `${who} lose ${Math.abs(t.net).toFixed(1)} on ${VIEW_NAME[t.key]}`
        : `${who} are level on ${VIEW_NAME[t.key]} (${fitFmt(t.net)}, inside the ${t.tau.toFixed(1)} noise floor)`);
    const depth = us.ready || them.ready
      ? ` ${us.ready ? `You are ${stateText(us)}` : ""}${us.ready && them.ready ? "; " : ""}${them.ready ? `${us.ready ? "they" : "They"} are ${stateText(them)}` : ""}.`
      : "";
    // JEG-1324: both sides' DDF Value (projections), the 1a test. A side that is not judged says so; never a 0.
    const proj = fit.natural || null;
    const projWhy = [];
    if (proj) {
      [[proj.us, "Your"], [proj.them, "Their"]].forEach(([side, who]) => {
        if (side.projections === false) projWhy.push(`${who} DDF Value (projections) falls ${Math.abs(side.projNet).toFixed(1)}.`);
      });
      if (proj.us.projections === null || proj.them.projections === null) projWhy.push("DDF Value (projections) not checked: a player in the trade has none, so it cannot be a Natural fit.");
    }
    if (fit.label === "natural") {
      const held = proj ? ` DDF Value (projections) holds for both teams (you ${fitFmt(proj.us.projNet)}, they ${fitFmt(proj.them.projNet)}).` : "";
      return `Natural fit: ${net(us, "you")} and ${net(them, "they")}. Roster construction works for both teams.${held}${depth}`;
    }
    if (fit.label === "market") {
      const why = [];
      if (!fit.constructionOk) {
        const issues = (fit.myConstruction.issues || []).concat(fit.theirConstruction.issues || []);
        why.push(`Roster construction issue${issues.length > 1 ? "s" : ""}: ${issues.join("; ")}.`);
      }
      if (!fit.yourValueOk) why.push(`Your DDF Value total does not rise (${fitFmt(us.net)}, starters ${fitFmt(us.starterDelta)}).`);
      why.push(...projWhy);
      return `Market supported: the trade charts favor them (${fitFmt(them.net)}).${why.length ? ` ${why.join(" ")}` : ""}${depth}`;
    }
    const why = [];
    if (!fit.constructionOk) {
      const issues = (fit.myConstruction.issues || []).concat(fit.theirConstruction.issues || []);
      if (issues.length) why.push(`Roster construction: ${issues.join("; ")}.`);
    }
    if (!fit.yourValueOk) {
      if (us.net <= NET_FLOOR) why.push(`Your DDF Value total does not rise (${fitFmt(us.net)}).`);
      else if (us.starterDelta < -NET_FLOOR) why.push(`Your starters drop ${Math.abs(us.starterDelta).toFixed(1)} on DDF Value.`);
    }
    if (them.net < -them.tau) why.push(`They lose ${Math.abs(them.net).toFixed(1)} on ${VIEW_NAME[them.key]}, outside the ${them.tau.toFixed(1)} noise floor.`);
    if (!fit.marketSupported) why.push(`The trade charts do not favor them (${fitFmt(them.net)}).`);
    why.push(...projWhy);
    const other = [[fit.usOther, "you", us], [fit.themOther, "they", them]].filter(([o, , own]) => !own.ok && o.up).map(([o, who]) => `Only on ${VIEW_NAME[o.key]} do ${who} gain (${fitFmt(o.net)}).`);
    return `Force fit: ${why.join(" ")}${other.length ? ` ${other.join(" ")}` : ""}${depth}`;
  }
  // Natural fits first, then market supported, then force fits; each tier keeps the incoming order (the edge ranking). No group
  // is changed or dropped, only moved. fitOf(group) -> a fit, or null (no fit: kept after the rest, in order).
  function tierOrder(labels) {
    return labels.map((label, i) => ({i, t: label ? FIT_TIER[label] : 3})).sort((a, b) => a.t - b.t || a.i - b.i).map(item => item.i);
  }
  function tierGroups(groups, fitOf) {
    return tierOrder(groups.map(g => { const f = fitOf(g); return f ? f.label : null; })).map(i => groups[i]);
  }

  // JEG-1019: the one-line answer to "is there a natural fit?", from the labels the groups already carry (no new math).
  // state: "missing" (a roster is empty), "pending" (rosters in, no search yet), "natural" (count groups), "none"
  // (no natural group: the trades are value-only or force fits, or none were found), "unjudged" (too few charts to judge fit).
  function fitHeadline(state, info) {
    const n = (info && info.count) || 0;
    if (state === "missing") return {text: "Add both rosters to see fit", link: null};
    if (state === "pending") return {text: "Press Find trades to see fit", link: null};
    if (state === "natural") {
      const charts = (info && info.chartsOnly) || 0, proj = (info && info.projectionsOnly) || 0;
      const parts = [charts ? `${charts} ${charts === 1 ? "is" : "are"} backed by the trade charts but not the projections` : "", proj ? `${proj} ${proj === 1 ? "is" : "are"} backed by the projections but not the trade charts` : ""].filter(Boolean);
      return {text: `Natural fit found: ${n} group${n === 1 ? "" : "s"}`, subtitle: parts.join("; ") || null, link: "Jump to the first natural group"};
    }
    if (state === "unjudged") return {text: "Fit not judged: not enough trade charts are available this week", link: null};
    return {text: `No natural fit between these rosters: ${info && info.reason ? info.reason : "the trades below are market supported or force fits"}`, link: null};
  }
  // JEG-1081 (tri-view, PR 3): the projections view beside DDF Value and the Trade chart average, display helpers (no math of
  // their own beyond differences of numbers the engine rows carry).
  // True when at least one row carries a projection value (otherwise the third column would read n/a all through).
  const hasProjections = rows => rows.some(r => r && r.values && finite(r.values[PROJECTIONS_KEY]));
  // The three-value tooltip of a score chip: "DDF Value: 24.3\nProjections: 22.1\nMarket: 20.8"; a missing view reads "no value".
  function chipTooltip(values) {
    const one = (label, v) => `${label}: ${finite(v) ? v.toFixed(1) : "no value"}`;
    const v = values || {};
    return [one("DDF Value", v.ddf), one("Projections", v.projections), one("Market", v.market)].join("\n");
  }
  // "Starters +4.2 DDF Value (+3.9 projections, +2.1 market)"; a view with no delta is left out of the parentheses.
  function deltaLine(what, deltas) {
    const sign = n => (Math.abs(n) < 0.05 ? "0.0" : (n > 0 ? "+" : "\u2212") + Math.abs(n).toFixed(1));
    const d = deltas || {};
    const others = [finite(d.projections) ? `${sign(d.projections)} projections` : "", finite(d.market) ? `${sign(d.market)} market` : ""].filter(Boolean);
    if (!finite(d.ddf)) return `${what}: no value`;
    return `${what} ${sign(d.ddf)} DDF Value${others.length ? ` (${others.join(", ")})` : ""}`;
  }
  // JEG-1130 (PMM doc, final naming 2026-10-26): one plain sentence per read, and no publisher names in a definition.
  const VIEW_TIPS = {ddf: "What a player is worth in your league: rooted in the trade charts, then adjusted for position weight and your league's rosters.",
    market: "What other managers will pay: the public trade market on one scale, before any position-weight adjustment. The common language for trade proposals.",
    projections: "The same read rooted in projections: projected points, adjusted for position weight and your league's rosters. Good for steady producers; it can underrate upside."};
  // Spec 4c; under a basis of the reader's own (Overrides) DDF Value is theirs, and the market's point scale follows it (spec 5b).
  function viewTip(id, basis) {
    const custom = Boolean(basis && !basis.isDefault);
    const name = custom ? basis.label : "";
    if (id === "ddf" && custom) return `Your basis, not the default DDF Value: ${name}, adjusted for your league's position weights. Change it on Overrides.`;
    if (id === "market" && custom) return `${VIEW_TIPS.market} Rescaled to ${basis.mode === "single" ? `${name}'s point scale` : `the point scale of ${name}`}.`;
    return VIEW_TIPS[id];
  }
  // JEG-1081 PR 7: what each fit label means, for the label's tooltip (spec 4c). Plain words, no abbreviations.
  const FIT_TIPS = {
    natural: "Natural fit: both rosters keep their starting slots filled, no bench player is forced into a starting spot, and no starter is lost without a starter coming back. Your DDF Value rises with your starters no worse. Their Trade chart average change is positive or any loss is within the source disagreement allowance. Neither team's DDF Value (projections) falls (a change under 0.05 counts as level), and every player in the trade has one. Fit totals weight bench value by the league's bench share.",
    market: "Market supported: their Trade chart average fit value rises by more than 0.05 points, using the league's bench share. A trade can earn this label while their starters lose value or either roster has construction issues; check the team-fit details.",
    force: "Force fit: a roster would be broken, a side loses, or the other team does not clear the bar on the Trade chart average."
  };
  const fitTip = variant => FIT_TIPS[variant] || FIT_TIPS.force;

  // ---------- JEG-894: a Find a trade search link ----------
  // A search is a roster pair, a package size and the two lineup ticks; the link carries all of them, plus the league
  // settings (the caller passes the page's own league query, so the reader's numbers are the sender's). Ids are the
  // engine player_key. The link is a plain URL fragment: it is never sent to a server.
  const FINDER_ID = /^[0-9A-Za-z_-]+$/;
  const FINDER_MAX_SIDE = 40;   // a crafted link cannot freeze the page
  const finderKeys = list => (list || []).map(p => (typeof p === "string" ? p : p && p.key))
    .filter(k => k !== undefined && k !== null && k !== "").map(k => encodeURIComponent(String(k))).join(",");
  // JEG-1328: the link also names the saved teams the two rosters were loaded from (ws = the league's id, mt / tt = the
  // teams' ids). They only matter to a reader with that same saved league; anywhere else the rosters stay a working copy.
  const FINDER_TEAM_ID = /^[0-9A-Za-z_-]{1,64}$/;
  // state: {mine, theirs, maxSize, keepMine, keepTheirs, guardrails, viableOnly, teams: {workspaceId, mineId, theirId}};
  // leagueQuery: the page's leagueLinkParts().join("&") (may be "").
  function encodeFinderHash(state, leagueQuery) {
    const s = state || {};
    const parts = [];
    const mine = finderKeys(s.mine);
    const theirs = finderKeys(s.theirs);
    if (mine) parts.push(`mine=${mine}`);
    if (theirs) parts.push(`theirs=${theirs}`);
    const size = Number(s.maxSize);
    parts.push(`size=${MAX_SIZE_CHOICES.includes(size) ? size : 2}`);
    parts.push(`km=${s.keepMine === false ? 0 : 1}`);
    parts.push(`kt=${s.keepTheirs === false ? 0 : 1}`);
    const g = s.guardrails || {};
    const backups = GUARDRAIL_POSITIONS.filter(pos => g.minBackups && g.minBackups[pos] > 0)
      .map(pos => `${pos}:${g.minBackups[pos]}`);
    if (backups.length) parts.push(`backups=${backups.join(",")}`);
    const positions = GUARDRAIL_POSITIONS.filter(pos => Array.isArray(g.protectedPositions) && g.protectedPositions.includes(pos));
    if (positions.length) parts.push(`protect=${positions.join(",")}`);
    if (g.minDdfEdge > 0) parts.push(`minEdge=${g.minDdfEdge}`);
    if (g.minUserLineupGain !== null && g.minUserLineupGain !== undefined) parts.push(`minMine=${g.minUserLineupGain}`);
    if (g.minTheirLineupGain !== null && g.minTheirLineupGain !== undefined) parts.push(`minTheirs=${g.minTheirLineupGain}`);
    if (s.viableOnly) parts.push("viable=1");
    const t = s.teams || {};
    const ids = [["mt", t.mineId], ["tt", t.theirId]].filter(([, id]) => FINDER_TEAM_ID.test(String(id || "")));
    if (FINDER_TEAM_ID.test(String(t.workspaceId || "")) && ids.length) parts.push(`ws=${t.workspaceId}`, ...ids.map(([k, id]) => `${k}=${id}`));
    const tail = String(leagueQuery || "").replace(/^[?&]+/, "");
    if (tail) parts.push(tail);
    return `#find-trade?${parts.join("&")}`;
  }
  // Pure: ids must look like keys, each side is capped, an id on both sides stays on "mine", `size` is 2/3/4 (else 2),
  // km/kt default on. knownKeys (a Set or array of engine keys) drops ids the engine no longer prices and counts them;
  // without it every well-formed id is kept. Returns {mine, theirs, size, keepMine, keepTheirs, dropped, unknown, both}.
  function decodeFinderHash(query, knownKeys) {
    // Accept a bare query ("mine=1"), a "?mine=1" query, or a full fragment ("#find-trade?mine=1").
    const raw = String(query || "");
    const params = new URLSearchParams(raw.includes("?") ? raw.slice(raw.indexOf("?") + 1) : raw.replace(/^[#?]+/, ""));
    const known = knownKeys ? new Set([...knownKeys].map(String)) : null;
    let dropped = 0;
    let unknown = 0;
    const readSide = name => {
      const out = [];
      const seen = new Set();
      String(params.get(name) || "").split(",").map(s => s.trim()).filter(Boolean).forEach(raw => {
        let id; try { id = decodeURIComponent(raw); } catch (error) { id = raw; }
        if (!FINDER_ID.test(id)) { dropped += 1; return; }
        if (seen.has(id)) return;
        if (known && !known.has(id)) { unknown += 1; return; }
        if (out.length >= FINDER_MAX_SIDE) { dropped += 1; return; }
        seen.add(id);
        out.push(id);
      });
      return out;
    };
    const mine = readSide("mine");
    const mineSet = new Set(mine);
    const theirsAll = readSide("theirs");
    const both = theirsAll.filter(k => mineSet.has(k));
    const theirs = theirsAll.filter(k => !mineSet.has(k));
    const size = Number(params.get("size"));
    const validMinimum = name => {
      if (!params.has(name)) return null;
      const raw = params.get(name);
      if (!/^(?:\d{1,3})(?:\.\d)?$/.test(raw)) return null;
      const n = Number(raw);
      return n <= 100 ? n : null;
    };
    const backups = {};
    (params.get("backups") || "").split(",").forEach(entry => {
      const match = /^(QB|RB|WR|TE):(\d{1,2})$/.exec(entry);
      if (match && Number(match[2]) <= 20) backups[match[1]] = Number(match[2]);
    });
    const teamId = name => (FINDER_TEAM_ID.test(params.get(name) || "") ? params.get(name) : null);
    const teams = {workspaceId: teamId("ws"), mineId: teamId("mt"), theirId: teamId("tt")};
    if (!teams.workspaceId || teams.mineId === teams.theirId) { teams.mineId = null; teams.theirId = null; }
    if (!teams.mineId && !teams.theirId) teams.workspaceId = null;
    return {mine, theirs, size: MAX_SIZE_CHOICES.includes(size) ? size : 2,
      keepMine: params.get("km") !== "0", keepTheirs: params.get("kt") !== "0", viableOnly: params.get("viable") === "1", teams, dropped, unknown, both: both.length,
      guardrails: {protectedPositions: GUARDRAIL_POSITIONS.filter(pos => (params.get("protect") || "").split(",").includes(pos)), minBackups: backups,
        minDdfEdge: validMinimum("minEdge") || 0, minUserLineupGain: validMinimum("minMine"), minTheirLineupGain: validMinimum("minTheirs")}};
  }

  // JEG-1328: which of a search link's saved teams (decoded teams plus the link's roster keys) label the rosters setSides
  // was given. A team counts only when every player given came from the link and the reader has that saved league and team.
  function linkTeamsFor(link, mine, theirs, workspace) {
    const none = {mineId: null, theirId: null};
    const fromLink = (list, keys) => list.every(p => keys.has(String(p.key)));
    if (!link || !workspace || workspace.id !== link.workspaceId) return none;
    if (!fromLink(mine, link.mineKeys) || !fromLink(theirs, link.theirKeys)) return none;
    const has = id => Boolean(id) && workspace.teams.some(team => team.id === id);
    return {mineId: has(link.mineId) ? link.mineId : null, theirId: has(link.theirId) ? link.theirId : null};
  }

  const api = {encodeFinderHash, decodeFinderHash, linkTeamsFor, benchBackups, startersAtGivenPositions, givenPositionsLine, viableGroups, viewTip, VIEW_TIPS, fitTip, FIT_TIPS, hasProjections, chipTooltip, deltaLine, fitHeadline, biggestImbalance, teamFit, tradeFit, naturalFit, projectionsHold, PROJ_FLOOR, FIT_VARIANTS, fitText, valueNoise, PROJECTION_KEYS, PROJECTIONS_KEY, tierGroups, tierOrder, benchWeight, FIT_Z, FIT_TIER, expectedDepth, rosterBalance, evalSentence, DEPTH_POS, USABLE_MIN, looksLikePage, isNotEvaluated, NOT_EVALUATED_POS, findTrades, evaluateCombo, collapseThrowIns, groupTrades, coreOf, pickStarters, lineupValue, rosterImpact, rosterConstructionOk, balanceCounts, viabilityLabel, withChartAverage, needLine, teamSummary, SUMMARY_ROWS, MARKET_KEY, lineupIssues, issueText, rosterGaps, matchNames, normName, parsePasted, subsets, subsetCount, OUR_KEY, CHART_KEYS, MIN_CHARTS, MAX_SIZE_CHOICES, MAX_SUBSETS, EXTRA_PLAYER_WEIGHT, LIMIT};
  // Stable identity comes from League, never the name (duplicate names are valid).
  function savedTeamChoices(workspace) {
    return workspace.teams.map((team, i) => ({id: team.id,
      label: `${team.name} · Team ${i + 1} · ${team.entries.length} players${workspace.myTeamId === team.id ? " · Your team" : ""}`}));
  }
  api.savedTeamChoices = savedTeamChoices;
  if (typeof module !== "undefined" && module.exports) { module.exports = api; return; }
  root.TradeValueFinder = api;

  // ---------- page (browser only) ----------
  const CHART_NAMES = {usatoday: "USA Today", fantasycalc: "FantasyCalc", fantasypros: "FantasyPros", cbs: "CBS Sports"};
  const $ = id => document.getElementById(id);
  const engine = () => root.TradeValueCurveControls;
  // mine / theirs: [{key, name, pos}]; sel: keys ticked for "Move selected"; undo: the rosters before the last swap or move (JEG-854).
  // src: the page text each side was read from (JEG-1020: re-read when the league settings change); removed: players the
// reader took off by hand, which a re-read must not bring back.
const S = {mine: [], theirs: [], maxSize: 2, keepMine: true, keepTheirs: true,
    guardrails: {protectedPositions: [], minBackups: {QB: 0, RB: 0, WR: 0, TE: 0}, minDdfEdge: 0, minUserLineupGain: null, minTheirLineupGain: null},
    sel: new Set(), undo: null, label: {mine: "", theirs: ""},
    src: {mine: null, theirs: null}, removed: new Set(), answered: new Set(), viableOnly: false};
  const renders = {};
  // JEG-1022: Waivers reuses the assessment helpers; its roster stays the workspace's marked team.
  const mineListeners = [];
  // JEG-1219: the matchup is view context. League/Waivers keep the marked roster; neither finder side writes it.
  const sharedStore = () => (root.TradeValueWorkspace ? root.TradeValueWorkspace.store : null);
  // JEG-1114: the settings this tab last applied, and whether an opened link's settings hold this tab. Another tab's
  // unrelated write (a rename, the star) carries the same saved settings and must not re-apply them or clear the results;
  // while a link holds the tab, no other-tab pull replaces its settings until the reader changes one here or loads a
  // league (a same-tab load or replace always reconciles).
  const settingsKey = settings => JSON.stringify(settings);
  let appliedSettings = null;
  let linkHolds = false;
  const savedSettings = () => {
    const W = root.TradeValueWorkspace;
    return W && W.store ? W.normalizeFinderSettings(W.store.get().ui.finderSettings) : null;
  };
  const applySettings = settings => {
    if (!settings) return;
    S.maxSize = settings.maxSize;
    S.keepMine = settings.keepMine;
    S.keepTheirs = settings.keepTheirs;
    S.guardrails = {protectedPositions: settings.protectedPositions.slice(), minBackups: {...settings.minBackups}, minDdfEdge: settings.minDdfEdge,
      minUserLineupGain: settings.minUserLineupGain, minTheirLineupGain: settings.minTheirLineupGain};
    const size = $("v2FindSize"); if (size) size.value = String(S.maxSize);
    const km = $("v2FindKeepMine"); if (km) km.checked = S.keepMine;
    const kt = $("v2FindKeepTheirs"); if (kt) kt.checked = S.keepTheirs;
    GUARDRAIL_POSITIONS.forEach(pos => { const box = $(`v2FindProtect${pos}`); if (box) box.checked = S.guardrails.protectedPositions.includes(pos); });
    GUARDRAIL_POSITIONS.forEach(pos => {
      const n = S.guardrails.minBackups[pos];
      const readout = $(`v2FindBackups${pos}`); if (readout) readout.textContent = String(n);
      const down = $(`v2FindBackups${pos}Down`); if (down) down.disabled = n === 0;
      const up = $(`v2FindBackups${pos}Up`); if (up) up.disabled = n === 20;
    });
    [["minDdfEdge", "v2FindMinEdge"], ["minUserLineupGain", "v2FindMinMine"], ["minTheirLineupGain", "v2FindMinTheirs"]].forEach(([key, id]) => {
      const input = $(id); if (input) input.value = S.guardrails[key] === null ? "" : String(S.guardrails[key]);
    });
    const folded = $("v2FindSummary"); if (folded && !folded.hidden) updateSummary();
  };
  const saveSettings = () => {
    const W = root.TradeValueWorkspace;
    if (!W || !W.store) return;
    const value = W.normalizeFinderSettings({...S.guardrails, maxSize: S.maxSize, keepMine: S.keepMine, keepTheirs: S.keepTheirs});
    linkHolds = false;
    appliedSettings = settingsKey(value);
    W.store.update(w => W.ops.setUi(w, {finderSettings: value}), "finder-settings");
  };
  let linkPending = false;   // JEG-894: a search link asked for a run once the rosters are in
  // The star is an initial default only. Explicit/manual/link context wins over subsequent workspace changes.
  let rosterCopy = null;   // {workspaceId, teamId, theirTeamId, active}
  const selectionKey = side => side === "mine" ? "teamId" : "theirTeamId";
  const pickerId = side => side === "mine" ? "v2FindSavedTeam" : "v2FindTheirSavedTeam";
  const reloadId = side => side === "mine" ? "v2FindReloadTeam" : "v2FindTheirReloadTeam";
  const pendingRosterInput = side => {
    const prefix = side === "mine" ? "v2FindMine" : "v2FindTheirs";
    return Boolean($(prefix + "Search")?.value.trim() || $(prefix + "Paste")?.value.trim()
      || $(prefix + "PasteResult")?.querySelector("button") || S[side].some(p => S.sel.has(p.key)));
  };
  const DRAFT_KEY = "ddf.v2.finder-roster-copy";
  const pristineDefault = () => Boolean(rosterCopy?.autoDefault && rosterCopy.initialRoster === JSON.stringify(S.mine)
    && !S.theirs.length && !S.src.mine && !S.src.theirs && !S.sel.size);
  function saveRosterCopy() {
    if (!rosterCopy) return;
    if (rosterCopy.autoDefault && !pristineDefault()) rosterCopy.autoDefault = false;
    if (rosterCopy.autoDefault) return;   // Only an engaged matchup is a persisted draft, not an unseen initial default.
    if (S.mine.length || S.theirs.length || S.src.mine || S.src.theirs) rosterCopy.active = true;
    if (!rosterCopy.active) return;   // An untouched empty view must not suppress a later initial starred-team default.
    try {
      root.sessionStorage.setItem(DRAFT_KEY, JSON.stringify({v: 1, ...rosterCopy, mine: S.mine, theirs: S.theirs,
        src: S.src, label: S.label, removed: [...S.removed], answered: [...S.answered]}));
    } catch (error) { /* Storage may be disabled or full; the working copy still works for this visit. */ }
  }
  function restoreRosterCopy() {
    try {
      const draft = JSON.parse(root.sessionStorage.getItem(DRAFT_KEY));
      const W = root.TradeValueWorkspace;
      if (!draft || draft.v !== 1 || typeof draft.workspaceId !== "string" || !Array.isArray(draft.mine) || !Array.isArray(draft.theirs)) return;
      rosterCopy = {workspaceId: draft.workspaceId, teamId: typeof draft.teamId === "string" ? draft.teamId : null,
        theirTeamId: typeof draft.theirTeamId === "string" ? draft.theirTeamId : null, active: true};
      S.mine = W.cleanEntries(draft.mine); S.theirs = W.cleanEntries(draft.theirs);
      ["mine", "theirs"].forEach(side => {
        const src = draft.src && draft.src[side];
        S.src[side] = src && typeof src.text === "string" ? {text: src.text, team: Number.isInteger(src.team) ? src.team : null} : null;
        S.label[side] = draft.label && typeof draft.label[side] === "string" ? draft.label[side] : "";
      });
      S.removed = new Set(Array.isArray(draft.removed) ? draft.removed.map(String) : []);
      S.answered = new Set(Array.isArray(draft.answered) ? draft.answered.map(String) : []);
    } catch (error) { /* Ignore invalid or unavailable session storage without writing to League. */ }
  }
  function updateSavedTeamPicker() {
    const store = sharedStore();
    if (!store) return;
    const ws = store.get();
    const choices = savedTeamChoices(ws);
    const sameLeague = rosterCopy && rosterCopy.workspaceId === ws.id;
    ["mine", "theirs"].forEach(side => {
      const select = $(pickerId(side)), note = $(pickerId(side) + "Note");
      if (!select || !note) return;
      const id = sameLeague && rosterCopy[selectionKey(side)];
      const otherId = sameLeague && rosterCopy[selectionKey(side === "mine" ? "theirs" : "mine")];
      const chosen = ws.teams.find(t => t.id === id);
      select.replaceChildren(el("option", {value: "", text: "Current roster"}),
        ...choices.map(t => {
          const option = el("option", {value: t.id, text: t.label});
          option.disabled = t.id === otherId;
          return option;
        }));
      // Keep a deleted ID visible: neither a new name nor a new league may redirect this copy to another team.
      if (id && !chosen) select.append(el("option", {value: id, text: "Previously selected team (no longer in this league)", disabled: ""}));
      select.value = id || "";
      select.disabled = !choices.length;
      const reload = $(reloadId(side));
      if (reload) reload.hidden = !chosen;
      const marked = store.getMyTeam();
      const suffix = side === "mine" ? (marked ? ` League and Waivers still use ${marked.name}, the marked Your team.` : " No team is marked as Your team in League.") : "";
      note.textContent = (!choices.length ? "No saved teams. Add teams on the League page. " : "")
        + (rosterCopy && !sameLeague ? "The saved league changed. Your working roster is kept; choose a team to load a copy from this league."
          : id && !chosen ? "That team is no longer in this league. Your working roster is kept; choose a saved team to load another copy."
          : "Working copy in this tab. Saved League rosters stay unchanged.") + suffix;
    });
  }
  function chooseSavedTeam(side, id) {
    const store = sharedStore(), ws = store && store.get();
    const team = ws && ws.teams.find(t => t.id === id);
    if (id && !team) { updateSavedTeamPicker(); return; }
    const sameLeague = rosterCopy && rosterCopy.workspaceId === ws.id;
    const otherKey = selectionKey(side === "mine" ? "theirs" : "mine");
    if (id && sameLeague && rosterCopy[otherKey] === id) {
      updateSavedTeamPicker(); arrangeSay("Choose different saved teams for the two sides."); return;
    }
    const prefix = side === "mine" ? "v2FindMine" : "v2FindTheirs";
    const input = $(prefix + "Search"), result = $(prefix + "PasteResult");
    // A partially typed query or unanswered paste choice cannot disappear just from changing a select.
    if (pendingRosterInput(side) && !root.confirm(`Load this roster and clear the unfinished input or player selections for ${side === "mine" ? "Your" : "Their"} roster? Your current rosters can be restored with Undo. Saved League teams stay unchanged.`)) {
      updateSavedTeamPicker(); return;
    }
    snapshot();
    const previousKeys = new Set(S[side].map(p => p.key));
    rosterCopy = {workspaceId: ws.id, teamId: sameLeague ? rosterCopy.teamId : null,
      theirTeamId: sameLeague ? rosterCopy.theirTeamId : null, active: true, [selectionKey(side)]: team ? team.id : null};
    if (team) {
      S[side] = team.entries.map(p => ({...p}));
      S.label[side] = team.name;
      S.src[side] = null;
    }
    if (input) input.value = "";
    const paste = $(prefix + "Paste"); if (paste) paste.value = "";
    if (result) result.replaceChildren();
    const searchResults = $(prefix + "Results");
    if (searchResults) { searchResults.replaceChildren(); searchResults.hidden = true; }
    // The explicit pick supersedes rosters from an opened link. Keep its league, value context and search controls,
    // but do not replay the old rosters over this tab's persisted working copy on reload or repeated navigation.
    if (location.hash.split("?")[0] === "#find-trade") {
      const params = new URLSearchParams(location.hash.split("?")[1] || "");
      params.delete("mine"); params.delete("theirs");
      const query = params.toString();
      root.history.replaceState(root.history.state, "", location.pathname + location.search + "#find-trade" + (query ? `?${query}` : ""));
    }
    previousKeys.forEach(key => S.sel.delete(key));
    renderBoth(); clearOutput();
    arrangeSay(team ? `Loaded a copy of ${team.name}. Saved teams and the marked Your team are unchanged. Undo restores the previous rosters.` : "Kept the current roster as a working copy. Saved teams stay unchanged.");
  }
  function savedTeamPicker(side) {
    const label = side === "mine" ? "Your saved League team" : "Their saved League team";
    const select = el("select", {id: pickerId(side), "aria-label": label, "aria-describedby": pickerId(side) + "Note"});
    select.addEventListener("change", () => chooseSavedTeam(side, select.value));
    const reload = el("button", {type: "button", class: "v2-link", id: reloadId(side), text: "Reload saved team", hidden: ""});
    reload.addEventListener("click", () => chooseSavedTeam(side, select.value));
    return el("div", {class: "v2-find-saved-team"},
      el("label", {class: "v2-field"}, el("span", {text: label}), select), reload,
      el("p", {class: "v2-meta", id: pickerId(side) + "Note", role: "status"}));
  }
  const pullMine = () => {
    const store = sharedStore();
    if (!store || (rosterCopy?.active && !pristineDefault()) || (S.mine.length && !pristineDefault())
      || S.theirs.length || pendingRosterInput("mine") || pendingRosterInput("theirs")) return;
    const ws = store.get(), team = ws.teams.find(t => t.id === ws.myTeamId);
    S.mine = team ? team.entries.map(p => ({...p})) : [];
    rosterCopy = {workspaceId: ws.id, teamId: team ? team.id : null, theirTeamId: null, active: Boolean(team),
      autoDefault: true, initialRoster: JSON.stringify(S.mine)};
    S.label.mine = team ? team.name : "";
    S.sel.clear(); renderBoth();
    if ($("v2FindOut")) clearOutput();
    mineListeners.forEach(fn => { try { fn(); } catch (error) { console.warn("Roster listener failed:", error); } });
  };
  const mineChanged = () => { saveRosterCopy(); updateSavedTeamPicker(); mineListeners.forEach(fn => { try { fn(); } catch (error) { console.warn("Roster listener failed:", error); } }); };
  api.ui = {depthContext, marketKeys, benchWeights, sideAssessment, assessmentTable, imbalanceText: w => imbalanceText(w), biggestImbalance,
    getMine: () => S.mine.map(p => ({...p})),
    setMine: list => { rosterCopy = {...(rosterCopy || {workspaceId: sharedStore().get().id}), teamId: null, active: true, autoDefault: false};
      S.mine = list.map(p => ({...p})); S.sel.clear(); renderBoth(); if ($("v2FindOut")) clearOutput(); },
    onMineChange: fn => { mineListeners.push(fn); },
    // JEG-1026: a DDF state (a pasted block or a link) sets both rosters at once. Undo puts back what was there; the page text each
    // side was read from is dropped (these players did not come from it), so a league-settings re-read does not overwrite them.
    getTheirs: () => S.theirs.map(p => ({...p})),
    setSides: (mine, theirs) => {
      snapshot();
      rosterCopy = {workspaceId: sharedStore().get().id, teamId: null, theirTeamId: null, active: true};
      adoptLinkTeams(mine, theirs);
      const have = new Set(mine.map(p => p.key));
      S.mine = mine.map(p => ({...p}));
      S.theirs = theirs.filter(p => !have.has(p.key)).map(p => ({...p}));
      S.src = {mine: null, theirs: null};
      S.label = {mine: "", theirs: ""};
      S.sel.clear();
      renderBoth();
      if ($("v2FindOut")) clearOutput();
      // JEG-894: a search link sets the rosters through here; run the search it asked for now that they are in.
      if (linkPending) { linkPending = false; if (S.mine.length && S.theirs.length) { if ($("v2FindSummary")) updateSummary(); run(); } }
      return {bothSides: theirs.filter(p => have.has(p.key)).map(p => p.name)};
    }};

  // JEG-894: the finder's own part of a search link. The rosters and the league settings arrive through the shared link
  // path (ddf-assist.js, which owns #find-trade?mine=..&theirs=..); this sets the package size and the two lineup ticks
  // and asks for the search to run as soon as setSides has the rosters in.
  function applyHash(params) {
    if (!params || location.hash.split("?")[0] !== "#find-trade") return null;
    const hasRosters = params.has("mine") || params.has("theirs");
    if (!hasRosters && !(rosterCopy && params.has("size"))) return null;
    const decoded = decodeFinderHash(params.toString(), null);
    S.maxSize = decoded.size;
    S.keepMine = decoded.keepMine;
    S.keepTheirs = decoded.keepTheirs;
    const linkSettings = root.TradeValueWorkspace.normalizeFinderSettings({...decoded.guardrails, maxSize: decoded.size,
      keepMine: decoded.keepMine, keepTheirs: decoded.keepTheirs});
    applySettings(linkSettings);
    const size = $("v2FindSize"); if (size) size.value = String(S.maxSize);
    const km = $("v2FindKeepMine"); if (km) km.checked = S.keepMine;
    const kt = $("v2FindKeepTheirs"); if (kt) kt.checked = S.keepTheirs;
    linkPending = hasRosters;
    // The opened link wins in this tab, across other tabs' writes. Like its rosters (JEG-1219), its settings stay this
    // tab's: nothing is written to the saved league.
    appliedSettings = settingsKey(linkSettings);
    linkHolds = true;
    return decoded;
  }
  // The "Copy link to this search" button: both rosters, the package size, the lineup ticks and the league settings.
  async function copyLink(button) {
    const note = $("v2FindShareNote");
    const say = text => { if (note) { note.hidden = false; note.textContent = text; } };
    const empty = !S.mine.length && !S.theirs.length ? "both rosters" : !S.mine.length ? "your roster" : !S.theirs.length ? "their roster" : "";
    if (empty) { say(`Add at least one player to ${empty} to make a link.`); return; }
    const league = root.TradeValueV2 && root.TradeValueV2.leagueQuery ? root.TradeValueV2.leagueQuery() : "";
    const teams = rosterCopy ? {workspaceId: rosterCopy.workspaceId, mineId: rosterCopy.teamId, theirId: rosterCopy.theirTeamId} : null;
    const hash = encodeFinderHash({mine: S.mine, theirs: S.theirs, maxSize: S.maxSize, keepMine: S.keepMine, keepTheirs: S.keepTheirs, guardrails: S.guardrails,
      viableOnly: S.viableOnly, teams}, league);
    const ov = root.DDFOverrides;
    const shared = ov && ov.shareLink ? ov.shareLink(hash) : {hash, dropped: false};
    const url = location.href.split("#")[0] + shared.hash;
    say("\u2713 Link copied. It opens this search with both rosters and these trade settings.");
    if (button) {
      if (!button.dataset.copyLabel) button.dataset.copyLabel = button.textContent;
      button.textContent = "Copied";
      clearTimeout(button.copyTimer);
      button.copyTimer = setTimeout(() => { button.textContent = button.dataset.copyLabel; }, 2000);
    }
    if (shared.dropped) say(ov.dropOverridesNote());
    try { await navigator.clipboard.writeText(url); }
    catch (error) { say(`Copy this link: ${url}`); }
  }
  // JEG-1328: a search link's viable-only tick and the saved teams its rosters came from. Each team is adopted when
  // setSides puts that link's rosters in (every player it is given came from the link), and only when this reader has
  // that saved league and the team in it; a later state with other rosters keeps the working copy unlabelled.
  let linkTeams = null;
  function adoptLinkTeams(mine, theirs) {
    const t = linkTeams;
    linkTeams = null;
    const picked = linkTeamsFor(t, mine, theirs, t && sharedStore() ? sharedStore().get() : null);
    if (picked.mineId) rosterCopy.teamId = picked.mineId;
    if (picked.theirId) rosterCopy.theirTeamId = picked.theirId;
  }
  api.applyHash = params => {
    const decoded = applyHash(params);
    linkTeams = decoded && decoded.teams.workspaceId && (params.has("mine") || params.has("theirs"))
      ? {...decoded.teams, mineKeys: new Set(decoded.mine), theirKeys: new Set(decoded.theirs)} : null;
    if (decoded) S.viableOnly = decoded.viableOnly;
    return decoded;
  };
  api.copyLink = copyLink;

  // JEG-892: the bye week (player-flags.js) on a player row; null when there is none.
  const flagsOf = row => (root.DDFPlayerFlags ? root.DDFPlayerFlags.node(row) : null);
  function el(tag, props, ...kids) {
    const node = document.createElement(tag);
    Object.entries(props || {}).forEach(([k, v]) => { if (k === "text") node.textContent = v; else node.setAttribute(k, v); });
    node.append(...kids.filter(Boolean));
    return node;
  }
  function setHeadline(state, info) {
    const box = $("v2FindFit");
    if (!box) return;
    const h = fitHeadline(state, info);
    box.dataset.state = state;
    box.replaceChildren(el("b", {text: h.text}));
    if (h.subtitle) box.append(" ", el("span", {class: "v2-find-headline-sub", text: h.subtitle}));
    if (h.link) {
      const jump = el("a", {href: "#v2FindFirstNatural", class: "v2-link", text: h.link});
      jump.addEventListener("click", event => {
        const target = $("v2FindFirstNatural");
        if (!target) return;
        event.preventDefault();
        target.scrollIntoView({block: "start", behavior: "auto"});
        target.focus({preventScroll: true});
      });
      box.append(" ", jump);
    }
  }
  const clearOutput = () => { const out = $("v2FindOut"); out.hidden = true; out.replaceChildren(); setHeadline(S.mine.length && S.theirs.length ? "pending" : "missing"); };

  // JEG-854: fixing which team is which must be one tap. Swap and Move change the rosters wholesale, so the shown
  // results are recomputed from the new rosters (never left standing from the old assignment); Undo restores the last one.
  function arrangeSay(text) { const p = $("v2FindArrangeNote"); if (p) p.textContent = text; }
  function updateArrange() {
    const undo = $("v2FindUndo");
    if (undo) undo.disabled = !S.undo;
    const clearBothButton = $("v2FindClearBoth");
    if (clearBothButton) clearBothButton.disabled = !S.mine.length && !S.theirs.length;
    ["mine", "theirs"].forEach(side => {
      const button = $(`v2Find${side[0].toUpperCase()}${side.slice(1)}MoveSel`);
      if (!button) return;
      const n = S[side].filter(p => S.sel.has(p.key)).length;
      button.disabled = !n;
      button.textContent = n ? `Move ${n} selected to the other team` : "Move selected to the other team";
    });
  }
  function renderBoth() { renders.mine && renders.mine(); renders.theirs && renders.theirs(); updateArrange(); updateSavedTeamPicker(); }
  function rerun() {
    const out = $("v2FindOut");
    const had = out && !out.hidden && out.childElementCount > 0;
    clearOutput();
    if (had) run();
  }
  function snapshot() { S.undo = {mine: S.mine.slice(), theirs: S.theirs.slice(), label: {...S.label}, src: {...S.src},
    rosterCopy: rosterCopy && {...rosterCopy}, removed: new Set(S.removed), answered: new Set(S.answered)}; }
  function afterArrange(text) {
    if (rosterCopy) { rosterCopy.autoDefault = false; rosterCopy.active = true; }
    S.sel.clear(); renderBoth(); rerun(); arrangeSay(text);
  }
  function swapTeams() {
    snapshot();
    if (rosterCopy) [rosterCopy.teamId, rosterCopy.theirTeamId] = [rosterCopy.theirTeamId, rosterCopy.teamId];
    [S.mine, S.theirs] = [S.theirs, S.mine];
    [S.label.mine, S.label.theirs] = [S.label.theirs, S.label.mine];
    [S.src.mine, S.src.theirs] = [S.src.theirs, S.src.mine];
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
  // JEG-1219: clear only this matchup's working rosters; League/Waivers keep their saved teams.
  function clearBoth() {
    if (!S.mine.length && !S.theirs.length) return;
    snapshot();
    S.mine = [];
    S.theirs = [];
    S.src = {mine: null, theirs: null};
    S.label = {mine: "", theirs: ""};
    afterArrange("Cleared both working rosters. Saved League teams stay unchanged. Undo puts them back.");
  }
  function undoArrange() {
    if (!S.undo) return;
    S.mine = S.undo.mine;
    S.theirs = S.undo.theirs;
    if (S.undo.label) S.label = {...S.undo.label};
    if (S.undo.src) S.src = {...S.undo.src};
    // Undoing a copy selection must not write an old snapshot over a team changed in another tab.
    rosterCopy = S.undo.rosterCopy || (rosterCopy ? {...rosterCopy, teamId: null, theirTeamId: null, active: true} : null);
    if (rosterCopy) { rosterCopy.autoDefault = false; rosterCopy.active = true; }
    if (S.undo.removed) S.removed = S.undo.removed;
    if (S.undo.answered) S.answered = S.undo.answered;
    S.undo = null;
    afterArrange("Undone.");
  }

  // ---------- JEG-853: a whole page pasted in (Jeremy, 2026-10-22: "control all, copy the whole page, drop the text in") ----------
  // roster-paste.js reads the page deterministically in the browser (no LLM, no network) against the engine's own rows.
  // A sure match (confidence 1: name, team and position agree) goes on the roster; a lesser one (nickname or
  // "D. Henry" form) waits for a tap; an unmatched line gets a one-tap search. Too few matches adds nothing unless asked.
  // A matchup page carries two teams: the user taps which is theirs; Swap teams (JEG-854) fixes a wrong pick.
  const MIN_MATCHED = 3;
  const MIN_SHARE = 0.5;
  const NAME_LIST_SHARE = 0.8;   // a pasted list of names: this share of its lines must be players, else it is not a roster
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
  // JEG-988: the engine prices no defense or kicker, so the parser leaves them unmatched. They are still roster players
  // (Jeremy: "don't make those null"): kept on the side as entries without an engine row, shown "Not evaluated", left out
  // of every sum. u: an unmatched line or import entry ({line | name, pos, team}).
  function keepNotEvaluated(side, unmatched) {
    const keptNames = [];
    const taken = new Set(S.mine.concat(S.theirs).map(p => p.key));
    (unmatched || []).filter(isNotEvaluated).forEach(u => {
      const name = cleanLine(u.line || u.name);
      const key = `x:${u.pos}:${u.team || normName(name)}`;
      if (!name || taken.has(key)) return;
      taken.add(key);
      S[side].push({key, name, pos: u.pos, team: u.team || "", slot: u.slot});
      keptNames.push(`${name} (${u.pos})`);
    });
    return keptNames;
  }
  // JEG-995: typed search also offers every defense and the kickers on a team now, by name, as the same unpriced entries a
  // paste keeps. The names come from window.TradeValueKDef (built from the Sleeper identity base, kdef-names.js); the engine
  // rows are never touched. A defense is keyed by team (as a paste keys it), a kicker by name.
  const teamCode = team => {
    const paste = window.DDFRosterPaste;
    return (paste && paste.normTeam ? paste.normTeam(team) : null) || String(team || "").toUpperCase();
  };
  function notEvaluatedChoices() {
    const data = window.TradeValueKDef || {};
    const choose = (list, pos) => (list || []).filter(item => item && item.name).map(item => {
      const team = teamCode(item.team);
      return {player_key: pos === "DEF" ? `x:DEF:${team}` : `x:K:${normName(item.name)}`, name: item.name, pos, team, notEvaluated: true};
    });
    return choose(data.defenses, "DEF").concat(choose(data.kickers, "K"));
  }
  // True when this choice is already on a roster: same key, or the same kicker name, or the same defense team (a pasted page
  // keys a kicker by team and a defense by its own wording).
  const alreadyOnRoster = (choice, onRosters) => onRosters.some(p => p.key === String(choice.player_key)
    || (isNotEvaluated(p) && p.pos === choice.pos && (choice.pos === "DEF" ? teamCode(p.team) === choice.team : normName(p.name) === normName(choice.name))));
  const keptNote = names => (names.length ? el("p", {class: "v2-meta v2-find-kept", text: `Kept, not evaluated (no value for defenses and kickers): ${names.join(", ")}.`}) : null);
  const evaluatedOnly = unmatched => (unmatched || []).filter(u => !isNotEvaluated(u));
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
  // JEG-988: the trade charts the engine says are available, and only with enough of them is there a Trade chart average.
  function marketKeys() {
    const C = engine();
    const info = C && C.getSourceInfo ? C.getSourceInfo() : [];
    const available = new Set(info.filter(item => item.available).map(item => item.key));
    const keys = CHART_KEYS.filter(key => available.has(key));
    return keys.length >= MIN_CHARTS ? keys : null;
  }
  // The two scores the search uses, shown on each roster row: DDF Value (fundamental, what you win by) and the Trade
  // chart average (market, what the other manager sees). A missing score reads "no value", never 0. Chips are the only
  // text that changes with the engine; they are read from the rows, no math of their own.
  function scoreChips(player, byKey, charts) {
    const row = byKey.get(player.key);
    if (isNotEvaluated(player) || !row) return null;
    const ddf = row.values ? row.values[OUR_KEY] : null;
    const avg = charts ? withChartAverage([row], charts)[0].values[MARKET_KEY] : null;
    const proj = row.values ? row.values[PROJECTIONS_KEY] : null;
    const tip = chipTooltip({ddf, projections: proj, market: avg});
    const chip = (kind, label, value) => el("span", {class: `v2-find-chip${finite(value) ? "" : " is-missing"}`, "data-kind": kind, title: tip, tabindex: "0", "aria-label": `${finite(value) ? value.toFixed(1) : "no value"} ${label}. ${tip.split("\n").join("; ")}`},
      el("span", {class: "v2-find-chip-value", text: finite(value) ? value.toFixed(1) : "no value"}), el("span", {class: "v2-find-chip-label", text: ` ${label}`}));
    // JEG-1059: the badge that marks a value the reader set, right after the DDF Value chip.
    const badge = window.DDFOverrides && window.DDFOverrides.flag ? window.DDFOverrides.flag(row) : null;
    return el("span", {class: "v2-find-chips"}, chip("ddf", "DDF Value", ddf), badge, chip("market", charts ? "Trade chart average" : "Trade chart average (too few charts)", avg));
  }
  // JEG-988: roster balance and the generated evaluation for one side, in both views: fundamentals (DDF Value) and market
  // pricing (Trade chart average, only with enough charts). Expected depth is the engine's own seats per team.
  function depthContext() {
    const C = engine();
    if (!C || !C.getAdjustmentWeights || !C.getRosterShape) return null;
    let allocation;
    try { allocation = C.getAdjustmentWeights().allocation; } catch (error) { return null; }
    const expected = expectedDepth(allocation, C.getState().teams);
    return expected ? {expected, shape: C.getRosterShape()} : null;
  }
  const STATUS_WORD = {under: "Under", over: "Over", ok: "OK"};
  // JEG-1019: ONE roster assessment for both teams, as a table. Each team in two views (DDF Value, Trade chart average):
  // players counted per position against the expected depth, the over / under flag, and the starter and bench value.
  // Nothing here is new math: lineupValue splits a view's best lineup into starters and bench, rosterBalance judges depth.
  function sideAssessment(side, list) {
    const ctx = depthContext();
    const players = list || S[side];   // JEG-1022: the Waivers tab assesses its own copy of "my roster"
    if (!ctx || !players.length) return null;
    const byKey = rowMap();
    const rows = players.map(p => byKey.get(p.key)).filter(Boolean);
    const slots = SLOT_KEYS.reduce((n, slot) => n + (ctx.shape[slot] || 0), 0);
    const have = rows.filter(r => DEPTH_POS.includes(r.pos)).length;
    const balance = rosterBalance(rows, ctx.expected, OUR_KEY, ctx.shape);
    if (!balance.ready) return {side, ready: false, slots, have};
    const charts = marketKeys();
    const marketRows = charts ? withChartAverage(rows, charts) : null;
    const view = (rowsOf, key) => (rowsOf ? {balance: rosterBalance(rowsOf, ctx.expected, key, ctx.shape), lineup: lineupValue(rowsOf, ctx.shape, key)} : null);
    return {side, ready: true, expected: ctx.expected, ddf: view(rows, OUR_KEY), market: view(marketRows, MARKET_KEY), projections: view(hasProjections(rows) ? rows : null, PROJECTIONS_KEY), kept: players.filter(isNotEvaluated),
      missing: lineupValue(rows, ctx.shape, OUR_KEY).unvalued.filter(r => !isNotEvaluated(r)).length};
  }
  const posSum = (list, pos, key) => list.filter(r => r.pos === pos).reduce((n, r) => n + r.values[key], 0);
  // The one imbalance of a view that is furthest from the expected range (the table shows the rest); null when balanced.
  function biggestImbalance(balance) {
    let worst = null;
    DEPTH_POS.forEach(pos => {
      const b = balance.positions[pos];
      const gap = b.status === "under" ? b.lo - b.have : b.status === "over" ? b.have - b.hi : 0;
      if (b.status !== "ok" && (!worst || gap > worst.gap)) worst = {pos, status: b.status, have: b.have, range: b.range, gap};
    });
    return worst;
  }
  const imbalanceText = w => `${w.pos} ${w.status === "over" ? "overweight" : "underweight"} (${w.have} counted, ${w.range} expected)`;
  const money = n => n.toFixed(1);
  function assessmentTable(a, b) {
    const sides = [a, b].filter(Boolean);   // JEG-1022: one team (Waivers) or both (Find a trade)
    // JEG-1081: DDF Value, Trade chart average, then DDF Value (projections) in a subdued, collapsible third group (hidden under 1024px until "Show projections").
    const basis = engine() && engine().getBasis ? engine().getBasis() : null;
    const custom = Boolean(basis && !basis.isDefault);
    const views = [{id: "ddf", label: custom ? `DDF Value (${basis.label})` : "DDF Value", key: OUR_KEY}, {id: "market", label: "Trade chart average", key: MARKET_KEY},
      {id: "projections", label: "DDF Value (projections)", key: PROJECTIONS_KEY, cls: "v2-find-proj-col"}];
    const cell = (text, props) => el("td", props || {}, text);
    const withCls = (v, props) => (v.cls ? {...props, class: `${(props && props.class) || ""} ${v.cls}`.trim()} : props);
    const head1 = el("tr", {}, el("th", {scope: "col", rowspan: "3", class: "v2-find-pos", text: "Position"}), el("th", {scope: "col", rowspan: "3", class: "v2-find-nowrap", text: "Expected"}),
      ...sides.map(x => el("th", {scope: "colgroup", colspan: "8", class: "v2-find-assess-team", text: x.side === "mine" ? "Your team" : "Their team"})));
    const head2 = el("tr", {}, ...sides.flatMap(() => [el("th", {scope: "colgroup", colspan: "2", text: "Players"}),
      ...views.map(v => el("th", withCls(v, {scope: "colgroup", colspan: "2", text: v.label, title: viewTip(v.id, basis)})))]));
    const head3 = el("tr", {}, ...sides.flatMap(() => [el("th", {scope: "col", text: "Counted"}), el("th", {scope: "col", text: "Flag"}),
      ...views.flatMap(v => ["Starters", "Bench"].map(t => el("th", withCls(v, {scope: "col", text: t}))))]));
    const flagOf = (x, pos) => {
      const f = x.ddf.balance.positions[pos].status;
      const m = x.market ? x.market.balance.positions[pos].status : f;
      return {text: STATUS_WORD[f] + (m !== f ? ` (market: ${STATUS_WORD[m].toLowerCase()})` : ""), cls: f !== "ok" ? `is-${f}` : (m !== "ok" ? `is-${m}` : "")};
    };
    const valueCells = (x, fn) => views.flatMap(v => {
      const part = x[v.id];
      return fn(part, v);
    });
    const body = DEPTH_POS.map(pos => el("tr", {"data-pos": pos}, el("th", {scope: "row", class: "v2-find-pos", text: pos}), cell(rangeText(a.expected[pos])),
      ...sides.flatMap(x => {
        const flag = flagOf(x, pos);
        return [cell(String(x.ddf.balance.positions[pos].have), {class: "num"}), cell(flag.text, {class: `${flag.cls} v2-find-flag`.trim()}),
          ...valueCells(x, (part, v) => (part
            ? [cell(money(posSum(part.lineup.starters, pos, v.key)), withCls(v, {class: "num", "data-cell": `${v.id}-starters`})), cell(money(posSum(part.lineup.bench, pos, v.key)), withCls(v, {class: "num", "data-cell": `${v.id}-bench`}))]
            : [cell("n/a", withCls(v, {class: "num"})), cell("n/a", withCls(v, {class: "num"}))]))];
      })));
    const benchRow = el("tr", {"data-row": "bench"}, el("th", {scope: "row", class: "v2-find-pos", text: "Bench subtotal"}), cell(""),
      ...sides.flatMap(x => [cell(String(x.ddf.lineup.bench.length), {class: "num"}), cell(""), ...valueCells(x, (part, v) => (part
        ? [cell("", withCls(v, {})), cell(money(part.lineup.benchValue), withCls(v, {class: "num", "data-cell": `${v.id}-bench-total`}))] : [cell("", withCls(v, {})), cell("n/a", withCls(v, {class: "num"}))]))]));
    const totalRow = el("tr", {"data-row": "total"}, el("th", {scope: "row", class: "v2-find-pos", text: "Total"}), cell(""),
      ...sides.flatMap(x => [cell(String(x.ddf.lineup.starters.length + x.ddf.lineup.bench.length), {class: "num"}), cell(""), ...valueCells(x, (part, v) => [
        part ? el("td", withCls(v, {colspan: "2", class: "num", "data-cell": `${v.id}-total`}), money(part.lineup.total)) : el("td", withCls(v, {colspan: "2", class: "num"}), "n/a")])]));
    const toggle = el("button", {type: "button", class: "v2-btn v2-find-proj-toggle", "aria-expanded": "false", text: "Show projections"});
    const wrap = el("div", {class: "v2-find-table-wrap"});
    // The team headings span the visible columns: 8 with the projections group showing (1024px and up, or opened), 6 without.
    const wide = typeof matchMedia === "function" ? matchMedia("(min-width: 1024px)") : null;
    const spans = () => { const n = (wide && wide.matches) || wrap.dataset.showProj === "1" ? "8" : "6"; wrap.querySelectorAll("th.v2-find-assess-team").forEach(th => th.setAttribute("colspan", n)); };
    toggle.addEventListener("click", () => {
      const on = wrap.dataset.showProj !== "1";
      wrap.dataset.showProj = on ? "1" : "0";
      toggle.setAttribute("aria-expanded", String(on));
      toggle.textContent = on ? "Hide projections" : "Show projections";
      spans();
    });
    if (wide && wide.addEventListener) wide.addEventListener("change", spans);
    wrap.append(toggle, el("table", {class: "v2-find-lineup v2-find-assess-table"},
      el("caption", {text: "Roster assessment: players counted against expected depth, and best-lineup value, starters and bench, by position"}),
      el("thead", {}, head1, head2, head3), el("tbody", {}, ...body, benchRow, totalRow)));
    spans();
    return wrap;
  }
  function renderAssessment() {
    const box = $("v2FindAssess");
    if (!box) return;
    const a = sideAssessment("mine");
    const b = sideAssessment("theirs");
    box.replaceChildren();
    box.hidden = true;
    if (!a && !b) return;
    box.hidden = false;
    const waiting = [a, b].filter(x => x && !x.ready);
    if (!a || !b || waiting.length) {
      const bits = [["mine", a], ["theirs", b]].map(([side, x]) => (!x ? `${SIDE_NAME[side]} has no players yet.` : !x.ready ? `${SIDE_NAME[side]} has ${x.have} of ${x.slots} players needed at QB, RB, WR and TE.` : ""));
      box.append(el("p", {class: "v2-meta", text: `The roster assessment shows once both rosters have at least as many QB, RB, WR and TE players as the league has starting slots. ${bits.filter(Boolean).join(" ")}`}));
      return;
    }
    box.append(assessmentTable(a, b));
    const notes = el("ul", {class: "v2-find-assess-notes"});
    [[a, "Your"], [b, "Their"]].forEach(([x, who]) => {
      const f = biggestImbalance(x.ddf.balance);
      const m = x.market ? biggestImbalance(x.market.balance) : null;
      let line = f ? `${who} biggest imbalance: ${imbalanceText(f)} in DDF Value.` : `${who} roster is balanced by position in DDF Value.`;
      if (m && (!f || m.pos !== f.pos || m.status !== f.status)) line += ` In Trade chart average: ${imbalanceText(m)}.`;
      else if (!m && x.market === null) line += " Trade chart average: not enough charts this week.";
      if (x.missing) line += ` ${plural(x.missing, "player")} with no DDF Value left out of the counts and sums.`;
      notes.append(el("li", {"data-note": "imbalance", text: line}));
    });
    const kept = a.kept.concat(b.kept);
    if (kept.length) notes.append(el("li", {"data-note": "not-evaluated", text: `Not evaluated, left out of every count and sum: ${[["Your team", a.kept], ["Their team", b.kept]].filter(([, l]) => l.length).map(([who, l]) => `${who} ${listJoin(l.map(p => p.pos))}`).join("; ")}.`}));
    box.append(notes);
  }
  // ---------- JEG-890: the team value card (display only; reads the rows, no math of its own) ----------
  const TS_LABEL = {starters: "Starters", bench: "Bench", unplaced: "No DDF Value", total: "Total", QB: "QB", RB: "RB", WR: "WR", TE: "TE"};
  const tsSeriesName = (key, id) => (id === "ddf" ? "DDF Value" : id === "market" ? "Trade chart average" : (CHART_NAMES[key] || key));
  // A cell: the number, or "—" when the row has players and none is priced (never 0), plus "incomplete" when a series
  // does not price every player in the row. The word is on the Total row; other rows carry a "*" with the names as a tip.
  // JEG-1246: a series with no cells (the Trade chart average with fewer than MIN_CHARTS charts) is "n/a" before any
  // cell is read. Starters and Bench carry a "*" while a player with no DDF Value cannot be placed in either.
  function tsCell(series, name) {
    if (series.available === false || !series.cells) return el("span", {class: "v2-find-ts-num is-unavailable", title: "Not enough charts this week", text: "n/a"});
    const cell = series.cells[name];
    const total = name === "total";
    const tip = `No value for ${cell.missing.join(", ")}`;
    if (cell.value === null) return el("span", {class: "v2-find-ts-incomplete", title: tip}, el("span", {class: "v2-find-ts-num is-missing", text: "—"}), el("span", {class: "v2-find-ts-inc", text: " incomplete"}));
    const num = el("span", {class: "v2-find-ts-num", text: cell.value.toFixed(1)});
    if (cell.complete && cell.unplaced && cell.unplaced.length) {
      const why = `Not placed, no DDF Value: ${cell.unplaced.join(", ")}`;
      return el("span", {class: "v2-find-ts-incomplete", "data-unplaced": "", title: why}, num, el("abbr", {class: "v2-find-ts-inc", title: why, text: "*"}));
    }
    if (cell.complete) return num;
    return el("span", {class: "v2-find-ts-incomplete", title: tip}, num,
      total ? el("span", {class: "v2-find-ts-inc", text: " incomplete"}) : el("abbr", {class: "v2-find-ts-inc", title: tip, text: "*"}));
  }
  function tsTable(sum, ids) {
    const head = el("tr", {}, el("th", {scope: "col", class: "v2-find-ts-row", text: "Row"}),
      ...ids.map(id => { const s = sum.series.find(x => x.id === id); return el("th", {scope: "col", class: "num", "data-series": id, text: tsSeriesName(s.key, id)}); }));
    const body = sum.rows.map(name => el("tr", {"data-row": name}, el("th", {scope: "row", class: "v2-find-ts-row", text: TS_LABEL[name]}),
      ...ids.map(id => { const s = sum.series.find(x => x.id === id); return el("td", {class: "num v2-find-ts-cell", "data-series": id}, tsCell(s, name)); })));
    return el("table", {class: "v2-find-ts-table"}, el("thead", {}, head), el("tbody", {}, ...body));
  }
  const tsBlock = (sum, label, ids, side) => el("div", {class: "v2-find-ts-team", "data-team": side},
    el("h4", {text: label}), tsTable(sum, ids));
  // The card: both rosters, once both are in. The two columns are DDF Value and the Trade chart average; the per-chart
  // columns sit behind "Show each chart". A held chart is named ("FantasyCalc not compared"), never silently dropped.
  function renderTeamSummary() {
    const box = $("v2FindTeamSummary");
    if (!box) return;
    const C = engine();
    if (!C || !C.getRosterShape || !S.mine.length || !S.theirs.length) { box.hidden = true; box.replaceChildren(); return; }
    const shape = C.getRosterShape();
    const info = C.getSourceInfo ? C.getSourceInfo() : [];
    const available = new Set(info.filter(i => i.available).map(i => i.key));
    const charts = CHART_KEYS.filter(k => available.has(k));
    const held = CHART_KEYS.filter(k => !available.has(k)).map(k => CHART_NAMES[k] || k);
    const byKey = rowMap();
    const rowsOf = list => list.map(p => byKey.get(p.key)).filter(Boolean);
    const mine = teamSummary(rowsOf(S.mine), shape, charts, OUR_KEY);
    const theirs = teamSummary(rowsOf(S.theirs), shape, charts, OUR_KEY);
    const kids = [el("h3", {text: "Team value summary"}),
      el("div", {class: "v2-find-ts-grid"}, tsBlock(mine, "Your team", ["ddf", "market"], "mine"), tsBlock(theirs, "Their team", ["ddf", "market"], "theirs"))];
    if (charts.length) {
      kids.push(el("details", {class: "v2-find-ts-charts"}, el("summary", {text: "Show each chart"}),
        el("div", {class: "v2-find-table-wrap"}, el("div", {class: "v2-find-ts-grid"},
          tsBlock(mine, "Your team", charts, "mine"), tsBlock(theirs, "Their team", charts, "theirs")))));
    } else {
      kids.push(el("p", {class: "v2-meta", text: "No trade chart is compared this week."}));
    }
    const notes = el("ul", {class: "v2-find-ts-notes"});
    if (held.length) notes.append(el("li", {"data-note": "held", text: `${held.map(name => `${name} not compared`).join(", ")}.`}));
    if (!mine.market) notes.append(el("li", {"data-note": "market", text: `Trade chart average: not enough charts this week (${charts.length} of ${MIN_CHARTS} needed).`}));
    [[mine, "Your"], [theirs, "Their"]].forEach(([sum, who]) => {
      if (sum.unplaced.length) notes.append(el("li", {"data-note": "unplaced", text: `${who} team: no DDF Value for ${listJoin(sum.unplaced)}, so Starters and Bench leave them out; their chart values are in the No DDF Value row and the Total.`}));
    });
    [[mine, "Your"], [theirs, "Their"]].forEach(([sum, who]) => {
      sum.series.filter(s => s.cells).forEach(s => {
        const total = s.cells.total;
        if (total.complete || !total.missing.length) return;
        notes.append(el("li", {"data-note": "incomplete", text: `${who} team, ${tsSeriesName(s.key, s.id)}: ${total.value === null ? "no listed player has a value" : "incomplete, a partial total"} (no value for ${listJoin(total.missing)}).`}));
      });
    });
    const notEval = [["Your", S.mine], ["Their", S.theirs]].map(([who, list]) => [who, list.filter(isNotEvaluated)]).filter(([, l]) => l.length);
    if (notEval.length) notes.append(el("li", {"data-note": "not-evaluated", text: `Not valued, left out of the totals: ${notEval.map(([who, l]) => `${who} ${listJoin(l.map(p => p.pos))}`).join("; ")}.`}));
    box.hidden = false;
    box.replaceChildren(...kids, notes);
  }

  // JEG-988: the engine's bench weights (the share of starts the bench takes, per position) and the fit context.
  function benchWeights() {
    const C = engine();
    const readout = C && C.getBenchShareReadout ? C.getBenchShareReadout() : null;
    const overall = readout && finite(readout.overall) ? readout.overall : (C && C.getBenchShare ? C.getBenchShare() : null);
    const weights = {overall: finite(overall) ? overall : 0};
    DEPTH_POS.forEach(pos => { if (readout && finite(readout[pos])) weights[pos] = readout[pos]; });
    return weights;
  }
  function fitContext(lineup) {
    const depth = depthContext();
    if (!lineup || !lineup.market || !depth) return null;
    return {shape: lineup.shape, expected: depth.expected, weights: benchWeights(), ourKey: OUR_KEY, marketKey: MARKET_KEY, chartKeys: lineup.market, z: FIT_Z};
  }
  // Rows of both teams carry DDF Value and the Trade chart average (lineup.*.market are the engine rows plus chart_avg).
  function fitFor(lineup, fitCtx, giveRows, recvRows) {
    const wide = rows => rows.map(r => lineup.byKey.get(String(r.player_key)) || r);
    const give = wide(giveRows);
    const recv = wide(recvRows);
    return tradeFit({mine: {roster: lineup.mine.market, leaving: give, arriving: recv}, theirs: {roster: lineup.theirs.market, leaving: recv, arriving: give}}, fitCtx);
  }
  const put = (box, ...kids) => box.append(...kids.filter(Boolean));
  const slotChip = slot => el("span", {class: "v2-find-slot", "data-slot": slotWord(slot), text: slotWord(slot)});
  const matchedList = added => el("ul", {class: "v2-find-matched"}, ...added.map(p =>
    el("li", {}, el("b", {text: p.name}), el("span", {class: "v2-meta", text: ` ${p.pos || ""} ${p.team || ""}`.trimEnd()}), slotChip(p.slot))));
  function unsureItem(side, p) {
    const li = el("li", {class: "v2-find-unsure", "data-unsure-id": String(p.id), "data-unsure-name": p.row.name});
    const yes = el("button", {type: "button", class: "v2-btn v2-find-confirm", text: "Yes, add", "aria-label": `Yes, add ${p.row.name}`});
    const no = el("button", {type: "button", class: "v2-btn v2-find-search-add", text: "No, search", "aria-label": `No, search for ${cleanLine(p.sourceLine)}`});
    li.append(el("span", {text: `Pasted “${cleanLine(p.sourceLine)}”: is this `}), el("b", {text: p.row.name}),
      el("span", {class: "v2-meta", text: ` ${p.row.pos || ""} ${p.row.team || ""}`.trimEnd()}), el("span", {text: "?"}), yes, no);
    yes.addEventListener("click", () => { S.answered.add(String(p.id)); const ok = addOne(side, p.row); li.replaceChildren(el("span", {text: ok ? `Added ${p.row.name}.` : `${p.row.name} is already on a roster.`})); });
    no.addEventListener("click", () => { S.answered.add(String(p.id)); li.remove(); searchFor(side, p.sourceLine); });
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
  // JEG-1010: for extraction results, show "Found N players" and the ignored-lines disclosure.
  function extractCountLine(res) {
    const ignored = (res.ignoredLines || []).length;
    return el("p", {class: `v2-find-paste-count ${res.matched ? "is-ok" : "is-bad"}`,
      text: `Found ${plural(res.matched, "player")}${ignored ? `, ignored ${plural(ignored, "line")}` : ""}.`});
  }
  function ignoredBlock(side, ignoredLines) {
    if (!ignoredLines || !ignoredLines.length) return null;
    const items = ignoredLines.slice(0, 50).map(line => {
      const search = el("button", {type: "button", class: "v2-btn v2-find-search-add", text: "Search", "aria-label": `Search for ${cleanLine(line)}`});
      search.addEventListener("click", () => searchFor(side, line));
      return el("li", {}, el("span", {class: "v2-meta", text: cleanLine(line)}), search);
    });
    return el("details", {class: "v2-find-ignored"}, el("summary", {text: `Show ${plural(ignoredLines.length, "ignored line")}`}),
      el("ul", {class: "v2-find-ignored-list"}, ...items));
  }

  // text: the pasted page; side: where it was pasted; box: the side's result panel; done(): the paste was used.
  function readPage(text, side, box, done) {
    box.replaceChildren();
    if (!String(text || "").trim()) { put(box, el("p", {class: "v2-meta", text: "Nothing pasted yet."})); return; }
    const res = parsePage(text);
    if (!res) { put(box, el("p", {class: "v2-meta", text: "Values are still loading. Try again in a moment."})); return; }
    res.sourceText = text;
    if (res.mode === "matchup" && res.teams && res.teams.length === 2) return readMatchup(res, side, box, done);
    if (!res.matched) {
      put(box, el("p", {class: "v2-find-paste-count is-bad", text: "No players recognised in that text. Nothing was added."}),
        el("p", {class: "v2-meta", text: "Paste a team page from any fantasy site (Ctrl+A, Ctrl+C on the page), or a list of player names. Search and add players by name below."}));
      return;
    }
    // JEG-1010: extraction results (mode "extract") always show what was found, no minimum-share gate.
    if (res.mode === "extract") {
      placeExtracted(side, res, box);
      done();
      return;
    }
    if (res.matched < MIN_MATCHED || res.matched / res.total < MIN_SHARE) {
      const anyway = el("button", {type: "button", class: "v2-btn", id: `${sideId(side)}PasteAnyway`, text: `Add these ${res.matched} anyway`});
      anyway.addEventListener("click", () => { box.replaceChildren(); placeTeam(side, res, box); done(); });
      put(box, countLine(res, true), el("p", {class: "v2-meta", text: "That is too few to trust, so nothing was added. Paste the whole team page, or search and add players by name below."}),
        anyway, ...unmatchedBlock(side, evaluatedOnly(res.unmatched)));
      return;
    }
    placeTeam(side, res, box);
    done();
  }
  function placeTeam(side, res, box) {
    const {added, onOther, unsure} = placePlayers(side, res.players, true);
    S.src[side] = {text: res.sourceText, team: null}; S.removed.clear(); S.answered.clear();
    const kept = keepNotEvaluated(side, res.unmatched);
    renderBoth();
    clearOutput();
    put(box, countLine(res),
      el("p", {class: "v2-meta", text: `${SIDE_NAME[side]} now has ${plural(S[side].length, "player")}.${onOther.length ? ` Left out because they are on the other roster: ${onOther.join(", ")}.` : ""}`}),
      matchedList(added), keptNote(kept), ...unsureBlock(side, unsure), ...unmatchedBlock(side, evaluatedOnly(res.unmatched)), benchNote(res));
  }
  // JEG-1010: place players from an extraction result (any source, noisy text).
  function placeExtracted(side, res, box) {
    const {added, onOther, unsure} = placePlayers(side, res.players, true);
    S.src[side] = {text: res.sourceText, team: null}; S.removed.clear(); S.answered.clear();
    const kept = keepNotEvaluated(side, res.unmatched);
    renderBoth();
    clearOutput();
    put(box, extractCountLine(res),
      el("p", {class: "v2-meta", text: `${SIDE_NAME[side]} now has ${plural(S[side].length, "player")}.${onOther.length ? ` Left out because they are on the other roster: ${onOther.join(", ")}.` : ""}`}),
      matchedList(added), keptNote(kept), ...unsureBlock(side, unsure), ...unmatchedBlock(side, evaluatedOnly(res.unmatched)), ignoredBlock(side, res.ignoredLines));
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
    S.src.mine = {text: res.sourceText, team: mineIdx}; S.src.theirs = {text: res.sourceText, team: 1 - mineIdx}; S.removed.clear(); S.answered.clear();
    const kept = res.teams.map((t, i) => keepNotEvaluated(sides[i], t.unmatched));
    renderBoth();
    clearOutput();
    box.replaceChildren();
    put(box, countLine(res),
      el("p", {class: "v2-find-assigned", text: `Your roster: ${teamLabel(res, mineIdx)} (${plural(S.mine.length, "player")}). Their roster: ${teamLabel(res, 1 - mineIdx)} (${plural(S.theirs.length, "player")}). Wrong way round? Use Swap teams above; Undo puts back what was there before.`}),
      ...res.teams.flatMap((t, i) => [el("h4", {text: `${teamLabel(res, i)}: ${SIDE_NAME[sides[i]].toLowerCase()}`}), matchedList(placed[i].added), keptNote(kept[i]),
        ...unsureBlock(sides[i], placed[i].unsure), ...unmatchedBlock(sides[i], evaluatedOnly(t.unmatched))]),
      foundNote(res), benchNote(res));
    arrangeSay(`Filled both rosters from the matchup page: ${teamLabel(res, mineIdx)} is yours.`);
    done();
  }

  function sideCard(side, title) {
    const id = sideId(side);
    const list = el("ul", {class: "v2-trade-players", id: `${id}Players`});
    const results = el("ul", {class: "v2-trade-results", id: `${id}Results`, hidden: ""});
    // JEG-988: one box per side. A textarea (one row, styled as a field) because a single-line input strips the
    // line breaks out of a pasted page. Its list opens inside .v2-find-search-wrap, so it sits directly under the box.
    const input = el("textarea", {id: `${id}Search`, rows: "1", placeholder: "Search a player, or paste a team page", autocomplete: "off",
      spellcheck: "false", "aria-controls": `${id}Results`, "aria-describedby": `${id}PasteHelp`});
    const label = el("label", {class: "v2-find-search-label"}, el("span", {class: "v2-sr", text: `Add players to ${title.toLowerCase()}: search by name, or paste a whole team page`}), input);
    const searchWrap = el("div", {class: "v2-find-search-wrap"}, label, results);
    const help = el("p", {class: "v2-meta v2-find-paste-help", id: `${id}PasteHelp`,
      text: "Type a name to search, or paste a team page: select all and copy on the page (Ctrl+A, Ctrl+C), then paste here. A matchup page fills both rosters. It stays on this device; nothing is sent anywhere."});
    const result = el("div", {class: "v2-find-paste-result", id: `${id}PasteResult`, role: "status", "aria-live": "polite"});
    const clear = el("button", {type: "button", class: "v2-link v2-find-clear", id: `${id}Clear`, text: "Clear", hidden: "", "aria-label": `Clear ${title.toLowerCase()}`});
    clear.addEventListener("click", () => {
      snapshot();
      const keys = new Set(S[side].map(p => p.key));
      S[side] = [];
      S.src[side] = null;
      S.label[side] = "";
      keys.forEach(k => S.sel.delete(k));
      result.replaceChildren();
      input.value = "";
      results.replaceChildren();
      results.hidden = true;
      afterArrange(`Cleared ${title.toLowerCase()}. Undo puts it back.`);
      input.focus();
    });
    const moveSel = el("button", {type: "button", class: "v2-btn v2-find-movesel", id: `${id}MoveSel`, text: "Move selected to the other team", disabled: ""});
    moveSel.addEventListener("click", () => moveKeys(S[side].filter(p => S.sel.has(p.key)).map(p => p.key)));
    const wrap = el("div", {class: "v2-trade-side v2-find-side", id}, el("div", {class: "v2-find-side-head"}, el("h3", {text: title}), clear),
      savedTeamPicker(side), searchWrap, help, result, list, moveSel, importBox());
    const render = () => {
      clear.hidden = !S[side].length;
      const byKey = rowMap();
      const charts = marketKeys();
      renderAssessment();
      renderTeamSummary();
      list.replaceChildren(...S[side].map(p => {
        const remove = el("button", {type: "button", class: "v2-link v2-find-remove", "aria-label": `Remove ${p.name}`, text: "Remove"});
        remove.addEventListener("click", () => { S[side] = S[side].filter(q => q.key !== p.key); S.sel.delete(p.key); S.removed.add(p.key); render(); updateArrange(); clearOutput(); });
        const pick = el("input", {type: "checkbox", class: "v2-find-pick", "aria-label": `Select ${p.name} to move`});
        pick.checked = S.sel.has(p.key);
        pick.addEventListener("change", () => { if (pick.checked) S.sel.add(p.key); else S.sel.delete(p.key); updateArrange(); });
        const move = el("button", {type: "button", class: "v2-link v2-find-move", "aria-label": `Move ${p.name} to the other team`, text: "Move"});
        move.addEventListener("click", () => moveKeys([p.key]));
        const badge = isNotEvaluated(p) ? el("span", {class: "v2-find-noteval", text: "Not evaluated"}) : null;
        return el("li", {class: "v2-find-row"}, el("label", {class: "v2-find-tick"}, pick), el("div", {}, el("b", {text: p.name}), el("span", {class: "v2-meta", text: p.pos ? ` ${p.pos}` : ""}, flagsOf(byKey[p.key] || p)), badge, scoreChips(p, byKey, charts)), move, remove);
      }));
      if (side === "mine") mineChanged();
      else saveRosterCopy();
    };
    renders[side] = render;
    // JEG-853 / JEG-988 / JEG-1010: text that is a whole page (looksLikePage) is read by roster-paste.js in the
    // browser. Format-specific parsers (Yahoo, ESPN) run first; the n-gram extractor (JEG-1010) handles everything
    // else. A matchup page fills both rosters; the user taps which team is theirs. A simple name-per-line list that
    // is 80%+ players is added directly.
    function consume(text) {
      input.value = "";
      results.replaceChildren();
      results.hidden = true;
      // Quick path: if parsePasted thinks it is a clean name list (80%+ players), add them directly.
      const lines = parsePasted(text);
      const { matched: nameMatches } = matchNames(lines, engine() ? engine().getAllRows() : []);
      if (nameMatches.length >= 2 && nameMatches.length >= NAME_LIST_SHARE * lines.length) {
        result.replaceChildren(el("p", {class: "v2-meta", text: apply(lines, "the list", false)}));
        return;
      }
      // Otherwise go through parsePage (which falls back to extractPlayers for unknown sites).
      readPage(text, side, result, () => {});
    }
    input.addEventListener("paste", event => {
      const text = event.clipboardData ? event.clipboardData.getData("text") : "";
      if (text && looksLikePage(text)) { event.preventDefault(); consume(text); }
    });
    input.addEventListener("keydown", event => { if (event.key === "Enter" && !event.shiftKey) event.preventDefault(); });
    // entries -> engine rows; replace (a team) or add (pasted names). A player on the other roster is not moved.
    // Returns the sentence that says what happened.
    function apply(entries, from, replace) {
      const rows = engine() ? engine().getAllRows() : [];
      const {matched, unmatched} = matchNames(entries, rows);
      const other = new Set(S[otherSide(side)].map(p => p.key));
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
      const kept = keepNotEvaluated(side, unmatched);
      render();
      updateArrange();
      clearOutput();
      const parts = [`Added ${added.length} player${added.length === 1 ? "" : "s"}${from ? ` from ${from}` : ""}.`];
      if (kept.length) parts.push(`Kept, not evaluated: ${kept.join(", ")}.`);
      if (onOther.length) parts.push(`Left out because they are on the other roster: ${onOther.join(", ")}.`);
      const rest = evaluatedOnly(unmatched);
      if (rest.length) parts.push(`Not matched (${rest.length}): ${rest.slice(0, 8).map(u => u.name).join(", ")}${rest.length > 8 ? ", …" : ""}.`);
      return parts.join(" ");
    }
    // Import: pasted names (JEG-1131: paste is the only league load). Names are matched to the engine's rows.
    function importBox() {
      const paste = el("textarea", {id: `${id}Paste`, rows: "4", placeholder: "One player per line", "aria-label": "Pasted player names"});
      const load = el("button", {type: "button", class: "v2-btn", id: `${id}Load`, text: "Add players"});
      const status = el("p", {class: "v2-meta", id: `${id}Status`, role: "status"});
      load.addEventListener("click", () => { status.textContent = apply(parsePasted(paste.value), "", false); paste.value = ""; });
      return el("details", {class: "v2-find-import"}, el("summary", {text: "Other ways to add players: a list of names"}),
        el("div", {class: "v2-find-import-body"}, paste, load, status));
    }
    window.TradeValueNameSearch.combobox(input, results);   // JEG-900
    input.addEventListener("input", () => {
      if (looksLikePage(input.value)) { consume(input.value); return; }
      const q = input.value.trim();
      results.replaceChildren();
      results.hidden = !q;
      if (!q || !engine()) return;
      const onRosters = S.mine.concat(S.theirs);
      // JEG-861: the page's one name matcher (reversed names, suffixes, typos), never a plain "contains". JEG-995: priced
      // players first, so on a tie they come before a defense or kicker.
      const hits = window.TradeValueNameSearch.search(engine().getAllRows().concat(notEvaluatedChoices()), q).slice(0, 8);
      if (!hits.length) results.append(el("li", {class: "is-empty v2-meta", text: `Can't find “${q}”. Check the spelling, or he may not have a value yet.`}));
      hits.forEach(row => {
        const key = String(row.player_key);
        const added = alreadyOnRoster(row, onRosters);
        const tag = row.notEvaluated ? el("span", {class: "v2-find-noteval", text: "Not evaluated"}) : null;
        const button = el("button", {type: "button"}, `${`${row.name} · ${row.pos || ""} ${row.team || ""}`.trim()}${added ? " ✓ Added" : ""}`, tag);
        if (added) button.disabled = true;
        button.addEventListener("click", () => {
          S[side].push(row.notEvaluated ? {key, name: row.name, pos: row.pos, team: row.team} : {key, name: row.name, pos: row.pos});
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

  const fmt = n => (Math.abs(n) < 0.05 ? "0.0" : (n > 0 ? "+" : "−") + Math.abs(n).toFixed(1));
  const names = rows => rows.map(r => r.name).join(" + ");

  function run() {
    const out = $("v2FindOut");
    out.hidden = false;
    out.replaceChildren();
    const note = text => out.append(el("p", {class: "v2-meta", text}));
    const C = engine();
    if (!C) return note("Values are still loading.");
    if (rosterCopy?.teamId && rosterCopy.teamId === rosterCopy.theirTeamId) {
      setHeadline("pending"); return note("Choose different saved teams for the two sides before finding trades.");
    }
    if (!S.mine.length || !S.theirs.length) { setHeadline("missing"); return note("Pick a trade partner. Paste in their roster and yours, and we'll find deals they'll like."); }
    const both = S.mine.filter(p => S.theirs.some(q => q.key === p.key));
    if (both.length) { setHeadline("pending"); return note(`Players on both rosters: ${both.map(p => p.name).join(", ")}. Remove them from one side before finding trades.`); }
    const all = C.getAllRows();
    const byKey = new Map(all.map(r => [String(r.player_key), r]));
    const rowsOf = list => list.map(p => byKey.get(p.key)).filter(Boolean);
    // JEG-819: use only charts the engine says are available (not held or missing), matching Compare and Targets.
    const sourceInfo = C.getSourceInfo ? C.getSourceInfo() : [];
    const availableKeys = new Set(sourceInfo.filter(item => item.available).map(item => item.key));
    const charts = CHART_KEYS.filter(key => availableKeys.has(key));
    if (!charts.length) { setHeadline("unjudged"); return note("No trade chart is available this week."); }
    if (charts.length < MIN_CHARTS) note(`Only ${charts.length} trade chart${charts.length === 1 ? " is" : "s are"} available this week. Not enough charts to judge acceptance.`);
    const shape = C.getRosterShape ? C.getRosterShape() : null;
    const mineRows = rowsOf(S.mine);
    const theirRows = rowsOf(S.theirs);
    // Roster sanity on what was typed in: a position the league starts that the roster does not cover.
    [["Your", mineRows], ["Their", theirRows]].forEach(([who, rows]) => {
      rosterGaps(rows, shape).forEach(g => note(`${who} roster has ${g.have} ${g.pos} for ${g.need} starting slot${g.need === 1 ? "" : "s"} in this league.`));
    });
    const res = findTrades(mineRows, theirRows, {chartKeys: charts, maxSize: S.maxSize, limit: 1e7,
      guardrails: {...S.guardrails, shape, mine: mineRows, theirs: theirRows, chartKeys: charts, ourKey: OUR_KEY},
      sanity: shape ? {shape, mine: mineRows, theirs: theirRows, keepMine: S.keepMine, keepTheirs: S.keepTheirs} : null});
    if (res.guardrailDropped) note(`${res.guardrailDropped} trade${res.guardrailDropped === 1 ? " was" : "s were"} left out by your protected positions or Advanced minimums.`);
    if (res.sanityDropped) note(`${res.sanityDropped} trade${res.sanityDropped === 1 ? "" : "s"} left out because ${res.sanityDropped === 1 ? "it leaves" : "they leave"} a starting lineup short at a position. Untick the boxes below to see ${res.sanityDropped === 1 ? "it" : "them"}.`);
    // JEG-988: defenses and kickers stay on the rosters and are not evaluated: they are named apart from players who merely lack a value.
    const notEval = S.mine.concat(S.theirs).filter(isNotEvaluated).length;
    if (notEval) note(`${notEval} ${notEval === 1 ? "defense or kicker is" : "defenses and kickers are"} kept on the rosters, not evaluated (no DDF Value or trade chart value; left out of every sum, not counted as 0).`);
    const skipped = res.mine.unpriced + res.theirs.unpriced;
    if (skipped > 0) note(`${skipped} player${skipped === 1 ? " has" : "s have"} no DDF Value and ${skipped === 1 ? "is" : "are"} left out, not counted as 0.`);
    if (res.mine.searched < res.mine.of || res.theirs.searched < res.theirs.of) {
      note(`Packages of up to ${S.maxSize} are searched among your top ${res.mine.searched} and their top ${res.theirs.searched} players by DDF Value.`);
    }
    if (!res.trades.length) {
      note(`No slam dunks with this team. No trade found where DDF Value says you win and ${charts.length === 1 ? "the one available chart says" : `at least ${res.minCharts} of ${charts.length} charts agree`} they break even or win. Try another team, or a larger package.`);
      setHeadline("none", {reason: "no trades were found"});
      return undefined;   // the roster assessment above stays: it is worth reading even when no trade is found
    }
    let groups = groupTrades(res.trades, {ourKey: res.ourKey});
    const lineup = lineupContext(mineRows, theirRows, charts, shape);
    const fitCtx = fitContext(lineup);
    // Natural fits first, then market supported, then force fits (JEG-1108); each tier keeps the edge ranking. Only the order changes.
    if (fitCtx) groups = tierGroups(groups, g => fitFor(lineup, fitCtx, g.best.give, g.best.receive));
    // JEG-885: at most 2 groups per received core player; the rest folded under "N more for <player>".
    const CORE_CAP = 2;
    const coreCount = new Map();
    const folded = new Map();   // core player_key -> count of hidden groups
    const capped = [];
    groups.forEach(g => {
      const ck = String(g.core.player_key);
      const n = (coreCount.get(ck) || 0) + 1;
      coreCount.set(ck, n);
      if (n <= CORE_CAP) { capped.push(g); }
      else { folded.set(ck, (folded.get(ck) || 0) + 1); }
    });
    groups = capped;
    const shownCount = Math.min(GROUP_LIMIT, groups.length);
    const fits = fitCtx ? groups.map(g => fitFor(lineup, fitCtx, g.best.give, g.best.receive)) : [];
    const naturalCount = fits.filter(f => f.label === "natural").length;
    const chartsOnly = fits.filter(f => f.variant === "natural-charts").length;
    const projectionsOnly = fits.filter(f => f.variant === "natural-projections").length;
    if (!fitCtx) setHeadline("unjudged");
    else if (naturalCount) setHeadline("natural", {count: naturalCount, chartsOnly, projectionsOnly});
    else setHeadline("none");
    const foldNote = folded.size ? ` ${[...folded.entries()].map(([ck, n]) => { const g = capped.find(g2 => String(g2.core.player_key) === ck) || groups.find(g2 => String(g2.core.player_key) === ck); return g ? `${n} more for ${g.core.name}` : `${n} more`; }).join("; ")}.` : "";
    note(`${res.total} trade${res.total === 1 ? "" : "s"} found in ${plural(capped.length + [...folded.values()].reduce((a, b) => a + b, 0), "group")}; ${groups.length > shownCount ? `the top ${shownCount} groups are listed` : "all are listed"}, ranked ${fitCtx ? "natural fits first, then market supported, then force fits, and within each by" : "by"} the best DDF Value edge in each, with simpler trades first.`
      + (res.foldedThrowIns ? ` ${plural(res.foldedThrowIns, "trade")} folded into a simpler one that only adds a player worth 0.0.` : "") + foldNote);
    const list = el("ol", {class: "v2-find-list", id: "v2FindList"});
    const ctx = {...res.ctx, maxSize: res.maxSize, lineup, fit: fitCtx};
    // JEG-1043: "Show viable offers only" filters the groups by their best package's viability label (JEG-1108) and
    // re-lists them; the ranking and the top-10 limit stay as they are.
    const viabOf = fitCtx ? g => viabilityFor(ctx, fitFor(lineup, fitCtx, g.best.give, g.best.receive), g.best.give, g.best.receive) : null;
    const tail = el("div", {class: "v2-find-list-tail"});
    const renderList = () => {
      const shown = S.viableOnly && viabOf ? viableGroups(groups, viabOf) : groups;
      const count = Math.min(GROUP_LIMIT, shown.length);
      list.replaceChildren(...shown.slice(0, count).map(g => groupCard(g, ctx)));
      const first = list.firstElementChild;
      if (naturalCount && first && first.dataset.findFit === "natural") { first.id = "v2FindFirstNatural"; first.tabIndex = -1; }
      tail.replaceChildren();
      if (!shown.length) {
        tail.append(el("p", {class: "v2-find-empty", id: "v2FindViableEmpty"}, el("b", {text: "No slam dunks with this team."}),
          " Your rosters fit a little too well. Try another team, or turn off \u201cShow viable offers only\u201d to see every offer."));
      } else if (shown.length > count) {
        const more = el("button", {type: "button", class: "v2-btn", id: "v2FindMoreGroups", text: `Show ${plural(shown.length - count, "more group")}`});
        more.addEventListener("click", () => { shown.slice(count).forEach(g => list.append(groupCard(g, ctx))); more.remove(); });
        tail.append(more);
      }
    };
    if (viabOf) {
      const viableCount = groups.filter(viabOf).length;
      const box = el("input", {type: "checkbox", id: "v2FindViableOnly"});
      box.checked = S.viableOnly;
      box.addEventListener("change", () => { S.viableOnly = box.checked; renderList(); });
      out.append(el("label", {class: "v2-find-viable-toggle", for: "v2FindViableOnly"}, box,
        ` Show viable offers only (${viableCount} of ${plural(groups.length, "group")})`));
    }
    renderList();
    out.append(list, tail);
  }

  // ---------- roster impact on the page (display only) ----------
  // ctx.lineup: both rosters in two points of view. DDF Value is the fundamental view; the Trade chart average (the
  // mean of the compared charts, as Compare's market read) is the market view, only with enough charts.
  function lineupContext(mineRows, theirRows, charts, shape) {
    if (!shape) return null;
    const market = charts.length >= MIN_CHARTS ? charts : null;
    const avg = rows => (market ? withChartAverage(rows, market) : null);
    const mineAvg = avg(mineRows);
    const theirAvg = avg(theirRows);
    const byKey = new Map();
    (mineAvg || []).concat(theirAvg || []).forEach(r => byKey.set(String(r.player_key), r));
    return {shape, market, projections: hasProjections(mineRows.concat(theirRows)), mine: {ddf: mineRows, market: mineAvg}, theirs: {ddf: theirRows, market: theirAvg}, byKey};
  }
  const VIEW_LABEL = {ddf: "DDF Value", market: "Trade chart average"};
  const viewKey = (view, ourKey) => (view === "ddf" ? ourKey : MARKET_KEY);
  const views = lineup => ["ddf"].concat(lineup.market ? ["market"] : []);
  // The team's rows leaving and arriving, in one view's rows.
  function sideRows(lineup, view, who, giveRows, recvRows) {
    const pickRows = rows => (view === "ddf" ? rows : rows.map(r => lineup.byKey.get(String(r.player_key)) || r));
    const leaving = pickRows(who === "mine" ? giveRows : recvRows);
    const arriving = pickRows(who === "mine" ? recvRows : giveRows);
    return {roster: lineup[who][view], leaving, arriving};
  }
  const signed = n => fmt(n);
  // Slot rows of one lineup: [{slot, row}] in slot order, empty slots as null.
  function slotList(l, shape) {
    const out = [];
    SLOTS.forEach(slot => {
      const n = (shape && shape[slot]) || 0;
      for (let i = 0; i < n; i++) out.push({slot: n > 1 ? `${slot}${i + 1}` : slot, row: l.slots[slot][i] || null});
    });
    return out;
  }
  function lineupTable(title, imp, shape, key) {
    const before = slotList(imp.before, shape);
    const after = slotList(imp.after, shape);
    // JEG-1059: the badge that marks a value the reader set, next to the player's DDF Value (our value only).
    const cell = row => {
      if (!row) return "empty";
      const text = `${row.name} ${row.values[key].toFixed(1)}`;
      const badge = key === OUR_KEY && window.DDFOverrides && window.DDFOverrides.flag ? window.DDFOverrides.flag(row) : null;
      return badge ? el("span", {}, text, badge) : text;
    };
    const val = row => (row ? row.values[key] : 0);
    const body = before.map((b, i) => el("tr", {}, el("th", {scope: "row", text: b.slot}), el("td", {}, cell(b.row)), el("td", {}, cell(after[i].row)),
      el("td", {text: signed(val(after[i].row) - val(b.row))})));
    body.push(el("tr", {}, el("th", {scope: "row", text: "Starters"}), el("td", {text: imp.before.starterValue.toFixed(1)}), el("td", {text: imp.after.starterValue.toFixed(1)}), el("td", {text: signed(imp.starterDelta)})));
    body.push(el("tr", {}, el("th", {scope: "row", text: "Bench"}), el("td", {text: imp.before.benchValue.toFixed(1)}), el("td", {text: imp.after.benchValue.toFixed(1)}), el("td", {text: signed(imp.benchDelta)})));
    return el("div", {class: "v2-find-table-wrap"}, el("table", {class: "v2-find-lineup"}, el("caption", {text: title}),
      el("thead", {}, el("tr", {}, ...["Slot", "Before", "After", "Change"].map(h => el("th", {scope: "col", text: h})))), el("tbody", {}, ...body)));
  }
  // The block inside one group card; update() re-reads the current selection.
  function impactBlock(ctx) {
    const node = el("div", {class: "v2-find-impact"});
    const lines = el("div", {class: "v2-find-impact-lines"});
    const detailsBody = el("div", {class: "v2-find-impact-body"});
    const details = el("details", {class: "v2-find-impact-details"}, el("summary", {text: "Show lineup details"}), detailsBody);
    const more = el("button", {type: "button", class: "v2-link v2-find-impact-more", "aria-expanded": "false", text: "Show other views"});
    more.addEventListener("click", () => {
      const on = node.dataset.expanded !== "1";
      node.dataset.expanded = on ? "1" : "0";
      more.setAttribute("aria-expanded", String(on));
      more.textContent = on ? "Hide other views" : "Show other views";
    });
    node.append(lines, more, details);
    return {node, update: (giveRows, recvRows) => {
      const lineup = ctx.lineup;
      const ourKey = ctx.ourKey;
      lines.replaceChildren();
      detailsBody.replaceChildren();
      [["mine", "You"], ["theirs", "They"]].forEach(([who, name]) => {
        const imps = {};
        views(lineup).forEach(view => {
          const side = sideRows(lineup, view, who, giveRows, recvRows);
          imps[view] = rosterImpact(side.roster, side.leaving, side.arriving, lineup.shape, viewKey(view, ourKey));
        });
        const parts = views(lineup).map(view => `${VIEW_LABEL[view]} ${imps[view].before.starterValue.toFixed(1)} → ${imps[view].after.starterValue.toFixed(1)} (${signed(imps[view].starterDelta)})`);
        const marketNote = lineup.market ? "" : " Trade chart average: not enough charts.";
        lines.append(el("p", {class: "v2-meta v2-find-impact-line"}, el("span", {class: "v2-find-who", text: `${name}: `}), `best starting lineup ${parts.join("; ")}.${marketNote}`),
          el("p", {class: "v2-meta v2-find-need"}, `${who === "mine" ? "Your" : "Their"} starters by position: ${needLine(imps.ddf)}.`));
        // JEG-1043: the starters at each position this side gives up, before → after (DDF Value lineup).
        const given = startersAtGivenPositions(imps.ddf, sideRows(lineup, "ddf", who, giveRows, recvRows).leaving);
        if (given.length) lines.append(el("p", {class: "v2-meta v2-find-given", "data-line": "given"},
          `${who === "mine" ? "Your starters at the positions you give up" : "Their starters at the positions they give up"}: ${givenPositionsLine(given)}.`));
        // JEG-1081: the same trade in the other views, one line each for starters and bench (hidden on a phone until expanded).
        const own = sideRows(lineup, "ddf", who, giveRows, recvRows);
        const projImp = hasProjections(own.roster.concat(own.arriving)) ? rosterImpact(own.roster, own.leaving, own.arriving, lineup.shape, PROJECTIONS_KEY) : null;
        const delta = field => ({ddf: imps.ddf[field], projections: projImp ? projImp[field] : null, market: imps.market ? imps.market[field] : null});
        lines.append(el("p", {class: "v2-meta v2-find-impact-secondary", "data-line": "secondary"}, `${deltaLine("Starters", delta("starterDelta"))}. ${deltaLine("Bench", delta("benchDelta"))}.`));
        views(lineup).forEach(view => detailsBody.append(lineupTable(`${who === "mine" ? "Your" : "Their"} best lineup, ${VIEW_LABEL[view]}`, imps[view], lineup.shape, viewKey(view, ourKey))));
        const missing = imps.ddf.before.unvalued.filter(r => !isNotEvaluated(r)).length;
        if (missing) detailsBody.append(el("p", {class: "v2-meta", text: `${plural(missing, "player")} on ${who === "mine" ? "your" : "their"} roster ${missing === 1 ? "has" : "have"} no value and ${missing === 1 ? "is" : "are"} left out of the lineup.`}));
      });
    }};
  }

  // One group: the player you receive, the best package for him preselected, side players selectable.
  // Each toggle re-judges the package with evaluateCombo, the function the search itself uses.
  const GROUP_LIMIT = 10;
  // JEG-1108 / JEG-1043: the viability label of one package (null when it is not viable or cannot be judged).
  function viabilityFor(ctx, fit, giveRows, recvRows) {
    const lineup = ctx.lineup;
    const mineAvg = lineup && lineup.mine ? lineup.mine.market || lineup.mine.ddf : null;
    const theirAvg = lineup && lineup.theirs ? lineup.theirs.market || lineup.theirs.ddf : null;
    return fit && mineAvg && theirAvg && lineup.shape ? viabilityLabel(fit, mineAvg, theirAvg, giveRows, recvRows, lineup.shape, ctx.ourKey, ctx.chartKeys || []) : null;
  }
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
    const fitLine = el("p", {class: "v2-find-fit", hidden: ""});
    const open = el("a", {class: "v2-link", text: "Open in Compare a trade"});
    const li = el("li", {class: "v2-find-group", "data-group": group.heavy.map(keyOf).join(",")});
    const target = el("span", {class: "v2-find-target"});
    // JEG-1059: the badge that marks a value the reader set, next to the DDF Value number.
    const coreBadge = window.DDFOverrides && window.DDFOverrides.flag ? window.DDFOverrides.flag(group.core) : null;
    target.append(el("span", {class: "v2-find-target-label", text: "Target: "}), el("span", {class: "v2-find-target-name", text: names(group.heavy)}),
      el("span", {class: "v2-meta"}, ` ${[group.core.pos, group.core.team].filter(Boolean).join(" · ")} · ${valueText(group.core, ourKey)}`, coreBadge, " DDF Value", flagsOf(group.core)));
    const boxes = [];
    const sideSet = (title, rows, sel, fixed) => {
      const box = el("fieldset", {class: "v2-find-side-pick"}, el("legend", {text: title}));
      rows.forEach(r => {
        const input = el("input", {type: "checkbox", "data-key": keyOf(r), "aria-label": `Include ${r.name} (value ${valueText(r, ourKey)})`});
        input.checked = sel.has(keyOf(r));
        input.defaultChecked = input.checked;   // JEG-1020: a settings change keeps only the ticks the reader changed
        if (fixed) input.disabled = true;
        input.addEventListener("change", () => { if (input.checked) sel.add(keyOf(r)); else sel.delete(keyOf(r)); refresh(); });
        // JEG-1059: the badge that marks a value the reader set, next to the DDF Value number.
        const badge = window.DDFOverrides && window.DDFOverrides.flag ? window.DDFOverrides.flag(r) : null;
        const label = el("label", {class: "v2-find-pick-row"}, input, el("span", {text: `${r.name} `}), el("span", {class: "v2-meta"}, `(${valueText(r, ourKey)}`, badge, " DDF Value)", flagsOf(r)));
        box.append(label);
        if (!fixed) boxes.push({input, row: r, sel, side: title});
      });
      return box;
    };
    const selectable = group.giveCandidates.length > 1 || group.receiveSide.length > 0;
    const giveBox = selectable ? sideSet("You give", group.giveCandidates, giveSel, false) : null;
    const recvBox = group.receiveSide.length ? sideSet("You also receive (core stays)", group.receiveSide, recvSel, false) : null;
    const capNote = el("span", {class: "v2-meta v2-find-cap", hidden: ""});
    const impact = ctx.lineup ? impactBlock(ctx) : null;
    li.append(...[target, tradeLabel, meta, fitLine, notes, impact && impact.node, giveBox, recvBox, capNote, open].filter(Boolean));

    function refresh() {
      const giveRows = group.giveCandidates.filter(r => giveSel.has(keyOf(r))).sort(order);
      const recvRows = group.heavy.concat(group.receiveSide.filter(r => recvSel.has(keyOf(r)))).sort(order);
      // Any size can be ticked (Jeremy 2026-10-23); only the last player given is kept. A package larger than the
      // searched size is labelled, and its math is still exact (evaluateCombo).
      boxes.forEach(b => { b.input.disabled = b.sel === giveSel && b.input.checked && giveSel.size <= 1; });
      const larger = giveRows.length > ctx.maxSize || recvRows.length > ctx.maxSize;
      capNote.hidden = !larger;
      capNote.textContent = larger ? `Larger package than searched: you searched up to ${ctx.maxSize}-for-${ctx.maxSize}, this is ${giveRows.length}-for-${recvRows.length}. The numbers below are exact, but the search did not look at packages this big.` : "";
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
      if (!e.passes.charts) warn.push(`Only ${e.rivalOkCount} of ${e.pricedCharts} charts have them winning or even, so they may say no.`);
      if (!e.passes.lineup) warn.push("It leaves a starting lineup short at a position.");
      if (e.passes.guardrails === false) warn.push("It breaks your protected positions or Advanced minimums.");
      const same = group.trades.find(t => idOf(t) === `${giveRows.map(r => r.player_key)}|${recvRows.map(r => r.player_key)}`);
      const throwIns = same && same.throwIns ? [].concat(same.throwIns.give, same.throwIns.receive) : [];
      // JEG-1059: the badge that marks a value the reader set, next to the throw-in's DDF Value.
      const noteKids = [];
      if (warn.length) noteKids.push(`${warn.join(" ")}`);
      if (throwIns.length) {
        if (warn.length) noteKids.push(" ");
        noteKids.push("Can add ");
        throwIns.forEach((r, i) => {
          if (i) noteKids.push(", ");
          noteKids.push(`${r.name} (${valueText(r, ourKey)}`);
          const badge = window.DDFOverrides && window.DDFOverrides.flag ? window.DDFOverrides.flag(r) : null;
          if (badge) noteKids.push(badge);
          noteKids.push(")");
        });
        noteKids.push(" as a throw-in.");
      }
      if (same && same.addedThrowIns) {
        if (noteKids.length) noteKids.push(" ");
        noteKids.push("Includes ");
        same.addedThrowIns.forEach((t, i) => {
          if (i) noteKids.push(", ");
          noteKids.push(`${t.row.name} (${valueText(t.row, ourKey)}`);
          const badge = window.DDFOverrides && window.DDFOverrides.flag ? window.DDFOverrides.flag(t.row) : null;
          if (badge) noteKids.push(badge);
          noteKids.push(")");
        });
        noteKids.push(` as ${same.addedThrowIns.length === 1 ? "a throw-in" : "throw-ins"}, so both teams trade the same number of players.`);
      }
      notes.replaceChildren(...noteKids);
      notes.classList.toggle("is-warn", warn.length > 0);
      if (impact) impact.update(giveRows, recvRows);
      const fit = ctx.fit ? fitFor(ctx.lineup, ctx.fit, giveRows, recvRows) : null;
      fitLine.hidden = !fit;
      if (fit) {
        const text = fitText(fit);
        const cut = text.indexOf(": ");
        // JEG-1108: viability label alongside fit.
        const FIT_LABEL = {natural: "Natural fit", market: "Market supported", force: "Force fit"};
        const VIAB_LABEL = {High: "High viability", "Med-High": "Medium-high viability", Medium: "Medium viability"};
        const viab = viabilityFor(ctx, fit, giveRows, recvRows);
        li.dataset.findViable = viab || "";
        const viabSuffix = viab ? ` · ${VIAB_LABEL[viab] || viab}` : "";
        fitLine.replaceChildren(el("b", {text: `${FIT_LABEL[fit.label] || text.slice(0, cut + 1)}${viabSuffix}:`}), ` ${text.slice(cut + 2)}`);
        fitLine.dataset.fit = fit.label;
        fitLine.dataset.fitVariant = fit.variant;
        fitLine.title = fitTip(fit.variant);
        li.dataset.findFit = fit.label;
        li.dataset.findFitVariant = fit.variant;
      }
      open.setAttribute("href", `v2/#compare-trade?give=${ids(giveRows)}&get=${ids(recvRows)}`);
      li.dataset.findEdge = String(e.edge);
    }
    refresh();
    return li;
  }

  // ---------- JEG-972: collapsible roster input ----------
  // After every Find trades press the roster input folds into one summary row per team (name, first three players,
  // position counts); "Edit rosters" opens it again. The package size, lineup boxes and Find button stay visible.
  // JEG-1237: the protected-position and bench-backup settings fold with it, read back as one line in the summary, so
  // the headline and results start on the first screen again; Advanced trade minimums stays its own closed disclosure.
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
  function guardrailText() {
    const g = S.guardrails;
    const parts = [];
    if (g.protectedPositions.length) parts.push(`protecting ${g.protectedPositions.join(", ")}`);
    const backups = GUARDRAIL_POSITIONS.filter(pos => g.minBackups[pos] > 0).map(pos => `${pos} ${g.minBackups[pos]}`);
    if (backups.length) parts.push(`minimum bench backups ${backups.join(", ")}`);
    return `Trade settings: ${parts.length ? parts.join("; ") : "no protected positions or bench backup minimums"}`;
  }
  function updateSummary() {
    const box = $("v2FindSummary");
    if (!box) return;
    ["mine", "theirs"].forEach(side => {
      const t = summaryText(S[side]);
      const node = $(`${sideId(side)}Summary`);
      node.replaceChildren(el("b", {text: S.label[side] ? `${SIDE_NAME[side]}: ${S.label[side]}` : SIDE_NAME[side]}), el("span", {class: "v2-find-sum-names", text: t.names}), el("span", {class: "v2-meta", text: t.counts}));
    });
    const rails = $("v2FindGuardrailSummary");
    if (rails) rails.textContent = guardrailText();
    $("v2FindEdit").setAttribute("aria-label", `Edit rosters and trade settings: your roster has ${plural(S.mine.length, "player")}, their roster has ${plural(S.theirs.length, "player")}`);
  }
  function setCollapsed(collapsed, focus) {
    const input = $("v2FindInput");
    const summary = $("v2FindSummary");
    const edit = $("v2FindEdit");
    if (!input || !summary) return;
    if (collapsed) updateSummary();
    input.hidden = collapsed;
    const rails = $("v2FindGuardrails");
    if (rails) rails.hidden = collapsed;
    summary.hidden = !collapsed;
    edit.setAttribute("aria-expanded", String(!collapsed));
    if (focus === "input") { const first = $("v2FindMineSearch"); if (first) first.focus(); }
    else if (focus === "edit") edit.focus();
  }
  const hasResults = () => { const out = $("v2FindOut"); return Boolean(out) && !out.hidden && out.childElementCount > 0; };
  function findPressed() {
    if (rosterCopy) { rosterCopy.autoDefault = false; rosterCopy.active = true; saveRosterCopy(); }
    run();
    if (!S.mine.length || !S.theirs.length) return;
    setCollapsed(true);
    const out = $("v2FindOut");
    const headline = $("v2FindFit");
    if (headline && headline.scrollIntoView && root.innerWidth < 768) headline.scrollIntoView({block: "start", behavior: "instant"});
  }

  // ---------- JEG-1020: the league settings changed (Your league applies live) ----------
  // Re-read the stored page text under the new settings, refresh every roster line and result from the engine, and keep
  // the reader's choices that still apply: the players ticked inside each group, which details are open, the folded or
  // open roster input, cleared sides and hand-removed players. Only players the engine no longer has are dropped.
  const groupState = () => {
    const state = new Map();
    document.querySelectorAll("#v2FindOut .v2-find-group").forEach(li => {
      const picks = {};
      li.querySelectorAll("input[data-key]").forEach(input => { if (input.checked !== input.defaultChecked) picks[input.dataset.key] = input.checked; });
      const open = [...li.querySelectorAll("details")].map(d => d.open);
      state.set(li.dataset.group, {picks, open});
    });
    return {groups: state, more: state.size > GROUP_LIMIT};
  };
  const restoreGroups = saved => {
    let kept = 0;
    document.querySelectorAll("#v2FindOut .v2-find-group").forEach(li => {
      const old = saved.groups.get(li.dataset.group);
      if (!old) return;
      kept += 1;
      li.querySelectorAll("details").forEach((d, i) => { if (old.open[i] !== undefined) d.open = old.open[i]; });
      li.querySelectorAll("input[data-key]").forEach(input => {
        if (old.picks[input.dataset.key] === undefined || input.checked === old.picks[input.dataset.key]) return;
        input.checked = old.picks[input.dataset.key];
        input.dispatchEvent(new Event("change", {bubbles: true}));
      });
    });
    return kept;
  };
  function reprocessRosters(asks) {
    const map = rowMap();
    const say = [];
    // Prompts that were still waiting for a tap before the change (JEG-1020: asked again, or said to be gone).
    const waiting = {};
    ["mine", "theirs"].forEach(side => {
      waiting[side] = [...document.querySelectorAll(`#${sideId(side)}PasteResult li.v2-find-unsure[data-unsure-id]`)]
        .filter(li => li.querySelector("button")).map(li => ({id: li.dataset.unsureId, name: li.dataset.unsureName}));
    });
    ["mine", "theirs"].forEach(side => {
      const who = side === "mine" ? "Your" : "Their";
      const dropped = S[side].filter(p => !isNotEvaluated(p) && !map.has(p.key));
      if (dropped.length) {
        S[side] = S[side].filter(p => !dropped.includes(p));
        dropped.forEach(p => S.sel.delete(p.key));
        say.push(`${who} roster no longer has ${dropped.map(p => p.name).join(", ")} (not priced under these settings).`);
      }
      S[side].forEach(p => { const row = map.get(p.key); if (row) { p.name = row.name; p.pos = row.pos; } });
    });
    ["mine", "theirs"].forEach(side => {
      const src = S.src[side];
      const res = src && parsePage(src.text);
      if (!res) return;
      const players = src.team !== null && res.teams && res.teams[src.team] ? res.teams[src.team].players : res.players;
      const here = new Set(S.mine.concat(S.theirs).map(p => p.key));
      const added = [];
      players.forEach(p => {
        const row = map.get(String(p.id));
        if (!row || !(p.confidence >= 1)) return;
        const key = String(row.player_key);
        if (here.has(key) || S.removed.has(key)) return;
        here.add(key);
        S[side].push({key, name: row.name, pos: row.pos, team: row.team, slot: p.slot});
        added.push(row.name);
      });
      if (added.length) say.push(`${side === "mine" ? "Your" : "Their"} roster read again: added ${added.join(", ")}.`);
      const unsure = players.filter(p => !(p.confidence >= 1) && map.get(String(p.id)) && !S.answered.has(String(p.id))
        && !here.has(String(map.get(String(p.id)).player_key)) && !S.removed.has(String(map.get(String(p.id)).player_key)))
        .map(p => ({...p, row: map.get(String(p.id))}));
      const still = new Set(unsure.map(p => String(p.id)));
      waiting[side].filter(w => !still.has(w.id)).forEach(w => say.push(`${side === "mine" ? "Your" : "Their"} roster: ${w.name} can no longer be matched, so the question about that player is gone.`));
      if (unsure.length) { asks[side] = unsure; say.push(`${side === "mine" ? "Your" : "Their"} roster: ${plural(unsure.length, "match")} to check again (${unsure.map(p => p.row.name).join(", ")}).`); }
    });
    S.sel = new Set([...S.sel].filter(k => S.mine.concat(S.theirs).some(p => p.key === k)));
    return say;
  }
  // JEG-1380: the week the page now shows, named in the note after a week change.
  function weekNote() {
    const state = engine().getWeekState ? engine().getWeekState() : null;
    return state && Number.isInteger(state.week) ? `Updated for Week ${state.week}.` : "Updated for the selected week.";
  }
  function onLeagueSettingsChanged(event) {
    if (!$("v2Find") || !engine()) return;
    const hadResults = hasResults();
    const saved = hadResults ? groupState() : null;
    const asks = {};
    const say = reprocessRosters(asks);
    renderBoth();
    ["mine", "theirs"].forEach(side => {
      const box = $(`${sideId(side)}PasteResult`);
      if (box && (asks[side] || (say.length && S[side].length && box.childElementCount))) {
        // Asked again below the roster line; nothing here takes focus.
        box.replaceChildren(el("p", {class: "v2-meta", text: `${SIDE_NAME[side]} now has ${plural(S[side].length, "player")} under the new settings.`}), ...unsureBlock(side, asks[side] || []));
      }
    });
    if (hadResults) {
      // The page's own live region says "Results updated for the new league settings"; the rebuilt list is not read out again.
      const out = $("v2FindOut");
      const headline = $("v2FindFit");
      out.setAttribute("aria-live", "off");
      if (headline) headline.setAttribute("aria-live", "off");
      clearOutput();
      run();
      restoreGroups(saved);
      if (saved.more && $("v2FindMoreGroups")) $("v2FindMoreGroups").click();
      setTimeout(() => { out.setAttribute("aria-live", "polite"); if (headline) headline.setAttribute("aria-live", "polite"); }, 150);
    }
    if (!$("v2FindSummary").hidden) updateSummary();
    const note = $("v2FindSettingsNote");
    const text = (hadResults || S.mine.length || S.theirs.length) ? `${event && event.detail && event.detail.reason === "sources" ? "Updated for the new source selection." : event && event.detail && event.detail.reason === "overrides" ? "Updated for your value overrides." : event && event.detail && event.detail.reason === "week" ? weekNote() : "Updated for the new league settings."} ${say.join(" ")}`.trim() : "";
    if (note) note.textContent = text;
    if (event && event.detail && event.detail.notes) event.detail.notes.push(...say);
  }
  document.addEventListener("ddf:league-settings-changed", onLeagueSettingsChanged);

  function build() {
    const host = $("v2FindTrade");
    if (!host || $("v2Find")) return;
    const size = el("select", {id: "v2FindSize"}, ...MAX_SIZE_CHOICES.map(n => el("option", {value: String(n), text: n === 1 ? "1-for-1 only" : `Up to ${n}-for-${n}`})));
    size.value = String(S.maxSize);
    size.addEventListener("change", () => { S.maxSize = Number(size.value); saveSettings(); clearOutput(); });
    const keep = (id, label, field) => {
      const box = el("input", {type: "checkbox", id});
      box.checked = S[field];
      box.addEventListener("change", () => { S[field] = box.checked; saveSettings(); clearOutput(); });
      return el("label", {class: "v2-field"}, box, el("span", {text: ` ${label}`}));
    };
    const protectedBoxes = GUARDRAIL_POSITIONS.map(pos => {
      const box = el("input", {type: "checkbox", id: `v2FindProtect${pos}`});
      box.checked = S.guardrails.protectedPositions.includes(pos);
      box.addEventListener("change", () => {
        S.guardrails.protectedPositions = GUARDRAIL_POSITIONS.filter(p => {
          const input = $(`v2FindProtect${p}`); return input && input.checked;
        });
        saveSettings(); clearOutput();
      });
      return el("label", {class: "v2-find-protect-choice"}, box, el("span", {text: pos}));
    });
    const protectedField = el("fieldset", {class: "v2-find-protect"},
      el("legend", {text: "Protect my starting group at"}),
      el("p", {class: "v2-meta", text: "Hide trades that weaken your starters at a selected position on DDF Value."}),
      el("div", {class: "v2-find-protect-choices"}, ...protectedBoxes));
    const backupRows = GUARDRAIL_POSITIONS.map(pos => {
      const n = S.guardrails.minBackups[pos];
      const readout = el("output", {id: `v2FindBackups${pos}`, "aria-live": "polite", text: String(n)});
      const adjust = (delta, suffix, label) => {
        const button = el("button", {type: "button", id: `v2FindBackups${pos}${suffix}`, class: "v2-btn", text: delta < 0 ? "−" : "+",
          "aria-label": `${label} minimum ${pos} bench backups`});
        button.disabled = delta < 0 ? n === 0 : n === 20;
        button.addEventListener("click", () => {
          S.guardrails.minBackups[pos] = Math.max(0, Math.min(20, S.guardrails.minBackups[pos] + delta));
          const count = S.guardrails.minBackups[pos];
          readout.textContent = String(count);
          $(`v2FindBackups${pos}Down`).disabled = count === 0;
          $(`v2FindBackups${pos}Up`).disabled = count === 20;
          saveSettings(); clearOutput();
        });
        return button;
      };
      return el("div", {class: "v2-find-backup-row"}, el("span", {text: pos}),
        adjust(-1, "Down", "Decrease"), readout, adjust(1, "Up", "Increase"));
    });
    const backupField = el("fieldset", {class: "v2-find-protect v2-find-backups"},
      el("legend", {text: "Minimum bench backups on my team"}),
      el("p", {class: "v2-meta", text: "After starters, FLEX and superflex are filled. Current default: 0 at every position. Players without a DDF Value do not count."}),
      el("div", {class: "v2-find-backup-rows"}, ...backupRows));
    const advancedStatus = el("p", {class: "v2-meta", id: "v2FindAdvancedStatus", role: "status"});
    const minimum = (key, id, label) => {
      const input = el("input", {type: "number", id, min: "0", max: "100", step: "0.1", inputmode: "decimal"});
      input.value = S.guardrails[key] === null ? "" : String(S.guardrails[key]);
      input.addEventListener("change", () => {
        const raw = input.value.trim();
        const valid = (raw === "" && key !== "minDdfEdge") || (/^\d{1,3}(?:\.\d)?$/.test(raw) && Number(raw) <= 100);
        if (!valid) {
          advancedStatus.textContent = `${label}: enter 0 to 100, in steps of 0.1.`;
          input.value = S.guardrails[key] === null ? "" : String(S.guardrails[key]);
          input.focus();
          return;
        }
        S.guardrails[key] = raw === "" ? null : Number(raw);
        advancedStatus.textContent = "Trade settings saved on this device.";
        saveSettings(); clearOutput();
      });
      return el("label", {class: "v2-find-minimum"}, el("span", {text: label}), input);
    };
    const advanced = el("details", {class: "v2-find-advanced"}, el("summary", {text: "Advanced trade minimums"}),
      el("p", {class: "v2-meta", text: "A starting-lineup minimum is off when blank. Setting it to 0 requires a strictly positive gain. Your DDF Value gain must always be positive."}),
      minimum("minDdfEdge", "v2FindMinEdge", "Minimum DDF Value gain"),
      minimum("minUserLineupGain", "v2FindMinMine", "Minimum gain for my starting lineup"),
      minimum("minTheirLineupGain", "v2FindMinTheirs", "Minimum market gain for their starting lineup"), advancedStatus,
      el("button", {type: "button", class: "v2-btn", id: "v2FindResetSettings", text: "Reset trade settings"}));
    advanced.querySelector("#v2FindResetSettings").addEventListener("click", () => {
      applySettings({protectedPositions: [], minBackups: {QB: 0, RB: 0, WR: 0, TE: 0}, maxSize: 2, keepMine: true, keepTheirs: true,
        minDdfEdge: 0, minUserLineupGain: null, minTheirLineupGain: null});
      advancedStatus.textContent = "Trade settings reset and saved.";
      saveSettings(); clearOutput();
    });
    const go = el("button", {type: "button", class: "v2-btn", id: "v2FindGo", text: "Find trades"});
    go.addEventListener("click", findPressed);
    const share = el("button", {type: "button", class: "v2-btn", id: "v2FindShare", text: "Copy link to this search"});
    share.addEventListener("click", () => copyLink(share));
    const swap = el("button", {type: "button", class: "v2-btn", id: "v2FindSwap", text: "Swap teams"});
    swap.addEventListener("click", swapTeams);
    const undo = el("button", {type: "button", class: "v2-btn", id: "v2FindUndo", text: "Undo", disabled: ""});
    undo.addEventListener("click", undoArrange);
    const clearBothButton = el("button", {type: "button", class: "v2-btn", id: "v2FindClearBoth", text: "Clear both", disabled: ""});
    clearBothButton.addEventListener("click", clearBoth);
    const edit = el("button", {type: "button", class: "v2-btn", id: "v2FindEdit", text: "Edit rosters", "aria-expanded": "true", "aria-controls": "v2FindInput v2FindGuardrails"});
    edit.addEventListener("click", () => setCollapsed(false, "input"));
    const summaryRow = el("div", {class: "v2-find-summary", id: "v2FindSummary", hidden: ""},
      el("div", {class: "v2-find-sumrow", id: "v2FindMineSummary"}), el("div", {class: "v2-find-sumrow", id: "v2FindTheirsSummary"}), edit,
      el("p", {class: "v2-meta v2-find-sum-rails", id: "v2FindGuardrailSummary"}));
    // Escape inside the opened input folds it back once there are results to read.
    const card = el("section", {class: "v2-card", id: "v2Find", "aria-labelledby": "v2FindTitle"},
      el("div", {class: "v2-card-head"}, el("div", {},
        el("h2", {id: "v2FindTitle", text: "Your roster and theirs"}),
        el("p", {class: "v2-meta", text: "Paste in your roster and another manager's (or one matchup page for both), or search names. Lists trades where DDF Value says you win and the available charts say the other manager breaks even or wins."}))),
      summaryRow,
      el("div", {id: "v2FindInput"},
        el("div", {class: "v2-ctoolbar v2-find-arrange"}, swap, clearBothButton, undo, el("p", {class: "v2-meta", id: "v2FindArrangeNote", role: "status"})),
        el("div", {class: "v2-trade-sides"}, sideCard("mine", "Your roster"), sideCard("theirs", "Their roster"))),
      el("div", {class: "v2-ctoolbar"}, el("label", {class: "v2-field"}, el("span", {class: "v2-field-label", text: "Package size:"}), size),
        keep("v2FindKeepMine", "Keep my starting lineup filled", "keepMine"), keep("v2FindKeepTheirs", "Keep theirs filled", "keepTheirs"), go, share),
      el("div", {class: "v2-find-guardrails", id: "v2FindGuardrails"}, protectedField, backupField), advanced,
      el("p", {class: "v2-meta v2-find-share-note", id: "v2FindShareNote", role: "status", hidden: ""}),
      el("div", {class: "v2-find-headline", id: "v2FindFit", role: "status", "aria-live": "polite", "data-state": "missing"}, el("b", {text: fitHeadline("missing").text})),
      el("section", {class: "v2-find-assess", id: "v2FindAssess", "aria-label": "Roster assessment", hidden: ""}),
      el("section", {class: "v2-find-teamsum", id: "v2FindTeamSummary", "aria-label": "Team value summary", hidden: ""}),
      el("p", {class: "v2-meta", id: "v2FindSettingsNote"}),
      el("div", {id: "v2FindOut", "aria-live": "polite", hidden: ""}));
    card.addEventListener("keydown", event => {
      if (event.key === "Escape" && !$("v2FindInput").hidden && hasResults() && S.mine.length && S.theirs.length) { setCollapsed(true, "edit"); }
    });
    host.insertBefore(card, host.querySelector(".v2-footnote"));
  }
  // JEG-1021: the league page (league.js) reads rosters with the same parser, name list reader and defense / kicker choices.
  api.page = {parsePage, cleanLine, notEvaluatedChoices, teamCode, slotWord, MIN_MATCHED, MIN_SHARE, NAME_LIST_SHARE};
  if (sharedStore()) {
    sharedStore().subscribe(pullMine);
    sharedStore().onChange((w, change) => {
      pullMine();
      updateSavedTeamPicker();
      if (!["load", "replace", "other-tab"].includes(change.reason)) return;
      if (linkHolds && change.reason === "other-tab") return;
      linkHolds = false;
      const incoming = root.TradeValueWorkspace.normalizeFinderSettings(w.ui.finderSettings);
      const key = settingsKey(incoming);
      if (key === appliedSettings) return;
      appliedSettings = key;
      applySettings(incoming);
      if ($("v2FindOut")) clearOutput();
    });
  }
  const start = () => { restoreRosterCopy(); const saved = savedSettings(); if (saved) appliedSettings = settingsKey(saved); applySettings(saved); build(); pullMine(); if (rosterCopy) renderBoth(); updateSavedTeamPicker(); };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);
  else start();
})(typeof window !== "undefined" ? window : globalThis);
