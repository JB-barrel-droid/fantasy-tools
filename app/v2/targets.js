// Trade Value v2 — Trade targets (Figma frames 03 / 04).
//
// Pure functions, no DOM: given the engine's own rows (TradeValueCurveControls
// .getRows()), pair our value with each published chart's value for the same
// player. The only arithmetic is one difference per player per chart:
//
//   gap = chart value − our value
//
// Both series are on the same trade-value point scale for the user's league
// (the published charts are indexed to our curve by the engine). A positive gap
// means the chart pays more than we would (a sell target); a negative gap means
// it pays less (a buy target). VORP vs waivers is a different unit and is never
// paired with anything here. A missing value on either side gives no gap
// (null plus a reason), never zero.
//
// GAP-025 (Jeremy, 2026-10-07: "Yes, use 0"): a player ESPN lists but projects
// at 0 (injured/out) has an ESPN · DDA value of 0.0 in the engine rows, not a
// missing one, so a chart that still pays for him is an ordinary sell target
// with gap = chart value. A player with no ESPN row is still missing.
//
// Our value (Jeremy, 2026-10-08, JEG-455): DDF Value (the engine's ddf_value
// series) is our value and the default. ESPN, CBS rest-of-season and Razzball
// projections stay as alternatives. Each is one engine series, read as is.
//
// Waiver line (Jeremy, 2026-10-07: "It's illogical that 0 value players would
// be on a buy list."). Every series here is value above waivers for the user's
// league: 0 means at or below that series' waiver line. A chart value at or
// below 0 is shown, but it is never a buy (or sell) target and gets no gap.
(function (root) {
  "use strict";

  const OUR_KEYS = ["ddf_value", "ddf_value_charts", "ddf_value_projections", "espn", "cbsros", "razzball"];
  const OUR_KEY = OUR_KEYS[0];   // default: DDF Value
  const OUR_NAMES = {ddf_value: "DDF Value", ddf_value_charts: "DDF Value · trade charts", ddf_value_projections: "DDF Value · projections", espn: "ESPN projections", cbsros: "CBS rest-of-season projections", razzball: "Razzball projections"};
  const OUR_SHORT = {ddf_value: "DDF Value", ddf_value_charts: "DDF Value · trade charts", ddf_value_projections: "DDF Value · projections", espn: "ESPN projections", cbsros: "CBS rest of season", razzball: "Razzball projections"};
  const CHART_KEYS = ["usatoday", "fantasycalc", "fantasypros", "cbs"];
  const CHART_NAMES = {usatoday: "USA Today", fantasycalc: "FantasyCalc", fantasypros: "FantasyPros", cbs: "CBS Sports"};

  const finite = value => typeof value === "number" && Number.isFinite(value);

  // JEG-504 (Jeremy, 2026-10-09, TT-09): the mean of the compared charts' rescaled values
  // that price the player, beside our value. A finite 0 counts (at or below that chart's
  // waiver line); a null is left out and counted in `left`. diff = our value − the average,
  // and equal says the two match to one decimal as shown, so the page shows a note instead
  // of a duplicate number. No chart prices the player: value null, no diff.
  function marketAverage(ours, cells) {
    const values = Object.values(cells).map(cell => cell.value).filter(finite);
    const left = Object.keys(cells).length - values.length;
    if (!values.length) return {value: null, count: 0, left, diff: null, equal: false};
    const value = values.reduce((sum, v) => sum + v, 0) / values.length;
    const diff = ours - value;
    return {value, count: values.length, left, diff, equal: ours.toFixed(1) === value.toFixed(1)};
  }

  // charts: the chart keys to compare (already filtered for availability and week).
  // opts.ours: which engine series is our value (default DDF Value).
  function buildTargets(rows, charts, opts) {
    const ourKey = (opts && opts.ours) || OUR_KEY;
    if (!OUR_KEYS.includes(ourKey)) throw new Error(`not an our-value series: ${ourKey}`);
    const players = [];
    let omittedNoOurs = 0;
    let atWaiverCells = 0;
    rows.forEach((row, index) => {
      const ours = row.values ? row.values[ourKey] : null;
      if (!finite(ours)) {
        omittedNoOurs += 1;
        return;
      }
      const cells = {};
      let bestSell = null;
      let bestBuy = null;
      charts.forEach(chart => {
        const value = row.values[chart];
        if (!finite(value)) {
          // JEG-541: the engine's own reason first (after JEG-508 a chart is null only when the engine
          // says why, e.g. "Not enough shared players to index"), then the generic line.
          const own = row.missingReasons ? row.missingReasons[chart] : null;
          cells[chart] = {value: null, gap: null,
            reason: typeof own === "string" && own.trim() ? own : `Not on ${CHART_NAMES[chart] || chart}'s chart`};
          return;
        }
        if (value <= 0) {
          atWaiverCells += 1;
          cells[chart] = {value, gap: null, atWaiver: true, reason: `At ${CHART_NAMES[chart] || chart}'s waiver line for your league`};
          return;
        }
        const gap = value - ours;
        cells[chart] = {value, gap, reason: null};
        if (gap > 0 && (!bestSell || gap > bestSell.gap)) bestSell = {chart, gap};
        if (gap < 0 && (!bestBuy || gap < bestBuy.gap)) bestBuy = {chart, gap};
      });
      players.push({row, order: index + 1, ours, cells, bestSell, bestBuy, market: marketAverage(ours, cells)});
    });
    const sell = players.filter(p => p.bestSell)
      .sort((a, b) => b.bestSell.gap - a.bestSell.gap || a.order - b.order);
    const buy = players.filter(p => p.bestBuy)
      .sort((a, b) => a.bestBuy.gap - b.bestBuy.gap || a.order - b.order);
    return {ours: ourKey, sell, buy, compared: players.length, omittedNoOurs, atWaiverCells};
  }

  // Chart columns to compare: every available published chart (JEG-459). A
  // chart that has not published this week yet is still compared on its
  // latest week and listed in `prior`, so the page can badge it.
  function chartsToCompare(sourceInfo, opts) {
    const byKey = Object.fromEntries((sourceInfo || []).map(item => [item.key, item]));
    const only = opts && opts.only;
    const used = [];
    const skipped = [];
    const prior = [];
    CHART_KEYS.forEach(key => {
      if (only && only !== key) return;
      const item = byKey[key];
      if (!item || !item.available) skipped.push({key, reason: item && item.paused ? "waiting on fresh inputs" : "not available for this league"});
      else used.push(key);
      if (item && item.available && item.stale) prior.push(key);
    });
    return {used, skipped, prior};
  }

  // Our-value choices at this league setting: unavailable ones carry a reason.
  function ourChoices(sourceInfo) {
    const byKey = Object.fromEntries((sourceInfo || []).map(item => [item.key, item]));
    return OUR_KEYS.map(key => {
      const item = byKey[key];
      const available = Boolean(item && item.available);
      return {key, available, reason: available ? null
        : item && item.paused ? "waiting on fresh inputs" : "not available for this league"};
    });
  }

  // ---------- Check 2: potential positional weight inflation (JEG-476, JEG-489) ----------
  // Does the market spend its value budget on a position (or a position's starters / bench) in
  // different proportions than DDF Value does? Raw totals cannot say: a per-player median sits under
  // the mean and one chart's whole scale can sit 20% under another's, which read as "underweighted"
  // everywhere. So each group is compared by SHARE, over the same players on both sides:
  //
  //   gap = (group share of the market total) / (group share of the DDF Value total) - 1
  //
  // Market = the consensus (median of the compared charts that price the player, 2+ charts) or one
  // chart. A positive gap says the market overweights the group (sell it); negative, underweights it (buy).
  const WEIGHT_POSITIONS = ["QB", "RB", "WR", "TE"];
  const WEIGHT_TIERS = ["starter", "bench"];
  const WEIGHT_SIGNAL = 0.10;       // +/-10%: sell / buy this group
  const WEIGHT_MIN_SHOW = 3;        // fewer players than this: no number
  const WEIGHT_MIN_HEADLINE = 8;    // fewer players than this: never named in the headline

  function median(values) {
    const sorted = values.slice().sort((a, b) => a - b);
    const mid = sorted.length >> 1;
    return sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
  }

  function weightSignal(gap) {
    if (!finite(gap)) return null;
    return gap >= WEIGHT_SIGNAL ? "sell" : gap <= -WEIGHT_SIGNAL ? "buy" : "fair";
  }

  // rows: engine rows (all positions). charts: chart keys to compare. opts.ours: the DDF Value key.
  function weightCheck(rows, charts, opts) {
    const oursKey = (opts && opts.ours) || OUR_KEY;
    const columns = ["consensus"].concat(charts);
    const marketOf = (row, column) => {
      if (column !== "consensus") return finite(row.values[column]) ? row.values[column] : null;
      const priced = charts.map(chart => row.values[chart]).filter(finite);
      return priced.length >= 2 ? median(priced) : null;
    };
    const groupKeys = [];
    WEIGHT_POSITIONS.forEach(pos => {
      groupKeys.push({key: pos, pos, tier: null});
      WEIGHT_TIERS.forEach(tier => groupKeys.push({key: `${pos}|${tier}`, pos, tier}));
    });
    const inGroup = (row, group) => row.pos === group.pos && (!group.tier || row.ddfTier === group.tier);
    const pairs = {};
    columns.forEach(column => {
      pairs[column] = rows.filter(row => row.values)
        .map(row => ({row, ours: row.values[oursKey], market: marketOf(row, column)}))
        .filter(p => finite(p.ours) && finite(p.market) && WEIGHT_POSITIONS.includes(p.row.pos));
    });
    const sum = (list, field) => list.reduce((total, p) => total + p[field], 0);
    const groups = groupKeys.map(group => {
      const byColumn = {};
      columns.forEach(column => {
        const all = pairs[column];
        const members = all.filter(p => inGroup(p.row, group));
        const totalOurs = sum(all, "ours");
        const totalMarket = sum(all, "market");
        const ours = sum(members, "ours");
        const market = sum(members, "market");
        const shown = members.length >= WEIGHT_MIN_SHOW && ours > 0 && totalOurs > 0 && totalMarket > 0;
        const gap = shown ? (market / totalMarket) / (ours / totalOurs) - 1 : null;
        byColumn[column] = {n: members.length, gap, signal: weightSignal(gap)};
      });
      return {...group, n: byColumn.consensus.n, cells: byColumn, consensus: byColumn.consensus};
    });
    // Players behind a group, sorted by the group's signal: a sell group lists the biggest overpay first,
    // a buy group the biggest underpay first, a fairly priced group the largest gap either way.
    const playersOf = group => {
      const signal = group.consensus.signal;
      const list = pairs.consensus.filter(p => inGroup(p.row, group)).map(p => ({
        row: p.row, ours: p.ours, market: p.market, gap: p.market - p.ours,
        charts: Object.fromEntries(charts.map(chart => [chart, finite(p.row.values[chart]) ? p.row.values[chart] : null]))}));
      list.sort((a, b) => signal === "buy" ? a.gap - b.gap : signal === "sell" ? b.gap - a.gap : Math.abs(b.gap) - Math.abs(a.gap));
      return list;
    };
    // Headline: the biggest consensus gaps among groups large enough to name (8+ players).
    const nameable = groups.filter(g => g.consensus.n >= WEIGHT_MIN_HEADLINE && finite(g.consensus.gap));
    const over = nameable.filter(g => g.consensus.gap > 0).sort((a, b) => b.consensus.gap - a.consensus.gap)[0] || null;
    const under = nameable.filter(g => g.consensus.gap < 0).sort((a, b) => a.consensus.gap - b.consensus.gap)[0] || null;
    const biggest = nameable.slice().sort((a, b) => Math.abs(b.consensus.gap) - Math.abs(a.consensus.gap))[0] || null;
    return {ours: oursKey, columns, groups, playersOf, headline: {over, under, biggest}, compared: pairs.consensus.length};
  }

  const api = {OUR_KEY, OUR_KEYS, OUR_NAMES, OUR_SHORT, CHART_KEYS, CHART_NAMES, buildTargets, chartsToCompare, ourChoices,
    weightCheck, weightSignal, WEIGHT_POSITIONS, WEIGHT_TIERS, WEIGHT_SIGNAL, WEIGHT_MIN_SHOW, WEIGHT_MIN_HEADLINE};
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.TradeValueTargets = api;
})(typeof window !== "undefined" ? window : globalThis);
