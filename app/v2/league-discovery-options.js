// JEG-1321 preparation: shared discovery controls -> one league pairing's finder options.
// Pure and deliberately not loaded by the page until the league/opportunities owner wires it in.
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory(require("./discovery-controls.js"));
  else root.TradeValueLeagueDiscoveryOptions = factory(root.TradeValueDiscoveryControls);
})(typeof window !== "undefined" ? window : globalThis, function (controls) {
  "use strict";

  // record is DiscoveryControls.fromWorkspace(ws.ui). ctx carries the existing pairing's
  // pricing/shape/charts; rows are the full priced rosters, including bench players.
  // Keep Infinity: opportunities must rank/filter all candidates before paginating.
  function finderOptions(record, ctx, mine, theirs) {
    const search = controls.searchOf(record);
    return {chartKeys: ctx.charts, maxSize: search.maxSize, limit: Infinity,
      guardrails: {...search.guardrails, shape: ctx.shape, mine, theirs, chartKeys: ctx.charts, ourKey: "ddf_value"},
      sanity: ctx.shape ? {shape: ctx.shape, mine, theirs, keepMine: search.keepMine, keepTheirs: search.keepTheirs} : null};
  }

  return {finderOptions};
});
