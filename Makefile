.PHONY: help value-check-compare values-explainer source-import source-match source-reference comparison-section comparison-reindex comparison-review comparison-promote coverage-triage comparison-merge naming reference sync guard-harness test validate serve preview-local deploy-status supabase-import import-health plan-status test-core validate-base test-core-shard-1 test-core-shard-2 test-core-shard-3 test-core-shard-4 test-all test-unit test-unit-modules test-integration

TODAY ?= $(shell date +%F)
PORT ?= 8000
SOURCE_FILE ?=
SNAPSHOT_FILE ?=
MATCH_FILE ?=
REFERENCE_FILE ?=
CANDIDATE_FILE ?=
SOURCE ?=
SCORING ?= ppr
TEAMS ?= 12

help:
	@echo "Modular dashboard commands:"
	@echo "  make source-import     Import SOURCE_FILE into standard raw source format"
	@echo "  make supabase-import   Import SOURCE from its Supabase table into a vintage-stamped snapshot"
	@echo "  make import-health   Verify all seven import sources (NFL_WEEK optional; default = content week from pipelines/nfl_week.py)"
	@echo "  make source-match      Match SNAPSHOT_FILE rows to canonical player_key values"
	@echo "  make source-reference  Build source reference artifact(s) from MATCH_FILE (one per scoring/teams/qb group)"
	@echo "  make comparison-section Build a candidate comparison section from REFERENCE_FILE (or REFERENCE_FILES=\"a.json b.json\" for multi-group sources)"
	@echo "  make comparison-merge  Merge CANDIDATE_FILE into a candidate comparison artifact"
	@echo "  make comparison-reindex Reindex CANDIDATE_FILE onto the anchor scale (fixed pie)"
	@echo "  make comparison-review Review REINDEXED_FILE for promotion (verdict: ready/hold)"
	@echo "  make coverage-triage   SOURCE=cbs [REV=<git rev>]  Decision brief for a source held on coverage"
	@echo "  make comparison-promote Promote REVIEW_FILE into the live fixture (needs APPROVE)"
	@echo "  make naming            Fail closed when players.json diverges from the naming manifest"
	@echo "  make reference         Validate current reference artifacts"
	@echo "  make sync              Copy reference artifacts into app/ and dist/"
	@echo "  make guard-harness     Run curve-widget guard math against fixture data"
	@echo "  make test              Run regression tests"
	@echo "  make validate          Run naming, reference, sync, and tests"
	@echo "  make serve             Serve the local dashboard"
	@echo "  make preview-local     Build dist/ the way production does, then serve dist/"
	@echo "  make deploy-status     Show recent GitHub deploy runs"

supabase-import:
	@test -n "$(SOURCE)" || (echo "Set SOURCE=fantasycalc|usatoday|fantasypros|espn|cbs" && exit 1)
	python3 pipelines/import_supabase_references.py --source "$(SOURCE)"

import-health:
	# NFL_WEEK optional: defaults to pipelines/nfl_week.py (content week, flips Tuesday; build-lag-001).
	python3 pipelines/verify_import_health.py $(if $(NFL_WEEK),--nfl-week "$(NFL_WEEK)")

source-import:
	@test -n "$(SOURCE_FILE)" || (echo "Set SOURCE_FILE=/path/to/scrape.csv or .json" && exit 1)
	@test -n "$(SOURCE)" || (echo "Set SOURCE=fantasycalc, cbs, usatoday, etc." && exit 1)
	python3 pipelines/import_source_snapshot.py --input "$(SOURCE_FILE)" --source "$(SOURCE)" --scoring "$(SCORING)" --teams "$(TEAMS)"

source-match:
	@test -n "$(SNAPSHOT_FILE)" || (echo "Set SNAPSHOT_FILE=data/raw/sources/.../snapshot.json" && exit 1)
	python3 pipelines/match_source_snapshot.py --input "$(SNAPSHOT_FILE)"

source-reference:
	@test -n "$(MATCH_FILE)" || (echo "Set MATCH_FILE=output/source-matches/.../matched.json" && exit 1)
	python3 pipelines/build_source_reference.py --input "$(MATCH_FILE)"

comparison-section:
	@test -n "$(REFERENCE_FILE)$(REFERENCE_FILES)" || (echo "Set REFERENCE_FILE=output/source-references/.../reference.json or REFERENCE_FILES=\"a.json b.json\"" && exit 1)
	python3 pipelines/build_comparison_source_section.py --input $(REFERENCE_FILES) $(REFERENCE_FILE)

comparison-merge:
	@test -n "$(CANDIDATE_FILE)" || (echo "Set CANDIDATE_FILE=output/comparison-candidates/.../section.json" && exit 1)
	python3 pipelines/merge_comparison_candidate.py --candidate "$(CANDIDATE_FILE)"

comparison-reindex:
	@test -n "$(CANDIDATE_FILE)" || (echo "Set CANDIDATE_FILE=output/comparison-candidates/.../section.json" && exit 1)
	python3 pipelines/reindex_comparison_section.py "$(CANDIDATE_FILE)"

comparison-review:
	@test -n "$(REINDEXED_FILE)" || (echo "Set REINDEXED_FILE=output/comparison-reference/...-reindexed.json" && exit 1)
	python3 pipelines/review_comparison_candidate.py "$(REINDEXED_FILE)" $(if $(TRIAGE_FILE),--triage "$(TRIAGE_FILE)")

coverage-triage:
	@test -n "$(SOURCE)" || (echo "Set SOURCE=<chain source key, e.g. cbs or fantasycalc>" && exit 1)
	python3 pipelines/coverage_triage.py report "$(SOURCE)" $(if $(REV),--rev "$(REV)")

comparison-promote:
	@test -n "$(REVIEW_FILE)" || (echo "Set REVIEW_FILE=output/comparison-review/...-review.json" && exit 1)
	@if [ -n "$(AUTO)" ]; then \
		python3 pipelines/promote_comparison_section.py "$(REVIEW_FILE)" --auto; \
	else \
		test -n "$(APPROVE)" || (echo "Set APPROVE=\"<name> <YYYY-MM-DD> <reason>\" or AUTO=1" && exit 1); \
		python3 pipelines/promote_comparison_section.py "$(REVIEW_FILE)" --approve "$(APPROVE)"; \
	fi

naming:
	python3 pipelines/check_naming_drift.py

# JEG-111: fail-closed Supabase naming-convention check.
naming-convention:
	python3 pipelines/check_supabase_naming.py

reference:
	python3 pipelines/build_reference_data.py --today $(TODAY)

sync:
	python3 pipelines/sync_dashboard_artifacts.py

guard-harness:
	node tools/guard_harness.mjs --assert-good
	node tools/guard_harness.mjs --simulate espn-anchor --assert-bad

# Headless render tests skip when no browser is installed, unless
# RENDER_TESTS_REQUIRED=1 (tests/_render_env.py). CI sets it in the step that
# installs the browser, so in CI a missing browser fails instead of skipping.

