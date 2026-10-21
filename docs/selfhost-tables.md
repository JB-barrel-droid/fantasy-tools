# Self-host migration: table classification (JEG-792)

Built 2026-10-21 for the move of the data store from cloud Supabase project `iskiybsimubiujwuchsl` (Postgres 17.6) to the Mac mini (lane A: `selfhost/supabase/`; this lane: `selfhost/migrate/`). Machine-readable copy: `selfhost/migrate/tables.json`; `selfhost/migrate/check_classification.py` fails the export if the cloud has a relation that is not classified there.

## How this was built

- **Inventory (verified).** Read-only queries through the Supabase MCP on 2026-10-21: `pg_class` (kind, `reltuples` row estimate, `pg_total_relation_size`), `information_schema.tables`, `pg_proc`, `pg_depend` (view dependencies), `pg_constraint` (foreign keys), `cron.job`, `vault.secrets` (names only). `information_schema.tables` for public, api, monitoring, ops, ross, archive returns **165 relations**; the md5 of the sorted list matches the list classified here (`fee512ed2e6060d1ce2955a40787241d`).
- **Counts.** public holds 100 tables and 30 views (the ticket said 130 public tables; the catalog shows the number here). api holds the 12 views. Row figures are planner estimates (`reltuples`; 0 can mean "never analyzed", e.g. `teams`); exact counts are taken at export time into `counts.tsv`. Size is table + indexes + TOAST.
- **Evidence (claimed from a text scan).** `grep -rlP "\bNAME\b"` over `pipelines tools .github/workflows producers scripts modules bin app Makefile` (tests and archive excluded), plus a separate scan of `sql/` and `supabase/`. Generic names (`players`, `teams`, `games`, `rosters`, `injuries`, `signals`, `anomalies`, `health`) match ordinary words, so for those the class rests on the specific call named in the Basis column (for example `sbclient.get_all("players")`), not on the hit count. `p/` = `pipelines/`, `wf/` = `.github/workflows/`.
- **Dependency.** A table or view with no caller of its own is classed with the object that needs it: an FK parent, the base table of a migrated view, or a table a migrated function writes.

## What moves

| Class | Tables | Views | Data migrated | Meaning |
|---|---|---|---|---|
| `chain` | 41 | 18 | yes | read or written by rebuild-chain, savers, loaders, fidelity pulse, bake, identity reconcile, source probes (or a dependency of such an object). Data migrated. |
| `dashboard-other` | 14 | 8 | yes | weekly dashboard, player trace, status history, nflverse history, ESPN weekly store, monitoring summary. Data migrated. |
| `other-app` | 53 | 16 | no | not referenced by this repo. Structure migrated in public (views and FKs need it), data NOT migrated; Jeremy decides. |
| `skip` | 12 | 3 | no | logs, backups, retired ops monitoring, archive schema. Structure migrated in public/api/monitoring/ops, data not. |

Tables carrying data: 55, about 210.9 MB on disk in the cloud including indexes (the dump moves table data only, so egress is lower). `value_check_values` (497.6 MB, about 1.25M rows) is created empty: `api.player_values` and `api.value_check_diff` are views over it, so its structure must exist.

Structure: every table, view, function, trigger, enum, sequence, RLS policy and grant in **public, api, monitoring, ops** is restored, including the other-app and skip tables (empty), because 16 public views and 30+ foreign keys reference them; dropping them would break the restore. **ross** and **archive** are not dumped at all.

Functions (35 in the four schemas) are listed in `tables.json` under `functions` with the same classes. All are restored with their schema; `cron_and_functions.sql` re-applies the two dispatch functions on their own.

## `chain`

