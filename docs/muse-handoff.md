# Fantasy Tools Modular Pipeline Handoff

Purpose: continue moving the Trade Value Dashboard toward a modular setup where Muse or other scrapers can collect data, but the repo owns normalization, player matching, reference artifacts, validation, dashboard build, and publishing.

## Current Links

- GitHub repo: https://github.com/JB-barrel-droid/fantasy-tools
- Public dashboard: https://jb-barrel-droid.github.io/fantasy-tools/
- Main branch currently deployed through GitHub Pages.

## Operating Goal

The project should not depend on ChatGPT/Codex as runtime infrastructure.

LLMs can work on the system:

- improve scraper adapters
- edit pipeline code
- add tests
- fix dashboard bugs
- document decisions

LLMs should not be inside the operating path:

- not the only way to refresh data
- not the only way to deploy the preview site
- not the only holder of process memory

The desired flow is:

```text
source data -> reference compute -> dashboard build -> frontend/site
```

## What Is Already Working

The repo now has a public GitHub home and Pages deploy:

- GitHub Actions runs `make validate`.
- `make validate` runs reference validation, dashboard sync, and tests.
- Passing pushes deploy `dist/` to GitHub Pages.

The current dashboard link is live:

```text
https://jb-barrel-droid.github.io/fantasy-tools/
```

## Current Command Layer

The repo has a `Makefile` with these commands:

```bash
make source-import
make source-match
make source-reference
make source-news
make reference
make sync
make test
make validate
make serve
make deploy-status
```

Important current commands:

```bash
make validate
```

Runs the safe validation path.

```bash
make serve
```

Runs the local dashboard.

```bash
make source-import SOURCE_FILE=/path/to/scrape.csv SOURCE=fantasycalc SCORING=ppr TEAMS=12
```

Imports a Muse or scraper output file into the standard raw source snapshot format.

```bash
make source-match SNAPSHOT_FILE=data/raw/sources/fantasycalc/2026-09-21/fantasycalc-ppr-12-2026-09-21T120000z.json
```

Matches imported source rows to canonical `player_key` values.

```bash
make source-reference MATCH_FILE=output/source-matches/fantasycalc/2026-09-21/fantasycalc-ppr-12-matched.json
```

Builds a source-reference artifact from matched rows.

## Important Files Added

### `Makefile`

Creates the operator command layer so work is not dependent on remembered ChatGPT instructions.

### `docs/modular-pipeline.md`

Explains the four-stage pipeline boundary:

```text
source data -> reference compute -> dashboard build -> frontend/site
```

### `pipelines/build_reference_data.py`

Validates current finished dashboard fixtures:

- `players.json`
- `comparison-sources-data.json`
- `player-news.json`

This is intentionally a thin boundary today. It does not fully recompute all reference data yet. Future source compute work should grow behind this command.

### `pipelines/import_source_snapshot.py`

Imports a scraped CSV or JSON into:

```text
trade-value-source-snapshot-v1
```

This is raw source input only. It does not match players and does not compute dashboard-ready values.

### `pipelines/match_source_snapshot.py`

Matches a raw source snapshot to canonical `player_key` values from `players.json`.

Rules:

- match by normalized player name
- use `team` / `pos` only to resolve duplicate names
- unmatched rows go to `review_rows`
- ambiguous rows go to `review_rows`
- no guessing

### `pipelines/build_source_reference.py`

Builds:

```text
trade-value-source-reference-v1
```

This creates one row per canonical `player_key` and preserves source values. Conflicting duplicate values for the same `player_key` go to review instead of being silently merged.

## Tests Added

The test suite grew to 27 passing tests before the current interrupted local work.

New tests cover:

- source snapshot import from CSV
- source snapshot import from JSON value maps
- fail-closed player matching
- suffix normalization such as `Jr.`
- duplicate-name resolution with team/position
- unknown player review rows
- ambiguous player review rows
- source-reference artifact shape
- duplicate `player_key` conflict handling

