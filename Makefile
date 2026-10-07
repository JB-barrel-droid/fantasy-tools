.PHONY: help source-import source-match source-reference comparison-section comparison-reindex comparison-review comparison-promote comparison-merge source-news naming reference sync guard-harness test validate serve preview-local deploy-status supabase-import import-health watchdog plan-status pr-checklist

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
	@echo "  make comparison-promote Promote REVIEW_FILE into the live fixture (needs APPROVE)"
	@echo "  make source-news       Refresh player-news raw/source data and fixture"
	@echo "  make naming            Fail closed when players.json diverges from the naming manifest"
	@echo "  make reference         Validate current reference artifacts"
	@echo "  make sync              Copy reference artifacts into app/ and dist/"
	@echo "  make guard-harness     Run curve-widget guard math against fixture data"
	@echo "  make test              Run regression tests"
	@echo "  make watchdog          Run the source-pull watchdog (writes ops/watchdog/health.json)"
	@echo "  make validate          Run naming, reference, sync, and tests"
	@echo "  make serve             Serve the local dashboard"
	@echo "  make preview-local     Build dist/ the way production does, then serve dist/"
	@echo "  make deploy-status     Show recent GitHub deploy runs"
	@echo "  make pr-checklist      Validate PR discrimination proof checklist (requires BODY_FILE and DIFF_FILE)"

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

comparison-promote:
	@test -n "$(REVIEW_FILE)" || (echo "Set REVIEW_FILE=output/comparison-review/...-review.json" && exit 1)
	@if [ -n "$(AUTO)" ]; then \
		python3 pipelines/promote_comparison_section.py "$(REVIEW_FILE)" --auto; \
	else \
		test -n "$(APPROVE)" || (echo "Set APPROVE=\"<name> <YYYY-MM-DD> <reason>\" or AUTO=1" && exit 1); \
		python3 pipelines/promote_comparison_section.py "$(REVIEW_FILE)" --approve "$(APPROVE)"; \
	fi

source-news:
	python3 pipelines/ingest_player_news.py --fetch-rss

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
	node tools/guard_harness.mjs --simulate tier-mismatch --assert-bad

# Source value lineage: scrape live pages once, then build the lineage card.
# The lineage builder consumes dist/modules/live-page-scrape.json and must NOT
# re-scrape at build time (intermittent bot blocks used to silently poison the
# monitor with null live values). Run the scrape first, then the builder.
monitor-lineage:
	python3 pipelines/scrape_live_source_pages.py
	python3 pipelines/build_source_value_lineage.py

