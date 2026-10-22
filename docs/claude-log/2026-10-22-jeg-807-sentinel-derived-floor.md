## 2026-10-22 - JEG-807: Razzball sentinel floor derived from current sources

Jeremy decision (2026-10-22): re-derive the sentinel floor from current projection
sources each week instead of the fixed 15.0 at `pipelines/fidelity_pulse.py` line 1457.

Root cause: Razzball QBs run about 0.83x ESPN as a systematic model difference
(Mahomes 13.8/g vs ESPN 19.2, CBS 22.7, population stdev 0.10). The fixed 15.0
constant (set 2026-10-12) held Razzball when its numbers were correct.

Change: sentinel bands are now derived from the mean of OTHER projection sources'
half-PPR per-game values for the same sentinel player, multiplied by named ratio
constants (`SENTINEL_LOW_RATIO = 0.55`, `SENTINEL_HIGH_RATIO = 1.50`). When no
other source has data, fixed fallback bands (the old constants) are used. The
players.json data is loaded once per pulse run via `load_extras`.

Why 0.55: Mahomes 13.7 / mean(19.22, 22.65) = 0.655, passes with margin. Two
standard deviations below the 0.83 population mean (0.83 - 2*0.10 = 0.63) > 0.55.
Catches value 0, column shifts (280 total points in a PPG field), wrong-player rows.
Rejected: 0.70 (the original bug), 0.65 (too close to the edge), 0.50 (too loose).

Verified:
- `tests/test_sentinel_derived_floor.py`: 23 tests, all pass. Covers: Razzball
  systematic discount passes (a), garbage values caught (b), missing sources fall
  back safely (c), negative tests.
- `tests/test_fidelity_sentinels.py`: 8 existing tests, all pass (backwards compat).
- `tests/test_fidelity_razzball.py` + `tests/test_fidelity_hold.py`: 82 tests, all pass.

Not changed: value-model.js, value_pipeline.py (separate agent: build-jeg-804-787-engine).