# Unit tests: no data/raw, snapshot, or external service dependency.
# Safe to run in CI (Pages deploy) where gitignored data is absent.
# Runs every line of test-unit-modules and keeps going past a failing one,
# then exits 1 listing the failures (2026-10-08: one playwright timeout
# stopped the suite and hid every module after it). `make test-unit-modules`
# runs the same list and stops at the first failure.
# The node harnesses pin their own playwright-core, whose bundled Chromium build
# often is not the one installed. Use $CHROMIUM_PATH, else the first browser the
# Python render tests would use (tests/_render_env.py), else Playwright's default.
NODE_CHROMIUM = $(or $(CHROMIUM_PATH),$(shell python3 -c "from playwright.sync_api import sync_playwright; from tests import _render_env as e; p = sync_playwright().start(); print(e.chromium_executable(p) or ''); p.stop()" 2>/dev/null))

test-unit:
	python3 tests/run_suite.py test-unit-modules

test-unit-modules:
	python3 -m unittest tests.test_run_suite
	# Render-sweep coverage guard (JEG-976): a warning, not a deploy gate (Jeremy, 2026-10-26).
	python3 -m unittest tests.test_render_sweep_coverage
	python3 -m unittest tests.test_render_sweep_shards
	python3 -m unittest tests.test_validate_runner
	python3 -m unittest tests.test_doc_staleness
	python3 -m unittest tests.test_mcp_remote
	python3 -m unittest tests.test_ddf_state
	python3 -m unittest tests.test_league_mapping
	# JEG-1179: the week get-values and the MCP tools price (default, explicit, error, transitions).
	python3 -m unittest tests.test_mcp_week
	python3 -m unittest tests.test_endpoint_parity
	python3 -m unittest tests.test_harness_main_guard
	python3 -m unittest tests.test_launch_qa_surfaces
	python3 -m unittest tests.test_migrations
	python3 -m unittest tests.test_gh_sbclient_bytes
	python3 -m unittest tests.test_usatoday_relay_source
	python3 -m unittest tests.test_bake_espn_zero_universe
	python3 -m unittest tests.test_nfl_universe
	python3 -m unittest tests.test_universe_chart_only
	python3 -m unittest tests.test_match_identity_keys
	python3 -m unittest tests.test_sleeper_identity_layer
	python3 -m unittest tests.test_coverage_intro_dynamic_universe
	python3 -m unittest tests.test_drift_snapshot_baseline
	python3 -m unittest tests.test_pull_fantasycalc_12team
	python3 -m unittest tests.test_pull_draftsharks
	python3 -m unittest tests.test_pull_fantasysharks
	python3 -m unittest tests.test_published_surfaces
	python3 -m unittest tests.test_monitoring_coverage
	python3 -m unittest tests.test_gha_schedules_pg_cron
	python3 -m unittest tests.test_monitor_alerts
	python3 -m unittest tests.test_fc_grain_check
	python3 -m unittest tests.test_fidelity_pulse
	python3 -m unittest tests.test_fidelity_espn
	python3 -m unittest tests.test_fidelity_cbsros
	python3 -m unittest tests.test_fidelity_razzball
	python3 -m unittest tests.test_fidelity_sharks
	python3 -m unittest tests.test_sharks_savers
	python3 -m unittest tests.test_fidelity_hold
	python3 -m unittest tests.test_position_conflict_names
	python3 -m unittest tests.test_source_divergence
	python3 -m unittest tests.test_open_divergence_issues
	python3 -m unittest tests.test_security_lockdown_migration
	python3 -m unittest tests.test_source_probe
	python3 -m unittest tests.test_source_snapshot_match
	python3 -m unittest tests.test_rebuild_chain_failclosed
	python3 -m unittest tests.test_rebuild_chain_per_source_hold
	python3 -m unittest tests.test_health_artifacts_summary_step
	python3 -m unittest tests.test_health_artifacts_watch
	python3 -m unittest tests.test_ops_dashboard
	python3 -m unittest tests.test_retired_extras
	python3 -m unittest tests.test_load_ddf_leg_contract
	python3 -m unittest tests.test_build_v2_page
	python3 -m unittest tests.test_v2_tokens
	python3 -m unittest tests.test_v2_assist
	python3 -m unittest tests.test_v2_targets_render
	python3 -m unittest tests.test_v2_targets_thin_render
	python3 -m unittest tests.test_v2_compare_render
	python3 -m unittest tests.test_v2_how_render
	python3 -m unittest tests.test_v2_manifesto_render
	python3 -m unittest tests.test_v2_contract_render
	python3 -m unittest tests.test_v2_finder_render
	python3 -m unittest tests.test_v2_finder_arrange_render
	python3 -m unittest tests.test_v2_finder_viable_render
	python3 -m unittest tests.test_waivers_render
	python3 -m unittest tests.test_waivers_paste_render
	python3 -m unittest tests.test_waivers_view_render
	python3 -m unittest tests.test_v2_espn_held_chip_render
	python3 -m unittest tests.test_v2_states_render
	python3 -m unittest tests.test_v2_nav_render
	python3 -m unittest tests.test_v2_phone_header_render
	python3 -m unittest tests.test_v2_phone_tap_targets_render
	python3 -m unittest tests.test_v2_audit_render
	python3 -m unittest tests.test_v2_health_check_render
	python3 -m unittest tests.test_v2_ux_render
	python3 -m unittest tests.test_v2_risers_render
	python3 -m unittest tests.test_v2_share_render
	python3 -m unittest tests.test_v2_share_links
	python3 -m unittest tests.test_v2_share_links_render
	python3 -m unittest tests.test_v2_assist_render
	python3 -m unittest tests.test_v2_season_weeks_render
	python3 -m unittest tests.test_weekly_matchup_swaps
	python3 -m unittest tests.test_v2_offer_render
	python3 -m unittest tests.test_v2_waterfall_render
	python3 -m unittest tests.test_v2_ddf_render
	python3 -m unittest tests.test_v2_panels_render
	python3 -m unittest tests.test_v2_a11y_render
	python3 -m unittest tests.test_v2_weight_render
	python3 -m unittest tests.test_v2_estimated_render
	python3 -m unittest tests.test_v2_expand_render
	python3 -m unittest tests.test_espn_zero_badge_render
	python3 -m unittest tests.test_per_source_rescale
	python3 -m unittest tests.test_verify_cbsros_legs
	python3 -m unittest tests.test_review_live_verify_combo
	python3 -m unittest tests.test_review_coverage_live_verify
	python3 -m unittest tests.test_review_coverage_churn
	python3 -m unittest tests.test_coverage_acceptance
	python3 -m unittest tests.test_coverage_triage
	python3 -m unittest tests.test_coverage_fill_in
	python3 -m unittest tests.test_publication_window_content_week
	python3 -m unittest tests.test_build_lag_gate
	python3 -m unittest tests.test_import_health
	python3 -m unittest tests.test_verify_import_health
	python3 -m unittest tests.test_promote_section
	python3 -m unittest tests.test_checkpoint_expected_week
	python3 -m unittest tests.test_checkpoint_pages_deploy
	python3 -m unittest tests.test_c10_committed_fixture_baseline
	python3 -m unittest tests.test_checkpoints_health_freshest
	python3 -m unittest tests.test_checkpoint_c2_collection
	python3 -m unittest tests.test_health_artifacts_publish
	python3 -m unittest tests.test_workflow_no_event_interpolation
	python3 -m unittest tests.test_trade_chart_ingest_ci
	python3 -m unittest tests.test_pull_fantasypros_parse
	python3 -m unittest tests.test_article_discovery
	python3 -m unittest tests.test_razzball_sync_ci
	python3 -m unittest tests.test_espn_weekly_store
	python3 -m unittest tests.test_load_nflverse_history
	python3 -m unittest tests.test_dashboard_fleet_counts_sections
	python3 -m unittest tests.test_dashboard_loader_declarations
	python3 -m unittest tests.test_comparison_candidate_build
	python3 -m unittest tests.test_comparison_source_integrity
	python3 -m unittest tests.test_bake_cbsros_intake
	python3 -m unittest tests.test_curve_default_guard
	python3 -m unittest tests.test_guard_harness_recorded
	python3 -m unittest tests.test_jeg103_bench_share_readout
	python3 -m unittest tests.test_jeg103_bench_slider_readout
	python3 -m unittest tests.test_jeg135_rendered_flexibility
	python3 -m unittest tests.test_ddf_two_tier_leg
	python3 -m unittest tests.test_imputed_vorps_validation
	python3 -m unittest tests.test_imputed_vorps_precision
	python3 -m unittest tests.test_imputed_roster_config
	python3 -m unittest tests.test_kdst_optional
	python3 -m unittest tests.test_reweighted_batch_anchor
	python3 -m unittest tests.test_option_c_sheet_oracle
	python3 -m unittest tests.test_sheet_oracle_canonical
	python3 -m unittest tests.test_reweight_reference_contract
	python3 -m unittest tests.test_reweight_inversion_budget
	python3 -m unittest tests.test_espn_pool_cap
	python3 -m unittest tests.test_vorp_refresh
	python3 -m unittest tests.test_projection_source_kind
	python3 -m unittest tests.test_vorp_translation_unified
	python3 -m unittest tests.test_two_qb_direction
	python3 -m unittest tests.test_short_chart_waiver
	python3 -m unittest tests.test_published_league_settings_engine
	python3 -m unittest tests.test_published_league_settings_render
	python3 -m unittest tests.test_value_reference_worked_example
	python3 -m unittest tests.test_value_check
	python3 -m unittest tests.test_load_value_check
	python3 -m unittest tests.test_spec_reference
	python3 -m unittest tests.test_spec_reference_value_pipeline
	python3 -m unittest tests.test_derive_lineup_parameters
	python3 -m unittest tests.test_expected_starts_model
	python3 -m unittest tests.test_score_lineup_values
	python3 -m unittest tests.test_consolidated_current
	python3 -m unittest tests.test_vorp_wiring
	python3 -m unittest tests.test_three_view_pipeline_wiring
	python3 -m unittest tests.test_review_batch70_views
	python3 -m unittest tests.test_vorp_views_preview
	python3 -m unittest tests.test_jeg242_blend_reference
	python3 -m unittest tests.test_jeg298_roster_shape_no_kdst
	python3 -m unittest tests.test_chart_kdst_positions_and_view_wiring
	python3 -m unittest tests.test_run_as_published_vorp
	python3 -m unittest tests.test_transform_batch70_to_comparison
	python3 -m unittest tests.test_backstop_hash_roundtrip
	python3 -m unittest tests.test_vintage_trigger
	python3 -m unittest tests.test_lock_revert_notice_render
	python3 -m unittest tests.test_source_curves_distinct
	python3 -m unittest tests.test_methodology_consistency
	python3 -m unittest tests.test_player_scenario_matrix
	python3 -m unittest tests.test_public_copy_no_vorp
	python3 -m unittest tests.test_product_data_wiring
	python3 -m unittest tests.test_source_freshness
	python3 -m unittest tests.test_freshness_display_render
	python3 -m unittest tests.test_publication_windows
	python3 -m unittest tests.test_qb_slot_scoping
	python3 -m unittest tests.test_source_combo_contract
	python3 -m unittest tests.test_razzball_monitor_coverage
	python3 -m unittest tests.test_indexed_monitor_math
	python3 -m unittest tests.test_espn_zeroed_staleness
	python3 -m unittest tests.test_health_function_no_hardcoded_green
	python3 -m unittest tests.test_razzball_supabase
	python3 -m unittest tests.test_reference_freshness
	python3 -m unittest tests.test_reindex_section
	python3 -m unittest tests.test_review_candidate
	python3 -m unittest tests.test_source_reference_build
	python3 -m unittest tests.test_scheduler_slip
	python3 -m unittest tests.test_static_export
	python3 -m unittest tests.test_consolidation_reconciliation
	python3 -m unittest tests.test_consolidated_write_fields
	python3 -m unittest tests.test_rebuild_chain_consolidation_nonblocking
	python3 -m unittest tests.test_methodology_payload
	python3 -m unittest tests.test_sync_health_freshest
	python3 -m unittest tests.test_dashboard_view_tags
	python3 -m unittest tests.test_dist_manifest
	python3 -m unittest tests.test_preview_workflow_matches_pages
	python3 -m unittest tests.test_v2_render_runs_on_data_push
	python3 -m unittest tests.test_ci_speedup_workflows
	python3 -m unittest tests.test_validate_shards
	python3 -m unittest tests.test_sync_monitor_fixture
	python3 -m unittest tests.test_rebuild_chain_workflow
	python3 -m unittest tests.test_rebuild_chain_conflict_handoff
	python3 -m unittest tests.test_workflow_dispatch_permissions
	python3 -m unittest tests.test_live_page_synthetic_workflow
	python3 -m unittest tests.test_live_page_synthetic
	python3 -m unittest tests.test_status_warnings
	python3 -m unittest tests.test_import_health_schema_doc
	python3 -m unittest tests.test_player_identity_guard
	python3 -m unittest tests.test_espn_ci_workflow
	python3 -m unittest tests.test_cbsros_sync_workflow
	python3 -m unittest tests.test_github_actions_status
	python3 -m unittest tests.test_check_fidelity_ordering
	python3 -m unittest tests.test_input_lineage
	python3 -m unittest tests.test_deploy_gate_unconditional
	python3 -m unittest tests.test_artifact_generated_at
	python3 -m unittest tests.test_production_verify
	python3 -m unittest tests.test_identity_case_duplicates
	python3 -m unittest tests.test_lane_protocol
	python3 -m unittest lanes.test_plan_tracker
	python3 -m unittest tests.test_backstop_exclusions
	python3 -m unittest tests.test_bake_espn_intake
	python3 -m unittest tests.test_bake_team_abbr
	python3 -m unittest tests.test_bake_today_unboundlocal
	python3 -m unittest tests.test_below_leg_zero_render
	python3 -m unittest tests.test_build_e2e_fidelity
	python3 -m unittest tests.test_build_source_fidelity
	python3 -m unittest tests.test_cbs_week_coding
	python3 -m unittest tests.test_cbsros_replace_semantics
	python3 -m unittest tests.test_cbsros_section
	python3 -m unittest tests.test_chart_input_coverage
	python3 -m unittest tests.test_check_issue_acceptance
	python3 -m unittest tests.test_check_source_fidelity
	python3 -m unittest tests.test_check_source_vintage
	python3 -m unittest tests.test_content_vintage_schema
	python3 -m unittest tests.test_dashboard_column_selection_preserved
	python3 -m unittest tests.test_dashboard_firstok_unwrap
	python3 -m unittest tests.test_dashboard_labels_no_hardcoded_week
	python3 -m unittest tests.test_dashboard_scale_agreement
	python3 -m unittest tests.test_ddf_groups
	python3 -m unittest tests.test_deadline_checker
	python3 -m unittest tests.test_espn_player_key_join
	python3 -m unittest tests.test_fantasycalc_drift
	python3 -m unittest tests.test_imputed_vorps_clean
	python3 -m unittest tests.test_inventory_supabase_schema
	python3 -m unittest tests.test_jeg137_card_script_order
	python3 -m unittest tests.test_jeg189_slip_wiring
	python3 -m unittest tests.test_jeg30_health_diagnostics
	python3 -m unittest tests.test_jeg38_raw_vorp_sources
	python3 -m unittest tests.test_lineage_writers
	python3 -m unittest tests.test_load_weekly_vintage_gate
	python3 -m unittest tests.test_lock_reset_caption_guard
	python3 -m unittest tests.test_no_failopen_workflows
	python3 -m unittest tests.test_pipeline_checkpoints
	python3 -m unittest tests.test_promote_exclusion_gate
	python3 -m unittest tests.test_promotion_provenance
	python3 -m unittest tests.test_publish_gate
	python3 -m unittest tests.test_pull_acquisition_summary
	python3 -m unittest tests.test_pull_fantasypros
	python3 -m unittest tests.test_quantile_mapping
	python3 -m unittest tests.test_razzball_dashboard_render
	python3 -m unittest tests.test_razzball_production_followups
	python3 -m unittest tests.test_rebuild_chain_bake
	python3 -m unittest tests.test_rebuild_chain_source_resiliency
	python3 -m unittest tests.test_scale_agreement
	python3 -m unittest tests.test_supabase_naming
	python3 -m unittest tests.test_trade_qa_card
	python3 -m unittest tests.test_verify_health_bake_selection
	python3 -m unittest tests.test_vorp_translation_checkpoint
	python3 -m unittest tests.test_week_for_source_designated
	# Test sweep (JEG-976): modules no target or workflow ran until 2026-10-23.
	python3 -m unittest tests.test_egress_trims_jeg793
	python3 -m unittest tests.test_espn_fidelity_jeg480
	python3 -m unittest tests.test_espn_ppg_basis
	python3 -m unittest tests.test_espn_pull_team_played_jeg574
	python3 -m unittest tests.test_fidelity_followups_jeg480
	python3 -m unittest tests.test_fidelity_sentinels
	python3 -m unittest tests.test_fundamental_bench
	python3 -m unittest tests.test_jeg606_unpriced_team_and_value
	python3 -m unittest tests.test_projection_captures
	python3 -m unittest tests.test_pull_cbs_ros_positions
	python3 -m unittest tests.test_pull_keeptradecut
	python3 -m unittest tests.test_razzball_chain_hold
	python3 -m unittest tests.test_record_post_rebuild_validation
	python3 -m unittest tests.test_save_dynasty_daddy
	python3 -m unittest tests.test_save_keeptradecut
	python3 -m unittest tests.test_save_numberfire_ros
	python3 -m unittest tests.test_save_rotoballer
	python3 -m unittest tests.test_sentinel_derived_floor
	python3 -m unittest tests.test_source_link_urls
	python3 -m unittest tests.test_stash_signals
	python3 -m unittest tests.test_usatoday_fidelity_jeg480
	python3 -m unittest tests.test_v2_deal_read
	python3 -m unittest tests.test_v2_deal_read_chart_avg
	python3 -m unittest tests.test_v2_deal_read_split
	python3 -m unittest tests.test_v2_disagree
	python3 -m unittest tests.test_v2_finder_import
	# JEG-1108: fit label rules, their guards, and the label distribution on the 20-team reference league.
	python3 -m unittest tests.test_v2_finder_fit
	python3 -m unittest tests.test_v2_finder_trifit
	python3 -m unittest tests.test_v2_finder_balance
	python3 -m unittest tests.test_v2_league_units
	python3 -m unittest tests.test_jeg1213_import tests.test_jeg1213_logic tests.test_jeg1213_summary_fields
	python3 -m unittest tests.test_jeg1216_lineup
	node tests/node/fit_diagnostic.cjs --assert
	python3 -m unittest tests.test_v2_group_weight
	python3 -m unittest tests.test_v2_name_search
	# pytest-style modules (unittest finds no tests in them); preview.yml installs pytest.
	python3 -m pytest -q -p no:cacheprovider tests/test_player_status_history_ids.py
	python3 -m pytest -q -p no:cacheprovider tests/test_pull_dynasty_daddy.py
	python3 -m pytest -q -p no:cacheprovider tests/test_pull_numberfire_ros.py
	python3 -m pytest -q -p no:cacheprovider tests/test_pull_rotoballer.py
	python3 -m pytest -q -p no:cacheprovider tests/test_pull_sleeper_projections.py
	python3 -m pytest -q -p no:cacheprovider tests/test_sleeper_projection_idmap.py
	# Cheapest green headless render modules from the sweep (about 2.5 min together); the rest are in the PR table.
	python3 -m unittest tests.test_v2_group_weight_render
	python3 -m unittest tests.test_v2_deal_read_empty_side_render
	python3 -m unittest tests.test_v2_held_pickers_render
	python3 -m unittest tests.test_v2_values_math_tip_render
	python3 -m unittest tests.test_v2_player_tags_render
	python3 -m unittest tests.test_v2_compare_empty_side_render
	python3 -m unittest tests.test_v2_disagree_render
	# Mobile phase 4 and 5 (JEG-955 layout collapse, JEG-956 safe areas, JEG-903 target size).
	python3 -m unittest tests.test_v2_phone_layout_collapse_render
	python3 -m unittest tests.test_v2_phone_safe_area_render
	python3 -m unittest tests.test_v2_phone_target_size_render
	# Dashboard render harnesses (JEG-308/310/312/318) that no target ran
	# until 2026-10-08. They need tests/rendered_gate's playwright-core
	# (npm ci --prefix tests/rendered_gate) and a Chromium (CHROMIUM_PATH).
	CHROMIUM_PATH="$(NODE_CHROMIUM)" node tests/rendered_gate/freshness-hero.mjs dist
	CHROMIUM_PATH="$(NODE_CHROMIUM)" node tests/rendered_gate/razzball_pill_harness.mjs dist
	CHROMIUM_PATH="$(NODE_CHROMIUM)" node tests/rendered_gate/source-import-health-table.mjs dist
	CHROMIUM_PATH="$(NODE_CHROMIUM)" node tests/rendered_gate/trade-qa-open-findings.mjs dist