| Relation | Kind | Est. rows | Size | Basis | Evidence (code; sql) |
|---|---|---|---|---|---|
| `public.bakes` | table | 991 | 392.0 kB | code | `wf/bake-players.yml`, `wf/loader-dry-run.yml`, `wf/rebuild-chain.yml`, `p/bake_players.py` (+12); sql: `sql/contract/api_publish_gate.sql`, `sql/migrations/004_source_trade_values_bake_version.sql` |
| `public.cbs_ros_projections` | table | 5,125 | 3.5 MB | code | `wf/cbsros-supabase-sync.yml`, `p/build_github_actions_status.py`, `p/build_source_fidelity.py`, `p/build_week_history.py` (+8); sql: `sql/contract/api_v1.sql`, `sql/migrations/002_cbs_ros_projections.sql` |
| `public.cbs_trade_values` | table | 3,204 | 1.9 MB | code | `wf/rebuild-chain.yml`, `p/build_week_history.py`, `p/check_source_vintage.py`, `p/fidelity_pulse.py` (+5); sql: `sql/migrations/001_FINDINGS_AND_PLAN.md`, `sql/migrations/001_pipeline_write_audit_repair.sql` |
| `public.consolidated_values` | table | 76,529 | 56.3 MB | code | `wf/cbsros-consolidation-load.yml`, `wf/loader-dry-run.yml`, `wf/rebuild-chain.yml`, `modules/consolidation.html` (+8); sql: `sql/consolidated_values.sql`, `sql/contract/api_publish_gate.sql` |
| `public.draftsharks_trade_values` | table | 917 | 1.6 MB | code | `wf/draftsharks-supabase-sync.yml`, `p/fidelity_sources/draftsharks.py`, `p/save_draftsharks_references.py`; sql: `sql/migrations/008_draftsharks_trade_values.sql`, `sql/migrations/010_keeptradecut_trade_values.sql` |
| `public.dynasty_daddy_trade_values` | table | 0 | 32.0 kB | code (saver) | `p/save_dynasty_daddy_references.py`; sql: `sql/migrations/013_dynasty_daddy_trade_values.sql` |
| `public.espn_season_projections` | table | 971 | 584.0 kB | code | `p/check_espn_bake_csv.py`, `p/check_source_vintage.py`, `p/fidelity_sources/espn.py`, `p/import_supabase_references.py` (+5); sql: `sql/contract/api_v1.sql`, `sql/migrations/001_FINDINGS_AND_PLAN.md` |
| `public.fantasysharks_projections` | table | 0 | 32.0 kB | code | `wf/fantasysharks-supabase-sync.yml`, `p/fidelity_sources/fantasysharks.py`, `p/save_fantasysharks_references.py`; sql: `sql/migrations/009_fantasysharks_projections.sql`, `sql/migrations/012_numberfire_ros_projections.sql` |
| `public.fidelity_divergences` | table | 1,437 | 640.0 kB | code | `wf/fidelity-pulse.yml`, `p/fidelity_pulse.py`; sql: `supabase/migrations/jeg480_fidelity_pulse.sql` |
| `public.fidelity_runs` | table | 973 | 2.3 MB | code | `wf/fidelity-pulse.yml`, `p/fidelity_pulse.py`; sql: `supabase/migrations/jeg480_fidelity_pulse.sql` |
| `public.fp_season_latest_norm` | table | 539 | 248.0 kB | code (bake_players.py) | `p/annotate_cbsros_ppg.py`, `p/bake_players.py` |
| `public.fp_season_projections` | table | 9,598 | 3.2 MB | code (bake_players.py) | `p/annotate_cbsros_ppg.py`, `p/bake_players.py` |
| `public.games` | table | 816 | 664.0 kB | code: sb.get_all("games") in save_espn_weekly.py, export_weekly_store.py; FK parent | `app/trade-value-chart/index.html`, `app/v2/finder.js`, `app/v2/shell.html`, `p/bake_players.py` (+29); sql: `sql/migrations/009_fantasysharks_projections.sql`, `sql/proposed/jeg525_nflverse_history.sql` |
| `public.keeptradecut_trade_values` | table | 0 | 32.0 kB | code (saver) | `p/save_keeptradecut_references.py`; sql: `sql/migrations/010_keeptradecut_trade_values.sql` |
| `public.leagues` | table | 0 | 48.0 kB | dependency: FK parent of players/teams/games; written by pull_espn_projections.py | `app/trade-value-chart/assets/product-data.js`, `app/trade-value-chart/assets/value-model.js`, `app/v2/finder.js`, `app/v2/shell.html` (+6) |
| `public.loader_runs` | table | 0 | 48.0 kB | code | `p/load_ddf_leg_to_supabase.py` |
| `public.numberfire_ros_projections` | table | 0 | 32.0 kB | code (saver) | `p/save_numberfire_ros_references.py`; sql: `sql/migrations/012_numberfire_ros_projections.sql` |
| `public.per_source_cap_audit` | table | 0 | 64.0 kB | code | `p/caps/per_source_rescale.py`, `p/load_ddf_leg_to_supabase.py`; sql: `sql/migrations/007_per_source_cap_audit.sql` |
| `public.pipeline_write_audit` | table | 78 | 152.0 kB | code (pipelines/lib/writer_audit.py, savers) | `p/inventory_supabase_schema.py`, `p/lib/writer_audit.py`, `p/save_espn_cbs_references.py`, `p/save_usatoday_references.py` (+2); sql: `sql/migrations/001_FINDINGS_AND_PLAN.md`, `sql/migrations/001_pipeline_write_audit_repair.sql` |
| `public.player_identities` | table | 529 | 240.0 kB | code (pipelines/lib/legacy_identity.py) | `p/lib/legacy_identity.py` |
| `public.player_identity_reconcile_runs` | table | 0 | 32.0 kB | code (reconcile_player_identity.py) | `p/reconcile_player_identity.py` |
| `public.player_name_aliases` | table | 602 | 344.0 kB | code (identity reconcile) | `wf/player-identity-reconcile.yml`, `p/build_monitoring_summary.py`, `p/lib/identity_queue.py`, `p/lib/player_aliases.py` (+2); sql: `supabase/migrations/archive_fp_kdst_20261008.sql`, `supabase/migrations/jeg438_alias_table_curated.sql` |
| `public.player_ppg_legs` | table | 0 | 16.0 kB | dependency: base of api.players; 0 rows | none |
| `public.player_values_tier_prices` | table | 0 | 24.0 kB | dependency: base of api.player_values, read by api.gate_source_freshness | none; sql: `sql/contract/api_publish_gate.sql`, `sql/contract/api_v1.sql` |
| `public.players` | table | 4,644 | 3.1 MB | code: sbclient.get_all("players") in every saver, reconcile, loaders; sync_sleeper_players.py writes | `wf/bake-players.yml`, `wf/espn-supabase-sync.yml`, `wf/health-artifacts.yml`, `wf/loader-dry-run.yml` (+165); sql: `sql/contract/api_publish_gate.sql`, `sql/contract/api_v1.sql` |
| `public.product_options` | table | 0 | 32.0 kB | dependency: api.run_publish_gate / api.player_values | `app/trade-value-chart/assets/product-data.js`; sql: `sql/contract/api_publish_gate.sql`, `sql/contract/api_v1.sql` |
| `public.product_snapshot` | table | 1 | 80.0 kB | code (pipelines/publish_gate.py via api.product_snapshot) | `app/trade-value-chart/assets/comparison-dashboard.js`, `app/trade-value-chart/assets/curve-widget.js`, `app/trade-value-chart/assets/product-data.js`, `p/publish_gate.py`; sql: `sql/contract/api_publish_gate.sql`, `sql/contract/api_v1.sql` |
| `public.projection_snapshots` | table | 106,415 | 36.3 MB | code (build_week_history.py in rebuild-chain.yml; save_espn_weekly.py) | `wf/espn-weekly-store.yml`, `p/build_week_history.py`, `p/export_weekly_store.py`, `p/save_espn_weekly.py` (+1); sql: `supabase/migrations/jeg521_g4_weekly_store_20261009.sql`, `supabase/migrations/players_merge_audric_estime_20261008.sql` |
| `public.publisher_roster_assumptions` | table | 168 | 128.0 kB | code (vorp_translation/unified.py) | `p/vorp_translation/unified.py`; sql: `supabase/migrations/jeg62_vorp_translation.sql` |
| `public.publisher_translated_values` | table | 6,596 | 2.0 MB | code (rebuild_comparison_chain.py) | `p/inventory_supabase_schema.py`, `p/rebuild_comparison_chain.py`, `p/refresh_vorp_translation.py`, `p/verify_vorp_wiring.py` (+1); sql: `supabase/migrations/archive_stale_vorp_grains_20261008.sql`, `supabase/migrations/jeg62_vorp_translation.sql` |
| `public.publisher_vorp` | table | 8,636 | 2.8 MB | code (vorp_translation/unified.py) | `p/inventory_supabase_schema.py`, `p/vorp_translation/unified.py`; sql: `supabase/migrations/jeg62_vorp_translation.sql` |
| `public.razzball_projections` | table | 9,595 | 8.9 MB | code | `wf/razzball-supabase-sync.yml`, `app/trade-value-chart/index.html`, `p/bake_players.py`, `p/build_week_history.py` (+7); sql: `sql/contract/api_v1.sql`, `sql/migrations/003_razzball_projections.sql` |
| `public.rotoballer_trade_values` | table | 0 | 32.0 kB | code (saver) | `p/save_rotoballer_references.py`; sql: `sql/migrations/011_rotoballer_trade_values.sql` |
| `public.source_config` | table | 0 | 32.0 kB | code (build_consolidated_values.py); FK parent of consolidated_values | `p/build_consolidated_values.py`, `p/build_reweighted_values.py`, `p/review_batch70_views.py`; sql: `supabase/migrations/jeg377_jeg380_api_mirror.sql`, `supabase/migrations/jeg479_value_check.sql` |
| `public.source_probe_log` | table | 584 | 320.0 kB | code (source_probe.py); small run log kept | `p/source_probe.py`; sql: `supabase/migrations/source_probe_tables_20261008.sql` |
| `public.source_probe_state` | table | 7 | 32.0 kB | code (source_probe.py, fidelity_pulse.py) | `wf/source-probe.yml`, `p/fidelity_pulse.py`, `p/source_probe.py`; sql: `supabase/migrations/source_probe_tables_20261008.sql` |
| `public.source_trade_values` | table | 69,784 | 42.5 MB | code | `wf/fantasycalc-weekly-save.yml`, `wf/rebuild-chain.yml`, `p/build_comparison_source_section.py`, `p/build_pipeline_checkpoints.py` (+15); sql: `sql/migrations/001_FINDINGS_AND_PLAN.md`, `sql/migrations/001_pipeline_write_audit_repair.sql` |
| `public.source_value_adjustments` | table | 66 | 120.0 kB | code (pipelines/lib/dataset_status.py) | `p/inventory_supabase_schema.py`, `p/lib/dataset_status.py` |
| `public.sports` | table | 0 | 48.0 kB | dependency: FK parent of leagues; pull_espn_projections.py | `p/fidelity_pulse.py`, `p/pull_espn_projections.py`; sql: `supabase/functions/usatoday-fetch/index.ts`, `supabase/migrations/cbs_bakes_source_urls_20261008.sql` |
| `public.teams` | table | 0 | 48.0 kB | code: sb.get_all("teams") in sync_sleeper_players.py, save_espn_weekly.py; FK parent | `wf/cbsros-consolidation-load.yml`, `wf/fantasycalc-weekly-save.yml`, `Makefile`, `app/inspector/math-inspector.js` (+96); sql: `sql/consolidated_values.sql`, `sql/contract/api_v1.sql` |
| `public.value_check_runs` | table | 51 | 2.4 MB | code (load_value_check.py in rebuild-chain.yml) | `p/load_value_check.py`; sql: `supabase/migrations/jeg479_value_check.sql` |
| `api.player_values` | view |  |  | read by pipelines/load_value_check.py and rebuild-chain.yml (value check step) | `wf/rebuild-chain.yml`, `app/trade-value-chart/assets/comparison-dashboard.js`, `app/trade-value-chart/assets/product-data.js`, `p/build_consolidated_values.py` (+1); sql: `sql/contract/api_v1.sql`, `sql/contract/api_v1_grants_stage2.sql` |
| `api.players` | view |  |  | dependency: view over public.players/teams/product_snapshot/player_ppg_legs; no direct caller (grep hits are the word "players") | `wf/bake-players.yml`, `wf/espn-supabase-sync.yml`, `wf/health-artifacts.yml`, `wf/loader-dry-run.yml` (+165); sql: `sql/contract/api_publish_gate.sql`, `sql/contract/api_v1.sql` |
| `api.product_options` | view |  |  | dependency of api.run_publish_gate (pipelines/publish_gate.py) | `app/trade-value-chart/assets/product-data.js`; sql: `sql/contract/api_publish_gate.sql`, `sql/contract/api_v1.sql` |
| `api.product_snapshot` | view |  |  | read by pipelines/publish_gate.py | `app/trade-value-chart/assets/comparison-dashboard.js`, `app/trade-value-chart/assets/curve-widget.js`, `app/trade-value-chart/assets/product-data.js`, `p/publish_gate.py`; sql: `sql/contract/api_publish_gate.sql`, `sql/contract/api_v1.sql` |
| `api.product_snapshot_history` | view |  |  | dependency: view over public.product_snapshot; no caller | none; sql: `sql/contract/api_publish_gate.sql` |
| `api.source_freshness` | view |  |  | read by pipelines/publish_gate.py | `p/publish_gate.py`; sql: `sql/contract/api_publish_gate.sql`, `supabase/migrations/jeg377_jeg380_api_mirror.sql` |
| `api.source_input_weeks` | view |  |  | dependency: view over api.source_inputs_weekly; no caller | none; sql: `supabase/migrations/jeg432_r4_source_inputs_weekly.sql` |
| `api.source_inputs_weekly` | view |  |  | read by pipelines/build_week_history.py (rebuild-chain.yml) | `p/build_week_history.py`; sql: `supabase/migrations/cbs_bakes_source_urls_20261008.sql`, `supabase/migrations/jeg432_r4_source_inputs_weekly.sql` |
| `api.value_check_diff` | view |  |  | read by pipelines/load_value_check.py (rebuild-chain.yml). Base table value_check_values arrives empty, so this view is empty until the next value check | `wf/rebuild-chain.yml`, `p/load_value_check.py`; sql: `supabase/migrations/jeg479_value_check.sql`, `supabase/migrations/jeg479_value_check_monitoring.sql` |
| `api.value_check_latest` | view |  |  | dependency: view over value_check_runs; no caller | none; sql: `supabase/migrations/jeg479_value_check.sql` |
| `public.consolidated_sources_available` | view |  |  | dependency: view over consolidated_values; no caller | none; sql: `sql/consolidated_values.sql` |
| `public.consolidated_weeks_available` | view |  |  | dependency: view over consolidated_values; no caller | none; sql: `sql/consolidated_values.sql` |
| `public.fidelity_latest_run` | view |  |  | dependency: view over fidelity_runs; no caller | none |
| `public.fidelity_pulse_history` | view |  |  | read by modules/status.html | `modules/status.html`; sql: `supabase/migrations/jeg480_fidelity_pulse.sql` |
| `public.fidelity_pulse_latest` | view |  |  | dependency: view over fidelity_runs; no caller | none; sql: `supabase/migrations/jeg480_fidelity_pulse.sql` |
| `public.fidelity_run_counts` | view |  |  | dependency: view over fidelity_divergences; no caller | none |
| `public.v_fp_season_latest` | view |  |  | dependency: view over fp_season_projections; no caller | none |
| `public.v_source_trade_values_wide` | view |  |  | dependency: view over source_trade_values; no caller | none |

