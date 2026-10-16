# JEG-687: Python and JS round ties differently

**Date:** 2026-10-16
**Branch:** be/jeg-687-rounding-parity

## Root cause

Python's `sum()` and JS's sequential `+=` accumulate the same floats
in different orders (Python sum uses pairwise summation internally),
producing values on opposite sides of a rounding boundary. For the
thin-peers vector at bench_per_team=6, QB total_vorp:

- Python sum(): 98.850000000000008... -> round(_, 1) = 98.9
- JS +=:        98.849999999999994... -> pyRound(_, 1) = 98.8

Both languages use half-to-even (banker's rounding) on the binary float,
so the rounding rule itself was already agreed; only the accumulation
differed.

## Fix

Changed `unified.py` line 514 from `sum(v for ...)` to a sequential
`+= v` loop, matching the JS engine's accumulation order. No JS changes.

## Tests added/changed

- `test_vorp_translation_js_parity`: added bench=6 to the parity sweep;
  added `accum-tie` and `thin-peers-b6` synthetic vectors that land
  total_vorp on a rounding boundary; added negative test
  `test_accum_tie_catches_sum_revert` that loads a reverted (sum-based)
  copy of unified.py and confirms the parity breaks.
- `test_short_chart_waiver.ImputationParity.test_guard_catches_broken_ports`:
  restored bench=6 (was changed to 7 in JEG-686 PR 642 to dodge the tie).

## Verified

- test_vorp_translation_js_parity: 10/10 pass (including negative test)
- test_short_chart_waiver: 9/9 pass
- test_spec_reference_value_pipeline: 20/20 pass
- value_check compare --rerun-engine --strict: agree, 0 mismatches
- 12-combo engine sweep: 13 settings, all fixedPieIndexed+indexedOrderOk True
- Sweep diff vs main: IDENTICAL (zero differences)
- Rank guard: pass, 0 inversions
- make validate: pass (exit 0)
