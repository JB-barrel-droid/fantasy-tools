## 2026-10-28 - JEG-1204: held and lagging source test matrix

Contract: continue notes-only PR #1051 with per-source tests before JEG-1203
isolation. Cover live-page superflex, publisher rank, reference week views,
and saved-week history with each source held or one week behind. Do not
implement source isolation or change production value logic.

### Verified (check named)

- Read the groomed JEG-1204 ticket (no comments), takeover document, latest
  main HANDOFF, AGENTS, and PR #1051 before editing. The PR was still the
  single notes commit `5ba0101b`. No `.agents/skills` directory is present.
- Chromium reproduction on original HEAD: FantasyCalc held at the current
  week passes `test_superflex.page_problems` and `test_week_history.collect`.
  This corrects the unconfirmed suspicion in the earlier hold-tolerance log:
  sourceMaps is a pipeline harness and retains held source values. Numeric
  assertions were not relaxed.
- First browser matrix: all 21 valid source/state cases and all seven
  source-specific served-data corruption controls passed. An underscored
  class alias made unittest start a duplicate render pass; removed that
  alias and stopped the redundant run. `make validate` runs the final suite.
- Focused CPU verification: 27 tests passed, including all fixture scenarios,
  replaying already-lagging inputs back to a current-week hold, actual
  isolated-fixture identity loading, and explicit clock pinning. A separate
  16-test run passed the superflex negative controls and CI shard registry.
- Final `tests.test_seeded_hold_build` under `make validate` passed all
  59 tests with Chromium required (356.126 seconds), including the 21 valid
  source/state render cases and seven independent corruption controls.
- Independent read-only review found no remaining blocking finding after
  correcting held-source `included` versus `hidden` expectations and making
  the replay baseline independent of pre-existing live lags.
- Missing-browser smoke: with Playwright imports blocked, the render class
  raises SkipTest for optional local renders and RuntimeError when
  `RENDER_TESTS_REQUIRED=1`; it cannot silently pass required CI renders.
- The initial full `make validate` exited 2 in the unrelated
  `tests.test_espn_listed_rows`: its legacy `tests._dist_server` locator only
  looks in Playwright's cache or at macOS Chrome and ignores CHROMIUM_PATH.
  Set `PLAYWRIGHT_BROWSERS_PATH=/tmp/jeg1204-browsers`, with the expected
  browser cache executables linked to the installed `/usr/bin/chromium`.
  Both explicit-path and default Playwright launches then worked, and the
  previously failing module passed all three tests. No test assertion or
  unrelated helper was changed. Validation resumes from that exact module
  through the rest of test-core, value-check-compare, and test-integration;
  already-passing long render modules are not repeated.
- The resumed remainder exited 0: the complete test-core recipe has now
  passed across the original and resumed runs, followed by
  `make value-check-compare test-integration` passing. This is the full gate
  on the original PR base plus this patch, not a claim that the interrupted
  original `make validate` command returned 0.

### Claimed, not confirmed

- Main integration, focused Week 8 checks, publication, and PR CI will be
  recorded before this lane stops. No PR merge, deployment, Supabase change,
  ticket completion, or live acceptance is claimed here.

### Choices and handoff

- Matrix remains in the existing seeded-hold core module; test scenarios
  use independent copies and served HTTP overrides. Reversible engineering
  choices are recorded in `docs/picks-log.md`.
- Projection source data lives in the page's inline player payload; a
  `players.json` HTTP override alone would not test it. The helper injects
  only changed PPG fields before the existing product-data conversion, with
  identical PPG values in reference input files. Corruption controls prove
  the browser consumes those altered inputs.
- Browser commands use `CHROMIUM_PATH=/usr/bin/chromium` and
  `RENDER_TESTS_REQUIRED=1`. Without CHROMIUM_PATH the builder tried an absent
  Playwright bundled browser; using the installed Chromium resolved it.
- Build output remains uncommitted; no generated files are deleted for
  cleanup. Parent owns main integration, green CI, serial merge/release,
  live verification, and then closing JEG-1204.
- Linear reread at 14:47 UTC reported JEG-1204 as Done while PR #1051 was
  still open and notes-only. This lane made no Linear edits or completion
  claim; the parent should reconcile that status with actual merged/live
  acceptance.
