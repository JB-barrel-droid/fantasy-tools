## 2026-10-29 - JEG-1182 league opportunity panel render test (PR #1159)

Contract: run tests/test_v2_league_oppanel_render.py with Chrome. Name the root cause of the failure, then fix the code, not the assertions.

### Verified (check named)
- On origin/main 5c07ad67, in a clean worktree (`git clean -fdx`, so no `build/`), `pytest tests/test_v2_league_oppanel_render.py -v` with `CHROMIUM_PATH` set to Google Chrome gave 3 failed and 1 passed. All three failures were `FileNotFoundError: build/engine/index.html`.
- Root cause: `_built_dist()` in tests/test_v2_finder_render.py calls `build_v2_page.build()`. That reads the gitignored `build/engine/index.html`, which `_render_env.ensure_built()` produces.
  - Modules call `ensure_built()` from `setUpModule`. This module has no `setUpModule`, and neither do six other `_league_render` modules (found with grep).
  - In a sweep, an earlier module builds `build/engine` first, which hid the gap.
- After running `pipelines/sync_dashboard_artifacts.py` on unchanged main, the same command gave 4 passed. The panel has Close (`#v2LgOppPanelClose`), and the viability slot matches the JEG-1108 regex.
- The original "viability slot or Close missing" symptom was already fixed (git log -S on app/v2/league.js and the 5ec98ad7 commit body):
  - 5ec98ad7 (#1021) split the combined message that covered both checks.
  - `viabilityText()` arrived with 2e90b88f (JEG-1129, #960).
- Fix: `_built_dist()` calls `_render_env.ensure_built()`. No assertion changed. With the fix, on a clean worktree, the same command gave 4 passed and 3 subtests passed.
- Also with the fix: tests/test_v2_contract_render.py and tests/test_no_real_clock.py gave 15 passed.
- PR preview CI on 7f138a1d: the rendered gate succeeded, and the DDF fixed pie failed for 0 of 12 shapes (preview-build comment on #1159).

### Claimed, not confirmed
- The other 63 modules that use `_built_dist` are unaffected apart from no longer needing an earlier build. I did not run them locally; full-suite coverage is preview CI's.
- `make validate` was not run locally.
