## 2026-10-22 - JEG-832 Trade chart average is mean of compared chart rows, not the DDF blend

- Problem: the "Trade chart average" card in Compare showed the same number as
  DDF Value on every trade (e.g. +4.8, +6.3, +5.1, +12.7, +21.5), even when
  all compared chart rows (USA Today, FantasyCalc, FantasyPros) were negative.
  The deal read was built on that card and said "the trade charts agree" when
  they disagreed. The verdict also said "Yes" when 0 of N other sources agreed.
- Root cause: `dealRead` used the `ddf_value_charts` engine series. That series
  is a DDF-weighted blend of chart inputs; when projections are held,
  `ddf_value == ddf_value_charts` by construction (same inputs, same weights).
  The market card was always a copy of the value card.
- Fix (trade.js, v2.js):
  - `dealRead` now accepts `chartKeys` and computes the market from the mean of
    per-chart rescaled nets (the same rows Compare's table shows).
  - `MIN_DEAL_CHARTS = 3`: when fewer than 3 charts are complete, the market
    card says "Not enough charts" instead of showing a misleading number.
  - Verdict Unclear rule strengthened: 0-of-N agree always triggers "Unclear",
    regardless of margin or answer. Previously it only fired on thin margins or
    "Even".
  - `collectCompare` in v2.js passes `chartKeys` to `dealRead`.
  - `renderDeal` in v2.js handles the "Not enough charts" display.
- Tests (all verified, all negative-tested with mutation):
  - `test_v2_deal_read_chart_avg.py`: fixture where DDF Value = +20 but all 3
    chart rows are negative. Asserts market net < 0, side = "lose", title =
    "Arbitrage: send it". Mutation: reverts to `ddf_value_charts` blend, test
    catches it.
  - `test_v2_headlines.py`: updated zero-agree expected from "Yes" to "Unclear";
    updated Python recomputation and mutation anchor.
  - `test_v2_deal_read_render.py`: rewritten to inject all 4 chart series in
    FEED, dynamically read chartKeys from the page, compute expected market from
    mean of per-chart nets.
  - `test_v2_deal_read_empty_side_render.py`: 2 passed (unchanged).
  - `test_v2_compare_render.py`: 2 passed (unchanged).
  - `test_v2_contract_render.py`: 6 passed (unchanged).
  - `make validate` subtargets: reference, guard-harness, value-check-compare,
    test-core, test-integration all green.
- Verified: CI (preview + v2-render) green on PR #780.
- Not verified: live site (pending merge).
- Branch: `jeg-832-chart-average`, PR #780.
