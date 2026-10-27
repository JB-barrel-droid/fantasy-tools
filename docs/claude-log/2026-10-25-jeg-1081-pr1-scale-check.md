## 2026-10-25 - JEG-1081 PR 1 follow-up: source scale check

Contract: confirm the per-source espn/cbsros/razzball values that `valueNoise` reads sit on the same point scale as `ddf_value_projections`, and compare against the pre-JEG-1073 build (commit 42562990). Adds to the PR 1 entry; claims there about scale and held-out stability are updated here.

### Verified (check named)
- Headless page (render lock, built dist, `TradeValueCurveControls.getRows()`): mean of the three sources over `ddf_value_projections` has median/p10/p90 of 1.000 on 105 rows; pool totals espn/cbsros/razzball 2352.0 each vs 2368.9; per-source median ratio espn 1.000, razzball 1.000, cbsros 0.960.
- Same extraction on a detached build of 42562990: projections SE mean 2.699 vs 2.711 now, p90 4.951 both.

### Claimed, not confirmed
- The historical build uses the same week-7 data, so this is not an earlier-week held-out test; the 25% stability rule is met only trivially.
