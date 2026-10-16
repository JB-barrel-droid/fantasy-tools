## 2026-10-15 - JEG-563: Default roster switch

Switch all pipeline defaults from old 1QB/2RB/3WR/1TE/1FLEX/6bench to the
convention default: 1QB/2RB/2WR/1TE/1FLEX/K/DEF/7bench (most common real
league format). Python-side only; JS parity is JEG-630.

### Verified (check named)

- 248 directly-affected Python tests pass: roster convention, imputed vorps,
  derive lineup parameters, VORP translation unified, player scenario matrix,
  DDF two-tier leg, DDF groups, VORP wiring, value reference worked example,
  PPG tie parity, reweight inversion budget, chain commits legs, and more.
- config/roster.json positions stays skill-only (QB/RB/WR/TE); K/DEF appear
  only in roster_shape. This prevents the value pipeline from iterating K/DEF
  (which have no waiver PPG or tier data).

### Claimed without confirming

- The 12-combo engine_dump sweep (3 scorings x 4 league sizes) was not run;
  the task instructions say to skip repeated sweeps while value lanes are
  still changing (JEG-630 will change them again).
- `make sync` not run (generated dist/ will change again with JEG-630).

### Known parity breaks (JEG-630 scope)

- test_superflex.py, test_vorp_translation_js_parity.py,
  test_bench_share_readout_matches_reference.py, test_value_check.py all
  fail because value-model.js still uses old 3WR/6bench defaults.

### Also fixed

- Pre-existing AttributeError: expected_starts_model had no ROSTER or
  FLEX_ELIGIBLE exports but score_lineup_values.py referenced them. Added
  both, derived from convention module defaults.

PR: https://github.com/JB-barrel-droid/fantasy-tools/pull/603
