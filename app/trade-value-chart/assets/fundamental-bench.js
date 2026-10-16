/**
 * Fundamental bench module: net-of-waiver value per bench spot by position
 * and depth.
 *
 * Ticket: JEG-564 (part of JEG-556).
 * Decision: Jeremy, 2026-10-10: "research + advice later. The fundamental
 * bench stays in Later. It never feeds values, tiers or waiver lines."
 *
 * This module is SEPARATE from the market bench convention
 * (roster-convention.js). The market bench sets tiers and the waiver line.
 * The fundamental bench NEVER does -- the parity test asserts this.
 *
 * Uses:
 *   - Roster advice (market vs fundamental gap)
 *   - Research content (JEG-557)
 *   - Expected-starts bench component (JEG-562, when it lands)
 *
 * Data: 2015-2025 history, pooled across 3 scorings x 4 league sizes.
 * No hindsight.
 */
(function (exports) {
  "use strict";

  // Pooled net-of-waiver ladder, sorted best-first.
  // Source: JEG-556 comment "Bench value net of the waiver alternative"
  // Units: net points per week per held player
  var LADDER = [
    {position: "RB", depth: 1, insurance: 0.33, upside: 0.07, total: 0.40, label: "1st backup RB"},
    {position: "WR", depth: 1, insurance: 0.15, upside: 0.05, total: 0.20, label: "1st backup WR"},
    {position: "WR", depth: 2, insurance: 0.12, upside: 0.05, total: 0.17, label: "2nd backup WR"},
    {position: "QB", depth: 1, insurance: 0.15, upside: 0.02, total: 0.17, label: "1st backup QB"},
    {position: "RB", depth: 2, insurance: 0.12, upside: 0.03, total: 0.15, label: "2nd backup RB"},
    {position: "TE", depth: 1, insurance: 0.04, upside: 0.05, total: 0.09, label: "1st backup TE"},
    {position: "RB", depth: 3, insurance: 0.03, upside: 0.01, total: 0.04, label: "3rd backup RB"},
    {position: "WR", depth: 3, insurance: 0.03, upside: 0.01, total: 0.04, label: "3rd backup WR"},
    {position: "QB", depth: 2, insurance: 0.00, upside: 0.00, total: 0.00, label: "2nd backup QB"},
    {position: "TE", depth: 2, insurance: 0.00, upside: 0.00, total: 0.00, label: "2nd backup TE"}
  ];

  var FINDINGS = {
    qb_te_upside_zero: "QB and TE upside nets to about zero in every setting; whatever a backup QB/TE might become, you can pick it up when it happens",
    second_qb_te_worthless: "Second QB/TE backups are worth about zero net of waivers",
    rb_most_reliable: "RB is the most reliable bench value (first backup +0.24 to +0.55 across settings)",
    everything_small: "Net of waivers, a bench spot is worth 0-0.5 points a week"
  };

  /**
   * Return the pooled net-of-waiver ladder, sorted best-first.
   * Each entry: {position, depth, insurance, upside, total, label}.
   */
  function ladder() {
    return LADDER.map(function (e) { return Object.assign({}, e); });
  }

  /**
   * Return net-of-waiver value for one bench slot.
   * @param {string} position - "QB", "RB", "WR", or "TE"
   * @param {number} depth - 1 = first backup, 2 = second, etc.
   * @returns {{insurance: number, upside: number, total: number}}
   */
  function benchValue(position, depth) {
    for (var i = 0; i < LADDER.length; i++) {
      var e = LADDER[i];
      if (e.position === position && e.depth === depth) {
        return {insurance: e.insurance, upside: e.upside, total: e.total};
      }
    }
    return {insurance: 0, upside: 0, total: 0};
  }

  /**
   * Allocate bench spots by fundamental value (greedy, best-first).
   * @param {number} benchSpots - number of bench spots to fill
   * @returns {Array} entries from the ladder, in priority order
   */
  function optimalBench(benchSpots) {
    return LADDER.slice(0, Math.max(0, benchSpots)).map(function (e) {
      return Object.assign({}, e);
    });
  }

  /**
   * How many backups per position to hold, given benchSpots.
   * @param {number} benchSpots
   * @returns {{QB: number, RB: number, WR: number, TE: number}}
   */
  function benchSummary(benchSpots) {
    var picks = optimalBench(benchSpots);
    var counts = {QB: 0, RB: 0, WR: 0, TE: 0};
    picks.forEach(function (p) {
      if (counts[p.position] !== undefined) {
        counts[p.position] += 1;
      }
    });
    return counts;
  }

  /**
   * Return research findings as {key: sentence}.
   */
  function findings() {
    return Object.assign({}, FINDINGS);
  }

  exports.FundamentalBench = {
    LADDER: LADDER,
    FINDINGS: FINDINGS,
    ladder: ladder,
    benchValue: benchValue,
    optimalBench: optimalBench,
    benchSummary: benchSummary,
    findings: findings
  };

})(typeof module !== "undefined" && module.exports ? module.exports : (this.window = this.window || {}));
