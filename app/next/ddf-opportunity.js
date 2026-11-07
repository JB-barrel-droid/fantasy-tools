/* Opportunity size and roster-improvement percent (JEG-1558).
 *
 * No value math here. Every number is a TradeValueFinder read on the engine's own rows: lineupValue, benchWeight,
 * withChartAverage, the same "worth" the Waivers tab and tradeFit use (starters in full, bench at the engine's bench
 * weights). This file only divides, compares with fixed thresholds and picks words.
 *
 * ONE DENOMINATOR (Jeremy 2026-11-07: "your roster gets x% better"): a percent is the change in a roster's worth over
 * that roster's worth before the move, both in the same valuation. Compared on 36 real rosters (3 leagues, week 9, see
 * docs/claude-log/2026-11-07-opportunity-size.md): worth, starters-only value and the roster's value above waivers give
 * nearly the same percent (median 6.6 / 6.6 / 6.1% for the best natural trade; none under 117 points), because DDF Value
 * is already priced above the waiver line. Worth was chosen: it is what the Waivers tab and the trade fit already count,
 * so the tier and the trade card say the same number; it counts the bench at its weight (a bench-only move is not 0%);
 * no roster in the data is under 117 points, so there is no tiny base. League-rank scale ("places") is not a percent of
 * the roster, so it is only used in the tier wording. A base under MIN_BASE points (a few priced players) gives no
 * percent at all (tiny-denominator guard).
 *
 * TIERS (Jeremy 2026-11-07, multiple choice): opportunity = the best gain from one waiver pickup or one 1- or 2-player
 * trade that fits both rosters (tradeFit label "natural"), counted only when it beats the engine's noise floor (tau, the
 * Waivers tab's Pick up rule), as a percent of worth. Under 3% none, 3 to under 6% marginal, 6 to under 10% medium,
 * 10% or more big. One place in a league's value ranking was 3.6 to 6.1% of worth in the data.
 * CAVEAT: these thresholds come from ONE week (week 9, 2026-11-07) of THREE Yahoo half-PPR 12-team leagues. Re-check them
 * on superflex and full-PPR leagues before relying on them there (follow-up JEG-1562).
 *
 * PARTNER BANDS (Jeremy 2026-11-07): the partner's signed percent in their valuation (default Analyst charts, the find
 * page's "their valuation"). On the best natural trade of each of the 36 rosters the partner's change was between
 * −5.8% and +1.1% (median −1.0%); half sat within ±1%, the next third between −1% and −3%. The engine's noise floor is
 * about 2.5% of a roster (median), too wide to call "unchanged", so the band is ±1%. 3% matches the "no meaningful
 * opportunity" line on the gain side: a cost under 3% is small, 3% or more is a real loss.
 *   better          pct >= 1
 *   unchanged       -1 < pct < 1
 *   slightly worse  -3 < pct <= -1
 *   clearly worse   pct <= -3
 * Percents are compared exactly and shown truncated toward zero to one decimal, so the shown number never crosses a
 * boundary the band did not (5.99 shows as 5.9, marginal).
 *
 * API: window.DDFOpportunity (module.exports in Node)
 *   rosterImprovementPct(trade, side, ctx) -> {side, key, before, after, delta, pct, shown, band, label, sentence}
 *       trade {mine:[rows], theirs:[rows], give:[rows], receive:[rows]} (give = your rows that leave, receive = theirs)
 *       side  'sender' (your roster) | 'partner' (their roster)
 *       ctx   {shape, weights, senderKey?='ddf_value', partnerKey?='chart_avg', chartKeys?=[cbs, usatoday, fantasypros]}
 *       pct is signed and null when the roster's base is under MIN_BASE (band 'unsized').
 *   tierOf(pct)                       'big' | 'medium' | 'marginal' | 'none'
 *   bandOf(pct)                       'better' | 'unchanged' | 'slightly_worse' | 'clearly_worse' | 'unsized'
 *   shownPct(pct)                     truncated toward zero, one decimal
 *   worth(rows, ctx, key)             starters in full plus bench at its weights
 *   assess({worth, waiver, trade, hole}) -> {tier, pct, shown, gain, source, waiversEmpty, headline, line, hole}
 *       waiver / trade: {gain, tau} or null (the best single pickup's totalDelta / the best natural trade's worth change)
 *   whereToLook(teams, meIndex, shape, chartKeys?, weights?) -> {slot, gap, value, median, pct} | null (Analyst charts slot gap)
 *   computeTeam(cur, mine) (browser) -> Promise of assess(...) for the reader's team on DDF.find / DDF.league
 */
