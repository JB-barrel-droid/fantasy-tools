## 2026-10-31 - JEG-1428 Chrome gate continuation

Contract: Run the full gate with installed Google Chrome; keep PR #1251 draft and change no product behavior.

### Verified (check named)
- `CHROMIUM_PATH='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' RENDER_TESTS_REQUIRED=1 make validate`: FAILED (exit 2) in test-core. Browser launch and sync succeeded. Weekly-input contract module ran 36 tests, OK.
- Failing command: `python3 -m unittest tests.test_v2_finder_saved_team tests.test_v2_finder_saved_team_render`: 11 tests, 1 failure. `test_keyboard_mobile_and_overlap_guard` at line 415 expected selected beta, got empty string. Jeremy identified this as a known red outside this PR, diagnosed by another job; left unchanged.
- No ENOSPC was reported. Generated tracked app/dist/data changes restored; pre-existing untracked build artifacts retained and excluded from commits. No value math or protected UI source changes committed.

### Claimed, not confirmed
- Remaining gate checks after test-core did not run; full validate is not green. Independent review and CI remain outstanding. No merge, deploy, Supabase write, production delete or credential change performed.
