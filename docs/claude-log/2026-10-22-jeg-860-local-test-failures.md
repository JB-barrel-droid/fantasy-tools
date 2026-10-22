## 2026-10-22 - JEG-860 two locally failing tests

Contract: classify and fix the cause of tests.test_espn_zero_badge_render and tests.test_static_export.StaticExportTest.test_inline_players_match_fixture failing locally on main.

### Verified (check named)
- test_inline_players_match_fixture passes on a clean worktree of origin/main 4733a5a (`python -m unittest tests.test_static_export.StaticExportTest.test_inline_players_match_fixture`, py3.12 venv). Local red was a stale dist/ (older players bake) in the old checkout, not a code or test defect. Source of dist/: `make sync` and the bake-players workflow regenerate it; nothing to change. No edit made.
- test_espn_zero_badge_render, `RENDER_TESTS_REQUIRED=1`, playwright==1.49.1 (the CI pin), failed on main: its Trade targets block still pinned the JEG-677 rule (ESPN-0 players that charts pay for are Sell targets with ESPN as our value). That behaviour was removed deliberately today by JEG-820 (Sell needs our value >= SELL_FLOOR 5; an ESPN-0 player has 0) and JEG-842 (out players are never recommended; counted as "left out"). Those PRs updated test_v2_targets*, not this test. Classification: stale pinned assertion; the code is right per the product decisions.
- Fix: the Trade targets assertions now require ESPN-0 and no-ESPN-row players to be absent from the sell list and the rendered sell table. The engine value 0.0, badge and drawer checks (Jeremy 2026-10-07/08) are unchanged. Re-run: 2 tests OK in 27s.
- Guard proven: new subtest "Trade targets list ESPN-0 players" serves a targets.js with SELL_FLOOR=0 and the out rule removed and requires check() to be non-empty; it passed (caught). Existing mutations still pass.

### Claimed, not confirmed
- CI status of this test on main (it is in test-unit-modules, not test-core) was not checked beyond run listing.
- Without playwright installed the test errors under RENDER_TESTS_REQUIRED=1; that is the designed environment guard, not a defect.
