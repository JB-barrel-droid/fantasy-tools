// Trade Value v2 — Compare a trade (Figma frames 07 / 08).
//
// Pure functions, no DOM: given the engine's own rows (TradeValueCurveControls
// .getAllRows()) for the players on each side and the series to compare, give
// one row per series:
//
//   net = sum(receive) − sum(give)        for that exact series only
//
// Frame 22 rule: each row is one exact series (publisher × method); there is no
// blended score across series and no overall win/lose verdict. A player with
// no value in a series makes that series' row incomplete: no sums, no net,
// "—" plus a reason, never a 0 standing in for the missing value. A real 0
// (at or below that series' waiver line) is a value and counts.
(function (root) {
  "use strict";

  const finite = value => typeof value === "number" && Number.isFinite(value);

  // giveRows / receiveRows: the engine rows of the players on each side (a
  // player the engine has no row for comes in with empty values, so it is
  // missing everywhere). series: series keys to compare, in display order.
  function compareTrade(giveRows, receiveRows, series) {
    const rows = series.map(key => {
      const missing = [];
      let giveSum = 0;
      let receiveSum = 0;
      giveRows.forEach(row => {
        const value = row.values ? row.values[key] : null;
        if (finite(value)) giveSum += value;
        else missing.push({row, side: "give"});
      });
      receiveRows.forEach(row => {
        const value = row.values ? row.values[key] : null;
        if (finite(value)) receiveSum += value;
        else missing.push({row, side: "receive"});
      });
      if (missing.length) return {key, give: null, receive: null, net: null, missing};
      return {key, give: giveSum, receive: receiveSum, net: receiveSum - giveSum, missing};
    });
    return {rows};
  }

  // One side's total in one series (frame 07: "<series> total" under each side).
  // Any player without a value makes the total incomplete: null plus who is missing.
  function sideTotal(rows, key) {
    const missing = rows.filter(row => !finite(row.values ? row.values[key] : null));
    if (!rows.length || missing.length) return {key, total: null, missing};
    return {key, total: rows.reduce((sum, row) => sum + row.values[key], 0), missing};
  }

  // Frame 22 #15, the trade story, read only from complete rows (no new numbers):
  //   contrast  one publisher's DDA and Indexed nets point opposite ways (same week);
  //   agree     every complete row points the same way;
  //   split     complete rows point different ways (different publishers);
  //   incomplete no row is complete.
  // A net that shows as 0.0 points neither way. meta(key) -> {publisher, method, week}.
  function tradeStory(rows, meta) {
    const complete = rows.filter(row => row.net !== null);
    if (!rows.length) return {kind: null};
    if (!complete.length) return {kind: "incomplete"};
    const sign = row => (Math.abs(row.net) < 0.05 ? 0 : row.net > 0 ? 1 : -1);
    const byPublisher = new Map();
    complete.forEach(row => {
      const m = meta(row.key);
      if (m.method === "vorp") return;
      if (!byPublisher.has(m.publisher)) byPublisher.set(m.publisher, {});
      byPublisher.get(m.publisher)[m.method] = {row, week: m.week};
    });
    for (const [publisher, pair] of byPublisher) {
      if (!pair.dda || !pair.indexed || pair.dda.week !== pair.indexed.week) continue;
      const a = sign(pair.dda.row);
      const b = sign(pair.indexed.row);
      if (a && b && a !== b) return {kind: "contrast", publisher, dda: pair.dda.row, indexed: pair.indexed.row};
    }
    const signs = complete.map(sign);
    const up = signs.filter(s => s > 0).length;
    const down = signs.filter(s => s < 0).length;
    const even = signs.length - up - down;
    if (complete.length < 2) return {kind: "single", up, down, even, total: complete.length};
    if ((up && !down && !even) || (down && !up && !even) || (even && !up && !down)) {
      return {kind: "agree", up, down, even, total: complete.length};
    }
    return {kind: "split", up, down, even, total: complete.length};
  }

  const api = {compareTrade, sideTotal, tradeStory};
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.TradeValueTrade = api;
})(typeof window !== "undefined" ? window : globalThis);
