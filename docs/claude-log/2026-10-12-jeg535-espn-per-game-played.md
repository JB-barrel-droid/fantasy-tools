## 2026-10-12 - JEG-535: harmonize ESPN per-game basis (MR-20)

Contract: convert ESPN projections from per-team-game to per-game-played
by counting non-zero ROS weeks as the denominator, per MR-20 option (a)
defaults approved by Jeremy 2026-10-12.

### Verified (check named)
- `make validate` exits 0 (all test suites green).
- 253 targeted tests pass (all ESPN-related: test_games_remaining,
  test_espn_fidelity_jeg480, test_ddf_two_tier_leg,
  test_bake_espn_zero_universe, test_espn_pull_team_played_jeg574,
  test_espn_zeroed_staleness, test_bake_espn_intake,
  test_espn_weekly_store, test_espn_pool_cap, test_espn_listed_rows,
  test_save_espn_cbs_references, test_espn_ci_workflow,
  test_espn_player_key_join, test_rebuild_chain_bake,
  test_chart_input_coverage, test_static_export, test_view_invariants,
  test_methodology_consistency, test_derive_lineup_parameters,
  test_fidelity_espn).
- 13-combo engine dump sweep (3 scorings x 4 sizes + superflex):
  fixedPieIndexed=True and sourceScaleAgreement=None for all 13.
- Backward compatibility: old CSV without espn_projected_games column is
  handled gracefully (falls back to team games as denominator).

### Claimed, not confirmed
- The next ESPN pull will populate espn_projected_games in the CSV. Until
  then, the code falls back to team games (identical to pre-change behavior).
- Injured players will show higher per-game-played values than the old
  per-team-game values once the pull runs, harmonizing ESPN with CBS/Razzball.

### Changes
- `pipelines/pull_espn_projections.py`: count non-zero ROS weeks per
  player as `espn_projected_games`; add column to CSV; use it in sidecar
  ppg instead of team games; add `espn_expected_games` to sidecar.
- `pipelines/bake_players.py`: read `espn_projected_games` from CSV in
  fetch_espn_intake; add `espn_expected_games` to player row; use it as
  denominator for `espn_ppg` and `blend_ppg` (falls back to team games).
- `producers/build_staged_bundle_espn.py`: use `espn_projected_games`
  for per-game computation (falls back to window length).
- `docs/math-review-agenda.md`: recorded MR-20 interim defaults under
  the item.
