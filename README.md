# Fantasy Tools Migration

This repository is the migration target for the fantasy-football Trade Value Dashboard currently running in Muse.

Current status: the Muse export has been imported into `app/trade-value-chart/` with current finished data fixtures under `data/fixtures/current/`.

## Goals

- Preserve the current Muse dashboard as the reference implementation.
- Reproduce the current Trade Value Dashboard outside Muse using the existing finished data artifacts first.
- Keep Supabase as the production database.
- Move calculations and collectors out of Muse incrementally only after equivalence tests exist.

## Intended Structure

- `app/` - lightweight web dashboard outside Muse.
- `trade_value/` - Trade Value domain logic and adapters.
- `pipelines/` - reproducible build and data-artifact generation steps.
- `shared/` - shared identity, scoring, team, and Supabase access helpers.
- `tests/` - regression and golden-output tests.
- `docs/` - migration documentation and status.

The exact source layout may be adjusted after the Muse ZIP is inspected. Existing paths should be preserved initially if that makes behavioral verification easier.

## Local Run

Serve the static dashboard locally:

```bash
python3 -m http.server 8000 --directory app/trade-value-chart
```

Then open:

```text
http://localhost:8000
```

## Tests

Run the current dependency-free regression checks:

```bash
python3 -m unittest discover -s tests
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

Pull the free league-wide RSS feeds into the raw article store, then rebuild the dashboard fixture and review queues:

```bash
python3 pipelines/ingest_player_news.py --fetch-rss
```

Add the daily per-player Google News layer for the top watchlist players:

```bash
python3 pipelines/ingest_player_news.py --fetch-rss --fetch-google-news --watchlist-top 200
```

Curated news adjustments are read from `data/raw/player-news-adjustments.json` and the checked-but-not-adjusted log is read from `data/raw/news-checked.json`. Ambiguous full-name matches are written to `output/player-news-unmatched.json`; injury and suspension items that need a reviewer are written to `output/player-news-review-queue.json`.

Sync the finished fixtures into the static dashboard and deployable `dist/` output:

```bash
python3 pipelines/sync_dashboard_artifacts.py
```

## Git Note

This workspace currently rejects creating `.git`. A persistent external Git directory is being used at `.gitstore/` until normal repository metadata can be created.

Use:

```bash
git --git-dir=.gitstore --work-tree=. status
```

## Secrets

Do not commit `.env`, Supabase keys, service-role keys, cookies, browser sessions, FantasyPros credentials, or any raw private export containing secrets.
