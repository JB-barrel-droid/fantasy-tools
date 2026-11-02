## 2026-11-02 - JEG-1450 front-door identity expectation

Contract: repair the stale front-door test expectation after the coordinator
verified the organization cutover. Preserve exact canonical equality checks,
production behavior and baseline-registry logic. No PR merge or main catch-up.

### Verified (check named)
- Local make test-core-shard-5 at exact 258abe1c reproduced exit 2: four
  tests.test_launch_front_door assertions expected the former Pages URL,
  while the configured builder emitted datadrivenfootball.github.io.
  Desktop-menu and view-invariant suites each passed both tests first.
- SITE now uses build_v2_page.SITE_URL, the existing configured repository
  identity. All existing canonical assertions remain exact and unchanged.
- New FrontDoorIdentityTests uses fresh subprocess imports and independent
  literal URL expectations for unset/default, explicit former repository,
  and destination repository. It fails against the old hardcoded SITE on
  the destination case and passes with the correction.
- Required-render focused run of FrontDoorIdentityTests and test_org_cutover:
  11 tests PASS under DDF_GITHUB_REPOSITORY=datadrivenfootball/fantasy-tools.
- Full required-render make test-core-shard-5 under the destination identity:
  47 tests across all nine modules PASS, no skips, including all 12 front-door tests and the unchanged
  missing-source, content-week, player-universe, settings and tag checks.
- No production code, baseline registry row, classifier, gate, or fractional
  stability/continuity test is changed. The separate fractional-test repair
  is not incorporated into this branch.

### Claimed, not confirmed
- Pushed-head CI remains required after these local passes.
- Local rendering uses Playwright 1.62.0 and Chromium 151; CI pins Playwright
  1.49.1. Full CI is the final environment-specific gate.
- The CI shard traceback was unavailable; diagnosis uses the independently
  reproduced local failure. No denied log endpoint was retried or bypassed.
- Independent review and merge remain coordinator-owned.