## Current Committed Chain

This chain is committed and pushed:

```text
scraped CSV/JSON
-> trade-value-source-snapshot-v1
-> trade-value-source-matches-v1
-> trade-value-source-reference-v1
```

This is the important new modular source ingestion foundation.

## Current Git Commits From This Session

Recent commits:

```text
4cca825 Add source reference artifact builder
88eb008 Add source snapshot player matching
8d6fc1a Add source snapshot import boundary
f4c4004 Add modular pipeline command layer
61c8dc7 Add GitHub Pages dashboard deploy
```

## Current Local Work In Progress

There is uncommitted local work that started the next bridge:

```text
pipelines/build_comparison_source_section.py
pipelines/merge_comparison_candidate.py
tests/test_comparison_candidate_build.py
```

Also modified:

```text
Makefile
README.md
docs/modular-pipeline.md
```

This local work was started but not completed, validated, committed, or pushed before the handoff request.

Intended next bridge:

```text
trade-value-source-reference-v1
-> candidate comparison source section
-> output/comparison-sources-data-candidate.json
```

The important safety rule: this should write only to `output/`. It should not replace:

```text
data/fixtures/current/comparison-sources-data.json
```

until it is tested and reviewed.

## Suggested Next Task For Muse

Finish the candidate comparison bridge.

Goal:

```text
source-reference artifact
-> candidate comparison-source section
-> candidate comparison-sources-data artifact in output/
```

Do not publish it to the dashboard yet.

Suggested steps:

1. Review `pipelines/build_comparison_source_section.py`.
2. Review `pipelines/merge_comparison_candidate.py`.
3. Review `tests/test_comparison_candidate_build.py`.
4. Run:

```bash
make validate
```

5. If tests fail, fix the candidate bridge.
6. If tests pass, commit with a message like:

```text
Add comparison candidate bridge
```

7. Push to GitHub and verify GitHub Actions passes.

## Important Data Boundary

Muse can remain responsible for difficult scraping if it is free and stable.

But Muse should output raw source data only.

The repo should own:

- source snapshot schema
- player identity matching
- review rows for ambiguous/unmatched players
- source-reference artifacts
- fixed-pie/reference compute
- validation tests
- dashboard build
- GitHub Pages deploy

The rule:

```text
Muse can collect. The repo decides, computes, tests, and publishes.
```

## What Not To Do Yet

Do not replace the live comparison fixture yet:

```text
data/fixtures/current/comparison-sources-data.json
```

Do not publish candidate comparison data to the dashboard until:

- candidate section builder is tested
- merge candidate script is tested
- output candidate is inspected
- current known-good fixture can be reproduced or compared
- null vs zero behavior is protected
- player_key matching review rows are clear

Do not silently merge duplicate player rows.

Do not guess player identity.

Do not move authenticated FantasyPros scraping first.

## Current Architecture Reality

The dashboard can run and deploy without ChatGPT now.

Still fragile or incomplete:

- full upstream trade-value computation is not yet rebuilt in this repo
- Muse-era collectors/scripts are still partly outside the repo
- source scraping is not fully automated source-by-source
- fixed-pie reindexing is not yet modularized behind a source-reference pipeline
- client-side code still owns meaningful display and some interim calculation behavior

## Practical North Star

Work source-by-source.

For each source:

1. scrape or export raw data
2. import to `trade-value-source-snapshot-v1`
3. match to canonical `player_key`
4. build source-reference artifact
5. build candidate comparison section
6. compare against current fixture
7. only then wire into reference compute

## Quick Recovery Commands

Check repo state:

```bash
git --git-dir=.gitstore --work-tree=. status --short
```

Run validation:

```bash
make validate
```

Check deploys:

```bash
make deploy-status
```

Serve local dashboard:

```bash
make serve
```

Public dashboard:

```text
https://jb-barrel-droid.github.io/fantasy-tools/
```

GitHub repo:

```text
https://github.com/JB-barrel-droid/fantasy-tools
```

