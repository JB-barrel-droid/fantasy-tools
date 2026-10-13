# JEG-562: expected-starts model onto the roster convention

**Date:** 2026-10-12
**Ticket:** JEG-562 (part of JEG-556, implements JEG-546 fix)

## Changes

Migrated `pipelines/expected_starts_model.py` from hardcoded roster/bench
allocation to the shared roster convention (`pipelines/lib/roster_convention.py`):

1. **tiers_on_mean -> tiers_on_values** (convention rule 6): bench-share
   measurement now tiers each player by their rank on the list being valued
   (DDF values when measuring DDF bench share, per-source values when
   measuring per-source). This is the root-cause fix for JEG-546's inflated
   22.7% QB bench share.

2. **alloc -> convention allocate_league**: replaced hardcoded ROSTER
   {QB:1,RB:2,WR:3,TE:1,FLEX:1,BENCH:6} and BENCH_MIX_12 {10,27,33,10}
   with convention defaults (1 QB / 2 RB / 2 WR / 1 TE / 1 FLEX / 1 K /
   1 DEF, 7 bench) using market bench ratios from config/market_bench.json.

3. **lines -> convention starter_line/waiver_line**: starter line now uses
   midpoint of last starter and first non-starter (convention rule 3) instead
   of first-non-starter. Waiver line uses first player not rostered (rule 4).

## Numbers (verified)

QB bench share at ppr/12: **8.66%** (was 14.31% with tiers_on_mean, 22.7%
before the Razzball fix). Overall bench share: **8.99%**. Zero inversions
across all 12 settings.

| Range | QB bench | Overall |
|-------|----------|---------|
| Low   | 6.32%    | 8.78%   |
| High  | 11.34%   | 12.16%  |

## Checks run

- 13-combo engine sweep: fixedPieIndexed=true, indexedOrderOk=true -- **PASS**
- Rank guard: 0 inversions -- **PASS**
- Guard harness: PASS (simulated espn-anchor: FAIL as expected)
- test_expected_starts_model.py: 13/13 PASS
- test_roster_convention.py: 29/29 PASS
- test_roster_convention_parity.py: 11/11 PASS
- value_check compare: **pre-existing disagree** on main (caused by JEG-569
  part 2 held-sources change, not by this PR)