# Integration tests: multi-stage pipeline paths (cascade, savers, imports,
# writer audit) on synthetic inputs. Hermetic -- no network, Supabase or
# data/raw -- and part of `make validate` since 2026-10-08 (GAP-013).
test-integration:
	python3 -m unittest tests.test_cbs_usatoday_recurring
	python3 -m unittest tests.test_naming_drift
	python3 -m unittest tests.test_pipeline_cascade
	python3 -m unittest tests.test_trade_chart_pullers
	python3 -m unittest tests.test_save_espn_cbs_references
	python3 -m unittest tests.test_source_snapshot_import
	python3 -m unittest tests.test_supabase_import
	python3 -m unittest tests.test_writer_audit_enforcement

# Full suite (local dev / rebuild workflow).
test: test-unit test-integration

# Three-view candidate refresh (JEG-242): wires the reviewed imputation /
# reweight producers into a versioned refresh path with the schema-specific
# review as a fail-closed gate. Candidate-only: writes to VORP_VIEWS_OUT_DIR,
# never Supabase, never promotion. Requires explicit weights via
# VORP_VIEWS_WEIGHT_ARGS ("--controls <file>" or "--reference <file>") --
# no defaults are invented; weight approval stays with Jeremy.
refresh-vorp-views:
	@test -n "$(VORP_VIEWS_VALUES_DIR)" || (echo "VORP_VIEWS_VALUES_DIR required" >&2; exit 2)
	@test -n "$(VORP_VIEWS_GROUP_VORPS)" || (echo "VORP_VIEWS_GROUP_VORPS required" >&2; exit 2)
	@test -n "$(VORP_VIEWS_ROSTER_CONFIG)" || (echo "VORP_VIEWS_ROSTER_CONFIG required" >&2; exit 2)
	@test -n "$(VORP_VIEWS_OUT_DIR)" || (echo "VORP_VIEWS_OUT_DIR required" >&2; exit 2)
	python3 pipelines/refresh_vorp_views.py --values-dir "$(VORP_VIEWS_VALUES_DIR)" \
		--group-vorps "$(VORP_VIEWS_GROUP_VORPS)" --roster-config "$(VORP_VIEWS_ROSTER_CONFIG)" \
		$(VORP_VIEWS_WEIGHT_ARGS) --out-dir "$(VORP_VIEWS_OUT_DIR)"

