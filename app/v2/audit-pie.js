// Health check tab (JEG-1011, was the Value pie tab of JEG-848): a plain "is anything
// wrong?" verdict first, one row per check, then drill-down tables that explain
// each row. Built for catching bad numbers fast.
//
// Pure read of the engine's runValuePipeline result via getInspection().
// No value math: every number shown is derived from the engine's own fields
// (adjusted, groups, positions, budgets, pie, indexed, ddf). The verdict rows
// and the tables come from the same computeChecks() result, so a row can
// never say pass while its table says flag.
//
// Contract: window.DDFAudit.register("health-check", render) where render(root, ctx)
// receives the mount element (#audit-pie-root) and ctx = {slug, engine} where
// engine = TradeValueCurveControls. Called by renderAudit() on tab show, setting
// change, and source-availability change. Must be idempotent (rebuilds mount
// each call). Guards for window.TradeValueV2 being undefined on first call.
(function (root) {
  "use strict";

  var POSITIONS = ["QB", "RB", "WR", "TE"];
  var FLAG_THRESHOLD = 0.10; // a per-slot value more than 10% from the middle source

  // Flag thresholds (JEG-1011, protected: change only with a logged justification
  // in docs/claude-log and the changelog). Derived from the engine's own output on
  // the training weeks and validated on held-out weeks by
  // tools/audit_health_thresholds.py (see docs/health-check-thresholds.md).
  var THRESHOLDS = Object.freeze({
    starterSpread: 0.17,           // all starters: (highest - lowest) / middle source, across sources
    positionStarterSpread: 0.24,   // RB, WR, TE starters (QB is informational, never flagged)
    positionTotalSpread: 0.01,     // a position's total is equal across sources by construction (floor)
    pieDelta: 0.5,                 // a source's total adjusted vs the value pie, points (floor)
    estimatedShare: 0.75,          // filled-in share of a position's rostered slots (largest healthy 63% + 10 points)
    reconcileDelta: 1.0            // Player values sum vs pie (projections), Rescaled vs DDF Value (charts), points (floor)
  });
  var BENCH_NOTE_MIN = 0.25;       // show the "bench is priced differently" explanation above this spread
  var RAW_SHIFT_NOTE = 0.15;       // raw -> adjusted shift worth a highlight in the collapsed table

  // ── Helpers ──────────────────────────────────────────────────────────

  function median(arr) {
    if (!arr.length) return 0;
    var sorted = arr.slice().sort(function (a, b) { return a - b; });
    var mid = Math.floor(sorted.length / 2);
    return sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
  }

  function spread(arr) {
    if (arr.length < 2) return 0;
    var min = Math.min.apply(null, arr);
    var max = Math.max.apply(null, arr);
    var med = median(arr);
    if (!med) return 0;
    return (max - min) / Math.abs(med);
  }

  function flagged(value, med) {
    if (value == null || !Number.isFinite(value) || !med) return false;
    return Math.abs((value - med) / Math.abs(med)) > FLAG_THRESHOLD;
  }

  // JEG-912: a rounding residue never shows a sign ("-0.00" is "0.00").
  function noNegZero(text) {
    return /^-0(\.0+)?$/.test(text) ? text.slice(1) : text;
  }

  function fmt(v, decimals) {
    if (v == null || !Number.isFinite(v)) return "—";
    return noNegZero(v.toFixed(decimals == null ? 1 : decimals)).replace("-", "−");
  }

  function fmtPct(v) {
    if (v == null || !Number.isFinite(v)) return "—";
    var text = noNegZero((v * 100).toFixed(1));
    return (text === "0.0" ? "" : text.startsWith("-") ? "−" + text.slice(1) : "+" + text) + (text === "0.0" ? "0.0" : "") + "%";
  }

  function fmtSpreadPct(v) {
    if (v == null || !Number.isFinite(v)) return "—";
    return (v * 100).toFixed(1) + "%";
  }

  function pctWhole(v) { return Math.round(v * 100) + "%"; }

  function el(tag, cls, text) {
    var node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text != null) node.textContent = String(text);
    return node;
  }

  function th(text, cls) {
    var node = el("th", cls || "", text);
    node.setAttribute("scope", "col");   // JEG-904
    return node;
  }
  function rowHead(text, cls) { return el("td", cls || "audit-pie-source", text); }   // JEG-904: every th in these tables is scope=col
  function td(text, cls) { return el("td", cls || "", text); }

  // ── Data extraction ─────────────────────────────────────────────────
  // Fields used (all from getInspection().valuePipeline, .players and .rows):
  //   groups[pos|role]         -- a source's pre-rescale group totals ("raw")
  //   players[src][key]        -- adjusted (rescaled value), pos, role, estimated
  //   positions[pos]           -- listed, starters, rostered, nEstimated
  //   budgets[pos|role]        -- the value pie's budget per group
  //   pie                      -- the league's value pie
  //   rows[key].indexed[src]   -- what Player values shows per source (Rescaled for charts)
  //   rows[key].ddf            -- the blended DDF Value (reduced fixtures) or
  //   rows[key].ddfByVersion.blended.value (live)

  function rowDdf(r) {
    if (!r) return null;
    if (Number.isFinite(r.ddf)) return r.ddf;
    var b = r.ddfByVersion && r.ddfByVersion.blended;
    return b && Number.isFinite(b.value) ? b.value : null;
  }

  function extract(inspection) {
    if (!inspection || !inspection.valuePipeline) return null;
    var vp = inspection.valuePipeline;
    var pie = vp.pie;
    var sources = vp.sources;
    var ddfWeights = vp.ddfWeights || {};
    // The pipeline exposes ddfWeights but not the funded object directly:
    // budget = DDF weight x pie.
    var budgets = vp.budgets || {};
    if (!Object.keys(budgets).length && Object.keys(ddfWeights).length) {
      Object.keys(ddfWeights).forEach(function (g) {
        budgets[g] = ddfWeights[g] * pie;
      });
    }
    var allocation = vp.allocation || {};
    var players = inspection.players || {};
    var engineRows = inspection.rows || null;
    var sourceKeys = Object.keys(sources);
    if (!sourceKeys.length) return null;

    var rows = [];
    sourceKeys.forEach(function (src) {
      var s = sources[src];
      var ps = players[src] || {};
      var groups = s.groups || {};

      // JEG-871: the Adjusted total counts estimated players (fill-ins) and always
      // equals the pie. Split it into the source's own posted values and the filled-in
      // ones, and read what the Player values table shows for this source
      // (rows[key].indexed[src]: the Rescaled chart view for charts, equal to
      // Adjusted for projections) so the audit reconciles to that table's column sum.
      var ownAdjusted = 0, filledAdjusted = 0;
      Object.keys(ps).forEach(function (key) {
        var p = ps[key];
        if (p.estimated) filledAdjusted += p.adjusted || 0;
        else ownAdjusted += p.adjusted || 0;
      });
      var tableTotal = null;
      // JEG-1011: a chart's Rescaled values for the players it lists must sum to
      // those players' DDF Value (that is how the factor is set), so the real
      // chart reconciliation compares those two sums.
      var sharedRescaled = 0, sharedDdf = 0, sharedCount = 0;
      if (engineRows) {
        Object.keys(engineRows).forEach(function (key) {
          var r = engineRows[key];
          var v = r && r.indexed ? r.indexed[src] : null;
          if (Number.isFinite(v)) {
            tableTotal = (tableTotal || 0) + v;
            var d = rowDdf(r);
            if (ps[key] && !ps[key].estimated && d != null) {
              sharedRescaled += v;
              sharedDdf += d;
              sharedCount += 1;
            }
          }
        });
      }

      // Per-position breakdown
      var posData = [];
      var totalListed = 0, totalRostered = 0, totalEstimated = 0;
      var totalAdjusted = 0, totalRawSlice = 0;
      var starterTotal = 0, benchTotal = 0;
      var starterRawTotal = 0, benchRawTotal = 0;

      POSITIONS.forEach(function (pos) {
        var posInfo = (s.positions && s.positions[pos]) || {};
        var listed = posInfo.listed || 0;
        var starters = posInfo.starters || 0;
        var rostered = posInfo.rostered || 0;
        var nEstimated = posInfo.nEstimated || 0;
        var benchCount = rostered - starters;

        // Raw (before rescaling): the pipeline's group totals.
        var starterRaw = groups[pos + "|starter"] || 0;
        var benchRaw = groups[pos + "|bench"] || 0;

        // Adjusted: sum from per-player data (the rescaled values)
        var starterAdj = 0, benchAdj = 0;
        Object.keys(ps).forEach(function (key) {
          var p = ps[key];
          if (p.pos !== pos) return;
          if (p.role === "starter") {
            starterAdj += p.adjusted || 0;
          } else if (p.role === "bench") {
            benchAdj += p.adjusted || 0;
          }
        });

        var posAdj = starterAdj + benchAdj;
        var posRaw = starterRaw + benchRaw;
        var budget = (budgets[pos + "|starter"] || 0) + (budgets[pos + "|bench"] || 0);

        totalListed += listed;
        totalRostered += rostered;
        totalEstimated += nEstimated;
        totalAdjusted += posAdj;
        totalRawSlice += posRaw;
        starterTotal += starterAdj;
        benchTotal += benchAdj;
        starterRawTotal += starterRaw;
        benchRawTotal += benchRaw;

        posData.push({
          pos: pos,
          listed: listed,
          starters: starters,
          bench: benchCount,
          rostered: rostered,
          nEstimated: nEstimated,
          estShare: rostered > 0 ? nEstimated / rostered : null,
          starterAdj: starterAdj,
          benchAdj: benchAdj,
          posAdj: posAdj,
          starterRaw: starterRaw,
          benchRaw: benchRaw,
          posRaw: posRaw,
          budget: budget,
          perRosterable: rostered > 0 ? posAdj / rostered : null,
          perListed: listed > 0 ? posAdj / listed : null
        });
      });

      rows.push({
        src: src,
        family: s.family,
        included: s.included,
        positions: posData,
        totalListed: totalListed,
        totalRostered: totalRostered,
        totalEstimated: totalEstimated,
        estShare: totalRostered > 0 ? totalEstimated / totalRostered : null,
        totalAdjusted: totalAdjusted,
        ownAdjusted: ownAdjusted,
        filledAdjusted: filledAdjusted,
        tableTotal: tableTotal,
        sharedRescaled: sharedCount ? sharedRescaled : null,
        sharedDdf: sharedCount ? sharedDdf : null,
        totalRawSlice: totalRawSlice,
        starterTotal: starterTotal,
        benchTotal: benchTotal,
        starterRawTotal: starterRawTotal,
        benchRawTotal: benchRawTotal,
        perListed: totalListed > 0 ? totalAdjusted / totalListed : null,
        perRosterable: totalRostered > 0 ? totalAdjusted / totalRostered : null
      });
    });

    return {pie: pie, budgets: budgets, ddfWeights: ddfWeights, allocation: allocation, rows: rows,
      setting: inspection.setting || null};
  }

  // ── Per-slot flags (more than 10% from the middle source) ───────────

  function computeFlags(data) {
    if (!data || !data.rows.length) return;

    var perListedValues = data.rows.map(function (r) { return r.perListed; }).filter(Number.isFinite);
    var perRosterableValues = data.rows.map(function (r) { return r.perRosterable; }).filter(Number.isFinite);
    var medPerListed = median(perListedValues);
    var medPerRosterable = median(perRosterableValues);

    data.rows.forEach(function (r) {
      r.flagPerListed = flagged(r.perListed, medPerListed);
      r.flagPerRosterable = flagged(r.perRosterable, medPerRosterable);
      r.medPerListed = medPerListed;
      r.medPerRosterable = medPerRosterable;
    });

    POSITIONS.forEach(function (pos, pi) {
      var posPerRosterable = data.rows.map(function (r) {
        return r.positions[pi].perRosterable;
      }).filter(Number.isFinite);
      var posPerListed = data.rows.map(function (r) {
        return r.positions[pi].perListed;
      }).filter(Number.isFinite);
      var medPosRosterable = median(posPerRosterable);
      var medPosListed = median(posPerListed);

      data.rows.forEach(function (r) {
        var pd = r.positions[pi];
        pd.flagPerRosterable = flagged(pd.perRosterable, medPosRosterable);
        pd.flagPerListed = flagged(pd.perListed, medPosListed);
        pd.medPerRosterable = medPosRosterable;
        pd.medPerListed = medPosListed;
      });
    });
  }

  // ── Cross-source spread per cut ─────────────────────────────────────

  function computeVerdicts(data) {
    if (!data || !data.rows.length) return {};

    var verdicts = {};
    var starterVals = data.rows.map(function (r) { return r.starterTotal; }).filter(Number.isFinite);
    var benchVals = data.rows.map(function (r) { return r.benchTotal; }).filter(Number.isFinite);
    var totalVals = data.rows.map(function (r) { return r.totalAdjusted; }).filter(Number.isFinite);

    verdicts.starters = {spread: spread(starterVals), within: spread(starterVals) <= THRESHOLDS.starterSpread};
    // Bench spread is informational (JEG-859): it never fails, so "within" is always true.
    verdicts.bench = {spread: spread(benchVals), within: true, informational: true};
    verdicts.total = {spread: spread(totalVals), within: spread(totalVals) <= THRESHOLDS.positionTotalSpread};

    verdicts.positions = {};
    POSITIONS.forEach(function (pos, pi) {
      var posStarters = data.rows.map(function (r) { return r.positions[pi].starterAdj; }).filter(Number.isFinite);
      var posBench = data.rows.map(function (r) { return r.positions[pi].benchAdj; }).filter(Number.isFinite);
      var posTotal = data.rows.map(function (r) { return r.positions[pi].posAdj; }).filter(Number.isFinite);

      verdicts.positions[pos] = {
        starters: {spread: spread(posStarters),
          within: pos === "QB" ? true : spread(posStarters) <= THRESHOLDS.positionStarterSpread,
          informational: pos === "QB"},
        bench: {spread: spread(posBench), within: true, informational: true},
        total: {spread: spread(posTotal), within: spread(posTotal) <= THRESHOLDS.positionTotalSpread}
      };
    });

    return verdicts;
  }

  // ── Labels ──────────────────────────────────────────────────────────

  // JEG-872: one name per source across the site. On the page the map is
  // v2.js's PUBLISHERS (symbol + label, the Player values headers); the
  // fallback below is for the standalone test harness only and mirrors it.
  var SOURCE_LABELS = {
    espn: {label: "ESPN", symbol: "●"},
    fantasycalc: {label: "FantasyCalc", symbol: "■"},
    fantasypros: {label: "FantasyPros", symbol: "▲"},
    usatoday: {label: "USA Today", symbol: "◆"},
    cbs: {label: "CBS Sports", symbol: "▼"},
    cbsros: {label: "CBS rest of season", symbol: "▽"},
    razzball: {label: "Razzball", symbol: "✚"}
  };

  function publisher(src) {
    // JEG-861/872: plain names only; the engine's own label is never used.
    var v2 = root.TradeValueV2;
    var map = v2 ? (typeof v2.publishers === "function" ? v2.publishers() : {}) : SOURCE_LABELS;
    var pub = map && map[src];
    return pub && pub.label ? pub : null;
  }
  // Table cells: symbol + name. Sentences: name only.
  function sourceLabel(src) {
    var pub = publisher(src);
    if (!pub) return src;
    return (pub.symbol ? pub.symbol + " " : "") + pub.label;
  }
  function plainLabel(src) {
    var pub = publisher(src);
    return pub ? pub.label : src;
  }

  // ── Checks: one row each in the verdict strip ───────────────────────
  // computeChecks(data) -> [{id, section, name, status: "pass"|"flag"|"info",
  //   reason, sources: [keys named], positions: [names], numbers: {...}}]
  // Status depends only on numbers and THRESHOLDS, never on the wording.

  function spreadInfo(rows, pick) {
    var items = rows.map(function (r) { return {src: r.src, v: pick(r)}; })
      .filter(function (i) { return Number.isFinite(i.v); });
    if (!items.length) return {n: 0, spread: 0, middle: 0, hi: null, lo: null, outlier: null};
    var vals = items.map(function (i) { return i.v; });
    var mid = median(vals);
    var hi = items[0], lo = items[0], out = items[0];
    items.forEach(function (i) {
      if (i.v > hi.v) hi = i;
      if (i.v < lo.v) lo = i;
      if (Math.abs(i.v - mid) > Math.abs(out.v - mid)) out = i;
    });
    return {n: items.length, spread: spread(vals), middle: mid, hi: hi, lo: lo,
      outlier: {src: out.src, v: out.v, dev: mid ? (out.v - mid) / Math.abs(mid) : 0}};
  }

  function direction(info) { return info.outlier.dev >= 0 ? "above" : "below"; }

  function computeChecks(data) {
    if (!data || !data.rows.length) return [];
    var T = THRESHOLDS;
    var rows = data.rows;
    var checks = [];

    // 1. Starters agree (all positions together).
    var st = spreadInfo(rows, function (r) { return r.starterTotal; });
    var stFlag = st.spread > T.starterSpread;
    checks.push({
      id: "starters", section: "starters", name: "Starter totals",
      status: stFlag ? "flag" : "pass",
      sources: stFlag ? [st.outlier.src] : [], positions: [],
      numbers: {spread: st.spread, limit: T.starterSpread},
      reason: stFlag
        ? plainLabel(st.outlier.src) + ", all positions: " + pctWhole(Math.abs(st.outlier.dev)) + " " + direction(st) +
          " the middle source (spread " + fmtSpreadPct(st.spread) + ", limit " + pctWhole(T.starterSpread) + ")."
        : "All " + st.n + " sources agree (spread " + fmtSpreadPct(st.spread) + ", limit " + pctWhole(T.starterSpread) + ")."
    });

    // 2. Positions agree (RB, WR, TE; QB is shown on its own row).
    var posInfo = {};
    POSITIONS.forEach(function (pos, pi) {
      posInfo[pos] = spreadInfo(rows, function (r) { return r.positions[pi].starterAdj; });
    });
    var flaggedPos = ["RB", "WR", "TE"].filter(function (pos) { return posInfo[pos].spread > T.positionStarterSpread; });
    flaggedPos.sort(function (a, b) { return posInfo[b].spread - posInfo[a].spread; });
    var worst = flaggedPos.length ? posInfo[flaggedPos[0]] : null;
    checks.push({
      id: "positions", section: "positions", name: "RB, WR and TE starters",
      status: flaggedPos.length ? "flag" : "pass",
      sources: flaggedPos.length ? flaggedPos.map(function (p) { return posInfo[p].outlier.src; })
        .filter(function (v, i, a) { return a.indexOf(v) === i; }) : [],
      positions: flaggedPos,
      numbers: {RB: posInfo.RB.spread, WR: posInfo.WR.spread, TE: posInfo.TE.spread, limit: T.positionStarterSpread},
      reason: flaggedPos.length
        ? flaggedPos[0] + ": " + plainLabel(worst.outlier.src) + " is " + pctWhole(Math.abs(worst.outlier.dev)) + " " +
          direction(worst) + " the middle source (spread " + fmtSpreadPct(worst.spread) + ", limit " + pctWhole(T.positionStarterSpread) + ")" +
          (flaggedPos.length > 1 ? "; also " + flaggedPos.slice(1).join(", ") : "") + "."
        : "RB " + fmtSpreadPct(posInfo.RB.spread) + ", WR " + fmtSpreadPct(posInfo.WR.spread) + ", TE " +
          fmtSpreadPct(posInfo.TE.spread) + ": all within the " + pctWhole(T.positionStarterSpread) + " limit."
    });

    // 3. QB starters: informational, never flagged (Jeremy, 2026-10-24).
    var qb = posInfo.QB;
    checks.push({
      id: "qb", section: "positions", name: "QB starters",
      status: "info", sources: [], positions: ["QB"],
      numbers: {spread: qb.spread},
      reason: "Spread " + fmtSpreadPct(qb.spread) + (qb.hi ? " (" + plainLabel(qb.hi.src) + " high, " + plainLabel(qb.lo.src) + " low)" : "") +
        ". Expected; never flagged."
    });

    // 4. Bench: informational (JEG-859).
    var bench = spreadInfo(rows, function (r) { return r.benchTotal; });
    checks.push({
      id: "bench", section: "starters", name: "Bench totals",
      status: "info", sources: [], positions: [],
      numbers: {spread: bench.spread},
      reason: "Spread " + fmtSpreadPct(bench.spread) + ". Expected: sources price bench differently."
    });

    // 5. Totals add up: every source's total is the pie; a position's total is the same across sources.
    var off = rows.filter(function (r) { return Math.abs(r.totalAdjusted - data.pie) > T.pieDelta; });
    var badPos = POSITIONS.filter(function (pos, pi) {
      return spread(rows.map(function (r) { return r.positions[pi].posAdj; }).filter(Number.isFinite)) > T.positionTotalSpread;
    });
    var slotOff = rows.filter(function (r) { return r.flagPerRosterable; });
    var totalsFlag = off.length || badPos.length || slotOff.length;
    var totalsSources = off.concat(slotOff).map(function (r) { return r.src; }).filter(function (v, i, a) { return a.indexOf(v) === i; });
    checks.push({
      id: "totals", section: "starters", name: "Totals vs the value pie",
      status: totalsFlag ? "flag" : "pass", sources: totalsSources, positions: badPos,
      numbers: {limit: T.pieDelta},
      reason: totalsFlag
        ? (off.length ? plainLabel(off[0].src) + ", all positions: adds up to " + fmt(off[0].totalAdjusted) + ", not the value pie " + fmt(data.pie) + "."
          : badPos.length ? badPos[0] + " totals differ between sources by over " + pctWhole(T.positionTotalSpread) + "."
          : plainLabel(slotOff[0].src) + " value per roster slot is over " + pctWhole(FLAG_THRESHOLD) + " from the middle source.")
        : "Every source adds up to the value pie (" + fmt(data.pie) + ")."
    });

    // 6. Few filled-in players: share of a position's rostered slots with a fill-in value.
    var cover = [];
    rows.forEach(function (r) {
      r.positions.forEach(function (pd) {
        if (pd.estShare != null && pd.estShare > T.estimatedShare) {
          cover.push({src: r.src, pos: pd.pos, n: pd.nEstimated, of: pd.rostered, share: pd.estShare});
        }
      });
    });
    cover.sort(function (a, b) { return b.share - a.share; });
    var maxShare = 0;
    rows.forEach(function (r) { r.positions.forEach(function (pd) { if (pd.estShare != null && pd.estShare > maxShare) maxShare = pd.estShare; }); });
    checks.push({
      id: "coverage", section: "coverage", name: "Filled-in players",
      status: cover.length ? "flag" : "pass",
      sources: cover.map(function (c) { return c.src; }).filter(function (v, i, a) { return a.indexOf(v) === i; }),
      positions: cover.map(function (c) { return c.pos; }).filter(function (v, i, a) { return a.indexOf(v) === i; }),
      numbers: {max: maxShare, limit: T.estimatedShare, cells: cover.length},
      reason: cover.length
        ? plainLabel(cover[0].src) + " " + cover[0].pos + ": " + cover[0].n + " of " + cover[0].of + " slots filled in (" +
          pctWhole(cover[0].share) + ", limit " + pctWhole(T.estimatedShare) + ")" +
          (cover.length > 1 ? "; " + (cover.length - 1) + " more below" : "") + "."
        : "At most " + pctWhole(maxShare) + " of any position's slots filled in (limit " + pctWhole(T.estimatedShare) + ")."
    });

    // 7. Player values tie out: projections to the pie, charts to DDF Value on the players they list.
    var recon = [];
    rows.forEach(function (r) {
      if (r.family === "projection") {
        if (Number.isFinite(r.tableTotal) && Math.abs(r.tableTotal - data.pie) > T.reconcileDelta) {
          recon.push({src: r.src, kind: "pie", got: r.tableTotal, want: data.pie});
        }
      } else if (Number.isFinite(r.sharedRescaled) && Math.abs(r.sharedRescaled - r.sharedDdf) > T.reconcileDelta) {
        recon.push({src: r.src, kind: "ddf", got: r.sharedRescaled, want: r.sharedDdf});
      }
    });
    checks.push({
      id: "reconcile", section: "reconcile", name: "Player values vs DDF Value",
      status: recon.length ? "flag" : "pass",
      sources: recon.map(function (c) { return c.src; }), positions: [],
      numbers: {limit: T.reconcileDelta},
      reason: recon.length
        ? (recon[0].kind === "pie"
          ? plainLabel(recon[0].src) + ", all positions: Player values add up to " + fmt(recon[0].got) + ", not the value pie " + fmt(recon[0].want)
          : plainLabel(recon[0].src) + ", all positions: Rescaled adds up to " + fmt(recon[0].got) + " for its listed players, DDF Value " + fmt(recon[0].want)) +
          (recon.length > 1 ? "; " + (recon.length - 1) + " more below" : "") + "."
        : "Projections add up to the value pie, and charts match DDF Value on the players they list."
    });

    data.coverFlags = cover;
    data.reconFlags = recon;
    data.positionInfo = posInfo;
    data.starterInfo = st;
    data.benchInfo = bench;
    return checks;
  }

  // The raw numbers the thresholds are judged against, with no threshold applied.
  // tools/audit_health_thresholds.py reads these across weeks and settings to derive
  // THRESHOLDS from the engine's own output (training weeks) and to validate them
  // on held-out weeks.
  function computeMetrics(data) {
    if (!data || !data.rows.length) return null;
    var rows = data.rows;
    var vals = function (pick) { return rows.map(pick).filter(Number.isFinite); };
    var posStarter = {}, posTotal = {};
    POSITIONS.forEach(function (pos, pi) {
      posStarter[pos] = spread(vals(function (r) { return r.positions[pi].starterAdj; }));
      posTotal[pos] = spread(vals(function (r) { return r.positions[pi].posAdj; }));
    });
    var estShareMax = 0, estCell = null;
    var projDelta = 0, chartDelta = 0;
    rows.forEach(function (r) {
      r.positions.forEach(function (pd) {
        if (pd.estShare != null && pd.estShare > estShareMax) { estShareMax = pd.estShare; estCell = r.src + " " + pd.pos; }
      });
      if (r.family === "projection") {
        if (Number.isFinite(r.tableTotal)) projDelta = Math.max(projDelta, Math.abs(r.tableTotal - data.pie));
      } else if (Number.isFinite(r.sharedRescaled)) {
        chartDelta = Math.max(chartDelta, Math.abs(r.sharedRescaled - r.sharedDdf));
      }
    });
    return {
      starterSpread: spread(vals(function (r) { return r.starterTotal; })),
      benchSpread: spread(vals(function (r) { return r.benchTotal; })),
      posStarterSpread: posStarter,
      posTotalSpreadMax: Math.max.apply(null, POSITIONS.map(function (p) { return posTotal[p]; })),
      pieDeltaMax: Math.max.apply(null, rows.map(function (r) { return Math.abs(r.totalAdjusted - data.pie); })),
      estShareMax: estShareMax, estCell: estCell,
      reconcileProjectionDelta: projDelta, reconcileChartDelta: chartDelta,
      sources: rows.length
    };
  }

  // ── DOM helpers ─────────────────────────────────────────────────────

  var SECTION_ID = {
    starters: "audit-pie-sec-starters", positions: "audit-pie-sec-positions", coverage: "audit-pie-sec-coverage",
    reconcile: "audit-pie-sec-reconcile", raw: "audit-pie-sec-raw", terms: "audit-pie-terms"
  };
  var STATUS_WORD = {pass: "Pass", flag: "Flag", info: "Info"};

  function scrollToSection(id) {
    var target = document.getElementById(id);
    if (!target) return;
    var details = target.closest ? target.closest("details") : null;
    if (details) details.open = true;
    if (target.tagName === "DETAILS") target.open = true;
    target.scrollIntoView({block: "start"});
    var focusable = target.querySelector("h2") || target;
    if (focusable.tabIndex < 0) focusable.tabIndex = -1;
    try { focusable.focus({preventScroll: true}); } catch (e) { /* focus is best effort */ }
  }

  function sectionLink(id, text, cls) {
    var a = el("a", cls || "audit-pie-check-link", text);
    a.setAttribute("href", "#values-auditing/health-check");
    a.setAttribute("data-flag-section", id);
    a.addEventListener("click", function (evt) { evt.preventDefault(); scrollToSection(id); });
    return a;
  }

  function tableWrap(table) {
    var wrap = el("div", "audit-pie-scroll");
    wrap.appendChild(table);
    return wrap;
  }

  function makeTable(label, headers) {
    var table = el("table", "audit-pie-table");
    table.setAttribute("aria-label", label);   // JEG-904
    var caption = el("caption", "audit-pie-caption", label);
    table.appendChild(caption);
    var thead = el("thead");
    var hr = el("tr");
    headers.forEach(function (h) { hr.appendChild(th(h, h === headers[0] ? "" : "audit-pie-num")); });
    thead.appendChild(hr);
    table.appendChild(thead);
    return table;
  }

  function section(id, question, lede) {
    var sec = el("section", "audit-pie-section");
    sec.id = id;
    sec.setAttribute("aria-labelledby", id + "-q");
    var h = el("h2", "audit-pie-heading", question);
    h.id = id + "-q";
    sec.appendChild(h);
    if (lede) sec.appendChild(el("p", "audit-pie-note audit-pie-how", lede));
    return sec;
  }

  function markCell(cell, why) {
    cell.classList.add("audit-pie-flag");
    cell.setAttribute("data-flag", "");
    if (why) cell.title = why;
    return cell;
  }

  function checkById(checks, id) {
    return checks.filter(function (c) { return c.id === id; })[0];
  }

  // ── DOM: verdict strip ──────────────────────────────────────────────

  function buildVerdictStrip(checks, data) {
    var wrap = el("section", "audit-pie-verdict");
    wrap.id = "audit-pie-verdict";
    wrap.setAttribute("aria-labelledby", "audit-pie-verdict-q");
    var q = el("h2", "audit-pie-heading audit-pie-verdict-q", "Is anything wrong?");
    q.id = "audit-pie-verdict-q";
    wrap.appendChild(q);
    wrap.appendChild(document.createTextNode(" "));

    var graded = checks.filter(function (c) { return c.status !== "info"; });
    var flags = graded.filter(function (c) { return c.status === "flag"; });
    var head = el("p", "audit-pie-headline " + (flags.length ? "audit-pie-headline-flag" : "audit-pie-headline-pass"),
      flags.length
        ? flags.length + " of " + graded.length + " checks need a look."
        : "Nothing is wrong: all " + graded.length + " checks pass.");
    head.setAttribute("aria-live", "polite");
    head.setAttribute("data-flag-count", String(flags.length));
    wrap.appendChild(head);

    var list = el("ul", "audit-pie-checks");
    list.setAttribute("aria-label", "Health checks, one row each");
    checks.forEach(function (c) {
      var li = el("li", "audit-pie-check audit-pie-check-" + c.status);
      li.setAttribute("data-check", c.id);
      li.setAttribute("data-status", c.status);
      li.setAttribute("aria-live", "polite");
      // The whole row is the link to its drill-down: a 44 px tap target that never overlaps its neighbours.
      var a = sectionLink(SECTION_ID[c.section], "", "audit-pie-check-row");
      a.appendChild(el("span", "audit-pie-badge audit-pie-badge-" + c.status, STATUS_WORD[c.status]));
      a.appendChild(el("span", "audit-pie-check-name", c.name));
      a.appendChild(el("span", "audit-pie-check-reason", c.reason));
      li.appendChild(a);
      list.appendChild(li);
    });
    wrap.appendChild(list);

    return wrap;
  }

  // ── DOM: section 1, do sources agree on total value ─────────────────

  function buildStartersSection(data, checks) {
    var stCheck = checkById(checks, "starters");
    var sec = section(SECTION_ID.starters, "Do sources agree on total value?",
      "Each row is a source. Starter and bench totals should be similar across sources. The total is always the value pie (" +
      fmt(data.pie) + "), by construction. An amber starter total is the source furthest from the middle when the spread is over " +
      pctWhole(THRESHOLDS.starterSpread) + ".");
    var table = makeTable("Starter, bench and total value by source", ["Source", "Starters", "Bench", "Total", "Per roster slot"]);
    var tbody = el("tbody");
    data.rows.forEach(function (r) {
      var tr = el("tr");
      tr.appendChild(rowHead(sourceLabel(r.src)));
      var starter = td(fmt(r.starterTotal), "audit-pie-num");
      if (stCheck.status === "flag" && stCheck.sources.indexOf(r.src) >= 0) {
        markCell(starter, "Furthest from the middle source: spread " + fmtSpreadPct(stCheck.numbers.spread) + ", limit " + pctWhole(THRESHOLDS.starterSpread));
      }
      tr.appendChild(starter);
      tr.appendChild(td(fmt(r.benchTotal), "audit-pie-num"));
      var total = td(fmt(r.totalAdjusted), "audit-pie-num");
      if (Math.abs(r.totalAdjusted - data.pie) > THRESHOLDS.pieDelta) markCell(total, "Not the value pie (" + fmt(data.pie) + ")");
      tr.appendChild(total);
      var slot = td(fmt(r.perRosterable, 2), "audit-pie-num");
      if (r.flagPerRosterable) {
        markCell(slot, "More than " + pctWhole(FLAG_THRESHOLD) + " from the middle source (" + fmt(r.medPerRosterable, 2) + ")");
      }
      tr.appendChild(slot);
      tbody.appendChild(tr);
    });
    table.appendChild(tbody);
    sec.appendChild(tableWrap(table));
    var summary = el("p", "audit-pie-note audit-pie-summary-line",
      "Starter spread " + fmtSpreadPct(data.starterInfo.spread) + " (limit " + pctWhole(THRESHOLDS.starterSpread) + "). Bench spread " +
      fmtSpreadPct(data.benchInfo.spread) + " (informational, never flagged).");
    sec.appendChild(summary);
    if (data.benchInfo.spread > BENCH_NOTE_MIN) {
      var note = el("p", "audit-pie-bench-note",
        "Sources price bench players differently. Trade charts list fewer players near the waiver line, so their bench values are " +
        "smaller after rescaling. This is expected and does not affect trade values.");
      note.setAttribute("data-bench-note", "");
      sec.appendChild(note);
    }
    return sec;
  }

  // ── DOM: section 2, do sources agree by position ────────────────────

  function buildPositionSection(data, checks) {
    var sec = section(SECTION_ID.positions, "Do sources agree by position?",
      "Within each position, starter values should agree within " + pctWhole(THRESHOLDS.positionStarterSpread) +
      ". Position totals are equal across sources by construction. QB is shown for reference and never flagged.");
    var posCheck = checkById(checks, "positions");
    POSITIONS.forEach(function (pos, pi) {
      var info = data.positionInfo[pos];
      var isQb = pos === "QB";
      var isFlag = !isQb && posCheck.positions.indexOf(pos) >= 0;
      var block = el("div", "audit-pie-pos-block");
      block.setAttribute("data-position", pos);
      var head = el("h3", "audit-pie-pos-heading", pos + " ");
      var tag = el("span", isFlag ? "audit-pie-pos-flag" : "audit-pie-pos-ok",
        "starter spread " + fmtSpreadPct(info.spread) + (isQb ? " (reference only)" : isFlag ? " (flagged)" : " (within range)"));
      head.appendChild(tag);
      block.appendChild(head);

      var table = makeTable("Starter, bench and total value by source, " + pos,
        ["Source", "Starters", "Bench", "Total", "Budget", "Per roster slot"]);
      var tbody = el("tbody");
      data.rows.forEach(function (r) {
        var pd = r.positions[pi];
        var tr = el("tr");
        tr.appendChild(rowHead(sourceLabel(r.src)));
        var starter = td(fmt(pd.starterAdj), "audit-pie-num");
        if (isFlag && info.outlier && info.outlier.src === r.src) {
          markCell(starter, "Furthest from the middle source: spread " + fmtSpreadPct(info.spread) + ", limit " + pctWhole(THRESHOLDS.positionStarterSpread));
        }
        tr.appendChild(starter);
        tr.appendChild(td(fmt(pd.benchAdj), "audit-pie-num"));
        tr.appendChild(td(fmt(pd.posAdj), "audit-pie-num"));
        tr.appendChild(td(fmt(pd.budget), "audit-pie-num"));
        var slot = td(fmt(pd.perRosterable, 2), "audit-pie-num");
        if (pd.flagPerRosterable) markCell(slot, "More than " + pctWhole(FLAG_THRESHOLD) + " from the middle source (" + fmt(pd.medPerRosterable, 2) + ")");
        tr.appendChild(slot);
        tbody.appendChild(tr);
      });
      table.appendChild(tbody);
      block.appendChild(tableWrap(table));
      sec.appendChild(block);
    });
    return sec;
  }

  // ── DOM: section 3, are any players valued oddly ────────────────────

  function buildCoverageSection(data) {
    var sec = section(SECTION_ID.coverage, "Are any players valued oddly?",
      "A filled-in player is one the source did not list, so the engine gave it a fill-in value from the other charts. " +
      "A high count means the source listed few players there. Each cell is filled-in players out of the rostered slots at that position; " +
      "amber is over " + pctWhole(THRESHOLDS.estimatedShare) + ".");
    var table = makeTable("Filled-in players out of rostered slots, by source and position",
      ["Source", "QB", "RB", "WR", "TE", "All positions"]);
    var tbody = el("tbody");
    data.rows.forEach(function (r) {
      var tr = el("tr");
      tr.appendChild(rowHead(sourceLabel(r.src)));
      r.positions.forEach(function (pd) {
        var share = pd.estShare;
        var cell = td(pd.nEstimated + " of " + pd.rostered + (pd.nEstimated ? " (" + pctWhole(share || 0) + ")" : ""), "audit-pie-num");
        if (share != null && share > THRESHOLDS.estimatedShare) markCell(cell, "More than " + pctWhole(THRESHOLDS.estimatedShare) + " of the rostered slots are filled in");
        tr.appendChild(cell);
      });
      tr.appendChild(td(r.totalEstimated + " of " + r.totalRostered + (r.totalEstimated ? " (" + pctWhole(r.estShare || 0) + ")" : ""), "audit-pie-num"));
      tbody.appendChild(tr);
    });
    table.appendChild(tbody);
    sec.appendChild(tableWrap(table));
    return sec;
  }

  // ── DOM: section 4, does DDF Value reconcile ────────────────────────

  function buildReconcileSection(data) {
    var sec = section(SECTION_ID.reconcile, "Does DDF Value reconcile?",
      "Total adjusted is the source's own posted values plus its fill-in values, and always equals the value pie (" + fmt(data.pie) +
      "). Projections show the same numbers in Player values, so the Player values sum should equal the pie. A trade chart shows " +
      "Rescaled values there instead: its native values times one factor, set so the players it lists add up to their DDF Value. " +
      "So for a chart the Player values sum may differ from the pie (fill-ins and unlisted players change it), and the check is that the " +
      "Rescaled values for the players it lists match their DDF Value.");
    var table = makeTable("Reconciling each source to Player values",
      ["Source", "Own values", "Filled in", "Total adjusted", "Player values sum", "Difference from pie", "Listed players: Rescaled minus DDF Value"]);
    var tbody = el("tbody");
    data.rows.forEach(function (r) {
      var tr = el("tr");
      tr.appendChild(rowHead(sourceLabel(r.src)));
      tr.appendChild(td(fmt(r.ownAdjusted), "audit-pie-num"));
      tr.appendChild(td(fmt(r.filledAdjusted), "audit-pie-num"));
      tr.appendChild(td(fmt(r.totalAdjusted), "audit-pie-num"));
      tr.appendChild(td(fmt(r.tableTotal), "audit-pie-num audit-pie-table-total"));
      var diff = Number.isFinite(r.tableTotal) ? r.tableTotal - data.pie : null;
      if (diff != null && Math.abs(diff) < 0.05) diff = 0;   // no "-0.0"
      var isProjection = r.family === "projection";
      var diffCell = td(fmt(diff), "audit-pie-num");
      if (isProjection && diff != null && Math.abs(diff) > THRESHOLDS.reconcileDelta) markCell(diffCell, "A projection's Player values should add up to the value pie");
      tr.appendChild(diffCell);
      var listed = !isProjection && Number.isFinite(r.sharedRescaled) ? r.sharedRescaled - r.sharedDdf : null;
      if (listed != null && Math.abs(listed) < 0.05) listed = 0;
      var listedCell = td(isProjection ? "n/a" : fmt(listed), "audit-pie-num");
      if (listed != null && Math.abs(listed) > THRESHOLDS.reconcileDelta) markCell(listedCell, "Rescaled values for the listed players should add up to their DDF Value");
      tr.appendChild(listedCell);
      tbody.appendChild(tr);
    });
    table.appendChild(tbody);
    sec.appendChild(tableWrap(table));
    return sec;
  }

  // ── DOM: section 5, raw vs adjusted (collapsed) ─────────────────────

  function buildRawSection(data) {
    var details = el("details", "audit-pie-section audit-pie-raw");
    details.id = SECTION_ID.raw;
    var summary = el("summary", "audit-pie-raw-summary");
    var h = el("h2", "audit-pie-heading", "How do raw and adjusted values compare?");
    h.id = SECTION_ID.raw + "-q";
    summary.appendChild(h);
    details.appendChild(summary);
    details.appendChild(el("p", "audit-pie-note audit-pie-how",
      "Raw values are each source's group totals before rescaling. Adjusted values are after rescaling to the value pie. " +
      "A large shift means the source's value shape disagrees with the league's budget for that position. Shifts over " +
      pctWhole(RAW_SHIFT_NOTE) + " are amber."));
    POSITIONS.forEach(function (pos, pi) {
      var block = el("div", "audit-pie-pos-block");
      block.appendChild(el("h3", "audit-pie-pos-heading", pos));
      var table = makeTable("Raw and adjusted value by source, " + pos,
        ["Source", "Raw starters", "Raw bench", "Raw total", "Adjusted starters", "Adjusted bench", "Adjusted total", "Shift from raw"]);
      var tbody = el("tbody");
      data.rows.forEach(function (r) {
        var pd = r.positions[pi];
        var tr = el("tr");
        tr.appendChild(rowHead(sourceLabel(r.src)));
        tr.appendChild(td(fmt(pd.starterRaw), "audit-pie-num"));
        tr.appendChild(td(fmt(pd.benchRaw), "audit-pie-num"));
        tr.appendChild(td(fmt(pd.posRaw), "audit-pie-num"));
        tr.appendChild(td(fmt(pd.starterAdj), "audit-pie-num"));
        tr.appendChild(td(fmt(pd.benchAdj), "audit-pie-num"));
        tr.appendChild(td(fmt(pd.posAdj), "audit-pie-num"));
        var shift = pd.posRaw > 0 ? (pd.posAdj - pd.posRaw) / pd.posRaw : null;
        var shiftCell = td(fmtPct(shift), "audit-pie-num");
        if (shift != null && Math.abs(shift) > RAW_SHIFT_NOTE) markCell(shiftCell, "Large shift from the raw total (over " + pctWhole(RAW_SHIFT_NOTE) + ")");
        tr.appendChild(shiftCell);
        tbody.appendChild(tr);
      });
      table.appendChild(tbody);
      block.appendChild(tableWrap(table));
      details.appendChild(block);
    });
    return details;
  }

  // ── DOM: terms ──────────────────────────────────────────────────────

  var TERMS = [
    ["Adjusted", "A source's values after rescaling so its total equals the value pie. Every source's adjusted total is the same."],
    ["Rescaled", "A trade chart's native values times one factor, set so the players it lists add up to their DDF Value. This is what Player values shows for trade charts. It is not the same as Adjusted."],
    ["DDF Value", "Our value: the equal-weight mean of the trade charts' Adjusted values (FantasyCalc, USA Today, FantasyPros, CBS). The projection sources are the alternate, DDF Value (projections)."],
    ["Filled-in", "A player the source did not list, given a fill-in value from the other charts so the math has a complete roster. Marked Estimated on the Single source tab."],
    ["Value pie", "The total value available in your league. Every source's Adjusted values add up to it. It depends on league size and roster, not on scoring."],
    ["Starter, bench, waiver", "A player's role: starter if he would start, bench if rostered but not starting, waiver if not rostered. Depends on your league settings."],
    ["Spread", "The highest source minus the lowest, as a share of the middle source. It measures how much the sources disagree."],
    ["Value above waivers", "A player's value above the best replacement available on waivers."],
    ["Fill-in value", "The value given to a filled-in player, derived from the other sources that do list him."]
  ];

  function buildTerms() {
    var details = el("details", "audit-pie-section audit-pie-terms");
    details.id = SECTION_ID.terms;
    var summary = el("summary", "audit-pie-raw-summary");
    summary.appendChild(el("h2", "audit-pie-heading", "Terms used on this page"));
    details.appendChild(summary);
    var dl = el("dl", "audit-pie-dl");
    TERMS.forEach(function (t) {
      dl.appendChild(el("dt", "", t[0]));
      dl.appendChild(el("dd", "", t[1]));
    });
    details.appendChild(dl);
    return details;
  }

  // ── Setting line ────────────────────────────────────────────────────

  function settingText(setting) {
    if (!setting) return "";
    var r = setting.roster || {};
    var scoring = String(setting.scoring || "");
    var scoringName = scoring === "ppr" ? "PPR" : scoring === "half_ppr" ? "half PPR" : scoring === "standard" ? "standard scoring" : scoring;
    var parts = [setting.teams + " teams", scoringName];
    var slots = POSITIONS.map(function (p) { return (r[p] || 0) + " " + p; });
    if (r.FLEX) slots.push(r.FLEX + " flex");
    if (r.SUPERFLEX) slots.push(r.SUPERFLEX + " superflex");
    if (r.BENCH !== undefined) slots.push(r.BENCH + " bench");
    return parts.join(", ") + "; " + slots.join(", ");
  }

  // ── Main render ─────────────────────────────────────────────────────

  var mounted = null;   // {host, ctx} of the last render, so a settings change redraws the visible tab

  function render(rootEl, ctx) {
    mounted = {host: rootEl, ctx: ctx};
    rootEl.innerHTML = "";

    // ctx = {slug, engine} where engine = TradeValueCurveControls.
    // Also accept {controls} for the standalone test harness.
    var engine = (ctx && ctx.engine) || (ctx && ctx.controls) || null;
    if (!engine || typeof engine.getInspection !== "function") {
      rootEl.appendChild(el("p", "audit-pie-empty", "Engine not ready."));
      return;
    }

    var inspection = engine.getInspection();
    var data = extract(inspection);
    if (!data) {
      rootEl.appendChild(el("p", "audit-pie-empty", "No pipeline data available."));
      return;
    }

    computeFlags(data);
    var checks = computeChecks(data);
    data.checks = checks;

    var header = el("div", "audit-pie-header");
    var setting = settingText(data.setting);
    header.appendChild(el("p", "audit-pie-meta",
      "Value pie: " + fmt(data.pie, 1) + " points · " + data.rows.length + " sources" + (setting ? " · " + setting : "") + " · "));
    header.firstChild.appendChild(sectionLink(SECTION_ID.terms, "Terms used on this page", "audit-pie-check-link"));

    rootEl.appendChild(buildVerdictStrip(checks, data));
    rootEl.appendChild(header);
    rootEl.appendChild(buildStartersSection(data, checks));
    rootEl.appendChild(buildPositionSection(data, checks));
    rootEl.appendChild(buildCoverageSection(data));
    rootEl.appendChild(buildReconcileSection(data));
    rootEl.appendChild(buildRawSection(data));
    rootEl.appendChild(buildTerms());
  }

  // ── Registration ────────────────────────────────────────────────────

  root.AuditPie = {
    extract: extract,
    computeFlags: computeFlags,
    computeVerdicts: computeVerdicts,
    computeChecks: computeChecks,
    computeMetrics: computeMetrics,
    render: render,
    _fmt: fmt,
    _fmtPct: fmtPct,
    _FLAG_THRESHOLD: FLAG_THRESHOLD,
    _THRESHOLDS: THRESHOLDS,
    _POSITIONS: POSITIONS,
    _TERMS: TERMS
  };

  // Live league settings (JEG-1011): the checks follow the engine's current setting. v2.js redraws the
  // visible audit tab on a shared-state change; this covers a rows change that arrives on its own.
  if (typeof root.addEventListener === "function") {
    root.addEventListener("trade-value-rows-change", function () {
      if (mounted && mounted.host.isConnected && mounted.host.offsetParent !== null) render(mounted.host, mounted.ctx);
    });
  }

  if (root.DDFAudit && typeof root.DDFAudit.register === "function") {
    root.DDFAudit.register("health-check", render);
  }

})(window);
