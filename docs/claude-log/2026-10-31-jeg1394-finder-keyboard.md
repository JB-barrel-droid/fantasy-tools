## 2026-10-31 - JEG-1394 finder keyboard baseline correction

Contract: Diagnose the finder keyboard failure that blocked draft PR #1240, fix a small test/setup issue if justified, and rerun the full gate. No shell, scoring, season-label or value-math changes.

### Verified (check named)
- Merged `origin/main` at `c267aa71` into `claude/JEG-1394-advanced-render` normally, without rebase or force push.
- In a new detached, source-unmodified `origin/main` worktree, `CHROMIUM_PATH='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' RENDER_TESTS_REQUIRED=1 python3 -m unittest tests.test_v2_finder_saved_team_render.FinderSavedTeamRenderTest.test_keyboard_mobile_and_overlap_guard` failed at line 415: selected `''`, expected `'beta'`.
- A browser event trace showed Home/ArrowDown reaching the native select without input/change events. A standalone three-option native select reproduced the inert arrow navigation in local headless Mac Chrome; letter type-ahead selected the intended option.
- Changed only the keyboard setup to type `s` twice through the duplicate team names (and once for the opponent). The same focused Chrome test passed at 1366, 390 and 320 pixels. Every selection, opponent-roster, overlap, target-size, overflow and saved-team-preservation assertion remains unchanged.
- Inside the full gate, `python3 -m unittest tests.test_v2_finder_saved_team tests.test_v2_finder_saved_team_render` passed all 11 tests with Google Chrome and render tests required.
- `CHROMIUM_PATH='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' RENDER_TESTS_REQUIRED=1 make validate` passed the previously failing finder stage, then failed with three errors at `tests/test_v2_phone_fallback_font_render.py:76`: DejaVu Sans is unavailable to local Chrome. No unchanged retry, font installation or assertion relaxation was performed. No ENOSPC error occurred.

### Claimed, not confirmed
- Full gate is not green; checks after the missing-font failure were not run.
- Linux browser behavior and production were not checked. No merge or deployment performed.
