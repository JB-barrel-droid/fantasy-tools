## 2026-11-07 - JEG-1550: waterfall render test's "lose" scenario lost its dissenting source

Contract: get `tests/test_v2_waterfall_render.py` green on main again with a test-only change.
No value math, page code, config, data or fixture changes.

### Verified (check named)
- The failure is real on current data: v2 render run 42322495172 (PR #1338, head cea3e530)
  shows `test_waterfall_verdict_layout_example` failing with "the 'lose' scenario has no dissenting
  source" at all four viewports, and `test_guard_fails_on_broken_builds` failing on
  "verdict names no source [lose]". The win scenario passes in the same run.
- In the old `SEED_VALUES`, USA Today's offsets cancelled for the picked trade (give ranks 0 and 5
  at +4/-2, receive ranks 2 and 3 at +4/-2: net 0), so the lose scenario had no seeded dissenter
  and depended on `SIMULATE_DISSENT` alone (arithmetic on the seed in the test file).
- The win run in 42322495172 names USA Today as a table-row dissenter on the same PICK, so USA Today
  is a shown table row with values for the picked players on current data.

### Claimed, not confirmed
- The fix (USA Today +4 on the two received players, +0.5 elsewhere: USA Today nets +7 against
  DDF Value's -6) makes the lose scenario pass at every viewport and keeps the guard mutation caught.
  To be confirmed by the PR's v2 render run; no Chromium was available in the cloud session.
- Why `SIMULATE_DISSENT` stopped producing a table-row dissenter after the 2026-11-06 rebuild
  (4b11126) is not diagnosed. It no longer matters for this scenario, but it is still the only
  dissent source for any unseeded check that relies on it.
