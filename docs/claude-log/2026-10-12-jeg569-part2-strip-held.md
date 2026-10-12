## 2026-10-12 - JEG-569 part 2: strip held sources instead of restoring

Contract: implement Jeremy's 2026-10-12 decision — when a source is held, strip
its combos (set to {}), run no calculations on it, and gray it out on the page.
Supersedes the earlier restore-from-last-good-build behavior.

### Verified (check named)
- `make test-core`: all pass except pre-existing test_razzball_one_save failure
  (same on main).
- `make validate`: same result (validate runs reference, sync, guard-harness,
  test-core, test-integration).
- test_seeded_hold_build: 5 tests verify held sections have empty combos, static
  export and superflex pass on a held build.
- test_fidelity_hold: 40 passed — ChainAppliesTheHold tests renamed and updated
  to verify combos stripped.
- test_static_export: 40 passed — present_sources now filters by non-empty
  combos; anchor pie test skips when ESPN held.
- test_ddf_composite_value: hold_on function strips combos; removed holdKeptWeek
  assertion.
- Front-end: held sources get `run: false` in eligibilityReason (previously
  `run: true`), so no pipeline runs on them.

### Claimed, not confirmed
- 12-combo headless sweep not run: held sources have no values to sweep, and the
  change only affects the hold path (run: false when held). The sweep is
  meaningful only when sources have data.
- _adjusted section handling is complete: tested via test_fidelity_hold and
  test_seeded_hold_build, but no integration test seeds a hold on a source that
  has live _adjusted data in the fixture.
