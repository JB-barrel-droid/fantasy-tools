## 2026-10-22 - JEG-791: content-week pin fix

Contract: Fix the content-week pin in test_week_history.py so the rebuild
chain's post_rebuild_validation does not fail with "page sees week 7 but data
only has week 6".

### Verified (check named)
- `_fixture_today()` now returns a date in the data's content week, not the
  build date's week. `make validate` exit 0 locally (all 29 test_week_history
  tests pass).
- Negative test (`FixtureTodayPinTest.test_pin_uses_data_week_not_build_week`)
  confirms the fix catches the bug: a simulated Week 7 `built_at` with Week 6
  data pins to Week 6.
- PR #742 merged to main (squash). CI checks `preview` and `v2-render` both
  passed.
- Chain run 39704335100 no longer fails on content-week pin -- no
  "page sees week 7" errors. The three DeltaRecomputeTest failures from the
  original chain (39699169810) are gone.

### Claimed, not confirmed
- The chain run (39704335100) fails for a DIFFERENT reason:
  `test_launch_front_door.py::test_v2_table_equals_engine_and_guard_fails_on_drift`
  asserts `columns >= 3` but gets 2 because `fidelity_hold.py apply` holds ALL
  sources at the Week 6->7 boundary. With all values stripped the v2 table
  renders only 2 DDF columns. This is a separate issue, not caused by the
  content-week pin fix. The seeded-hold test (test_seeded_hold_build.py) only
  seeds 2/7 source holds, so the all-held case is untested.
