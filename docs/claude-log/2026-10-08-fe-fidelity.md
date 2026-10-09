## 2026-10-08 - fe-fidelity: freshness fails closed; bench share shown as used

Contract: fix two v2 data-fidelity bugs. (1) The Source freshness panel showed "✓ Current" when
`reference-freshness.json` failed to load or a source's own row was missing. (2) Below the feasible
bench window v2 showed the requested bench share, not the share the engine priced with.

### Verified (check named)
- Before the fix (unmodified `origin/main` a027e4d1 v2.js with the new tests):
  `tests.test_v2_panels_render.PanelsRenderTest.test_panels_drive_the_engine` FAILED with 11 freshness
  errors (e.g. "with the file missing usatoday shows '✓ Current', want unknown");
  `tests.test_v2_bench_used_render.BenchUsedRenderTest.test_bench_share_shown_is_the_share_used` FAILED
  with 10 errors (no getBenchShareUsed; readout/split showed 2.0%, engine priced QB 7.54%, RB 4.74%,
  WR 4.40%, TE 4.45%; no note).
- After the fix: both pass; the guard tests catch the new mutations ("freshness fails open" in
  `test_v2_panels_render`, "requested share shown instead of the used one" in `test_v2_bench_used_render`).
- Engine probe (headless, PPR 12 teams): `getBenchBounds()` = [0.01, 0.30]; bench_share_used at 2% =
  QB 0.0754, RB 0.0474, WR 0.0440, TE 0.0445; at 15% all 0.15.
- `getBenchShareUsed()` returns exactly the calibration's `bench_share_used` (asserted in the bench test
  against `TradeValueTwoTierLive.calibration`).
- Full v2 render suites, `tests.test_launch_front_door` and validate: see the commit message.

### Claimed, not confirmed
- "Lowest/highest the league supports" wording assumes all used shares move the same way as the request;
  a mixed case (some positions above, some below) would say "lowest".
- The "checking sources…" chip text before the freshness file loads was not screenshot-checked.
