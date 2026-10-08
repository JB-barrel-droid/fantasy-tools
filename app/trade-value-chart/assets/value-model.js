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

  function sourceComboKey(source, scoring, teams, qbSlots) {
    var score = {ppr: "full", full: "full", half_ppr: "half", half: "half",
      standard: "standard"}[scoring];
    if (!score || !Number.isInteger(teams) || teams <= 0) return null;
    var key = score + "_" + teams;
    if (source === "fantasycalc" || source === "fantasycalc_adjusted") {
      var qb = qbSlots;
      if (qb !== 1 && qb !== 2) return null;
      key += "_qb" + qb;
    }
    // Exact identity only: never borrow another league size or QB grain.
    return key;
  }

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

  // Live adjusted cells are fitted per position/tier. A single global
  // starter/bench normalisation can keep the total pie correct while pushing
  // one position's curve badly out of shape. First align each position's peak
  // to the anchor on the shared players, then preserve the shared total.
  function shapeToAnchorPeaksThenSharedTotal(opts) {
    var values = opts.values;
    var anchor = opts.anchor;
    var playerOf = opts.playerOf;
    var basis = sharedPieBasis(opts);
    if (!basis) return new Map(values);

    var anchorPeaks = {}, valuePeaks = {};
    POSITION_ORDER.forEach(function (pos) {
      anchorPeaks[pos] = 0;
      valuePeaks[pos] = 0;
    });
    basis.keys.forEach(function (playerKey) {
      var player = playerOf(playerKey);
      if (!player || POSITION_ORDER.indexOf(player.pos) === -1) return;
      var a = Number(anchor.get(playerKey));
      var v = Number(values.get(playerKey));
      if (isFinite(a) && a > anchorPeaks[player.pos]) anchorPeaks[player.pos] = a;
      if (isFinite(v) && v > valuePeaks[player.pos]) valuePeaks[player.pos] = v;
    });

    var shaped = new Map();
    values.forEach(function (value, playerKey) {
      var player = playerOf(playerKey);
      var safe = isFinite(Number(value)) ? Math.max(0, Number(value)) : 0;
      var scale = player && valuePeaks[player.pos] > 0 && anchorPeaks[player.pos] > 0
        ? anchorPeaks[player.pos] / valuePeaks[player.pos]
        : 1;
      shaped.set(playerKey, safe * scale);
    });
    return scaleToSharedTotal({
      values: shaped,
      anchor: anchor,
      playerOf: playerOf
    });
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
    // As-published sources (FantasyCalc, USA Today, etc.) must use a single
    // global scale to preserve their native cross-position order. The
    // starter/bench two-tier scaling is for the ESPN DDF model only; applying
    // different scales to starters vs bench creates a discontinuity at the
    // transition and destroys the source's own ranking.
    if (opts.singleScale) {
      var total = starterTotal + benchTotal;
      var scale = total > 0 && target > 0 ? target / total : 0;
      var out = new Map();
      values.forEach(function (value, playerKey) {
        var safe = isFinite(Number(value)) ? Math.max(0, Number(value)) : 0;
        out.set(playerKey, safe * scale);
      });
      return out;
    }
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

  // JEG-68: sane band for the fixed-pie starter markup (adjusted/pure) on
  // the raw value-above-waivers curves.
  //
  // markup = target_starter_share / raw_starter_share, so it is ~1.0
  // whenever a source's raw pool already sits at the target split. CBS ROS
  // does exactly that (84.96% raw starter share at the default shape,
  // verified source-pure from the CBS snapshot: per_game = ROS/gp, and the
  // pipeline's independent two-tier raw_value prices the same pool at
  // 86.25%): the adjustment is correctly a near-no-op there, not a bug.
  // Below the low bound the pie materially inverts (starters marked down),
  // which is what already-valued "raw" inputs produce (~91% raw starter
  // share -> ~0.93 markup). Above the high bound the raw pool is
  // implausibly bench-heavy. Both are real defects; ~1.0 is not.
  var STARTER_MARKUP_SANE_LOW = 0.98;
  var STARTER_MARKUP_SANE_HIGH = 1.6;

  function starterMarkupSane(markup) {
    return typeof markup === "number" && isFinite(markup) &&
      markup >= STARTER_MARKUP_SANE_LOW && markup <= STARTER_MARKUP_SANE_HIGH;
  }

  // Fixed-pie direction tolerance (JEG-69).
  //
  // The `${vorpKey}-fixed-pie-direction` ChartHealth check asserts the raw
  // pool is bench-heavy enough that the fixed pie marks starters UP and
  // bench DOWN. A strict `rawStarterShare < starterShare` is knife-edge:
  // CBS ROS's raw pool genuinely sits at 85.2-85.3% starter share at
  // 14-team standard (verified source-pure -- JEG-68), 0.2-0.3pp over the
  // 85% target, and tripped the check on a correct build even though the
  // markup (0.996) sits inside the sane band.
  //
  // Tolerate the sane band's headroom instead: the check fails only where
  // the markup would also leave the sane band -- a material inversion like
  // the ~91% pre-valued-inputs defect (JEG-68). 1pp keeps the direction
  // check slightly stricter than the markup check (fails at 86.0% raw
  // starter share vs 86.7% for markup < 0.98), so it still guards the
  // direction while noise at the boundary passes.
  var STARTER_DIRECTION_EPS = 0.01;

  function fixedPieDirectionSane(rawStarterShare, starterShare) {
    return typeof rawStarterShare === "number" && isFinite(rawStarterShare) &&
      typeof starterShare === "number" && isFinite(starterShare) &&
      rawStarterShare < starterShare + STARTER_DIRECTION_EPS;
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
  // Cross-position bench comparisons may NOT use those units directly.
  // Ranking the pool by raw per-game points lets quarterbacks monopolise the
  // bench because they simply score more, which pushes the QB waiver line far
  // down the board and inflates every QB's value above it -- Josh Allen ends
  // up the most valuable asset in a 1QB league. A preseason positional rank
  // was the old workaround, and it was worse: four players share rank 1, so
  // the QB1 sorted ahead of the RB1 at x=1.
  //
  // Instead, bench players compare on surplus over each position's OWN
  // dedicated-starter baseline. That baseline is fixed by the league's slot
  // counts, so it is not circular, and it makes a point of RB surplus mean the
  // same as a point of QB surplus.
  //
  // Ordinary flex slots are different: after dedicated RB/WR/TE starters are
  // filled, that slot really does compare the best remaining eligible players
  // by projected points. Using surplus there under-counted deep RB rooms and
  // let lower-projection WRs win flex starter treatment just because WR had a
  // flatter dedicated-starter baseline. Superflex still uses surplus because
  // QB raw points are on a different scale.
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
    var remaining = function (positions, scoreOf) {
      var out = [];
      positions.forEach(function (pos) {
        byPos[pos].forEach(function (p) { if (!roles.has(p.player_key)) out.push(p); });
      });
      return out.sort(function (a, b) { return scoreOf(b) - scoreOf(a) || stableTiebreak(a, b); });
    };
    var flexPositions = flexEligible(shape);
    var flexScore = flexPositions.indexOf("QB") === -1 ? rankOf : surplus;
    remaining(flexPositions, flexScore).slice(0, teams * (Number(shape.FLEX) || 0))
      .forEach(function (p) { roles.set(p.player_key, "starter"); });
    remaining(POSITION_ORDER, surplus).slice(0, teams * (Number(shape.BENCH) || 0))
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

  // ---------------------------------------------------------------------
  // Published-chart value-above-waivers translation (JEG-332 / JEG-364).
  //
  // A line-for-line port of pipelines/vorp_translation/unified.py
  // (translate_ranked) and vorp_via_roster.py (apportion, bench_for_teams,
  // allocate_flex_vorp_weighted, rostered_for_teams). The server runs it
  // once, at 12 teams and the standard roster; under league-settings-001 the
  // browser runs the SAME arithmetic at whatever team count, roster and bench
  // the reader picks, starting from the source's saved 12-team native values.
  //
  // Parity is enforced, not hoped for: tests/test_vorp_translation_js_parity.py
  // runs this function and the Python on identical inputs and requires every
  // count, waiver line and rounded value to be EQUAL. Bump the version when
  // the arithmetic changes on purpose, and change the Python with it.
  // /2 (2026-10-07, V2-WAIVER-COVERAGE): a short chart's waiver line is
  // extrapolated from the other published charts (peers, imputeExtension).
  var VORP_TRANSLATION_VERSION = "unified-py-jeg62/2";
  // Our positional maxes (unified.py OUR_MAX): the 0-70 anchors per position.
  var TRANSLATION_OUR_MAX = {QB: 25.0, RB: 70.0, WR: 55.0, TE: 30.0};
  // unified.py POSITIONAL_MAX_VERSION / TOP_OF_SCALE (JEG332-DERIVED-PEAKS):
  // league-following maxes, see positionalMaxForSetup.
  var POSITIONAL_MAX_VERSION = "espn-vaw-ratio/1";
  var TRANSLATION_TOP_OF_SCALE = 70.0;
  // build_ddf_two_tier_leg.py REF_SLOTS / REF_FLEX_COUNT / BENCH_MIX_12.
  var TRANSLATION_REF_SLOTS = {QB: 1, RB: 2, WR: 3, TE: 1};
  var TRANSLATION_REF_FLEX_COUNT = 1;
  var TRANSLATION_BENCH_MIX_12 = {QB: 10, RB: 27, WR: 33, TE: 10};

  // Python round(x, nd): round-half-even on the exact binary value. toFixed
  // rounds exact ties UP, so ties are detected and settled separately. An
  // exact decimal tie at nd digits exists only when x * 2^(nd+1) is an odd
  // integer (x = odd / 2^(nd+1)); e.g. 12.25 -> 12.2 in Python, 12.3 via toFixed.
  function pyRound(x, nd) {
    if (!isFinite(x)) return x;
    if (x < 0) return -pyRound(-x, nd);
    var twice = x * Math.pow(2, nd + 1);
    if (Number.isInteger(twice) && twice % 2 === 1) {
      var p = Math.pow(10, nd);
      var n = Math.floor(x * p);
      if (n % 2 !== 0) n += 1;
      return n / p;
    }
    return Number(x.toFixed(nd));
  }

  // vorp_via_roster.apportion: highest-averages seat allocation. Ties go to
  // the first position in POSITION_ORDER (Python max() keeps the first).
  function apportionSlots(weights, total) {
    if (!(total >= 0) || Math.floor(total) !== total) {
      throw new Error("slot total must be a nonnegative integer");
    }
    POSITION_ORDER.forEach(function (pos) {
      var w = weights[pos];
      if (w !== undefined && (!isFinite(w) || w < 0)) {
        throw new Error("allocation weights must be finite and nonnegative");
      }
    });
    var result = {};
    POSITION_ORDER.forEach(function (pos) { result[pos] = 0; });
    var eligible = POSITION_ORDER.filter(function (pos) { return (weights[pos] || 0) > 0; });
    if (total && !eligible.length) throw new Error("positive slot total requires positive weights");
    for (var i = 0; i < total; i += 1) {
      var best = null, bestScore = -Infinity;
      eligible.forEach(function (pos) {
        var score = weights[pos] / (result[pos] + 1);
        if (score > bestScore) { best = pos; bestScore = score; }
      });
      result[best] += 1;
    }
    return result;
  }

  // vorp_via_roster.bench_for_teams.
  function translationBench(teams, benchPerTeam) {
    var total = teams * benchPerTeam;
    if (!isFinite(total) || total < 0) throw new Error("bench capacity must be finite and nonnegative");
    return apportionSlots(TRANSLATION_BENCH_MIX_12, Math.floor(total + 0.5));
  }

  function checkTeamsFlex(teams, flexCount) {
    if (!(teams > 0) || Math.floor(teams) !== teams || !(flexCount >= 0) || Math.floor(flexCount) !== flexCount) {
      throw new Error("teams must be positive and flex count nonnegative integers");
    }
  }

  // vorp_via_roster.allocate_flex_vorp_weighted. ranked: {pos: [{value}]}
  // sorted descending.
  function translationFlexWeighted(ranked, teams, flexCount, waiverEstimates, slots, flexElig) {
    checkTeamsFlex(teams, flexCount);
    var totalFlex = teams * flexCount;
    var weights = {};
    var weightSum = 0;
    flexElig.forEach(function (pos) {
      var nDed = teams * (slots[pos] || 0);
      var players = ranked[pos] || [];
      var waiver = waiverEstimates[pos] !== undefined ? waiverEstimates[pos] : 0.0;
      if (!isFinite(waiver) || players.some(function (p) { return !isFinite(p.value); })) {
        throw new Error(pos + ": publisher values and waiver must be finite");
      }
      var candidates = players.slice(nDed, Math.min(players.length, nDed + totalFlex));
      if (!candidates.length) { weights[pos] = 0.0; return; }
      var sum = 0;
      candidates.forEach(function (p) { sum += Math.max(0.0, p.value - waiver); });
      var avg = totalFlex ? sum / totalFlex : 0.0;
      weights[pos] = (slots[pos] || 0) * avg;
    });
    flexElig.forEach(function (pos) { weightSum += weights[pos]; });
    if (weightSum <= 0) {
      weights = {};
      flexElig.forEach(function (pos) { weights[pos] = slots[pos] || 0; });
    }
    return apportionSlots(weights, totalFlex);
  }

  function waiverAt(players, n) {
    if (players.length > n) return players[n].value;
    if (players.length) return players[players.length - 1].value;
    return 0.0;
  }

  // vorp_via_roster.rostered_for_teams (VORP-weighted flex when ranked given).
  function translationRostered(teams, benchPerTeam, flexCount, ranked, slots, flexElig) {
    checkTeamsFlex(teams, flexCount);
    var flexAlloc;
    if (ranked) {
      var baseline = translationRostered(teams, benchPerTeam, flexCount, null, slots, flexElig);
      var waiverEst = {};
      POSITION_ORDER.forEach(function (pos) {
        waiverEst[pos] = waiverAt(ranked[pos] || [], baseline[pos].rostered);
      });
      flexAlloc = translationFlexWeighted(ranked, teams, flexCount, waiverEst, slots, flexElig);
    } else {
      var w = {};
      flexElig.forEach(function (pos) { w[pos] = slots[pos] || 0; });
      flexAlloc = apportionSlots(w, teams * flexCount);
    }
    var benchAlloc = translationBench(teams, benchPerTeam);
    var out = {};
    POSITION_ORDER.forEach(function (pos) {
      var dedicated = teams * (slots[pos] || 0);
      var flex = flexAlloc[pos] || 0;
      var bench = benchAlloc[pos] || 0;
      out[pos] = {dedicated: dedicated, flex: flex, bench: bench, rostered: dedicated + flex + bench};
    });
    return out;
  }

  function sortRanked(input) {
    var ranked = {};
    POSITION_ORDER.forEach(function (pos) {
      var rows = (input && input[pos]) || [];
      ranked[pos] = rows.map(function (row) { return {key: row.key, value: Number(row.value)}; })
        .sort(function (a, b) { return b.value - a.value; });
    });
    return ranked;
  }

  // unified.projection_max_vorp: the top player's value above waivers per
  // position (unrounded), with the translation's own roster/waiver rules.
  function projectionMaxVorp(ranked, teams, benchPerTeam, flexCount, slots, flexElig) {
    var roster = translationRostered(teams, benchPerTeam, flexCount, ranked, slots, flexElig);
    var out = {};
    POSITION_ORDER.forEach(function (pos) {
      var rows = ranked[pos];
      if (!rows.length) return;
      out[pos] = Math.max(0.0, rows[0].value - waiverAt(rows, roster[pos].rostered));
    });
    return out;
  }

  // unified.positional_max_for_setup (JEG332-DERIVED-PEAKS, decision for
  // Jeremy 2026-10-07: "derived curves should shift with position settings").
  // OUR_MAX is the calibration at the saved setup. At any other setting each
  // position's max is OUR_MAX scaled by how far OUR model's top player at that
  // position (ESPN per-game projections, the anchor's input) sits above the
  // waiver line there, relative to the saved setup; then all four are scaled
  // so the top position is 70 (the chart's top-player convention). A 2-QB
  // roster pulls the QB waiver line down and raises the QB max; a deeper WR
  // or flex requirement raises WR; shallow leagues lift the positions whose
  // replacement level barely moves. Saved setup: exactly OUR_MAX.
  // opts: projection ({pos: [{key, value}]}), teams, benchPerTeam, flexCount,
  // slots, flexEligible (defaults as translatePublishedVorp).
  function positionalMaxForSetup(opts) {
    opts = opts || {};
    var ranked = sortRanked(opts.projection);
    var benchPerTeam = opts.benchPerTeam === undefined ? 6.0 : Number(opts.benchPerTeam);
    var flexCount = opts.flexCount === undefined || opts.flexCount === null
      ? TRANSLATION_REF_FLEX_COUNT : Number(opts.flexCount);
    var ref = projectionMaxVorp(ranked, SAVED_SETUP_TEAMS, 6.0, TRANSLATION_REF_FLEX_COUNT,
      TRANSLATION_REF_SLOTS, DEFAULT_FLEX_ELIGIBLE);
    var at = projectionMaxVorp(ranked, Number(opts.teams), benchPerTeam, flexCount,
      opts.slots || TRANSLATION_REF_SLOTS, opts.flexEligible || DEFAULT_FLEX_ELIGIBLE);
    var raw = {};
    var top = -Infinity;
    POSITION_ORDER.forEach(function (pos) {
      var r = ref[pos] === undefined ? 0.0 : ref[pos];
      var a = at[pos] === undefined ? 0.0 : at[pos];
      raw[pos] = r > 0 ? TRANSLATION_OUR_MAX[pos] * (a / r) : TRANSLATION_OUR_MAX[pos];
      if (raw[pos] > top) top = raw[pos];
    });
    var out = {};
    if (!(top > 0)) {
      POSITION_ORDER.forEach(function (pos) { out[pos] = TRANSLATION_OUR_MAX[pos]; });
      return out;
    }
    var k = TRANSLATION_TOP_OF_SCALE / top;
    POSITION_ORDER.forEach(function (pos) { out[pos] = raw[pos] * k; });
    return out;
  }

  // unified.impute_extension (V2-WAIVER-COVERAGE, Jeremy 2026-10-07: "If
  // needed for computations, cover them by extrapolating from the average of
  // other charts. Denote them. Where it's not needed, hide those values.").
  // ranked: {pos: [{key, value}]} this chart, sorted descending. peers:
  // {source: {pos: [{key, value}]}} the OTHER published charts' saved 12-team
  // natives. Per position and peer O: k_O = sum(this chart) / sum(O) over the
  // players both list among this chart's bottom half (value <= its median
  // listed value; >= IMPUTE_MIN_FIT of them, else O is skipped). An unlisted
  // player's imputed native = mean over usable peers listing him of k_O x O's
  // native, capped at this chart's last listed value. Returns {pos: [{key,
  // value}]} sorted value desc, key asc. Same arithmetic order as the Python
  // (peers by sorted name, players by sorted key string) -> identical floats.
  var IMPUTATION_VERSION = "other-charts-tail-ratio/1";
  var IMPUTE_MIN_FIT = 3;
  var WAIVER_IMPUTED = "imputed_from_other_charts";

  function keyCompare(a, b) {
    var x = String(a), y = String(b);
    return x < y ? -1 : (x > y ? 1 : 0);
  }

  function imputeExtension(ranked, peers) {
    var out = {};
    if (!peers) return out;
    var peerNames = Object.keys(peers).sort(keyCompare);
    POSITION_ORDER.forEach(function (pos) {
      var listed = ranked[pos] || [];
      if (!listed.length) return;
      var mine = new Map();
      listed.forEach(function (p) { mine.set(String(p.key), Number(p.value)); });
      var last = Number(listed[listed.length - 1].value);
      var median = Number(listed[Math.floor(listed.length / 2)].value);
      var tail = listed.filter(function (p) { return Number(p.value) <= median; })
        .map(function (p) { return String(p.key); }).sort(keyCompare);
      var acc = new Map();
      peerNames.forEach(function (name) {
        var theirs = new Map();
        ((peers[name] || {})[pos] || []).forEach(function (p) { theirs.set(String(p.key), Number(p.value)); });
        var shared = tail.filter(function (k) { return theirs.has(k); });
        if (shared.length < IMPUTE_MIN_FIT) return;
        var num = 0.0, den = 0.0;
        shared.forEach(function (k) { num += mine.get(k); den += theirs.get(k); });
        if (!(den > 0)) return;
        var ratio = num / den;
        Array.from(theirs.keys()).sort(keyCompare).forEach(function (k) {
          if (mine.has(k)) return;
          var slot = acc.get(k);
          if (!slot) { slot = [0.0, 0]; acc.set(k, slot); }
          slot[0] += ratio * theirs.get(k);
          slot[1] += 1;
        });
      });
      var ext = [];
      acc.forEach(function (slot, k) { ext.push({key: k, value: Math.min(last, slot[0] / slot[1])}); });
      if (!ext.length) return;
      ext.sort(function (a, b) { return (b.value - a.value) || keyCompare(a.key, b.key); });
      out[pos] = ext;
    });
    return out;
  }

  // unified.translate_ranked. opts:
  //   ranked: {pos: [{key, value}]} -- the source's native values per position.
  //           Sorted here (stable, value descending), so input order only
  //           settles exact ties, which cannot change any output number.
  //   teams, benchPerTeam (default 6), flexCount (default 1),
  //   slots (default {QB:1,RB:2,WR:3,TE:1}), flexEligible (default RB/WR/TE),
  //   peers (optional {source: {pos: [{key, value}]}}: the other published
  //   charts; a short position's waiver line is read from the chart extended
  //   by imputeExtension -- waiver_method "imputed_from_other_charts").
  // Returns {version, positions: {pos: {...}}, translated: {key: {pos,
  // native, vorp, translated}}}. Only players above the waiver line appear in
  // `translated`, exactly as on the server; imputed players never do.
  function translatePublishedVorp(opts) {
    opts = opts || {};
    var teams = Number(opts.teams);
    var benchPerTeam = opts.benchPerTeam === undefined ? 6.0 : Number(opts.benchPerTeam);
    var flexCount = opts.flexCount === undefined || opts.flexCount === null
      ? TRANSLATION_REF_FLEX_COUNT : Number(opts.flexCount);
    var slots = opts.slots || TRANSLATION_REF_SLOTS;
    var flexElig = opts.flexEligible || DEFAULT_FLEX_ELIGIBLE;
    var ourMax = opts.ourMax || TRANSLATION_OUR_MAX;
    var ranked = sortRanked(opts.ranked);
    var extension = opts.peers ? imputeExtension(ranked, opts.peers) : {};
    var extended = {};
    var work, roster;
    for (;;) {
      work = {};
      POSITION_ORDER.forEach(function (pos) {
        work[pos] = extended[pos] ? ranked[pos].concat(extension[pos]) : ranked[pos];
      });
      roster = translationRostered(teams, benchPerTeam, flexCount, work, slots, flexElig);
      var short = POSITION_ORDER.filter(function (pos) {
        return !extended[pos] && extension[pos] && ranked[pos].length
          && ranked[pos].length <= roster[pos].rostered;
      });
      if (!short.length) break;
      short.forEach(function (pos) { extended[pos] = true; });
    }
    var result = {version: VORP_TRANSLATION_VERSION, positions: {}, translated: {}};
    POSITION_ORDER.forEach(function (pos) {
      var players = ranked[pos];
      if (!players.length) return;
      var line = work[pos];
      var r = roster[pos];
      var nRostered = r.rostered;
      var waiverVal, method, nImputed = 0;
      if (line.length > nRostered) {
        waiverVal = line[nRostered].value;
        if (nRostered < players.length) method = "roster_determined";
        else { method = WAIVER_IMPUTED; nImputed = nRostered - players.length + 1; }
      } else { waiverVal = players[players.length - 1].value; method = "insufficient_coverage"; }
      var maxVorp = 0.0, totalVorp = 0;
      var vorps = players.map(function (p) {
        var v = Math.max(0.0, p.value - waiverVal);
        if (v > maxVorp) maxVorp = v;
        totalVorp += v;
        return v;
      });
      var scale = maxVorp > 0 ? ourMax[pos] / maxVorp : 0.0;
      players.forEach(function (p, i) {
        var v = vorps[i];
        if (v > 0) {
          result.translated[p.key] = {
            pos: pos,
            native: pyRound(p.value, 1),
            vorp: pyRound(v, 1),
            translated: pyRound(v * scale, 1)
          };
        }
      });
      result.positions[pos] = {
        n_dedicated: r.dedicated,
        n_flex: r.flex,
        n_bench: r.bench,
        n_rostered: nRostered,
        n_listed: players.length,
        n_imputed: nImputed,
        waiver_line_value: pyRound(waiverVal, 2),
        waiver_method: method,
        max_vorp: pyRound(maxVorp, 1),
        total_vorp: pyRound(totalVorp, 1),
        scale_factor: pyRound(scale, 3)
      };
    });
    var total = 0;
    Object.keys(result.positions).forEach(function (pos) { total += result.positions[pos].total_vorp; });
    Object.keys(result.positions).forEach(function (pos) {
      var w = total > 0 ? result.positions[pos].total_vorp / total : 0;
      result.positions[pos].implied_weight = pyRound(w, 4);
    });
    return result;
  }

  // ---------------------------------------------------------------------
  // League-settings engine for published charts (league-settings-001).
  //
  // The backend saves ONE setup per scoring: 12 teams, standard roster. At
  // that setup the chart shows the saved values untouched. At any other team
  // count or roster the browser derives the published chart from the saved
  // 12-team inputs, running the same recipe the server ran at 12 teams:
  //
  //   1. value above waivers, translated onto our positional maxes
  //      (translatePublishedVorp) at the chosen teams/roster/bench, for every
  //      player above that setting's waiver line. The maxes themselves follow
  //      the setting (positionalMaxForSetup) when `projection` is passed;
  //   2. every other player -- at or below that setting's waiver line, or
  //      with no native value to rank -- is worth 0: value above waivers is
  //      zero by definition.
  //
  // /3 (2026-10-07, Jeremy agreed): step 2 used to mirror the server's
  // fail-safe (the saved value, or the 12-team flex-aware pie value) for
  // below-waiver players. It now prices them at 0.
  // /2 (2026-10-07): optional `projection` makes the positional maxes follow
  // the setting (JEG332-DERIVED-PEAKS); both chart callers pass it.
  // /4 (2026-10-07, V2-WAIVER-COVERAGE): `peers` -- a short position's waiver
  // line is extrapolated from the other published charts; result `waiver`.
  var PUBLISHED_DERIVATION_VERSION = "league-settings-001/4";
  var SAVED_SETUP_TEAMS = 12;
  var SAVED_SETUP_SHAPE = {QB: 1, RB: 2, WR: 3, TE: 1, FLEX: 1, BENCH: 6};

  function isSavedSetup(teams, shape) {
    if (Number(teams) !== SAVED_SETUP_TEAMS) return false;
    shape = shape || {};
    if (shape.SUPERFLEX) return false;
    return Object.keys(SAVED_SETUP_SHAPE).every(function (key) {
      return Number(shape[key]) === SAVED_SETUP_SHAPE[key];
    });
  }

  // The translation's league arguments for a chart roster shape.
  function settingForShape(teams, shape) {
    return {
      teams: Number(teams),
      benchPerTeam: Number(shape.BENCH),
      flexCount: Number(shape.FLEX),
      slots: {QB: Number(shape.QB), RB: Number(shape.RB), WR: Number(shape.WR), TE: Number(shape.TE)},
      flexEligible: flexEligible(shape)
    };
  }

  // {source: Map key -> native} -> {source: {pos: [{key, value}]}} for
  // translatePublishedVorp's peers (V2-WAIVER-COVERAGE). null when empty.
  function peersByPosition(peers, posOf) {
    if (!peers) return null;
    var out = {};
    Object.keys(peers).forEach(function (src) {
      if (peers[src] && peers[src].size) out[src] = rankedByPosition(peers[src], posOf);
    });
    return Object.keys(out).length ? out : null;
  }

  // The denotation for one translation: per position how the waiver line was
  // set (unified.waiver_summary), plus the positions whose line is
  // extrapolated from other charts ("imputed") or still the chart's last
  // listed value because no other chart covers enough players ("short").
  function waiverSummary(at) {
    var positions = {}, imputed = [], short = [];
    POSITION_ORDER.forEach(function (pos) {
      var p = at.positions[pos];
      if (!p) return;
      positions[pos] = {method: p.waiver_method, n_listed: p.n_listed,
                        n_rostered: p.n_rostered, n_imputed: p.n_imputed};
      if (p.waiver_method === WAIVER_IMPUTED) imputed.push(pos);
      if (p.waiver_method === "insufficient_coverage") short.push(pos);
    });
    return {version: IMPUTATION_VERSION, positions: positions, imputed: imputed, short: short};
  }

  // The waiver denotation for a published chart at a setting, without
  // deriving values (used at the saved setup, where the chart shows the saved
  // values -- which the chain computed with the same peers). opts as
  // derivePublishedSetup (native, peers, posOf, teams, shape).
  function publishedWaiverInfo(opts) {
    var shape = opts.shape || SAVED_SETUP_SHAPE;
    var setting = settingForShape(opts.teams, shape);
    var at = translatePublishedVorp(Object.assign({ranked: rankedByPosition(opts.native, opts.posOf),
      peers: peersByPosition(opts.peers, opts.posOf)}, setting));
    return waiverSummary(at);
  }

  function rankedByPosition(native, posOf) {
    var ranked = {};
    POSITION_ORDER.forEach(function (pos) { ranked[pos] = []; });
    native.forEach(function (value, key) {
      var pos = posOf(key);
      var v = Number(value);
      if (ranked[pos] && isFinite(v)) ranked[pos].push({key: key, value: v});
    });
    return ranked;
  }

  // opts: native (Map key -> saved 12-team native value), saved (Map key ->
  // saved 12-team chart value; only its KEY SET is used off the saved setup),
  // indexTotal (unused since /3, accepted for callers), posOf(key), teams,
  // shape ({QB,RB,WR,TE,FLEX,BENCH[,SUPERFLEX]}), projection (optional Map
  // key -> ESPN per-game points for this scoring), peers (optional {source:
  // Map key -> saved 12-team native} of the OTHER published charts at this
  // scoring: a short position's waiver line is extrapolated from them).
  // Returns {version, values: Map, ourMax, positionalMax, translated,
  // belowWaiver, waiver}. The player set is the saved set, at every setting.
  function derivePublishedSetup(opts) {
    var native = opts.native;
    var saved = opts.saved;
    var posOf = opts.posOf;
    var shape = opts.shape || SAVED_SETUP_SHAPE;
    var ranked = rankedByPosition(native, posOf);
    var setting = settingForShape(opts.teams, shape);
    // JEG332-DERIVED-PEAKS: with our projections supplied, the positional
    // maxes follow the setting (positionalMaxForSetup); without them they stay
    // at OUR_MAX (the pre-2026-10-07 behaviour).
    var projection = null;
    if (opts.projection && opts.projection.size) {
      projection = {};
      POSITION_ORDER.forEach(function (pos) { projection[pos] = []; });
      opts.projection.forEach(function (value, key) {
        var pos = posOf(key);
        if (projection[pos] && typeof value === "number" && isFinite(value)) {
          projection[pos].push({key: key, value: value});
        }
      });
    }
    var ourMax = projection
      ? positionalMaxForSetup(Object.assign({projection: projection}, setting))
      : TRANSLATION_OUR_MAX;
    var at = translatePublishedVorp(Object.assign({ranked: ranked, ourMax: ourMax,
      peers: peersByPosition(opts.peers, posOf)}, setting));
    var values = new Map();
    var counts = {translated: 0, belowWaiver: 0};
    saved.forEach(function (savedValue, key) {
      var t = at.translated[String(key)];
      if (t) { values.set(key, t.translated); counts.translated += 1; return; }
      values.set(key, 0); counts.belowWaiver += 1;
    });
    var maxes = {};
    POSITION_ORDER.forEach(function (pos) { maxes[pos] = ourMax[pos]; });
    return {version: PUBLISHED_DERIVATION_VERSION, translationVersion: at.version,
            positionalMax: projection ? POSITIONAL_MAX_VERSION : "fixed", ourMax: maxes,
            values: values, translated: counts.translated, belowWaiver: counts.belowWaiver,
            waiver: waiverSummary(at),
            // Read-only echo of the translation behind `values` (math inspector).
            translation: at};
  }

  // ---------------------------------------------------------------------
  // The chart's other two views for published charts at any league setting
  // (JEG332-VORP-VIEWS, 2026-10-07; Jeremy: "I'm ok with however you set up
  // values to get the tool working" -- math to be reviewed).
  //
  // The saved `vorp_views` (pipelines/build_imputed_vorps.py +
  // build_reweighted_values.py) exist for one scoring at 12 teams. Everywhere
  // else the browser derives both views from the same league arithmetic as
  // derivePublishedSetup, so all three views agree on who is above waivers
  // (everyone at or below the setting's waiver line is 0 in every view):
  //
  //   VORP vs waivers: each player's value above that setting's waiver line
  //     in the publisher's own units (translatePublishedVorp `vorp`), times
  //     ONE factor per chart so the chart's total equals our anchor's total
  //     at this setting over the players the chart ranks (the sum of its
  //     eight group budgets; measured on the shared set like sharedPieBasis,
  //     so a thin chart is not forced taller). One factor, no re-tiering: the
  //     publisher's own cross-position valuation is kept, and every curve has
  //     the "same shared total as Indexed" (footnote copy).
  //   Adjusted values: our position weighting applied. Players are grouped
  //     position x role (starter = the translation's dedicated + flex count at
  //     that position, bench = the rest of the rostered players); each group
  //     shares OUR anchor's total for the same group in proportion to value
  //     above waivers (build_imputed_vorps' eight-group recipe, weighted by
  //     value above waivers instead of the raw published value so the waiver
  //     line is a 0, not a cliff). Then ONE common factor puts the top player
  //     across the batch (every published chart derived at this setting) at
  //     70 -- build_reweighted_values' 70 anchor. Its blend-reference group
  //     budgets exist for the saved setup only; here the budgets are the
  //     anchor's own group totals at the setting.
  //
  // opts: sources {key: {native: Map key -> saved 12-team native value,
  //       keys: Map|Set|Array of player keys to return (the plotted set),
  //       budgets: {QB|RB|WR|TE: {starter, bench}} -- the anchor's group
  //       totals over this chart's players (anchorGroupTotals with keys)}},
  //       posOf(key), teams, shape, natives (optional {source: Map} of EVERY
  //       published chart's saved natives at this scoring; each chart's peers
  //       are the others. Default: the natives in `sources`).
  // Returns {version, batchMax, adjScale, sources: {key: {vorp: Map, adj: Map,
  // total, vorpScale, groups: {pos: {starter, bench}} (sum of value above
  // waivers, publisher units)}}}.
  // /2 (2026-10-07, V2-WAIVER-COVERAGE): same peers-extended waiver line.
  var PUBLISHED_VIEWS_VERSION = "published-views-001/2";
  var VIEW_TOP_OF_SCALE = 70.0;

  function nativesOf(sources) {
    var out = {};
    Object.keys(sources || {}).forEach(function (src) { out[src] = sources[src].native; });
    return out;
  }

  function derivePublishedViews(opts) {
    var shape = opts.shape || SAVED_SETUP_SHAPE;
    var setting = settingForShape(opts.teams, shape);
    var posOf = opts.posOf;
    var out = {version: PUBLISHED_VIEWS_VERSION, batchMax: 0, adjScale: 0, sources: {}};
    var grouped = {};
    Object.keys(opts.sources || {}).forEach(function (src) {
      var input = opts.sources[src];
      var budgets = input.budgets || {};
      var total = 0;
      POSITION_ORDER.forEach(function (pos) {
        ["starter", "bench"].forEach(function (role) {
          var b = Number((budgets[pos] || {})[role]);
          if (isFinite(b) && b > 0) total += b;
        });
      });
      var ranked = rankedByPosition(input.native, posOf);
      var all = opts.natives || nativesOf(opts.sources);
      var peers = {};
      Object.keys(all).forEach(function (other) { if (other !== src) peers[other] = all[other]; });
      var at = translatePublishedVorp(Object.assign({ranked: ranked,
        peers: peersByPosition(peers, posOf)}, setting));
      var sorted = sortRanked(ranked);
      var info = new Map();
      var groups = {};
      var vorpSum = 0;
      POSITION_ORDER.forEach(function (pos) {
        var p = at.positions[pos];
        groups[pos] = {starter: 0, bench: 0};
        if (!p) return;
        var nStart = p.n_dedicated + p.n_flex;
        sorted[pos].forEach(function (row, i) {
          var t = at.translated[String(row.key)];
          if (!t) return;
          var role = i < nStart ? "starter" : "bench";
          info.set(String(row.key), {pos: pos, role: role, vorp: t.vorp});
          groups[pos][role] += t.vorp;
          vorpSum += t.vorp;
        });
      });
      var vorpScale = vorpSum > 0 ? total / vorpSum : 0;
      var vorp = new Map();
      var weighted = new Map();
      var keys = input.keys instanceof Map ? Array.from(input.keys.keys()) : Array.from(input.keys);
      keys.forEach(function (key) {
        var row = info.get(String(key));
        var v = 0, w = 0;
        if (row) {
          v = row.vorp * vorpScale;
          var groupTotal = groups[row.pos][row.role];
          var budget = Number((budgets[row.pos] || {})[row.role]);
          w = groupTotal > 0 && isFinite(budget) && budget > 0 ? budget * row.vorp / groupTotal : 0;
        }
        vorp.set(key, v);
        weighted.set(key, w);
        if (w > out.batchMax) out.batchMax = w;
      });
      grouped[src] = weighted;
      // budgets, roles (key -> {pos, role, vorp}) and translation are
      // read-only echoes of this function's inputs and intermediates for the
      // math inspector; no value is derived from them.
      out.sources[src] = {vorp: vorp, total: total, vorpScale: vorpScale, groups: groups,
                          waiver: waiverSummary(at), budgets: budgets, roles: info,
                          translation: at};
    });
    out.adjScale = out.batchMax > 0 ? VIEW_TOP_OF_SCALE / out.batchMax : 0;
    Object.keys(out.sources).forEach(function (src) {
      var adj = new Map();
      grouped[src].forEach(function (w, key) { adj.set(key, w * out.adjScale); });
      out.sources[src].adj = adj;
    });
    return out;
  }

  // Our anchor's eight group totals at a setting: the anchor's values summed
  // per position x role, roles from roleMap (dedicated, then flex, then bench,
  // by value) at that teams/roster over the WHOLE anchor. Waiver players are
  // in no group. opts: values (Map key -> anchor value), playerOf(key), teams,
  // shape, keys (optional Set: sum only these players -- one chart's set).
  function anchorGroupTotals(opts) {
    var roles = opts.roles || roleMap(opts);
    var only = opts.keys || null;
    var totals = {};
    POSITION_ORDER.forEach(function (pos) { totals[pos] = {starter: 0, bench: 0}; });
    opts.values.forEach(function (value, key) {
      var role = roles.get(key);
      var player = opts.playerOf(key);
      var v = Number(value);
      if (only && !only.has(key)) return;
      if (!player || !totals[player.pos] || !(role === "starter" || role === "bench") || !isFinite(v)) return;
      totals[player.pos][role] += Math.max(0, v);
    });
    return totals;
  }

  root.ValueModel = {
    PUBLISHED_DERIVATION_VERSION: PUBLISHED_DERIVATION_VERSION,
    SAVED_SETUP_TEAMS: SAVED_SETUP_TEAMS,
    SAVED_SETUP_SHAPE: SAVED_SETUP_SHAPE,
    isSavedSetup: isSavedSetup,
    derivePublishedSetup: derivePublishedSetup,
    PUBLISHED_VIEWS_VERSION: PUBLISHED_VIEWS_VERSION,
    derivePublishedViews: derivePublishedViews,
    anchorGroupTotals: anchorGroupTotals,
    VORP_TRANSLATION_VERSION: VORP_TRANSLATION_VERSION,
    TRANSLATION_OUR_MAX: TRANSLATION_OUR_MAX,
    POSITIONAL_MAX_VERSION: POSITIONAL_MAX_VERSION,
    positionalMaxForSetup: positionalMaxForSetup,
    pyRound: pyRound,
    apportionSlots: apportionSlots,
    translationRostered: translationRostered,
    translatePublishedVorp: translatePublishedVorp,
    IMPUTATION_VERSION: IMPUTATION_VERSION,
    imputeExtension: imputeExtension,
    publishedWaiverInfo: publishedWaiverInfo,
    POSITION_ORDER: POSITION_ORDER,
    DEFAULT_FLEX_ELIGIBLE: DEFAULT_FLEX_ELIGIBLE,
    MIN_SHARED_FOR_PIE: MIN_SHARED_FOR_PIE,
    sourceComboKey: sourceComboKey,
    flexEligible: flexEligible,
    stableTiebreak: stableTiebreak,
    roleMap: roleMap,
    projectionRoles: projectionRoles,
    positionalTierScales: positionalTierScales,
    sharedPieBasis: sharedPieBasis,
    benchShareOf: benchShareOf,
    scaleToSharedTotal: scaleToSharedTotal,
    shapeToAnchorPeaksThenSharedTotal: shapeToAnchorPeaksThenSharedTotal,
    PEAK_AGREEMENT_LOW: PEAK_AGREEMENT_LOW,
    PEAK_AGREEMENT_HIGH: PEAK_AGREEMENT_HIGH,
    peakAgreement: peakAgreement,
    normalizeToFixedPie: normalizeToFixedPie,
    STARTER_MARKUP_SANE_LOW: STARTER_MARKUP_SANE_LOW,
    STARTER_MARKUP_SANE_HIGH: STARTER_MARKUP_SANE_HIGH,
    starterMarkupSane: starterMarkupSane,
    STARTER_DIRECTION_EPS: STARTER_DIRECTION_EPS,
    fixedPieDirectionSane: fixedPieDirectionSane,
    allocationCounts: allocationCounts
  };
})(typeof globalThis !== "undefined" ? globalThis : this);

if (typeof module !== "undefined" && module.exports) module.exports = globalThis.ValueModel;
