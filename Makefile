.PHONY: help source-import source-news reference sync test validate serve deploy-status

TODAY ?= $(shell date +%F)
PORT ?= 8000
SOURCE_FILE ?=
SOURCE ?=
SCORING ?= ppr
TEAMS ?= 12

help:
	@echo "Modular dashboard commands:"
	@echo "  make source-import     Import SOURCE_FILE into standard raw source format"
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
