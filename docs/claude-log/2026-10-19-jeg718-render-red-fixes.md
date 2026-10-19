## 2026-10-19 - JEG-718 v2 render test fixes

Contract: fix three red v2 render test modules (panels, targets, waterfall)
plus two pre-existing guard mutations exposed by the CSS fixes.

### Verified (check named)

- `test_v2_panels_render.py`: 2 tests, 20 subtests green
  (`pytest tests/test_v2_panels_render.py -q`)
- `test_v2_targets_render.py`: 2 tests, 26 subtests green
  (`pytest tests/test_v2_targets_render.py -q`)
- `test_v2_waterfall_render.py`: 2 tests, 6+6 subtests green
  (`pytest tests/test_v2_waterfall_render.py -q`)
- All three modules run together: 6 tests, 52 subtests green

### Changes

**app/v2/v2.css** (3 changes):
- `--v2-cell-pad-x` clamp max 8px->7px: eliminates 9px table scroll at 1440
- New chart-h rule for `max-height: 800px`: fits chart card at 1366x768
- Short viewport verdict: `gap: 2px`, `.v2-deal` padding 4px, `.v2-cstory` margin 0: fits verdict at 1366x768

**tests/test_v2_targets_render.py** (1 change):
- Replaced "equal case duplicates the number" mutant with "consensus always shows equal note" (always-true mutation caught by check_market)

**tests/test_v2_waterfall_render.py** (2 changes):
- PICK: find gap against `compareView.pointKeys` (waterfall table sources) instead of `shown()`. Root cause: player 35 missing cbsros (in shown but not in pointKeys) so waterfall table had no missing step.
- SIMULATE_DISSENT: pick from pointKeys minus ddf_value instead of hardcoded `['espn', 'cbsros', 'razzball']`. Root cause: none of those were in pointKeys, so no waterfall-table source disagreed.

**tests/test_v2_panels_render.py** (2 changes):
- check_weights: share test value 10%->30% (default QB is ~9.95%, too close to detect a no-op Apply)
- check_league: expanded-table mode to verify tier column header (meta columns hidden at 1440 by media query)

### Claimed, not confirmed

- The CSS changes don't affect production appearance at common viewports (no visual regression test beyond the automated checks).
