# Modular Pipeline

The dashboard should run in four plain stages. Each stage owns one job and hands
files to the next stage.

```text
source data -> reference compute -> dashboard build -> frontend/site
```

## 1. Source Data

Source jobs collect raw snapshots from trade-value pages, public APIs, RSS feeds,
or Muse scrapers.

Input: external pages and feeds.

Output: timestamped raw files under `data/raw/`.

Rule: source jobs collect facts only. They do not decide final player identity,
fixed-pie math, or dashboard behavior.

Current repo-owned source job:

```bash
make source-news
```

Import a scraped trade-value page from Muse or another scraper:

```bash
make source-import SOURCE_FILE=/path/to/scrape.csv SOURCE=fantasycalc SCORING=ppr TEAMS=12
```

The importer writes a `trade-value-source-snapshot-v1` JSON file under
`data/raw/sources/`. That snapshot is raw source input; it is not player-key
matched and it is not safe to publish directly.

Muse may stay responsible for difficult page scraping if it is free and stable,
but its output should be treated as raw input to this repo.

## 2. Reference Compute

Reference jobs turn raw/source files into stable dashboard artifacts.

Input: `data/raw/` plus any imported Muse/source snapshots.

Output: `data/fixtures/current/players.json`,
`data/fixtures/current/comparison-sources-data.json`, and
`data/fixtures/current/player-news.json`.

Current command:

```bash
make reference
```

Today this validates the finished artifacts and writes
`output/reference-build-report.json`. As collectors move into the repo, this is
the command that should grow into the real compute step.

## 3. Dashboard Build

The dashboard build copies finished reference artifacts into the static app and
deployable output.

Input: `data/fixtures/current/`.

Output: `app/trade-value-chart/` and `dist/`.

Command:

```bash
make sync
```

## 4. Frontend And Site

The frontend displays the finished reference artifacts. It can own user
interaction such as filters, zoom, sorting, source toggles, tooltips, and local
roster-shape inspection.

It should not be the long-term home for source scraping, player identity
matching, or canonical reference-data computation.

Local run:

```bash
make serve
```

GitHub Pages deploys `dist/` after pushes to `main`.

## Safe Work Order

Use this order for ordinary changes:

```bash
make reference
make sync
make test
```

Or run all three:

```bash
make validate
```

## Next Migration Rule

Move one source at a time.

For each new source, add:

1. a raw snapshot format,
2. a parser/normalizer,
3. identity matching that fails closed,
4. a reference artifact update,
5. a test proving nulls, zeros, and player keys behave correctly.
