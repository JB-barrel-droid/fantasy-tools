## 2026-10-16 - JEG-705: fc_grain_check false-positive column-swap detection

Investigated a gate-slack alert claiming FantasyCalc stored `full|2` values were
closest to live `half|2` — reported as a genuine column swap in the puller/saver.

### Root cause (verified)

**Not a column swap.** The puller (`pull_fantasycalc_12team.py`) and saver
(`save_fantasycalc_references.py`) mappings are correct: `SCORINGS` maps
`standard->0, half->0.5, full->1` and `FC_COMBOS` maps filenames to the matching
grain keys. Stored values match live API values exactly on a fresh bake.

The false positive comes from `fc_grain_check` in `fidelity_pulse.py`. It
compares stored bake values against live API values and flags when stored "full"
is 1.5x closer to live "half" than to live "full". FantasyCalc's scoring gap
between formats is only ~10-50 points, but intraday crowd-voting drift after 2+
hours is ~20-40 points. On a stale bake the drift exceeds the scoring gap,
making every stored column look "closer" to a wrong live column.

Evidence:
- 15:40Z fidelity run vs 2.5h-stale bake: RED with column-swap message
- 17:36Z fidelity run vs 31-min-fresh bake: GREEN, 1188/1188 exact match
- Direct Supabase query: stored full|2 values for top players match live API full PPR

### Fix

Added a bake-age guard to `fc_grain_check`: when `bake_age_s` exceeds
`FC_GRAIN_CHECK_MAX_AGE_S` (7200s / 2h), the column-swap check is skipped
entirely. The `stage_publisher` caller now computes bake age from `saved_at` and
passes it through.

### Verified (check named)

- `pytest tests/test_fc_grain_check.py`: 6/6 pass (3 classes, covering genuine
  swap detection, false-positive suppression on stale bakes, correct-data no-fire)
- Negative test: old code (no age guard) produces 5 false-positive swap
  detections on the drift scenario; new code returns `[]`
- No stored rows need correction — all data is correct

### Not verified

- Full `make validate` not run (standing instruction: skip repeated sweeps while
  value lanes still changing)
- Live fidelity run with the new code not exercised
