# Pipeline Rules

Standing rules for the fantasy-tools pipeline. These live in the repo so the
process memory is not held by any LLM tool or chat thread. GitHub is the store
of record: if a rule is not written here, it does not exist.

See also: `docs/modular-pipeline.md` for the four-stage flow these rules guard.

## 1. Naming authority

- The Supabase `players` table is the naming authority: one table, one numeric
  `player_key`, one `full_name`.
- `data/fixtures/current/players.json` is a pinned export of that table. It is
  never hand-edited for identity fields.
- The pin is recorded in `data/fixtures/current/players.naming-manifest.json`:
  exported_at, source label, row count, and a SHA-256 hash of the identity
  projection (player_key, full_name, pos, team).
- Refresh contract: every rebuild of players.json from the naming table must
  re-pin the manifest atomically with the same exported_at, labeled
  `supabase:players` (or the exact export job id):

  ```bash
  python3 pipelines/pin_naming_manifest.py --source-label "supabase:players"
  ```

- `make validate` runs `pipelines/check_naming_drift.py` first. A players.json
  whose identity projection diverges from the manifest fails closed and blocks
  the build. No exceptions, no silent re-pins.
- Identity matching anywhere in the pipeline resolves through the fixture's
  canonical key space (never a recomputed slug, never a source spelling).
  Legacy slug quirks are preserved byte-for-byte by reading the fixture's own
  `player_keys` map, not by re-deriving names.

## 2. Identity matching is fail-closed

- Match by normalized name; use team/pos only to resolve duplicate names.
- Unmatched, ambiguous, or position-conflicting identities go to `review_rows`.
- Nothing is guessed. A guessed identity is a data-corruption bug, not a
  convenience.
- Conflicting duplicate values for the same `player_key` go to review; they
  are never silently merged (first-wins, last-wins, and averaging are all
  silent merges).

## 3. Candidate artifacts stay in output/

- The candidate bridge (`build_comparison_source_section.py`,
  `merge_comparison_candidate.py`) writes ONLY under `output/`.
- The reference-compute reindex stage (`reindex_comparison_section.py`,
  `isotonic.py`) also writes ONLY under `output/` (`output/comparison-reference/`);
  its `--out` refuses any path inside `data/`.
- The live fixture `data/fixtures/current/comparison-sources-data.json` is
  never replaced by candidate output.
- Promotion checklist (all required before a candidate touches the fixture):
  1. candidate section builder is tested,
  2. merge script is tested,
  3. the candidate artifact in `output/` is inspected,
  4. the current known-good fixture can be reproduced or compared
     (`comparison-candidate-report.json` covers the comparison),
  5. null-vs-zero behavior is protected (rule 4),
  6. `review_rows` are triaged, not ignored.
- The merge script refuses any `--output`/`--report` path inside `data/`.
- Candidate sections carry `reindex_status: "pending"`: fixed-pie reindexing is
  reference-compute math and must be reviewed before promotion. Native values
  are carried as scraped; they are never presented as finished chart values.
- Reindexed sections (`reindex_status: "complete"`) carry `reindexed`,
  `native`, `fit`, `n`, and per-position `index_total` mirroring the fixture
  shape. The reindex anchor is the fixture's ESPN leg -- NOT the retired
  Monday rail the existing fixture sections were baked against. Promotion
  review must surface that anchor change; legacy equality is not asserted.
- The isotonic fit is strictly per position (QB/RB/WR/TE) with at least 10
  anchor-matched pairs; fewer fails closed. Cross-position pooling is never
  allowed to happen silently.
- Promotion requires a `ready` verdict from `review_comparison_candidate.py`.
  The review never promotes and never writes under `data/`; the promotion
  itself is a separate, explicitly approved step. `review_rows` must be
  triaged (via `--triage`), not ignored.
