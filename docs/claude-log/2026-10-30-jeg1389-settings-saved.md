## 2026-10-30 - JEG-1389: a league import or share link saves its league settings (Jeremy's pick A)

Contract: Jeremy picked A on JEG-1389 (2026-10-30): when a league import or share link applies league settings, save
them the same way the settings form does, so they survive a reload. Cause named in
`docs/claude-log/2026-10-30-jeg1389-bench-switch.md`; no value math changes.

### Change
- `app/v2/v2.js` `applyLinkLeague(params, options)`: with `{save: true}` it ends with `saveLeagueSettings()` (the settings
  form's save) instead of only announcing the inputs, also when the settings were already in force. Without it (trade,
  Waivers and DDF state links) nothing changes: those settings still last for the visit only.
- `app/v2/league.js`: `applyImported` (file Load and the `#find-league?workspace=` share link) and Undo pass `{save: true}`,
  so Undo of a load also restores the saved settings.
- `.github/workflows/v2-render-test.yml`: runs both JEG-1389 render tests (the switch test was not wired before).

### Verified (check named)
- New test `tests/test_jeg1389_link_settings_reload_render.py` (RENDER_TESTS_REQUIRED=1, Google Chrome): opens the USO
  teams as a share link with USO's settings (`scoring=half_ppr&teams=12&roster=QB1.RB2.WR3.TE1.FLEX1.SF0.BN5`), reloads.
  - Before the fix: fails "after a reload: the engine does not hold USO's settings" (scoring ppr, WR 2, BENCH 7);
    Kyren Williams 44.1 drawn locally (CBS held), 45.9 with CBS shown, the live number.
  - After: OK. After the reload the engine holds half PPR, 12 teams, QB1 RB2 WR3 TE1 FLEX1 BN5, Kyren Williams
    reads the same as before the reload, and 55.8 with CBS shown.
- With the change, all OK: test_jeg1389_switch_redraw_render 1, test_v2_share_render 2, test_v2_league_render 2,
  test_v2_inputs_status_render 8, test_v2_advanced_render 2, test_v2_season_weeks_render 2, test_v2_assist_render 2,
  test_jeg1213_import 5, test_jeg1213_acceptance_render 11, test_jeg1140_settings_fieldnotes 19,
  test_jeg1140_settings_fieldnotes_render 9.
- test_v2_league_live_render `test_settings_apply_live_and_find_reprocesses` errors (timeout waiting for
  `#v2FindOut .v2-find-group`) with and without the change: the same error on a clean worktree at c7c8800b (the branch
  head before this change). Baseline red, Find a trade results, not this path; its other test passes.

### Claimed, not confirmed
- `make validate` and the full suite were not run locally; CI runs them on the PR.
- The "Use N teams in league settings" button on the league page still applies without saving (not part of pick A).
