/* Trade & Waiver Recommendations: the searches behind find.html and waivers.html (JEG-1539, lane "find").
 *
 * No value math here. The trade search is the live Find a trade search (TradeValueFinder.findTrades, groupTrades,
 * tradeFit) run against every partner the way the live league search does it (TradeValueOpportunities' pairing:
 * findTrades with the available trade charts as the acceptance gate and both lineup checks on, then tradeFit on rows that
 * carry the chart average). The pickups are the live Waivers tab (TradeValueWaivers.evaluateAll) with the live context
 * (TradeValueFinder.ui.depthContext / benchWeights). This file only picks inputs, runs those functions and sorts.
 *
 * Your / Their valuation (find.html selects; tokens kept from the wireframe):
 *   your valuation  -> findTrades ourKey (what you must win on), tradeFit ourKey, the waivers view
 *   their valuation -> tradeFit marketKey (the other team's side of the fit label)
 *   The acceptance gate stays the live one: at least one available trade chart has the package even or better for them.
 *   "Analyst charts" (token Market) = chart_avg over CBS Sports, USA Today and FantasyPros (withChartAverage).
 *
 * API: window.DDF.find
 *   VALUATIONS             token -> {key, label, view, avg}
 *   context()              {shape, expected, weights, gate, analyst, ready} from the engine (null before it loads)
 *   searchPartner(ctx, mine, theirs, opts) -> {trades, total, sanityDropped, guardrailDropped, searched, partial}
 *   classify(trade)        'natural' | 'neutral' | 'force' | 'unjudged'
 *   group(trades, opts)    TradeValueFinder.groupTrades per class
 *   pickups(ctx, mineEntries, candEntries, token) -> TradeValueWaivers.evaluateAll output (+ dd, roster entries)
 *   entriesOf(team)        DDF.league team -> waivers-style entries [{key, name, pos, team}]
 *   rowsOf(team)           DDF.league team -> engine rows (priced players only)
 */