# Unit tests: no data/raw, snapshot, or external service dependency.
# Safe to run in CI (Pages deploy) where gitignored data is absent.
test-unit:
	python3 -m unittest tests.test_migrations
	python3 -m unittest tests.test_bake_espn_zero_universe
	python3 -m unittest tests.test_match_identity_keys
	python3 -m unittest tests.test_sleeper_identity_layer
	python3 -m unittest tests.test_drift_snapshot_baseline
	python3 -m unittest tests.test_pull_fantasycalc_12team
	python3 -m unittest tests.test_published_surfaces
	python3 -m unittest tests.test_monitoring_coverage
	python3 -m unittest tests.test_source_snapshot_match
	python3 -m unittest tests.test_rebuild_chain_failclosed
	python3 -m unittest tests.test_refresh_fantasycalc_supabase
	python3 -m unittest tests.test_health_artifacts_summary_step
	python3 -m unittest tests.test_health_artifacts_watch
	python3 -m unittest tests.test_load_ddf_leg_contract
	python3 -m unittest tests.test_per_source_rescale
	python3 -m unittest tests.test_verify_cbsros_legs
	python3 -m unittest tests.test_review_live_verify_combo
	python3 -m unittest tests.test_review_coverage_live_verify
	python3 -m unittest tests.test_publication_window_content_week
	python3 -m unittest tests.test_build_lag_gate
	python3 -m unittest tests.test_import_health
	python3 -m unittest tests.test_verify_import_health
	python3 -m unittest tests.test_promote_section
	python3 -m unittest tests.test_adjusted_curve_pause
	python3 -m unittest tests.test_adjusted_fixture_sections
	python3 -m unittest tests.test_adjustment_inputs
	python3 -m unittest tests.test_checkpoint_expected_week
	python3 -m unittest tests.test_checkpoint_pages_deploy
	python3 -m unittest tests.test_c10_committed_fixture_baseline
	python3 -m unittest tests.test_checkpoints_health_freshest
	python3 -m unittest tests.test_checkpoint_c2_collection
	python3 -m unittest tests.test_health_artifacts_publish
	python3 -m unittest tests.test_workflow_no_event_interpolation
	python3 -m unittest tests.test_trade_chart_ingest_ci
	python3 -m unittest tests.test_razzball_sync_ci
	python3 -m unittest tests.test_dashboard_fleet_counts_sections
	python3 -m unittest tests.test_dashboard_loader_declarations
	python3 -m unittest tests.test_comparison_candidate_build
	python3 -m unittest tests.test_comparison_source_integrity
	python3 -m unittest tests.test_bake_cbsros_intake
	python3 -m unittest tests.test_curve_default_guard
	python3 -m unittest tests.test_guard_harness_recorded
	python3 -m unittest tests.test_jeg68_starter_markup
	python3 -m unittest tests.test_jeg69_direction_check
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
	python3 -m unittest tests.test_validate_imputed_vorps
	python3 -m unittest tests.test_projection_source_kind
	python3 -m unittest tests.test_vorp_translation_unified
	python3 -m unittest tests.test_vorp_translation_js_parity
	python3 -m unittest tests.test_published_league_settings_engine
	python3 -m unittest tests.test_published_league_settings_render
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
	python3 -m unittest tests.test_translate_via_vorp
	python3 -m unittest tests.test_lineage_snapshot_guard
	python3 -m unittest tests.test_lock_revert_notice_render
	python3 -m unittest tests.test_methodology_consistency
	python3 -m unittest tests.test_player_scenario_matrix
	python3 -m unittest tests.test_public_copy_no_vorp
	python3 -m unittest tests.test_product_data_wiring
	python3 -m unittest tests.test_source_freshness
	python3 -m unittest tests.test_publication_windows
	python3 -m unittest tests.test_qb_slot_scoping
	python3 -m unittest tests.test_source_combo_contract
	python3 -m unittest tests.test_razzball_monitor_coverage
	python3 -m unittest tests.test_indexed_monitor_math
	python3 -m unittest tests.test_lineage_merge
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
	python3 -m unittest tests.test_methodology_payload
	python3 -m unittest tests.test_sync_health_freshest
	python3 -m unittest tests.test_two_tier_frontend
	python3 -m unittest tests.test_dashboard_view_tags
	python3 -m unittest tests.test_view_artifacts
	python3 -m unittest tests.test_lineage_view_indicators
	python3 -m unittest tests.test_dist_manifest
	python3 -m unittest tests.test_preview_workflow_matches_pages
	python3 -m unittest tests.test_sync_monitor_fixture
	python3 -m unittest tests.test_rebuild_chain_workflow
	python3 -m unittest tests.test_workflow_dispatch_permissions
	python3 -m unittest tests.test_live_page_synthetic_workflow
	python3 -m unittest tests.test_player_identity_guard
	python3 -m unittest tests.test_espn_ci_workflow
	python3 -m unittest tests.test_github_actions_status
	python3 -m unittest tests.test_check_fidelity_ordering
	python3 -m unittest tests.test_input_lineage
	python3 -m unittest tests.test_deploy_gate_unconditional
	python3 -m unittest tests.test_artifact_generated_at
	python3 -m unittest tests.test_production_verify
	python3 -m unittest tests.test_identity_case_duplicates
	python3 -m unittest tests.test_lane_protocol
	python3 -m unittest tests.test_pr_template_checklist
	python3 -m unittest tests.test_doc_vs_code
	python3 -m unittest lanes.test_plan_tracker


# Integration tests: require data/raw snapshots, Supabase, or pipeline artifacts.
# Run in the rebuild-chain workflow or locally where data is present.
test-integration:
	python3 -m unittest tests.test_cbs_usatoday_recurring
	python3 -m unittest tests.test_naming_drift
	python3 -m unittest tests.test_pipeline_cascade
	python3 -m unittest tests.test_pull_watchdog
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

watchdog:
	python3 ops/watchdog/pull_watchdog.py

validate: naming naming-convention reference sync guard-harness test-unit

# Operating-model plan status (JEG-96). Reads lanes/plan.json + lanes/linear_fixture.json.
plan-status:
	@python3 lanes/plan_status.py

serve:
	python3 -m http.server $(PORT) --directory app/trade-value-chart

# Serves the built dist/ -- the tree production publishes -- not app/. `make serve`
# serves app/trade-value-chart, which is not what users get. See docs/preview-deploys.md.
preview-local: sync
	python3 -m http.server $(PORT) --directory dist

deploy-status:
	gh run list --repo JB-barrel-droid/fantasy-tools --workflow "Deploy dashboard" --limit 5

pr-checklist:
	@test -n "$(BODY_FILE)" || (echo "Set BODY_FILE=<pr-body.md>" && exit 1)
	@test -n "$(DIFF_FILE)" || (echo "Set DIFF_FILE=<pr.diff>" && exit 1)
	python3 pipelines/check_pr_discrimination.py --body-file $(BODY_FILE) --diff-file $(DIFF_FILE)
