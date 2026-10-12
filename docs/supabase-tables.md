# Supabase tables: who writes, who reads

Last updated: 2026-10-12 (JEG-600). Project `iskiybsimubiujwuchsl`, schema `public`: 94 tables and 30 views listed by a read-only `pg_class` query on 2026-10-12.

Method and limits: writer/reader columns come from a text scan of `pipelines/`, `producers/` and `tools/` (non-test files) for each table name, classing a file as a writer when a line naming the table has upsert/insert/POST/PATCH/on_conflict, or the file is a `save_*`/`pull_*`/`load_*`/`store_*` script. Treat it as a map to start from, not proof: generic names (`players`, `teams`, `games`, `signals`, `sports`, `leagues`) match unrelated words, and writes done through SQL migrations, pg_cron or edge functions (`supabase/functions/`) are not seen. Verified: the table and view list and the cron job list (read-only queries). Claimed: the writer/reader assignments.

Naming rules are in `docs/supabase-naming-conventions.md`; how scraped references map to tables is `docs/supabase-source-mapping.md`; the table-writer audit and guard is `docs/SUPABASE_WRITER_AUDIT.md`. Which jobs run on a schedule is in `docs/architecture-current.md` (19 pg_cron jobs, all active on 2026-10-12; no switched-off jobs remain in `cron.job`).

## Tables with a writer or reader in this repo

| Table | Written by | Read by |
|---|---|---|
| `bakes` | `build_consolidated_values.py`, `load_ddf_leg_to_supabase.py`, `save_espn_cbs_references.py`, `save_usatoday_references.py` | `bake_players.py`, `build_espn_section_from_ddf_leg.py`, `build_pipeline_checkpoints.py`, `build_week_history.py`, `check_source_vintage.py`, `fidelity_pulse.py` (+3 more) |
| `cbs_ros_projections` | `save_cbsros_references.py` | `build_github_actions_status.py`, `build_source_fidelity.py`, `build_week_history.py`, `cbsros.py`, `check_source_vintage.py`, `export_cbsros_snapshot.py` (+3 more) |
| `cbs_trade_values` | `save_espn_cbs_references.py` | `build_week_history.py`, `check_source_vintage.py`, `fidelity_pulse.py`, `import_supabase_references.py`, `verify_import_health.py` |
| `consolidated_values` | `build_consolidated_values.py`, `load_ddf_leg_to_supabase.py`, `load_value_check.py` | `export_consolidated_json.py`, `per_source_rescale.py`, `sync_dashboard_artifacts.py`, `verify_cbsros_legs_vs_fixture.py` |
| `espn_season_projections` | `save_espn_cbs_references.py` | `check_espn_bake_csv.py`, `check_source_vintage.py`, `espn.py`, `import_supabase_references.py`, `verify_import_health.py`, `writer_audit.py` |
| `external_id_map` | none found | `player_key_index.py` |
| `fidelity_divergences` | `fidelity_pulse.py` | none found |
| `fidelity_runs` | `fidelity_pulse.py` | none found |
| `fp_season_latest_norm` | none found | `annotate_cbsros_ppg.py`, `bake_players.py` |
| `fp_season_projections` | none found | `annotate_cbsros_ppg.py`, `bake_players.py` |
| `games` | `pull_espn_projections.py`, `pull_razzball_ros.py`, `save_espn_weekly.py`, `save_player_status_history.py` | `bake_players.py`, `build_cbsros_ddf_leg.py`, `build_ddf_two_tier_leg.py`, `build_espn_raw_values.py`, `build_source_fidelity.py`, `cbsros.py` (+9 more) |
| `injuries` | `save_player_status_history.py` | none found |
| `leagues` | `pull_espn_projections.py`, `save_espn_cbs_references.py` | none found |
| `loader_runs` | `load_ddf_leg_to_supabase.py` | none found |
| `nflverse_player_week_actuals` | `load_nflverse_history.py` | none found |
| `nflverse_team_weeks` | `load_nflverse_history.py` | none found |
| `per_source_cap_audit` | `load_ddf_leg_to_supabase.py`, `per_source_rescale.py` | none found |
| `pipeline_write_audit` | `save_espn_cbs_references.py`, `save_usatoday_references.py`, `writer_audit.py` | `inventory_supabase_schema.py` |
| `player_game_stats` | `save_espn_weekly.py` | `espn_weekly.py`, `export_weekly_store.py` |
| `player_identities` | none found | `legacy_identity.py` |
| `player_identity_reconcile_runs` | none found | `reconcile_player_identity.py` |
| `player_name_aliases` | none found | `build_monitoring_summary.py`, `identity_queue.py`, `monitor_alerts.py`, `player_aliases.py`, `reconcile_player_identity.py` |
| `player_status_history` | `save_player_status_history.py` | none found |
| `players` | `canonical_players.py`, `fidelity_pulse.py`, `load_ddf_leg_to_supabase.py`, `load_value_check.py`, `load_weekly_dashboard.py`, `pull_cbs_ros_projections.py` (+14 more) | `annotate_cbsros_ppg.py`, `backstop_shallow_sources.py`, `bake_players.py`, `build_aggregate_diagnostics.py`, `build_cbsros_ddf_leg.py`, `build_cbsros_section_from_ddf_leg.py` (+80 more) |
| `product_snapshot` | `publish_gate.py` | none found |
| `projection_snapshots` | `save_espn_weekly.py` | `build_week_history.py`, `export_weekly_store.py` |
| `publisher_roster_assumptions` | none found | `unified.py` |
| `publisher_translated_values` | none found | `inventory_supabase_schema.py`, `rebuild_comparison_chain.py`, `refresh_vorp_translation.py`, `unified.py`, `verify_vorp_wiring.py` |
| `publisher_vorp` | none found | `inventory_supabase_schema.py`, `unified.py` |
| `razzball_projections` | `pull_razzball_ros.py`, `save_razzball_references.py` | `bake_players.py`, `build_week_history.py`, `check_source_vintage.py`, `import_supabase_references.py`, `razzball.py`, `rebuild_comparison_chain.py` (+1 more) |
| `signals` | `load_weekly_dashboard.py` | `build_staged_bundle_espn.py`, `fidelity_pulse.py`, `source_probe.py`, `sync_dashboard_artifacts.py` |
| `source_config` | none found | `build_consolidated_values.py`, `build_reweighted_values.py`, `review_batch70_views.py` |
| `source_probe_log` | `source_probe.py` | none found |
| `source_probe_state` | `source_probe.py` | `fidelity_pulse.py` |
| `source_trade_values` | `save_fantasycalc_references.py`, `save_fantasypros_references.py`, `save_usatoday_references.py` | `build_comparison_source_section.py`, `build_pipeline_checkpoints.py`, `build_week_history.py`, `check_source_vintage.py`, `fidelity_pulse.py`, `import_supabase_references.py` (+6 more) |
| `source_value_adjustments` | none found | `dataset_status.py`, `inventory_supabase_schema.py` |
| `sports` | `pull_espn_projections.py` | `fidelity_pulse.py` |
| `teams` | `build_consolidated_values.py`, `load_ddf_leg_to_supabase.py`, `load_nflverse_history.py`, `load_value_check.py`, `pull_espn_projections.py`, `pull_fantasycalc_12team.py` (+1 more) | `backstop_shallow_sources.py`, `bake_players.py`, `build_cbsros_ddf_leg.py`, `build_cbsros_section_from_ddf_leg.py`, `build_comparison_source_section.py`, `build_ddf_groups.py` (+50 more) |
| `value_check_runs` | `load_value_check.py` | none found |
| `value_check_values` | `load_value_check.py` | none found |
| `weekly_dashboard_runs` | `load_weekly_dashboard.py` | none found |
| `weekly_dashboard_signals` | `load_weekly_dashboard.py` | none found |

