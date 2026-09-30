# Supabase Writer-Audit DDL — Findings & Migration Plan (2026-09-29)

## TL;DR

The Python side of the writer-audit system is already fixed (commit `6bda9e4`:
PATCH-not-POST, fail-closed mandatory audit, 22 tests passing). The **database
side is broken and is now blocking all Supabase writes**: the live
`pipeline_write_audit` table is missing 4 columns the code requires, so every
`WriterAudit.start()` gets HTTP 400 and every write fails closed.

Migration `sql/migrations/001_pipeline_write_audit_repair.sql` is designed,
reviewable, and **not executed**. Jeremy must review before it runs in the
Supabase SQL editor.

## Findings

### 1. Live `pipeline_write_audit` schema ≠ design spec (BLOCKING)

Probed live via PostgREST 2026-09-29 (~23:50 UTC). Table exists, **0 rows**.

| Live (11 cols) | Spec `docs/SUPABASE_WRITER_AUDIT.md` (15 cols) | Missing |
|---|---|---|
| run_id, writer_identity, source, operation, reason, table_name, row_count, started_at, completed_at, failed_at, metadata | + id (PK), code_revision, error_message, created_at | **id, code_revision, error_message, created_at** |

Impact:
- `WriterAudit.start()` POSTs `code_revision` → **HTTP 400** (verified: column probe returns 42703).
- `WriterAudit.fail()` PATCHes `error_message` → **HTTP 400**.
- Since commit `6bda9e4` made audit mandatory/fail-closed, **no Supabase write can
  succeed until the schema is repaired**. The 6-hour GitHub Actions rebuild will
  fail at the import step until this runs.

### 2. POST-vs-PATCH bug — already fixed in code

`pipelines/lib/writer_audit.py` (fixed 2026-09-29 23:44 UTC, commit `6bda9e4`):
`start()` → POST (correct), `complete()`/`fail()` → PATCH with dict body
(correct). Pinned by `tests/test_writer_audit_lifecycle.py` (6 tests) and the
updated `tests/test_writer_audit_enforcement.py` (16 tests) — all 22 pass.

(Note: an earlier read of these files returned stale cached content showing the
old POST code — ground truth was verified via `grep`/`inspect` on disk. The
AGENTS.md stale-.pyc lesson applies to file reads too; verify with grep.)

### 3. RLS not enabled on `pipeline_write_audit`

No RLS → any key with table grants could read/write the audit trail. Both
pipeline paths use service_role (local skill credential verified as the secret
key via the `/rest/v1/` OpenAPI probe; GitHub Actions uses
`SUPABASE_SERVICE_KEY`), which bypasses RLS — so enabling RLS with zero public
policies is safe and is the correct posture. No anon/authenticated access is
needed (nothing reads the audit table except service_role tooling).

### 4. Historical rows: NULL identity + misleading `_written_at`

Sampled `source_trade_values`, `cbs_trade_values`, `espn_season_projections`:
`_writer_identity`/`_run_id` are NULL (audit never worked — every `start()`
400'd and the old code silently proceeded), and `_written_at` =
`2026-09-29T23:03:44` — the DDL execution time from `DEFAULT now()`, **not**
the write time. The migration NULLs `_written_at` where `_writer_identity IS
NULL` (honest "unknown"; also the undeclared-write detection signal).

### 5. Writer coverage is complete

Only two modules write to Supabase (`save_espn_cbs_references.py`,
`save_usatoday_references.py`); both use WriterAudit mandatorily since
`6bda9e4`. `import_supabase_references.py` is read-only. The earlier "silent
fallback" is gone — failures now raise.

### 6. `players` table has no audit columns

`add_audit_columns.sql` targeted it with `IF EXISTS`, but the columns are
absent live (table likely absent or skipped). No pipeline writes to `players`
per the coverage grep — no action needed.

## Migration plan (`sql/migrations/001_pipeline_write_audit_repair.sql`)

Designed only — **do not execute without Jeremy's review**. Run in the Supabase
SQL editor (PostgREST cannot run DDL). All steps idempotent/guarded.

1. `ADD COLUMN IF NOT EXISTS`: `id uuid DEFAULT gen_random_uuid()`,
   `code_revision text`, `error_message text`, `created_at timestamptz DEFAULT now()`.
2. Backfill `id`, add `PRIMARY KEY` (guarded by `pg_constraint` check).
3. `UNIQUE(run_id)` — one audit record per operation; makes the
   `?run_id=eq.X` PATCH targeting safe.
4. `CHECK (operation IN (...))` from the spec.
5. `SET NOT NULL` on run_id, writer_identity, source, operation, table_name,
   started_at, created_at (spec alignment; table is empty).
6. Spec indexes (writer/table/source); `ENABLE ROW LEVEL SECURITY` with **no
   policies** (default-deny; service_role bypasses). Explicitly no `FORCE RLS`.
7. `UPDATE ... SET _written_at = NULL WHERE _writer_identity IS NULL` on the
   three data tables.
8. Verification queries included as comments (schema, constraints, RLS,
   backfill counts, end-to-end audit row check).

Deliberately out of scope: NOT NULL on data-table audit columns (historical
rows have no provenance — NULL is honest and is the undeclared-write signal);
RLS on data tables (dashboard reads depend on current posture); `FORCE RLS`
(would break service_role pipeline writes).

## After Jeremy approves and runs it

1. Re-run the 22 audit tests (already green; unaffected by DDL).
2. Trigger one real write (e.g. the USA Today saver or the next GitHub Actions
   run) and confirm a complete audit row appears:
   `SELECT run_id, writer_identity, operation, row_count, started_at, completed_at
    FROM public.pipeline_write_audit ORDER BY started_at DESC LIMIT 1;`
3. Confirm `complete()`/`fail()` PATCH the same row (no duplicate run_ids).
