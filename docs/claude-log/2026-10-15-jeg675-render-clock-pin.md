## 2026-10-15 - JEG-675 render tests red on main (clock drift)

Contract: root-cause the red render suites on origin/main after JEG-631 and fix forward without loosening assertions.

### Root causes
- Clock. The render tests build and read the committed Week 5 fixture (as_of 2026-10-12) on the real date. After the Tuesday 2026-10-13 content-week flip every chart read one week behind: prior-week badges on current charts, one-week-old charts dropped from first load (test_asset_load_retry), filter wrap. Fix: `FANTASY_TOOLS_TODAY` (pipelines/nfl_week.today, sync freshness report, week-history build) set by `_render_env.ensure_built`, and `_render_env` wraps Playwright `Browser.new_page/new_context` to set `window.TRADE_VALUE_TODAY` to the fixture date for every render test.
- Held series. Razzball carries a fidelity `validationHold` in the committed fixture, so it is correctly not offered as "Our value". test_v2_targets_render assumed all four series render rows. It now checks the series the page offers, and asserts a held one is a disabled option. The old assertion was wrong about fixture state, not the code.
- Real CSS bug the hold exposed. The held option reads "Razzball projections - not available for this league", which stretched the Our value select to 482px and wrapped Compare against at 1366 and pushed the top 5 below the fold. Fix: `max-width: 240px` on the Trade targets filter selects at 768px and up. This would have hit production, where Razzball is held.
- test_trade_chart_ingest_ci (3 errors) passes on current main; no change.

### Verified (check named)
- tests.test_v2_targets_render, test_v2_panels_render, test_v2_waterfall_render, test_trade_chart_ingest_ci: red before (3 failures, 1 timeout under load), green after the clock pin plus the targets changes.
- make validate output in the PR description / ticket comment.

### Claimed, not confirmed
- Other render suites not in the red list may also be clock-sensitive; the central pin covers them, but each was not run individually.

### Addenda (same PR)
- The equal-to-market guard ("equal case duplicates the number") had only been fed by Razzball rows; with Razzball held it could not prove it catches its bug. SIMULATE_ROWS now seeds a player whose market average equals our value, and the guard fails again on the mutation (tests.test_v2_targets_render guard test, green only because the mutation is caught).
- JEG-476 (merged during this work) added a section heading and a longer subtitle, pushing the top 5 below the 1366x768 fold. Fixed in CSS (short laptop screens: explainer line hidden, tighter spacing), assertion unchanged.
- Verified: tests.test_v2_targets_render, panels, waterfall, asset_load_retry, trade_chart_ingest_ci, v2_group_weight_render, v2_contract_render, freshness_display_render all OK (50 tests).
- Not mine, still red on main: tests.test_bench_share_readout_matches_reference (17 failures; fails identically with the clock pin disabled), the JEG-630 engine lane. `make validate` stops there in test-core, so the later suites were run targeted as above. value_check compare not run: no value-affecting file changed.
- Seen, not fixed: at 1366 the nav's Research tab is clipped ("Res") by the status chip (JEG-543).
