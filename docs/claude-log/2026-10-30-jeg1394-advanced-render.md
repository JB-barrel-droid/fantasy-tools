## 2026-10-30 - Advanced settings retain their live draft / JEG-1394

Contract: Diagnose the missing bench slider on main without weakening the render test. Preserve the Advanced controls' draft reference across live updates; no value math changes.

### Verified (check named)
- `git log -S v2BenchSlider -- app/v2/v2.js` shows the slider was retained, not removed or renamed. `git log -S 'draft.adv = now'` traces the replacement to 439cae1c (#886).
- Merged current `origin/main` normally (fast-forward to 7358589c); no rebase.
- After `CHROMIUM_PATH='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' make sync`, `RENDER_TESTS_REQUIRED=1 python3 -m unittest tests.test_v2_advanced_render` with the same Chrome path failed on unmodified main: two tests, one error setting the null slider's value.
- After changing `draft.adv = now` to `Object.assign(draft.adv, now)`, the same build and Chrome test commands passed: two tests, including all five broken-build guards. No test assertions changed.
- With the same Chrome path and `RENDER_TESTS_REQUIRED=1`, `python3 -m unittest tests.test_v2_inputs_status_render tests.test_v2_contract_render` passed all 14 tests, including the related Advanced settings panel, live contract walkthrough and mutation guards.
- `CHROMIUM_PATH='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' RENDER_TESTS_REQUIRED=1 make validate` failed in `tests.test_v2_finder_saved_team_render.FinderSavedTeamRenderTest.test_keyboard_mobile_and_overlap_guard`: selected team was `''`, expected `'beta'` (11 tests in that stage, one failure). No retry or out-of-scope correction was made.

### Claimed, not confirmed
- No production or live-site verification; this is a draft PR, with no merge or deployment.
- The finder failure's cause and whether it also fails on main were not investigated; the full gate is not green.