## `dashboard-other`

| Relation | Kind | Est. rows | Size | Basis | Evidence (code; sql) |
|---|---|---|---|---|---|
| `monitoring.check_config` | table | 19 | 72.0 kB | read by pipelines/audit_monitoring_coverage.py; FK parent of check_observations | `p/audit_monitoring_coverage.py`; sql: `supabase/migrations/20261008_live_page_synthetic_schedule.sql`, `supabase/migrations/20261008_monitoring_6h_and_posture.sql` |
| `monitoring.check_heartbeats` | table | 30 | 88.0 kB | read by pipelines/build_monitoring_summary.py (health-artifacts.yml) | `p/build_monitoring_summary.py`; sql: `supabase/migrations/20261008_monitoring_6h_and_posture.sql`, `supabase/migrations/20261008_security_lockdown.sql` |
| `monitoring.check_observations` | table | 3,396 | 1.1 MB | written via RPC public.monitoring_record_observation from record_monitor_check.py, reconcile_player_identity.py and most sync workflows | `wf/cbsros-supabase-sync.yml`, `wf/espn-supabase-sync.yml`, `wf/fidelity-pulse.yml`, `wf/health-artifacts.yml` (+10); sql: `supabase/migrations/20261008_live_page_synthetic_schedule.sql`, `supabase/migrations/20261008_monitoring_6h_and_posture.sql` |
| `monitoring.cron_check_map` | table | 0 | 48.0 kB | dependency of monitoring.record_cron_observations; FK to check_config | none; sql: `supabase/migrations/20261008_monitoring_6h_and_posture.sql`, `supabase/migrations/monitoring_coverage_20261007.sql` |
| `monitoring.scheduler_heartbeats` | table | 22 | 64.0 kB | written by public.monitoring_record_observation | none; sql: `supabase/migrations/20261008_monitoring_6h_and_posture.sql`, `supabase/migrations/20261008_security_lockdown.sql` |
| `public.injuries` | table | 1,216 | 648.0 kB | written by pipelines/save_player_status_history.py (status history) | `app/trade-value-chart/assets/curve-widget.js`, `app/v2/shell.html`, `app/v2/v2.js`, `p/save_player_status_history.py`; sql: `supabase/migrations/jeg521_g4_weekly_store_20261009.sql` |
| `public.live_page_checks` | table | 0 | 8.0 kB | written by live-page-synthetic.yml; base of monitoring.v_check_observations | `wf/live-page-synthetic.yml`; sql: `sql/consolidated_values.sql`, `supabase/migrations/20261008_security_lockdown.sql` |
| `public.nflverse_player_week_actuals` | table | 61,977 | 10.7 MB | code (load_nflverse_history.py) | `wf/nflverse-history-load.yml`, `p/load_nflverse_history.py`; sql: `sql/proposed/jeg525_nflverse_history.sql`, `supabase/migrations/jeg532_nflverse_history_20261010.sql` |
| `public.nflverse_team_weeks` | table | 5,790 | 440.0 kB | code (load_nflverse_history.py) | `wf/nflverse-history-load.yml`, `p/load_nflverse_history.py`; sql: `sql/proposed/jeg525_nflverse_history.sql`, `supabase/migrations/jeg532_nflverse_history_20261010.sql` |
| `public.player_game_stats` | table | 41,079 | 21.1 MB | code (save_espn_weekly.py, espn-weekly-store.yml) | `wf/espn-weekly-store.yml`, `p/export_weekly_store.py`, `p/lib/espn_weekly.py`, `p/save_espn_weekly.py`; sql: `sql/proposed/jeg525_nflverse_history.sql`, `supabase/migrations/jeg521_g4_weekly_store_20261009.sql` |
| `public.player_status_history` | table | 10,497 | 2.3 MB | code (save_player_status_history.py) | `wf/player-status-history.yml`, `p/save_player_status_history.py`; sql: `supabase/migrations/jeg521_g4_weekly_store_20261009.sql` |
| `public.signals` | table | 0 | 32.0 kB | code (load_weekly_dashboard.py, weekly-dashboard-load.yml) | `wf/pages.yml`, `wf/preview.yml`, `wf/weekly-dashboard-load.yml`, `modules/status.html` (+7); sql: `sql/contract/weekly_dashboard_api_contract.sql`, `sql/contract/weekly_dashboard_promote_rpc.sql` |
| `public.weekly_dashboard_runs` | table | 5 | 96.0 kB | code (load_weekly_dashboard.py) | `wf/weekly-dashboard-load.yml`, `p/load_weekly_dashboard.py`; sql: `sql/contract/api_v1_grants_stage2.sql`, `sql/contract/weekly_dashboard_api_contract.sql` |
| `public.weekly_dashboard_signals` | table | 1,182 | 3.1 MB | code (load_weekly_dashboard.py) | `wf/weekly-dashboard-load.yml`, `p/load_weekly_dashboard.py`; sql: `sql/contract/api_v1_grants_stage2.sql`, `sql/contract/weekly_dashboard_api_contract.sql` |
| `api.v_current_weekly_signals` | view |  |  | read by pipelines/load_weekly_dashboard.py | `p/load_weekly_dashboard.py`; sql: `sql/contract/api_v1_grants_stage2.sql`, `sql/contract/weekly_dashboard_api_contract.sql` |
| `api.weekly_dashboard_status` | view |  |  | read by scripts/check_weekly_freshness.py (weekly-dashboard-load.yml) | `scripts/check_weekly_freshness.py`; sql: `sql/contract/weekly_dashboard_api_contract.sql` |
| `monitoring.v_check_observations` | view |  |  | dependency of public.monitoring_summary (build_monitoring_summary.py) | none; sql: `supabase/migrations/20261008_monitoring_6h_and_posture.sql`, `supabase/migrations/jeg339_monitoring_schema.sql` |
| `public.nflverse_v_player_week_actuals_all` | view |  |  | dependency: view over nflverse + player_game_stats; no caller | none; sql: `sql/proposed/jeg525_nflverse_history.sql`, `supabase/migrations/jeg532_nflverse_history_20261010.sql` |
| `public.player_identity_unresolved_v` | view |  |  | read by pipelines/build_ops_status.py (health-artifacts.yml) | `p/build_ops_status.py`; sql: `supabase/migrations/archive_fp_kdst_20261008.sql` |
| `public.v_current_weekly_signals` | view |  |  | read by pipelines/load_weekly_dashboard.py | `p/load_weekly_dashboard.py`; sql: `sql/contract/api_v1_grants_stage2.sql`, `sql/contract/weekly_dashboard_api_contract.sql` |
| `public.v_player_game_actuals` | view |  |  | read by derive_lineup_parameters.py, export_weekly_store.py, score_lineup_values.py | `wf/espn-weekly-store.yml`, `p/derive_lineup_parameters.py`, `p/export_weekly_store.py`, `p/lib/espn_weekly.py` (+2); sql: `sql/proposed/jeg525_nflverse_history.sql`, `supabase/migrations/jeg521_g4_weekly_store_20261009.sql` |
| `public.v_player_week_projections` | view |  |  | dependency: view over projection_snapshots; no caller | none |