- Promotion is the ONLY stage that may write under `data/`, and only via
  `promote_comparison_section.py` with `--approve "<name> <YYYY-MM-DD>
  <reason>"`. It refuses on: non-`ready` verdict, reindexed bytes changed
  since the review, fixture natives changed since the review, or a candidate
  slug outside the fixture's `player_keys`. Natives carry over byte-identical
  (vintage untouched); only the reindex anchor changes, recorded on the
  section. The replaced section is kept in the promotion record as a rollback
  record.

## 4. Null, never zero

- A missing source value stays missing (null / absent key). It is never
  converted to zero.
- Zero is a real number: a source that publishes 0 means 0. The pipeline must
  never invent a 0 where the source had nothing.
- The merge step verifies this: every candidate native value must trace to a
  numeric source-reference row (`zero_fill_check` in the candidate report).

## 5. Freshness is content vintage, never pull time

- A source backs a claim only if its content is current. Re-downloading the
  same numbers resets nothing.
- Week-designated sources must match the current NFL week ("current" feeds must
  be freshly pulled with genuinely new content).
- Stale sources are priors-only context, labeled as such, never the current read.
- Every source section records `fetched_at` and, where applicable,
  `week_designated`. The candidate report surfaces both.

## 6. Public copy rules

- Values are described as "value above waivers". Never use the term VORP in
  anything user-facing.
- The market side is always called "Vegas", never "the market".
- ECR is never called by the FantasyPros brand name in public copy or in
  conversation. Internally the ECR feed still supplies rank and expert point
  projections.

## 7. Scraped references are saved in Supabase; the repo imports from Supabase

- Every scraped reference backing the dashboard is piped via Supabase and
  saved, stamped with content vintage (when the source last changed its
  numbers, never pull time).
- The repo's import stage (`make supabase-import`) reads from Supabase into
  versioned snapshots under `data/raw/`; it never ingests ad-hoc files except
  the documented `--from-file` gap path (ESPN/CBS until their Supabase tables
  exist), which is stamped identically and flagged `save_gap` in the manifest.
- Dashboard sources only: espn, usatoday, fantasycalc, fantasypros, cbs. ECR,
  Vegas/prediction-markets, and Razzball are never imported as comparison
  sources.

## 8. Import health gates fixture updates

- `make import-health NFL_WEEK=<n>` verifies every active source's snapshot:
  bytes match the manifest, Supabase counts/vintage agree, week-designated
  charts match the NFL week.
- Missing, stale, or failed imports fail closed: no match, reference, section,
  reindex, review, or promote step runs on a red gate. The gate exits non-zero
  with a loud signal.
- Per-source health is written to `output/source-import-health.json`
  (schema: `docs/import-health-schema.md`); it is the pull watchdog's input.
  The watchdog reads; it never writes this file.

## 9. Adjusted curves render live; the fixture carries raw sections only

- No `*_adjusted` section is baked into the fixture going forward. Adjusted
  curves are derived live in the browser from fixture raw refs plus the
  versioned adjustment-inputs asset (`trade-value-adjustment-inputs-v1`).
  (The three legacy baked `*_adjusted` sections from the old workspace fit
  predate this rule; their removal is Jeremy's transition decision —
  see `docs/fixture-transition-proposal.md`.)
- Adjustment cells are fit against the DDF two-tier leg (stage 2); the asset
  is versioned and the fit recipe is documented in-asset.
- Bench share is a UI parameter (default 0.15, per position; bounded slider
  with feasibility-derived bounds, recommended tick at 0.15). Calibration is
  parametric in (league config × bench share) and re-solves live; fail closed
  per position when starter rate ≤ bench rate.

## Operating notes

- LLMs (Muse, ChatGPT, Codex, or any other) may collect raw source data and
  may improve this repo's code, but they are not runtime infrastructure: no
  LLM is the only way to refresh data, the only way to deploy, or the holder
  of process memory. Raw scraper output enters through `make source-import`
  and is treated as untrusted input until it passes matching, review, and
  validation.
- Move one source at a time (see `docs/modular-pipeline.md`, "Next Migration
  Rule"). Each source gets: raw snapshot format, parser/normalizer,
  fail-closed identity matching, reference artifact update, and a test proving
  nulls, zeros, and player keys behave correctly.
