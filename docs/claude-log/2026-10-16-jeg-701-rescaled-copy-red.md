## 2026-10-16 - JEG-701 banned word "indexed" in v2 dot tooltip

tests.test_v2_rescaled_copy was red on main: app/v2/v2.js dot tooltip read "<chart> (indexed) <value>" (from JEG-677). JEG-510 (2026-10-09) pins user-facing copy as "rescaled". Changed the tooltip to "(rescaled)". Test_v2_rescaled_copy untouched. tests/test_v2_targets_render.py line 556 asserted the old tooltip string; updated because the assertion pinned the wrong copy.

### Verified (check named)
- tests.test_v2_rescaled_copy green; tests.test_v2_targets_render run (see PR).

### Claimed, not confirmed
- Jeremy says "indexed" in speech (2026-10-16 targets decision); the pinned copy rule is unchanged and not contradicted by this fix.
