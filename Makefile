.PHONY: help source-import source-match source-reference source-news reference sync test validate serve deploy-status

TODAY ?= $(shell date +%F)
PORT ?= 8000
SOURCE_FILE ?=
SNAPSHOT_FILE ?=
MATCH_FILE ?=
SOURCE ?=
SCORING ?= ppr
TEAMS ?= 12

help:
	@echo "Modular dashboard commands:"
	@echo "  make source-import     Import SOURCE_FILE into standard raw source format"
	@echo "  make source-match      Match SNAPSHOT_FILE rows to canonical player_key values"
	@echo "  make source-reference  Build a source reference artifact from MATCH_FILE"
	@echo "  make source-news       Refresh player-news raw/source data and fixture"
	@echo "  make reference         Validate current reference artifacts"
	@echo "  make sync              Copy reference artifacts into app/ and dist/"
	@echo "  make test              Run regression tests"
	@echo "  make validate          Run reference, sync, and tests"
	@echo "  make serve             Serve the local dashboard"
	@echo "  make deploy-status     Show recent GitHub deploy runs"

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

source-news:
	python3 pipelines/ingest_player_news.py --fetch-rss

reference:
	python3 pipelines/build_reference_data.py --today $(TODAY)

sync:
	python3 pipelines/sync_dashboard_artifacts.py

test:
	python3 -m unittest discover -s tests

validate: reference sync test

serve:
	python3 -m http.server $(PORT) --directory app/trade-value-chart

deploy-status:
	gh run list --repo JB-barrel-droid/fantasy-tools --workflow "Deploy dashboard" --limit 5
