# JEG-686: imputation py/js parity red after JEG-563

**Date:** 2026-10-16
**Ticket:** JEG-686

## Root cause

PR 603 (JEG-563, default roster 3WR/6bench -> 2WR/7bench) updated the
synthetic thin-peers vector in `_synthetic_vectors()` to bench_per_team=7 but
missed the copy in `test_guard_catches_broken_ports` which still used
bench_per_team=6. At bench=6 the QB total_vorp sums to exactly 98.85, a
rounding tie where Python's float accumulation lands at 98.85000000000001
(rounds to 98.9) and JS lands at 98.85 (toFixed rounds to 98.8).

## Fix

Updated `tests/test_short_chart_waiver.py` line 193-196:
- bench filter (3, 6) -> (3, 7) (6 was dead: real vectors never generate it)
- thin-peers bench_per_team 6 -> 7 (matches new default)

At bench=7 the QB total_vorp is 99.825, which rounds cleanly to 99.8 in both.

## Verified (check named)

- test_short_chart_waiver (all 9 tests): pass
- test_vorp_translation_js_parity: pass
- test_spec_reference_value_pipeline: pass
- test_roster_convention_parity: pass
- value_check compare --rerun-engine --strict: agree, 0 mismatches

## Claimed without confirming

- engine_dump sweep (timed out on playwright; change is test-only, no engine code touched)
