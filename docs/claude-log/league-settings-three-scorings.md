## 2026-10-30 - JEG-1424 League settings: three scorings, restore check (render test)

Contract: `check_settings` in `tests/test_v2_league_tables_render.py` now reads the top three Trade opportunities gains on the
4-team fixture under Full PPR (before), Standard, Half PPR and Full PPR again, using the same Edit league popover steps. Each
pair of scorings must differ and the second Full PPR result must equal the first exactly. No numbers are hard-coded. Test only:
no app code, no value math.

### Verified (check named)
- Mac session, Google Chrome via `CHROMIUM_PATH`, `RENDER_TESTS_REQUIRED=1`, base origin/main 06ebcba9: the `settings` check
  alone (`run_checks(only={"settings"})`) returns no errors.
- Fails when broken: with the cache reset in `app/v2/league.js` (`UI.cache = O.createCache();` before `store.replace(ws, "settings")`)
  removed, the check still passes, because the pairing cache key (`opportunities.js` `sigOf` plus `contextSig`) already changes with
  scoring. With the reset removed AND the cache key made blind to scoring (served as overrides, no source edit), the check fails:
  the opportunities did not change, and all three scoring pairs reported the same top gains.

### Claimed, not confirmed
- `python -m unittest tests.test_v2_league_tables_render` fails on `[opps]` market sort ("market desc: shown [3.6, 2.4, ...]") on this
  base, before and independent of this change; `test_tables` was not green as a whole. Not investigated here.
- The cache reset alone is not guarded by this check (see above); it is redundant while the key covers scoring.
