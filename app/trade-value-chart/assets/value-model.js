// Shared value model for the trade-value chart.
//
// Why this file exists: the curve widget and the player table each carried
// their OWN copy of the role map, the fixed-pie normalisation and the roster
// allocation. Two implementations of one invariant drift, and nothing catches
// it because each stays internally consistent. They had already drifted --
// the table rendered Jahmyr Gibbs at 76.5 for the ESPN leg while the curve
// above it peaked at 69.5 for the same source, on the same page load.
//
// Everything here is PURE: no module state, no DOM, no closures over league
// settings. Callers pass what they have. That is what makes the two callers
// testable against each other (see the divergence test), which is the only
// thing that keeps them from drifting again.
//
// Ordering note: player order comes from the ACTIVE LOCK, never from a
// preseason consensus rank. A positional rank is not an overall ordering --
// four players share rank 1 -- so using it put the QB1 at x=1 ahead of the
// RB1, which read as "Josh Allen is the most valuable asset in fantasy".
(function (root) {
  "use strict";

  var POSITION_ORDER = ["QB", "RB", "WR", "TE"];
  var DEFAULT_FLEX_ELIGIBLE = ["RB", "WR", "TE"];
  // Minimum shared players before a source may be anchored on the shared set.
  var MIN_SHARED_FOR_PIE = 40;

  function flexEligible(shape) {
    return shape && shape.SUPERFLEX
      ? ["QB"].concat(DEFAULT_FLEX_ELIGIBLE)
      : DEFAULT_FLEX_ELIGIBLE.slice();
  }

  // Stable, preseason-free tiebreak. Values decide order; this only settles
  // exact ties so the ordering is deterministic across reloads and callers.
  function stableTiebreak(a, b) {
    if (!a || !b) return 0;
    return String(a.name || "").localeCompare(String(b.name || ""))
      || (Number(a.player_key) - Number(b.player_key));
  }

  // Who is a starter, who is bench, who is waiver -- by VALUE under the
  // active lock, filling dedicated slots first, then flex, then bench.
  function roleMap(opts) {
    var values = opts.values;
    var playerOf = opts.playerOf;
    var teams = Number(opts.teams) || 0;
    var shape = opts.shape || {};
    var rows = [];
    values.forEach(function (value, playerKey) {
      var player = playerOf(playerKey);
      var numeric = Number(value);
      if (!player || POSITION_ORDER.indexOf(player.pos) === -1) return;
      if (!isFinite(numeric) || !(numeric > 0)) return;
      rows.push({ playerKey: playerKey, value: numeric, player: player });
    });
    rows.sort(function (a, b) {
      return b.value - a.value || stableTiebreak(a.player, b.player);
    });

    var roles = new Map();
    POSITION_ORDER.forEach(function (pos) {
      rows.filter(function (row) { return row.player.pos === pos; })
        .slice(0, teams * (Number(shape[pos]) || 0))
        .forEach(function (row) { roles.set(row.playerKey, "starter"); });
    });
    var elig = flexEligible(shape);
    rows.filter(function (row) {
      return elig.indexOf(row.player.pos) !== -1 && !roles.has(row.playerKey);
    }).slice(0, teams * (Number(shape.FLEX) || 0))
      .forEach(function (row) { roles.set(row.playerKey, "starter"); });
    rows.filter(function (row) { return !roles.has(row.playerKey); })
      .slice(0, teams * (Number(shape.BENCH) || 0))
      .forEach(function (row) { roles.set(row.playerKey, "bench"); });
    return roles;
  }

  // Players the anchor prices but this source does not are NOT part of this
  // source's pie. Scaling a 124-player chart and a 350-player anchor to the
  // SAME total forces the thinner chart's curve taller everywhere. Both sides
  // must be measured on the shared set, or the scale is short by whatever
  // sits outside the overlap.
  function sharedPieBasis(opts) {
    var values = opts.values;
    var anchor = opts.anchor;
    var playerOf = opts.playerOf;
    if (!anchor || !anchor.size) return null;
    var keys = new Set();
    var target = 0;
    values.forEach(function (value, playerKey) {
      var player = playerOf(playerKey);
      if (!player || POSITION_ORDER.indexOf(player.pos) === -1) return;
      var anchorValue = anchor.get(playerKey);
      if (!isFinite(anchorValue) || !isFinite(Number(value))) return;
      keys.add(playerKey);
      target += Math.max(0, anchorValue);
    });
    if (keys.size < MIN_SHARED_FOR_PIE || !(target > 0)) return null;
    return { keys: keys, target: target };
  }

  // The share of a value set's own pie that sits on bench players, measured
  // with the SAME role model the charts are normalised with.
  //
  // Why this is not a constant: the anchor is the two-tier leg, built by
  // the pipeline at its own starter/bench split. Forcing every chart to a
  // hardcoded 0.15 re-splits them AWAY from the anchor they are supposed to
  // match -- the charts' bench ends up marked up relative to the anchor's,
  // for no reason except that the constant disagreed with the leg.
  // Returns null when there is nothing to measure, so the caller can fall
  // back rather than invent a split.
  function benchShareOf(opts) {
    var values = opts.values;
    var roles = opts.roles || roleMap(opts);
    var starter = 0, bench = 0;
    values.forEach(function (value, playerKey) {
      var v = isFinite(Number(value)) ? Math.max(0, Number(value)) : 0;
      var role = roles.get(playerKey);
      if (role === "starter") starter += v;
      else if (role === "bench") bench += v;
    });
    var total = starter + bench;
    if (!(total > 0) || !(bench > 0)) return null;
    return bench / total;
  }

  // Scale a series onto the anchor's pie WITHOUT re-splitting its tiers.
  //
  // For the raw value-above-waivers series this is the whole job: its shape
  // is deliberately its own (it is the un-adjusted curve), but its LEVEL has
  // to be the anchor's or it is not on the same chart. Scaling it to the sum
  // of the positional targets instead left it 15.7 points above the anchor's
  // total over the players they share, because the anchor prices players the
  // raw series has no projection for.
  function scaleToSharedTotal(opts) {
    var values = opts.values;
    var basis = sharedPieBasis(opts);
    if (!basis) return new Map(values);
    var total = 0;
    values.forEach(function (value, playerKey) {
      if (!basis.keys.has(playerKey)) return;
      var v = Number(value);
      if (isFinite(v) && v > 0) total += v;
    });
    var scale = total > 0 ? basis.target / total : 1;
    var out = new Map();
    values.forEach(function (value, playerKey) {
      var v = Number(value);
      out.set(playerKey, isFinite(v) ? Math.max(0, v) * scale : 0);
    });
    return out;
  }

  // Starters marked up, bench marked down, to the shared-set target.
  function normalizeToFixedPie(opts) {
    var values = opts.values;
    var share = Number(opts.share);
    var roles = opts.roles || roleMap(opts);
    var basis = sharedPieBasis(opts);
    var inBasis = function (playerKey) { return !basis || basis.keys.has(playerKey); };

    var starterTotal = 0, benchTotal = 0;
    values.forEach(function (value, playerKey) {
      if (!inBasis(playerKey)) return;
      var safe = isFinite(Number(value)) ? Math.max(0, Number(value)) : 0;
      var role = roles.get(playerKey);
      if (role === "starter") starterTotal += safe;
      else if (role === "bench") benchTotal += safe;
    });

    var target = basis ? basis.target
      : (typeof opts.fallbackTarget === "function"
          ? opts.fallbackTarget(starterTotal + benchTotal)
          : starterTotal + benchTotal);
    var starterShare = Math.max(0, Math.min(1, 1 - share));
    var benchShare = Math.max(0, Math.min(1, share));
    var starterScale = starterTotal > 0 && target > 0 ? (target * starterShare) / starterTotal : 0;
    var benchScale = benchTotal > 0 && target > 0 ? (target * benchShare) / benchTotal : 0;

    var out = new Map();
    values.forEach(function (value, playerKey) {
      var role = roles.get(playerKey) || "waiver";
      var safe = isFinite(Number(value)) ? Math.max(0, Number(value)) : 0;
      out.set(playerKey, role === "starter" ? safe * starterScale
        : role === "bench" ? safe * benchScale : 0);
    });
    return out;
  }

  // Cross-source scale agreement, as a pure comparison so it can be tested
  // against the numbers the defect actually produced.
  //
  // Every pie check compares TOTALS, and the totals agreed to a rounding
  // error while the ESPN line was a different valuation model: RB peak 99.1
  // against the published charts' 75-80, QB peak 12.5 against their
  // 16.0-16.9. A total is blind to shape. This compares where each
  // position's curve starts, which is what a reader is looking at.
  //
  // Band: healthy peak ratios span 0.94-1.05 on live data; the defect ran to
  // 1.39 (QB) and 1.61 (TE). 0.80/1.25 clears the healthy spread four times
  // over and still catches the defect on every position it touched.
  var PEAK_AGREEMENT_LOW = 0.80;
  var PEAK_AGREEMENT_HIGH = 1.25;

  function peakAgreement(opts) {
    var anchorPeaks = opts.anchorPeaks || {};
    var sources = opts.sources || {};
    var low = isFinite(Number(opts.low)) ? Number(opts.low) : PEAK_AGREEMENT_LOW;
    var high = isFinite(Number(opts.high)) ? Number(opts.high) : PEAK_AGREEMENT_HIGH;
    var label = opts.labelOf || function (key) { return key; };
    var offenders = [];
    var compared = 0;
    Object.keys(sources).forEach(function (key) {
      var peaks = sources[key] || {};
      POSITION_ORDER.forEach(function (pos) {
        var a = Number(anchorPeaks[pos]), v = Number(peaks[pos]);
        // A position the anchor or the source does not price is not evidence
        // either way; a NaN peak is a different failure (validValues).
        if (!isFinite(a) || !(a > 0) || !isFinite(v) || !(v > 0)) return;
        compared += 1;
        var ratio = v / a;
        if (ratio < low || ratio > high) {
          offenders.push(label(key) + " " + pos + " " + v.toFixed(1) +
            " vs anchor " + a.toFixed(1) + " (" + ratio.toFixed(2) + "x)");
        }
      });
    });
    return {ok: compared > 0 && offenders.length === 0, compared: compared,
            offenders: offenders, band: [low, high]};
  }

  // Roster allocation. `rankOf` returns a sortable projection for a player --
  // higher is better, in that position's own units.
  //
  // Cross-position comparisons (the flex slot, the bench) may NOT use those
  // units directly. Ranking the pool by raw per-game points lets quarterbacks
  // monopolise the bench because they simply score more, which pushes the QB
  // waiver line far down the board and inflates every QB's value above it --
  // Josh Allen ends up the most valuable asset in a 1QB league. A preseason
  // positional rank was the old workaround, and it was worse: four players
  // share rank 1, so the QB1 sorted ahead of the RB1 at x=1.
  //
  // Instead, compare on surplus over each position's OWN dedicated-starter
  // baseline. That baseline is fixed by the league's slot counts, so it is
  // not circular, and it makes a point of RB surplus mean the same as a point
  // of QB surplus.
  // Assign starter / bench / waiver from PROJECTIONS, using the same
  // surplus-over-baseline comparison as allocationCounts. Returns a Map of
  // player_key -> role. The ESPN leg needs the roles (to find each position's
  // waiver baseline), not just the counts, and it used to assign them inline
  // by raw per-game points -- which filled the bench with quarterbacks and
  // drove the QB waiver line through the floor.
  function projectionRoles(opts) {
    var pool = opts.pool || [];
    var teams = Number(opts.teams) || 0;
    var shape = opts.shape || {};
    var rankOf = opts.rankOf;

    var byPos = {}, direct = {};
    POSITION_ORDER.forEach(function (pos) {
      direct[pos] = teams * (Number(shape[pos]) || 0);
      byPos[pos] = pool.filter(function (p) {
        return p.pos === pos && isFinite(rankOf(p));
      }).sort(function (a, b) { return rankOf(b) - rankOf(a) || stableTiebreak(a, b); });
    });

    var baseline = {};
    POSITION_ORDER.forEach(function (pos) {
      var list = byPos[pos];
      if (!list.length) { baseline[pos] = 0; return; }
      var idx = Math.min(Math.max(direct[pos] - 1, 0), list.length - 1);
      baseline[pos] = rankOf(list[idx]);
    });
    var surplus = function (p) { return rankOf(p) - (baseline[p.pos] || 0); };

    var roles = new Map();
    POSITION_ORDER.forEach(function (pos) {
      byPos[pos].slice(0, direct[pos]).forEach(function (p) { roles.set(p.player_key, "starter"); });
    });
    var remaining = function (positions) {
      var out = [];
      positions.forEach(function (pos) {
        byPos[pos].forEach(function (p) { if (!roles.has(p.player_key)) out.push(p); });
      });
      return out.sort(function (a, b) { return surplus(b) - surplus(a) || stableTiebreak(a, b); });
    };
    remaining(flexEligible(shape)).slice(0, teams * (Number(shape.FLEX) || 0))
      .forEach(function (p) { roles.set(p.player_key, "starter"); });
    remaining(POSITION_ORDER).slice(0, teams * (Number(shape.BENCH) || 0))
      .forEach(function (p) { roles.set(p.player_key, "bench"); });
    return { roles: roles, direct: direct, baseline: baseline };
  }

  // Raw points above a positional waiver line are NOT comparable across
  // positions: a quarterback point is worth less because a league starts one
  // of them. The positional pie corrects that, and the ESPN leg used to skip
  // it entirely -- one global starter/bench scale over the whole pool -- which
  // left every QB at roughly double what the published charts price them at.
  //
  // Pre-scaling raw surplus to the pie and THEN splitting does not work: the
  // pie targets already encode the split, so the pre-scaled pool arrives at a
  // 85.3% starter share and the markup inverts. The scales have to be solved
  // per position and per tier at once.
  //
  // starterScale[pos] = target[pos] * (1 - share) / starterRaw[pos]
  // benchScale[pos]   = target[pos] *      share  / benchRaw[pos]
  //
  // Each position then lands on its own pie, and because every position splits
  // the same way, the whole pool lands on the 85/15 identity too.
  function positionalTierScales(rows, targetFor, share) {
    var starterRaw = {}, benchRaw = {};
    POSITION_ORDER.forEach(function (pos) { starterRaw[pos] = 0; benchRaw[pos] = 0; });
    rows.forEach(function (row) {
      if (POSITION_ORDER.indexOf(row.pos) === -1) return;
      var v = Number(row.value);
      if (!isFinite(v) || v <= 0) return;
      if (row.role === "starter") starterRaw[row.pos] += v;
      else if (row.role === "bench") benchRaw[row.pos] += v;
    });
    var starterShare = Math.max(0, Math.min(1, 1 - Number(share)));
    var benchShare = Math.max(0, Math.min(1, Number(share)));
    var starter = {}, bench = {}, target = {};
    POSITION_ORDER.forEach(function (pos) {
      var t = Number(targetFor(pos));
      target[pos] = isFinite(t) && t > 0 ? t : 0;
      // Fail closed to 0 rather than inventing a scale from an empty tier.
      starter[pos] = starterRaw[pos] > 0 && target[pos] > 0
        ? (target[pos] * starterShare) / starterRaw[pos] : 0;
      bench[pos] = benchRaw[pos] > 0 && target[pos] > 0
        ? (target[pos] * benchShare) / benchRaw[pos] : 0;
    });
    return { starter: starter, bench: bench, starterRaw: starterRaw,
             benchRaw: benchRaw, target: target };
  }

  // Counts only -- the roles come from projectionRoles, so there is exactly
  // one ordering rule in this file.
  function allocationCounts(opts) {
    var assigned = projectionRoles(opts);
    var direct = assigned.direct;
    var lineup = Object.assign({}, direct);
    var rostered = Object.assign({}, direct);
    var seenDirect = {};
    POSITION_ORDER.forEach(function (pos) { seenDirect[pos] = 0; });
    (opts.pool || []).slice().sort(function (a, b) {
      return opts.rankOf(b) - opts.rankOf(a) || stableTiebreak(a, b);
    }).forEach(function (p) {
      if (POSITION_ORDER.indexOf(p.pos) === -1) return;
      var role = assigned.roles.get(p.player_key);
      if (!role) return;
      if (role === "starter" && seenDirect[p.pos] < direct[p.pos]) { seenDirect[p.pos] += 1; return; }
      if (role === "starter") { lineup[p.pos] += 1; rostered[p.pos] += 1; return; }
      rostered[p.pos] += 1;
    });
    return { direct: direct, lineup: lineup, rostered: rostered };
  }

  root.ValueModel = {
    POSITION_ORDER: POSITION_ORDER,
    DEFAULT_FLEX_ELIGIBLE: DEFAULT_FLEX_ELIGIBLE,
    MIN_SHARED_FOR_PIE: MIN_SHARED_FOR_PIE,
    flexEligible: flexEligible,
    stableTiebreak: stableTiebreak,
    roleMap: roleMap,
    projectionRoles: projectionRoles,
    positionalTierScales: positionalTierScales,
    sharedPieBasis: sharedPieBasis,
    benchShareOf: benchShareOf,
    scaleToSharedTotal: scaleToSharedTotal,
    PEAK_AGREEMENT_LOW: PEAK_AGREEMENT_LOW,
    PEAK_AGREEMENT_HIGH: PEAK_AGREEMENT_HIGH,
    peakAgreement: peakAgreement,
    normalizeToFixedPie: normalizeToFixedPie,
    allocationCounts: allocationCounts
  };
})(typeof globalThis !== "undefined" ? globalThis : this);

if (typeof module !== "undefined" && module.exports) module.exports = globalThis.ValueModel;
