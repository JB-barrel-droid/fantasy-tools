## 2026-10-23 - JEG-879 and JEG-881 restore loosened guards

Contract: tests only. Check which JEG-879 loosenings (PR #814) are still loose on origin/main, restore any that are, and rewrite the tautological finder held-chart check (JEG-881) with an independent expectation, each proven against a simulated broken state.

### Verified (check named)
- JEG-879 engine: on origin/main 71abb2e7 `test_value_pipeline_engine.py` already has `assertEqual(len(bands), 2)` and an un-skipped `test_guard_catches_one_band_only`. `pytest tests/test_value_pipeline_engine.py`: 14 passed. Broken state: ran the engine with the band-loop mutation (`break;`); `variant_problems` returned 361 problems, WR bands expected 2 got 1, so both the pin and the mutation guard discriminate.
- JEG-879 composite: main already asserts `explicitDefaults.ok`, `isDefault`, `explicitDefaultsSame` (defaults == allowed == projection keys after #814) and `assert_held_chart_not_in_ddf_value` checks `excludedReason.startswith(reason_start)`. `pytest tests/test_ddf_composite_value.py` (under the render lock): 17 passed. Broken states applied to curve-widget.js (app and dist, then reverted): (a) setCompositeInputs no longer collapses the default set to null -> test_set_composite_inputs failed on 'setCompositeInputs(allowed) should be isDefault'; (b) excludedReason null -> both held-chart tests failed ('not found'); (c) excludedReason 'zzz' -> both failed on the startswith(reason_start) assertion. No test change was needed for composite.
- JEG-881 unit: `tests/test_v2_finder.py` check() now passes the three non-held chart keys with hand-derived expectations (held chart rejecting does not block; held chart accepting does not count; charts list is exactly the available keys). New MUTANT "chartKeys ignored" is caught; run against that build `check()` returns exactly the two new errors. `pytest tests/test_v2_finder.py`: 2 passed, 7 subtests.
- JEG-881 render: `test_v2_finder_render.py` now serves the dist with pinned holds (CBS held) and errors if `heldNames` is empty; new mutation "availability filter dropped" is caught. First run on the unpinned fixture failed the new assertion (heldNames empty), confirming the old check was vacuous. After pinning: 2 passed, 4 subtests. This one file was run before the shared render lock was in use.

### Claimed, not confirmed
- JEG-878 untouched by design.
