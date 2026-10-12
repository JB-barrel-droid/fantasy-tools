# JEG-630: port JS value engine to shared roster convention

**Date:** 2026-10-12
**Ticket:** JEG-630
**File changed:** `app/trade-value-chart/assets/value-model.js`

## Root cause

PR 557 (JEG-560) moved the Python reference (`value_reference.py`) onto the
shared roster convention (`pipelines/lib/roster_convention.py`), which uses
`config/market_bench.json` ratios and D'Hondt allocation for bench seats, and
midpoint starter line. The JS value engine still used hardcoded
`VP_BENCH_MIX_12 = {QB:10, RB:27, WR:33, TE:10}` and first-bench-player
starter line. Result: `value_check compare` disagreed on all 7 sources.

## Fix

1. **Bench allocation**: replaced hardcoded `VP_BENCH_MIX_12` with
   `MARKET_BENCH_RATIOS` (one_qb/two_qb from market_bench.json). `vpBenchSeats`
   now computes weights as `starters * ratio[pos]` and passes them to the
   existing `apportionSlots` (D'Hondt). Updated call sites in `vpAllocate` and
   `esChartSigma`.

2. **Starter line**: changed from first-bench-player to midpoint of last starter
   and first non-starter, matching convention rule 3. Added waiver floor.

Translation path (`translationBench`, `TRANSLATION_BENCH_MIX_12`) was NOT
changed -- it already matched the Python translation path.

## Verified

- `value_check compare`: **agree**, 912877 values, max_abs_diff=8.53e-14
- `test_bench_share_readout_matches_reference`: pass
- 12-combo + superflex sweep: fixedPieIndexed=true, 0 problems
- Guard harness, superflex, bench share low pie tests: all pass

## Pre-existing failures (not caused by this change)

- `test_spec_reference_value_pipeline`: 6 failures on vanilla main (pinned
  expected values stale from a prior change)
- `test_trade_chart_ingest_ci`: 3 errors on main (Python 3.9 `write_text`
  compat; needs 3.10+)
- `test_value_check.SeededMismatch`: razzball validationHold from automated
  rebuild
