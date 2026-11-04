// JEG-1230: one readout of an explicit trade for Compare, Find a trade and the league finder. It only gathers what
// finder.js already computes (rosterImpact, withChartAverage, needLine, isNotEvaluated) per available view and says
// why a view is missing; lineup-comparison.js draws it. JEG-1483 adds the explicit
// private four-entry fit policy, reusing existing lineup/roster/noise functions.
// Player valuation, lineup selection and ranking algorithms stay in their owners.
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

  // JEG-1483 is an explicit private-contract opt-in. Existing callers without
  // calculationSettings keep the released readout until their route integrates
  // the reconciled contract. No price, lineup picker or roster check is forked.
  const PUBLISHED_CHARTS = Object.freeze(["usatoday", "fantasypros", "cbs"]);
  const MARKET_NAMES = {"published-average": "Indexed published-chart average", usatoday: "USA Today", fantasypros: "FantasyPros", cbs: "CBS", fantasycalc: "Indexed FantasyCalc"};
  function calculationSettings(raw) {
    const r = raw || {}, minimum = (value, ours) => {
      const v = value || {}, allowed = ours ? ["any", "noise", "custom"] : ["neutral", "noise", "gain", "custom"];
      const tier = allowed.includes(v.tier) ? v.tier : allowed[0];
      return {tier, ...(tier === "custom" ? {value: finite(v.value) ? (ours ? Math.max(0, v.value) : v.value) : 0} : {})};
    };
    return {basis: r.basis === "ddf_value_projections" ? r.basis : "ddf_value",
      market: Object.hasOwn(MARKET_NAMES, r.market) ? r.market : "published-average",
      ourMinimum: minimum(r.ourMinimum, true), theirMinimum: minimum(r.theirMinimum, false)};
  }
  // Values' range, Build's MKT column and the readout use this same coverage
  // definition. A fallback single publisher value is never called an average.
  function marketQuote(row, raw, availableKeys = [...PUBLISHED_CHARTS, "fantasycalc"]) {
    const settings = calculationSettings(raw), average = settings.market === "published-average";
    const wanted = average ? PUBLISHED_CHARTS : [settings.market];
    const sources = wanted.filter(k => availableKeys.includes(k) && finite(row?.values?.[k]));
    const values = sources.map(k => row.values[k]), fitAvailable = average ? values.length >= 2 : values.length === 1;
    const mean = values.length ? values.reduce((a, b) => a + b, 0) / values.length : null;
    const coverage = {available: sources.length, total: wanted.length, required: average ? 2 : 1, text: `${sources.length} of ${wanted.length}`};
    const sourceViews = root.DDFSourceViews || (typeof require === "function" ? require("./source-views.js") : null);
    const ancestry = sourceViews ? sourceViews.read(row, settings.market === "fantasycalc" ? "observed_trade_estimate" : "published_chart_average", availableKeys).inputs.filter(input => wanted.includes(input.key)) : null;
    return {value: mean, average: average && fitAvailable ? mean : null, fitAvailable, sources, coverage,
      inputs: ancestry,
      status: fitAvailable ? "available" : sources.length ? "individual" : "unknown",
      label: average && !fitAvailable && sources.length ? MARKET_NAMES[sources[0]] : MARKET_NAMES[settings.market],
      aggregation: average && fitAvailable ? "arithmetic mean of complete indexed published charts" : "individual indexed source",
      range: average && fitAvailable ? {min: Math.min(...values), max: Math.max(...values),
        lowSources: sources.filter(k => row.values[k] === Math.min(...values)), highSources: sources.filter(k => row.values[k] === Math.max(...values))} : null};
  }
  function marketPlan(rows, settings, availableKeys, F) {
    const wanted = settings.market === "published-average" ? PUBLISHED_CHARTS : [settings.market];
    const valued = rows.filter(r => !F.isNotEvaluated(r));
    // All compared roster values use one compatible source set; no incomplete
    // source contributes a different denominator to one team's starter sum.
    const complete = wanted.filter(k => availableKeys.includes(k) && valued.length && valued.every(r => finite(r.values?.[k])));
    const average = settings.market === "published-average", required = average ? 2 : 1;
    return {fitAvailable: complete.length >= required, chartKeys: complete,
      coverage: {available: complete.length, total: wanted.length, required, text: `${complete.length} of ${wanted.length}`},
      label: average && complete.length === 1 ? MARKET_NAMES[complete[0]] : MARKET_NAMES[settings.market],
      aggregation: average && complete.length >= required ? "arithmetic mean of complete indexed published charts" : "individual indexed source"};
  }

  function starterDecision(out, settings, inputs, F, partnerKind) {
    const basisView = settings.basis === F.PROJECTIONS_KEY ? "projections" : "ddf";
    const quantity = (subject, scope, basis, value, known, sources, coverage, aggregation, extra = {}) => ({subject, scope, basis,
      value: known ? value : null, status: known ? "known" : "unknown", sources, coverage, aggregation,
      sign: "positive is better for the subject", tolerance: null, ...extra});
    const side = (who, id, rosterId, minimum) => {
      const view = out.sides[who][id], meta = out.views[id], known = Boolean(out.ready && view?.complete && meta.status === "available");
      const sourceKeys = id === "market" ? meta.chartKeys || [] : [view?.valueKey || (id === "ddf" ? out.ourKey : F.PROJECTIONS_KEY)];
      const coverage = id === "market" ? meta.coverage : {available: known ? 1 : 0, total: 1, required: 1, text: `${known ? 1 : 0} of 1`};
      const team = inputs[id]?.[who];
      const tau = known && team ? F.fitTolerance(team.leaving.concat(team.arriving), view.valueKey, meta.chartKeys || inputs.chartKeys) : null;
      let threshold = 0, operator = who === "mine" ? ">" : ">=";
      if (minimum.tier === "noise") { threshold = who === "mine" ? tau : tau === null ? null : -tau; }
      if (minimum.tier === "gain") operator = ">";
      if (minimum.tier === "custom") { threshold = minimum.value; operator = who === "mine" && threshold === 0 ? ">" : ">="; }
      const value = known ? view.starterDelta : null;
      const pass = !known ? null : operator === ">" ? value > threshold : value >= threshold;
      const basis = id === "market" ? settings.market : settings.basis;
      const q = quantity(who, "starters", basis, value, known, sourceKeys, coverage, "sum of existing best eligible starting lineup", {
        id: rosterId === "our-roster" ? "our-starters" : "their-starters", label: who === "mine" ? "Our starter value" : "Their market starter value",
        tolerance: tau, threshold, operator, tier: minimum.tier, pass,
        reason: known ? null : out.reason || meta.reason || "This roster has unresolved or missing values."});
      const construction = known && team ? F.rosterConstructionOk(team, out.shape, view.valueKey, view.impact) : null;
      const roster = quantity(who, "roster", basis, construction?.ok ?? null, Boolean(construction), sourceKeys, coverage, "existing rosterConstructionOk", {
        id: rosterId, label: who === "mine" ? "Our roster construction" : "Their roster construction", pass: construction?.ok ?? null,
        issues: construction?.issues || [], reason: construction ? null : "Roster construction cannot be judged with unresolved or missing roster values."});
      return [q, roster];
    };
    const questions = [...side("mine", basisView, "our-roster", settings.ourMinimum), ...side("theirs", "market", "their-roster", settings.theirMinimum)];
    const waiver = partnerKind === "waivers";
    if (waiver) questions.splice(2, 2, ...questions.slice(2).map(q => ({...q, value: null, pass: null, status: "not_applicable", reason: "Not applicable: Waivers"})));
    const tested = waiver ? questions.slice(0, 2) : questions, natural = !waiver && tested.every(q => q.pass === true);
    const supporting = {};
    for (const who of ["mine", "theirs"]) {
      if (waiver && who === "theirs") { supporting[who] = null; continue; }
      supporting[who] = {};
      for (const id of ["ddf", "projections", "market"]) {
        const s = out.sides[who][id], meta = out.views[id], complete = Boolean(s?.complete);
        const basis = id === "market" ? settings.market : meta.valueKey, sources = meta.chartKeys || [meta.valueKey];
        const coverage = known => meta.coverage || {available: known ? 1 : 0, total: 1, required: 1, text: `${known ? 1 : 0} of 1`};
        // A package can be fully priced even when an unrelated roster player
        // is unresolved. Do not turn that known package evidence into a fit.
        const packageKnown = Boolean(s && !s.tradedUnpriced.length && finite(s.totalDelta));
        supporting[who][id] = {starters: quantity(who, "starters", basis, s?.starterDelta, complete, sources, coverage(complete), "existing rosterImpact starter delta"),
          package: quantity(who, "package total", basis, s?.totalDelta, packageKnown, sources, coverage(packageKnown), "sum received minus sum given")};
      }
    }
    return {contract: "JEG-1483/1", settings, questions, natural, participants: out.participants,
      partnerKind: waiver ? "waivers" : "team", deal: {give: out.give.slice(), get: out.receive.slice()},
      label: waiver ? "Pickup" : natural ? "Natural fit" : tested.some(q => q.pass === null) ? "Not judged" : "Other",
      passes: tested.every(q => q.pass === true), failed: tested.filter(q => q.pass === false).map(q => q.id), unknown: tested.filter(q => q.pass === null).map(q => q.id), supporting};
  }

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
  function sideReadout(F, roster, leaving, arriving, shape, valueKey, notEvaluated, unresolved, options) {
    const impact = F.rosterImpact(roster, leaving, arriving, shape, valueKey, options?.before);
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
      depth: options?.decisionOnly ? null : {before: benchDepth(F, impact.before, valueKey), after: benchDepth(F, impact.after, valueKey)},
      lowConfidence: valueKey === F.OUR_KEY ? roster.concat(arriving).filter(row => row.ddfLowConfidence && priced(row)).map(keyOf) : [],
      complete: !missing.length && !unresolved.length
    };
  }

  // input: {shape, ourKey, chartKeys, sourceInfo, mine: {rows, entries?}, theirs: {rows, entries?}, give: [keys], receive: [keys]}
  // chartKeys are the charts the engine says are available; the market view needs F.MIN_CHARTS of them (finder.js and
  // league.js rule). give leaves mine for theirs; receive leaves theirs for mine. Inputs are never modified.
  function build(input, deps) {
    const F = finder(deps);
    const memo = deps?._memo;
    const indexOf = rows => {
      let indexed = memo?.indexes.get(rows);
      if (!indexed) { indexed = new Map(rows.map(row => [keyOf(row), row])); memo?.indexes.set(rows, indexed); }
      return indexed;
    };
    const sideOf = side => {
      let found = memo?.sides.get(side);
      if (!found) { found = sideRoster(side, F); if (side) memo?.sides.set(side, found); }
      return found;
    };
    if (!F || !F.rosterImpact) throw new Error("TradeValueFinder is required");
    const calculations = input.calculationSettings ? calculationSettings(input.calculationSettings) : null;
    const shape = input.shape || null;
    // A released display-series parameter is not a second calculation basis.
    const ourKey = calculations ? F.OUR_KEY : input.ourKey || F.OUR_KEY;
    const give = (input.give || []).map(String);
    const receive = (input.receive || []).map(String);
    const mine = sideOf(input.mine);
    const theirs = sideOf(input.theirs);
    const mineByKey = indexOf(mine.rows);
    const theirByKey = indexOf(theirs.rows);
    const outside = {give: give.filter(key => !mineByKey.has(key)), receive: receive.filter(key => !theirByKey.has(key))};
    const charts = (input.chartKeys || []).slice();
    const allRows = mine.rows.concat(theirs.rows);
    const allowedCharts = charts.filter(k => !(input.sourceInfo || []).some(s => s.key === k && (!s.available || s.paused || HELD(s))));
    const waiver = calculations && input.partnerKind === "waivers";
    const marketRows = waiver ? mine.rows.concat(receive.map(k => theirByKey.get(k)).filter(Boolean)) : allRows;
    const planKey = waiver ? receive.slice().sort().join(",") : "team";
    let plan = memo?.plans.get(planKey);
    if (!plan) { plan = calculations ? marketPlan(marketRows, calculations, allowedCharts, F) : null; if (plan) memo?.plans.set(planKey, plan); }
    const market = calculations ? plan.fitAvailable ? plan.chartKeys : null : charts.length >= F.MIN_CHARTS ? charts : null;
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
    if (plan) Object.assign(views.market, {label: plan.label, chartKeys: plan.chartKeys, coverage: plan.coverage, sources: sourceStatus(input.sourceInfo, calculations.market === "published-average" ? PUBLISHED_CHARTS : [calculations.market]),
      aggregation: plan.aggregation, reason: plan.fitAvailable ? null : `${plan.coverage.text} complete ${calculations.market === "published-average" ? "published " : ""}sources for these rosters; no average or market fit judgment.`});
    if (calculations && input.sourceInfo?.length && !input.sourceInfo.some(s => F.PROJECTION_KEYS.includes(s.key) && s.available && !s.paused && !HELD(s))) {
      Object.assign(views.projections, {status: "unavailable", reason: "Projection sources are unavailable or held; stale values are not used for judgment."});
    }
    const out = {version: VERSION, shape, ourKey, give, receive, outside, views, contextKey: input.contextKey || null,
      ready: Boolean(shape) && (give.length > 0 || calculations && input.partnerKind === "waivers") && receive.length > 0 && !outside.give.length && !outside.receive.length,
      reason: null, roster: null, sides: {mine: {}, theirs: {}}};
    if (calculations) out.participants = {mine: input.mine?.id == null ? null : String(input.mine.id), theirs: input.theirs?.id == null ? null : String(input.theirs.id)};
    if (!shape) out.reason = "League roster shape is unavailable.";
    else if ((!give.length && !(calculations && input.partnerKind === "waivers")) || !receive.length) out.reason = "Add a player to both sides to see how each roster changes.";
    else if (outside.give.length || outside.receive.length) out.reason = "This trade includes players outside the selected rosters.";
    if (calculations && (new Set(give).size !== give.length || new Set(receive).size !== receive.length || give.some(k => receive.includes(k)))) {
      out.ready = false; out.reason = "The package contains duplicate or conflicting player identities.";
    }
    if (calculations && [...mineByKey.keys()].some(key => theirByKey.has(key))) {
      out.ready = false; out.reason = "A player appears on both selected rosters; resolve ownership before judging fit.";
    }
    if (!out.ready) {
      if (calculations) out.decision = starterDecision(out, calculations, {chartKeys: charts}, F, input.partnerKind);
      return out;
    }
    if (!deps?._decisionOnly) {
      out.roster = rosterReadout(F, {mine, theirs}, give, receive, shape, reserveRule(deps));
      if (waiver) out.roster.theirs = null; // No manager, roster limit, or starting lineup belongs to Waivers.
    }
    // Each view reads the same rows; the market view reads them with the chart average added (finder lineupContext).
    const rowsFor = id => {
      if (id !== "market") return {mine: mine.rows, theirs: theirs.rows};
      const key = market.join(","); let found = memo?.marketRows.get(key);
      if (!found) { found = {mine: F.withChartAverage(mine.rows, market), theirs: F.withChartAverage(theirs.rows, market)}; memo?.marketRows.set(key, found); }
      return found;
    };
    const decisionInputs = {chartKeys: plan?.chartKeys || charts};
    VIEWS.forEach(({id}) => {
      const view = views[id];
      if (view.status !== "available") { out.sides.mine[id] = null; out.sides.theirs[id] = null; return; }
      const rows = rowsFor(id);
      const pickMine = indexOf(rows.mine);
      const pickTheirs = indexOf(rows.theirs);
      const giveRows = give.map(key => pickMine.get(key));
      const receiveRows = receive.map(key => pickTheirs.get(key));
      decisionInputs[id] = {mine: {roster: rows.mine, leaving: giveRows, arriving: receiveRows}, theirs: {roster: rows.theirs, leaving: receiveRows, arriving: giveRows}};
      // A team whose rows carry no value in this view gets no readout (finder.js hasProjections rule), never zeros.
      const valued = list => list.some(row => row.values && finite(row.values[view.valueKey]));
      const optionsFor = who => {
        if (!memo) return null;
        const key = `${who}:${id}:${view.valueKey}:${id === "market" ? market.join(",") : ""}`;
        let before = memo.before.get(key);
        if (!before) { before = F.lineupValue(rows[who], shape, view.valueKey); memo.before.set(key, before); }
        return {before, decisionOnly: Boolean(deps._decisionOnly)};
      };
      out.sides.mine[id] = valued(rows.mine.concat(receiveRows))
        ? sideReadout(F, rows.mine, giveRows, receiveRows, shape, view.valueKey, mine.notEvaluated, mine.unresolved, optionsFor("mine")) : null;
      out.sides.theirs[id] = !waiver && valued(rows.theirs.concat(giveRows))
        ? sideReadout(F, rows.theirs, receiveRows, giveRows, shape, view.valueKey, theirs.notEvaluated, theirs.unresolved, optionsFor("theirs")) : null;
    });
    if (calculations) out.decision = starterDecision(out, calculations, decisionInputs, F, input.partnerKind);
    return out;
  }

  // One captured pair/settings snapshot only. Cache before-lineups/indexes,
  // never eligibility or after-lineups; each exact package is still evaluated.
  function createEvaluator(baseInput, deps) {
    const base = {...baseInput, calculationSettings: baseInput.calculationSettings || {}};
    const memo = {sides: new WeakMap(), indexes: new WeakMap(), plans: new Map(), marketRows: new Map(), before: new Map()};
    return {evaluate: deal => build({...base, give: deal.give || [], receive: deal.receive || deal.get || []}, {...deps, _memo: memo, _decisionOnly: true}).decision};
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
    const views = Object.fromEntries(Object.entries(readout.views).map(([id, v]) => [id, {status: v.status, reason: v.reason, held: v.held || [],
      ...(readout.decision ? {label: v.label, valueKey: v.valueKey, ...(v.coverage ? {coverage: v.coverage, chartKeys: v.chartKeys, aggregation: v.aggregation} : {})} : {})}]));
    return {version: readout.version, ready: readout.ready, reason: readout.reason, outside: readout.outside, views, roster: readout.roster,
      ...(readout.decision ? {decision: JSON.parse(JSON.stringify(readout.decision))} : {}),
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
      return {id: team?.id ?? null, rows: entries.map(entry => e.rowsByKey.get(String(entry.key))).filter(Boolean),
        entries: entries.map(entry => ({key: String(entry.key), name: entry.name, pos: entry.pos, ...(entry.slot ? {slot: entry.slot} : {})}))};
    };
    const sources = (ctx.common && ctx.common.sources) || {};
    const sourceInfo = e.sourceInfo || Object.keys(sources).map(key => ({key, available: sources[key].status === "available",
      ...(sources[key].status === "held" ? {excludedReason: `held: ${sources[key].reason || "data check"}`} : {})}));
    return {shape: e.shape, ourKey: e.ourKey, chartKeys: e.chartKeys, sourceInfo, mine: side(teams.mine), theirs: side(partner),
      ...(e.calculationSettings || ctx.common?.calculationSettings ? {calculationSettings: e.calculationSettings || ctx.common.calculationSettings} : {}),
      ...(e.partnerKind || partner?.kind ? {partnerKind: e.partnerKind || partner.kind} : {}),
      give: (ctx.deal && ctx.deal.give) || [], receive: (ctx.deal && ctx.deal.get) || [],
      contextKey: TC && TC.cacheKey ? TC.cacheKey(ctx, "readout") : null};
  }

  const api = {VERSION, VIEWS, build, summary, renderSide, sourceStatus, inputFromContext, PUBLISHED_CHARTS, calculationSettings, marketQuote, createEvaluator};
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.TradeValueReadout = api;
})(typeof window !== "undefined" ? window : globalThis);
