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

  // JEG332-SUPERFLEX-FLEX (Jeremy 2026-10-08, option A): superflex is a
  // DEDICATED roster slot (shape.SUPERFLEX = slots per team, 0 or 1 on the
  // page), filled after the dedicated slots and before FLEX by the best
  // remaining player with QBs eligible. It no longer widens FLEX: FLEX stays
  // RB/WR/TE. (Before 2026-10-08 SUPERFLEX was a flag that made QB eligible
  // for every FLEX slot; no control could set it.)
  var SUPERFLEX_ELIGIBLE = ["QB", "RB", "WR", "TE"];

  function superflexCount(shape) {
    var n = Math.floor(Number(shape && shape.SUPERFLEX) || 0);
    return n > 0 ? n : 0;
  }

  function flexEligible(shape) {
    return DEFAULT_FLEX_ELIGIBLE.slice();
  }

  // Stable, preseason-free tiebreak. Values decide order; this only settles
  // exact ties so the ordering is deterministic across reloads and callers.
  function stableTiebreak(a, b) {
    if (!a || !b) return 0;
    return String(a.name || "").localeCompare(String(b.name || ""))
      || (Number(a.player_key) - Number(b.player_key));
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
  // /3 (2026-10-08, JEG332-SUPERFLEX-FLEX option A): optional dedicated
  // superflex slots (superflexCount); 0 reproduces /2 exactly.
  var VORP_TRANSLATION_VERSION = "unified-py-jeg62/3";
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

  // vorp_via_roster.allocate_superflex (JEG332-SUPERFLEX-FLEX option A): the
  // teams x count best players left after the dedicated starters, across all
  // four positions, by value -- no per-position slot weight. Ties: position
  // order, then rank (Python sorts (-value, posIdx, rank)). Without ranked
  // values: apportioned by dedicated slots (the waiver-estimate baseline).
  function translationSuperflex(ranked, teams, count, slots) {
    if (!(count >= 0) || Math.floor(count) !== count) {
      throw new Error("superflex count must be a nonnegative integer");
    }
    var total = teams * count;
    var out = {};
    POSITION_ORDER.forEach(function (pos) { out[pos] = 0; });
    if (!total) return out;
    if (!ranked) {
      var w = {};
      POSITION_ORDER.forEach(function (pos) { w[pos] = slots[pos] || 0; });
      return apportionSlots(w, total);
    }
    var candidates = [];
    POSITION_ORDER.forEach(function (pos, posIdx) {
      var players = ranked[pos] || [];
      if (players.some(function (p) { return !isFinite(p.value); })) {
        throw new Error(pos + ": publisher values must be finite");
      }
      players.slice(teams * (slots[pos] || 0)).forEach(function (p, i) {
        candidates.push({value: p.value, posIdx: posIdx, i: i, pos: pos});
      });
    });
    candidates.sort(function (a, b) {
      return (b.value - a.value) || (a.posIdx - b.posIdx) || (a.i - b.i);
    });
    candidates.slice(0, total).forEach(function (c) { out[c.pos] += 1; });
    return out;
  }

  // vorp_via_roster.allocate_flex_vorp_weighted. ranked: {pos: [{value}]}
  // sorted descending. sfAlloc: superflex starters already taken per position
  // (flex candidates start after them).
  function translationFlexWeighted(ranked, teams, flexCount, waiverEstimates, slots, flexElig, sfAlloc) {
    checkTeamsFlex(teams, flexCount);
    var totalFlex = teams * flexCount;
    var weights = {};
    var weightSum = 0;
    flexElig.forEach(function (pos) {
      var nTaken = teams * (slots[pos] || 0) + ((sfAlloc && sfAlloc[pos]) || 0);
      var players = ranked[pos] || [];
      var waiver = waiverEstimates[pos] !== undefined ? waiverEstimates[pos] : 0.0;
      if (!isFinite(waiver) || players.some(function (p) { return !isFinite(p.value); })) {
        throw new Error(pos + ": publisher values and waiver must be finite");
      }
      var candidates = players.slice(nTaken, Math.min(players.length, nTaken + totalFlex));
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
  // sfCount: dedicated superflex slots per team (default 0).
  function translationRostered(teams, benchPerTeam, flexCount, ranked, slots, flexElig, sfCount) {
    checkTeamsFlex(teams, flexCount);
    sfCount = sfCount === undefined ? 0 : sfCount;
    var flexAlloc, sfAlloc;
    if (ranked) {
      var baseline = translationRostered(teams, benchPerTeam, flexCount, null, slots, flexElig, sfCount);
      var waiverEst = {};
      POSITION_ORDER.forEach(function (pos) {
        waiverEst[pos] = waiverAt(ranked[pos] || [], baseline[pos].rostered);
      });
      sfAlloc = translationSuperflex(ranked, teams, sfCount, slots);
      flexAlloc = translationFlexWeighted(ranked, teams, flexCount, waiverEst, slots, flexElig, sfAlloc);
    } else {
      sfAlloc = translationSuperflex(null, teams, sfCount, slots);
      var w = {};
      flexElig.forEach(function (pos) { w[pos] = slots[pos] || 0; });
      flexAlloc = apportionSlots(w, teams * flexCount);
    }
    var benchAlloc = translationBench(teams, benchPerTeam);
    var out = {};
    POSITION_ORDER.forEach(function (pos) {
      var dedicated = teams * (slots[pos] || 0);
      var superflex = sfAlloc[pos] || 0;
      var flex = flexAlloc[pos] || 0;
      var bench = benchAlloc[pos] || 0;
      out[pos] = {dedicated: dedicated, superflex: superflex, flex: flex, bench: bench,
                  rostered: dedicated + superflex + flex + bench};
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
  function projectionMaxVorp(ranked, teams, benchPerTeam, flexCount, slots, flexElig, sfCount) {
    var roster = translationRostered(teams, benchPerTeam, flexCount, ranked, slots, flexElig, sfCount);
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
      opts.slots || TRANSLATION_REF_SLOTS, opts.flexEligible || DEFAULT_FLEX_ELIGIBLE,
      Number(opts.superflexCount) || 0);
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
  //   superflexCount (default 0: dedicated superflex slots per team; when > 0
  //   each position also reports n_superflex),
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
    var sfCount = opts.superflexCount === undefined || opts.superflexCount === null
      ? 0 : Number(opts.superflexCount);
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
      roster = translationRostered(teams, benchPerTeam, flexCount, work, slots, flexElig, sfCount);
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
      if (sfCount) result.positions[pos].n_superflex = r.superflex;
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
  // The backend saves ONE setup per scoring: 12 teams, standard roster.
  // isSavedSetup says whether the reader's league is that setup. Every
  // published chart value at any setting comes from runValuePipeline
  // (JEG-508, VP-6.4: the chart's natives times one factor). The browser
  // derivation that preceded it (derivePublishedSetup, league-settings-001/6)
  // and the batch published views (derivePublishedViews,
  // published-views-001/3) were retired by JEG-539.
  var SAVED_SETUP_TEAMS = 12;
  var SAVED_SETUP_SHAPE = {QB: 1, RB: 2, WR: 3, TE: 1, FLEX: 1, BENCH: 6};

  function isSavedSetup(teams, shape) {
    if (Number(teams) !== SAVED_SETUP_TEAMS) return false;
    shape = shape || {};
    if (superflexCount(shape)) return false;
    return Object.keys(SAVED_SETUP_SHAPE).every(function (key) {
      return Number(shape[key]) === SAVED_SETUP_SHAPE[key];
    });
  }

  // DDF Composite Value (JEG-455 / JEG-471, Jeremy 2026-10-08): the
  // equal-weight mean of a player's finite values on the included series.
  // A series that does not price him is left out, never counted as 0; a
  // real 0 (ESPN lists him at 0, GAP-025) is a finite value and counts.
  // values: {seriesKey: number|null}; keys: the included series, in order.
  // Returns {value: mean or null when no included series prices him,
  // count, used: the keys that went into the mean}.
  function compositeValue(values, keys) {
    var used = [];
    var sum = 0;
    (keys || []).forEach(function (key) {
      var v = values ? values[key] : null;
      if (typeof v !== "number" || !isFinite(v)) return;
      used.push(key);
      sum += v;
    });
    return { value: used.length ? sum / used.length : null, count: used.length, used: used };
  }

  // ===================================================================
  // Value Pipeline (source-neutral), docs/methodology.md "Value Pipeline
  // (source-neutral, 2026-10-09)", VP-0..VP-8. JEG-508.
  //
  // One pure function, runValuePipeline(input), turns every source's natives
  // at one league setting into value above waivers, Adjusted values, DDF
  // Value (three versions), Indexed values and tiers. No source has a
  // special role: ESPN is a projection like CBS ROS and Razzball. The widget
  // feeds it the natives it has loaded and reads every number it shows from
  // the result; tests/test_value_pipeline_engine.py pins it to the worked
  // example (tests/fixtures/value_pipeline_worked_example.json) to 1e-6.
  //
  // input = {
  //   setting: {teams, slots: {QB,RB,WR,TE}, flex, superflex, bench_per_team,
  //             bench_share (optional; 0.15 default), position_shares
  //             (optional {pos: share})},
  //   players: {key: {pos, name?}},
  //   sources: {key: {family: "projection"|"chart", status: "included" |
  //             <exclusion reason>, values: {playerKey: native}, label?}},
  //   included: [keys] (optional; overrides status, used for the prior week
  //             so both weeks share one I, VP-8),
  //   compositeInputs: [keys] (optional; the reader's selection, VP-1.5),
  //   pie: number (optional; VP-8 prior week reuses the current pie)
  // }
  // Player keys are numeric strings; every output map is keyed by String(key).
  // ===================================================================
  var VALUE_PIPELINE_VERSION = "value-pipeline/2";
  // JEG-630: market bench ratios from config/market_bench.json (frozen,
  // Jeremy 2026-10-10). Convention rule 1: bench weight = starters * ratio,
  // then D'Hondt. Replaces the hardcoded VP_BENCH_MIX_12 {10,27,33,10}.
  var MARKET_BENCH_RATIOS = {
    one_qb: {QB: 0.88, RB: 0.83, WR: 1.03, TE: 0.40},
    two_qb: {QB: 0.28, RB: 0.69, WR: 0.85, TE: 0.44}
  };
  var VP_IMPUTE_MIN_FIT = 3;
  var VP_ESTIMATE_FIT_N = 10;
  var VP_DEFAULT_BENCH_SHARE = 0.15;
  var VP_PIE_PER_STARTING_SLOT = 28;
  var VP_FLEX_ELIGIBLE = ["RB", "WR", "TE"];
  var VP_ROLES = ["starter", "bench"];

  function vpGroupKey(pos, role) { return pos + "|" + role; }

  function vpEmptyGroups() {
    var out = {};
    POSITION_ORDER.forEach(function (pos) {
      VP_ROLES.forEach(function (role) { out[vpGroupKey(pos, role)] = 0; });
    });
    return out;
  }

  function vpPosIndex(pos) { return POSITION_ORDER.indexOf(pos); }

  // round_half_up for the bench seat total (VP-2.2d).
  function vpRoundHalfUp(x) { return Math.floor(x + 0.5); }

  // VP-2.2d: D'Hondt bench seats via roster convention (market bench ratios,
  // JEG-630). weight_p = starters_p * backups_per_starter_p, then D'Hondt
  // over POSITION_ORDER. Ties to position order (earliest wins).
  // slots: {QB:n, RB:n, WR:n, TE:n} dedicated per team.
  // opts.superflex: true when the roster has a superflex slot.
  // opts.flexFilled: optional {pos: count} of flex starters already assigned.
  function vpBenchSeats(slots, teams, benchPerTeam, opts) {
    opts = opts || {};
    var key = (opts.superflex || ((slots && slots.QB) || 1) >= 2) ? "two_qb" : "one_qb";
    var ratios = MARKET_BENCH_RATIOS[key];
    var ff = opts.flexFilled || {};
    var weights = {};
    POSITION_ORDER.forEach(function (pos) {
      var starters = ((slots && slots[pos]) || 0) + (ff[pos] || 0);
      weights[pos] = starters * (ratios[pos] || 0);
    });
    return apportionSlots(weights, vpRoundHalfUp(teams * benchPerTeam));
  }

  function vpNumKey(a, b) { return Number(a) - Number(b); }

  // VP-2.2 a-e on per-position orders. `orders[pos]` = [{key, score}] already
  // sorted best first; `score` is m (or the source's own native in the
  // degenerate case, VP-2.2f). Returns {pos: {dedicated, superflex, flex,
  // bench, starters, rostered}}.
  function vpAllocate(orders, setting) {
    var teams = Number(setting.teams) || 0;
    var slots = setting.slots || {};
    var sfSlots = Math.max(0, Number(setting.superflex) || 0);
    var flexSlots = Math.max(0, Number(setting.flex) || 0);
    var bench = vpBenchSeats(slots, teams, Math.max(0, Number(setting.bench_per_team) || 0),
                             {superflex: sfSlots > 0});
    var alloc = {};
    POSITION_ORDER.forEach(function (pos) {
      alloc[pos] = { dedicated: teams * (Number(slots[pos]) || 0), superflex: 0, flex: 0,
        bench: bench[pos], starters: 0, rostered: 0 };
    });
    function takeBest(eligiblePositions, offsetOf, count) {
      var cand = [];
      eligiblePositions.forEach(function (pos) {
        var order = orders[pos] || [];
        for (var i = offsetOf(pos); i < order.length; i += 1) {
          cand.push({ pos: pos, key: order[i].key, score: order[i].score });
        }
      });
      cand.sort(function (a, b) {
        if (a.score !== b.score) return b.score - a.score;
        var pa = vpPosIndex(a.pos), pb = vpPosIndex(b.pos);
        if (pa !== pb) return pa - pb;
        return vpNumKey(a.key, b.key);
      });
      var taken = { QB: 0, RB: 0, WR: 0, TE: 0 };
      cand.slice(0, Math.max(0, count)).forEach(function (c) { taken[c.pos] += 1; });
      return taken;
    }
    var sf = takeBest(POSITION_ORDER, function (pos) { return alloc[pos].dedicated; }, teams * sfSlots);
    POSITION_ORDER.forEach(function (pos) { alloc[pos].superflex = sf[pos]; });
    var fx = takeBest(VP_FLEX_ELIGIBLE, function (pos) {
      return alloc[pos].dedicated + alloc[pos].superflex;
    }, teams * flexSlots);
    POSITION_ORDER.forEach(function (pos) {
      var a = alloc[pos];
      a.flex = fx[pos] || 0;
      a.starters = a.dedicated + a.superflex + a.flex;
      a.rostered = a.starters + a.bench;
    });
    return alloc;
  }

  function vpMedian(xs) {
    var s = xs.slice().sort(function (a, b) { return a - b; });
    var n = s.length;
    if (!n) return null;
    return n % 2 ? s[(n - 1) / 2] : (s[n / 2 - 1] + s[n / 2]) / 2;
  }

  function vpFinite(v) { return typeof v === "number" && isFinite(v); }

  function vpLabel(sources, key) {
    var s = sources[key];
    return (s && s.label) || key;
  }

  function vpListLabels(labels) {
    if (labels.length <= 1) return labels.join("");
    if (labels.length === 2) return labels[0] + " and " + labels[1];
    return labels.slice(0, -1).join(", ") + " and " + labels[labels.length - 1];
  }

  // ===================================================================
  // Expected starts (JEG-536, es-value-001; docs/methodology.md ES-0..ES-15).
  // With input.lineup set, the two parts of ES-5 replace the VP-2.6 slices:
  // each player's value above waivers is split into a start-worthy part and
  // a fill-in part by the lineup share of his level, and the bench share
  // becomes an output (ES-14). Without input.lineup the pipeline runs the
  // VP-2.6 slices at the bench share, as before (the JEG-508 worked example).
  //
  // input.lineup = the resolved parameters (resolveLineupParameters below,
  // the mirror of pipelines/derive_lineup_parameters.resolve()):
  //   {bye, projection_confidence, positions: {pos: {m, sigma_rel, sigma_floor}}}
  // setting.bench_share_override: null (default) or a share; when set it
  // replaces the computed share as the bench groups' weight (VP-3.4).
  // ===================================================================
  var LINEUP_OBJECTIVES = ["season", "regular", "playoffs"];
  var LINEUP_INJURY_HISTORY = ["recent", "all"];
  var LINEUP_PROJECTION_CONFIDENCE = [0.5, 1, 1.5];
  var LINEUP_DEFAULT_LEAGUE_WEEKS = { regular_season_end: 14, playoff_weeks: [15, 17] };
  var BENCH_SHARE_OVERRIDE_BOUNDS = [0.01, 0.30];
  var ES_DEFAULT_CHART_SIGMA = 0.2;     // ES-15.3: no chart pair at the position
  var ES_CHART_COMMON_TOTAL = 1000;     // ES-15.3: the common scale's total

  // ES-12 window: [lo, hi]; lo > hi = empty.
  function lineupWindow(objective, contentWeek, leagueWeeks) {
    var lw = leagueWeeks || LINEUP_DEFAULT_LEAGUE_WEEKS;
    var pLo = lw.playoff_weeks[0], pHi = lw.playoff_weeks[1];
    if (objective === "season") return [contentWeek + 1, pHi];
    if (objective === "regular") return [contentWeek + 1, lw.regular_season_end];
    if (objective === "playoffs") return [Math.max(pLo, contentWeek + 1), pHi];
    throw new Error("unknown objective " + objective);
  }

  // League-wide share of team-weeks in [lo, hi] that are byes.
  function lineupByeShare(byes, lo, hi) {
    var weeks = hi - lo + 1;
    var teams = Object.keys(byes || {});
    if (!(weeks > 0) || !teams.length) return 0;
    var withBye = 0;
    teams.forEach(function (t) { var w = byes[t]; if (lo <= w && w <= hi) withBye += 1; });
    return withBye / (teams.length * weeks);
  }

  // Weeks of projection drift to the window's middle.
  function lineupDriftHorizon(win, contentWeek) {
    if (win[1] < win[0]) return 0;
    return Math.max(0, win[0] - contentWeek - 1) + (win[1] - win[0] + 1) / 2;
  }

  // Mirror of derive_lineup_parameters.resolve(cfg, objective, injury_history,
  // league_weeks, content_week, projection_confidence). `settings` keys are
  // the Python argument names; a missing one takes the config's default.
  function resolveLineupParameters(cfg, settings) {
    settings = settings || {};
    var d = cfg.defaults;
    var objective = settings.objective || d.objective;
    var injury = settings.injury_history || d.injury_history;
    var lwIn = settings.league_weeks || {};
    var leagueWeeks = {
      regular_season_end: lwIn.regular_season_end !== undefined ? lwIn.regular_season_end
        : d.league_weeks.regular_season_end,
      playoff_weeks: (lwIn.playoff_weeks || d.league_weeks.playoff_weeks).slice()
    };
    var contentWeek = settings.content_week === undefined || settings.content_week === null
      ? cfg.content_week : settings.content_week;
    var scale = settings.projection_confidence === undefined || settings.projection_confidence === null
      ? d.projection_confidence : settings.projection_confidence;
    if (LINEUP_INJURY_HISTORY.indexOf(injury) === -1) throw new Error("unknown injury history " + injury);
    var win = lineupWindow(objective, contentWeek, leagueWeeks);
    var bye = win[1] >= win[0] ? lineupByeShare(cfg.byes, win[0], win[1]) : 0;
    var h = lineupDriftHorizon(win, contentWeek);
    var out = { objective: objective, injury_history: injury, league_weeks: leagueWeeks,
      content_week: contentWeek, projection_confidence: scale, window: win, bye: bye,
      horizon_weeks: h, positions: {} };
    POSITION_ORDER.forEach(function (pos) {
      var b = cfg.positions[pos];
      var m = (objective === "playoffs" ? b.m_late : b.m)[injury];
      var weekly = b.sigma_weekly * Math.sqrt(h);
      var sig = Math.sqrt(b.sigma_now * b.sigma_now + weekly * weekly);
      out.positions[pos] = { m: m, sigma_rel: sig * scale, sigma_floor: b.sigma_floor * scale };
    });
    return out;
  }

  // erf to double precision: the all-positive series
  // erf(x) = 2/sqrt(pi) exp(-x^2) sum_n 2^n x^(2n+1) / (1*3*...*(2n+1)),
  // and +-1 beyond |x| = 6 (erfc(6) < 3e-17).
  function esErf(x) {
    if (x === 0) return 0;
    var ax = Math.abs(x);
    if (ax >= 6) return x > 0 ? 1 : -1;
    var term = ax, sum = ax, x2 = ax * ax;
    for (var n = 1; n < 500; n += 1) {
      term *= 2 * x2 / (2 * n + 1);
      sum += term;
      if (term < sum * 1e-17) break;
    }
    var r = 2 / Math.sqrt(Math.PI) * Math.exp(-x2) * sum;
    if (r > 1) r = 1;
    return x > 0 ? r : -r;
  }

  function esPhi(z) { return 0.5 * (1 + esErf(z / Math.SQRT2)); }

  // P(lo < X <= hi), X ~ N(mu, s); a point mass when s = 0; hi may be Infinity.
  function esProbBand(mu, s, lo, hi) {
    if (hi <= lo) return 0;
    if (s <= 0) return lo < mu && mu <= hi ? 1 : 0;
    var za = (lo - mu) / s;
    if (hi === Infinity) return 1 - esPhi(za);
    return esPhi((hi - mu) / s) - esPhi(za);
  }

  // Standard normal pdf (needed by esBandSurplus).
  function esNormPdf(z) {
    return Math.exp(-0.5 * z * z) / Math.sqrt(2 * Math.PI);
  }

  // JEG-530: E[(X - w)⁺ × 1{lo < X <= hi}] for X ~ N(mu, s), w <= lo.
  // The convex option form (manifesto §5): pays for the SIZE of the upside
  // in each band, not just the probability of being in it. Ported from
  // expected_starts_model.band_surplus.
  function esBandSurplus(mu, s, w, lo, hi) {
    if (hi <= lo) return 0;
    if (s <= 0) {
      return (lo < mu && (hi === Infinity || mu <= hi) && mu > w) ? (mu - w) : 0;
    }
    var za = (lo - mu) / s;
    if (hi === Infinity) {
      return (mu - w) * (1 - esPhi(za)) + s * esNormPdf(za);
    }
    var zc = (hi - mu) / s;
    return (mu - w) * (esPhi(zc) - esPhi(za)) + s * (esNormPdf(za) - esNormPdf(zc));
  }

  // P(Binomial(n, q) >= k).
  function esBinomialAtLeast(n, q, k) {
    if (k <= 0) return 1;
    if (n <= 0 || k > n) return 0;
    var total = 0;
    for (var j = k; j <= n; j += 1) {
      var c = 1;
      for (var i = 1; i <= j; i += 1) c = c * (n - j + i) / i;
      total += c * Math.pow(q, j) * Math.pow(1 - q, n - j);
    }
    return total;
  }

  // Python's round(): half to even (ES-15.2, n_p).
  function esRoundHalfEven(x) {
    var f = Math.floor(x), diff = x - f;
    if (diff > 0.5) return f + 1;
    if (diff < 0.5) return f;
    return f % 2 === 0 ? f : f + 1;
  }

  function esMean(xs) { var s = 0; xs.forEach(function (x) { s += x; }); return s / xs.length; }

  function esStdev(xs) {
    var m = esMean(xs), ss = 0;
    xs.forEach(function (x) { ss += (x - m) * (x - m); });
    return Math.sqrt(ss / (xs.length - 1));
  }

  // ES-15.3 chart sigma: the charts in I on a common scale (one factor per
  // chart, 1000 / its total over the players every one of them lists); per
  // position, players at least two charts list ranked by their mean; the
  // median of sd / mean over ranks [S'/2, N') where S', N' are the starters
  // and rostered counts position p would have filling its dedicated slots,
  // the superflex and flex slots it is eligible for, and its bench seats on
  // its own (expected_starts_model.chart_sigma_from). Listed natives only.
  function esChartSigma(chartKeys, listed, setting) {
    var teams = Number(setting.teams) || 0;
    var slots = setting.slots || {};
    var flexElig = setting.flex_eligible || VP_FLEX_ELIGIBLE;
    var bench = vpBenchSeats(slots, teams, Math.max(0, Number(setting.bench_per_team) || 0),
                             {superflex: (Number(setting.superflex) || 0) > 0});
    var maps = chartKeys.map(function (src) {
      var m = {};
      POSITION_ORDER.forEach(function (pos) { listed[src][pos].forEach(function (r) { m[r.key] = r.native; }); });
      return m;
    });
    var shared = maps.length ? Object.keys(maps[0]).filter(function (k) {
      return maps.every(function (m) { return Object.prototype.hasOwnProperty.call(m, k); });
    }).sort(vpNumKey) : [];
    var factors = maps.map(function (m) {
      var tot = 0;
      shared.forEach(function (k) { tot += m[k]; });
      return tot > 0 ? ES_CHART_COMMON_TOTAL / tot : 1;
    });
    var out = {};
    POSITION_ORDER.forEach(function (pos) {
      var acc = {};
      chartKeys.forEach(function (src, ci) {
        listed[src][pos].forEach(function (r) {
          (acc[r.key] = acc[r.key] || []).push(r.native * factors[ci]);
        });
      });
      var rows = Object.keys(acc).filter(function (k) { return acc[k].length >= 2; })
        .map(function (k) { return { key: k, mean: esMean(acc[k]), sd: esStdev(acc[k]) }; })
        .sort(function (a, b) { return a.mean !== b.mean ? b.mean - a.mean : vpNumKey(a.key, b.key); });
      var dedicated = teams * (Number(slots[pos]) || 0);
      var extra = teams * Math.max(0, Number(setting.superflex) || 0)
        + (flexElig.indexOf(pos) !== -1 ? teams * Math.max(0, Number(setting.flex) || 0) : 0);
      var starters = dedicated + Math.min(extra, Math.max(0, rows.length - dedicated));
      var rostered = starters + bench[pos];
      var band = rows.slice(Math.floor(starters / 2), rostered).filter(function (r) { return r.mean > 0; });
      out[pos] = { sigma_rel: band.length ? vpMedian(band.map(function (r) { return r.sd / r.mean; }))
        : ES_DEFAULT_CHART_SIGMA, players: rows.length, band: band.length, shared_players: shared.length,
        starters: starters, rostered: rostered };
    });
    return out;
  }

  // ES-3 / ES-4 for one source and position on its work list (sorted, listed
  // and estimated). Returns the lines, bands and each row's parts.
  function esPositionParts(work, starters, teams, waiver, starterLine, m, bye, sigmaRel, sigmaFloor) {
    var avail = (1 - bye) * (1 - m);
    var q = bye + (1 - bye) * m;
    var nPerTeam = teams ? Math.max(1, esRoundHalfEven(starters / teams)) : 1;
    var edges = [starterLine];
    for (var k = 1; ; k += 1) {
      var idx = starters + k * teams;
      if (!teams || idx >= work.length || work[idx].native <= waiver) break;
      edges.push(work[idx].native);
    }
    var bands = [];
    for (var d = 1; d < edges.length; d += 1) {
      bands.push({ depth: d, lo: edges[d], hi: edges[d - 1], fill: esBinomialAtLeast(nPerTeam, q, d) });
    }
    bands.push({ depth: edges.length, lo: waiver, hi: edges[edges.length - 1],
      fill: esBinomialAtLeast(nPerTeam, q, edges.length) });
    var parts = work.map(function (r) {
      var x = r.native;
      var s = x > 0 ? Math.max(sigmaRel * x, sigmaFloor) : sigmaFloor;
      var v = Math.max(0, x - waiver);
      var pStart = esProbBand(x, s, starterLine, Infinity);
      var fillProb = 0;
      bands.forEach(function (b) { fillProb += b.fill * esProbBand(x, s, b.lo, b.hi); });
      // JEG-530: option form parts (convex, pays for the size of the upside).
      var optStart = esBandSurplus(x, s, waiver, starterLine, Infinity);
      var optFill = 0;
      bands.forEach(function (b) { optFill += b.fill * esBandSurplus(x, s, waiver, b.lo, b.hi); });
      return { sigma: s, startWorthy: pStart, lineupShare: avail * (pStart + fillProb),
        starterPart: avail * (v * pStart), benchPart: avail * (v * fillProb),
        optionStarterPart: avail * optStart, optionBenchPart: avail * optFill };
    });
    return { avail: avail, unavailable: q, nPerTeam: nPerTeam, bands: bands, parts: parts };
  }

  function runValuePipeline(input) {
    var setting = input.setting || {};
    var players = input.players || {};
    var sources = input.sources || {};
    // Source order = the caller's order (the widget passes its canonical
    // series order; the fixture lists p1, p2, c1..c5). Peers, `m` sums and
    // the DDF source lists follow it.
    var sourceKeys = Object.keys(sources);
    var posOf = function (key) {
      var p = players[key];
      return p && vpPosIndex(p.pos) !== -1 ? p.pos : null;
    };
    var familyOf = function (key) { return sources[key].family === "projection" ? "projection" : "chart"; };

    // --- VP-1 included set
    var included, excluded = [];
    if (Array.isArray(input.included)) {
      included = sourceKeys.filter(function (k) { return input.included.indexOf(k) !== -1; });
    } else {
      included = sourceKeys.filter(function (k) { return sources[k].status === "included"; });
    }
    sourceKeys.forEach(function (k) {
      if (included.indexOf(k) === -1) {
        excluded.push({ key: k, reason: sources[k].status && sources[k].status !== "included"
          ? sources[k].status : "not included" });
      }
    });
    var inI = {};
    included.forEach(function (k) { inI[k] = true; });
    // JEG-569 part 2: hidden (held) sources participate in the pipeline
    // (weights, pie, universe) so no other source's Adjusted/VORP values
    // change.  They are excluded from the DDF blend and Indexed basis.
    var hiddenKeys = Array.isArray(input.hidden) ? input.hidden : [];
    var isHidden = {};
    hiddenKeys.forEach(function (k) { isHidden[k] = true; });

    // --- Lists (VP-0, VP-2.1): finite natives at a known position.
    var listed = {}; // src -> {pos: [{key, native}] sorted}
    var nativeOf = {}; // src -> {key: native}
    sourceKeys.forEach(function (src) {
      var vals = sources[src].values || {};
      var byPos = { QB: [], RB: [], WR: [], TE: [] };
      var nat = {};
      Object.keys(vals).forEach(function (rawKey) {
        var key = String(rawKey);
        var v = vals[rawKey];
        if (v === null || v === undefined || v === "") return;
        v = Number(v);
        if (!isFinite(v)) return;
        var pos = posOf(key);
        if (!pos) return;
        nat[key] = v;
        byPos[pos].push({ key: key, native: v });
      });
      POSITION_ORDER.forEach(function (pos) {
        byPos[pos].sort(function (a, b) {
          if (a.native !== b.native) return b.native - a.native;
          return vpNumKey(a.key, b.key);
        });
      });
      listed[src] = byPos;
      nativeOf[src] = nat;
    });

    // --- Mean points per game m (VP-0), from the projections in I.
    var projI = included.filter(function (k) { return familyOf(k) === "projection"; });
    var chartsI = included.filter(function (k) { return familyOf(k) === "chart"; });
    var meanPpg = {};
    var allKeys = {};
    sourceKeys.forEach(function (src) {
      Object.keys(nativeOf[src]).forEach(function (k) { allKeys[k] = true; });
    });
    Object.keys(allKeys).forEach(function (k) {
      var sum = 0, n = 0;
      projI.forEach(function (src) {
        if (Object.prototype.hasOwnProperty.call(nativeOf[src], k)) { sum += nativeOf[src][k]; n += 1; }
      });
      if (n) meanPpg[k] = sum / n;
    });
    var degenerate = projI.length === 0;
    var ppgOrder = {}; // pos -> [{key, score}]
    POSITION_ORDER.forEach(function (pos) {
      ppgOrder[pos] = Object.keys(meanPpg).filter(function (k) { return posOf(k) === pos; })
        .map(function (k) { return { key: k, score: meanPpg[k] }; })
        .sort(function (a, b) { return a.score !== b.score ? b.score - a.score : vpNumKey(a.key, b.key); });
    });

    // --- VP-2.2 league allocation (once, on the projected-points order).
    var allocation = degenerate ? null : vpAllocate(ppgOrder, setting);

    // --- VP-2.4a rosterable / fill sets.
    var fillSets = {};
    POSITION_ORDER.forEach(function (pos) {
      fillSets[pos] = allocation
        ? ppgOrder[pos].slice(0, allocation[pos].rostered + 1).map(function (r) { return r.key; })
        : [];
    });

    // --- Pie (VP-5.1)
    var slots = setting.slots || {};
    var startingSlots = POSITION_ORDER.reduce(function (s, p) { return s + (Number(slots[p]) || 0); }, 0)
      + (Number(setting.flex) || 0) + (Number(setting.superflex) || 0);
    var pie = vpFinite(input.pie) ? input.pie
      : VP_PIE_PER_STARTING_SLOT * (Number(setting.teams) || 0) * startingSlots;
    var bsInput = vpFinite(setting.bench_share) ? setting.bench_share : VP_DEFAULT_BENCH_SHARE;
    // ES-5 / ES-14: with lineup parameters the parts replace the slices and
    // the bench share is computed unless the reader's override is set.
    var lineup = input.lineup && input.lineup.positions ? input.lineup : null;
    var esMode = !!lineup;
    var bsOverride = vpFinite(setting.bench_share_override) ? setting.bench_share_override : null;
    if (esMode) bsInput = bsOverride;
    var esConfidence = esMode && vpFinite(lineup.projection_confidence) ? lineup.projection_confidence : 1;
    var chartSigma = esMode ? esChartSigma(chartsI, listed, setting) : null;

    // JEG-528: timing factor = fraction of the season window remaining.
    // Fill-in (bench) value scales by this; starter value does not.
    // When not in ES mode or no window, timingFactor = 1 (no discount).
    var timingFactor = 1;
    if (esMode && lineup.window && lineup.window[1] >= lineup.window[0]) {
      var windowWeeks = lineup.window[1] - lineup.window[0] + 1;
      var fullSeasonWeeks = LINEUP_DEFAULT_LEAGUE_WEEKS.playoff_weeks[1];
      timingFactor = Math.min(1, windowWeeks / fullSeasonWeeks);
    }

    var chartPeersFor = function (src) {
      return chartsI.filter(function (k) { return k !== src; });
    };

    // --- VP-2.4 fill-in estimate for chart `src`, player `key` at `pos`.
    function estimateFor(src, key, pos) {
      var own = listed[src][pos];
      var ownIndex = {};
      own.forEach(function (r) { ownIndex[r.key] = true; });
      var cap = own[own.length - 1].native;
      var info = { peers: {}, cap: cap, path: null, raw: null, value: null, capped: false };
      var ests = [];
      var usedPeers = [];
      chartPeersFor(src).forEach(function (peer) {
        var peerNat = nativeOf[peer];
        if (!Object.prototype.hasOwnProperty.call(peerNat, key)) return;
        var shared = own.filter(function (r) { return Object.prototype.hasOwnProperty.call(peerNat, r.key); });
        var fit = shared.slice(shared.length - Math.min(VP_ESTIMATE_FIT_N, shared.length));
        var num = 0, den = 0;
        fit.forEach(function (r) { num += r.native; den += peerNat[r.key]; });
        var rec = { usable: false, fitPlayers: fit.map(function (r) { return r.key; }), num: num, den: den,
          ratio: null, peerNative: peerNat[key], estimate: null };
        if (fit.length >= VP_IMPUTE_MIN_FIT && den > 0) {
          rec.usable = true;
          rec.ratio = num / den;
          rec.estimate = rec.ratio * peerNat[key];
          ests.push(rec.estimate);
          usedPeers.push(peer);
        }
        info.peers[peer] = rec;
      });
      var raw;
      if (ests.length) {
        info.path = "peers";
        info.usedPeers = usedPeers;
        raw = vpMedian(ests);
      } else {
        info.path = "curve";
        var pts = own.filter(function (r) { return vpFinite(meanPpg[r.key]); });
        pts = pts.slice(pts.length - Math.min(VP_ESTIMATE_FIT_N, pts.length));
        var mI = meanPpg[key];
        var allEqual = pts.every(function (r) { return meanPpg[r.key] === meanPpg[pts[0].key]; });
        if (pts.length >= VP_IMPUTE_MIN_FIT && !allEqual) {
          var sm = 0, sx = 0;
          pts.forEach(function (r) { sm += meanPpg[r.key]; sx += r.native; });
          var mm = sm / pts.length, mx = sx / pts.length;
          var sxy = 0, sxx = 0;
          pts.forEach(function (r) {
            var dm = meanPpg[r.key] - mm;
            sxy += dm * (r.native - mx);
            sxx += dm * dm;
          });
          var slope = sxy / sxx;
          var intercept = mx - slope * mm;
          raw = intercept + slope * mI;
          info.curve = { kind: "ols", points: pts.map(function (r) { return r.key; }), slope: slope,
            intercept: intercept, meanPpg: mI };
        } else {
          var low = null;
          own.forEach(function (r) { if (vpFinite(meanPpg[r.key]) && meanPpg[r.key] > 0) low = r; });
          if (low) {
            raw = low.native * mI / meanPpg[low.key];
            info.curve = { kind: "proportional", points: [low.key], low: low.key, meanPpg: mI };
          } else {
            raw = 0;
            info.curve = { kind: "none", points: [], meanPpg: mI };
          }
        }
      }
      info.raw = raw;
      info.value = Math.min(Math.max(raw, 0), cap);
      info.capped = raw > cap;
      var label = vpLabel(sources, src);
      info.reason = info.path === "peers"
        ? "Estimated: " + label + " doesn't list him; scaled from "
          + vpListLabels(usedPeers.map(function (k) { return vpLabel(sources, k); }))
        : "Estimated: no chart lists him; from " + label + "'s values against projected points";
      return info;
    }

    // --- VP-2 / VP-3 per source.
    var out = {};
    sourceKeys.forEach(function (src) {
      var family = familyOf(src);
      var srcAlloc = allocation;
      if (degenerate) {
        var ownOrders = {};
        POSITION_ORDER.forEach(function (pos) {
          ownOrders[pos] = listed[src][pos].map(function (r) { return { key: r.key, score: r.native }; });
        });
        srcAlloc = vpAllocate(ownOrders, setting);
      }
      var positions = {};
      var playersOut = {};
      var groups = vpEmptyGroups();
      var surplusTotal = 0;
      POSITION_ORDER.forEach(function (pos) {
        var a = srcAlloc[pos];
        var own = listed[src][pos];
        var work = own.map(function (r) { return { key: r.key, native: r.native, estimated: false }; });
        var estimates = {};
        if (family === "chart" && !degenerate && own.length) {
          var ownSet = {};
          own.forEach(function (r) { ownSet[r.key] = true; });
          fillSets[pos].forEach(function (k) {
            if (ownSet[k]) return;
            var est = estimateFor(src, k, pos);
            estimates[k] = est;
            work.push({ key: k, native: est.value, estimated: true });
          });
          work.sort(function (x, y) {
            if (x.native !== y.native) return y.native - x.native;
            if (x.estimated !== y.estimated) return x.estimated ? 1 : -1;
            return vpNumKey(x.key, y.key);
          });
        }
        var N = a.rostered, S = a.starters;
        var method, waiver = null, starterLine = null;
        if (work.length > N) {
          waiver = work[N].native;
          method = work[N].estimated ? "estimated" : "roster_determined";
        } else if (work.length) {
          waiver = work[work.length - 1].native;
          method = "insufficient_coverage";
        } else {
          method = "no_players";
        }
        if (method !== "no_players") {
          // Convention rule 3 (JEG-630): midpoint of last starter and first
          // non-starter, replacing the old first-non-starter rule.
          if (S > 0 && work.length >= S) {
            var lastStarter = work[S - 1].native;
            if (work.length > S) {
              starterLine = (lastStarter + work[S].native) / 2.0;
            } else {
              starterLine = lastStarter;
            }
          } else {
            starterLine = waiver;
          }
          starterLine = Math.max(starterLine, waiver);
        }
        // ES-3 / ES-4: the lineup share of each row's level (expected starts).
        var es = null;
        if (esMode && method !== "no_players") {
          var lp = lineup.positions[pos];
          var sigRel = family === "chart" ? chartSigma[pos].sigma_rel * esConfidence : lp.sigma_rel;
          var sigFloor = family === "chart" ? 0 : lp.sigma_floor;
          es = esPositionParts(work, S, Number(setting.teams) || 0, waiver, starterLine, lp.m, lineup.bye,
            sigRel, sigFloor);
          es.sigmaRel = sigRel;
          es.sigmaFloor = sigFloor;
          es.m = lp.m;
        }
        var bsum = 0, ssum = 0, vsum = 0;
        work.forEach(function (r, i) {
          var rank = i + 1;
          var v = Math.max(0, r.native - waiver);
          var bsl, ssl, part = es ? es.parts[i] : null;
          if (part) {
            // ES-5: start-worthy part and fill-in part (bsl := fi, ssl := sw).
            bsl = part.benchPart;
            ssl = part.starterPart;
          } else {
            bsl = Math.max(0, Math.min(r.native, starterLine) - waiver);
            ssl = Math.max(0, r.native - starterLine);
          }
          bsum += bsl; ssum += ssl; vsum += v;
          // JEG-530: option form parts (convex upside); null when not in ES mode.
          var optBsl = part ? part.optionBenchPart : null;
          var optSsl = part ? part.optionStarterPart : null;
          playersOut[r.key] = { pos: pos, native: r.native, estimated: r.estimated, rank: rank,
            role: rank <= S ? "starter" : (rank <= N ? "bench" : "waiver"),
            vorp: v, benchSlice: bsl, starterSlice: ssl, adjusted: 0, vorpDisplay: 0,
            lineupShare: part ? part.lineupShare : null, startWorthy: part ? part.startWorthy : null,
            optionBenchSlice: optBsl, optionStarterSlice: optSsl,
            optionAdjusted: 0, timingAdjusted: 0 };
        });
        groups[vpGroupKey(pos, "starter")] = ssum;
        groups[vpGroupKey(pos, "bench")] = bsum;
        surplusTotal += vsum;
        positions[pos] = { dedicated: a.dedicated, superflex: a.superflex, flex: a.flex, bench: a.bench,
          starters: S, rostered: N, listed: own.length, nEstimated: Object.keys(estimates).length,
          estimates: estimates, method: method, waiver: waiver, starterLine: starterLine,
          avail: es ? es.avail : null, bands: es ? es.bands : null,
          lineup: es ? { m: es.m, unavailable: es.unavailable, nPerTeam: es.nPerTeam,
            sigmaRel: es.sigmaRel, sigmaFloor: es.sigmaFloor } : null };
      });
      var total = 0;
      POSITION_ORDER.forEach(function (pos) {
        total += groups[vpGroupKey(pos, "starter")] + groups[vpGroupKey(pos, "bench")];
      });
      var sSum = 0, bSum = 0;
      POSITION_ORDER.forEach(function (pos) {
        sSum += groups[vpGroupKey(pos, "starter")];
        bSum += groups[vpGroupKey(pos, "bench")];
      });
      var hasWeights = total > 0;
      var starterMix = null, benchMix = null, weights = null;
      if (hasWeights) {
        if (sSum > 0) {
          starterMix = {};
          POSITION_ORDER.forEach(function (pos) { starterMix[pos] = groups[vpGroupKey(pos, "starter")] / sSum; });
        }
        if (bSum > 0) {
          benchMix = {};
          POSITION_ORDER.forEach(function (pos) { benchMix[pos] = groups[vpGroupKey(pos, "bench")] / bSum; });
        }
        weights = vpEmptyGroups();
        POSITION_ORDER.forEach(function (pos) {
          var sm = starterMix ? starterMix[pos] : 0;
          var bm = benchMix ? benchMix[pos] : 0;
          if (esMode && bsInput === null) {
            // ES-15.1: the source's own implied weights, each group's share
            // of its parts (the bench share is an output).
            weights[vpGroupKey(pos, "starter")] = groups[vpGroupKey(pos, "starter")] / total;
            weights[vpGroupKey(pos, "bench")] = groups[vpGroupKey(pos, "bench")] / total;
          } else if (starterMix && benchMix) {
            weights[vpGroupKey(pos, "starter")] = (1 - bsInput) * sm;
            weights[vpGroupKey(pos, "bench")] = bsInput * bm;
          } else {
            weights[vpGroupKey(pos, "starter")] = sm;
            weights[vpGroupKey(pos, "bench")] = bm;
          }
        });
      }
      out[src] = { family: family, status: inI[src] ? "included" : (sources[src].status || "excluded"),
        included: !!inI[src], label: vpLabel(sources, src), positions: positions, players: playersOut,
        groups: groups, totalVorp: total, surplusTotal: surplusTotal, hasWeights: hasWeights, starterMix: starterMix,
        benchMix: benchMix, weights: weights, allocation: srcAlloc };
    });

    // --- VP-4 DDF weights.
    var Sraw = {}, Braw = {};
    POSITION_ORDER.forEach(function (pos) {
      var ss = 0, sn = 0, bs = 0, bn = 0;
      included.forEach(function (src) {
        var o = out[src];
        if (!o.hasWeights || o.positions[pos].method === "no_players") return;
        if (o.starterMix) { ss += o.starterMix[pos]; sn += 1; }
        if (o.benchMix) { bs += o.benchMix[pos]; bn += 1; }
      });
      Sraw[pos] = sn ? ss / sn : 0;
      Braw[pos] = bn ? bs / bn : 0;
    });
    var sumS = 0, sumB = 0;
    POSITION_ORDER.forEach(function (pos) { sumS += Sraw[pos]; sumB += Braw[pos]; });
    var bsStar;
    var W = vpEmptyGroups();
    if (esMode && bsInput === null) {
      // ES-15.1: the mean of the sources' own weights per group (over the
      // sources VP-4.1 counts at that position), renormalized to 1. The bench
      // share applied is the bench groups' total: an output.
      var Wraw = vpEmptyGroups(), wTotal = 0;
      POSITION_ORDER.forEach(function (pos) {
        VP_ROLES.forEach(function (role) {
          var g = vpGroupKey(pos, role), sum = 0, n = 0;
          included.forEach(function (src) {
            var o = out[src];
            if (!o.hasWeights || o.positions[pos].method === "no_players") return;
            sum += o.weights[g]; n += 1;
          });
          Wraw[g] = n ? sum / n : 0;
          wTotal += Wraw[g];
        });
      });
      bsStar = 0;
      POSITION_ORDER.forEach(function (pos) {
        VP_ROLES.forEach(function (role) {
          var g = vpGroupKey(pos, role);
          W[g] = wTotal > 0 ? Wraw[g] / wTotal : 0;
        });
        bsStar += W[vpGroupKey(pos, "bench")];
      });
    } else {
      bsStar = sumB === 0 ? 0 : (sumS === 0 ? 1 : bsInput);
      POSITION_ORDER.forEach(function (pos) {
        W[vpGroupKey(pos, "starter")] = sumS > 0 ? (1 - bsStar) * Sraw[pos] / sumS : 0;
        W[vpGroupKey(pos, "bench")] = sumB > 0 ? bsStar * Braw[pos] / sumB : 0;
      });
    }
    var WBase = {};
    Object.keys(W).forEach(function (g) { WBase[g] = W[g]; });
    var shares = setting.position_shares;
    if (shares && typeof shares === "object") {
      POSITION_ORDER.forEach(function (pos) {
        if (!vpFinite(shares[pos])) return;
        var st = W[vpGroupKey(pos, "starter")], be = W[vpGroupKey(pos, "bench")];
        var sum = st + be;
        if (!(sum > 0)) return;
        W[vpGroupKey(pos, "starter")] = st * shares[pos] / sum;
        W[vpGroupKey(pos, "bench")] = be * shares[pos] / sum;
      });
    }

    // --- VP-5 budgets, rates, Adjusted, VORP display.
    var budgets = vpEmptyGroups();
    Object.keys(W).forEach(function (g) { budgets[g] = pie * W[g]; });
    sourceKeys.forEach(function (src) {
      var o = out[src];
      var rates = vpEmptyGroups();
      var funded = {};
      Object.keys(budgets).forEach(function (g) { funded[g] = budgets[g]; });
      var moved = [], unpaid = [];
      if (o.hasWeights) {
        POSITION_ORDER.forEach(function (pos) {
          VP_ROLES.forEach(function (role) {
            var g = vpGroupKey(pos, role);
            var other = vpGroupKey(pos, role === "starter" ? "bench" : "starter");
            if (o.groups[g] === 0 && budgets[g] > 0) {
              if (o.groups[other] > 0) {
                funded[other] += budgets[g];
                funded[g] = 0;
                moved.push({ from: g, to: other, amount: budgets[g] });
              } else {
                unpaid.push({ group: g, amount: budgets[g] });
              }
            }
          });
        });
        Object.keys(rates).forEach(function (g) { rates[g] = o.groups[g] > 0 ? funded[g] / o.groups[g] : 0; });
      }
      // VP-5.6: one factor per source so its value above waivers sums to the
      // pie (ES-15.4: over the surplus, which the parts no longer equal).
      var vorpFactor = o.hasWeights && o.surplusTotal > 0 ? pie / o.surplusTotal : 0;
      Object.keys(o.players).forEach(function (k) {
        var r = o.players[k];
        if (!o.hasWeights) { r.adjusted = 0; r.vorpDisplay = 0; r.optionAdjusted = 0; r.timingAdjusted = 0; return; }
        var rbench = rates[vpGroupKey(r.pos, "bench")];
        var rstarter = rates[vpGroupKey(r.pos, "starter")];
        r.adjusted = rbench * r.benchSlice + rstarter * r.starterSlice;
        r.vorpDisplay = r.vorp * vorpFactor;
        // JEG-530: option-form adjusted value (convex upside) through the
        // same share-form rates. The option premium is the difference.
        if (r.optionBenchSlice !== null && r.optionStarterSlice !== null) {
          r.optionAdjusted = rbench * r.optionBenchSlice + rstarter * r.optionStarterSlice;
        } else {
          r.optionAdjusted = r.adjusted;
        }
        // JEG-528: timing-adjusted value. The bench (fill-in) part is scaled
        // by the fraction of the season remaining (horizon). Starter part is
        // unaffected (starters produce every week they play).
        r.timingAdjusted = rbench * r.benchSlice * timingFactor + rstarter * r.starterSlice;
      });
      o.rates = rates;
      o.unfundedMoved = moved;
      o.unfundedGroups = unpaid;
      o.vorpFactor = vorpFactor;
    });

    // --- VP-6 rows.
    var rowKeys = Object.keys(allKeys).sort(vpNumKey);
    var rows = {};
    var selection = Array.isArray(input.compositeInputs) ? input.compositeInputs : null;
    var versionSources = {
      blended: included,
      charts: chartsI,
      projections: projI
    };
    function rowCell(src, key) {
      var o = out[src];
      var pos = posOf(key);
      var p = o.players[key];
      if (p) {
        return { status: p.estimated ? "estimated" : "listed", player: p };
      }
      if (o.positions[pos].method === "no_players") {
        return { status: "no_players", reason: o.label + " doesn't price " + pos };
      }
      if (o.family === "projection") {
        return { status: "unlisted", reason: o.label + " doesn't project this player" };
      }
      return { status: "below_depth", reason: "Below rosterable depth; " + o.label + " doesn't list him" };
    }
    rowKeys.forEach(function (key) {
      var row = { key: key, pos: posOf(key), name: players[key] && players[key].name,
        meanPpg: vpFinite(meanPpg[key]) ? meanPpg[key] : null,
        adjusted: {}, vorp: {}, indexed: {}, estimated: {}, estimatedPath: {}, reasons: {}, ddfByVersion: {} };
      sourceKeys.forEach(function (src) {
        var c = rowCell(src, key);
        if (c.player) {
          row.adjusted[src] = c.player.adjusted;
          row.vorp[src] = c.player.vorpDisplay;
          if (c.player.estimated) {
            var est = out[src].positions[row.pos].estimates[key];
            row.estimated[src] = est.reason;
            row.estimatedPath[src] = est.path;
          }
        } else if (c.status === "below_depth") {
          row.adjusted[src] = 0;
          row.vorp[src] = 0;
          row.reasons[src] = c.reason;
        } else {
          row.adjusted[src] = null;
          row.vorp[src] = null;
          row.reasons[src] = c.reason;
        }
      });
      // ES-10: the blended mean over I of the sources' lineup share of his
      // level and of P(X > l), over the sources with him on their work list.
      row.lineupShare = null;
      row.startWorthy = null;
      row.lineupShareBySource = {};
      if (esMode) {
        var shSum = 0, swSum = 0, shN = 0;
        sourceKeys.forEach(function (src) {
          var p = out[src].players[key];
          if (!p || p.lineupShare === null) return;
          row.lineupShareBySource[src] = p.lineupShare;
          if (!inI[src]) return;
          shSum += p.lineupShare; swSum += p.startWorthy; shN += 1;
        });
        if (shN) { row.lineupShare = shSum / shN; row.startWorthy = swSum / shN; }
      }
      // JEG-530: option value = mean over I of (optionAdjusted - adjusted).
      // JEG-528: timing value = mean over I of (adjusted - timingAdjusted).
      // Both are separate series; DDF Value is unchanged.
      row.optionValue = null;
      row.timingValue = null;
      if (esMode) {
        var optSum = 0, optN = 0, timeSum = 0, timeN = 0;
        included.forEach(function (src) {
          if (isHidden[src]) return;
          var p = out[src].players[key];
          if (!p) return;
          if (vpFinite(p.optionAdjusted) && vpFinite(p.adjusted)) {
            optSum += p.optionAdjusted - p.adjusted;
            optN += 1;
          }
          if (vpFinite(p.timingAdjusted) && vpFinite(p.adjusted)) {
            timeSum += p.adjusted - p.timingAdjusted;
            timeN += 1;
          }
        });
        if (optN) row.optionValue = optSum / optN;
        if (timeN) row.timingValue = timeSum / timeN;
      }
      Object.keys(versionSources).forEach(function (version) {
        var keys = versionSources[version].filter(function (k) {
          return !selection || selection.indexOf(k) !== -1;
        });
        // JEG-569 part 2: hidden (held) sources are excluded from the DDF
        // blend.  They contributed to weights and pie so no other source's
        // Adjusted/VORP values change; the DDF blend is recomputed from the
        // remaining visible sources.
        var used = [], sum = 0;
        keys.forEach(function (k) {
          if (isHidden[k]) return;
          var v = row.adjusted[k];
          if (!vpFinite(v)) return;
          used.push(k); sum += v;
        });
        var entry = { value: used.length ? sum / used.length : null, count: used.length, sources: used,
          lowConfidence: used.length === 1, reason: null };
        if (!included.length) entry.reason = "No source available this week";
        else if (!used.length) entry.reason = "No source prices this player";
        else if (used.length === 1) entry.reason = "Only one source prices this player";
        row.ddfByVersion[version] = entry;
      });
      rows[key] = row;
    });

    // --- VP-6.4 Indexed. Its basis is blended DDF Value over I. Reading
    // (VP-1.5): the reader's input selection "never changes ... any source's
    // values", and Indexed is a source's values, so the basis ignores the
    // selection; with no selection it is exactly the displayed blended value.
    // JEG-569 part 2: hidden sources are excluded from the basis (consistent
    // with the DDF blend) so fixedPieIndexed holds.
    var indexBasis = {};
    rowKeys.forEach(function (key) {
      var sum = 0, n = 0;
      included.forEach(function (k) {
        if (isHidden[k]) return;
        var v = rows[key].adjusted[k];
        if (!vpFinite(v)) return;
        sum += v; n += 1;
      });
      indexBasis[key] = n ? sum / n : null;
    });
    var indexed = {};
    sourceKeys.forEach(function (src) {
      var o = out[src];
      if (o.family !== "chart") return;
      var ddfTotal = 0, nativeTotal = 0, n = 0;
      POSITION_ORDER.forEach(function (pos) {
        listed[src][pos].forEach(function (r) {
          var d = indexBasis[r.key];
          if (!vpFinite(d)) return;
          ddfTotal += d; nativeTotal += r.native; n += 1;
        });
      });
      // Ruling 7 (JEG-508): a basis total <= 0 gives a null factor, never 0.
      var factor = n && nativeTotal > 0 && ddfTotal > 0 ? ddfTotal / nativeTotal : null;
      indexed[src] = { factor: factor, sharedPlayers: n, ddfTotal: ddfTotal, nativeTotal: nativeTotal };
      o.indexedFactor = factor;
      rowKeys.forEach(function (key) {
        var row = rows[key];
        var p = o.players[key];
        if (p) {
          row.indexed[src] = factor === null ? null : p.native * factor;
          if (factor === null) row.reasons[src] = row.reasons[src] || "Not enough shared players to index";
        } else {
          // Lead's ruling 4 (JEG-508): with a null factor the whole chart's
          // Indexed series is null, players below rosterable depth included.
          row.indexed[src] = factor !== null && row.adjusted[src] === 0 ? 0 : null;
        }
      });
    });
    sourceKeys.forEach(function (src) {
      if (out[src].family === "projection") {
        out[src].indexedFactor = null;
        rowKeys.forEach(function (key) { rows[key].indexed[src] = rows[key].adjusted[src]; });
      }
    });

    // --- VP-7 slot fill, tiers, ranking.
    var slotFill = allocation;
    if (!slotFill) {
      var ddfOrders = {};
      POSITION_ORDER.forEach(function (pos) {
        ddfOrders[pos] = rowKeys.filter(function (k) {
          return rows[k].pos === pos && vpFinite(rows[k].ddfByVersion.blended.value);
        }).map(function (k) { return { key: k, score: rows[k].ddfByVersion.blended.value }; })
          .sort(function (a, b) { return a.score !== b.score ? b.score - a.score : vpNumKey(a.key, b.key); });
      });
      slotFill = vpAllocate(ddfOrders, setting);
    }
    POSITION_ORDER.forEach(function (pos) {
      var ranked = rowKeys.filter(function (k) {
        return rows[k].pos === pos && vpFinite(rows[k].ddfByVersion.blended.value);
      }).sort(function (a, b) {
        var da = rows[a].ddfByVersion.blended.value, db = rows[b].ddfByVersion.blended.value;
        if (da !== db) return db - da;
        var ma = rows[a].meanPpg, mb = rows[b].meanPpg;
        if (ma !== mb) {
          if (ma === null) return 1;
          if (mb === null) return -1;
          return mb - ma;
        }
        return vpNumKey(a, b);
      });
      ranked.forEach(function (k, i) {
        var rank = i + 1;
        var v = rows[k].ddfByVersion.blended.value;
        rows[k].tier = v === 0 ? "waiver"
          : (rank <= slotFill[pos].starters ? "starter" : (rank <= slotFill[pos].rostered ? "bench" : "waiver"));
      });
    });
    rowKeys.forEach(function (k) { if (rows[k].tier === undefined) rows[k].tier = null; });
    var defaultRanking = rowKeys.slice().sort(function (a, b) {
      var da = rows[a].ddfByVersion.blended.value, db = rows[b].ddfByVersion.blended.value;
      var fa = vpFinite(da), fb = vpFinite(db);
      if (fa !== fb) return fa ? -1 : 1;
      if (fa && da !== db) return db - da;
      return vpNumKey(a, b);
    });

    // ES-14 readout: the bench tier's share of each position's blended DDF
    // Value and of the whole (players ranked S_p+1..N_p on the projected-
    // points order of VP-2.2, over every player in that order; blended over
    // I, the reader's input selection ignored like the Indexed basis).
    var readout = null;
    if (!degenerate) {
      readout = { QB: null, RB: null, WR: null, TE: null, overall: null,
        override: esMode ? bsOverride !== null : true,
        overrideValue: esMode ? bsOverride : bsInput,
        fillInShare: bsStar,
        method: esMode ? "expected-starts" : "fixed-share" };
      var benchAll = 0, totalAll = 0;
      POSITION_ORDER.forEach(function (pos) {
        var bench = 0, total = 0;
        ppgOrder[pos].forEach(function (r, i) {
          var v = indexBasis[r.key];
          if (!vpFinite(v)) return;
          total += v;
          if (i >= allocation[pos].starters && i < allocation[pos].rostered) bench += v;
        });
        readout[pos] = total > 0 ? bench / total : null;
        benchAll += bench; totalAll += total;
      });
      readout.overall = totalAll > 0 ? benchAll / totalAll : null;
    }

    return {
      version: VALUE_PIPELINE_VERSION,
      setting: setting,
      pie: pie,
      method: esMode ? "expected-starts" : "slices",
      benchShare: readout,
      benchShareInput: bsInput,
      benchShareOverride: esMode ? bsOverride : null,
      lineup: lineup,
      chartSigma: chartSigma,
      benchShareApplied: bsStar,
      included: included,
      excluded: excluded,
      degenerate: degenerate,
      meanPpg: meanPpg,
      allocation: allocation,
      slotFill: slotFill,
      fillSets: fillSets,
      starterMixMean: Sraw,
      benchMixMean: Braw,
      ddfWeights: W,
      ddfWeightsBeforeShares: WBase,
      budgets: budgets,
      sources: out,
      indexed: indexed,
      rows: rows,
      defaultRanking: defaultRanking,
      timingFactor: timingFactor
    };
  }

  // Compact, JSON-safe summary for TradeValueCurveDiagnostics.valuePipeline
  // (VP-11). Player-level detail stays on the rows.
  function valuePipelineDiagnostics(result) {
    var sources = {};
    Object.keys(result.sources).forEach(function (src) {
      var o = result.sources[src];
      var positions = {};
      POSITION_ORDER.forEach(function (pos) {
        var p = o.positions[pos];
        var estimates = {};
        Object.keys(p.estimates).forEach(function (k) {
          var e = p.estimates[k];
          var peers = {};
          Object.keys(e.peers).forEach(function (peer) {
            var r = e.peers[peer];
            peers[peer] = { usable: r.usable, fitPlayers: r.fitPlayers, ratio: r.ratio, estimate: r.estimate };
          });
          estimates[k] = { path: e.path, peers: peers, curve: e.curve || null, raw: e.raw, cap: e.cap,
            capped: e.capped, value: e.value, reason: e.reason };
        });
        positions[pos] = { method: p.method, waiver: p.waiver, starterLine: p.starterLine,
          starters: p.starters, rostered: p.rostered, listed: p.listed, nEstimated: p.nEstimated,
          avail: p.avail, bands: p.bands, lineup: p.lineup, estimates: estimates };
      });
      sources[src] = { family: o.family, included: o.included, totalVorp: o.totalVorp,
        surplusTotal: o.surplusTotal, groups: o.groups,
        weights: o.weights, starterMix: o.starterMix, benchMix: o.benchMix, rates: o.rates,
        unfundedGroups: o.unfundedGroups, unfundedMoved: o.unfundedMoved, vorpFactor: o.vorpFactor,
        indexedFactor: o.indexedFactor === undefined ? null : o.indexedFactor, positions: positions };
    });
    return {
      version: result.version, setting: result.setting, pie: result.pie, method: result.method,
      benchShare: result.benchShare, benchShareInput: result.benchShareInput,
      benchShareOverride: result.benchShareOverride, lineup: result.lineup, chartSigma: result.chartSigma,
      benchShareApplied: result.benchShareApplied, included: result.included, excluded: result.excluded,
      degenerate: result.degenerate, ddfWeights: result.ddfWeights, allocation: result.allocation,
      slotFill: result.slotFill, fillSets: result.fillSets, sources: sources
    };
  }

  root.ValueModel = {
    VALUE_PIPELINE_VERSION: VALUE_PIPELINE_VERSION,
    VP_DEFAULT_BENCH_SHARE: VP_DEFAULT_BENCH_SHARE,
    VP_PIE_PER_STARTING_SLOT: VP_PIE_PER_STARTING_SLOT,
    runValuePipeline: runValuePipeline,
    resolveLineupParameters: resolveLineupParameters,
    lineupWindow: lineupWindow,
    LINEUP_OBJECTIVES: LINEUP_OBJECTIVES,
    LINEUP_INJURY_HISTORY: LINEUP_INJURY_HISTORY,
    LINEUP_PROJECTION_CONFIDENCE: LINEUP_PROJECTION_CONFIDENCE,
    LINEUP_DEFAULT_LEAGUE_WEEKS: LINEUP_DEFAULT_LEAGUE_WEEKS,
    BENCH_SHARE_OVERRIDE_BOUNDS: BENCH_SHARE_OVERRIDE_BOUNDS,
    esErf: esErf,
    esNormPdf: esNormPdf,
    esBandSurplus: esBandSurplus,
    esBinomialAtLeast: esBinomialAtLeast,
    valuePipelineDiagnostics: valuePipelineDiagnostics,
    compositeValue: compositeValue,
    SAVED_SETUP_TEAMS: SAVED_SETUP_TEAMS,
    SAVED_SETUP_SHAPE: SAVED_SETUP_SHAPE,
    isSavedSetup: isSavedSetup,
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
    POSITION_ORDER: POSITION_ORDER,
    DEFAULT_FLEX_ELIGIBLE: DEFAULT_FLEX_ELIGIBLE,
    MIN_SHARED_FOR_PIE: MIN_SHARED_FOR_PIE,
    sourceComboKey: sourceComboKey,
    flexEligible: flexEligible,
    SUPERFLEX_ELIGIBLE: SUPERFLEX_ELIGIBLE,
    superflexCount: superflexCount,
    stableTiebreak: stableTiebreak
  };
})(typeof globalThis !== "undefined" ? globalThis : this);

if (typeof module !== "undefined" && module.exports) module.exports = globalThis.ValueModel;
