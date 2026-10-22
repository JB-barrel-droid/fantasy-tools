## 2026-10-22 - JEG-851 Trade targets: compare against a single source

- Problem: the "Compare against" dropdown had every individual chart grayed
  out ("needs 2 or more charts") since JEG-834. Jeremy wants any single chart
  selectable, and chart keys selectable as "Our value" so any source can
  compare against any other.
- Fix (targets.js): CHART_KEYS added to OUR_KEYS. When ourKey is a chart key,
  effectiveCharts = charts minus ourKey (prevents self-comparison). With
  exactly one effectiveChart, minCharts = 1 (single voter suffices); otherwise
  2. rankEquivalents and marketConsensus accept minCharts as a parameter.
  buildTargets returns singleChart (the lone chart key, or null).
- Fix (v2.js): "Compare against" enables every chart; disabled only when
  unavailable or same as current "Our value". "Our value" shows chart keys;
  disabled when same as "Compare against". Heading, empty-state, footnote, and
  market-value tooltip rewrite for single-chart mode (chart name instead of
  "market consensus"). Fixed out-of-scope `TT` reference in `renderTargets()`
  that caused a ReferenceError at runtime -- this was the root cause of the
  render test timeout (the page errored before `window.TradeValueV2.targets()`
  was set).
- All existing rules preserved: rank-gap rule, BUY_RANK_MARGIN = 2,
  SELL_FLOOR = 5.0, out/estimated exclusions (JEG-842), "missing is never
  zero / chart value 0.0 is never a buy".
- Verified: `test_v2_targets.py` 2 passed (4 new harnesses: singleUSA,
  chartAsOurs, selfCompare, singleEstimated; 4 new mutations each proven to
  catch its bug). Node syntax check and smoke test on both JS files.
- Not run locally: full `make validate`, Playwright render tests (Mac
  overloaded with parallel agents; CI is the gate).
- PR: #807, branch fe/JEG-851, waiting on CI.