## `other-app`

| Relation | Kind | Est. rows | Size | Basis | Evidence (code; sql) |
|---|---|---|---|---|---|
| `public.blended_calibration` | table | 115 | 72.0 kB | no reference; base of v_blended_season_vorp (Vegas/blend product) | none |
| `public.blended_player_map` | table | 539 | 200.0 kB | no reference | none |
| `public.blended_source_confidence` | table | 4 | 32.0 kB | no reference | none |
| `public.data_sources` | table | 0 | 48.0 kB | no reference; FK parent of external_id_map only | none |
| `public.dfs_salaries` | table | 746 | 344.0 kB | no reference (DFS) | none |
| `public.espn_fetch_config` | table | 0 | 24.0 kB | no reference | none |
| `public.external_id_map` | table | 11,533 | 2.4 MB | only a comment in pipelines/lib/player_key_index.py says it is NOT used; no reader | `p/lib/player_key_index.py` |
| `public.fantasy_salaries` | table | 0 | 24.0 kB | no reference (DFS) | none |
| `public.fantasy_sites` | table | 0 | 32.0 kB | no reference (DFS) | none |
| `public.fantasy_slates` | table | 0 | 16.0 kB | no reference (DFS) | none |
| `public.game_weather` | table | 54 | 48.0 kB | no reference | none |
| `public.handicapper_picks` | table | 0 | 24.0 kB | no reference | none |
| `public.handicappers` | table | 0 | 16.0 kB | no reference | none |
| `public.lottery_breakout_labels` | table | 0 | 24.0 kB | no reference (lottery model) | none |
| `public.lottery_league_profiles` | table | 0 | 48.0 kB | no reference (lottery model) | none |
| `public.lottery_model_runs` | table | 0 | 80.0 kB | no reference (lottery model) | none |
| `public.lottery_paths` | table | 639 | 488.0 kB | no reference (lottery model) | none |
| `public.lottery_player_features` | table | 348 | 704.0 kB | no reference (lottery model) | none |
| `public.lottery_predictions` | table | 16,102 | 6.2 MB | no reference (lottery model) | none |
| `public.lottery_valuations` | table | 696 | 3.2 MB | no reference (lottery model) | none |
| `public.news_items` | table | 31,425 | 28.5 MB | no reference (player news) | none |
| `public.no_market_read_flags` | table | 28 | 152.0 kB | no reference | none |
| `public.odds_history` | table | 16,475 | 6.9 MB | no reference (odds) | none |
| `public.player_canonical_map` | table | 3,029 | 864.0 kB | no reference; base of v_blended_season_vorp | none |
| `public.player_identity_aliases` | table | 597 | 312.0 kB | no code reference; used by resolve_weekly_identities() and v_player_identity_map | none |
| `public.player_value_notes` | table | 5,700 | 5.3 MB | no reference | none |
| `public.post_queue` | table | 270 | 216.0 kB | no reference | none |
| `public.ranker_performance` | table | 2 | 48.0 kB | no reference (ranker) | none |
| `public.ranker_rankings` | table | 3,785 | 1.5 MB | no reference (ranker) | none |
| `public.rankers` | table | 0 | 48.0 kB | no reference (ranker) | none |
| `public.risk_tilts` | table | 0 | 64.0 kB | no reference | none |
| `public.season_actuals_ytd` | table | 1,047 | 344.0 kB | no reference (Vegas/blend) | none |
| `public.sleeper_season_latest_norm` | table | 3,029 | 1.1 MB | no reference (blend) | none |
| `public.sportsbooks` | table | 0 | 64.0 kB | no reference (odds) | none |
| `public.trade_watch` | table | 60 | 48.0 kB | no reference (Yahoo) | none |
| `public.trending` | table | 700 | 216.0 kB | no reference | none |
| `public.vegas_player_map` | table | 115 | 80.0 kB | no reference (Vegas) | none |
| `public.vegas_season_totals` | table | 372 | 240.0 kB | no reference (Vegas) | none |
| `public.venues` | table | 47 | 32.0 kB | no reference | none |
| `public.waiver_trends` | table | 12,794 | 7.6 MB | no reference (waiver) | none |
| `public.weekly_no_market_read_flags` | table | 0 | 32.0 kB | written only by api.ingest_weekly_snapshots (no caller); 0 rows | none; sql: `supabase/migrations/jeg377_jeg380_api_mirror.sql` |
| `public.weekly_source_snapshots` | table | 7,793 | 6.2 MB | AMBIGUOUS: defined by this repo (sql/migrations/007_never_blend_trigger.sql, supabase/migrations/jeg377_jeg380_api_mirror.sql) but no code reads or writes it | none; sql: `sql/migrations/007_never_blend_trigger.sql`, `supabase/migrations/jeg377_jeg380_api_mirror.sql` |
| `public.yahoo_leagues` | table | 0 | 32.0 kB | no reference (Yahoo league) | none |
| `public.yahoo_rostered_snapshot` | table | 347 | 104.0 kB | no reference (Yahoo league) | none |
| `public.yahoo_rosters` | table | 360 | 168.0 kB | no reference (Yahoo league) | none |
| `public.yahoo_teams` | table | 0 | 48.0 kB | no reference (Yahoo league) | none |
| `ross.draft_results` | table | 168 | 64.0 kB | ross schema = Ross keeper league app; no reference in this repo | none |
| `ross.keeper_contracts` | table | 177 | 64.0 kB | ross schema; no reference | none |
| `ross.keeper_declarations` | table | 28 | 32.0 kB | ross schema; no reference | none |
| `ross.league_settings` | table | 0 | 32.0 kB | ross schema; no reference | none |
| `ross.player_values` | table | 174 | 80.0 kB | ross schema; grep hits are api.player_values, not ross.* | `wf/rebuild-chain.yml`, `app/trade-value-chart/assets/comparison-dashboard.js`, `app/trade-value-chart/assets/product-data.js`, `p/build_consolidated_values.py` (+1); sql: `sql/contract/api_v1.sql`, `sql/contract/api_v1_grants_stage2.sql` |
| `ross.rosters` | table | 174 | 80.0 kB | ross schema; grep hits are the word "rosters" | `wf/fantasycalc-weekly-save.yml`, `app/v2/finder.js`, `app/v2/v2.js`, `modules/dashboard.html` (+8) |
| `ross.teams` | table | 0 | 32.0 kB | ross schema; grep hits are public.teams / the word "teams" | `wf/cbsros-consolidation-load.yml`, `wf/fantasycalc-weekly-save.yml`, `Makefile`, `app/inspector/math-inspector.js` (+96); sql: `sql/consolidated_values.sql`, `sql/contract/api_v1.sql` |
| `public.v_blended_season_vorp` | view |  |  | view over other-app tables | none |
| `public.v_latest_signals` | view |  |  | view over post_queue (retired) | none |
| `public.v_line_movement` | view |  |  | odds view | none |
| `public.v_lottery_board` | view |  |  | lottery view | none |
| `public.v_no_market_read_latest` | view |  |  | view over no_market_read_flags | none |
| `public.v_player_identity_map` | view |  |  | view over player_identity_aliases | none |
| `public.v_player_identity_resolver` | view |  |  | no caller | none |
| `public.v_props_enriched` | view |  |  | odds view | none |
| `public.v_vegas_season_vorp` | view |  |  | Vegas view | none |
| `public.v_vegas_unpriced_watchlist` | view |  |  | Vegas view | none |
| `public.v_waiver_adds` | view |  |  | waiver view | none |
| `public.v_waiver_drops` | view |  |  | waiver view | none |
| `public.v_waiver_fades` | view |  |  | waiver view | none |
| `public.weekly_disagreement` | view |  |  | view over weekly_source_snapshots | none |
| `public.weekly_disagreement_v1` | view |  |  | view over weekly_source_snapshots | none |
| `public.weekly_intersection` | view |  |  | view over weekly_source_snapshots | none |