# As-published VORP orchestration (JEG-242): resolves Jeremy's pinned blend
# reference (leg-sha verification, group-VORP rebuild from the pinned leg,
# --controls extracted mechanically from the reference budgets) and runs the
# reviewed refresh_vorp_views path end-to-end. Candidate-only: writes to
# VORP_VIEWS_OUT_DIR, never Supabase, never promotion. No weights invented.
run-as-published-vorp:
	@test -n "$(VORP_VIEWS_VALUES_DIR)" || (echo "VORP_VIEWS_VALUES_DIR required" >&2; exit 2)
	@test -n "$(VORP_VIEWS_ROSTER_CONFIG)" || (echo "VORP_VIEWS_ROSTER_CONFIG required" >&2; exit 2)
	@test -n "$(VORP_VIEWS_OUT_DIR)" || (echo "VORP_VIEWS_OUT_DIR required" >&2; exit 2)
	python3 pipelines/run_as_published_vorp.py --values-dir "$(VORP_VIEWS_VALUES_DIR)" \
		--roster-config "$(VORP_VIEWS_ROSTER_CONFIG)" --out-dir "$(VORP_VIEWS_OUT_DIR)" \
		$(if $(VORP_VIEWS_REFERENCE),--reference "$(VORP_VIEWS_REFERENCE)") \
		$(if $(VORP_VIEWS_GROUP_VORPS_OVERRIDE),--group-vorps "$(VORP_VIEWS_GROUP_VORPS_OVERRIDE)")

