## 2026-10-29 - JEG-1339 correction to JEG-1318: merge a created or cleared manager

Contract: the review of #1170 at `2d27eec` found that a manager one tab creates or clears (a blank profile and an
empty league are never stored) still lost the other tab's edit, and that this tab's timer could write over a save
whose storage event it had not handled yet. Correct both on the same branch.

Fix: `mergeBook()` merges profile by profile and reads a missing profile as the blank one (with the base's
timestamps), so a first mark, a reset or a blanking untick merges field by field. `write()` re-reads storage and
merges any save it has not heard about before writing.

### Verified (check named)
- `node tests/manager_profiles_harness.cjs app/v2` with the module at `2d27eec`: the five new checks fail
  (`test_store_merge_first_mark_on_blank_manager`, `test_store_merge_other_tab_clears_league`,
  `test_store_merge_this_tab_blanks_manager`, `test_store_merge_other_tab_blanks_manager`,
  `test_store_write_merges_unhandled_other_tab_save`); with the fix, all 32 checks pass.
- `python3 -m unittest tests.test_jeg1217_manager_profiles tests.test_jeg1217_manager_recs`: OK, including four new
  mutations (missing profile merged whole, whole books merged as values, blanked manager wins outright, write ignores
  an unheard save), each caught by its named check.
- The reviewer's probe `ddf/jeg-1339-merge-probe.cjs`: all six cases pass. Its conflict case (this tab resets a
  manager, the other tab ticks a box) stores the manager with Won't trade off and the other tab's tick kept.

### Claimed, not confirmed
- Not exercised in two real browser tabs (no Chromium in the cloud session).
