// JEG-1230: one readout of an explicit trade for Compare, Find a trade and the league finder. It only gathers what
// finder.js already computes (rosterImpact, withChartAverage, needLine, isNotEvaluated) per available view and says
// why a view is missing; lineup-comparison.js draws it. No valuation, lineup, fit or ranking rule lives here.
(function (root) {
  "use strict";
  const finite = n => typeof n === "number" && Number.isFinite(n);
  const keyOf = row => String(row.player_key);
  const VERSION = 2;   // 2: JEG-1323 second-half rows (readout.rows)
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
    if (!out.ready) { out.rows = secondHalf(F, input, out, null, deps); return out; }
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
    out.rows = secondHalf(F, input, out, {mine, theirs, market, rowsFor, mineByKey, theirByKey}, deps);
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
      rows: readout.rows ? rowsSummary(readout.rows) : null,
      mine: Object.fromEntries(Object.entries(readout.sides.mine).map(([id, s]) => [id, side(s)])),
      theirs: Object.fromEntries(Object.entries(readout.sides.theirs).map(([id, s]) => [id, side(s)]))};
  }

  // ---------- JEG-1323: the readout's second half (spec docs/specs/trade-page-parity.md 3.2, slice 4) ----------
  // Five rows: verdict, will they accept, sell gap, data labels, context line. Like the first half they only gather what
  // finder.js (tradeFit, fitText, viabilityLabel, evaluateCombo, withChartAverage) and team-summary.js (marketGaps) already
  // compute, plus what the caller hands in from #1084 (the appeal band) and #1105 (league depth). No new number, no new rule.
  // Every row reads one basis (rest-of-season values); the week in the context line is the values' data week, never a
  // weekly number, so no row mixes weekly and ROS data. Extra input fields, all optional:
  //   fit:        {expected, weights, z?}, the depth and bench weights of finder.js fitContext / league.js mathContext.
  //   appeal:     the #1084 recommendation for this deal and partner: {band: "likely"|"possible"|"longShot", likelihood, why?}.
  //   leagueDepth:{check: {ok, reasons}, gapOf(key) -> {ours, theirs, gap} | null, floor?}: #1105's completeness check, its
  //               per-player gap (DDF Value at the market level minus the DDF level) and its SELL_MIN_GAP. Used only when check.ok.
  //   context:    {scoring, teams, superflex?, basis: {mode}, benchLevel: "modeled"|"league", week}. inputFromContext fills it.
  // Labels reuse the finder's words and the JEG-1221 strings (S8, S9, S10, S13, GL-03 tags).
  const FIT_NAME = Object.freeze({natural: "Natural fit", market: "Market supported", force: "Force fit"});
  const VIABILITY_NAME = Object.freeze({High: "High viability", "Med-High": "Medium-high viability", Medium: "Medium viability"});
  const APPEAL_BANDS = Object.freeze(["likely", "possible", "longShot"]);
  const SCORING_NAME = Object.freeze({standard: "Standard", half_ppr: "Half PPR", ppr: "Full PPR"});
  const MARKET_LABEL = "Trade chart average";
  const CHART_NAMES = Object.freeze({usatoday: "USA Today", fantasycalc: "FantasyCalc", fantasypros: "FantasyPros", cbs: "CBS Sports"});   // finder.js CHART_NAMES
  const LOW_CONFIDENCE_NOTE = "Only one source prices this player";   // v2.js LOW_CONFIDENCE_NOTE
  const STRINGS = Object.freeze({
    notEvaluated: "Not evaluated: kickers and defenses have no trade value. Kept on the roster, left out of every sum.",   // S8
    noValueThisWeek: "No value this week: not in this week's sources. Left out of every sum, not counted as 0.",          // S9
    noSeriesValue: series => `No ${series} value: left out of this series, not counted as 0.`,                           // S10
    tooFewCharts: n => `Not enough trade charts this week (${n} of 3 needed), so we can't judge whether they'd accept.`, // S13
    marketChip: n => `${MARKET_LABEL} unavailable (${n} of 3 charts).`                                                  // S13 chip
  });
  const overrideFmt = v => (finite(v) ? (Math.abs(v) < 0.05 ? "0.0" : v.toFixed(1).replace("-", "−")) : "—");   // overrides.js fmt
  // overrides.js flag(): the page's own badge text when it is loaded, else the same words (modelValue, fmt).
  function overrideText(row, deps) {
    const O = (deps && deps.overrides) || root.DDFOverrides || null;
    const badge = O && O.flag ? O.flag(row) : null;
    if (badge && badge.title) return badge.title;
    const base = finite(row.ddfPipelineValue) ? row.ddfPipelineValue : null;
    return base !== null
      ? `You set this player's value to ${overrideFmt(row.valueOverride)} (was ${overrideFmt(base)} from DDF Value). Reset on the Overrides tab.`
      : `You set this player's value to ${overrideFmt(row.valueOverride)}. Reset on the Overrides tab.`;
  }
  const teamSummary = deps => (deps && deps.teamSummary) || root.TradeValueTeamSummary || (typeof require === "function" ? require("./team-summary.js") : null);
  const unavailable = (status, reason) => ({status, reason});

  // Verdict: finder.js tradeFit on the market rows (fitFor), with which of its tests failed. Fit needs the Trade chart
  // average and the league's expected depth (fitContext returns null without them).
  function verdictRow(F, input, out, w) {
    if (!out.ready) return unavailable("not-ready", out.reason);
    if (!w.market) return unavailable("unavailable", STRINGS.tooFewCharts((input.chartKeys || []).length));
    const fitIn = input.fit || null;
    if (!fitIn || !fitIn.expected) return unavailable("unavailable", "Fit is not judged: the league's expected roster depth is not known here.");
    // tradeFit's lineup nets leave an unpriced player out, which would judge the deal as if that player were worth 0. So a
    // moving player without DDF Value or the Trade chart average means no verdict, with who is missing (kickers and
    // defenses are not evaluated and never block it). Like Compare's trade.js "incomplete" rule, but stricter: Compare
    // judges on any 3 charts that price every moving player, while the chart average needs every available chart, and
    // tradeFit can't judge on fewer without a new number.
    const missing = [];
    w.giveRows.concat(w.receiveRows).forEach(row => {
      if (!row || F.isNotEvaluated(row)) return;
      const v = row.values || {};
      const series = [[out.ourKey, "DDF Value"], [F.MARKET_KEY, MARKET_LABEL]].filter(([k]) => !finite(v[k])).map(([, label]) => label);
      if (series.length) missing.push({key: keyOf(row), name: row.name || keyOf(row), series});
    });
    if (missing.length) {
      const who = missing.map(m => `${m.name} has no ${m.series.join(" or ")} value`).join("; ");
      return {status: "incomplete", reason: `No verdict: ${who}, and a missing value is never counted as 0.`, missing};
    }
    const fit = F.tradeFit(w.sides, {shape: out.shape, expected: fitIn.expected, weights: fitIn.weights || {overall: 0},
      ourKey: out.ourKey, marketKey: F.MARKET_KEY, chartKeys: w.market, z: finite(fitIn.z) ? fitIn.z : F.FIT_Z});
    if (!fit) return unavailable("unavailable", STRINGS.tooFewCharts(w.market.length));
    const tests = {
      construction: {pass: fit.constructionOk, issues: (fit.myConstruction.issues || []).concat(fit.theirConstruction.issues || [])},
      yourValue: {pass: fit.yourValueOk, net: fit.us.net, starterDelta: fit.us.starterDelta},
      theirMarket: {pass: fit.theirOk, net: fit.them.net, tau: fit.them.tau},
      marketSupported: {pass: fit.marketSupported}
    };
    // Natural fit 1a (JEG-1324, now inside tradeFit as `natural`): each side's DDF Value (projections) must not fall.
    // pass is null when a side is not judged (a moving player has no projection), and a side not judged is not Natural,
    // so null counts as failed here too. Read from tradeFit, never recomputed.
    const nat = fit.natural || null;
    if (nat) {
      tests.yourProjections = {pass: nat.us.projections, net: nat.us.projNet};
      tests.theirProjections = {pass: nat.them.projections, net: nat.them.projNet};
    }
    const failed = ["construction", "yourValue", "theirMarket", "yourProjections", "theirProjections"]
      .filter(id => tests[id] && tests[id].pass !== true);
    return {status: "available", reason: null, label: fit.label, name: FIT_NAME[fit.label], text: F.fitText(fit), tests, failed,
      basis: "tradeFit", fit};
  }

  // Will they accept: the #1084 band when the reader has a profile for this manager, otherwise the finder's viability
  // label and the count of charts that have them winning or even (evaluateCombo, the search's own count).
  function acceptRow(F, input, out, w, verdict) {
    if (!out.ready) return unavailable("not-ready", out.reason);
    const appeal = input.appeal || null;
    if (appeal && APPEAL_BANDS.includes(appeal.band) && typeof appeal.likelihood === "string" && appeal.likelihood) {
      return {status: "available", reason: null, basis: "profile", band: appeal.band, likelihood: appeal.likelihood,
        why: Array.isArray(appeal.why) ? appeal.why.slice() : [],
        text: `${appeal.likelihood}: your own read of this manager from the Managers card, not a prediction.`};
    }
    const charts = (input.chartKeys || []).slice();
    if (!w.market) return {...unavailable("unavailable", STRINGS.tooFewCharts(charts.length)), basis: "viability"};
    const combo = F.evaluateCombo(w.giveRows, w.receiveRows, {ourKey: out.ourKey, chartKeys: charts, minCharts: Math.min(F.MIN_CHARTS, charts.length)});
    const chartsLine = `${combo.rivalOkCount} of ${combo.pricedCharts} charts have them winning or even.`;
    const fit = verdict && verdict.fit;
    const viability = fit ? F.viabilityLabel(fit, w.sides.mine.roster, w.sides.theirs.roster, w.sides.mine.leaving, w.sides.mine.arriving,
      out.shape, out.ourKey, w.market) : null;
    const name = viability ? VIABILITY_NAME[viability] || viability : null;
    return {status: "available", reason: null, basis: "viability", viability, viabilityName: name,
      charts: {even: combo.rivalOkCount, priced: combo.pricedCharts, available: charts.length}, heldCharts: (out.views.market.held || []).slice(),
      text: name ? `${name}. ${chartsLine}` : fit ? `No viability label: a roster check fails or your DDF Value edge is below 0. ${chartsLine}`
        : `Viability is not judged without a fit. ${chartsLine}`};
  }

  // Sell gap: each player in the deal, DDF Value against the Trade chart average (team-summary.js marketGaps, gap = DDF
  // Value minus the chart average), or #1105's league depth when every team passes its completeness check (gap = DDF
  // Value at the market level minus the DDF level). basis says which one is showing; a player either side cannot price
  // keeps the reason, never a 0.
  function sellGapRow(F, input, out, w, deps) {
    if (!out.ready) return unavailable("not-ready", out.reason);
    const moving = out.give.map(key => ({key, side: "give", row: w.mineByKey.get(key)}))
      .concat(out.receive.map(key => ({key, side: "receive", row: w.theirByKey.get(key)})));
    const depth = input.leagueDepth || null;
    const leagueOk = Boolean(depth && depth.check && depth.check.ok && typeof depth.gapOf === "function");
    const leagueReasons = depth && depth.check && !depth.check.ok ? (depth.check.reasons || []).slice() : [];
    if (leagueOk) {
      const players = moving.map(({key, side, row}) => {
        const g = depth.gapOf(key);
        const name = row ? row.name : key;
        if (!g || !finite(g.ours) || !finite(g.theirs) || !finite(g.gap)) return {key, side, name, status: "unpriced", reason: STRINGS.noSeriesValue("league-depth DDF Value")};
        // A lean is named only at or above the caller's floor (#1105's SELL_MIN_GAP), else by sign alone.
        const floor = finite(depth.floor) ? depth.floor : 0;
        return {key, side, status: "priced", ours: g.ours, theirs: g.theirs, gap: g.gap,
          direction: g.gap > 0 && g.gap >= floor ? "market-higher" : g.gap < 0 && -g.gap >= floor ? "ddf-higher" : "even", name};
      });
      return {status: "available", reason: null, basis: "league", label: "League depth: DDF Value at your league's market level against its DDF level",
        leagueReasons: [], floor: finite(depth.floor) ? depth.floor : null, heldCharts: [], players};
    }
    const base = {basis: "market", label: `Per player: DDF Value against the ${MARKET_LABEL}`, leagueReasons};
    if (!w.market) return {...unavailable("unavailable", STRINGS.marketChip((input.chartKeys || []).length)), ...base, players: []};
    const TS = teamSummary(deps);
    const rows = F.withChartAverage(moving.map(m => m.row), w.market);
    // The gap is marketGaps' number (every non-zero gap at floor 0); a lean is named only above team-summary.js's
    // NOISE_FLOOR, the rule the league page uses to list a player as under or overvalued (Q13 A).
    const all = TS.marketGaps(rows, 0);
    const listed = TS.marketGaps(rows, TS.NOISE_FLOOR);
    const byKey = new Map(all.under.concat(all.over).map(item => [item.key, item]));
    const lean = new Map(listed.under.map(item => [item.key, "ddf-higher"]).concat(listed.over.map(item => [item.key, "market-higher"])));
    const players = moving.map(({key, side, row}, i) => {
      const r = rows[i];
      const ddf = r.values ? r.values[out.ourKey] : null;
      const chart = r.values ? r.values[F.MARKET_KEY] : null;
      const name = row.name;
      if (F.isNotEvaluated(r)) return {key, side, name, status: "not-evaluated", reason: STRINGS.notEvaluated};
      if (!finite(ddf)) return {key, side, name, status: "unpriced", reason: STRINGS.noSeriesValue("DDF Value")};
      if (!finite(chart)) return {key, side, name, status: "unpriced", reason: STRINGS.noSeriesValue(MARKET_LABEL)};
      const item = byKey.get(key);
      return {key, side, name, status: "priced", ddf, market: chart, gap: item ? item.gap : 0, direction: lean.get(key) || "even"};
    });
    return {status: "available", reason: null, ...base, floor: TS.NOISE_FLOOR, heldCharts: (out.views.market.held || []).slice(), players};
  }

  // Data labels: per team, every player on its roster before the trade (each player once), in the JEG-1221 words. Kinds:
  // "single-source" (GL-03 "◐ 1 source"), "estimated" ("≈ estimated", per chart the market view reads), "not-evaluated"
  // (S8), "no-value-this-week" (S9: no engine row, or no value in any view), "no-series-value" (S10), "override".
  function dataLabelsRow(F, input, out, w, deps) {
    const sideOf = who => {
      const raw = (input[who] && input[who].rows) || [];
      const entries = (input[who] && input[who].entries) || [];
      const rows = raw.filter((row, i) => raw.findIndex(other => keyOf(other) === keyOf(row)) === i);   // each player once
      const have = new Set(rows.map(keyOf));
      const labels = [];
      const views = VIEWS.filter(v => out.views[v.id].status === "available").map(v => ({...v, valueKey: out.views[v.id].valueKey}));
      // The market view's own charts, ready deal or not: before both sides are picked w is null, and reading the chart
      // average off w would label every priced player "No Trade chart average value".
      const charts = out.views.market.status === "available" ? out.views.market.chartKeys : null;
      const shown = rows.map(row => (charts ? F.withChartAverage([row], charts)[0] : row));
      shown.forEach(row => {
        const key = keyOf(row);
        const name = row.name || key;
        const v = row.values || {};
        if (F.isNotEvaluated(row)) { labels.push({key, name, kind: "not-evaluated", text: STRINGS.notEvaluated}); return; }
        const priced = views.filter(view => finite(v[view.valueKey]));
        if (!priced.length) { labels.push({key, name, kind: "no-value-this-week", text: STRINGS.noValueThisWeek}); return; }
        views.filter(view => !finite(v[view.valueKey])).forEach(view =>
          labels.push({key, name, kind: "no-series-value", series: view.label, text: STRINGS.noSeriesValue(view.label)}));
        if (row.ddfLowConfidence && finite(v[out.ourKey])) {
          const count = finite(row.ddfCount) ? row.ddfCount : 1;
          labels.push({key, name, kind: "single-source", tag: `◐ ${count} source${count === 1 ? "" : "s"}`, text: row.ddfConfidenceNote || LOW_CONFIDENCE_NOTE});
        }
        const est = row.estimated || {};
        [out.ourKey].concat(charts || []).forEach(series => {
          const reason = est[series];
          if (typeof reason === "string" && reason.trim() && finite(v[series])) labels.push({key, name, kind: "estimated", series, tag: "≈ estimated", text: reason});
        });
        if (row.valueOverride !== null && row.valueOverride !== undefined) labels.push({key, name, kind: "override", text: overrideText(row, deps)});
      });
      entries.filter((entry, i) => !have.has(String(entry.key)) && entries.findIndex(e => String(e.key) === String(entry.key)) === i).forEach(entry => labels.push(F.isNotEvaluated(entry)
        ? {key: String(entry.key), name: entry.name || String(entry.key), kind: "not-evaluated", text: STRINGS.notEvaluated}
        : {key: String(entry.key), name: entry.name || String(entry.key), kind: "no-value-this-week", text: STRINGS.noValueThisWeek}));
      return labels;
    };
    return {status: "available", reason: null, mine: sideOf("mine"), theirs: sideOf("theirs")};
  }

  // Context line: scoring, teams, superflex, basis, bench level, week. A part the caller does not know is left out, and
  // listed in missing, never guessed.
  function contextRow(input) {
    const known = v => v !== undefined && v !== null;
    const c = input.context || {};
    const shape = input.shape || {};
    const parts = [];
    const missing = [];
    if (SCORING_NAME[c.scoring]) parts.push(SCORING_NAME[c.scoring]); else missing.push("scoring");
    const teams = known(c.teams) && finite(Number(c.teams)) && Number(c.teams) > 0 ? Number(c.teams) : null;
    const week = known(c.week) && finite(Number(c.week)) && Number(c.week) > 0 ? Number(c.week) : null;
    if (teams !== null) parts.push(`${teams} teams`); else missing.push("teams");
    const sf = known(c.superflex) ? Boolean(c.superflex) : input.shape ? Number(shape.SUPERFLEX) > 0 : null;
    if (sf === null) missing.push("superflex"); else parts.push(sf ? "Superflex" : "1QB");
    const mode = c.basis && c.basis.mode;
    if (mode === "default") parts.push("DDF Value basis"); else if (mode === "single" || mode === "blend") parts.push("Your basis, not ours");
    else missing.push("basis");
    if (c.benchLevel === "league") parts.push("Bench from your league's rosters"); else if (c.benchLevel === "modeled") parts.push("Standard bench");
    else missing.push("bench level");
    if (week !== null) parts.push(`Week ${week}`); else missing.push("week");
    return {status: "available", reason: null, scoring: c.scoring || null, teams,
      superflex: sf, basis: mode || null, benchLevel: c.benchLevel || null, week,
      missing, text: parts.join(" · ")};
  }

  // w: the built sides (null when the readout is not ready). The verdict and acceptance read the market rows, as
  // finder.js fitFor and league.js do (give and receive rows carry the chart average too).
  function secondHalf(F, input, out, built, deps) {
    let w = null;
    if (built) {
      const rows = built.market ? built.rowsFor("market") : null;
      const pick = list => new Map(list.map(row => [keyOf(row), row]));
      const mineM = rows ? pick(rows.mine) : null;
      const theirM = rows ? pick(rows.theirs) : null;
      const giveRows = out.give.map(key => (mineM ? mineM.get(key) : built.mineByKey.get(key)));
      const receiveRows = out.receive.map(key => (theirM ? theirM.get(key) : built.theirByKey.get(key)));
      w = {...built, giveRows, receiveRows,
        sides: rows ? {mine: {roster: rows.mine, leaving: giveRows, arriving: receiveRows}, theirs: {roster: rows.theirs, leaving: receiveRows, arriving: giveRows}} : null};
    }
    const ready = w || {market: null, mineByKey: new Map(), theirByKey: new Map()};
    const verdict = verdictRow(F, input, out, ready);
    return {verdict, accept: acceptRow(F, input, out, ready, verdict), sellGap: sellGapRow(F, input, out, ready, deps),
      dataLabels: dataLabelsRow(F, input, out, w, deps), context: contextRow(input)};
  }
  // Plain copy for golden fixtures and cross-route comparison (the fit object stays out; its numbers are in tests).
  function rowsSummary(rows) {
    const {fit, ...verdict} = rows.verdict;
    void fit;
    return {verdict, accept: rows.accept, sellGap: rows.sellGap, dataLabels: rows.dataLabels, context: rows.context};
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


  // JEG-1323: the second-half rows, drawn once for every page, in the spec's order. Each row says its value or why not.
  function renderRows(readout, deps) {
    const doc = (deps && deps.document) || root.document;
    const rows = readout.rows;
    const wrap = doc.createElement("div");
    wrap.className = "v2-readout-rows";
    const row = (id, title, status, lines) => {
      const box = doc.createElement("div");
      box.className = "v2-readout-row";
      box.dataset.row = id;
      box.dataset.status = status;
      const h = doc.createElement("p");
      h.className = "v2-readout-row-title";
      const b = doc.createElement("b");
      b.textContent = title;
      h.appendChild(b);
      box.appendChild(h);
      lines.filter(Boolean).forEach(line => {
        const p = doc.createElement("p");
        p.className = "v2-meta";
        if (typeof line === "string") p.textContent = line;
        else { p.textContent = line.text; Object.entries(line.data || {}).forEach(([k, v]) => { p.dataset[k] = v; }); }
        box.appendChild(p);
      });
      wrap.appendChild(box);
    };
    const heldLine = list => (list && list.length ? `Held this week (data check), not in the ${MARKET_LABEL}: ${list.map(k => CHART_NAMES[k] || k).join(", ")}.` : null);
    const v = rows.verdict;
    row("verdict", "Verdict", v.status, v.status === "available" ? [{text: v.text, data: {fit: v.label}}] : [v.reason]);
    const a = rows.accept;
    row("accept", "Will they accept", a.status, a.status === "available"
      ? [{text: a.text, data: {basis: a.basis}}].concat(a.basis === "profile" ? a.why : [heldLine(a.heldCharts)]) : [a.reason]);
    const g = rows.sellGap;
    const gapLine = p => {
      const who = p.side === "give" ? "you send" : "you get";
      if (p.status !== "priced") return {text: `${p.name} (${who}): ${p.reason}`, data: {player: p.key, status: p.status}};
      const size = Math.abs(p.gap).toFixed(1);
      const pair = g.basis === "league" ? `market level ${p.theirs.toFixed(1)}, DDF level ${p.ours.toFixed(1)}`
        : `${MARKET_LABEL} ${p.market.toFixed(1)}, DDF Value ${p.ddf.toFixed(1)}`;
      const lean = p.direction === "market-higher" ? `the market prices them ${size} higher` : p.direction === "ddf-higher" ? `DDF Value prices them ${size} higher`
        : g.floor !== null ? `within ${g.floor.toFixed(1)} points, not a gap` : "even";
      return {text: `${p.name} (${who}): ${pair}; ${lean}.`, data: {player: p.key, direction: p.direction}};
    };
    row("sell-gap", "Sell gap", g.status, g.status === "available"
      ? [{text: g.label, data: {basis: g.basis}}].concat(g.players.map(gapLine), [heldLine(g.heldCharts)])
        .concat(g.leagueReasons.length ? [`League depth not used: ${g.leagueReasons.join("; ")}.`] : []) : [g.reason]);
    const d = rows.dataLabels;
    const labelLine = who => item => ({text: `${who}, ${item.name}: ${item.tag ? `${item.tag}: ` : ""}${item.text}`, data: {player: item.key, kind: item.kind}});
    row("data-labels", "Data labels", d.status, d.mine.map(labelLine("Your team")).concat(d.theirs.map(labelLine("Their team")))
      .concat(d.mine.length || d.theirs.length ? [] : ["Every player here has a full value."]));
    const c = rows.context;
    row("context", "Context", c.status, [c.text || "League settings are not known here."]);
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
    // JEG-1323: the context line from common.league, common.valuation.basis and pricing.mode; the week is env.week.
    const league = (ctx.common && ctx.common.league) || {};
    const basis = ctx.common && ctx.common.valuation ? ctx.common.valuation.basis : null;
    const pricing = ctx.pricing || null;
    const roster = league.roster || null;
    const contextLine = {scoring: league.scoring, teams: league.teams, basis: basis || null,
      superflex: roster && roster.SUPERFLEX !== undefined ? Number(roster.SUPERFLEX) > 0 : undefined,
      benchLevel: pricing ? (pricing.mode === "league" ? "league" : "modeled") : e.benchLevel, week: e.week};
    return {shape: e.shape, ourKey: e.ourKey, chartKeys: e.chartKeys, sourceInfo, mine: side(teams.mine), theirs: side(partner),
      fit: e.fit || null, appeal: e.appeal || null, leagueDepth: e.leagueDepth || null, context: contextLine,
      give: (ctx.deal && ctx.deal.give) || [], receive: (ctx.deal && ctx.deal.get) || [],
      contextKey: TC && TC.cacheKey ? TC.cacheKey(ctx, "readout") : null};
  }

  const api = {VERSION, VIEWS, build, summary, renderSide, renderRows, sourceStatus, inputFromContext, STRINGS, FIT_NAME, VIABILITY_NAME};
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.TradeValueReadout = api;
})(typeof window !== "undefined" ? window : globalThis);
