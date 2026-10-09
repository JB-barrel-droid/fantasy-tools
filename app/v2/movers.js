// Trade Value v2 — Risers & fallers and Δ prior week (Figma frames 05 / 06, frame 22).
//
// Pure functions, no DOM. The engine prices the prior week itself
// (TradeValueCurveControls.getPriorWeek(series): that series' saved inputs from
// the week before the one served now, recomputed at the reader's current
// league, roster, bench share and weights). The only arithmetic here is one
// difference per player for one exact series:
//
//   Δ = current value − prior-week value        (same series, same setting)
//
// Never across two series. A player without a prior value has no Δ ("Δ —" plus
// a reason), never a 0 and never the current value standing in for it.
(function (root) {
  "use strict";

  // Series with saved weeks, in picker order: the published charts (Indexed)
  // and the two projection sources the engine recomputes. ESPN is the common
  // scale and has no recomputed prior week (engine reason, risk HISTORY-ESPN-PRIOR).
  const SERIES = ["fantasycalc", "usatoday", "fantasypros", "cbs", "cbsros", "razzball", "espn"];

  const finite = value => typeof value === "number" && Number.isFinite(value);

  // One player's Δ for one series. prior: the getPriorWeek result.
  function deltaFor(current, prior, playerKey) {
    if (!prior || !prior.available) return {delta: null, reason: (prior && prior.reason) || "no prior week"};
    if (!finite(current)) return {delta: null, reason: "no value this week"};
    const before = prior.values ? prior.values[playerKey] : undefined;
    if (!finite(before)) return {delta: null, reason: `not priced in Week ${prior.priorWeek}`};
    return {delta: current - before, before, reason: null};
  }

  // rows: engine rows (getRows). series: one key. prior: getPriorWeek(series).
  function buildMovers(rows, series, prior) {
    if (!prior || !prior.available) {
      return {series, available: false, reason: (prior && prior.reason) || "no prior week",
        risers: [], fallers: [], compared: 0, noPrior: 0, noCurrent: 0, unchanged: 0};
    }
    const movers = [];
    let noPrior = 0;
    let noCurrent = 0;
    let unchanged = 0;
    rows.forEach((row, index) => {
      const current = row.values ? row.values[series] : null;
      const d = deltaFor(current, prior, String(row.player_key));
      if (d.delta === null) {
        if (!finite(current)) noCurrent += 1;
        else noPrior += 1;
        return;
      }
      const item = {row, order: index + 1, current, before: d.before, delta: d.delta};
      if (Math.abs(d.delta) < 0.05) unchanged += 1;   // shows as 0.0: neither a riser nor a faller
      else movers.push(item);
    });
    const risers = movers.filter(m => m.delta > 0).sort((a, b) => b.delta - a.delta || a.order - b.order);
    const fallers = movers.filter(m => m.delta < 0).sort((a, b) => a.delta - b.delta || a.order - b.order);
    return {series, available: true, currentWeek: prior.currentWeek, priorWeek: prior.priorWeek,
      risers, fallers, compared: movers.length + unchanged, noPrior, noCurrent, unchanged};
  }

  const api = {SERIES, deltaFor, buildMovers};
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.TradeValueMovers = api;
})(typeof window !== "undefined" ? window : globalThis);
