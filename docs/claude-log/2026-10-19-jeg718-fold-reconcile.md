## 2026-10-19 - JEG-718 fold reconcile: restore 280px plot AND fit fold

Contract: PR 713 (render-fix-001) fixed the 1366x768 fold by shrinking the chart
plot to 248px, but JEG-470/JEG-477 require a 280px floor. This session reconciles
both contracts by trimming surrounding chrome instead of shrinking the plot.

### Verified (check named)

- `test_v2_chart_height_render` passes (2 tests, 4 subtests): plot is 280px at
  1366x768, matching `max(280, min(height - 490, 0.42 * height))`.
- `test_v2_panels_render` passes (2 tests, 20 subtests): card bottom 757.4px at
  768px viewport (10.6px margin), fold check `chartBottom <= innerHeight + 0.5`.
- `test_v2_waterfall_render` passes (2 tests, 6 subtests).
- All 39 v2 render modules run sequentially, 0 failures.
- Guard test `test_guard_fails_on_broken_builds` still catches the "laptop fold
  changed" mutation (anchor `--v2-chart-h: clamp(280px, calc(100vh - 490px), 42vh)`
  on line 37 unchanged).

### Claimed, not confirmed

- No visual regression outside the 1366x768 viewport. The chrome trimming media
  query targets `min-width: 1280px and max-height: 800px` only.

### Change

Single file: `app/v2/v2.css` lines 1093-1101.

Removed PR 713's `--v2-chart-h` override (`clamp(240px, calc(100vh - 520px), 42vh)`)
which gave 248px. Replaced with chrome trimming in the same media query:
- `#v2Main .v2-chart-card` padding: 9.5px -> 4px (needs `#v2Main` for specificity
  over `#v2Main .v2-card` rule at line 988)
- `.v2-chart-head` gap: default -> `0 8px`
- `.v2-chart-head .v2-legend` gap: default -> `8px 8px`
- `.v2-plot` margin-top: default -> `2px`

Total recovered: ~32px, enough to keep the 280px plot within the fold even with
pinned holds causing 3-row legend wrapping (164px chart head).
