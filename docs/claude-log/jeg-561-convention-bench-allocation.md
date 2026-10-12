# JEG-561: Baked legs, DDF groups, backstop on roster convention

**Date:** 2026-10-12
**Ticket:** JEG-561 (part of JEG-556)
**PR:** TBD

## What changed

Replaced the legacy `bench_mix_for_teams` formula (hardcoded
`floor(BENCH_MIX_12[pos] * teams/12 + 0.5)`) with the roster convention
module's D'Hondt bench allocation using measured market bench ratios
(config/market_bench.json).

### Files changed

- `pipelines/build_ddf_two_tier_leg.py`: bench_mix_for_teams now delegates
  to `roster_convention.bench_seats(REF_SLOTS, teams, DEFAULT_BENCH)`.
  BENCH_MIX_12 and REF_BENCH_SLOTS kept as backward-compat exports for
  callers outside this ticket's scope (vorp_via_roster, value_reference).
- `pipelines/build_razzball_ddf_leg.py`: removed BENCH_MIX_12 import (unused).
- `pipelines/build_cbsros_ddf_leg.py`: removed BENCH_MIX_12 import (unused).
- `pipelines/build_ddf_groups.py`: removed unused `_leg_utc_now` import.
- `pipelines/backstop_shallow_sources.py`: `configured_target_count` now uses
  convention's D'Hondt bench allocation instead of raw bench_total from manifest.
- `tests/test_roster_convention_parity.py`: TwoTier parity test is now GREEN
  (was expectedFailure, confirmed by this migration).
- `tests/test_ddf_two_tier_leg.py`: removed unused REF_BENCH_SLOTS import.

### Bench allocation changes (12 teams)

| Pos | Legacy | Convention | Delta |
|-----|--------|------------|-------|
| QB  | 10     | 12         | +2    |
| RB  | 27     | 23         | -4    |
| WR  | 33     | 44         | +11   |
| TE  | 10     | 5          | -5    |
| Tot | 80     | 84         | +4    |

Mechanism: WR has 3 starters x 1.03 backups/starter = 3.09 weight,
dominating the D'Hondt allocation. TE has only 0.40 backups/starter.
DEFAULT_BENCH = 7 per team (vs legacy ~6.67 = 80/12).

### Decisions

- REF_SLOTS kept at {QB:1, RB:2, WR:3, TE:1} (not switched to convention
  DEFAULT_SLOTS {QB:1, RB:2, WR:2, TE:1}) because changing it cascades to
  the VORP translation path (JEG-560's lane). The bench allocation method
  changed; the reference shape did not.
- build_week_history.py: no bench/tier logic found; the "12 teams" references
  are Supabase data-grain filters, not allocation. No change needed.

## Verified

- 12-combo headless sweep: fixedPieIndexed PASS for all 12 combos (3 scorings x
  4 league sizes).
- Parity test `TestBenchSeatsParity_TwoTier`: GREEN.
- `make validate`: chain green, all tests pass except pre-existing
  `test_razzball_one_save` (unrelated).
- `make sync`: generated files rebuilt.