## `skip`

| Relation | Kind | Est. rows | Size | Basis | Evidence (code; sql) |
|---|---|---|---|---|---|
| `archive.fp_season_kdst_projections` | table | 66 | 112.0 kB | archive schema (retired 2026-10-08); not migrated | none; sql: `supabase/migrations/archive_fp_kdst_20261008.sql` |
| `archive.publisher_translated_values_stale_20261008` | table | 2,044 | 264.0 kB | archive schema; not migrated | none; sql: `supabase/migrations/archive_stale_vorp_grains_20261008.sql` |
| `monitoring.dispatch_log` | table | 1,081 | 256.0 kB | log written by public.dispatch_gha_workflow on every dispatch; structure needed, history not | none; sql: `supabase/migrations/gha_schedules_pg_cron.sql`, `supabase/migrations/monitoring_coverage_20261007.sql` |
| `ops.anomalies` | table | 0 | 8.0 kB | retired ops monitoring; grep hits are the word "anomalies" in build_aggregate_diagnostics.py | `modules/dashboard.html`, `p/build_aggregate_diagnostics.py`, `p/fidelity_sources/__init__.py` |
| `ops.cbsros_consolidated_backup_20261005` | table | 333 | 136.0 kB | one-off backup table | none |
| `ops.gate_audit` | table | 0 | 16.0 kB | retired ops monitoring (ops.run_gate_audit, no cron job) | none |
| `ops.health` | table | 7,908 | 1.4 MB | retired ops monitoring log (ops.run_health_checks, no cron job); trigger trg_health_alert | `wf/espn-supabase-sync.yml`, `wf/fantasycalc-drift.yml`, `wf/fantasycalc-weekly-save.yml`, `wf/fidelity-pulse.yml` (+37); sql: `sql/consolidated_values.sql`, `sql/contract/api_publish_gate.sql` |
| `ops.slice_stats` | table | 0 | 16.0 kB | retired ops monitoring | none |
| `public.gate_audits` | table | 107 | 376.0 kB | log written only by api.audit_publish_gate (no caller); v_gate_audits_latest | none; sql: `supabase/migrations/20261008_monitoring_6h_and_posture.sql`, `supabase/migrations/jeg377_jeg380_api_mirror.sql` |
| `public.pipeline_cron_log` | table | 0 | 32.0 kB | cron log (log_dispatch_intent shadow mode); 0 rows | none; sql: `sql/consolidated_values.sql` |
| `public.pipeline_cron_state` | table | 0 | 16.0 kB | cron state, no reference; 0 rows | none; sql: `sql/consolidated_values.sql` |
| `public.value_check_values` | table | 1,250,841 | 497.6 MB | value check log, 1.25M rows / ~500 MB, never read by the site; empty structure kept (api.player_values, api.value_check_diff depend on it) | `wf/rebuild-chain.yml`, `p/load_value_check.py`; sql: `supabase/migrations/jeg479_value_check.sql`, `supabase/migrations/jeg479_value_check_monitoring.sql` |
| `archive.v_fp_season_kdst_latest` | view |  |  | archive schema; not migrated | none; sql: `supabase/migrations/archive_fp_kdst_20261008.sql` |
| `monitoring.v_dispatch_outcomes` | view |  |  | view over monitoring.dispatch_log and net._http_response (needs pg_net locally) | none; sql: `supabase/migrations/20261008_security_lockdown.sql`, `supabase/migrations/monitoring_coverage_20261007.sql` |
| `public.v_gate_audits_latest` | view |  |  | view over gate_audits | none |

