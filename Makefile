.PHONY: help source-import source-match source-reference comparison-section comparison-reindex comparison-review comparison-promote comparison-merge source-news naming reference sync test validate serve deploy-status supabase-import import-health watchdog

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
	@echo "  make import-health   Verify all five import sources are fresh (needs NFL_WEEK=<current NFL week>, passed by the watchdog/cron)"
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
	@echo "  make test              Run regression tests"
	@echo "  make watchdog          Run the source-pull watchdog (writes ops/watchdog/health.json)"
	@echo "  make validate          Run naming, reference, sync, and tests"
	@echo "  make serve             Serve the local dashboard"
	@echo "  make deploy-status     Show recent GitHub deploy runs"

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
	@test -n "$(APPROVE)" || (echo "Set APPROVE=\"<name> <YYYY-MM-DD> <reason>\"" && exit 1)
	python3 pipelines/promote_comparison_section.py "$(REVIEW_FILE)" --approve "$(APPROVE)"

source-news:
	python3 pipelines/ingest_player_news.py --fetch-rss

naming:
	python3 pipelines/check_naming_drift.py

reference:
	python3 pipelines/build_reference_data.py --today $(TODAY)

sync:
	python3 pipelines/sync_dashboard_artifacts.py

test:
	python3 -m unittest discover -s tests

watchdog:
	python3 ops/watchdog/pull_watchdog.py

validate: naming reference sync test

serve:
	python3 -m http.server $(PORT) --directory app/trade-value-chart

deploy-status:
	gh run list --repo JB-barrel-droid/fantasy-tools --workflow "Deploy dashboard" --limit 5
