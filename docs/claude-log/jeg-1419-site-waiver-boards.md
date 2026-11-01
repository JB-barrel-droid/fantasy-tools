# JEG-1419 — site waiver-board build

`make sync` runs the offline weekly producer and board builder before the
optional browser-dependent explainer. Boards live in `dist/data/weekly/`:
`waiver-board-wkN-SCORING-TEAMS-sfN.json`. The index `waiver-boards.json`
and retained `waiver-boards-wkN.json` carry the site build tag, settings and
SHA-256 of each board. Board schema remains 0.1.0, with no engine changes.

All three canonical scoring keys, 8/10/12/14 teams and SF 0/1 are built.
The current board contract supports these settings, not custom roster shapes.
Weekly points remain from the named ESPN weekly leg only; absent status and
weekly data stay disabled with upstream reasons. There is no ROS fallback.

The default capture cutoff is HEAD's commit timestamp, matching sync's
commit-derived build tag. Replays can pass `--as-of` to
`pipelines/build_site_waiver_boards.py`. Identical inputs and clock give
identical bytes. Board Value uses the published chart fixture and sync's
published history, through the unchanged Python reference.

Sync preserves prior-week files in dist and restores versioned source archives
from `data/weekly/waiver-boards-wkN.json.gz`. Each build writes its current
archive with a deterministic gzip timestamp. Commit these compact archives
with weekly refreshes; clean checkouts restore the original board bytes and
build metadata. Plain archived board JSON is also supported. No pruning occurs.

Stack: based on PR #1239 at a09735ad. After that PR merges, merge origin/main
into be/JEG-1419, then retarget the draft to main; never force-push.

## Local validation (2026-10-31)

- `make validate`: failed in sync's value explainer; Playwright Chromium headless shell 1208 is absent. Board generation completed first.
- `pipelines/lib/waiver_board.py dist/data/weekly/waiver-board-wk*.json`: all 24 valid.
- Source archive: decompressed and all 24 SHA-256 hashes match its manifest.
- `tests.test_site_waiver_boards`: original full build/disabled-source/byte-stability test passed; final archive-extension run failed with ENOSPC on the second publish. Archive byte stability is therefore not confirmed.
- `tests.test_build_weekly_inputs tests.test_build_waiver_board`: 135 tests ran, one setup error in FromReference due to missing Chromium.
- `guard-harness` passed. Core spec reference passed (26 tests). Core engine suite ran 29 tests with one Chromium-related error. Additional core checks passed through test_chain_commits_legs; test_rebuild_chain_concurrent_main was interrupted.
- `value-check-compare` was interrupted after disk exhaustion. `test-integration` did not run. No unchanged command was retried automatically.
- Disk exhaustion stopped the remaining checks; no files were deleted to free space. The gate is NOT green.

Remaining core recipe commands (not run; browser-dependent commands also lack Chromium):

