## 2026-10-26 - phone tap targets on the menu base (JEG-1116)

Contract: make tests/test_v2_phone_tap_targets_render.py green on the PR #949 base (stacks on #948 menu, #944 finder): the 768 px source-link overlap and the Reviewed chip guard gap. Assertions are unchanged.

### Verified (check named)
- Cause of the 768 px overlap: the info button's box (default margin-left -10 px) covers the last 8 px of the source link in a column head. Same geometry on origin/fe/JEG-1093-finder and origin/fe/JEG-1106-nav (probe of both built dist/), but the finder branch reports 0 overlaps because the sweep skips controls whose centre scrolls out of the window; #948 changed the page height so it is now measured. Latent before, exposed by #948. Fixed in v2.css: `.v2-table th .v2-info { margin-left: 0 }`, and no touch padding on the link's info side.
- Reviewed chip guard: the baked data has no public resolution URL, so every chip is a span and the sweep never saw a link chip (the JEG-1048 pseudo-element only applies to links). The test now serves reference-freshness.json with every source reviewed and linked (`_with_linked_reviews`). The first assertion of test_guard_fails_without_jeg1048_fixes (small Reviewed chip) passes; before this it failed.
- Serving linked chips exposed a real overlap: on a wide window with a fine pointer the legend chip's 15 px extension above and below covered the source link in the row above or below (768 to 1280 px, every chart tab). Fixed in v2.css (`.v2-showing-legend a.v2-div-chip::after` keeps its own box on fine pointers). Overlap sweep at 768, 1024, 1280 on trade-targets and player-values: 0 overlaps.
- Negative checks: the overlaps above were observed with the fixes absent (before-state runs), and gone with them.

### Follow-up (Jeremy decision, 2026-10-26)
- Removed the Compare net info-button rule (`#v2Compare .v2-deal-nets .v2-info { height: 24px ... }`) and the half of test_guard_fails_without_jeg1048_fixes that guarded it. Reason: the rule is dead. With it removed there is no overlap at 1280x800, 1280x768, 1366x768, 1440x800 or 1280x720 (probe of the built page), so the guard could not fail. This was not done to go green; the Reviewed chip half stays and passes.
- Verified: tests/test_v2_phone_tap_targets_render.py (3), tests/test_render_sweep_coverage.py and tests/test_v2_waterfall_render.py all pass (11 passed, RENDER_TESTS_REQUIRED=1, Chrome). File removed from KNOWN_RED and wired into the Makefile render list next to the phone header test.

### Claimed, not confirmed
- make test-core was not run.
