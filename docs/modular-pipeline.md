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

Supabase import stage (dashboard sources only):

```bash
make supabase-import SOURCE=fantasycalc
make supabase-import SOURCE=espn FROM_FILE=/path/to/espn_projections.csv
```

Scraped references are saved to Supabase first (workspace scrapes), then the
repo imports from Supabase — never from ad-hoc files. The importer writes the
same `trade-value-source-snapshot-v1` JSON under
`data/raw/sources/<source>/<content-vintage>/` with a `snapshot-manifest.json`
sidecar (source, Supabase table, content vintage and how it was derived, pull
time labeled as such, row counts, sha256 of the snapshot bytes). Content
vintage is when the SOURCE last changed its numbers, never pull time.
Dashboard sources only: espn, usatoday, fantasycalc, fantasypros, cbs — ECR,
Vegas/prediction-markets, and Razzball are never imported here. The full
table mapping lives in `docs/supabase-source-mapping.md`.

ESPN and CBS have no Supabase table yet (stage1b gap): they import via
`FROM_FILE` from the workspace saved references, stamped identically, with
`save_gap: "no-supabase-table-stage1b"` in the manifest. DDL for the two
missing tables is written for review at
`pipelines/sql/create_espn_cbs_reference_tables.sql` (not executed).

Import health gate:

```bash
make import-health NFL_WEEK=3
```

Verifies every active source's snapshot landed with fresh content vintage
(bytes match the manifest, Supabase row counts/vintage agree, week-designated
charts match the NFL week). A missing, stale, or failed import fails closed:
non-zero exit, loud signal, and NO match/reference/section/reindex/review/
promote step may run on a red gate. Per-source health (last successful import,
content vintage, row counts, failure reason) is written to
`output/source-import-health.json` (schema: `docs/import-health-schema.md`)
for the pull watchdog.

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