## Tables with no reference in the repo pipelines

These exist in `public` but no non-test pipeline, producer or tool file names them. They are legacy (lottery, Vegas, waiver, handicapper, Yahoo, DFS) or are written only by migrations/cron/edge code. Do not drop any without a read-only check of row counts and the `supabase/` and `sql/` folders first.

`blended_calibration`, `blended_player_map`, `blended_source_confidence`, `data_sources`, `dfs_salaries`, `espn_fetch_config`, `fantasy_salaries`, `fantasy_sites`, `fantasy_slates`, `game_weather`, `gate_audits`, `handicapper_picks`, `handicappers`, `live_page_checks`, `lottery_breakout_labels`, `lottery_league_profiles`, `lottery_model_runs`, `lottery_paths`, `lottery_player_features`, `lottery_predictions`, `lottery_valuations`, `news_items`, `no_market_read_flags`, `odds_history`, `pipeline_cron_log`, `pipeline_cron_state`, `player_canonical_map`, `player_identity_aliases`, `player_ppg_legs`, `player_value_notes`, `player_values_tier_prices`, `post_queue`, `product_options`, `ranker_performance`, `ranker_rankings`, `rankers`, `risk_tilts`, `season_actuals_ytd`, `sleeper_season_latest_norm`, `sportsbooks`, `trade_watch`, `trending`, `vegas_player_map`, `vegas_season_totals`, `venues`, `waiver_trends`, `weekly_no_market_read_flags`, `weekly_source_snapshots`, `yahoo_leagues`, `yahoo_rostered_snapshot`, `yahoo_rosters`, `yahoo_teams`

## What we use Supabase for, and why

- Postgres as the store of record for scraped source rows, so every rebuild reads one durable snapshot instead of a laptop's files (JEG-392, and the source stores in JEG-521: ESPN weekly, player-status history, 2015-2025 nflverse history).
- pg_cron as the scheduler that dispatches the workflows; 19 jobs, listed in `docs/architecture-current.md`.
- Monitoring history tables (`source_probe_*`, `fidelity_*`, `value_check_*`, `pipeline_write_audit`) so the ops page has run history without scraping workflow logs.
- Not used: auth, storage, realtime, or edge functions as a runtime for the site. The site never calls Supabase.

The earlier 744-line features recommendation (JEG-110) is archived at `archive/2026-10-12-docs/supabase-features-recommendation.md`.

## Views

Views are defined in `sql/` and `supabase/migrations/`. Repo code reads three of them: `fidelity_pulse_history` (`modules/status.html`), `player_identity_unresolved_v` (`pipelines/build_ops_status.py`) and `v_current_weekly_signals` (`pipelines/load_weekly_dashboard.py`). The other views have no reader in the repo (consolidation, fidelity, identity-map and VORP views may be used ad hoc or by SQL); the `v_*` signals, waiver, Vegas, props and lottery views belong to retired products.
