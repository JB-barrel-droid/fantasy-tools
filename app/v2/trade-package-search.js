// JEG-1183: greedy, re-checked package selection (decision 2026-10-29).
// Pure companion to package-composition-preview.js; the preview remains display-only.
// selectPackage(league, candidates, ctx) consumes a COMPLETE opportunities result, not its
// paginated/capPerCore display. ctx is the same pricing snapshot as opportunities.computePairing:
// {rowsByKey: Map, shape, expected, weights?, charts, market, keepMine?, keepTheirs?,
//  minCharts?, guardrails?}. Do not mix candidates and a different engine snapshot.
// Uses the existing finder gates, live viabilityLabel and opportunity order; never prices
// players or invents offers. Re-ranks all remaining legal candidates after each pick.
// Greedy is deterministic, not an exhaustive global optimum. A later route adapter owns
// loading this module and handing its trades to the selected-package preview.
(function (root) {
  "use strict";
  const node = typeof module !== "undefined" && module.exports;
  const deps = () => node ? {
    F: require("./finder.js"), O: require("./opportunities.js"), P: require("./trade-package-constraints.js")
  } : {F: root.TradeValueFinder, O: root.TradeValueOpportunities, P: root.TradePackageConstraints};
  const finite = n => typeof n === "number" && Number.isFinite(n);
  const keyOf = r => String(r && typeof r === "object" ? (r.key ?? r.player_key) : r);
  const failure = (code, message, errors) => ({ok: false, status: "unavailable", method: "greedy_rechecked",
    errors: errors || [{code, message}], trades: [], league: null, edge: null});

  function selectPackage(league, candidates, ctx) {
    const {F, O, P} = deps();
    if (!F || !O || !P) return failure("missing_helpers", "Package search helpers are unavailable.");
    const baseline = P.applyPackage(league, []);
    if (!baseline.ok) return failure("bad_league", "The league could not be read.", baseline.errors);
    if (!Array.isArray(candidates)) return failure("bad_candidates", "Candidates must be the complete opportunity rows.");
    if (!ctx || !(ctx.rowsByKey instanceof Map) || !ctx.shape || !ctx.expected
      || !Array.isArray(ctx.charts) || !Array.isArray(ctx.market) || ctx.market.length < F.MIN_CHARTS
      || !ctx.market.every(k => ctx.charts.includes(k))) {
      return failure("missing_context", "The completed opportunity search's pricing and roster context is required.");
    }
    // Unpriced K/DEF entries stay in the helper's rosters; they are never guessed into a valued lineup.
    for (const team of baseline.league.teams) {
      for (const entry of team.entries) {
        if (!ctx.rowsByKey.has(String(entry.key)) && !F.isNotEvaluated(entry)) {
          return failure("missing_player", `No pricing row for ${entry.key}.`);
        }
      }
    }
    const rowsFor = team => F.withChartAverage(team.entries.map(e => ctx.rowsByKey.get(String(e.key))).filter(Boolean), ctx.market);
    const trades = [];
    let current = baseline.league;
    let edge = 0;
    while (true) {
      const mine = rowsFor(current.teams.find(t => t.id === current.myTeamId));
      const ranked = [];
      for (const candidate of candidates) {
        // Original league + entire prefix enforces original ownership, team-once and
        // player-once together. Validating only the next trade would permit re-trading arrivals.
        if (!P.validatePackage(league, trades.concat([candidate])).ok) continue;
        const opponent = current.teams.find(t => t.id === String(candidate.opponentId));
        const theirs = rowsFor(opponent);
        const byKey = new Map(mine.concat(theirs).map(r => [String(r.player_key), r]));
        const give = candidate.give.map(r => byKey.get(keyOf(r)));
        const receive = candidate.receive.map(r => byKey.get(keyOf(r)));
        // Missing moving values are unavailable, never the zero fallback in viabilityLabel.
        if (!give.concat(receive).every(r => r && r.values && finite(r.values[F.OUR_KEY]) && finite(r.values[F.MARKET_KEY]))) continue;
        const judged = F.evaluateCombo(give, receive, {ourKey: F.OUR_KEY, chartKeys: ctx.charts,
          minCharts: ctx.minCharts || Math.min(F.SEARCH_MIN_CHARTS, ctx.charts.length),
          sanity: {shape: ctx.shape, mineCounts: mine, theirCounts: theirs,
            keepMine: ctx.keepMine !== false, keepTheirs: ctx.keepTheirs !== false},
          ...(ctx.guardrails ? {guardrails: {...ctx.guardrails, shape: ctx.shape, ourKey: F.OUR_KEY,
            chartKeys: ctx.market, mine, theirs}} : {})});
        if (!Object.values(judged.passes).every(Boolean)) continue;
        const fit = F.tradeFit({mine: {roster: mine, leaving: give, arriving: receive},
          theirs: {roster: theirs, leaving: receive, arriving: give}},
        {shape: ctx.shape, expected: ctx.expected, weights: ctx.weights, ourKey: F.OUR_KEY,
          marketKey: F.MARKET_KEY, chartKeys: ctx.market, z: F.FIT_Z});
        const viability = F.viabilityLabel(fit, mine, theirs, give, receive, ctx.shape, F.OUR_KEY, ctx.market);
        if (!viability) continue;
        // Ignore stale candidate rank/edge/fit and resolve identities from the pricing snapshot.
        const id = `${opponent.id}|${give.map(keyOf).sort()}|${receive.map(keyOf).sort()}`;
        ranked.push({id, opponentId: opponent.id, opponent: opponent.name || opponent.id,
          give, receive, edge: judged.edge, score: judged.score, size: give.length + receive.length,
          charts: judged.charts, pricedCharts: judged.pricedCharts, rivalOkCount: judged.rivalOkCount,
          overall: fit.label, tier: O.TIERS[fit.label], fit, viability});
      }
      if (!ranked.length) break;
      const next = O.rankRows(ranked)[0];
      const applied = P.applyTrade(current, next);
      if (!applied.ok) return failure("apply_failed", "The selected trade could not be applied.", applied.errors);
      trades.push({...next, rank: trades.length + 1});
      edge += next.edge;
      current = applied.league;
    }
    return {ok: true, status: trades.length ? "ready" : "empty", method: "greedy_rechecked",
      errors: [], trades, league: current, edge};
  }
  const api = {selectPackage};
  if (node) { module.exports = api; return; }
  root.TradeValuePackageSearch = api;
})(typeof window !== "undefined" ? window : globalThis);
