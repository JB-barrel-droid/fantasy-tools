# JEG-560: Move live value paths onto roster convention

**PR:** (pending)
**Ticket:** JEG-560 (part of JEG-556)
**Date:** 2026-10-12

## What changed

Migrated value_reference.py (the Python value pipeline reference) and
spec_reference/value_pipeline.py (the clean-room spec reference) to use
the shared roster convention module (pipelines/lib/roster_convention.py,
merged in PR 546 / JEG-559) for:

1. **Bench seats**: replaced fixed BENCH_MIX_12 D'Hondt weights with
   convention's market_bench_ratios * starters D'Hondt. The old
   `bench_seats(total: int)` signature is now `bench_seats(league: League)`.

2. **Starter line**: replaced first-non-starter rule (`work[S].value`)
   with convention rule 3: midpoint of last starter and first non-starter
   (`(values[S-1] + values[S]) / 2`).

3. **Waiver line**: value_reference.py already matched the convention
   (last-listed value on short lists, first-unrostered on long lists).
   No code change needed; parity test updated to verify.

## Numbers changed

The worked example fixture (value_pipeline_worked_example.json) was
regenerated. Sample changes at the fixture's 2-team league:

- Bench allocation: {QB:0, RB:2, WR:2, TE:0} -> {QB:1, RB:1, WR:2, TE:0}
- RB Delta Adjusted (p1): 47.910397 -> 49.077706
- DDF Blended (RB Delta): 48.511113 -> 48.882505

## Parity test results

Three `@unittest.expectedFailure` decorators removed from
test_roster_convention_parity.py:

- TestBenchSeatsParity_ValuePipeline: PASSES (VP delegates to convention)
- TestStarterLineParity: PASSES (VP uses convention midpoint)
- TestWaiverLineParity: PASSES (VP matches convention short-list rule)
- TestBenchSeatsParity_TwoTier: still expectedFailure (JEG-561 scope)

## Verified

- `make validate` green (pre-existing razzball test failure unrelated)
- Parity test: 10 pass, 1 expected failure (two-tier, JEG-561)
- Worked example: 3193 expected numbers, 0 mismatches at 1e-6

## Not changed

- Two-tier leg builder (JEG-561 scope: bake_players.py, build_ddf_two_tier_leg.py)
- JS engine (value-model.js, curve-widget.js) - separate migration
- spec_reference/value_model.py - uses BENCH_MIX_12 from twotier, separate migration
- Default roster switch (JEG-563)
