# 2026-10-08 bench-share-low lane (fix/bench-share-low)

Bug from the views-audit lane (origin/main a1ff559): Full PPR / 12 teams, bench
share 1-3%, then any rebuild -> "Curve regression guard failed:
fixedPieIndexed" (ESPN anchor 2.05 over its pie, tolerance 2), and the page
stayed failed. Risk-register row: GAP-BENCH-SHARE-LOW-PIE.

## Verified (check named)

- **The anchor's pie was genuinely off; the tolerance was not the problem.**
  Headless probe (classic page, branch base aefb8f7, 12 combos x 1-40%): ESPN
  anchor total minus pie sum was +0.65 to +1.78 at 1-5% in 10 of 12 combos
  (at most 0.04 at 14 teams except ppr/14 4%: +0.35), shrinking to 0 by ~12-15%;
  standard/8 was +0.02 at the 15% default. Per-position totals all above
  their pies (ppr/12 1%: QB 59.98/59.82, RB 394.91/394.09, WR 409.49/408.99,
  TE 69.18/69.13). Positive excess = the max(0, alpha + beta x) clip in
  `buildLiveAdjustedMap`: OLS fitted sums equal the cell targets, the clip
  only adds. Confirmed by the fix: the same probe after restoring each clipped
  cell's fitted total shows delta 0.00 at every combo and share 1-30%.
- **1-3% is selectable by design.** `getBenchBounds()` is [0.01, 0.30] in all
  12 combos. `TradeValueTwoTierLive.calibration(s)` at ppr/12 for s = 1-3%
  steps every position up inside its window (QB 0.0754, RB 0.0474, WR 0.0441,
  TE 0.0445), so 1-3% price identically; 4% is just inside the RB/WR/TE
  windows (bench rate ~0, the clip's worst case). Not clamped: the step-up is
  the pipeline rule.
- **Stickiness, two causes.** (a) `setBenchShareFraction` never re-priced:
  stale.py probe on aefb8f7, Aaron Jones ESPN 19.60 at 15%, still 19.60 after
  setBenchShare(2) and after a slider input/change to 5%, 10.36 only after a
  view-tab click. After the fix: 10.19 at 2% and 10.36 at 5% directly, on
  /classic/ and /. (b) a guard failure left `guardsPassed` true, so resize
  repainted rejected curves (recovery check: canvas painted after a forced
  failure on the mutation, blank on the fix).
- `tests/test_bench_share_low_pie.py` (added to test-core), 7 tests, 38 s.
  Passes on the branch. Discrimination: the sweep fails on aefb8f7's widget
  (pie +1.519 at ppr/12 1%, 176 of 474 anchor values stale) and on two
  single-defect mutations (clip correction removed -> pie failures only;
  slider refresh disabled -> stale only); the recovery check fails on aefb8f7
  (slider never ran the guards) and on a mutation that keeps `guardsPassed`
  true (canvas painted after failure and resize).
- 12-combo sweep, aefb8f7 widget vs branch widget on the same `make sync`
  dist (only curve-widget.js differs), default share: 11 combos identical in
  every getAllRows value, sourcePeaks, fixedPieIndexed, sourceScaleAgreement.
  standard/8 moves: espn 17 values (max 0.008) and every shared-total series
  by at most 0.003 (cbsros, razzball, *_adjusted, *_vorp), sourcePeaks differ
  by that amount; fixedPieIndexed true both sides. At 4%: espn moves at most
  0.19 (bench players in clipped cells), others at most 0.14 via shared
  totals; half_ppr/14 identical.
- `make sync` then `CHROMIUM_PATH=... make validate`: exit 0.
- Pinned assertion changed: `tests/stage1_fallback_golden.json`
  `buildLiveAdjustedMap` body (test_two_tier_frontend
  TestStage1FallbackFrozen). The golden is a verbatim snapshot; the contract
  it guards (no live machinery in the fallback, no raw passthrough for a
  missing two-tier-native cell) is unchanged and still checked by the
  identifier scan in the same test. Re-snapshotted, not loosened.
- test_jeg103_bench_slider_readout and test_v2_panels_render pass.

## Claimed, not confirmed

- `tests/rendered_gate/bench_share_readout_harness.mjs` was not run (no Node
  Playwright here); its Python wrapper passed. The slider input/change path
  was checked with Python Playwright instead.
- v2's own bench control (`app/v2/v2.js` 1431, front-end lane) now gets a
  re-priced chart from `setBenchShareFraction` and can receive a thrown guard
  error like other setters; not exercised beyond the / page probe.
- No server parity change: the pipeline bakes ESPN cells at 0.15 only, where
  the identity-like fit does not clip; the live refit at other shares is
  browser-only.
