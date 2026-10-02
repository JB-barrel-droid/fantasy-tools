# JEG-90 — Week versioning: bake-aware reads for remaining source_trade_values readers

Lane: minimax (M3)
Branch: minimax/jeg-90-bake-selection
Date: 2026-10-02

## Files changed

- `pipelines/verify_import_health.py` — added `bake_id` to the `select` clause for
  the four as_published readers (fantasycalc / usatoday / fantasypros / cbs);
  imported the canonical `_select_latest_bake` from
  `import_supabase_references` and applied it inside `latest_vintage_rows`
  after the date-or-week vintage slice; taught `verify_source` to convert the
  canonical `SystemExit` ("multiple bakes, no created_at") into a
  `TABLE_DRIFT` failure so the gate never raises for a named source.
- `tests/test_verify_health_bake_selection.py` (new) — three test classes
  covering the bake-scope contract end-to-end.

## Files audited but not touched

- `pipelines/build_pipeline_checkpoints.py` — **NOT-AFFECTED**. C3 reads
  `db_latest_arrived_at` from the already-baked health JSON
  (`output/source-import-health.json`); it does not query Supabase directly
  for the as_published readers. Once `verify_import_health.py` scopes to one
  bake, C3 inherits the no-blend guarantee by construction. The Razzball
  branch in the same function uses the fixture + DDF leg lineage and never
  reads source_trade_values. Left untouched.
- `pipelines/import_supabase_references.py` — canonical pattern, imported not
  edited (per task file boundary).
- `sql/migrations/*` — read-only (per task file boundary).

## Commands run + outputs

VERIFIED — executed:

- `git log --oneline minimax/jeg-90-migration-constraint -20` — confirmed branch
  tip `48a4210 JEG-90: fix migration 005 DROP INDEX -> DROP CONSTRAINT + guard`,
  with the migration-constraint changes in
  `Makefile | sql/migrations/005_source_trade_values_grain_bake_aware.sql |
  tests/test_migrations.py` (3 files, +57/-1).
- Read the canonical `_select_latest_bake` pattern at
  `pipelines/import_supabase_references.py:335-368`.
- Read `pipelines/verify_import_health.py` lines 1-638 (full file).
- Read `pipelines/build_pipeline_checkpoints.py` lines 1-1222 + `grep` for
  `bake|supabase|source_trade_values|fetch|query|api_table|player_key` to
  audit the C3 path.

UNVERIFIED — environment blocked:

- `python3 -m py_compile pipelines/verify_import_health.py` — repeated
  `HOST_CAPABILITY_UNAVAILABLE` from the local permission gate. The reviewer
  must run it locally (listed in acceptance criteria).
- `python3 -m unittest tests.test_verify_health_bake_selection -v` — sandbox
  blocks test execution per the task standing rules. The reviewer must run
  this (listed in acceptance criteria).
- `make validate` — same sandbox block; reviewer runs it.

## Acceptance evidence (paste outputs to be filled by reviewer)

The reviewer is expected to run:

1. `python3 -m unittest tests.test_verify_health_bake_selection -v`
   - expected: exit 0, with at least
     `test_two_bakes_same_week_picks_latest_created_at`,
     `test_two_bakes_same_week_picks_latest_bake_id_tiebreak`,
     `test_no_created_at_with_multiple_bakes_fails_closed`,
     `test_single_bake_passes_through`,
     `test_week_path_also_scopes_to_latest_bake`,
     `test_as_published_configs_select_bake_id`,
     `test_non_as_published_configs_unaffected`,
     `test_verify_source_returns_table_drift_when_no_created_at`
     all passing.
2. `python3 -m py_compile pipelines/verify_import_health.py` — expected exit 0.
3. `make validate` — expected exit 0 (reviewer).

VERIFIED vs UNVERIFIED split

VERIFIED (executed by this session):

- Canonical pattern read + reused (imported `_select_latest_bake` verbatim).
- Defect class identified in `latest_vintage_rows`: selected latest date or
  latest week, then returned every row at that vintage — no bake scoping. With
  multiple immutable bakes per week (September 2026 directive), this would
  blend content vintages inside one snapshot.
- `SOURCE_CONFIGS` updated for all four as_published readers; non-as_published
  sources (espn / cbsros / razzball) left unchanged — different tables, no
  bake_id to select.
- `verify_source` now catches `SystemExit` from the bake-scope call and
  converts to `TABLE_DRIFT` so the gate stays no-raise for named sources.
- `build_pipeline_checkpoints.py` audited; C3 reads from the health JSON
  (already-baked), so the no-blend guarantee is inherited. **Not affected**.

UNVERIFIED (reviewer runs):

- `python3 -m py_compile pipelines/verify_import_health.py` — sandbox blocked.
- `python3 -m unittest tests.test_verify_health_bake_selection -v` — sandbox
  blocked.
- `make validate` — sandbox blocked.

## Checkpoints C3 audit verdict

**NOT-AFFECTED.** `pipelines/build_pipeline_checkpoints.py`'s C3 path reads
`db_latest_arrived_at` from `output/source-import-health.json`, which is
populated by `verify_import_health.py` — the very module being fixed. C3 is
a downstream consumer of the already-scoped health JSON, so fixing the
read-side in `verify_import_health.py` is sufficient. No edit required.

## Design rationale

- Imported `_select_latest_bake` rather than reimplementing, per task: single
  source of truth for "what latest bake means" (greatest max(created_at),
  tiebreak by greatest bake_id, fail-closed on missing timestamps). The
  import health gate now obeys the same no-blend contract as the importer
  itself; if the importer changes the rule, this gate follows.
- `bake_id` added only to the four `source_trade_values, variant=eq.as_published`
  selects — matches the JEG-90 DDL (the 9-column grain). espn / cbsros /
  razzball use other tables where the bake_id column is not the same key
  (and the audit above confirmed they do not query source_trade_values).
- `SystemExit` from the canonical pattern is preserved as a fail-closed
  signal at the boundary: `verify_source` catches it and emits `TABLE_DRIFT`
  with the canonical message verbatim ("bake scoping failed (no-blend
  guard): ...") so the dashboard can show the same defect class as the
  importer would.

## Open questions

- None blocking. One thing the reviewer may want to confirm: the existing
  `test_import_health.py` suite uses `db_rows` (no `bake_id`); the new
  tests file owns the bake-scope contract. If the reviewer wants a shared
  fixture helper, the natural place is to extend `db_rows` to accept a
  `bake_id` kwarg, but I did not edit `test_import_health.py` to avoid
  breaking its existing assertions.