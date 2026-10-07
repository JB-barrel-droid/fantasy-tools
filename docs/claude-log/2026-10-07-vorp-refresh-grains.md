## 2026-10-07 - JEG-437 item 1: retired FantasyCalc grains out of the VORP refresh

### Verified (check named)
- Before: `refresh.GRAINS` had 7 (source, teams) pairs incl. fantasycalc 8/10/14;
  `resolve_combo_key` raises SystemExit (not an Exception) for them, so the
  per-grain `except Exception` never catches it (risk row JEG332-VORP-REFRESH-RETIRED).
- After: GRAINS = 4 pairs x 3 scorings = 12; `python3 -m unittest tests.test_vorp_refresh` OK.
- Negative test: re-adding `("fantasycalc", 8)` to GRAINS makes
  `test_grain_enumeration_is_12` (5 != 4) and the new `test_every_grain_is_translatable`
  (resolve_combo_key SystemExit against the fixture) fail.
- The test was edited because its 21-grain expectation was the bug, not the code.

### Claimed, not confirmed
- The refresh was not run against Supabase (no credentials here); the
  publisher_translated_values rows stay at week 4 until the next chain run.
