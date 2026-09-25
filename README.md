# Fantasy Tools Migration

This repository is the migration target for the fantasy-football Trade Value Dashboard currently running in Muse.

Current status: the Muse export has been imported into `app/trade-value-chart/` with current finished data fixtures under `data/fixtures/current/`.

## Goals

- Preserve the current Muse dashboard as the reference implementation.
- Reproduce the current Trade Value Dashboard outside Muse using the existing finished data artifacts first.
- Keep Supabase as the production database.
- Move calculations and collectors out of Muse incrementally only after equivalence tests exist.

## Working with AI sessions

`CLAUDE.md` holds the working agreements — most importantly, that every session
appends to `docs/claude-log.md` before it finishes, separating what it verified
from what it only claimed. Read the log before starting: it carries forward what
the last session measured, what it asserted without checking, and what is still
open.

## Structure

- `app/trade-value-chart/` - the dashboard source: `index.html` plus `assets/`.
- `dist/` - generated. Exactly what GitHub Pages publishes; never edit by hand.
- `data/fixtures/current/` - the finished artifacts everything else builds from.
- `data/inputs/`, `data/raw/` - vendored source inputs and raw pulls (`raw/` is ignored).
- `pipelines/` - build and data-artifact generation steps; shared helpers in `pipelines/lib/`.
- `modules/` - the module monitor (`dashboard.html`), published to `dist/modules/`.
- `ops/watchdog/` - source-pull watchdog and per-source ingesters.
- `weekly_vegas/` - Weekly Vegas dashboard (Vegas-vs-ECR disagreement signals) + its build pipeline (bin/, collectors/, engine/, v4/, loaders/, sql/, docs/, research/); a segmented sibling tree to the trade-value chart, not part of it. See `weekly_vegas/README.md`.
- `waiver_wire/` - Waiver dashboard (weekly add / don't-add / drop board) + its build pipeline (bin/, engine/, sql/); a segmented sibling tree to both the trade-value chart and `weekly_vegas/`. Its only cross-tree relationship is a read-only input from the published chart fixture `data/fixtures/current/players.json`. See `waiver_wire/README.md`.
- `tests/` - regression and golden-output tests.
- `docs/` - migration documentation and status.

An earlier plan also called for top-level `trade_value/` and `shared/` packages.
Neither was ever used: domain logic lives in `pipelines/` and the shared identity,
scoring, and naming helpers live in `pipelines/lib/`. The empty placeholders were
removed rather than left standing as structure that does not exist.

## Local Run

Serve the static dashboard locally:

```bash
make serve
```

Then open:

```text
http://localhost:8000
```

## Tests

Run the normal validation path:

```bash
make validate
```

That validates the finished reference artifacts, syncs them into the static
dashboard output, and runs the regression tests.

Run the current dependency-free regression checks:

```bash
make test
```

Check reference freshness without mutating source artifacts:

```bash
python3 pipelines/check_reference_freshness.py --today YYYY-MM-DD
```

The report is written to ignored `output/reference-freshness.json` and records when a reference date is unchanged from the prior run.

Ingest play/value news when a raw JSON or JSONL feed is available:

```bash
python3 pipelines/ingest_player_news.py --input data/raw/player-news.jsonl
```

Import a scraped trade-value page from Muse or another scraper into the standard
raw source format:

```bash
make source-import SOURCE_FILE=/path/to/scrape.csv SOURCE=fantasycalc SCORING=ppr TEAMS=12
```

Match an imported source snapshot to canonical player keys:

```bash
make source-match SNAPSHOT_FILE=data/raw/sources/fantasycalc/2026-09-21/fantasycalc-ppr-12-2026-09-21T120000z.json
```

Build a source-reference artifact from matched rows:

```bash
make source-reference MATCH_FILE=output/source-matches/fantasycalc/2026-09-21/fantasycalc-ppr-12-matched.json
```

Pull the free league-wide RSS feeds into the raw article store, then rebuild the dashboard fixture and review queues:

```bash
python3 pipelines/ingest_player_news.py --fetch-rss
```

Add the daily per-player Google News layer for the top watchlist players:

```bash
python3 pipelines/ingest_player_news.py --fetch-rss --fetch-google-news --watchlist-top 200
```

Curated news adjustments are read from `data/raw/player-news-adjustments.json` and the checked-but-not-adjusted log is read from `data/raw/news-checked.json`. Ambiguous full-name matches are written to `output/player-news-unmatched.json`; injury and suspension items that need a reviewer are written to `output/player-news-review-queue.json`.

Muse player-news bundles can be unpacked under `data/raw/muse-player-news/`; copy `poll_log.jsonl`, `news_adjustments.json`, `news_checked.json`, and `news_consumed.json` to the default raw filenames above before running the ingester. The Google News pull automatically uses the latest `data/raw/muse-player-news/news-watchlist*.json` file when present, or you can pass one explicitly:

```bash
python3 pipelines/ingest_player_news.py --fetch-rss --fetch-google-news --watchlist data/raw/muse-player-news/news-watchlist-week2-2026-09-20.json
```

For late-week builds, fail closed unless supplemental injury data is fresh as of Friday evening or later:

```bash
python3 pipelines/ingest_player_news.py --require-fresh-injury-data --injury-data-updated-at 2026-09-18T18:30:00-05:00
```

When the raw player-news store contains `fetched_at` timestamps, the ingester can derive that freshness proof automatically:

```bash
python3 pipelines/ingest_player_news.py --require-fresh-injury-data
```

Sync the finished fixtures into the static dashboard and deployable `dist/` output:

```bash
make sync
```

## Modular Pipeline

The project should move in four stages:

```text
source data -> reference compute -> dashboard build -> frontend/site
```

- `source data`: collect raw snapshots from feeds, public pages, APIs, or Muse.
- `reference compute`: turn raw/source snapshots into stable fixtures under
  `data/fixtures/current/`.
- `dashboard build`: copy finished fixtures into `app/trade-value-chart/` and
  `dist/`.
- `frontend/site`: display the finished artifacts and handle user interaction.

See `docs/modular-pipeline.md` for the working boundary rules.

## Publishing

There is one publish path. Pushing to `main` runs `.github/workflows/pages.yml`,
which runs `make validate` and deploys `dist/` to GitHub Pages.

`make validate` is the same gate locally: it checks naming drift, validates the
reference artifacts, regenerates `dist/` from `app/` and the current fixtures,
and runs the test suite. Because `sync` regenerates `dist/`, editing anything
under `dist/` by hand is always wrong -- edit `app/trade-value-chart/` (or the
fixtures) and re-run `make sync`.

After a deploy, confirm the live site matches the repo:

```bash
python3 verify_live.py
```

## Secrets

Do not commit `.env`, Supabase keys, service-role keys, cookies, browser sessions, FantasyPros credentials, or any raw private export containing secrets.