# Batch70 -> comparison bridge (JEG-242): rewrites a REVIEWED batch70
# candidate's three views into the vorp_views blocks the JEG-210 chart view
# toggle consumes. Writes a candidate copy; promotion to the live fixture is
# a separate reviewed step.
transform-vorp-views:
	@test -n "$(VORP_VIEWS_OUT_DIR)" || (echo "VORP_VIEWS_OUT_DIR required" >&2; exit 2)
	@test -n "$(VORP_VIEWS_COMPARISON_IN)" || (echo "VORP_VIEWS_COMPARISON_IN required" >&2; exit 2)
	@test -n "$(VORP_VIEWS_COMPARISON_OUT)" || (echo "VORP_VIEWS_COMPARISON_OUT required" >&2; exit 2)
	python3 pipelines/transform_batch70_to_comparison.py \
		--batch70 "$(VORP_VIEWS_OUT_DIR)/candidate.json" \
		--comparison "$(VORP_VIEWS_COMPARISON_IN)" \
		--out "$(VORP_VIEWS_COMPARISON_OUT)"

# Three-view preview (JEG-242): loads a REVIEWED candidate into a COPIED
# output dashboard and proves per-view numerical parity (indexed =
# native*70/common peak; vorp/adj verbatim; genuine zeros kept; absent keys
# stay absent). Candidate-only; production is never touched. Run after
# refresh-vorp-views with the same VORP_VIEWS_OUT_DIR.
preview-vorp-views:
	@test -n "$(VORP_VIEWS_OUT_DIR)" || (echo "VORP_VIEWS_OUT_DIR required" >&2; exit 2)
	@test -n "$(VORP_VIEWS_PREVIEW_DIR)" || (echo "VORP_VIEWS_PREVIEW_DIR required" >&2; exit 2)
	python3 pipelines/preview_vorp_views.py \
		--candidate "$(VORP_VIEWS_OUT_DIR)/candidate.json" \
		--batch "$(VORP_VIEWS_OUT_DIR)/work/batch.json" \
		--out-dir "$(VORP_VIEWS_PREVIEW_DIR)"
	node preview/check_preview_parity.js \
		"$(VORP_VIEWS_PREVIEW_DIR)/preview-dashboard/assets/vorp-views-preview.json"
	# JEG-242: bridge the REVIEWED candidate into the COPIED dashboard's
	# comparison data (the vorp_views view contract) and verify it with an
	# independent second-language check. The transformer's output is consumed
	# and verified here; production promotion stays a separate reviewed step.
	python3 pipelines/transform_batch70_to_comparison.py \
		--batch70 "$(VORP_VIEWS_OUT_DIR)/candidate.json" \
		--comparison "$(VORP_VIEWS_PREVIEW_DIR)/preview-dashboard/assets/comparison-sources-data.json" \
		--out "$(VORP_VIEWS_PREVIEW_DIR)/preview-dashboard/assets/comparison-sources-data.json"
	node preview/check_vorp_views_parity.js \
		"$(VORP_VIEWS_OUT_DIR)/candidate.json" \
		"$(VORP_VIEWS_PREVIEW_DIR)/preview-dashboard/assets/comparison-sources-data.json"

