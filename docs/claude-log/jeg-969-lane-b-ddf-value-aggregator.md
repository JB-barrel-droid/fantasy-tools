## 2026-10-23 - JEG-969 lane B: DDF Value aggregator tests

### What was done

Tested whether any aggregation method beats the equal-weight mean of projection
sources for DDF Value, using all available data. Branch
`research/JEG-969-ddf-value`, PR #866.

### Steps

1. **Data audit**: verified inventory of ESPN week-ahead (6 weeks), ROS
   projections (5 weeks, 3 sources), RotoWire/Sleeper week-ahead (8 seasons,
   52k rows), Supabase captures (22,437 rows, ROS only). Three-source
   week-ahead comparison blocked until JEG-944 captures start.

2. **Aggregator tests**: ran aggregators 1-7 from post 10 protocol on PPR
   data. Equal mean (n=1,122): MAE 4.609. No alternative's CI excludes zero
   vs equal weights. Bias correction is significantly worse (+0.107 MAE).
   RotoWire and ESPN are indistinguishable head-to-head (n=1,812, CI [-0.07,
   0.06]). RotoWire stable across 8 seasons (CV 0.09).

3. **Decision**: equal weights remain production. Automatic re-test script
   (`aggregator_retest_check.py`) committed. MR-32 logged in math review
   agenda.

4. **Impact**: zero. No engine code changed. No values change.

### Verified

- All data counts checked against files and Supabase (read-only)
- Aggregator test script runs end-to-end, bootstrap 2000 resamples
- No file in `app/` or `pipelines/` modified
- Sleeper idmap match rates confirmed against PR #850 report

### Claimed (not verified)

- The QB positive bias (+3.4 ppg from RotoWire) is genuine and not an
  artifact of the join or missing data. The 8-season sample is large but
  I did not independently verify the RotoWire source data.
- The re-test script's Supabase query path is untested (no week-ahead
  captures exist yet).
