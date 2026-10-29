## 2026-10-29 - Waivers: focus after roster Clear and Undo (JEG-1316)

Contract: build option A of JEG-1316 (the coordinator's pick, 21:53 UTC, under Jeremy's standing OK to make picks and log them). After roster Clear, focus lands on the unfolded roster
input. After roster Undo, focus lands on the roster control that is on screen (Edit roster once results fold the input), and
"Your roster is back." shows outside the folded input. Candidate Clear/Undo and all Clear/Undo data behavior are unchanged.

### Verified (check named)
- `node --check app/v2/waivers.js` passes.
- The non-browser tests that read waivers.js pass: `tests.test_waivers_math`, `tests.test_waivers_views`,
  `tests.test_v2_copy_names`, `tests.test_jeg1130_copy_glossary`.
- The three existing mutant anchors in `tests/test_waivers_clear_isolation_render.py` are still unique in waivers.js
  (the test's `mutate()` asserts this; checked by reading the diff).

### Claimed, not confirmed
- `tests/test_waivers_clear_isolation_render.py` now asserts both focus points and the visible "is back" message at 320,
  390 and 1366 wide, and three new mutants (Clear focusing before the input unfolds, Undo leaving focus to the fold, the
  message left inside the folded input) each fail their named assertion. The cloud session has no Playwright Chromium,
  so this runs in CI's preview render job (RENDER_TESTS_REQUIRED=1) or on the Mac:
  `python3 -m unittest tests.test_waivers_clear_isolation_render -v`.
- `make test-core` here stops at `tests.test_week_history` needing Playwright (environment, not this change).

### Correction (JEG-1345)
- d6dfa38c also carried 20 regenerated build files (`dist/`, `app/trade-value-chart/assets/*.json`,
  `app/trade-value-chart/index.html`): `git add -A` ran after a local `make test-core` rebuilt them. Backed out by
  restoring each to the branch base and deleting the three it added, then merging `origin/main` in. Verified:
  `git diff --name-only origin/main...HEAD` and `git diff --name-only origin/main HEAD` both list only waivers.js,
  the render test and this log.
- Same push: the Undo focus check now requires `v2WaiversEdit` whenever `#v2WaiversMineInput` is hidden (review nit).
