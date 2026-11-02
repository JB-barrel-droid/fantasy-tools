## 2026-10-30 - JEG-1424 League settings: three scorings, restore check (render test)

Contract: `check_settings` in `tests/test_v2_league_tables_render.py` now reads the top three Trade opportunities gains on the
4-team fixture under Full PPR (before), Standard, Half PPR and Full PPR again, using the same Edit league popover steps. Each
pair of scorings must differ and the second Full PPR result must equal the first exactly. No numbers are hard-coded. Test only:
no app code, no value math.

### Verified (check named)
- Mac session 2026-11-01, Google Chrome via `CHROMIUM_PATH`, `RENDER_TESTS_REQUIRED=1`: `python -m unittest tests.test_v2_league_tables_render`
  runs 2 tests, OK (test_tables and test_guard_fails_on_broken_builds).
- Fix to the render test's reader: the earlier `[opps]` market sort failure was the test, not the app. The table prints negative gains with a
  Unicode minus (`signed` in `app/v2/league.js`), and the `num` reader in `OPP_ROWS` did not parse it, so negatives read as positive.
  `num` now accepts the Unicode minus. No app code changed.
- The mutation that bites: `math context frozen at its first build` (new row in `test_guard_fails_on_broken_builds`, `settings` check).
  `mathContext()` is memoized at its first build, so a scoring switch never reaches the math and the later scorings repeat the Full PPR
  result; the settings check reports it and the guard test requires that.

### Not a valid mutation
- Removing the cache reset in `app/v2/league.js` (`UI.cache = O.createCache();` before `store.replace(ws, "settings")`) cannot fail any
  check: the pairing cache key (`opportunities.js` `sigOf` plus `contextSig`) already changes with scoring, so the reset is redundant while
  that key covers scoring. It is not used as a mutation.