The source-reference stage emits one artifact per (scoring, teams, qb) group
found in the matched rows -- a source that publishes the same player under
several scorings (e.g. USA Today's standard/half_ppr/ppr rows) gets one
reference file per scoring, each with its own `combo_key` and a combo-suffixed
output path (`<source>-<combo>-reference.json`) so files never collide. Rows
are never compared across scorings: grouping by player_key alone used to turn
one player_key's three scoring rows into spurious "duplicate_player_key"
review groups. Genuine duplicates (same player_key AND same scoring/teams/qb
with conflicting values) still become duplicate review rows. Rows whose
scoring cannot be resolved (neither row-level nor match defaults) are never
placed and never guessed into a group -- they become `missing_scoring` review
rows, the same fail-closed convention as the match stage's no_match/ambiguous
rows.

The source-reference artifact has one row per canonical `player_key` per
group and keeps source values separate from dashboard display math. Duplicate
player-key rows with conflicting values are sent to review instead of being
merged.

Build a candidate comparison source section from the reference artifact(s):

```bash
make comparison-section REFERENCE_FILE=output/source-references/fantasycalc/2026-09-21/fantasycalc-ppr-12-reference.json
# ...or pass every per-group artifact for a multi-scoring source:
make comparison-section REFERENCE_FILES="output/source-references/usatoday/2026-09-21/usatoday-standard-12-reference.json output/source-references/usatoday/2026-09-21/usatoday-half-ppr-12-reference.json output/source-references/usatoday/2026-09-21/usatoday-ppr-12-reference.json"
```

The section builder accepts one or more reference inputs and unions them into
a single candidate (inputs must agree on source and fetched_at -- mixing
sources or vintages fails closed); identical inherited review rows are
deduped. A single input behaves exactly as before.

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

### Comparison source pipeline (candidate -> reference compute)

A candidate source section (schema `trade-value-source-reference-v1`, built by
`make comparison-section`) carries only native published values. The reference
compute stage translates it onto the chart's canonical scale:

```bash
make comparison-reindex CANDIDATE_FILE=output/comparison-candidates/.../section.json
```

`pipelines/reindex_comparison_section.py` runs two steps per (combo, position):

1. **Isotonic reindex.** Per-position non-decreasing (PAVA) fit of the source's
   native values onto the anchor scale, preserving rank order and
   within-position relative shape. The anchor is the fixture's ESPN leg for
   the same combo -- the repo-owned equivalent of the retired Monday rail.
   Fewer than 10 anchor-matched pairs per position fails closed (no pooled
   cross-position fit, ever).
2. **Fixed-pie indexing.** Each combo's total over its OWN priced set is
   compared to the anchor's total over that SAME set:
   `factor = anchor_total(priced) / reindexed_total(priced)`, recorded as
   `index_total {target_total, pre_total, factor, n_priced}` per position.
   Per-player comparisons are pure allocation disagreements.

Output schema `trade-value-comparison-section-reindexed-v1` mirrors the
fixture's combo shape (`reindexed`, `native`, `fit`, `n`, `index_total`) so the
promotion path is a mechanical slice. Written under
`output/comparison-reference/` only -- never under `data/`.

Notes:

- Genuine source zeros stay zero; nulls stay absent. K/DST are not indexed.
- Identity resolves slug -> numeric `player_key` -> position from
  `players.json`; never by name normalization.
- Existing fixture sections were baked against the retired Monday rail; repo
  candidates anchor to the ESPN leg. The promotion review must surface that
  anchor change explicitly -- legacy equality is NOT asserted.

### Promotion review

A reindexed section is reviewed before any human promotion decision:

```bash
make comparison-review REINDEXED_FILE=output/comparison-reference/...-reindexed.json
```

`pipelines/review_comparison_candidate.py` compares the candidate against the
fixture's existing section for the same source and writes a
`trade-value-comparison-review-v1` report under `output/comparison-review/`
with verdict `ready` or `hold`:

- `combos_match`, `native_drift` (the source moved since the fixture was baked?),
  `coverage` (lost players?), `zero_preservation`, `pie_factors_sane`
- `review_rows_triaged`: every review row must be triaged via `--triage`
  (a JSON slug -> note map) before the verdict can be `ready`
- `anchor_disclosure`: always informational -- the anchor change (ESPN leg vs
  Monday rail) is measured as per-position divergence, never asserted equal

The script never promotes anything and never writes under `data/`. `ready`
means a human MAY promote; the promotion itself is a separate, explicitly
approved step.

### Promotion

The only stage allowed to write under `data/`:

```bash
make comparison-promote \
  REVIEW_FILE=output/comparison-review/usatoday-2026-09-21-review.json \
  APPROVE="Jeremy 2026-09-21 re-anchor usatoday to the ESPN leg"
```

`pipelines/promote_comparison_section.py` refuses unless ALL hold:

1. the review verdict is `ready`
2. the reindexed section bytes still match the review's `reindexed_sha256`
3. the fixture's current natives still match the review's
   `fixture_native_sha256` (nothing moved under the review)
4. every candidate slug already exists in the fixture's `player_keys`
5. `--approve "<name> <YYYY-MM-DD> <reason>"` is given (recorded verbatim)

Promotion replaces the source's `reindexed` values, `fit`, and `index_total`
with the candidate's, carries natives over byte-identical (vintage
`fetched_at` untouched -- only the anchor changes), records
`reindex_anchor: espn_leg` + `promoted_at` on the section, preserves the
fixture's compact serialization, and writes a promotion record (with the
replaced section as a rollback record) under `output/comparison-promotions/`.

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

Adjusted curves render live in the browser. The fixture carries RAW source
sections only; each `*_adjusted` curve is derived live from the fixture's raw
refs plus the versioned adjustment-inputs asset (`data/adjustment-inputs/` →
`app/trade-value-chart/assets/adjustment-inputs.json`, schema
`trade-value-adjustment-inputs-v1`). Stage 1 ships the architecture with an
empty inputs asset (`stage1-empty`, all sources `pending-stage2`) and falls
back exactly to current behavior; stage 2 fills per-source/per-position/
per-tier fit cells (fit against the DDF two-tier leg).

Bench share is a UI parameter (bounded slider, default 0.15, per position).
Moving it re-runs the per-position two-tier calibration live in the browser,
per league-size config; the slider bounds are the feasible interval where
every position's calibration yields starter rate > bench rate (recomputed on
config change), with a recommended tick at 0.15. Fail-closed per position:
starter rate ≤ bench rate withholds that position's derived values with a
visible flag — never zero-filled, never guessed.

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