(function (root) {
  "use strict";
  var isNode = typeof module !== "undefined" && module.exports;
  var F = function () { return isNode ? require("../v2/finder.js") : root.TradeValueFinder; };
  var finite = function (v) { return typeof v === "number" && isFinite(v); };
  var ANALYST = ["cbs", "usatoday", "fantasypros"];
  var OUR_KEY = "ddf_value", MARKET_KEY = "chart_avg";
  var MIN_BASE = 20;   // points: below this a roster has too few priced players for a percent to mean anything
  var NET_FLOOR = 0.05; // a change that shows as 0.0 is no change (finder.js / waivers.js)
  var TIERS = [{id: "big", min: 10}, {id: "medium", min: 6}, {id: "marginal", min: 3}];
  var BANDS = {better: 1, unchanged: -1, slightly_worse: -3};
  var SLOTS = ["QB", "RB", "WR", "TE", "FLEX", "SUPERFLEX"];

  function shownPct(pct) { return finite(pct) ? (pct < 0 ? -1 : 1) * Math.floor(Math.abs(pct) * 10 + 1e-9) / 10 : null; }
  function fmt(pct) { return shownPct(Math.abs(pct)).toFixed(1) + "%"; }
  function tierOf(pct) {
    if (!finite(pct)) return "none";
    for (var i = 0; i < TIERS.length; i++) if (pct >= TIERS[i].min) return TIERS[i].id;
    return "none";
  }
  function bandOf(pct) {
    if (!finite(pct)) return "unsized";
    if (pct >= BANDS.better) return "better";
    if (pct > BANDS.unchanged) return "unchanged";
    if (pct > BANDS.slightly_worse) return "slightly_worse";
    return "clearly_worse";
  }

  // Starters in full, bench at the engine's bench weights (finder.js netOf / waivers.js netOf, same formula and inputs).
  function worth(rows, ctx, key) {
    var f = F(), k = key || OUR_KEY;
    var list = k === MARKET_KEY ? f.withChartAverage(rows, ctx.chartKeys || ANALYST) : rows;
    var L = f.lineupValue(list, ctx.shape, k);
    return L.starterValue + L.bench.reduce(function (t, r) {
      var v = r.values ? r.values[k] : null;
      return t + (finite(v) ? f.benchWeight(ctx.weights || {}, r.pos) * v : 0);
    }, 0);
  }

  var keyOf = function (r) { return String(r.player_key); };
  function after(roster, leaving, arriving) {
    var gone = new Set(leaving.map(keyOf));
    return roster.filter(function (r) { return !gone.has(keyOf(r)); }).concat(arriving);
  }

  var SENDER_TEXT = {
    better: function (p) { return {label: "Your roster gets about " + fmt(p) + " better", sentence: "Your roster gets about " + fmt(p) + " better."}; },
    unchanged: function (p) { return {label: "Your roster is about the same (" + fmt(p) + ")", sentence: "This barely changes your roster (about " + fmt(p) + ")."}; },
    slightly_worse: function (p) { return {label: "Your roster gets about " + fmt(p) + " worse", sentence: "This costs you about " + fmt(p) + " of your roster's value."}; },
    clearly_worse: function (p) { return {label: "Your roster gets about " + fmt(p) + " worse", sentence: "This costs you about " + fmt(p) + " of your roster's value, a real loss."}; }
  };
  var PARTNER_TEXT = {
    better: function (p) { return {label: "Their roster gets about " + fmt(p) + " better", sentence: "Their roster gets about " + fmt(p) + " better too, so there is something in it for them."}; },
    unchanged: function (p) { return {label: "Their roster is about the same (" + fmt(p) + ")", sentence: "This barely changes their roster (about " + fmt(p) + "), so they may still say yes."}; },
    slightly_worse: function (p) { return {label: "Their roster gets about " + fmt(p) + " worse", sentence: "It costs them about " + fmt(p) + " of their roster's value: a small cost they may accept if the trade fills a need."}; },
    clearly_worse: function (p) { return {label: "Their roster gets about " + fmt(p) + " worse", sentence: "It costs them about " + fmt(p) + " of their roster's value, a real loss, so they are unlikely to accept it as it stands."}; }
  };
  var UNSIZED = {label: "Not enough priced players to size this as a percent", sentence: ""};

  function rosterImprovementPct(trade, side, ctx) {
    ctx = ctx || {};
    var partner = side === "partner";
    var key = partner ? (ctx.partnerKey || MARKET_KEY) : (ctx.senderKey || OUR_KEY);
    var roster = (partner ? trade.theirs : trade.mine) || [];
    var leaving = (partner ? trade.receive : trade.give) || [], arriving = (partner ? trade.give : trade.receive) || [];
    var before = worth(roster, ctx, key), next = worth(after(roster, leaving, arriving), ctx, key);
    var delta = next - before;
    if (Math.abs(delta) < NET_FLOOR) delta = 0;
    var pct = finite(before) && before >= MIN_BASE ? 100 * delta / before : null;
    var band = bandOf(pct);
    var text = band === "unsized" ? UNSIZED : (partner ? PARTNER_TEXT : SENDER_TEXT)[band](pct);
    return {side: partner ? "partner" : "sender", key: key, before: before, after: next, delta: delta, pct: pct, shown: shownPct(pct),
      band: band, label: text.label, sentence: text.sentence};
  }

  // Tier wording (Jeremy 2026-11-07). Never a promise: "about", "we found".
  var HEADLINE = {big: "Big opportunity", medium: "A real opportunity", marginal: "A small edge", none: "No meaningful move right now"};
  function lineFor(tier, gain, pct) {
    var n = "about " + gain.toFixed(1) + " value (" + fmt(pct) + " of your team)";
    if (tier === "big") return "Your best move adds " + n + ", roughly two places in your league's value ranking.";
    if (tier === "medium") return "Your best move adds " + n + ", about one place in your league's value ranking.";
    if (tier === "marginal") return "Your best move adds " + n + ". Your roster is close to its best.";
    return "Your roster is already sharp: the best trade or pickup we found is within the normal noise of the values.";
  }
  function counted(x) { return x && finite(x.gain) && x.gain > NET_FLOOR && x.gain > (finite(x.tau) ? x.tau : 0) ? x.gain : 0; }
  function assess(o) {
    var w = o.worth, tg = counted(o.trade), wg = counted(o.waiver);
    var gain = Math.max(tg, wg);
    var pct = finite(w) && w >= MIN_BASE ? 100 * gain / w : null;
    var tier = gain > 0 ? tierOf(pct) : "none";
    return {tier: tier, pct: pct, shown: shownPct(pct), gain: gain, source: gain <= 0 ? null : tg >= wg ? "trade" : "waiver",
      waiversEmpty: wg <= 0, headline: HEADLINE[tier], line: lineFor(tier, gain, pct || 0), hole: o.hole || null};
  }

  // Where to look: the starting slot furthest below the league's median for that slot, valued on the Analyst charts.
  // teams: [{index, rows}] (every team with priced players). A slot whose player the charts do not price is skipped,
  // never read as 0; an empty starting slot is 0.
  function whereToLook(teams, meIndex, shape, chartKeys, weights) {
    var f = F(), keys = chartKeys || ANALYST;
    var slotVals = teams.map(function (t) {
      var L = f.lineupValue(f.withChartAverage(t.rows, keys), shape, MARKET_KEY), out = {};
      SLOTS.forEach(function (s) {
        for (var i = 0; i < (shape[s] || 0); i++) {
          var r = (L.slots[s] || [])[i];
          out[s + (i + 1)] = r ? (finite(r.values[MARKET_KEY]) ? r.values[MARKET_KEY] : null) : 0;
        }
      });
      return {index: t.index, slots: out, worth: worth(t.rows, {shape: shape, chartKeys: keys, weights: weights || {}}, MARKET_KEY)};
    });
    var mine = slotVals.find(function (t) { return t.index === meIndex; });
    if (!mine) return null;
    var best = null;
    Object.keys(mine.slots).forEach(function (s) {
      var vals = slotVals.map(function (t) { return t.slots[s]; }).filter(finite).sort(function (a, b) { return a - b; });
      if (!vals.length || !finite(mine.slots[s])) return;
      var m = vals.length >> 1, median = vals.length % 2 ? vals[m] : (vals[m - 1] + vals[m]) / 2;
      var gap = median - mine.slots[s];
      if (gap > NET_FLOOR && (!best || gap > best.gap)) best = {slot: s, gap: gap, value: mine.slots[s], median: median};
    });
    if (best) best.pct = mine.worth >= MIN_BASE ? 100 * best.gap / mine.worth : null;
    return best;
  }

  // Browser: the reader's opportunity on the live searches (DDF.find, the find.html defaults) and the Waivers tab's
  // candidates (an entered list in DDF.state 'available', else the league's available players). Waivers are never a
  // trade partner: partners are the league's other teams only.
  function candidates(cur) {
    var DDF = root.DDF, saved = null;
    try { saved = DDF.state ? DDF.state.get("available", null) : null; } catch (e) { saved = null; }
    var list = saved && Array.isArray(saved.players) ? saved.players.filter(function (p) { return p && typeof p.n === "string"; }) : [];
    if (list.length) {
      var recs = DDF.engine.players(), rows = recs.map(function (r) { return r.row; });
      var byRow = new Map(recs.map(function (r) { return [r.row, r]; }));
      return F().matchNames(list.map(function (p) { return {name: p.n, pos: p.pos || ""}; }), rows).matched
        .map(function (row) { var r = byRow.get(row); return {key: r.key, name: r.n, pos: r.pos, team: r.team}; });
    }
    return (cur.waivers || []).map(function (r) { return {key: r.key, name: r.n, pos: r.pos, team: r.team}; });
  }
  // Keeps the best move that beats its own noise floor; a move under its floor is kept only while none beats one
  // (each move has its own tau, so the biggest raw gain is not always the biggest counted gain).
  function better(best, gain, tau, extra) {
    if (!finite(gain)) return best;
    var c = {gain: gain, tau: tau};
    Object.keys(extra || {}).forEach(function (k) { c[k] = extra[k]; });
    if (!best) return c;
    var on = counted(c) > 0, bestOn = counted(best) > 0;
    if (on !== bestOn) return on ? c : best;
    return gain > best.gain ? c : best;
  }
  function computeTeam(cur, mine) {
    return new Promise(function (resolve) {
      setTimeout(function () {
        var DDF = root.DDF, ctx = DDF.find.context();
        if (!ctx || !ctx.shape) { resolve(null); return; }
        var mineRows = DDF.find.rowsOf(mine), w = worth(mineRows, ctx, OUR_KEY);
        var cand = candidates(cur), waiver = null;
        if (cand.length && root.TradeValueWaivers) {
          var pk = DDF.find.pickups(ctx, DDF.find.entriesOf(mine), cand, "DDF");
          pk.results.forEach(function (r) { waiver = better(waiver, r.totalDelta, r.tau); });
        }
        var trade = null, teams = [];
        cur.teams.forEach(function (t) {
          var rows = DDF.find.rowsOf(t);
          if (!rows.length) return;
          teams.push({index: t.index, rows: rows});
          if (t.index === mine.index) return;
          DDF.find.searchPartner(ctx, mineRows, rows, {your: "DDF", their: "Market", sizes: [1, 2]}).trades.forEach(function (tr) {
            if (tr.cls !== "natural") return;
            trade = better(trade, tr.fit.us.net, tr.fit.us.tau, {partner: t.index});
          });
        });
        var res = assess({worth: w, waiver: waiver, trade: trade, hole: whereToLook(teams, mine.index, ctx.shape, ctx.analyst || ANALYST, ctx.weights)});
        res.worth = w; res.trade = trade; res.waiver = waiver; res.candidates = cand.length;
        resolve(res);
      }, 0);
    });
  }

  var api = {MIN_BASE: MIN_BASE, TIERS: TIERS, BANDS: BANDS, HEADLINE: HEADLINE, tierOf: tierOf, bandOf: bandOf, shownPct: shownPct,
    worth: worth, rosterImprovementPct: rosterImprovementPct, assess: assess, whereToLook: whereToLook, computeTeam: computeTeam};
  if (isNode) { module.exports = api; return; }
  root.DDFOpportunity = api;
})(typeof window !== "undefined" ? window : this);
