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

  const OUR_KEYS = ["ddf_value", "espn", "cbsros", "razzball"];
  const OUR_KEY = OUR_KEYS[0];   // default: DDF Value
  const OUR_NAMES = {ddf_value: "DDF Value", espn: "ESPN projections", cbsros: "CBS rest-of-season projections", razzball: "Razzball projections"};
  const OUR_SHORT = {ddf_value: "DDF Value", espn: "ESPN projections", cbsros: "CBS rest of season", razzball: "Razzball projections"};
  const CHART_KEYS = ["usatoday", "fantasycalc", "fantasypros", "cbs"];
  const CHART_NAMES = {usatoday: "USA Today", fantasycalc: "FantasyCalc", fantasypros: "FantasyPros", cbs: "CBS Sports"};

  const finite = value => typeof value === "number" && Number.isFinite(value);

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
          cells[chart] = {value: null, gap: null, reason: `Not on ${CHART_NAMES[chart] || chart}'s chart`};
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
      players.push({row, order: index + 1, ours, cells, bestSell, bestBuy});
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

  const api = {OUR_KEY, OUR_KEYS, OUR_NAMES, OUR_SHORT, CHART_KEYS, CHART_NAMES, buildTargets, chartsToCompare, ourChoices};
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.TradeValueTargets = api;
})(typeof window !== "undefined" ? window : globalThis);
