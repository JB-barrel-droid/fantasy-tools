# 2026-10-23: Turn both JEG-969 flags on by default

## What
Commit `489d6f94`: turn flex_bench_seats on by default (Jeremy approved
2026-10-23). Combined with the promotion_model (already on since `69c27bc7`),
PR #867 now has both engine changes active.

## Verified
- 45 engine + spec reference tests pass (22 engine + 23 spec)
- value_check compare --rerun-engine --strict: **agree** on 1,224,771 values
- Headless browser 12-combo sweep: fixedPieIndexed **PASS** all 13 settings
- sourceScaleAgreement: retired (GAP-026), not checked
- make validate: running (background)
- Fixture-matching tests explicitly pass promotion_model=False, flex_bench_seats=False
- No assertion was weakened; the only changes to tests add explicit False flags

## Not verified
- make validate not yet complete at time of log entry (check bg task)

## Before/after at Full PPR / 12 teams (both flags combined)
- Overall bench share: 0.1170 -> 0.1278
- QB bench share: 0.235 -> 0.095 (-0.139)
- QB bench seats: 15 -> 4
- Top movers up: Jahmyr Gibbs RB +4.5, Jordan Addison WR +4.4
- Top movers down: Jared Goff QB -4.9, Caleb Williams QB -4.9
- Players > 1.0 DDF Value change: 123 of 734
- Buy/Sell tier changes: 0

## Commits on PR #867
- `0b50b90c` Step 1 diagnosis
- `47da016c` Step 2 decomposition and rates
- `53339ff7` Step 3 promotion model (flag off)
- `eff69bef` Step 4 sweep
- `69c27bc7` Promotion model on by default
- `5d5e0385` Log: promotion model
- `720f9652` MR-28 flex_bench_seats (flag off)
- `5d5e0385` Log: flex_bench_seats
- `489d6f94` Both flags on by default
