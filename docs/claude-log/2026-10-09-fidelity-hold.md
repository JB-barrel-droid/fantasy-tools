## 2026-10-09 - JEG-520: a fidelity pulse red holds the source, with per-source tolerance

Contract: a confirmed pulse red holds that source and its derived series (validationHold, reason
`fidelity: <stage>`), with tolerance so normal publisher drift does not hold; each tolerance documented
with measured drift.

### Verified (check named)
- FantasyCalc drift measured from `source_trade_values` (week 5, every pair of saves 10-08 12:59Z to
  10-09 17:05Z): share of values outside the max(25%, 50) band is 0-0.8% at 3-4 h, up to 4.2% at 7 h,
  up to 8.0% at 28 h; the 10% red line is kept. Projections day-to-day change measured from
  `cbs_ros_projections` and `razzball_projections` (docs/fidelity-tolerances.md).
- tests/test_fidelity_hold.py (22 tests): seeded bad states (stored != same article, chart != stored, wrong
  week, truncated save, FantasyCalc broken save, zeroed projection) hold exactly that source; FantasyCalc
  movement in band, an article revision after the save, a projection daily update do not hold.
- Negative tests (scratch mutation script, 8 simulated broken states: hold on amber, hold every source,
  release any hold, value check releasing fidelity holds, no restore, count drop red when the publisher
  dropped too, held chart never red, article revision red): each fails at least one test.
- Workflow tests (rebuild chain, no-failopen, dispatch permissions, event interpolation) pass.

### Claimed, not confirmed
- First live chain run with the step: checked after merge (see the PR / JEG-520 comment).
- A held projection keeps its current section (labelled, out of DDF Value), not its last good one:
  restoring it alone would break the ESPN anchor triple; open as a follow-up.
