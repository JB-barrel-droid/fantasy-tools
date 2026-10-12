# JEG-546: QB bench share analysis

**Date:** 2026-10-12
**Ticket:** JEG-546
**Type:** Investigation (analysis only; implementation deferred to JEG-562)
**Status:** Findings posted; ticket left In Progress for JEG-562

## Root cause (verified)

The 22.6% QB bench share at ppr/12 is caused by a tier-basis mismatch in
`tiers_on_mean()` (pipelines/expected_starts_model.py line 370).

`tiers_on_mean()` ranks players by the mean of the three projection sources
(ESPN, CBS Roster, Razzball) and assigns starter/bench/waiver tiers on that
ranking. But the bench share metric is measured on the blended DDF value, which
averages across all 7 sources (3 projections + 4 trade charts).

The trade charts rank certain QBs much higher than the projections do. Lamar
Jackson and Patrick Mahomes project at ranks 18-19 by projection mean (~17 ppg)
but carry enormous DDF values (16.79 and 10.43) because the trade charts value
them as top-tier QBs. Since `tiers_on_mean` calls them "bench", their large
DDF values inflate the bench share.

This is exactly the bug JEG-562 describes: "it ranks on the projection mean
but measures the 7-source blend."

## Numbers (verified against the model)

### QB bench share: tiers_on_mean vs per-source-own-tiers

| Setting | tiers_on_mean | ESPN own | CBS own | Razzball own |
|---------|--------------|----------|---------|--------------|
| ppr/8   | 13.1%        | 12.5%   | 15.2%  | 7.8%        |
| ppr/10  | 11.4%        | 11.4%   | 11.0%  | 12.0%       |
| ppr/12  | 22.7%        | 13.7%   | 9.4%   | 14.9%       |
| ppr/14  | 20.5%        | 13.3%   | 11.2%  | 11.6%       |

The mismatch appears only at 12 and 14 teams (where the projection-mean QB
ranking diverges most from the chart ranking). The same pattern holds across
all three scoring formats.

### Top bench-tier QB DDF values driving the inflation

| Player          | Projection mean | DDF value | Tier (by mean) |
|-----------------|----------------|-----------|----------------|
| Lamar Jackson   | 17.17 ppg      | 16.79     | bench          |
| Patrick Mahomes | 17.10 ppg      | 10.43     | bench          |
| Bryce Young     | 17.75 ppg      |  4.50     | bench          |
| Jordan Love     | 18.10 ppg      |  2.68     | bench          |

These four account for 34.4 of the 39.7 total bench-tier QB value (87%).

### Allocation details at ppr/12

- QB starters: 12 (1 per team)
- QB bench (hardcoded BENCH_MIX_12): 9
- QB rostered: 21
- QB waiver line: rank 22, 16.15 ppg (projection mean)
- QB starter line: rank 13, 18.10 ppg

### Fill-in rate for first bench QB (ESPN)

- Depth band 1: fill_prob = 0.187 (1-QB lineup, ~19% chance starter misses)
- First bench QB share of surplus: 44.5%

## The fix (JEG-562)

Replace `tiers_on_mean()` with convention rule 6: "rank within position on the
list being valued." Each source's bench share should be measured against that
source's own tier assignments. The convention module
(`pipelines/lib/roster_convention.py`) already implements the correct lines
(rules 3-4) and allocation (rule 1).

Specific changes needed in `pipelines/expected_starts_model.py`:

1. Replace `tiers_on_mean(sources, teams)` with per-source tier assignments
   using `roster_convention.allocate_league()`, `starter_line()`, and
   `waiver_line()`.
2. Replace `alloc()` + hardcoded `BENCH_MIX_12` with
   `roster_convention.allocate_league()` (convention rule 1 bench allocation).
3. Replace `lines()` with `roster_convention.starter_line()` (midpoint rule)
   and `roster_convention.waiver_line()`.
4. In `shares_and_ratio()`, use the tier of the player on the source being
   measured, not a global tier from projection means.

Expected result: QB bench share ~13.7% at ppr/12 (from JEG-562 description),
overall ~8.2%.

## What was NOT verified

- The exact post-fix numbers depend on the full convention integration (JEG-562),
  which also changes the bench allocation (convention rule 1 vs BENCH_MIX_12)
  and the starter line (midpoint vs first-non-starter).
- Cross-setting ranges after the fix (the "12-setting ranges" in the ticket).