## pg_cron jobs and the vault

All 20 jobs in `cron.job` (active on 2026-10-21) are in `selfhost/migrate/cron_and_functions.sql` with names, schedules and commands verbatim. 19 call `public.dispatch_gha_workflow`, one calls `public.dispatch_vintage_check`, one (`cron-retention-30d`) trims `cron.job_run_details`. Two exist for the retired monitoring lane: `health-artifacts-live` and `live-page-synthetic-live` (tagged `[monitoring]`). No job belongs to another app.

`dispatch_gha_workflow` reads the GitHub token from `vault.decrypted_secrets` by name (`github_dispatch_token`) and posts with `pg_net`. The token was not read or copied; the file has a `\prompt` step for Jeremy to store it. The cloud vault also has `supabase_service_key` (Edge Function auth), which the site does not need.

## Running it (on the Mac)

1. `export DATABASE_URL=<cloud connection string>`, then `selfhost/migrate/export_cloud.sh`. Needs pg_dump 17. It checks classification, records roles and exact counts, dumps, re-counts (fails if a scheduled writer ran in between) and checks the archive TOC (data for every data table, none for `value_check_values`, 12 api views).
2. `export LOCAL_DATABASE_URL=<Mac Postgres>`, then `selfhost/migrate/import_local.sh selfhost/migrate/out/<stamp>`. It refuses a Supabase URL or a non-empty target, creates extensions and roles (`service_role` with BYPASSRLS), restores in one transaction and runs `verify_counts.py`, which fails on any count mismatch or on rows in a structure-only table.
3. Turn off the cloud jobs (Jeremy), store the token, then `psql "$LOCAL_DATABASE_URL" -v cloud_cron_is_off=1 -f selfhost/migrate/cron_and_functions.sql`.
4. If the direct connection is refused: `export_via_rest.py --yes-i-accept-egress` (data only, JSON over REST, costs more egress, may itself get HTTP 402). The structure still needs `pg_dump --schema-only`.

