// Trade Value v2 — the trade opportunities table's data (JEG-1021 section 4).
//
// "My team" against every other team: one flat list of trades, the same code for 1 opponent or 20. Each pairing is searched by
// findTrades (finder.js, unchanged) and judged by tradeFit (finder.js); this file only runs the pairings (cached, chunked),
// flattens them into rows with the eight columns, labels each row's overall fit, and ranks the rows.
//
// Decisions (Jeremy, 2026-10-24, JEG-1021):
//   * ranking = fit tiers first (natural, market supported, force; JEG-1108 retired Value fit), then the fundamentals edge (DDF Value receive - give);
//   * default order is best first; force fits are shown, labelled, with a one-click Hide force fits.
// Defaults chosen here, to log in docs/math-review-agenda.md: at most PER_PAIRING trades per pairing (the finder's LIMIT),
// at most MAX_OPPONENTS opponents per run.
(function (root) {
  "use strict";

  const MAX_OPPONENTS = 20;
  const OUR_KEY = "ddf_value";
  const MARKET_KEY = "chart_avg";
  const PROJ_KEY = "ddf_value_projections";
  const TIERS = {natural: 0, market: 1, force: 2};
  const UNJUDGED_TIER = 4;
  const CACHE_LIMIT = 400;
  const finite = value => typeof value === "number" && Number.isFinite(value);
  const finder = () => (typeof module !== "undefined" && module.exports ? require("./finder.js") : root.TradeValueFinder);
  const shown = n => Math.round(n * 10) / 10;
  const asShown = n => (Math.abs(n) < 0.05 ? 0 : n);
  const fmt = n => (Math.abs(n) < 0.05 ? "0.0" : (n > 0 ? "+" : "−") + Math.abs(n).toFixed(1));
  const listJoin = items => (items.length <= 1 ? items.join("") : `${items.slice(0, -1).join(", ")} and ${items[items.length - 1]}`);
  const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;

  // ---------- the labels (JEG-1108: rewritten) ----------
  // tradeFit already computes the final label (natural / market / force). These helpers extract sub-signals for columns.
  function ourFitOf(fit) {
    if (fit.yourValueOk && fit.constructionOk) return {label: "natural", detail: "total rises, starters hold, construction OK"};
    if (fit.yourValueOk) return {label: "partial", detail: "total rises but construction issue"};
    const us = fit.us;
    return {label: "force", detail: us.down ? "loses value" : us.flat ? "no measurable gain" : "starters drop"};
  }
  function theirFitOf(fit) {
    const them = fit.them;
    if (fit.marketSupported) return {label: "favorable", detail: "trade charts favor them"};
    if (them.net >= -them.tau) return {label: "neutral", detail: "within noise floor"};
    return {label: "hurts", detail: "loses value on trade charts"};
  }
  // JEG-1108: the overall fit now comes straight from tradeFit's label. The overallFit function bridges older callers.
  function overallFit(ourLabel, marketOk, chartEdge, theirLabel, fit) {
    // When we have the tradeFit result, use its label directly.
    if (fit && fit.label) return fit.label;
    // Fallback for callers without the full fit object.
    if (ourLabel === "force") return "force";
    if (!marketOk) return "force";
    if (chartEdge !== null && asShown(chartEdge) >= 0) return "market";
    return "force";
  }
  // JEG-1081: does DDF Value (projections) back the trade? projEdge = what you receive minus what you give in that view (the
  // same direction as the DDF Value capture). true: it gains you 0.05 or more; false: it loses you 0.05 or more; null: level or no
  // projection for a player in the package (never counted as 0).
  function projAgreement(projEdge) {
    if (!finite(projEdge)) return null;
    if (projEdge >= 0.05) return true;
    if (projEdge <= -0.05) return false;
    return null;
  }
  const FIT_WORD = {natural: "Natural fit", market: "Market supported", force: "Force fit"};

  // ---------- one pairing ----------
  const rowsFor = (entries, rowsByKey) => (entries || []).map(e => rowsByKey.get(String(e.key))).filter(Boolean);
  const rowSig = r => `${r.player_key}:${[OUR_KEY, "ddf_value_projections"].concat(["usatoday", "fantasycalc", "fantasypros", "cbs"]).map(k => (r.values && finite(r.values[k]) ? r.values[k].toFixed(3) : "-")).join(",")}:${r.pos}`;
  const sigOf = rows => rows.map(rowSig).sort().join(";");
  // Everything besides the two rosters that changes a pairing's answer.
  function contextSig(ctx) {
    return JSON.stringify([ctx.shape || null, ctx.charts || [], ctx.market || null, ctx.maxSize || 2, Boolean(ctx.keepMine), Boolean(ctx.keepTheirs),
      ctx.expected || null, ctx.weights || null]);
  }

  // mine, opp: {id, name, entries}. ctx: {rowsByKey, shape, expected, weights, charts (available trade charts), market (charts when there are
  // enough for a Trade chart average, else null), maxSize, keepMine, keepTheirs}. Returns the pairing's rows (not yet ranked).
  function computePairing(mine, opp, ctx) {
    const F = finder();
    const mineRows = rowsFor(mine.entries, ctx.rowsByKey);
    const theirRows = rowsFor(opp.entries, ctx.rowsByKey);
    const find = ctx.findTrades || F.findTrades;
    const res = find(mineRows, theirRows, {chartKeys: ctx.charts, maxSize: ctx.maxSize || 2, limit: F.LIMIT,
      sanity: ctx.shape ? {shape: ctx.shape, mine: mineRows, theirs: theirRows, keepMine: ctx.keepMine !== false, keepTheirs: ctx.keepTheirs !== false} : null});
    const market = ctx.market && ctx.market.length >= F.MIN_CHARTS ? ctx.market : null;
    const judged = Boolean(market && ctx.expected && ctx.shape);
    const avg = rows => (market ? F.withChartAverage(rows, market) : null);
    const mineAvg = avg(mineRows);
    const theirAvg = avg(theirRows);
    const byKey = new Map((mineAvg || []).concat(theirAvg || []).map(r => [String(r.player_key), r]));
    const fitCtx = judged ? {shape: ctx.shape, expected: ctx.expected, weights: ctx.weights, ourKey: OUR_KEY, marketKey: MARKET_KEY, chartKeys: market, z: F.FIT_Z} : null;
    const wide = rows => rows.map(r => byKey.get(String(r.player_key)) || r);
    const myStart = ctx.shape ? F.lineupValue(mineRows, ctx.shape, OUR_KEY).starterValue : 0;
    const slots = ctx.shape ? ["QB", "RB", "WR", "TE", "FLEX", "SUPERFLEX"].reduce((n, s) => n + (ctx.shape[s] || 0), 0) : 0;
    const partial = theirRows.filter(r => ["QB", "RB", "WR", "TE"].includes(r.pos)).length < slots;
    const rows = res.trades.map(t => {
      const give = wide(t.give);
      const recv = wide(t.receive);
      let fit = null;
      if (fitCtx) fit = F.tradeFit({mine: {roster: mineAvg, leaving: give, arriving: recv}, theirs: {roster: theirAvg, leaving: recv, arriving: give}}, fitCtx);
      const sumOf = (list, key) => list.reduce((n, r) => (n === null || !r.values || !finite(r.values[key]) ? null : n + r.values[key]), 0);
      const giveAvg = market ? sumOf(give, MARKET_KEY) : null;
      const recvAvg = market ? sumOf(recv, MARKET_KEY) : null;
      const chartEdge = giveAvg !== null && recvAvg !== null ? giveAvg - recvAvg : null;
      const marketOk = t.pricedCharts >= Math.min(F.MIN_CHARTS, ctx.charts.length) && t.rivalOkCount >= Math.min(F.MIN_CHARTS, ctx.charts.length);
      const sumAll = (list, key) => list.reduce((n, r) => (n === null || !r.values || !finite(r.values[key]) ? null : n + r.values[key]), 0);
      const projGive = sumAll(give, PROJ_KEY);
      const projRecv = sumAll(recv, PROJ_KEY);
      const projEdge = projGive !== null && projRecv !== null ? projRecv - projGive : null;
      const ours = fit ? ourFitOf(fit) : null;
      const theirs = fit ? theirFitOf(fit) : null;
      const overall = fit ? overallFit(ours.label, marketOk, chartEdge, theirs.label, fit) : null;
      const core = F.coreOf(t.receive, OUR_KEY);
      return {id: `${opp.id}|${t.give.map(r => r.player_key)}|${t.receive.map(r => r.player_key)}`, opponentId: opp.id, opponent: opp.name, give: t.give, receive: t.receive, core,
        edge: t.edge, edgePct: myStart > 0 ? (t.edge / myStart) * 100 : null, score: t.score, charts: t.charts, pricedCharts: t.pricedCharts, rivalOkCount: t.rivalOkCount,
        chartCount: ctx.charts.length, chartEdge, projEdge, projAgrees: projAgreement(projEdge), ours, theirs, overall, tier: overall ? TIERS[overall] : UNJUDGED_TIER, fit, partial, throwIns: t.throwIns || null, size: t.give.length + t.receive.length};
    });
    return {opponentId: opp.id, rows, total: res.total, partial, evaluated: theirRows.length, searched: {mine: res.mine, theirs: res.theirs}, sanityDropped: res.sanityDropped};
  }

  // The order of the table: fit tier, then fundamentals edge (best first), then the finder's own score, simpler trade, opponent, trade key.
  function compareRows(a, b) {
    return a.tier - b.tier || shown(b.edge) - shown(a.edge) || b.edge - a.edge || b.score - a.score || a.size - b.size
      || a.opponent.localeCompare(b.opponent) || (a.id < b.id ? -1 : a.id > b.id ? 1 : 0);
  }
  // Rank is the position in that order: 1..N, no gaps, no repeats.
  function rankRows(rows) {
    return rows.slice().sort(compareRows).map((row, i) => ({...row, rank: i + 1}));
  }

  // JEG-885 (Jeremy, 2026-10-25, option B): the list shows at most CAP_PER_CORE rows for one received core player; the rest
  // fold under a "N more for <player>" control that expands in place (league.js draws it). Selection only: keyFn(row) is the
  // received core player's key, the order is the ranking order the caller passes in, and every value on a row is untouched.
  const CAP_PER_CORE = 2;
  // rows -> {list (at most n per key, in the order given), folds (key -> the rows beyond the cap, in the order given)}.
  function capPerCore(rows, keyFn, n) {
    const limit = Math.max(1, n || 1);
    const seen = new Map();
    const list = [];
    const folds = new Map();
    rows.forEach(row => {
      const key = String(keyFn(row));
      const used = seen.get(key) || 0;
      seen.set(key, used + 1);
      if (used < limit) { list.push(row); return; }
      if (!folds.has(key)) folds.set(key, []);
      folds.get(key).push(row);
    });
    return {list, folds};
  }

  // ---------- all pairings: cached, chunked ----------
  function createCache() { return new Map(); }
  const nextFrame = () => new Promise(resolve => (root.requestAnimationFrame ? root.requestAnimationFrame(() => resolve()) : setTimeout(resolve, 0)));
  // mine: {id, name, entries}; opponents: [{id, name, entries}]. Options: {cache, onProgress({index, total, name}), yieldFn, isCancelled(), budgetMs}.
  // Resolves {rows (ranked), perOpponent, capped, computed, reused, cancelled}.
  async function runAll(mine, opponents, ctx, options) {
    const o = options || {};
    const cache = o.cache || createCache();
    const yieldFn = o.yieldFn || nextFrame;
    const budget = o.budgetMs === undefined ? 12 : o.budgetMs;
    const clock = () => (root.performance && root.performance.now ? root.performance.now() : Date.now());
    const eligible = opponents.filter(t => rowsFor(t.entries, ctx.rowsByKey).length > 0);
    const run = eligible.slice(0, MAX_OPPONENTS);
    const mineRows = rowsFor(mine.entries, ctx.rowsByKey);
    const cSig = contextSig(ctx);
    const mineSig = sigOf(mineRows);
    const out = {rows: [], perOpponent: [], capped: eligible.length > run.length, computed: 0, reused: 0, cancelled: false, skipped: opponents.length - eligible.length};
    let last = clock();
    for (let i = 0; i < run.length; i++) {
      if (o.isCancelled && o.isCancelled()) { out.cancelled = true; return out; }
      const opp = run[i];
      const key = `${mineSig}#${sigOf(rowsFor(opp.entries, ctx.rowsByKey))}#${cSig}`;
      let result = cache.get(key);
      if (result) out.reused += 1;
      else {
        if (o.onProgress) o.onProgress({index: i, total: run.length, name: opp.name});
        result = computePairing(mine, opp, ctx);
        cache.set(key, result);
        if (cache.size > CACHE_LIMIT) cache.delete(cache.keys().next().value);
        out.computed += 1;
        if (clock() - last > budget) { await yieldFn(); last = clock(); }
      }
      // A cached pairing belongs to whichever team had these players; re-label it for this opponent.
      const rows = result.rows.map(r => ({...r, opponentId: opp.id, opponent: opp.name, id: `${opp.id}|${r.id.split("|").slice(1).join("|")}`}));
      out.rows.push(...rows);
      out.perOpponent.push({id: opp.id, name: opp.name, count: rows.length, partial: result.partial, evaluated: result.evaluated, sanityDropped: result.sanityDropped,
        natural: rows.filter(r => r.overall === "natural").length,
        market: rows.filter(r => r.overall === "market").length, force: rows.filter(r => r.overall === "force").length});
    }
    out.rows = rankRows(out.rows);
    return out;
  }

  // ---------- filters (section 4.7, JEG-1108: value retired) ----------
  // filters: {fit: "all" | "natural" | "naturalMarket", opponent: "all" | id, minCapture: points, minCharts: count}; hideForce: boolean.
  function filterRows(rows, filters, hideForce) {
    const f = filters || {};
    return rows.filter(r => {
      if (hideForce && r.overall === "force") return false;
      if (f.fit === "natural" && r.overall !== "natural") return false;
      // Legacy "naturalValue" now means natural + market supported.
      if ((f.fit === "naturalMarket" || f.fit === "naturalValue") && r.overall !== "natural" && r.overall !== "market") return false;
      if (f.opponent && f.opponent !== "all" && r.opponentId !== f.opponent) return false;
      if (f.minCapture && !(r.edge >= f.minCapture)) return false;
      if (f.minCharts && !(r.rivalOkCount >= f.minCharts)) return false;
      return true;
    });
  }

  // ---------- headlines (section 4.5) ----------
  const names = rows => rows.map(r => r.name).join(" + ");
  const tradeSentence = r => `send ${names(r.give)} to ${r.opponent} for ${names(r.receive)} (${fmt(r.edge)} DDF, ${r.rivalOkCount}/${r.chartCount} charts fair)`;
  // result: runAll's output; mineBalance: {over: [pos], under: [pos]} or null. Counts are of the whole list, not the filtered one.
  function leagueHeadline(result, mineBalance) {
    const rows = result.rows;
    const opponents = result.perOpponent.length;
    if (!rows.length) return opponents ? `No trade opportunities found across ${plural(opponents, "opponent")}.` : "";
    const natural = rows.find(r => r.overall === "natural");
    const counts = ["natural", "market", "force"].map(k => ({k, n: rows.filter(r => r.overall === k).length}));
    const head = `${plural(rows.length, "trade opportunity").replace("opportunitys", "opportunities")} across ${plural(opponents, "opponent")}.`;
    const best = natural ? ` Best natural fit: ${tradeSentence(natural)}.`
      : ` No natural fits found: ${counts.filter(c => c.k !== "natural" && c.n).map(c => `${c.n} ${c.k === "market" ? "market supported" : c.k} fit${c.n === 1 ? "" : "s"}`).join(", ") || "none judged"}.`;
    const bal = mineBalance && (mineBalance.over.length || mineBalance.under.length)
      ? ` Your roster is ${[mineBalance.over.length ? `overweight at ${listJoin(mineBalance.over)}` : "", mineBalance.under.length ? `underweight at ${listJoin(mineBalance.under)}` : ""].filter(Boolean).join(" and ")}.` : "";
    return `${head}${best}${bal}`;
  }
  // One opponent's line, from its counts and its depth ({under: [pos]} of their roster).
  function opponentHeadline(entry, theirBalance) {
    const parts = [["natural", "natural fit"], ["market", "market supported"], ["force", "force fit"]].filter(([k]) => entry[k]).map(([k, w]) => `${entry[k]} ${w}${entry[k] === 1 ? "" : "s"}`);
    const need = theirBalance && theirBalance.under.length ? ` Their roster is short at ${listJoin(theirBalance.under)}.` : "";
    return `vs ${entry.name}: ${parts.length ? parts.join(", ") : "no trades found"}.${need}${entry.partial ? " (partial roster)" : ""}`;
  }

  // ---------- the table's columns, for table-sort.js (section 6) ----------
  const OPP_COLUMNS = [
    {id: "rank", label: "Opportunity rank", type: "number", first: "asc", rank: true, get: r => r.rank},
    {id: "opponent", label: "Opponent", type: "text", first: "asc", get: r => r.opponent},
    {id: "capture", label: "DDF Value capture", type: "number", first: "desc", get: r => r.edge},
    {id: "market", label: "Market perception", type: "number", first: "desc", get: r => r.chartEdge},
    {id: "proj", label: "Projections agree", type: "number", first: "desc", get: r => (r.projAgrees === null || r.projAgrees === undefined ? null : r.projAgrees ? 1 : 0)},
    {id: "fair", label: "Charts fair", type: "number", first: "desc", get: r => r.rivalOkCount},
    {id: "overall", label: "Overall fit", type: "number", first: "asc", rank: true, get: r => (r.overall ? r.tier : null)}
  ];
  const OPP_DEFAULT = {col: "rank", dir: "asc"};
  const OPP_TIES = [{get: r => r.rank, type: "number", dir: "asc"}, {get: r => r.opponent, type: "text", dir: "asc"}, {get: r => r.id, type: "text", dir: "asc"}];

  const api = {OPP_COLUMNS, OPP_DEFAULT, OPP_TIES, MAX_OPPONENTS, TIERS, FIT_WORD, ourFitOf, theirFitOf, overallFit, projAgreement, PROJ_KEY, CAP_PER_CORE, capPerCore, computePairing, compareRows, rankRows, createCache, runAll, filterRows, leagueHeadline,
    opponentHeadline, contextSig, sigOf, fmt};
  if (typeof module !== "undefined" && module.exports) { module.exports = api; return; }
  root.TradeValueOpportunities = api;
})(typeof window !== "undefined" ? window : globalThis);