(function () {
  "use strict";
  var DDF = window.DDF = window.DDF || {};
  var F = function () { return window.TradeValueFinder; };
  var WV = function () { return window.TradeValueWaivers; };
  var ANALYST = ["cbs", "usatoday", "fantasypros"];
  var finite = function (v) { return typeof v === "number" && isFinite(v); };

  var VALUATIONS = {
    "DDF": {key: "ddf_value", label: "DDF", view: "ddf"},
    "DDF (Projection based)": {key: "ddf_value_projections", label: "DDF (Projection based)", view: "projections"},
    "Market": {key: "chart_avg", label: "Analyst charts", view: "market", avg: true},
    "CBS Sports": {key: "cbs", label: "CBS Sports", view: "src:cbs"},
    "USA Today": {key: "usatoday", label: "USA Today", view: "src:usatoday"},
    "FantasyPros": {key: "fantasypros", label: "FantasyPros", view: "src:fantasypros"},
    "FantasyCalc": {key: "fantasycalc", label: "Live market (FantasyCalc)", view: "src:fantasycalc"},
    "ESPN projections": {key: "espn", label: "ESPN projections", view: "src:espn"},
    "CBS rest-of-season projections": {key: "cbsros", label: "CBS rest-of-season projections", view: "src:cbsros"},
    "Razzball projections": {key: "razzball", label: "Razzball projections", view: "src:razzball"}
  };
  function valuation(token) { return VALUATIONS[token] || VALUATIONS.DDF; }

  function context() {
    var C = window.TradeValueCurveControls, f = F();
    if (!C || !f || !f.ui || !C.getAllRows) return null;
    var info = C.getSourceInfo ? C.getSourceInfo() : [];
    var available = new Set(info.filter(function (i) { return i.available; }).map(function (i) { return i.key; }));
    var depth = f.ui.depthContext();
    var shape = C.getRosterShape ? C.getRosterShape() : null;
    var analyst = ANALYST.filter(function (k) { return available.has(k); });
    return {shape: shape, expected: depth ? depth.expected : null, weights: f.ui.benchWeights(),
      gate: f.CHART_KEYS.filter(function (k) { return available.has(k); }),
      analyst: analyst.length === ANALYST.length ? analyst : null};
  }

  var keyOf = function (r) { return String(r.player_key); };
  function rowsOf(team) {
    return (team ? team.players : []).filter(function (p) { return !p.unpriced && p.row; }).map(function (p) { return p.row; });
  }
  function entriesOf(team) {
    return (team ? team.players : []).map(function (p) {
      if (!p.unpriced) return {key: p.key, name: p.n, pos: p.pos, team: p.team || ""};
      if (p.pos === "K" || p.pos === "DEF" || p.pos === "DST") return {key: "x:" + p.pos + ":" + p.name, name: p.name, pos: p.pos, team: ""};
      return null;   // a name that matched no player: not on the evaluated roster, never a 0
    }).filter(Boolean);
  }

  // One partner, searched the way the live league search searches a pairing. mine / theirs: engine rows (whole rosters).
  // opts: {your, their, sizes:[1..4], minBench:{QB,RB,WR,TE}, held:Set(player_key)}.
  function searchPartner(ctx, mine, theirs, opts) {
    var f = F(), your = valuation(opts.your), their = valuation(opts.their);
    var sizes = (opts.sizes && opts.sizes.length ? opts.sizes : [1, 2]).slice().sort();
    var held = opts.held || new Set();
    var canAvg = Boolean(ctx.analyst);
    var widen = function (rows) { return canAvg ? f.withChartAverage(rows, ctx.analyst) : rows; };
    // The search reads the rows as the engine gives them; only a chart-average valuation needs the extra series on them.
    var mineS = your.avg ? widen(mine) : mine, theirS = your.avg ? widen(theirs) : theirs;
    var pool = mineS.filter(function (r) { return !held.has(keyOf(r)); });
    var minBench = opts.minBench || {};
    var res = f.findTrades(pool, theirS, {ourKey: your.key, chartKeys: ctx.gate, maxSize: sizes[sizes.length - 1], limit: Infinity,
      guardrails: {protectedPositions: [], minBackups: {QB: +minBench.QB || 0, RB: +minBench.RB || 0, WR: +minBench.WR || 0, TE: +minBench.TE || 0},
        minDdfEdge: 0, minUserLineupGain: null, minTheirLineupGain: null, shape: ctx.shape, mine: mineS, theirs: theirS, chartKeys: ctx.gate, ourKey: your.key},
      sanity: ctx.shape ? {shape: ctx.shape, mine: mineS, theirs: theirS, keepMine: true, keepTheirs: true} : null});
    var judged = Boolean(ctx.shape && ctx.expected && (!their.avg || canAvg) && (!your.avg || canAvg));
    var fitCtx = judged ? {shape: ctx.shape, expected: ctx.expected, weights: ctx.weights, ourKey: your.key, marketKey: their.key,
      chartKeys: ctx.analyst || undefined, z: f.FIT_Z} : null;
    var mineW = widen(mine), theirW = widen(theirs);
    var byKey = new Map(mineW.concat(theirW).map(function (r) { return [keyOf(r), r]; }));
    var wide = function (rows) { return rows.map(function (r) { return byKey.get(keyOf(r)) || r; }); };
    var slots = ctx.shape ? ["QB", "RB", "WR", "TE", "FLEX", "SUPERFLEX"].reduce(function (n, s) { return n + (ctx.shape[s] || 0); }, 0) : 0;
    var trades = res.trades.filter(function (t) {
      return sizes.indexOf(t.give.length) >= 0 && sizes.indexOf(t.receive.length) >= 0
        && !t.give.some(function (r) { return held.has(keyOf(r)); });
    }).map(function (t) {
      var give = wide(t.give), recv = wide(t.receive);
      var fit = fitCtx ? f.tradeFit({mine: {roster: mineW, leaving: give, arriving: recv}, theirs: {roster: theirW, leaving: recv, arriving: give}}, fitCtx) : null;
      var out = {give: t.give, receive: t.receive, edge: t.edge, score: t.score, charts: t.charts, pricedCharts: t.pricedCharts,
        rivalOkCount: t.rivalOkCount, chartCount: ctx.gate.length, throwIns: t.throwIns || null, addedThrowIns: t.addedThrowIns || null,
        unbalanced: Boolean(t.unbalanced), fit: fit,
        you: fit ? fit.us.starterDelta : null, them: fit ? fit.them.starterDelta : null};
      out.cls = classify(out);
      return out;
    });
    return {trades: trades, total: res.total, sanityDropped: res.sanityDropped, guardrailDropped: res.guardrailDropped || 0,
      searched: {mine: res.mine, theirs: res.theirs}, partial: theirs.filter(function (r) { return ["QB", "RB", "WR", "TE"].indexOf(r.pos) >= 0; }).length < slots,
      judged: judged};
  }
  // Natural fit is tradeFit's label (both sides, JEG-1324). Partner neutral: not natural, and the other team's side of the
  // fit is not worse than its noise floor (the live "neutral" / "favorable" reading of their side). The rest are force fits.
  function classify(t) {
    if (!t.fit) return "unjudged";
    if (t.fit.label === "natural") return "natural";
    return t.fit.them.net >= -t.fit.them.tau ? "neutral" : "force";
  }
  // Groups by the player(s) you receive (the live grouping), separately per class so every card keeps its own label.
  function group(trades, opts) {
    var f = F(), byClass = {};
    trades.forEach(function (t) { (byClass[t.cls] = byClass[t.cls] || []).push(t); });
    var out = [];
    Object.keys(byClass).forEach(function (cls) {
      f.groupTrades(byClass[cls], {ourKey: valuation(opts.your).key}).forEach(function (g) { out.push(Object.assign({cls: cls}, g)); });
    });
    return out;
  }

  // The live Waivers tab's evaluation for the reader's roster. mineEntries / candEntries: [{key, name, pos, team}].
  function pickups(ctx, mineEntries, candEntries, token) {
    var w = WV(), C = window.TradeValueCurveControls;
    var byKey = new Map(C.getAllRows().map(function (r) { return [keyOf(r), r]; }));
    var mine = w.rowsFor(mineEntries, byKey);
    var dd = w.dedupe(candEntries, mineEntries);
    var cands = w.rowsFor(dd.kept, byKey);
    var view = w.viewFor(valuation(token).view, null);
    var wctx = {shape: ctx.shape, weights: ctx.weights, expected: ctx.expected, chartKeys: ctx.analyst, rosterSize: w.rosterSizeOf(ctx.shape),
      byes: window.TradeValueByes ? window.TradeValueByes.byes : null, status: w.statusFreshness(window.TradeValueStatus || null, Date.now()), view: view};
    if (!mine.rows.length || !cands.rows.length) return {results: [], combos: [], dd: dd, mine: mine, cands: cands, view: view};
    var out = w.evaluateAll(wctx, mine.rows, cands.rows);
    out.dd = dd; out.mine = mine; out.cands = cands;
    return out;
  }

  var shown = function (n) { return Math.abs(n) < 0.05 ? "0.0" : (n > 0 ? "+" : "−") + Math.abs(n).toFixed(1); };

  DDF.find = {VALUATIONS: VALUATIONS, valuation: valuation, ANALYST: ANALYST, context: context, searchPartner: searchPartner,
    classify: classify, group: group, pickups: pickups, entriesOf: entriesOf, rowsOf: rowsOf, shown: shown, finite: finite};
})();
