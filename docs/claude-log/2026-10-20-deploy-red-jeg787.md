## 2026-10-20 - Fix deploy-red: spec reference eligibility() did not honour amber-hold-001 (JEG-787)

Deploy dashboard (run 39496908728) and all hourly runs since ~2026-10-20T18:00Z
failed at test-core on `test_every_projection_held_is_a_degenerate_week`.
Rebuild comparison chain (run 39496776150) failed on Supabase 402 (egress quota,
unrelated infrastructure issue).

### Root cause

Two defects, one blocking:

1. **spec_reference/pipeline_live.py `eligibility()`** treated every
   `validationHold` as ineligible, including amber holds. amber-hold-001
   (Jeremy, 2026-10-19) says amber holds stay eligible; only red holds hide.
   PR 714 updated the main pipeline but missed the independent spec reference.

2. **test_every_projection_held_is_a_degenerate_week** was data-dependent:
   it held only 3 projection sources (red) and called `_check_live()` which
   asserts `included` is truthy. When the live fixture also had chart sources
   held or unpublished, `included=[]` for every setting and the assertion
   failed. The test now seeds its own all-held fixture (all 7 sources red-held)
   so the guard is data-independent.

### Changes

- `pipelines/spec_reference/pipeline_live.py`: `eligibility()` checks
  `hold_level`; amber holds return None (eligible), red/absent stays "held".
- `pipelines/spec_reference/SPEC_AMBIGUITIES.md`: SA-5 updated for amber holds.
- `tests/test_spec_reference_value_pipeline.py`: degenerate test seeded with
  all sources red-held, no longer calls `_check_live`. New
  `test_amber_hold_stays_eligible` positive+negative test.

### Verified (check named)

- `python3 -m unittest tests.test_spec_reference_value_pipeline` -- 22/22 pass
- `test_amber_hold_stays_eligible` negative-tested: red holds exclude, amber
  holds do not

### Not verified

- `make validate` not run to completion (pre-existing `test_week_history`
  failure on main, data-dependent, unrelated to this change)
- CI deploy and chain dispatch pending PR merge
