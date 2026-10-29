/**
 * Shared roster convention: one definition of bench seats, starter line,
 * waiver line, flex allocation and tier basis.
 *
 * Ticket: JEG-559 (part of JEG-556).
 * Decisions: Jeremy 2026-10-10/12 (see JEG-556 comments).
 *
 * Every value path must call these functions. No other module may define its
 * own bench counts, starter line, waiver line or tier boundaries.
 *
 * Rules implemented:
 *   1. Bench seats: weight_p = starters_p * backups_per_starter_p (from
 *      config/market_bench.json), D'Hondt over teams * bench.
 *   2. Flex: greedy by points (projections) or by value (charts). Superflex
 *      includes QB.
 *   3. Starter line: midpoint of last starter and first non-starter.
 *   4. Waiver line: first player not rostered.
 *   5. Short lists: fill with real players from other sources, valued at the
 *      source's last listed value (imputation).
 *   6. Tier basis: rank within position on the list being valued.
 */
(function (exports) {
  "use strict";

  var POSITIONS = ["QB", "RB", "WR", "TE", "K", "DEF"];
  var SKILL_POSITIONS = ["QB", "RB", "WR", "TE"];
  var POS_ORDER = {};
  POSITIONS.forEach(function (p, i) { POS_ORDER[p] = i; });
  var FLEX_ELIGIBLE = ["RB", "WR", "TE"];
  var SUPERFLEX_ELIGIBLE = ["QB", "RB", "WR", "TE"];

  // Default roster: 1 QB / 2 RB / 2 WR / 1 TE / 1 FLEX / 1 K / 1 DEF, 7 bench.
  var DEFAULT_SLOTS = {QB: 1, RB: 2, WR: 2, TE: 1, K: 1, DEF: 1};
  var DEFAULT_FLEX = 1;
  var DEFAULT_SUPERFLEX = 0;
  var DEFAULT_BENCH = 7;
  var DEFAULT_TEAMS = 12;

  /**
   * Return backups-per-starter ratios.
   * Uses two_qb when the roster has 2+ QB slots or a superflex slot.
   *
   * @param {Object} marketBenchConfig - parsed config/market_bench.json
   * @param {Object} opts - {superflex: bool, qbSlots: number}
   * @returns {Object} {QB: number, RB: number, ...}
   */
  function marketBenchRatios(marketBenchConfig, opts) {
    opts = opts || {};
    var key = (opts.superflex || (opts.qbSlots || 1) >= 2) ? "two_qb" : "one_qb";
    var ratios = {};
    var src = marketBenchConfig[key].backups_per_starter;
    POSITIONS.forEach(function (p) {
      ratios[p] = src[p] !== undefined ? src[p] : 0;
    });
    return ratios;
  }

  /**
   * Convention rule 1: bench weight per position.
   * weight_p = starters_p * backups_per_starter_p.
   */
  function benchWeights(slots, ratios, flexFilled) {
    flexFilled = flexFilled || {};
    var weights = {};
    POSITIONS.forEach(function (pos) {
      var starters = (slots[pos] || 0) + (flexFilled[pos] || 0);
      weights[pos] = starters * (ratios[pos] || 0);
    });
    return weights;
  }

  /**
   * D'Hondt (highest averages) seat allocation.
   * Ties go to position order (earliest in POSITIONS wins).
   */
  function dhondtAllocate(weights, total) {
    if (total < 0 || Math.floor(total) !== total) {
      throw new Error("total must be a nonnegative integer");
    }
    var seats = {};
    POSITIONS.forEach(function (p) { seats[p] = 0; });
    var eligible = POSITIONS.filter(function (p) { return (weights[p] || 0) > 0; });
    if (total > 0 && !eligible.length) {
      throw new Error("positive total requires at least one positive weight");
    }
    for (var i = 0; i < total; i++) {
      var best = null, bestScore = -Infinity;
      eligible.forEach(function (p) {
        var score = weights[p] / (seats[p] + 1);
        if (score > bestScore || (score === bestScore && POS_ORDER[p] < POS_ORDER[best])) {
          best = p;
          bestScore = score;
        }
      });
      seats[best] += 1;
    }
    return seats;
  }

  /**
   * Convention rule 1: D'Hondt bench allocation using market bench ratios.
   * Returns {pos: bench_count} across the entire league.
   */
  function benchSeats(slots, teams, benchPerTeam, ratios, opts) {
    opts = opts || {};
    var ff = opts.flexFilled || {};
    var w = benchWeights(slots, ratios, ff);
    return dhondtAllocate(w, teams * benchPerTeam);
  }

  /**
   * Convention rule 2: greedy flex allocation by score.
   * remaining[pos] = [key, ...] sorted best-first.
   * scores[key] = score to rank by.
   */
  function flexAllocateGreedy(remaining, scores, count, eligible) {
    var candidates = [];
    eligible.forEach(function (pos) {
      (remaining[pos] || []).forEach(function (key) {
        if (scores[key] !== undefined) {
          candidates.push({pos: pos, key: key, score: scores[key]});
        }
      });
    });
    candidates.sort(function (a, b) {
      if (a.score !== b.score) return b.score - a.score;
      if (POS_ORDER[a.pos] !== POS_ORDER[b.pos]) return POS_ORDER[a.pos] - POS_ORDER[b.pos];
      return (a.key < b.key ? -1 : a.key > b.key ? 1 : 0);
    });
    var filled = {};
    POSITIONS.forEach(function (p) { filled[p] = 0; });
    var n = Math.max(0, count);
    for (var i = 0; i < Math.min(n, candidates.length); i++) {
      filled[candidates[i].pos] += 1;
    }
    return filled;
  }

  /**
   * Convention rule 3: starter line = midpoint of last starter and first
   * non-starter.
   * values: sorted descending. starters: count at this position.
   */
  function starterLine(values, starters) {
    if (starters <= 0 || values.length < starters) return null;
    var lastStarter = values[starters - 1];
    if (values.length > starters) {
      var firstBench = values[starters];
      return (lastStarter + firstBench) / 2.0;
    }
    return lastStarter;
  }

  /**
   * Convention rule 4: waiver line = the first player not rostered.
   * values: sorted descending. rostered: starters + bench at this position.
   */
  function waiverLine(values, rostered) {
    if (rostered <= 0 || values.length === 0) return null;
    if (values.length > rostered) return values[rostered];
    return values[values.length - 1];
  }

  /**
   * JEG-1047 (Jeremy, 2026-10-29: "A"): a projection source's waiver line is
   * the average of the 7 players around the first non-rostered seat.
   * Twin of roster_convention.waiver_band_line.
   */
  var WAIVER_BAND_HALF_WIDTH = 3;

  function waiverBandLine(values, rostered, halfWidth) {
    var h = halfWidth == null ? WAIVER_BAND_HALF_WIDTH : halfWidth;
    if (rostered <= 0 || values.length === 0) return null;
    if (values.length <= rostered) return values[values.length - 1];
    var lo = Math.max(0, rostered - h), hi = Math.min(values.length, rostered + h + 1);
    var sum = 0;
    for (var i = lo; i < hi; i++) sum += values[i];
    return sum / (hi - lo);
  }

  /**
   * Full league allocation: dedicated + superflex + flex + bench.
   * Returns {pos: {dedicated, superflex, flex, bench, starters, rostered}}.
   */
  function allocateLeague(slots, teams, benchPerTeam, flexCount, superflexCount,
                          playerOrder, playerScores, ratios, opts) {
    opts = opts || {};
    var flexEligible = opts.flexEligible || FLEX_ELIGIBLE;
    var superflexEligible = opts.superflexEligible || SUPERFLEX_ELIGIBLE;
    var t = teams;

    // Dedicated slots
    var dedicated = {};
    POSITIONS.forEach(function (p) { dedicated[p] = t * (slots[p] || 0); });

    // Remaining after dedicated
    var remainAfterDed = {};
    POSITIONS.forEach(function (p) {
      var order = playerOrder[p] || [];
      remainAfterDed[p] = order.slice(dedicated[p]);
    });

    // Superflex: greedy across all positions
    var sfFilled = flexAllocateGreedy(
      remainAfterDed, playerScores,
      t * superflexCount, superflexEligible
    );

    // Remaining after superflex
    var remainAfterSf = {};
    POSITIONS.forEach(function (p) {
      remainAfterSf[p] = remainAfterDed[p].slice(sfFilled[p]);
    });

    // Flex: greedy across flex-eligible
    var fxFilled = flexAllocateGreedy(
      remainAfterSf, playerScores,
      t * flexCount, flexEligible
    );

    // Bench: convention rule 1
    var effectiveFlex = {};
    POSITIONS.forEach(function (p) {
      effectiveFlex[p] = sfFilled[p] + fxFilled[p];
    });

    var b = benchSeats(slots, teams, benchPerTeam, ratios, {flexFilled: effectiveFlex});

    var out = {};
    POSITIONS.forEach(function (pos) {
      var s = dedicated[pos] + sfFilled[pos] + fxFilled[pos];
      out[pos] = {
        dedicated: dedicated[pos],
        superflex: sfFilled[pos],
        flex: fxFilled[pos],
        bench: b[pos],
        starters: s,
        rostered: s + b[pos]
      };
    });
    return out;
  }

  /**
   * Compute starter line and waiver line for one position.
   */
  function computeLines(values, starters, rostered) {
    var sl = starterLine(values, starters);
    var wl = waiverLine(values, rostered);
    if (sl !== null && wl !== null) {
      sl = Math.max(sl, wl);
    }
    var method = "roster_determined";
    if (values.length < rostered) method = "insufficient_coverage";
    if (values.length === 0) {
      method = "no_players";
      sl = null;
      wl = null;
    }
    return {starter_line: sl, waiver_line: wl, method: method};
  }

  // Export
  exports.RosterConvention = {
    POSITIONS: POSITIONS,
    SKILL_POSITIONS: SKILL_POSITIONS,
    POS_ORDER: POS_ORDER,
    FLEX_ELIGIBLE: FLEX_ELIGIBLE,
    SUPERFLEX_ELIGIBLE: SUPERFLEX_ELIGIBLE,
    DEFAULT_SLOTS: DEFAULT_SLOTS,
    DEFAULT_FLEX: DEFAULT_FLEX,
    DEFAULT_SUPERFLEX: DEFAULT_SUPERFLEX,
    DEFAULT_BENCH: DEFAULT_BENCH,
    DEFAULT_TEAMS: DEFAULT_TEAMS,
    marketBenchRatios: marketBenchRatios,
    benchWeights: benchWeights,
    dhondtAllocate: dhondtAllocate,
    benchSeats: benchSeats,
    flexAllocateGreedy: flexAllocateGreedy,
    starterLine: starterLine,
    waiverLine: waiverLine,
    WAIVER_BAND_HALF_WIDTH: WAIVER_BAND_HALF_WIDTH,
    waiverBandLine: waiverBandLine,
    allocateLeague: allocateLeague,
    computeLines: computeLines
  };

})(typeof module !== "undefined" && module.exports ? module.exports : (this.window = this.window || {}));