## Not migrated or not verified from here; Jeremy decides

**Verified:** the inventory and its md5 match with `information_schema`, the cron job list, the dispatch function bodies and grants, the vault secret names, the extension list (pg_cron 1.6.4, pg_net 0.20.4, supabase_vault 0.3.1, pgcrypto, uuid-ossp), view dependencies and FKs; `bash -n`, `py_compile`, the classification coverage check, including a negative test with an extra relation.

**Not verified:**

- No script has run against a live Postgres. The sandbox has Postgres 16 binaries, but starting a server needs `su postgres`, which the session guard blocks, so `export_cloud.sh`, `import_local.sh`, `verify_counts.py` and `export_via_rest.py` are untested end to end. The first run on the Mac is the test.
- Whether the cloud accepts a direct Postgres connection (pooler or direct host) while over the egress quota. Unknown from here; the REST fallback may also return 402.
- Whether lane A's image ships `pg_net`, `pg_cron` and `supabase_vault`. Without pg_net, dispatch fails at run time and `monitoring.v_dispatch_outcomes` is left out; without pg_cron nothing schedules; without the vault, use the shim in `cron_and_functions.sql` STEP 1b (plain text token in the Mac database).
- The writer and reader assignments are a text scan (see above), not a trace of live queries.
- GitHub Actions secrets `SUPABASE_URL` / `SUPABASE_SERVICE_KEY` still point at the cloud. Pointing the workflows at the Mac (a tunnel or public PostgREST endpoint) is out of this lane.
- Cloud roles `lane_b_reader`, `lane_b_writer`, `platform_owner` and `supabase_admin` appear in grants. The import creates them NOLOGIN with no passwords; nothing logs in as them locally unless lane A configures it.

