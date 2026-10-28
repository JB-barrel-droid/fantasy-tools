/* JEG-1212: source taxonomy and comparison-only views. No engine or trade rule reads this module. */
(function (root) {
  "use strict";
  const PUBLISHED = Object.freeze(["usatoday", "fantasypros", "cbs"]);
  const OBSERVED = Object.freeze(["fantasycalc"]);
  const PROJECTIONS = Object.freeze(["espn", "cbsros", "razzball"]);
  const CATEGORIES = Object.freeze([
    Object.freeze({id: "projections", label: "Projections", keys: PROJECTIONS}),
    Object.freeze({id: "published", label: "Published charts", keys: PUBLISHED}),
    Object.freeze({id: "observed", label: "Observed-trade estimates", keys: OBSERVED})
  ]);
  const PUBLISHED_RECIPE = Object.freeze({role: "comparison_only", scale: "indexed",
    aggregation: "equal_weight_mean", coverage: "all_inputs_required"});
  const OBSERVED_RECIPE = Object.freeze({role: "comparison_only", scale: "indexed",
    aggregation: "single_source", coverage: "source_required"});
  const VIEWS = Object.freeze([
    Object.freeze({id: "published_chart_average", label: "Published chart average", keys: PUBLISHED, recipe: PUBLISHED_RECIPE}),
    Object.freeze({id: "observed_trade_estimate", label: "Observed-trade estimate", keys: OBSERVED, recipe: OBSERVED_RECIPE})
  ]);
  const finite = n => typeof n === "number" && Number.isFinite(n);
  const categoryOf = key => CATEGORIES.find(c => c.keys.includes(String(key).replace(/_(adjusted|vorp)$/, ""))) || null;

  // The page's chart values are the engine's Indexed series. Numeric zero
  // contributes; null does not. Estimates remain with explicit ancestry.
  function read(row, viewId, availableKeys) {
    const view = VIEWS.find(v => v.id === viewId);
    if (!view) throw new Error(`Unknown comparison view: ${viewId}`);
    const available = new Set(availableKeys || []);
    const inputs = view.keys.map(key => {
      const value = row && row.values && row.values[key];
      const estimated = Boolean(row && row.estimated && row.estimated[key]);
      const usable = available.has(key) && finite(value);
      // The engine assigns a meaningful zero below rosterable depth and also
      // carries a missingReason: the publisher did not actually list him.
      const zeroReason = usable && value === 0 && row && row.missingReasons && row.missingReasons[key];
      const status = !available.has(key) ? "source_unavailable" : !usable ? "missing"
        : estimated ? "estimated" : zeroReason ? "unlisted_zero" : "listed";
      return {key, value: usable ? value : null, estimated: usable && estimated,
        unlistedZero: Boolean(zeroReason), status,
        estimateReason: usable && estimated ? row.estimated[key] : null,
        missingReason: zeroReason || (usable ? null : !available.has(key) ? "Source unavailable"
          : (row && row.missingReasons && row.missingReasons[key]) || "No indexed value")};
    });
    const complete = inputs.every(input => input.value !== null);
    const sourceCount = inputs.filter(input => input.value !== null).length;
    return {id: view.id, label: view.label, recipe: view.recipe,
      value: complete ? inputs.reduce((sum, input) => sum + input.value, 0) / inputs.length : null,
      complete, status: complete ? "complete" : sourceCount ? "partial" : "unavailable", sourceCount,
      expectedSourceCount: inputs.length,
      listedCount: inputs.filter(input => input.value !== null && !input.estimated && !input.unlistedZero).length,
      unlistedZeroCount: inputs.filter(input => input.unlistedZero).length,
      estimatedCount: inputs.filter(input => input.estimated).length,
      inputs};
  }
  const api = {CATEGORIES, VIEWS, PUBLISHED, OBSERVED, PROJECTIONS, categoryOf, read};
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  root.DDFSourceViews = api;
})(typeof window !== "undefined" ? window : globalThis);
