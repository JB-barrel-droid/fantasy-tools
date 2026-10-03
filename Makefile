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
	@echo "  make import-health   Verify all seven import sources are fresh (needs NFL_WEEK=<current NFL week>, passed by the watchdog/cron)"
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
	@test -n "$(NFL_WEEK)" || (echo "Set NFL_WEEK=<current NFL week>; the pull watchdog/cron passes it" && exit 1)
	python3 pipelines/verify_import_health.py --nfl-week "$(NFL_WEEK)"

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
	python3 -m unittest tests.test_adjusted_curve_pause
	python3 -m unittest tests.test_adjusted_fixture_sections
	python3 -m unittest tests.test_adjustment_inputs
	python3 -m unittest tests.test_checkpoint_expected_week
	python3 -m unittest tests.test_checkpoint_pages_deploy
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
	python3 -m unittest tests.test_jeg135_rendered_flexibility
	python3 -m unittest tests.test_ddf_two_tier_leg
	python3 -m unittest tests.test_imputed_vorps_validation
	python3 -m unittest tests.test_imputed_vorps_precision
	python3 -m unittest tests.test_imputed_roster_config
	python3 -m unittest tests.test_espn_pool_cap
	python3 -m unittest tests.test_vorp_refresh
	python3 -m unittest tests.test_projection_source_kind
	python3 -m unittest tests.test_vorp_translation_unified
	python3 -m unittest tests.test_vorp_wiring
	python3 -m unittest tests.test_translate_via_vorp
	python3 -m unittest tests.test_lineage_snapshot_guard
	python3 -m unittest tests.test_lock_revert_notice_render
	python3 -m unittest tests.test_methodology_consistency
	python3 -m unittest tests.test_player_scenario_matrix
	python3 -m unittest tests.test_public_copy_no_vorp
	python3 -m unittest tests.test_publication_windows
	python3 -m unittest tests.test_qb_slot_scoping
	python3 -m unittest tests.test_source_combo_contract
	python3 -m unittest tests.test_razzball_monitor_coverage
	python3 -m unittest tests.test_lineage_merge
	python3 -m unittest tests.test_espn_zeroed_staleness
	python3 -m unittest tests.test_razzball_supabase
	python3 -m unittest tests.test_reference_freshness
	python3 -m unittest tests.test_reindex_section
	python3 -m unittest tests.test_review_candidate
	python3 -m unittest tests.test_source_reference_build
	python3 -m unittest tests.test_scheduler_slip
	python3 -m unittest tests.test_static_export
	python3 -m unittest tests.test_methodology_payload
	python3 -m unittest tests.test_sync_health_freshest
	python3 -m unittest tests.test_two_tier_frontend
	python3 -m unittest tests.test_dist_manifest
	python3 -m unittest tests.test_preview_workflow_matches_pages
	python3 -m unittest tests.test_sync_monitor_fixture
	python3 -m unittest tests.test_rebuild_chain_workflow
	python3 -m unittest tests.test_player_identity_guard
	python3 -m unittest tests.test_espn_ci_workflow
	python3 -m unittest tests.test_github_actions_status
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
	python3 -m unittest tests.test_import_health
	python3 -m unittest tests.test_naming_drift
	python3 -m unittest tests.test_pipeline_cascade
	python3 -m unittest tests.test_promote_section
	python3 -m unittest tests.test_pull_watchdog
	python3 -m unittest tests.test_rebuild_chain_failclosed
	python3 -m unittest tests.test_save_espn_cbs_references
	python3 -m unittest tests.test_source_snapshot_import
	python3 -m unittest tests.test_source_snapshot_match
	python3 -m unittest tests.test_supabase_import
	python3 -m unittest tests.test_writer_audit_enforcement

# Full suite (local dev / rebuild workflow).
test: test-unit test-integration

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
