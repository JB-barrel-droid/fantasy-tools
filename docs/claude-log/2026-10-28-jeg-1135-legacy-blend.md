## 2026-10-28 - JEG-1135: merge main into #976; old three-projection blend maps to our methodology

Contract: bring PR #976 up to date with main (it was conflicting) and apply
Jeremy's 2026-10-27 decision on the open JEG-1073 question: a saved blend with
all three projections ticked (the old default) maps to our methodology instead
of carrying over as a blend. Fewer ticked still carry over as their blend.

### Verified (check named)
- Merge conflict was only in the Makefile render-sweep shard 3 list; both new
  modules kept. `python3 -m unittest tests.test_render_sweep_shards` passes.

### Claimed, not confirmed
- `tests.test_v2_overrides_basis_render` (renamed test
  `test_all_three_projections_ticked_maps_to_our_methodology`, assertion changed
  because Jeremy changed the rule) passes: no Chromium in this session, PR CI runs it.
