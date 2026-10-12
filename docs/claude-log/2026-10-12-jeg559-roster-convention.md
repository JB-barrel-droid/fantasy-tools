# JEG-559: Shared roster convention module

**Date:** 2026-10-12
**Ticket:** JEG-559 (part of JEG-556)
**Branch:** jeg-559-roster-convention

## What changed

Created the shared roster convention module (JS + Python twin) that defines
every roster rule in one place:

- `pipelines/lib/roster_convention.py` — Python module
- `app/trade-value-chart/assets/roster-convention.js` — JS twin
- `tests/test_roster_convention.py` — 29 unit tests (all rules + negative tests)
- `tests/test_roster_convention_parity.py` — 10 parity tests (4 expected failures)
- Added both test modules to `make test-core` in Makefile

## Rules implemented

1. **Bench seats:** D'Hondt on `starters_p * backups_per_starter_p` from
   `config/market_bench.json`. Uses `two_qb` ratios for superflex/2-QB.
2. **Flex:** greedy by points (projections) or value (charts).
3. **Starter line:** midpoint of last starter and first non-starter.
4. **Waiver line:** first player not rostered. Short lists: last listed value.
5. **Tier basis:** rank on the list being valued.
6. **Fundamental bench guard:** no value path may import the fundamental bench.

## Verified

- 29 unit tests pass (per-rule + negative tests proving each guard catches its bug)
- 4 JS/Python parity tests pass (twins are bit-exact)
- 4 parity tests correctly fail as `expectedFailure`, documenting:
  - VP bench seats: fixed BENCH_MIX_12 vs convention ratios
  - Two-tier bench: round-half-up scaling vs convention D'Hondt
  - Starter line: first-non-starter vs midpoint
  - Waiver line: 0.0 on short lists vs last-listed value
- `make test-core` pre-existing failure (test_razzball_one_save) is unrelated

## No value changes

This ticket adds the module and tests only. No live value path is changed.
The migration happens in JEG-560/561/563.
