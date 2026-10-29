// JEG-1230: one readout of an explicit trade for Compare, Find a trade and the league finder. It only gathers what
// finder.js already computes (rosterImpact, withChartAverage, needLine, isNotEvaluated) per available view and says
// why a view is missing; lineup-comparison.js draws it. No valuation, lineup, fit or ranking rule lives here.
(function (root) {
  "use strict";
  const finite = n => typeof n === "number" && Number.isFinite(n);
  const keyOf = row => String(row.player_key);
  const VERSION = 1;
  // View ids and labels follow the JEG-1221 glossary; market keeps today's "Trade chart average" until #1071 renames it.
  const VIEWS = Object.freeze([
    Object.freeze({id: "ddf", label: "DDF Value"}),
    Object.freeze({id: "market", label: "Trade chart average"}),
    Object.freeze({id: "projections", label: "DDF Value (projections)"})
  ]);
  const HELD = item => Boolean(item && item.excludedReason && /^held/i.test(item.excludedReason));
  const finder = deps => (deps && deps.finder) || root.TradeValueFinder || (typeof require === "function" ? require("./finder.js") : null);

  // Why a source is not in this view this week, in the page's words (v2.js unavailableReason).
  function sourceStatus(sourceInfo, keys) {
    const byKey = new Map((sourceInfo || []).map(item => [item.key, item]));
    return keys.map(key => {
      const item = byKey.get(key);
      const reason = !item ? null : item.available ? null : HELD(item) ? "held this week (data check)"
        : item.paused ? "waiting on fresh inputs" : "not available for this league";
      return {key, available: !item || Boolean(item.available), held: HELD(item), reason};
    });
  }

  // Splits a side's explicit roster into priced rows, kickers/defenses (not evaluated) and entries with no engine row.
  function sideRoster(side, F) {
    const rows = (side && side.rows) || [];
    const have = new Set(rows.map(keyOf));
    const entries = (side && side.entries) || [];
    const missing = entries.filter(entry => !have.has(String(entry.key)));
    return {
      rows,
      notEvaluated: rows.filter(F.isNotEvaluated).map(keyOf).concat(missing.filter(F.isNotEvaluated).map(entry => String(entry.key))),
      unresolved: missing.filter(entry => !F.isNotEvaluated(entry)).map(entry => String(entry.key))
    };
  }

  // One team, one view: the exact rosterImpact result plus what is missing from it. Nothing is recomputed.
  function sideReadout(F, roster, leaving, arriving, shape, valueKey, notEvaluated, unresolved) {
    const impact = F.rosterImpact(roster, leaving, arriving, shape, valueKey);
    const priced = row => Boolean(row.values) && finite(row.values[valueKey]);
    const unpriced = rows => rows.filter(row => !priced(row) && !F.isNotEvaluated(row)).map(keyOf);
    const newlyEmpty = {};
    Object.keys(impact.after.empty).forEach(slot => {
      const more = impact.after.empty[slot] - (impact.before.empty[slot] || 0);
      if (more > 0) newlyEmpty[slot] = more;
    });
    const tradedUnpriced = unpriced(leaving.concat(arriving));
    const rosterUnpriced = unpriced(roster);
    return {
      valueKey, impact,
      starterDelta: impact.starterDelta, benchDelta: impact.benchDelta, totalDelta: impact.totalDelta, spotsOpened: impact.spotsOpened,
      emptyBefore: {...impact.before.empty}, emptyAfter: {...impact.after.empty}, newlyEmpty,
      needLine: F.needLine(impact),
      tradedUnpriced, rosterUnpriced, notEvaluated: notEvaluated.slice(), unresolved: unresolved.slice(),
      lowConfidence: valueKey === F.OUR_KEY ? roster.concat(arriving).filter(row => row.ddfLowConfidence && priced(row)).map(keyOf) : [],
      complete: !tradedUnpriced.length && !rosterUnpriced.length && !unresolved.length
    };
  }

  // input: {shape, ourKey, chartKeys, sourceInfo, mine: {rows, entries?}, theirs: {rows, entries?}, give: [keys], receive: [keys]}
  // chartKeys are the charts the engine says are available; the market view needs F.MIN_CHARTS of them (finder.js and
  // league.js rule). give leaves mine for theirs; receive leaves theirs for mine. Inputs are never modified.
  function build(input, deps) {
    const F = finder(deps);
    if (!F || !F.rosterImpact) throw new Error("TradeValueFinder is required");
    const shape = input.shape || null;
    const ourKey = input.ourKey || F.OUR_KEY;
    const give = (input.give || []).map(String);
    const receive = (input.receive || []).map(String);
    const mine = sideRoster(input.mine, F);
    const theirs = sideRoster(input.theirs, F);
    const mineByKey = new Map(mine.rows.map(row => [keyOf(row), row]));
    const theirByKey = new Map(theirs.rows.map(row => [keyOf(row), row]));
    const outside = {give: give.filter(key => !mineByKey.has(key)), receive: receive.filter(key => !theirByKey.has(key))};
    const charts = (input.chartKeys || []).slice();
    const market = charts.length >= F.MIN_CHARTS ? charts : null;
    const allRows = mine.rows.concat(theirs.rows);
    const projectionSources = sourceStatus(input.sourceInfo, F.PROJECTION_KEYS);
    const chartSources = sourceStatus(input.sourceInfo, F.CHART_KEYS);
    const heldNames = list => list.filter(s => s.held).map(s => s.key);
    const views = {
      ddf: {id: "ddf", label: "DDF Value", valueKey: ourKey,
        status: allRows.some(row => row.values && finite(row.values[ourKey])) ? "available" : "unavailable",
        reason: allRows.some(row => row.values && finite(row.values[ourKey])) ? null : "No DDF Value for these rosters this week."},
      market: {id: "market", label: "Trade chart average", valueKey: F.MARKET_KEY, chartKeys: market, sources: chartSources,
        held: heldNames(chartSources), status: market ? "available" : "unavailable",
        reason: market ? null : charts.length ? `Only ${charts.length} trade chart${charts.length === 1 ? " is" : "s are"} available this week.`
          : "No trade chart is available this week."},
      projections: {id: "projections", label: "DDF Value (projections)", valueKey: F.PROJECTIONS_KEY, sources: projectionSources,
        held: heldNames(projectionSources), status: F.hasProjections(allRows) ? "available" : "unavailable",
        reason: F.hasProjections(allRows) ? null : heldNames(projectionSources).length === F.PROJECTION_KEYS.length
          ? "Projection sources are held this week (data check)." : "No projection values for these rosters."}
    };
    const out = {version: VERSION, shape, ourKey, give, receive, outside, views,
      ready: Boolean(shape) && give.length > 0 && receive.length > 0 && !outside.give.length && !outside.receive.length,
      reason: null, sides: {mine: {}, theirs: {}}};
    if (!shape) out.reason = "League roster shape is unavailable.";
    else if (!give.length || !receive.length) out.reason = "Add a player to both sides to see how each roster changes.";
    else if (outside.give.length || outside.receive.length) out.reason = "This trade includes players outside the selected rosters.";
    if (!out.ready) return out;
    // Each view reads the same rows; the market view reads them with the chart average added (finder lineupContext).
    const rowsFor = id => {
      if (id !== "market") return {mine: mine.rows, theirs: theirs.rows};
      return {mine: F.withChartAverage(mine.rows, market), theirs: F.withChartAverage(theirs.rows, market)};
    };
    VIEWS.forEach(({id}) => {
      const view = views[id];
      if (view.status !== "available") { out.sides.mine[id] = null; out.sides.theirs[id] = null; return; }
      const rows = rowsFor(id);
      const pickMine = new Map(rows.mine.map(row => [keyOf(row), row]));
      const pickTheirs = new Map(rows.theirs.map(row => [keyOf(row), row]));
      const giveRows = give.map(key => pickMine.get(key));
      const receiveRows = receive.map(key => pickTheirs.get(key));
      // A team whose rows carry no value in this view gets no readout (finder.js hasProjections rule), never zeros.
      const valued = list => list.some(row => row.values && finite(row.values[view.valueKey]));
      out.sides.mine[id] = valued(rows.mine.concat(receiveRows))
        ? sideReadout(F, rows.mine, giveRows, receiveRows, shape, view.valueKey, mine.notEvaluated, mine.unresolved) : null;
      out.sides.theirs[id] = valued(rows.theirs.concat(giveRows))
        ? sideReadout(F, rows.theirs, receiveRows, giveRows, shape, view.valueKey, theirs.notEvaluated, theirs.unresolved) : null;
    });
    return out;
  }

  // A plain-number copy of a readout (golden fixtures and cross-route comparison). No rows, no DOM.
  function summary(readout) {
    const lineup = l => ({starterValue: l.starterValue, benchValue: l.benchValue, total: l.total, counts: {...l.counts}, size: l.size,
      slots: Object.fromEntries(Object.entries(l.slots).map(([slot, rows]) => [slot, rows.map(keyOf)])),
      bench: l.bench.map(keyOf), unvalued: l.unvalued.map(keyOf), empty: {...l.empty}});
    const side = s => (s ? {starterDelta: s.starterDelta, benchDelta: s.benchDelta, totalDelta: s.totalDelta, spotsOpened: s.spotsOpened,
      newlyEmpty: s.newlyEmpty, needLine: s.needLine, tradedUnpriced: s.tradedUnpriced, rosterUnpriced: s.rosterUnpriced,
      notEvaluated: s.notEvaluated, unresolved: s.unresolved, lowConfidence: s.lowConfidence, complete: s.complete,
      before: lineup(s.impact.before), after: lineup(s.impact.after)} : null);
    const views = Object.fromEntries(Object.entries(readout.views).map(([id, v]) => [id, {status: v.status, reason: v.reason, held: v.held || []}]));
    return {version: readout.version, ready: readout.ready, reason: readout.reason, outside: readout.outside, views,
      mine: Object.fromEntries(Object.entries(readout.sides.mine).map(([id, s]) => [id, side(s)])),
      theirs: Object.fromEntries(Object.entries(readout.sides.theirs).map(([id, s]) => [id, side(s)]))};
  }

  // One team's readout in one view, drawn by the shared lineup table. An unavailable view says why instead of a zero.
  function renderSide(readout, who, viewId, caption, deps) {
    const doc = (deps && deps.document) || root.document;
    const L = (deps && deps.lineup) || root.TradeValueLineupComparison;
    const view = readout.views[viewId];
    const side = readout.sides[who] && readout.sides[who][viewId];
    const wrap = doc.createElement("div");
    wrap.className = "v2-readout-view";
    wrap.dataset.view = viewId;
    wrap.dataset.status = !readout.ready ? "not-ready" : side ? (side.complete ? "complete" : "partial") : view.status;
    const note = text => { const p = doc.createElement("p"); p.className = "v2-meta"; p.textContent = text; wrap.appendChild(p); };
    if (!readout.ready) { note(readout.reason); return wrap; }
    if (!side) { note(`${view.label}: ${view.reason || "no values for this roster."}`); return wrap; }
    const table = L.renderTable(side.impact, readout.shape, side.valueKey, caption || `Best starting lineup in ${view.label}`);
    table.querySelector("table").setAttribute("data-view", view.label);
    wrap.appendChild(table);
    note(`${side.needLine}.`);
    const missing = side.tradedUnpriced.length + side.rosterUnpriced.length;
    if (missing) note(`${missing} player${missing === 1 ? " has" : "s have"} no ${view.label} and ${missing === 1 ? "is" : "are"} left out of this lineup.`);
    if (side.unresolved.length) note(`${side.unresolved.length} roster player${side.unresolved.length === 1 ? " is" : "s are"} missing from this week's values.`);
    if (side.notEvaluated.length) note(`Kickers and defenses are not evaluated (${side.notEvaluated.length} on this roster).`);
    return wrap;
  }

  const api = {VERSION, VIEWS, build, summary, renderSide, sourceStatus};
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.TradeValueReadout = api;
})(typeof window !== "undefined" ? window : globalThis);
