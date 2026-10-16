# JEG-676: chain review holds now set validationHold

**Date:** 2026-10-16
**Ticket:** JEG-676

## Finding
The rebuild chain's `isolate_hold()` restores a review-held source's fixture
section to its pre-run state but never set `validationHold` on it.
Downstream, `test_week_history.held_roots()` checks for `validationHold` to
identify held sources and exclude them from the served-week check. Without the
flag, CBS (review-held at week 5) was included in the served-week check against
the week-6 chart and failed: "cbs served week != chart" (164 players). This
blocked every chain run since the CBS coverage drop triggered the review hold.

## Change
- `pipelines/rebuild_comparison_chain.py` `isolate_hold()`: after restoring the
  fixture, sets `validationHold` (reason "chain hold: ...") on the held
  source's fixture sections. This makes the source visible to `held_roots()`
  and excluded from served-week checks.
- `pipelines/value_check.py` `release_holds()`: skips "chain hold: ..." holds
  (like it already skips "fidelity: ..." holds), so the value-check step does
  not accidentally release them. Only the next successful chain run clears them.
- `tests/test_value_check.py`: regression test proving chain holds survive
  `release_holds`.

## Verified vs claimed
- Verified: test_value_check (21 tests), test_fidelity_hold (40 tests),
  test_seeded_hold_build (5 tests), test_static_export (36 tests),
  test_spec_reference_value_pipeline (20 tests) all green locally.
- Verified: new test `test_chain_hold_is_not_released_by_value_check` fails
  with the value_check change reverted (chain hold would be released).
- Claimed: the chain will pass `make validate` on the next run because
  test_week_history will exclude CBS from the served-week check.

## Follow-up: test assertion fixes (PR #619)

First chain run after PR #617 failed because three test files compared
held sections with exact equality against their pre-hold state, which now
fails because the section correctly contains `validationHold`.

- `tests/test_bake_on_change.py` (2 tests): verify hold metadata, compare
  content without it
- `tests/test_razzball_refresh.py` (2 tests): same pattern
- `tests/test_rebuild_chain_per_source_hold.py` (helper): same pattern

Verified: all 58 tests in the three files pass locally.
Assertions are strictly stronger: they now check both preserved content
AND correct hold metadata (reason prefix "chain hold: ", correct root).
