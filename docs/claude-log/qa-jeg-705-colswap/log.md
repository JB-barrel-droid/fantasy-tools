## 2026-10-19 - JEG-705 QA: test_column_swap_red failing on main

- **Finding:** `test_column_swap_red` in `test_fidelity_pulse.py` failed with `AssertionError: 'column check' not found in summary`. The test went red from systemic mismatch, not from column-swap detection.
- **Root cause:** The test fixture bake was 8 h old (`SAVED=15:00`, `NOW=23:00`), but PR 673 (JEG-705) added `FC_GRAIN_CHECK_MAX_AGE_S=7200` (2 h) which skips `fc_grain_check` on stale bakes. The grain check was silently skipped, so the "column check" reason never appeared in the summary. The test assertion was correct; the fixture timing was wrong.
- **Fix:** Set `created_at` to 1 h before `NOW` in the test so the bake is fresh and the grain check runs. Added `test_column_swap_stale_bake_no_false_positive` proving a stale bake does not false-positive on the column check.
- **Verified:** 60 passed, 16 subtests passed (test_fidelity_pulse + test_fc_grain_check). Negative-tested: without fresh bake, "column check" absent from summary; with fresh bake, present. CI green (v2-render + preview). PR #707 squash-merged.
