# Modular Pipeline

Standing rules for every stage live in `docs/pipeline-rules.md` (naming
authority, fail-closed identity, candidate promotion, null-not-zero, content
vintage, public copy). GitHub is the store of record; if a rule is not written
there, it does not exist.

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

Match an imported source snapshot to canonical `player_key` values:

```bash
make source-match SNAPSHOT_FILE=data/raw/sources/fantasycalc/2026-09-21/fantasycalc-ppr-12-2026-09-21T120000z.json
```

The matcher writes a `trade-value-source-matches-v1` file under
`output/source-matches/`. Unmatched or ambiguous names stay in `review_rows`.
They are not guessed.

Build a source-reference artifact from matched rows:

```bash
make source-reference MATCH_FILE=output/source-matches/fantasycalc/2026-09-21/fantasycalc-ppr-12-matched.json
```

The source-reference artifact has one row per canonical `player_key` and keeps
source values separate from dashboard display math. Duplicate player-key rows
with conflicting values are sent to review instead of being merged.

Build a candidate comparison source section from the reference artifact:

```bash
make comparison-section REFERENCE_FILE=output/source-references/fantasycalc/2026-09-21/fantasycalc-ppr-12-reference.json
```

The section builder emits a `trade-value-comparison-section-candidate-v1` file
under `output/comparison-candidates/`, shaped like one entry of the comparison
fixture's `sources{}` map. It carries native source values only
(`reindex_status: "pending"` -- fixed-pie reindexing is reference-compute math
and must be reviewed before promotion). Player keys with no canonical fixture
slug and non-numeric values go to `review_rows`; nothing is guessed and nothing
is zero-filled.

Merge the candidate section into a reviewable candidate artifact:

```bash
make comparison-merge CANDIDATE_FILE=output/comparison-candidates/fantasycalc/2026-09-21/fantasycalc-full-12-section.json
```

This writes `output/comparison-sources-data-candidate.json` (a deep copy of the
live fixture with the candidate section installed and marked `"candidate"`)
plus `output/comparison-candidate-report.json` (native-value deltas against the
current baseline for the same section key, when one exists). It refuses to
write anywhere under `data/` -- the live fixture is read-only here.

Do not promote a candidate into `data/fixtures/current/` until the checklist in
`docs/pipeline-rules.md` ("Candidate artifacts stay in output/") is complete.

Combo keys map the reference artifact's scoring vocabulary (`ppr`/`half_ppr`/
`standard`) onto the fixture's (`full`/`half`/`standard`). The reference
artifact carries no QB-count split, so candidate combos are QB-unspecified and
will show zero overlap against QB-suffixed baseline combos in the report until
that split is modeled -- another reason the report is for review, not for
silent promotion.

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