**Decisions for Jeremy:**

1. **Other-app tables** (structure restored empty, data left in the cloud). Keep the data with `INCLUDE_OTHER_APP=1` (about 75 MB more egress), or leave it:
   - blend / season VORP: `blended_calibration` (72.0 kB), `blended_player_map` (200.0 kB), `blended_source_confidence` (32.0 kB), `player_canonical_map` (864.0 kB), `season_actuals_ytd` (344.0 kB), `sleeper_season_latest_norm` (1.1 MB)
   - unclear (may be this repo's legacy): `data_sources` (48.0 kB), `espn_fetch_config` (24.0 kB), `external_id_map` (2.4 MB), `news_items` (28.5 MB), `no_market_read_flags` (152.0 kB), `player_identity_aliases` (312.0 kB), `player_value_notes` (5.3 MB), `post_queue` (216.0 kB), `risk_tilts` (64.0 kB), `trending` (216.0 kB), `waiver_trends` (7.6 MB), `weekly_no_market_read_flags` (32.0 kB), `weekly_source_snapshots` (6.2 MB)
   - DFS: `dfs_salaries` (344.0 kB), `fantasy_salaries` (24.0 kB), `fantasy_sites` (32.0 kB), `fantasy_slates` (16.0 kB)
   - odds / Vegas: `game_weather` (48.0 kB), `handicapper_picks` (24.0 kB), `handicappers` (16.0 kB), `odds_history` (6.9 MB), `sportsbooks` (64.0 kB), `vegas_player_map` (80.0 kB), `vegas_season_totals` (240.0 kB), `venues` (32.0 kB)
   - lottery model: `lottery_breakout_labels` (24.0 kB), `lottery_league_profiles` (48.0 kB), `lottery_model_runs` (80.0 kB), `lottery_paths` (488.0 kB), `lottery_player_features` (704.0 kB), `lottery_predictions` (6.2 MB), `lottery_valuations` (3.2 MB)
   - ranker: `ranker_performance` (48.0 kB), `ranker_rankings` (1.5 MB), `rankers` (48.0 kB)
   - Yahoo league: `trade_watch` (48.0 kB), `yahoo_leagues` (32.0 kB), `yahoo_rostered_snapshot` (104.0 kB), `yahoo_rosters` (168.0 kB), `yahoo_teams` (48.0 kB)
   - ross schema (Ross keeper league, 7 tables, about 0.4 MB): not dumped at all.
2. **`weekly_source_snapshots`** (6.2 MB): this repo created it (`sql/migrations/007_never_blend_trigger.sql`, `supabase/migrations/jeg377_jeg380_api_mirror.sql`) but no code reads or writes it. Classed other-app; say if it should carry data.
3. **`external_id_map`** (2.4 MB): the only mention is a comment saying it is not used. Classed other-app.
4. **Cloud pg_cron off** before the Mac schedules the same 20 jobs, or every workflow runs twice. That is a cloud write; only Jeremy does it.
5. **Monitoring jobs** `health-artifacts-live` and `live-page-synthetic-live`: keep on the Mac or drop.
6. **The `archive` schema** (2 tables, about 0.4 MB) is not migrated. Say if you want it.
