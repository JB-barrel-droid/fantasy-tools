// JEG-1322: pure listing filters for the your-team finder's existing ranked groups.
// Preparatory only: finder.js/build wiring and persistence belong to the integration owner.
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory(
    () => require("./discovery-controls.js"), () => require("./opportunities.js"), () => require("./finder.js"));
  else root.TradeValuePairDiscoveryFilters = factory(
    () => root.TradeValueDiscoveryControls, () => root.TradeValueOpportunities, () => root.TradeValueFinder);
})(typeof window !== "undefined" ? window : globalThis, function (controls, opportunities, finder) {
  "use strict";

  // record is discovery-controls.js's shared record, not a workspace or its ui.
  // fitOf(group) returns the existing tradeFit of group.best (or null when unjudged).
  // viableOf(group) returns the existing viability label (or null). As on today's
  // finder page, viableOnly has no effect when no viability evaluator is available.
  // Filters select whole groups by their best package; alternatives never promote a
  // group or change its contents. Apply before the page's core cap and pagination.
  function filterGroups(groups, record, fitOf, viableOf) {
    const listing = controls().listingOf(record);
    const filters = {...listing.filters, opponent: "all"}; // This route has one partner.
    const needsFit = filters.fit !== "all" || listing.hideForce;
    const rows = groups.map(group => {
      const fit = needsFit && fitOf ? fitOf(group) : null;
      return {group, overall: fit ? fit.label : null,
        edge: group.best.edge, rivalOkCount: group.best.rivalOkCount};
    });
    const selected = opportunities().filterRows(rows, filters, listing.hideForce).map(row => row.group);
    return listing.viableOnly && viableOf ? finder().viableGroups(selected, viableOf) : selected;
  }

  return {filterGroups};
});
