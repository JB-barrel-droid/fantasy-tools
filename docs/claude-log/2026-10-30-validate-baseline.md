## 2026-10-30 - make validate baseline (JEG-1263)

Contract: get `make validate` green on main again. Two known reds: `test_keyboard_mobile_and_overlap_guard` and `test_render_sweep_coverage`. No change to `app/v2/v2.js` or `app/v2/shell.html` (JEG-1389 holds that lock).

### Causes
- **`test_keyboard_mobile_and_overlap_guard` (tests/test_v2_finder_saved_team_render.py): a stale test, not a page bug.** The test picked a saved team with `Home`, `ArrowDown`, `ArrowDown` on a closed `<select>`. Chrome on macOS opens a native popup on ArrowDown instead of changing the value, and Playwright cannot drive that popup, so the value stayed unchanged (`'' != 'beta'`). Linux and Windows change the value. Probe on the Mac: `Home` moves to "Current roster", then ArrowDown/Enter/Space leave the value alone. The page's change handler (`chooseSavedTeam`) is correct. Fix: a `keyboard_pick` helper that still sends the keys, and when the value did not move, makes the same choice with `select_option` (same change event). Linux CI keeps the pure keyboard path. Every assertion is unchanged. An `Escape` in the fallback collapsed the finder panel, so the helper does not send it.
- **`test_render_sweep_coverage`: seven green render modules were in no run list** (listed below), plus one red. Wired the seven into `test-render-extra` and one shard each. Also fixed a second red in `test_render_sweep_shards`: `test_jeg1231_opponent_inclusion_render` and `test_jeg1231_league_inclusion_render` were in shard 3 but not in `test-render-extra`.
- `test_uso_site_journey_render` fails alone (3 of 18: `test_guard_fails_on_a_link_without_get`, `test_journey_keeps_the_trade_context`, `test_unequal_deal_keeps_its_package`; the journey does not reach Compare for both picks, "no opportunity sends Jaxon Smith-Njigba"). Left out of the Makefile and listed in `KNOWN_RED` under JEG-1263.

### Verified (check named)
- Each wired module run alone with `python3 -m unittest tests.<name>` (RENDER_TESTS_REQUIRED=1, CHROMIUM_PATH=Google Chrome): all pass.
- `python3 -m unittest tests.test_v2_finder_saved_team_render.FinderSavedTeamRenderTest.test_keyboard_mobile_and_overlap_guard`: OK after the fix, fails before it with `'' != 'beta'`.
- `python3 -m unittest tests.test_render_sweep_coverage tests.test_render_sweep_shards`: OK.
- `make validate` (venv first on PATH, CHROMIUM_PATH=Google Chrome, RENDER_TESTS_REQUIRED unset): exit 0. With RENDER_TESTS_REQUIRED=1 it stops in `test_v2_phone_fallback_font_render`, because DejaVu Sans is not installed on this Mac; that test skips locally as designed and runs on Linux CI.

### Claimed, not confirmed
- That the unfixed test passes on Linux CI (inferred from the platform select behavior, not run there).
- The cause of the `test_uso_site_journey_render` failures; not investigated.
