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
  // JEG-1260: IR and taxi slots come from the engine's own rule (ValueModel.isReserveSlot, JEG-1188) when the page has it.
  // Without it every non-starter counts on the bench, and the readout says the reserve slots are not known.
  const reserveRule = deps => (deps && deps.isReserveSlot) || (root.ValueModel && root.ValueModel.isReserveSlot) || null;
  const STARTING = ["QB", "RB", "WR", "TE", "FLEX", "SUPERFLEX"];
  const unique = keys => [...new Set(keys)];

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
    // Physical identities: every engine row and every listed entry, each key once (entries carry the league slot).
    const slotOf = new Map(entries.map(entry => [String(entry.key), entry.slot || null]));
    const players = unique(rows.map(keyOf).concat(entries.map(entry => String(entry.key)))).map(key => {
      const row = rows.find(r => keyOf(r) === key);
      const entry = entries.find(e => String(e.key) === key);
      return {key, pos: (row && row.pos) || (entry && entry.pos) || "", slot: slotOf.get(key) || null};
    });
    return {
      rows, players,
      notEvaluated: rows.filter(F.isNotEvaluated).map(keyOf).concat(missing.filter(F.isNotEvaluated).map(entry => String(entry.key))),
      unresolved: missing.filter(entry => !F.isNotEvaluated(entry)).map(entry => String(entry.key))
    };
  }

  // JEG-1260: one team's physical roster, before or after, independent of any value view. players: [{key, pos, slot?}].
  // Starting slots are filled by eligibility alone (finder.js pickStarters with every player at one value, so its slot
  // order and FLEX/SUPERFLEX rules apply), plus K and DEF slots by count. Bench = active players not in a filled
  // starting slot; IR and taxi players are held but are not on the bench. Nothing here prices or cuts anyone.
  function rosterCount(F, players, shape, reserveOf) {
    const PROBE = "__jeg1260_slot";
    const reserve = reserveOf ? players.filter(p => reserveOf(p.slot)) : [];
    const active = players.filter(p => !reserve.includes(p));
    const probe = active.filter(p => !F.isNotEvaluated(p)).map(p => ({player_key: p.key, pos: p.pos, values: {[PROBE]: 1}}));
    const lineup = F.pickStarters(probe, shape, PROBE);
    const want = slot => Math.max(0, Number(shape[slot]) || 0);
    const kickers = Math.min(want("K"), active.filter(p => p.pos === "K").length);
    const defenses = Math.min(want("DST"), active.filter(p => p.pos === "DEF" || p.pos === "DST").length);
    const startingSlots = STARTING.reduce((n, slot) => n + want(slot), 0) + want("K") + want("DST");
    const filled = lineup.starters.length + kickers + defenses;
    return {size: players.length, active: active.length, reserve: reserve.length, startingSlots, filledStarting: filled,
      emptyStarting: startingSlots - filled, bench: active.length - filled};
  }
  // Both rosters before and after the deal, by player identity (each key once). Configured bench capacity is the
  // league's BN setting; over capacity is reported as a number, never resolved by dropping a player.
  function rosterReadout(F, sides, give, receive, shape, reserveOf) {
    const goneMine = new Set(give), goneTheirs = new Set(receive);
    const byKey = new Map(sides.mine.players.concat(sides.theirs.players).map(p => [p.key, p]));
    const configured = Number.isFinite(Number(shape.BENCH)) && shape.BENCH !== null && shape.BENCH !== undefined ? Number(shape.BENCH) : null;
    const one = (players, leaving, arriving) => {
      const before = rosterCount(F, players, shape, reserveOf);
      const after = rosterCount(F, players.filter(p => !leaving.has(p.key)).concat([...arriving].map(k => byKey.get(k))), shape, reserveOf);
      const over = c => (configured !== null && c.bench > configured ? c.bench - configured : 0);
      return {configuredBench: configured, reserveKnown: Boolean(reserveOf), before, after,
        rosterSizeDelta: after.size - before.size, benchDelta: after.bench - before.bench,
        overCapacity: {before: over(before), after: over(after)}};
    };
    return {mine: one(sides.mine.players, goneMine, goneTheirs), theirs: one(sides.theirs.players, goneTheirs, goneMine)};
  }
  // Bench players with a usable value in one view, per position (finder.js rosterBalance's depth rule: at least
  // USABLE_MIN; a missing value is never depth). DDF Value reads the DDF replacement depth, the Trade chart average the
  // market held depth, from the rows the caller passes (the league's own levels when JEG-1188 supplies them).
  function benchDepth(F, lineup, valueKey) {
    const usable = row => row.values && finite(row.values[valueKey]) && row.values[valueKey] >= F.USABLE_MIN;
    return Object.fromEntries(F.DEPTH_POS.map(pos => [pos, lineup.bench.filter(row => row.pos === pos && usable(row)).length]));
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
    // JEG-1260: an outgoing player is on the roster and in the deal; count each missing player once.
    const missing = unique(rosterUnpriced.concat(tradedUnpriced));
    return {
      valueKey, impact,
      starterDelta: impact.starterDelta, benchDelta: impact.benchDelta, totalDelta: impact.totalDelta, spotsOpened: impact.spotsOpened,
      emptyBefore: {...impact.before.empty}, emptyAfter: {...impact.after.empty}, newlyEmpty,
      needLine: F.needLine(impact),
      tradedUnpriced, rosterUnpriced, missing, notEvaluated: notEvaluated.slice(), unresolved: unresolved.slice(),
      depth: {before: benchDepth(F, impact.before, valueKey), after: benchDepth(F, impact.after, valueKey)},
      lowConfidence: valueKey === F.OUR_KEY ? roster.concat(arriving).filter(row => row.ddfLowConfidence && priced(row)).map(keyOf) : [],
      complete: !missing.length && !unresolved.length
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
    const out = {version: VERSION, shape, ourKey, give, receive, outside, views, contextKey: input.contextKey || null,
      ready: Boolean(shape) && give.length > 0 && receive.length > 0 && !outside.give.length && !outside.receive.length,
      reason: null, roster: null, sides: {mine: {}, theirs: {}}};
    if (!shape) out.reason = "League roster shape is unavailable.";
    else if (!give.length || !receive.length) out.reason = "Add a player to both sides to see how each roster changes.";
    else if (outside.give.length || outside.receive.length) out.reason = "This trade includes players outside the selected rosters.";
    if (!out.ready) return out;
    out.roster = rosterReadout(F, {mine, theirs}, give, receive, shape, reserveRule(deps));
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
      newlyEmpty: s.newlyEmpty, needLine: s.needLine, tradedUnpriced: s.tradedUnpriced, rosterUnpriced: s.rosterUnpriced, missing: s.missing,
      depth: s.depth,
      notEvaluated: s.notEvaluated, unresolved: s.unresolved, lowConfidence: s.lowConfidence, complete: s.complete,
      before: lineup(s.impact.before), after: lineup(s.impact.after)} : null);
    const views = Object.fromEntries(Object.entries(readout.views).map(([id, v]) => [id, {status: v.status, reason: v.reason, held: v.held || []}]));
    return {version: readout.version, ready: readout.ready, reason: readout.reason, outside: readout.outside, views, roster: readout.roster,
      mine: Object.fromEntries(Object.entries(readout.sides.mine).map(([id, s]) => [id, side(s)])),
      theirs: Object.fromEntries(Object.entries(readout.sides.theirs).map(([id, s]) => [id, side(s)]))};
  }

  const signedCount = n => (n > 0 ? `+${n}` : n < 0 ? `−${-n}` : "no change");
  const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;
  // Roster size and bench occupancy are separate counts (an empty TE filled by a 2-for-1 is roster −1, bench −2).
  function rosterNotes(r) {
    const lines = [`Roster: ${r.before.size} → ${plural(r.after.size, "player")} (${signedCount(r.rosterSizeDelta)}).`];
    lines.push(r.configuredBench === null
      ? `Bench: ${r.before.bench} → ${r.after.bench} players (${signedCount(r.benchDelta)}); this league's bench size is not set.`
      : `Bench: ${r.before.bench} → ${r.after.bench} of ${plural(r.configuredBench, "spot")} used (${signedCount(r.benchDelta)}).`);
    if (r.after.emptyStarting > 0) lines.push(`${plural(r.after.emptyStarting, "starting slot")} open after the trade.`);
    if (r.overCapacity.after > 0) lines.push(`Over the bench limit by ${r.overCapacity.after} after the trade; no player is dropped automatically.`);
    if (r.reserveKnown && (r.before.reserve || r.after.reserve)) lines.push(`On IR or taxi, not counted on the bench: ${r.before.reserve} → ${r.after.reserve}.`);
    if (!r.reserveKnown) lines.push("IR and taxi slots are not known here, so every player not starting counts on the bench.");
    return lines;
  }
  function depthLine(depth, label) {
    const parts = Object.keys(depth.before).filter(pos => depth.before[pos] || depth.after[pos])
      .map(pos => `${pos} ${depth.before[pos]} → ${depth.after[pos]}`);
    return parts.length ? `${label} (bench players with a usable value): ${parts.join(", ")}.` : null;
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
    const note = (text, extra) => { const p = doc.createElement("p"); p.className = extra ? `v2-meta ${extra}` : "v2-meta"; p.textContent = text; wrap.appendChild(p); };
    if (!readout.ready) { note(readout.reason); return wrap; }
    if (!side) { note(`${view.label}: ${view.reason || "no values for this roster."}`); return wrap; }
    // The bench rows line up before and after players, so their count is a row count, not the After bench count.
    const benchLabel = (rows, hidden) => `${hidden ? "Show" : "Hide"} ${rows} bench row${rows === 1 ? "" : "s"}`;
    const table = L.renderTable(side.impact, readout.shape, side.valueKey, caption || `Best starting lineup in ${view.label}`, {benchLabel});
    table.querySelector("table").setAttribute("data-view", view.label);
    wrap.appendChild(table);
    note(`${side.needLine}.`);
    const roster = readout.roster && readout.roster[who];
    if (roster) rosterNotes(roster).forEach(text => note(text, "v2-readout-roster"));
    const depth = depthLine(side.depth, viewId === "ddf" ? "DDF replacement depth" : viewId === "market" ? "Market held depth" : `Bench depth in ${view.label}`);
    if (depth) note(depth, "v2-readout-depth");
    const missing = side.missing.length;
    if (missing) note(`${missing} player${missing === 1 ? " has" : "s have"} no ${view.label} and ${missing === 1 ? "is" : "are"} left out of this lineup.`);
    if (side.unresolved.length) note(`${side.unresolved.length} roster player${side.unresolved.length === 1 ? " is" : "s are"} missing from this week's values.`);
    if (side.notEvaluated.length) note(`Kickers and defenses are not evaluated (${side.notEvaluated.length} on this roster).`);
    return wrap;
  }

  // JEG-1260: build's input from JEG-1229's TradeContext (fromCompare / fromLeague / fromPair), so the same context and
  // deal give the same readout on every route. env: {rowsByKey (Map of engine rows; the league's level rows when JEG-1188
  // supplies them), shape, ourKey?, chartKeys, sourceInfo?}. The partner is Their team, or on the league finder the one
  // opponent holding every received key (TradeContext.dealPartner). Source status falls back to context.common.sources.
  function inputFromContext(context, env, deps) {
    const TC = (deps && deps.context) || root.TradeValueTradeContext || null;
    const ctx = context || {};
    const e = env || {};
    const teams = ctx.teams || {};
    const partner = TC && TC.dealPartner ? TC.dealPartner(ctx) : teams.theirs || null;
    const side = team => {
      const entries = (team && team.roster) || [];
      return {rows: entries.map(entry => e.rowsByKey.get(String(entry.key))).filter(Boolean),
        entries: entries.map(entry => ({key: String(entry.key), name: entry.name, pos: entry.pos, ...(entry.slot ? {slot: entry.slot} : {})}))};
    };
    const sources = (ctx.common && ctx.common.sources) || {};
    const sourceInfo = e.sourceInfo || Object.keys(sources).map(key => ({key, available: sources[key].status === "available",
      ...(sources[key].status === "held" ? {excludedReason: `held: ${sources[key].reason || "data check"}`} : {})}));
    return {shape: e.shape, ourKey: e.ourKey, chartKeys: e.chartKeys, sourceInfo, mine: side(teams.mine), theirs: side(partner),
      give: (ctx.deal && ctx.deal.give) || [], receive: (ctx.deal && ctx.deal.get) || [],
      contextKey: TC && TC.cacheKey ? TC.cacheKey(ctx, "readout") : null};
  }

  const api = {VERSION, VIEWS, build, summary, renderSide, sourceStatus, inputFromContext};
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.TradeValueReadout = api;
})(typeof window !== "undefined" ? window : globalThis);
