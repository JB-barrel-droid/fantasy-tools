## 2026-11-01 - PR #1233 required-render validation (JEG-1263)

Contract: resume the interrupted Mac job, use the first heavy-suite lane, repair the validate baseline without
weakening tests, and leave publication and merging to the merge gate. No app/v2/v2.js, shell.html, value-math,
production-data or credential change. Remote branch: claude/JEG-1263-validate-baseline.

### Verified (check named)

- Checked git state and surviving processes first. The interrupted type-ahead log was empty and its process gone;
  it is not a pass. Preserved the intervening PR preparation commits through a normal branch merge, then merged
  origin/main fe1faaf4 normally (77427ae3). Resolved the local HANDOFF stash conflict by preserving both sections.
- Read JEG-1465's merge-gate:window-lock-rule. No writes to the named six batch branches; this job must finish
  all pushes before 10:45 UTC and stop writing until that window's results. No other heavy make process was active.
- Before the interruption, fc-list was unavailable and system_profiler SPFontsDataType had no DejaVu match.
  Installed font-dejavu with HOMEBREW_NO_AUTO_UPDATE=1 brew install --cask font-dejavu, user-level in ~/Library/Fonts,
  without sudo. DejaVuSans.ttf is present after restart. No font test or repository environment rule was changed.
- Read #1240's Finder patch at 16f72d4d. Adopted its genuine keyboard type-ahead instead of the programmatic
  fallback: two `s` keys cycle the duplicate Same name entries to beta; one selects alpha on the other side.
  Removed keyboard_pick and its sys.platform condition. #1233 is the single owner of this harness repair.
- Current-main failing-before probe: loaded origin/main's unchanged Finder test in memory and ran
  FinderSavedTeamRenderTest.test_keyboard_mobile_and_overlap_guard against app/config/data identical to main
  fe1faaf4, with local Chrome and RENDER_TESTS_REQUIRED=1. Fails in 33.565s with selected '' rather than 'beta'.
  Log: /tmp/jeg1263-finder-before-fe1faaf4.log. The older 12887fc7 reproduction fails identically.
- python3 -m unittest tests.test_render_sweep_coverage tests.test_render_sweep_shards: 10 OK. AST comparison
  confirms every Finder assertion equals current main. git diff --check passes. No new KNOWN_RED entry: the
  existing USO journey exemption names fixing owner JEG-1403 (related context ticket JEG-1259).
- With local Chrome and RENDER_TESTS_REQUIRED=1, the focused Finder keyboard test and all three
  tests.test_v2_phone_fallback_font_render tests pass: 4 tests in 118.403s. This includes both old-CSS
  mutation guards. Log: /tmp/jeg1263-typeahead-font-after.log. DejaVu is now exercised, not just present on disk.
- Full CHROMIUM_PATH='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' RENDER_TESTS_REQUIRED=1
  make validate passed with exit 0. Includes all 11 saved-team unit/render tests, all three fallback-font tests,
  fractional-seat stability, rank guard, 15-setting/270-check view audit, core and integration checks.
  Strict engine/reference comparison agrees on 1,234,507 values with zero mismatches.
  Log: /tmp/jeg1263-validate-required-fe1faaf4.log; completion sidecar contains 0.
  The run had resource warnings and a local HTTP BrokenPipe during desktop-menu testing; that suite still passed
  both tests. No failed test was retried, omitted or weakened to obtain the full-gate result.
- Separate required-render contract suite plus tests.test_jeg1389_link_settings_reload_render and
  tests.test_jeg1389_switch_redraw_render: 8 tests passed in 606.483s, including the contract broken-build guards.
  Log: /tmp/jeg1263-contract-new-modules.log; completion sidecar contains 0.
- Temporary raw logs listed above are summarized here and removed with this job's own temporary worktree on exit.
  DejaVu fonts remain installed for future Mac gates. Other owners' worktrees/artifacts are outside cleanup scope.

### Claimed, not confirmed

- Current-head CI and independent delta review remain required after push. No merge, deploy, Supabase write or scoring/season
  relabeling. Integration import messages were dry runs, not production writes.
