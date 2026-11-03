## 2026-10-29 - JEG-1318 manager profiles keep a pending edit when another tab saves

Contract: a manager-profile edit still inside this tab's 1-second write delay must not be dropped when another tab
saves. Built on #1084's head (`8fac0986`), since `app/v2/manager-profiles.js` is not on main yet. No value, ranking or
band change.

Fix: `createStore()` keeps the book it last read from or wrote to storage. When another tab saves while this tab has
an unsaved edit, `reloadFromStorage()` merges the two from that base: a value only one tab changed keeps that tab's
change, ticked boxes combine box by box, and a field both tabs set keeps this tab's value (the later edit). The edit
stays owed and the pending timer writes the merged book. If storage already holds the edit, nothing is owed and the
status reads saved. Picked merge over "skip the reload until the save is written" because skipping would overwrite the
other tab's save when this tab writes, which only moves the lost edit to the other tab.

### Verified (check named)
- `node tests/manager_profiles_harness.cjs app/v2` on the unfixed module: the three new checks fail
  (`test_store_pending_edit_survives_other_tab`, `test_store_pending_edit_merges_same_manager`,
  `test_store_reload_without_pending_edit_takes_other_tab`); with the fix, all 27 checks pass.
- `python3 -m unittest tests.test_jeg1217_manager_profiles`: OK, including six new mutations, each caught by its named
  check (reload drops the edit, skip-only overwrites the other tab, merge base not moved on save, boxes not combined,
  both-set field goes to the other tab, save still owed once storage holds it).
- `python3 -m unittest tests.test_jeg1217_manager_recs`: OK (unchanged).

### Claimed, not confirmed
- Two real browser tabs on the built page were not exercised (no Chromium in the cloud session); the storage event
  wiring at the bottom of the module is unchanged.
