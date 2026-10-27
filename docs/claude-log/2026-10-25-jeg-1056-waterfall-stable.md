## 2026-10-25 - Waterfall render example stable under data refreshes (part of JEG-1056)

Contract: make test_waterfall_verdict_layout_example and test_wide_font_guard_fails_on_broken_nav green on main (06c9be24), keep all assertions at the same strength, and confirm each mutation guard still catches its target.

### Root causes (two separate bugs)

**test_waterfall_verdict_layout_example**: PICK selects players from live engine data sorted by ESPN. A data bake (b227f453) changed which players are selected and their DDF Value/market relationships. The new trade produced a "you win" verdict with multiple dissenting sources, whose longer text and taller deal card (191px vs 154px) pushed the verdict column 54px past the 1366x768 fold. No app code changed; the test was data-unstable.

Additionally, the "verdict names no source" mutation guard was not caught because the baseline at 1366x768 already had layout overflow errors, and the mutation's errors matched the same `shape` (number-masked pattern). A clean baseline is needed for mutation detection.

**test_wide_font_guard_fails_on_broken_nav**: The "tabs shrink with the label" mutation sets both `.v2-tabs` and `.v2-freshness` to equal `flex-shrink: 1`. The guard only checked tab squeeze at 1279px, where neither the clean nor mutated version squeezes (tabs fit at that width). At 1280px the nav enters a wider layout mode and the mutation causes visible tab squeeze (748px vs 871px natural), but this width was not checked.

### Fix

1. **Seeded fixture** (`SEED_VALUES`): wraps `getAllRows`/`getRows`/`getPlayer` to replace the top-12 ESPN players' values with small, deterministic numbers (floor above 13th player + 2-point spread). Produces a stable "you lose" verdict with short text and a 154px deal card that fits 1366x768 with 19px margin. The seed runs after example-trade checks but before PICK, so example checks use live data and linked-trade checks use seeded data.

2. **check_wide_font 1280 split** (follow-up after CI run 40255965792): the real nav squeezes at 1280 on CI fonts (DejaVu Sans, 868 of 964px -- GAP-WATERFALL-NAV-1280-SQUEEZE, JEG-1113). The real-page check now asserts only at 1279. The mutation guard in `test_wide_font_guard_fails_on_broken_nav` runs a baseline-vs-mutation comparison at 1280: the mutation must widen the squeeze beyond the baseline, proving it is caught at the breakpoint without requiring the real page to be clean at 1280.

### Verified (check named)

- `test_waterfall_verdict_layout_example`: PASSED (seeded, all 4 viewports)
- `test_wide_font_guard_fails_on_broken_nav`: PASSED (both mutations caught)
- `test_guard_fails_on_broken_builds`: PASSED, all 7 mutations caught including "verdict names no source" (1 new error: verdict does not name the sources that see it the other way)
- `test_no_sideways_scroll_with_a_wide_fallback_font`: PASSED
- All 4 tests in test_v2_waterfall_render: PASSED (47.88s)
- `make -o sync validate`: fails on pre-existing test_rank_guard sync error (product-data.js rmtree race), unrelated to this change

### Live data finding

With current data (06c9be24) and no seed, the PICK-selected trade overflows at 1366x768 by 54px (bottom=822 vs fold=768). This is a data-dependent product issue: the deal read card and verdict text grow with certain trade outcomes ("you win" + multiple dissenters). The seeded fixture makes the test stable; a product fix to fit all realistic trades at 768px would require reducing the deal card, verdict text, or header area by ~55px.

### Claimed, not confirmed

- That the seeded fixture will remain stable through arbitrarily many future data bakes. The floor is computed from the 13th player's ESPN, so it adapts, but if the number of available sources changes (adding/removing a source), the verdict column height could shift.
- That `make -o sync validate` would pass on a clean checkout of main; the rank_guard sync error may be worktree-specific.