# Deploy gate (go-live, 2026-10-07): block only when the numbers are wrong or
# the site would be broken. Everything else runs in `make test-unit`, which CI
# runs as non-blocking.
# GAP-013 (2026-10-08): the hermetic integration tests (cascade, promote,
# writer audit, savers) gate deploys too; none needs network, Supabase or data/raw.
# JEG-633: value-path suites are in test-core. value-check-compare (reference vs
# JEG-668: value-check-compare wired after held-source reference fix landed.
validate: reference sync guard-harness test-core value-check-compare test-integration

# JEG-1170: preview.yml and pages.yml run validate-base (validate minus test-core) in one job
# and test-core as the test-core-shard-N targets in parallel matrix jobs.
# tests/test_validate_shards.py fails unless the shards together run exactly
# test-core's lines (none missing, none twice) and validate == validate-base + test-core.
validate-base: reference sync guard-harness value-check-compare test-integration

value-check-compare:
	python3 pipelines/value_check.py compare --rerun-engine --strict --report output/value-check.json

test-core:
	python3 -m unittest tests.test_spec_reference_value_pipeline
	# JEG-1057: the engine side of the worked example. It ran in no target, so
	# #867 regenerated the fixture for the new defaults and this went red unseen.
	python3 -m unittest tests.test_value_pipeline_engine
	# JEG-1152: engine promotion model part-for-part with the reference.
	python3 -m unittest tests.test_promotion_model_parity
	python3 -m unittest tests.test_static_export
	python3 -m unittest tests.test_seeded_hold_build
	python3 -m unittest tests.test_rank_guard
	python3 -m unittest tests.test_games_remaining
	python3 -m unittest tests.test_ppg_tie_parity
	python3 -m unittest tests.test_kdst_removed
	python3 -m unittest tests.test_market_bench
	python3 -m unittest tests.test_comparison_source_integrity
	python3 -m unittest tests.test_source_curves_distinct
	python3 -m unittest tests.test_curve_default_guard
	python3 -m unittest tests.test_superflex
	python3 -m unittest tests.test_superflex_publisher_values
	python3 -m unittest tests.test_cbsros_bake_identity
	python3 -m unittest tests.test_suffix_identity
	python3 -m unittest tests.test_player_aliases
	python3 -m unittest tests.test_one_name_resolver
	python3 -m unittest tests.test_player_alias_table
	python3 -m unittest tests.test_jeg539_position_and_inactive_rules
	python3 -m unittest tests.test_chain_commits_legs
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
	python3 -m unittest tests.test_waivers_math
	python3 -m unittest tests.test_waivers_views
	python3 -m unittest tests.test_v2_copy_names
	python3 -m unittest tests.test_v2_finder_trifit
	python3 -m unittest tests.test_v2_finder_projection_noise
	python3 -m unittest tests.test_v2_finder_triview_display
	node tests/test_v2_roster_paste.js
	node tests/test_v2_league_paste.js
	node tests/test_v2_name_format.js
	python3 -m unittest tests.test_v2_headlines
	python3 -m unittest tests.test_v2_movers
	python3 -m unittest tests.test_v2_trade_story
	python3 -m unittest tests.test_v2_rescaled_copy
	node tests/node/source_views_check.mjs
	python3 -m unittest tests.test_v2_waterfall
	# Phone layout guards (JEG-829): run on the Linux CI runner, where the wide fallback face (DejaVu Sans) applies.
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
	python3 -m unittest tests.test_lineup_content_week_advance
	python3 -m unittest tests.test_position_weights_setter
	python3 -m unittest tests.test_value_overrides
	python3 -m unittest tests.test_ddf_composite_value
	python3 -m unittest tests.test_view_switch_hidden_defaults
	python3 -m unittest tests.test_row_missing_reasons
	python3 -m unittest tests.test_search_players_universe
	python3 -m unittest tests.test_source_scale_agreement_retired
	python3 -m unittest tests.test_week_calendar
	# JEG-1177: shared defaultWeek vectors (JS + Python) and the New York clock.
	python3 -m unittest tests.test_week_state
	python3 -m unittest tests.test_two_qb_direction
	python3 -m unittest tests.test_short_chart_waiver
	python3 -m unittest tests.test_published_league_settings_engine
	python3 -m unittest tests.test_value_reference_worked_example
	python3 -m unittest tests.test_roster_convention
	python3 -m unittest tests.test_roster_convention_parity
	python3 -m unittest tests.test_player_tags
	python3 -m unittest tests.test_contract_qa_report
	# Test sweep (JEG-976): the Razzball outlier hold.
	# (tests.test_value_pipeline_engine is wired into test-core by #914 / JEG-1057.)
	python3 -m unittest tests.test_razzball_outlier_guard

# JEG-1170: test-core split into parallel shards for preview.yml and pages.yml. Their union
# is exactly test-core: a line added to test-core must also go into one shard, or
# tests/test_validate_shards.py fails. Balanced by the per-module times of preview run 40199508029
# (about 7.5 minutes of tests each); within a shard the lines keep test-core's order.
test-core-shard-1:
	python3 -m unittest tests.test_seeded_hold_build
	python3 -m unittest tests.test_market_bench
	python3 -m unittest tests.test_superflex
	python3 -m unittest tests.test_player_aliases
	python3 -m unittest tests.test_chain_commits_legs
	python3 -m unittest tests.test_timestamps
	python3 -m unittest tests.test_producers_schedule_tidy
	python3 -m unittest tests.test_verify_live
	python3 -m unittest tests.test_v2_copy_names
	node tests/test_v2_roster_paste.js
	python3 -m unittest tests.test_v2_movers
	python3 -m unittest tests.test_v2_phone_layout_render
	python3 -m unittest tests.test_v2_phone_context_row_render
	python3 -m unittest tests.test_v2_desktop_menu_render
	python3 -m unittest tests.test_v2_phone_trade_rows_render
	python3 -m unittest tests.test_view_invariants
	python3 -m unittest tests.test_launch_front_door
	python3 -m unittest tests.test_launch_copy_guard
	python3 -m unittest tests.test_week_history
	python3 -m unittest tests.test_missing_section_render
	python3 -m unittest tests.test_lineup_content_week_advance
	python3 -m unittest tests.test_search_players_universe
	python3 -m unittest tests.test_published_league_settings_engine
	python3 -m unittest tests.test_player_tags

