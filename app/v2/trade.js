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

  const api = {compareTrade};
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.TradeValueTrade = api;
})(typeof window !== "undefined" ? window : globalThis);