```sh
python3 -m unittest tests.test_promotion_model_parity
python3 -m unittest tests.test_seeded_hold_build
python3 -m unittest tests.test_rank_guard
python3 -m unittest tests.test_superflex
python3 -m unittest tests.test_superflex_publisher_values
python3 -m unittest tests.test_jeg1365_two_qb_superflex_values
python3 -m unittest tests.test_razzball_refresh
python3 -m unittest tests.test_bake_on_change
python3 -m unittest tests.test_razzball_one_save
python3 -m unittest tests.test_timestamps
python3 -m unittest tests.test_pipelines_import_standalone
python3 -m unittest tests.test_trade_chart_ingest_ci
python3 -m unittest tests.test_fc_week4_value_repair_sql
python3 -m unittest tests.test_producers_schedule_tidy
python3 -m unittest tests.test_player_scenario_matrix
python3 -m unittest tests.test_published_surfaces
python3 -m unittest tests.test_v2_targets
python3 -m unittest tests.test_verify_live
python3 -m unittest tests.test_v2_compare
python3 -m unittest tests.test_v2_finder
python3 -m unittest tests.test_v2_finder_viable
python3 -m unittest tests.test_v2_finder_guardrails
python3 -m unittest tests.test_v2_finder_saved_team tests.test_v2_finder_saved_team_render
python3 -m unittest tests.test_v2_finder_link_tabs_render
python3 -m unittest tests.test_waivers_math
python3 -m unittest tests.test_waivers_status
python3 -m unittest tests.test_player_flags
python3 -m unittest tests.test_waivers_views
python3 -m unittest tests.test_v2_copy_names
python3 -m unittest tests.test_v2_finder_trifit
python3 -m unittest tests.test_v2_finder_projection_noise
python3 -m unittest tests.test_v2_finder_triview_display
python3 -m unittest tests.test_lineup_presentation_properties
node tests/test_v2_roster_paste.js
python3 -m unittest tests.test_roster_paste_mutation_proof
node tests/test_v2_league_paste.js
node tests/test_v2_name_format.js
python3 -m unittest tests.test_v2_headlines
python3 -m unittest tests.test_v2_movers
python3 -m unittest tests.test_v2_trade_story
python3 -m unittest tests.test_v2_rescaled_copy
node tests/node/source_views_check.mjs
node tests/node/league_status_check.cjs
python3 -m unittest tests.test_v2_waterfall
python3 -m unittest tests.test_v2_examples
python3 -m unittest tests.test_compare_evidence_view_contract
python3 -m unittest tests.test_v2_phone_customize_targets_render
python3 -m unittest tests.test_v2_phone_fallback_font_render
python3 -m unittest tests.test_v2_phone_landscape_render
python3 -m unittest tests.test_v2_phone_layout_render
python3 -m unittest tests.test_v2_phone_context_row_render
python3 -m unittest tests.test_v2_hamburger_nav_render
python3 -m unittest tests.test_v2_desktop_menu_render
python3 -m unittest tests.test_v2_phone_rank_overflow_render
python3 -m unittest tests.test_v2_phone_source_links_render
python3 -m unittest tests.test_v2_phone_trade_actions_render
python3 -m unittest tests.test_v2_phone_trade_rows_render
python3 -m unittest tests.test_v2_phone_weight_render
python3 -m unittest tests.test_v2_phone_wide_font_render
python3 -m unittest tests.test_v2_phone_zoom_render
python3 -m unittest tests.test_disagreement_units_render
python3 -m unittest tests.test_main_table_engine_parity
python3 -m unittest tests.test_math_inspector
python3 -m unittest tests.test_view_invariants
python3 -m unittest tests.test_launch_front_door
python3 -m unittest tests.test_launch_copy_guard
python3 -m unittest tests.test_week_history
python3 -m unittest tests.test_asset_load_retry
python3 -m unittest tests.test_espn_listed_rows
python3 -m unittest tests.test_page_load_no_404
python3 -m unittest tests.test_missing_section_render
python3 -m unittest tests.test_bench_share_low_pie
python3 -m unittest tests.test_bench_share_readout_matches_reference
python3 -m unittest tests.test_bench_budget_cut_render
python3 -m unittest tests.test_lineup_content_week_advance
python3 -m unittest tests.test_position_weights_setter
python3 -m unittest tests.test_value_overrides
python3 -m unittest tests.test_ddf_composite_value
python3 -m unittest tests.test_view_switch_hidden_defaults
python3 -m unittest tests.test_row_missing_reasons
python3 -m unittest tests.test_search_players_universe
python3 -m unittest tests.test_source_scale_agreement_retired
python3 -m unittest tests.test_week_calendar
python3 -m unittest tests.test_week_state
python3 -m unittest tests.test_week_stale
python3 -m unittest tests.test_source_health_release
python3 -m unittest tests.test_two_qb_direction
python3 -m unittest tests.test_short_chart_waiver
python3 -m unittest tests.test_published_league_settings_engine
python3 -m unittest tests.test_value_reference_worked_example
python3 -m unittest tests.test_roster_convention
python3 -m unittest tests.test_bench_miss_rate
python3 -m unittest tests.test_roster_convention_parity
python3 -m unittest tests.test_player_tags
python3 -m unittest tests.test_contract_qa_report
python3 -m unittest tests.test_razzball_outlier_guard
python3 -m unittest tests.test_waiver_band_line
```

Next: free local disk space and provide Chromium, complete validation, then obtain independent review. Keep JEG-1419 In Progress. After #1239 merges, merge main into the branch and retarget; no idle monitoring was started.