test-core-shard-2:
	python3 -m unittest tests.test_spec_reference_value_pipeline
	python3 -m unittest tests.test_value_pipeline_engine
	python3 -m unittest tests.test_games_remaining
	python3 -m unittest tests.test_comparison_source_integrity
	python3 -m unittest tests.test_superflex_publisher_values
	python3 -m unittest tests.test_one_name_resolver
	python3 -m unittest tests.test_razzball_refresh
	python3 -m unittest tests.test_pipelines_import_standalone
	python3 -m unittest tests.test_player_scenario_matrix
	python3 -m unittest tests.test_v2_compare
	python3 -m unittest tests.test_v2_finder_trifit
	node tests/test_v2_league_paste.js
	python3 -m unittest tests.test_v2_trade_story
	python3 -m unittest tests.test_v2_phone_customize_targets_render
	python3 -m unittest tests.test_v2_phone_fallback_font_render
	python3 -m unittest tests.test_v2_phone_rank_overflow_render
	python3 -m unittest tests.test_v2_phone_weight_render
	python3 -m unittest tests.test_v2_phone_wide_font_render
	python3 -m unittest tests.test_math_inspector
	python3 -m unittest tests.test_asset_load_retry
	python3 -m unittest tests.test_value_overrides
	python3 -m unittest tests.test_source_scale_agreement_retired
	python3 -m unittest tests.test_value_reference_worked_example
	python3 -m unittest tests.test_contract_qa_report

test-core-shard-3:
	python3 -m unittest tests.test_promotion_model_parity
	python3 -m unittest tests.test_ppg_tie_parity
	python3 -m unittest tests.test_source_curves_distinct
	python3 -m unittest tests.test_cbsros_bake_identity
	python3 -m unittest tests.test_player_alias_table
	python3 -m unittest tests.test_bake_on_change
	python3 -m unittest tests.test_trade_chart_ingest_ci
	python3 -m unittest tests.test_published_surfaces
	python3 -m unittest tests.test_v2_finder
	python3 -m unittest tests.test_v2_finder_viable
	python3 -m unittest tests.test_v2_finder_guardrails
	python3 -m unittest tests.test_v2_finder_saved_team tests.test_v2_finder_saved_team_render
	python3 -m unittest tests.test_waivers_math
	python3 -m unittest tests.test_v2_finder_projection_noise
	node tests/test_v2_name_format.js
	python3 -m unittest tests.test_v2_rescaled_copy
	node tests/node/source_views_check.mjs
	python3 -m unittest tests.test_v2_phone_source_links_render
	python3 -m unittest tests.test_v2_phone_zoom_render
	python3 -m unittest tests.test_main_table_engine_parity
	python3 -m unittest tests.test_espn_listed_rows
	python3 -m unittest tests.test_page_load_no_404
	python3 -m unittest tests.test_bench_share_low_pie
	python3 -m unittest tests.test_ddf_composite_value
	python3 -m unittest tests.test_view_switch_hidden_defaults
	python3 -m unittest tests.test_week_calendar
	python3 -m unittest tests.test_week_state
	python3 -m unittest tests.test_roster_convention
	python3 -m unittest tests.test_razzball_outlier_guard

test-core-shard-4:
	python3 -m unittest tests.test_static_export
	python3 -m unittest tests.test_rank_guard
	python3 -m unittest tests.test_kdst_removed
	python3 -m unittest tests.test_curve_default_guard
	python3 -m unittest tests.test_suffix_identity
	python3 -m unittest tests.test_jeg539_position_and_inactive_rules
	python3 -m unittest tests.test_razzball_one_save
	python3 -m unittest tests.test_fc_week4_value_repair_sql
	python3 -m unittest tests.test_v2_targets
	python3 -m unittest tests.test_waivers_views
	python3 -m unittest tests.test_v2_finder_triview_display
	python3 -m unittest tests.test_v2_headlines
	python3 -m unittest tests.test_v2_waterfall
	python3 -m unittest tests.test_v2_phone_landscape_render
	python3 -m unittest tests.test_v2_hamburger_nav_render
	python3 -m unittest tests.test_v2_phone_trade_actions_render
	python3 -m unittest tests.test_disagreement_units_render
	python3 -m unittest tests.test_bench_share_readout_matches_reference
	python3 -m unittest tests.test_position_weights_setter
	python3 -m unittest tests.test_row_missing_reasons
	python3 -m unittest tests.test_two_qb_direction
	python3 -m unittest tests.test_short_chart_waiver
	python3 -m unittest tests.test_roster_convention_parity

# Daily render sweep (JEG-976): the green headless render modules that are in neither test-core nor
# test-unit-modules (about 25 min together). Run by .github/workflows/render-sweep.yml, dispatched daily
# by pg_cron; never part of validate or a deploy. Keeps going past a failure and exits 1 at the end.
# tests/test_render_sweep_coverage.py fails when a render module is in no list; it runs in
# test-unit-modules (non-blocking, preview CI's full-suite job), not in test-core or validate.
test-render-sweep:
	python3 tests/run_suite.py test-render-extra

# JEG-1117 (Jeremy, 2026-10-26: split into 3 parallel jobs): the first scheduled sweep ran all of
# test-render-extra in one job and hit the 60-minute timeout. render-sweep.yml now runs these three
# targets as a matrix. Their union is exactly test-render-extra (no module twice, none missing):
# tests/test_render_sweep_shards.py fails otherwise, so a module added to test-render-extra must also
# be added to one shard. Balanced by the per-module times of run 40287913420 (about 25 minutes each;
# modules that run had not reached, at 80 s assumed, are spread by that guess).
test-render-sweep-1:
	python3 -m unittest tests.test_v2_paste_only_render
	python3 -m unittest tests.test_v2_audit_source_render
	python3 -m unittest tests.test_v2_chart_zones_render
	python3 -m unittest tests.test_v2_customize_cleanup_render
	python3 -m unittest tests.test_v2_finder_import_render
	python3 -m unittest tests.test_v2_divergence_chip_render
	python3 -m unittest tests.test_v2_name_search_render
	python3 -m unittest tests.test_v2_polish_render
	python3 -m unittest tests.test_v2_research_render
	python3 -m unittest tests.test_v2_source_count_render
	python3 -m unittest tests.test_v2_targets_combos_render
	python3 -m unittest tests.test_v2_writing_routes_render
	python3 -m unittest tests.test_v2_finder_chips_render
	python3 -m unittest tests.test_v2_finder_fit_render
	python3 -m unittest tests.test_v2_league_render
	python3 -m unittest tests.test_v2_mobile_phase1_render
	python3 -m unittest tests.test_v2_topbar_notice_render
	python3 -m unittest tests.test_v2_league_oppanel_render
	python3 -m unittest tests.test_jeg1216_lineup_render
	python3 -m unittest tests.test_v2_find_split_render

