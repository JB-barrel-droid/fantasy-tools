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

### Merge with main (second pass, same PR)
- Merged origin/main (JEG-505 verdict card, JEG-609 divergence chip, JEG-476 deal read). Conflicts were generated files only (app/, dist/); took main's and regenerated with the sync pipeline.
- Waterfall fold regression, real: the JEG-476 deal read made the verdict card 38 px too tall at 1366x768 (panels ended at y=806). CSS only, short laptop screens (min-width 1280, max-height 800): tighter deal block spacing and a one-line waterfall caption. Assertion unchanged.
- Targets: header sub-label now carries the JEG-609 "Check"/"Reviewed" chip inside `.th-sub`, so the JEG-458 check "ends with rescaled" read the chip text. The chip is deliberate; the test now reads the label with the chip removed (`subLabel`). The assertion on the label itself is unchanged.
- Targets fold regression, real: the same chip and main's rows pushed top 5 to y=796 at 1366x768. CSS only: 3 px row padding on Trade targets rows at short laptop heights (header padding left alone, the 44 px info buttons need it).
- Verified: tests.test_v2_targets_render, test_v2_waterfall_render, test_v2_deal_read_render, test_v2_panels_render, test_v2_states_render, test_asset_load_retry green on the merged tree (last targets re-run after the final CSS change; others ran before it, and the final change only touches `#v2Targets` rules).
- Second merge of origin/main (JEG-677/628/629 landed meanwhile): main had fixed the same sub-label read in test_v2_targets_render; took main's version and dropped mine. The chip is a link in the targets header when a source is Reviewed, 18 px high, so the header chip is now rendered without the link (the note above the lists still links).
- Still red, present with this PR's app/v2 CSS and JS swapped for origin/main's: tests.test_v2_panels_render test_panels_drive_the_engine, main table scrolls sideways (84 px at 1440, 37 px at 1366) with the wide selection. Cause is on main (header widths after JEG-457 source links and the JEG-609 chips), not the clock pin. Not fixed here; for the risk register.
