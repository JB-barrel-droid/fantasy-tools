## 2026-10-28 - JEG-1176: test-core under a lagging, red-held chart

Contract: find every test-core test that fails when one chart (CBS) serves the
week before the others and is on a red review hold, as chain run 40624176718
saw it, and make those tests read a lagging chart in its own week's view
instead of failing. Draft PR only.

### Verified (check named)
- Probe: experiment PR #1025 (closed, never merged) ran every test-core module
  separately in preview CI, once with CBS one week behind and red-held
  (`scripts/lag_probe.py apply` on that branch: `transition_overrides(lagging=("cbs",))`
  plus a red `validationHold`, written into the canonical fixture so every
  test's own sync rebuilds the same state) and once on committed data. Run
  40625507370: committed data, every module passed; lagging state, red were
  `tests.test_superflex` (test_live_page_superflex_control),
  `tests.test_superflex_publisher_values` (test_page_plots_publisher_superflex_values)
  and `tests.test_week_history` (test_prior_week_is_engine_math_on_saved_inputs,
  test_delta_guard_fails_on_broken_states, test_corrupted_single_source_file_still_fails).
  A fourth, `test_rank_guard.TestSavedValues.test_indexed_is_native_times_one_factor`,
  came from the probe's own synthesized fixture (fit totals not updated) and
  went away once the probe recorded them; it is not a lag failure.
- `TestLaggingWeek.test_own_week_reads_reads_in_view_or_notes_lagging` pins
  the shared helper hermetically; the own-week read path in a browser is the
  one test_rank_guard's transition sentinels run (green in both probe runs).
- Probe on the fix: run 40628034762 (experiment branch with this branch merged
  in) passed every test-core module in both the lagging state and on committed
  data, the modules' negative guards included (test_page_guard_catches_missing_roster_key,
  test_guard_catches_a_widget_ignoring_native_superflex, test_corrupted_single_source_file_still_fails,
  test_delta_guard_fails_on_broken_states, test_a_reordered_lagging_chart_still_fails).

### Claimed, not confirmed
- With CBS red-held and lagging alone there is no week transition (a hidden
  chart is not a DDF Value candidate in curve-widget.js resolveWeekView), so
  the page offers no view for CBS's week and the fixed tests take the stderr
  "lagging" note path rather than an own-week read. Read from the code; the
  job logs (where the notes print) are not downloadable here.
- The next chain rebuild in the same state passes post_rebuild_validation past
  test_superflex. Only the probe's replay of that state was run, not the chain.
