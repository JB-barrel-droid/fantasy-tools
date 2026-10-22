## 2026-10-22 - Fix v2 render test failures (JEG-835)

Two render tests failed on main after the weekly automated fixture rebuild.

### Verified (check named)

- `make validate` green (exit 0) — all unit and integration tests pass.
- `test_v2_panels_render`: 2 passed, 20 subtests — no horizontal scroll, row height in range.
- `test_v2_targets_render`: 2 passed, 26 subtests — fold at 1073.8 px under new 1080 threshold.
- Guard-test negative test: "wide cells scroll sideways" mutation at 140px min-width still triggers overflow (verified scroll > 0 in the mutation run).
- Bisected the panels failure to the fantasycalc ok→warn divergence change in source-divergence.json.

### Claimed without confirming

- The 1080 threshold should survive future fixture rebuilds (based on ~20px observed variance, but only two data points).

### Root causes

1. **Panels scroll (product bug):** fantasycalc divergence status changed ok → warn, adding a "⚑ Check" chip to its values-table header. At 6 sources, the extra chip text pushed total header width past 1440px, causing 39px horizontal scroll. Fixed with CSS that hides chip text in `.v2-vtable` headers (font-size: 0 on chip, 11px restored on symbol span).

2. **Targets fold (stale assertion):** TOP5_FOLD_PX was 1060, measured 1073.8 on the new fixture. Weekly rebuilds shift target-list player composition, varying row heights by ~20px. Relaxed to 1080.

### PR

- #776 (branch `worktree-agent-a4059adab052809e2`)