test-render-sweep-2:
	python3 -m unittest tests.test_v2_chart_fullscreen_render
	python3 -m unittest tests.test_v2_chart_fit_render
	python3 -m unittest tests.test_v2_advanced_render
	python3 -m unittest tests.test_v2_ddf_versions_render
	python3 -m unittest tests.test_v2_customize_pages_render
	python3 -m unittest tests.test_v2_deal_read_render
	python3 -m unittest tests.test_v2_names_render
	python3 -m unittest tests.test_v2_modules_render
	python3 -m unittest tests.test_v2_review_polish_render
	python3 -m unittest tests.test_v2_finder_collapse_render
	python3 -m unittest tests.test_v2_finder_impact_render
	python3 -m unittest tests.test_v2_finder_kdef_search_render
	python3 -m unittest tests.test_v2_finder_triview_render
	python3 -m unittest tests.test_v2_league_live_render
	python3 -m unittest tests.test_v2_league_shared_roster_render
	python3 -m unittest tests.test_v2_optimize_caption_render
	python3 -m unittest tests.test_v2_inputs_status_render
	python3 -m unittest tests.test_v2_league_parsed_render

test-render-sweep-3:
	python3 -m unittest tests.test_v2_consistency_render
	python3 -m unittest tests.test_v2_a11y_batch1_render
	python3 -m unittest tests.test_v2_a11y_batch2_render
	python3 -m unittest tests.test_v2_chart_height_render
	python3 -m unittest tests.test_v2_customize_legend_render
	python3 -m unittest tests.test_v2_held_chip_render
	python3 -m unittest tests.test_v2_plain_copy_render
	python3 -m unittest tests.test_v2_values_tab_ux_render
	python3 -m unittest tests.test_v2_finder_paste_render
	python3 -m unittest tests.test_basis_overrides_render
	python3 -m unittest tests.test_v2_all_projections_paused_render
	python3 -m unittest tests.test_v2_finder_box_render
	python3 -m unittest tests.test_v2_finder_eval_render
	python3 -m unittest tests.test_v2_finder_groups_render
	python3 -m unittest tests.test_v2_league_basis_render
	python3 -m unittest tests.test_v2_league_phone_render
	python3 -m unittest tests.test_v2_league_tables_render
	python3 -m unittest tests.test_jeg1213_acceptance_render
	python3 -m unittest tests.test_v2_overrides_basis_render
	python3 -m unittest tests.test_v2_league_top10_render
	# JEG-1058 / JEG-1059: the adjustment kind and the flag on every overridden value.
	python3 -m unittest tests.test_v2_override_adjustments_render

test-render-extra:
	python3 -m unittest tests.test_v2_a11y_batch1_render
	python3 -m unittest tests.test_v2_chart_fit_render
	python3 -m unittest tests.test_v2_a11y_batch2_render
	python3 -m unittest tests.test_v2_audit_source_render
	python3 -m unittest tests.test_v2_chart_height_render
	python3 -m unittest tests.test_v2_advanced_render
	python3 -m unittest tests.test_v2_chart_zones_render
	python3 -m unittest tests.test_v2_customize_legend_render
	python3 -m unittest tests.test_v2_ddf_versions_render
	python3 -m unittest tests.test_v2_customize_cleanup_render
	python3 -m unittest tests.test_v2_customize_pages_render
	python3 -m unittest tests.test_v2_deal_read_render
	python3 -m unittest tests.test_v2_finder_import_render
	python3 -m unittest tests.test_v2_divergence_chip_render
	python3 -m unittest tests.test_v2_held_chip_render
	python3 -m unittest tests.test_v2_name_search_render
	python3 -m unittest tests.test_v2_names_render
	python3 -m unittest tests.test_v2_modules_render
	python3 -m unittest tests.test_v2_polish_render
	python3 -m unittest tests.test_v2_research_render
	python3 -m unittest tests.test_v2_source_count_render
	python3 -m unittest tests.test_v2_review_polish_render
	python3 -m unittest tests.test_v2_plain_copy_render
	python3 -m unittest tests.test_v2_targets_combos_render
	python3 -m unittest tests.test_v2_values_tab_ux_render
	python3 -m unittest tests.test_v2_writing_routes_render
	python3 -m unittest tests.test_v2_finder_paste_render
	python3 -m unittest tests.test_v2_chart_fullscreen_render
	python3 -m unittest tests.test_v2_consistency_render
	python3 -m unittest tests.test_v2_paste_only_render
	# Render modules added on main after the sweep (wired here so the coverage guard passes; green status not yet verified).
	python3 -m unittest tests.test_basis_overrides_render
	python3 -m unittest tests.test_v2_all_projections_paused_render
	python3 -m unittest tests.test_v2_finder_box_render
	python3 -m unittest tests.test_v2_finder_chips_render
	python3 -m unittest tests.test_v2_finder_collapse_render
	python3 -m unittest tests.test_v2_finder_eval_render
	python3 -m unittest tests.test_v2_finder_fit_render
	python3 -m unittest tests.test_v2_finder_groups_render
	python3 -m unittest tests.test_v2_finder_impact_render
	python3 -m unittest tests.test_v2_finder_kdef_search_render
	python3 -m unittest tests.test_v2_finder_triview_render
	python3 -m unittest tests.test_v2_league_basis_render
	python3 -m unittest tests.test_v2_league_live_render
	python3 -m unittest tests.test_v2_league_phone_render
	python3 -m unittest tests.test_v2_league_render
	python3 -m unittest tests.test_v2_league_shared_roster_render
	python3 -m unittest tests.test_v2_league_oppanel_render
	python3 -m unittest tests.test_jeg1216_lineup_render
	python3 -m unittest tests.test_v2_league_tables_render
	python3 -m unittest tests.test_jeg1213_acceptance_render
	python3 -m unittest tests.test_v2_league_parsed_render
	python3 -m unittest tests.test_v2_league_top10_render
	python3 -m unittest tests.test_v2_find_split_render
	python3 -m unittest tests.test_v2_mobile_phase1_render
	python3 -m unittest tests.test_v2_optimize_caption_render
	python3 -m unittest tests.test_v2_overrides_basis_render
	# JEG-1058 / JEG-1059: the adjustment kind and the flag on every overridden value.
	python3 -m unittest tests.test_v2_override_adjustments_render
	python3 -m unittest tests.test_v2_topbar_notice_render
	python3 -m unittest tests.test_v2_inputs_status_render

# Contract QA report (JEG-491): runs every live contract check, writes docs/qa-report.md, exits non-zero on a failing line.
qa-report:
	python3 scripts/contract_qa_report.py

test-all: naming naming-convention test-unit

# Operating-model plan status (JEG-96). Reads lanes/plan.json + lanes/linear_fixture.json.
plan-status:
	@python3 lanes/plan_status.py

# Values explainer standalone build (make sync also builds it to dist/value-logic/index.html).
# Needs Playwright Chromium. MARK_REVIEWED=1 after re-checking the narrative.
values-explainer:
	python3 pipelines/build_values_explainer.py $(if $(MARK_REVIEWED),--mark-reviewed,)

serve:
	python3 -m http.server $(PORT) --directory app/trade-value-chart

# Serves the built dist/ -- the tree production publishes -- not app/. `make serve`
# serves app/trade-value-chart, which is not what users get. See docs/preview-deploys.md.
preview-local: sync
	python3 -m http.server $(PORT) --directory dist

deploy-status:
	gh run list --repo JB-barrel-droid/fantasy-tools --workflow "Deploy dashboard" --limit 5
