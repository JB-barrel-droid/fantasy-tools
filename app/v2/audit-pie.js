// Value pie tab (JEG-848): cross-source comparison of Adjusted value
// distribution by position and role (starter/bench).
//
// Pure read of the engine's runValuePipeline result via getInspection().
// No value math: every number shown is derived from the engine's own fields
// (adjusted, groups, positions, budgets, pie). A flag marks any source whose
// per-rosterable-slot value at a position deviates >10% from the cross-source
// median.
//
// Raw (pre-rescale) values come from groups[pos|role] on the pipeline
// diagnostics (value-model.js:841-842, the sum of starterSlice / benchSlice
// before the rate multiplier). Adjusted = rate * slice (value-model.js:993).
// These differ whenever rate != 1.0 (i.e. when the source's raw shape
// disagrees with the budget allocation).
//
// Contract: window.DDFAudit.register("value-pie", render) where render(root, ctx)
// receives the mount element (#audit-pie-root) and ctx = {slug, engine} where
// engine = TradeValueCurveControls. Called by renderAudit() on tab show, setting
// change, and source-availability change. Must be idempotent (rebuilds mount
// each call). Guards for window.TradeValueV2 being undefined on first call.
(function (root) {
  "use strict";

  var POSITIONS = ["QB", "RB", "WR", "TE"];
  var ROLES = ["starter", "bench"];
  var FLAG_THRESHOLD = 0.10; // 10% from median

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

  function fmt(v, decimals) {
    if (v == null || !Number.isFinite(v)) return "—";
    return v.toFixed(decimals == null ? 1 : decimals);
  }

  function fmtPct(v) {
    if (v == null || !Number.isFinite(v)) return "—";
    return (v >= 0 ? "+" : "") + (v * 100).toFixed(1) + "%";
  }

  function fmtSpreadPct(v) {
    if (v == null || !Number.isFinite(v)) return "—";
    return (v * 100).toFixed(1) + "%";
  }

  function el(tag, cls, text) {
    var node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text != null) node.textContent = String(text);
    return node;
  }

  function th(text, cls) { return el("th", cls || "", text); }
  function td(text, cls) { return el("td", cls || "", text); }

  // ── Data extraction ─────────────────────────────────────────────────
  // Fields used (all from getInspection().valuePipeline and .players):
  //   groups[pos|role]         -- pre-rescale group totals (value-model.js:841-842)
  //   players[key].adjusted   -- rescaled value (value-model.js:993)
  //   players[key].pos, .role -- position and starter/bench/waiver
  //   positions[pos].listed, .starters, .rostered, .nEstimated
  //   budgets[pos|role]       -- the pie budget per group
  //   pie                     -- the league pie

  function extract(inspection) {
    if (!inspection || !inspection.valuePipeline) return null;
    var vp = inspection.valuePipeline;
    var pie = vp.pie;
    var sources = vp.sources;
    var ddfWeights = vp.ddfWeights || {};
    // budgets = funded[g] = ddfWeights[g] * pie (value-model.js:979-980).
    // The pipeline exposes ddfWeights but not the funded object directly.
    var budgets = vp.budgets || {};
    if (!Object.keys(budgets).length && Object.keys(ddfWeights).length) {
      Object.keys(ddfWeights).forEach(function (g) {
        budgets[g] = ddfWeights[g] * pie;
      });
    }
    var allocation = vp.allocation || {};
    var players = inspection.players || {};
    var sourceKeys = Object.keys(sources);
    if (!sourceKeys.length) return null;

    var rows = [];
    sourceKeys.forEach(function (src) {
      var s = sources[src];
      var ps = players[src] || {};
      var groups = s.groups || {};

      // Per-position breakdown
      var posData = [];
      var totalListed = 0, totalRostered = 0, totalEstimated = 0;
      var totalAdjusted = 0, totalRawSlice = 0;
      var starterTotal = 0, benchTotal = 0;
      var starterRawTotal = 0, benchRawTotal = 0;

      POSITIONS.forEach(function (pos) {
        var posInfo = s.positions[pos] || {};
        var listed = posInfo.listed || 0;
        var starters = posInfo.starters || 0;
        var rostered = posInfo.rostered || 0;
        var nEstimated = posInfo.nEstimated || 0;
        var benchCount = rostered - starters;

        // Raw (pre-rescale): from groups on the pipeline diagnostics
        // groups[pos|starter] = sum of starterSlice for pos starters (value-model.js:841)
        // groups[pos|bench]   = sum of benchSlice for pos bench (value-model.js:842)
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
        totalAdjusted: totalAdjusted,
        totalRawSlice: totalRawSlice,
        starterTotal: starterTotal,
        benchTotal: benchTotal,
        starterRawTotal: starterRawTotal,
        benchRawTotal: benchRawTotal,
        perListed: totalListed > 0 ? totalAdjusted / totalListed : null,
        perRosterable: totalRostered > 0 ? totalAdjusted / totalRostered : null
      });
    });

    return {pie: pie, budgets: budgets, ddfWeights: ddfWeights, allocation: allocation, rows: rows};
  }

  // ── Flag computation (>10% from median) ─────────────────────────────

  function computeFlags(data) {
    if (!data || !data.rows.length) return;

    // Total-level medians
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

    // Per-position medians
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

  // ── Verdicts: cross-source spread per cut ───────────────────────────

  function computeVerdicts(data) {
    if (!data || !data.rows.length) return {};

    var verdicts = {};

    // Total-level verdicts: starters, bench, total
    var starterVals = data.rows.map(function (r) { return r.starterTotal; }).filter(Number.isFinite);
    var benchVals = data.rows.map(function (r) { return r.benchTotal; }).filter(Number.isFinite);
    var totalVals = data.rows.map(function (r) { return r.totalAdjusted; }).filter(Number.isFinite);

    verdicts.starters = {spread: spread(starterVals), within: spread(starterVals) <= FLAG_THRESHOLD};
    verdicts.bench = {spread: spread(benchVals), within: spread(benchVals) <= FLAG_THRESHOLD};
    verdicts.total = {spread: spread(totalVals), within: spread(totalVals) <= FLAG_THRESHOLD};

    // Per-position verdicts
    verdicts.positions = {};
    POSITIONS.forEach(function (pos, pi) {
      var posStarters = data.rows.map(function (r) { return r.positions[pi].starterAdj; }).filter(Number.isFinite);
      var posBench = data.rows.map(function (r) { return r.positions[pi].benchAdj; }).filter(Number.isFinite);
      var posTotal = data.rows.map(function (r) { return r.positions[pi].posAdj; }).filter(Number.isFinite);

      verdicts.positions[pos] = {
        starters: {spread: spread(posStarters), within: spread(posStarters) <= FLAG_THRESHOLD},
        bench: {spread: spread(posBench), within: spread(posBench) <= FLAG_THRESHOLD},
        total: {spread: spread(posTotal), within: spread(posTotal) <= FLAG_THRESHOLD}
      };
    });

    return verdicts;
  }

  // ── Label helpers ───────────────────────────────────────────────────

  var SOURCE_LABELS = {
    espn: "ESPN", cbsros: "CBS ROS", razzball: "Razzball",
    fantasycalc: "FantasyCalc", usatoday: "USA Today",
    fantasypros: "FantasyPros", cbs: "CBS"
  };
  var FAMILY_LABELS = {projection: "Projection", chart: "Trade chart"};

  function sourceLabel(src) {
    var v2 = root.TradeValueV2;
    if (v2 && typeof v2.shown === "function") {
      try {
        var info = root.TradeValueCurveControls && root.TradeValueCurveControls.getSourceInfo
          ? root.TradeValueCurveControls.getSourceInfo() : [];
        var match = info.find(function (s) { return s.key === src; });
        if (match && match.label) return match.label;
      } catch (e) { /* ignore */ }
    }
    return SOURCE_LABELS[src] || src;
  }

  // ── DOM: verdict row ────────────────────────────────────────────────

  function verdictText(v) {
    return "spread " + fmtSpreadPct(v.spread) + ", within " + (FLAG_THRESHOLD * 100) + "%: " + (v.within ? "yes" : "no");
  }

  function buildVerdictRow(label, v, colspan) {
    var tr = el("tr", "audit-pie-verdict-row");
    var cell = td(label + ": " + verdictText(v), v.within ? "audit-pie-verdict-pass" : "audit-pie-verdict-fail");
    cell.colSpan = colspan;
    tr.appendChild(cell);
    return tr;
  }

  // ── DOM: summary table ──────────────────────────────────────────────

  function buildSummaryTable(data, verdicts) {
    var section = el("div", "audit-pie-section");
    var heading = el("h3", "audit-pie-heading", "Total pie by source");
    section.appendChild(heading);

    var table = el("table", "audit-pie-table audit-pie-summary");
    var thead = el("thead");
    var hr = el("tr");
    ["Source", "Family", "Players posted", "Rosterable", "Estimated",
     "Starter total", "Bench total", "Total adjusted",
     "Pie target", "Delta",
     "Per player posted", "Per rosterable slot"].forEach(function (label) {
      hr.appendChild(th(label));
    });
    thead.appendChild(hr);
    table.appendChild(thead);

    var tbody = el("tbody");
    data.rows.forEach(function (r) {
      var tr = el("tr");
      tr.appendChild(td(sourceLabel(r.src)));
      tr.appendChild(td(FAMILY_LABELS[r.family] || r.family));
      tr.appendChild(td(r.totalListed, "audit-pie-num"));
      tr.appendChild(td(r.totalRostered, "audit-pie-num"));
      tr.appendChild(td(r.totalEstimated, "audit-pie-num"));
      tr.appendChild(td(fmt(r.starterTotal), "audit-pie-num"));
      tr.appendChild(td(fmt(r.benchTotal), "audit-pie-num"));
      tr.appendChild(td(fmt(r.totalAdjusted), "audit-pie-num"));
      tr.appendChild(td(fmt(data.pie), "audit-pie-num"));
      tr.appendChild(td(fmt(r.totalAdjusted - data.pie, 2), "audit-pie-num"));

      var pplCell = td(fmt(r.perListed, 2), "audit-pie-num");
      if (r.flagPerListed) {
        pplCell.classList.add("audit-pie-flag");
        pplCell.title = ">" + (FLAG_THRESHOLD * 100) + "% from median (" + fmt(r.medPerListed, 2) + ")";
      }
      tr.appendChild(pplCell);

      var prCell = td(fmt(r.perRosterable, 2), "audit-pie-num");
      if (r.flagPerRosterable) {
        prCell.classList.add("audit-pie-flag");
        prCell.title = ">" + (FLAG_THRESHOLD * 100) + "% from median (" + fmt(r.medPerRosterable, 2) + ")";
      }
      tr.appendChild(prCell);

      tbody.appendChild(tr);
    });

    // Verdict rows
    tbody.appendChild(buildVerdictRow("Starters", verdicts.starters, 12));
    tbody.appendChild(buildVerdictRow("Bench", verdicts.bench, 12));
    tbody.appendChild(buildVerdictRow("Total", verdicts.total, 12));

    table.appendChild(tbody);

    var wrap = el("div", "audit-pie-scroll");
    wrap.appendChild(table);
    section.appendChild(wrap);
    return section;
  }

  // ── DOM: position breakdown table ───────────────────────────────────

  function buildPositionTable(data, verdicts) {
    var section = el("div", "audit-pie-section");
    var heading = el("h3", "audit-pie-heading", "By position: adjusted values");
    section.appendChild(heading);

    var note = el("p", "audit-pie-note",
      "Adjusted values sum to the league pie for every source (by construction). " +
      "Differences in per-player and per-slot values reveal where sources disagree on position weight.");
    section.appendChild(note);

    POSITIONS.forEach(function (pos, pi) {
      var sub = el("div", "audit-pie-pos-block");
      var posHead = el("h4", "audit-pie-pos-heading", pos);
      sub.appendChild(posHead);

      var table = el("table", "audit-pie-table audit-pie-pos");
      var thead = el("thead");
      var hr = el("tr");
      ["Source", "Listed", "Starters", "Bench", "Rosterable", "Estimated",
       "Starter adj.", "Bench adj.", "Position adj.", "Budget", "Delta",
       "Per rosterable"].forEach(function (label) {
        hr.appendChild(th(label));
      });
      thead.appendChild(hr);
      table.appendChild(thead);

      var tbody = el("tbody");
      data.rows.forEach(function (r) {
        var pd = r.positions[pi];
        var tr = el("tr");
        tr.appendChild(td(sourceLabel(r.src)));
        tr.appendChild(td(pd.listed, "audit-pie-num"));
        tr.appendChild(td(pd.starters, "audit-pie-num"));
        tr.appendChild(td(pd.bench, "audit-pie-num"));
        tr.appendChild(td(pd.rostered, "audit-pie-num"));
        tr.appendChild(td(pd.nEstimated, "audit-pie-num"));
        tr.appendChild(td(fmt(pd.starterAdj), "audit-pie-num"));
        tr.appendChild(td(fmt(pd.benchAdj), "audit-pie-num"));
        tr.appendChild(td(fmt(pd.posAdj), "audit-pie-num"));
        tr.appendChild(td(fmt(pd.budget), "audit-pie-num"));
        tr.appendChild(td(fmt(pd.posAdj - pd.budget, 2), "audit-pie-num"));

        var prCell = td(fmt(pd.perRosterable, 2), "audit-pie-num");
        if (pd.flagPerRosterable) {
          prCell.classList.add("audit-pie-flag");
          prCell.title = ">" + (FLAG_THRESHOLD * 100) + "% from median (" + fmt(pd.medPerRosterable, 2) + ")";
        }
        tr.appendChild(prCell);

        tbody.appendChild(tr);
      });

      // Position verdicts
      var pv = verdicts.positions[pos];
      if (pv) {
        tbody.appendChild(buildVerdictRow("Starters", pv.starters, 12));
        tbody.appendChild(buildVerdictRow("Bench", pv.bench, 12));
        tbody.appendChild(buildVerdictRow("Total", pv.total, 12));
      }

      table.appendChild(tbody);

      var wrap = el("div", "audit-pie-scroll");
      wrap.appendChild(table);
      sub.appendChild(wrap);
      section.appendChild(sub);
    });

    return section;
  }

  // ── DOM: raw (pre-rescale) slices alongside adjusted ────────────────

  function buildRawVsAdjustedTable(data) {
    var section = el("div", "audit-pie-section");
    var heading = el("h3", "audit-pie-heading", "Raw slices vs adjusted values");
    section.appendChild(heading);

    var note = el("p", "audit-pie-note",
      "Raw slices are the pre-rescale group totals from the pipeline " +
      "(groups[pos|role], value-model.js:841–842: sum of starterSlice / benchSlice " +
      "before rate multiplication). Adjusted = rate × slice (value-model.js:993). " +
      "They differ when rate ≠ 1, i.e. when the source's raw shape disagrees " +
      "with the budget allocation.");
    section.appendChild(note);

    POSITIONS.forEach(function (pos, pi) {
      var sub = el("div", "audit-pie-pos-block");
      var posHead = el("h4", "audit-pie-pos-heading", pos);
      sub.appendChild(posHead);

      var table = el("table", "audit-pie-table audit-pie-raw");
      var thead = el("thead");
      var hr = el("tr");
      ["Source", "Raw starter", "Raw bench", "Raw total",
       "Adj. starter", "Adj. bench", "Adj. total",
       "Rescale shift"].forEach(function (label) {
        hr.appendChild(th(label));
      });
      thead.appendChild(hr);
      table.appendChild(thead);

      var tbody = el("tbody");
      data.rows.forEach(function (r) {
        var pd = r.positions[pi];
        var tr = el("tr");
        tr.appendChild(td(sourceLabel(r.src)));
        tr.appendChild(td(fmt(pd.starterRaw), "audit-pie-num"));
        tr.appendChild(td(fmt(pd.benchRaw), "audit-pie-num"));
        tr.appendChild(td(fmt(pd.posRaw), "audit-pie-num"));
        tr.appendChild(td(fmt(pd.starterAdj), "audit-pie-num"));
        tr.appendChild(td(fmt(pd.benchAdj), "audit-pie-num"));
        tr.appendChild(td(fmt(pd.posAdj), "audit-pie-num"));

        var shift = pd.posRaw > 0 ? (pd.posAdj - pd.posRaw) / pd.posRaw : null;
        var shiftCell = td(fmtPct(shift), "audit-pie-num");
        if (shift != null && Math.abs(shift) > 0.15) {
          shiftCell.classList.add("audit-pie-flag");
          shiftCell.title = "Large rescale shift (>15%)";
        }
        tr.appendChild(shiftCell);

        tbody.appendChild(tr);
      });
      table.appendChild(tbody);

      var wrap = el("div", "audit-pie-scroll");
      wrap.appendChild(table);
      sub.appendChild(wrap);
      section.appendChild(sub);
    });

    return section;
  }

  // ── DOM: coverage table ─────────────────────────────────────────────

  function buildCoverageTable(data) {
    var section = el("div", "audit-pie-section");
    var heading = el("h3", "audit-pie-heading", "Coverage: players posted vs rosterable slots");
    section.appendChild(heading);

    var note = el("p", "audit-pie-note",
      "Sources that post fewer players spread the same pie across fewer values. " +
      "The per-player-posted and per-rosterable-slot columns show this difference. " +
      "Flagged values differ from the cross-source median by more than " +
      (FLAG_THRESHOLD * 100) + "%.");
    section.appendChild(note);

    POSITIONS.forEach(function (pos, pi) {
      var sub = el("div", "audit-pie-pos-block");
      var posHead = el("h4", "audit-pie-pos-heading", pos);
      sub.appendChild(posHead);

      var table = el("table", "audit-pie-table audit-pie-coverage");
      var thead = el("thead");
      var hr = el("tr");
      ["Source", "Listed", "Rosterable", "Estimated",
       "Per listed", "Per rosterable"].forEach(function (label) {
        hr.appendChild(th(label));
      });
      thead.appendChild(hr);
      table.appendChild(thead);

      var tbody = el("tbody");
      data.rows.forEach(function (r) {
        var pd = r.positions[pi];
        var tr = el("tr");
        tr.appendChild(td(sourceLabel(r.src)));
        tr.appendChild(td(pd.listed, "audit-pie-num"));
        tr.appendChild(td(pd.rostered, "audit-pie-num"));
        tr.appendChild(td(pd.nEstimated, "audit-pie-num"));

        var plCell = td(fmt(pd.perListed, 2), "audit-pie-num");
        if (pd.flagPerListed) {
          plCell.classList.add("audit-pie-flag");
          plCell.title = ">" + (FLAG_THRESHOLD * 100) + "% from median (" + fmt(pd.medPerListed, 2) + ")";
        }
        tr.appendChild(plCell);

        var prCell = td(fmt(pd.perRosterable, 2), "audit-pie-num");
        if (pd.flagPerRosterable) {
          prCell.classList.add("audit-pie-flag");
          prCell.title = ">" + (FLAG_THRESHOLD * 100) + "% from median (" + fmt(pd.medPerRosterable, 2) + ")";
        }
        tr.appendChild(prCell);

        tbody.appendChild(tr);
      });
      table.appendChild(tbody);

      var wrap = el("div", "audit-pie-scroll");
      wrap.appendChild(table);
      sub.appendChild(wrap);
      section.appendChild(sub);
    });

    return section;
  }

  // ── Main render ─────────────────────────────────────────────────────

  function render(rootEl, ctx) {
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
    var verdicts = computeVerdicts(data);

    // Header
    var header = el("div", "audit-pie-header");
    var title = el("p", "audit-pie-meta",
      "League pie: " + fmt(data.pie, 1) + " points" +
      " · " + data.rows.length + " sources" +
      " · active league setting");
    header.appendChild(title);
    rootEl.appendChild(header);

    // Tables
    rootEl.appendChild(buildSummaryTable(data, verdicts));
    rootEl.appendChild(buildPositionTable(data, verdicts));
    rootEl.appendChild(buildRawVsAdjustedTable(data));
    rootEl.appendChild(buildCoverageTable(data));
  }

  // ── Registration ────────────────────────────────────────────────────

  root.AuditPie = {
    extract: extract,
    computeFlags: computeFlags,
    computeVerdicts: computeVerdicts,
    render: render,
    _FLAG_THRESHOLD: FLAG_THRESHOLD,
    _POSITIONS: POSITIONS
  };

  if (root.DDFAudit && typeof root.DDFAudit.register === "function") {
    root.DDFAudit.register("value-pie", render);
  }

})(window);
