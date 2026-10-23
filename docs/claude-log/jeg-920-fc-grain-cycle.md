## 2026-10-23 - JEG-920: Fix fc_grain_check 3-cycle detection

### Root cause

`fc_grain_check` (line 1113 of `pipelines/fidelity_pulse.py`) required a mutual
swap (`nearest.get(n) == g`) to flag a column mix-up. This catches 2-cycles
(A<->B) but misses 3-cycles (A->B->C->A), which is a valid save-time column
rotation. Introduced in 54a59a41 (JEG-807, 2026-10-22) to stop false-positive
reds from lone drift.

### Fix

Replaced the mutual-swap check with general cycle detection: walk the `nearest`
map from each displaced column; if the chain closes back to the start (length
>= 2), every column on the cycle is flagged. The FC_SWAP_RATIO gate still
applies per column. Lone drift (no cycle) is still ignored.

### Test changes

Converted `tests/test_fc_grain_check.py` from pytest-style classes to
`unittest.TestCase` so `python3 -m unittest` discovers them (the existing CI
pattern). Added the module to `test-unit-modules` in the Makefile. No test
assertions were changed; only the base class and assert syntax were adapted.

### Verified

- `python3 -m unittest tests.test_fc_grain_check -v`: 6/6 pass (0.002s)
- Guard proof: monkey-patching the old mutual-only logic makes exactly the 3
  swap-detection tests fail; the 3 negative tests still pass
- CI time impact: +0.002s (pure-Python unit test, no network or render)

### Not verified

- Full `make validate` (not run; only `fidelity_pulse.py` changed, and the
  fix is additive to the detection logic)
