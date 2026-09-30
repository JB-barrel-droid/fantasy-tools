-- ============================================================
-- Migration 001: Repair public.pipeline_write_audit + harden RLS
-- Date: 2026-09-29
-- Status: DESIGNED — DO NOT EXECUTE without Jeremy's review.
-- Execute via the Supabase SQL editor (PostgREST cannot run DDL).
--
-- BACKGROUND
--   The prototype DDL executed 2026-09-29 created a REDUCED version of
--   the audit table (11 columns) that does not match the design spec in
--   docs/SUPABASE_WRITER_AUDIT.md (15 columns). The writer helper
--   (pipelines/lib/writer_audit.py) was fixed in commit 6bda9e4 to be
--   fail-closed: WriterAudit.start() is now MANDATORY, no silent writes.
--   But start() POSTs `code_revision` and fail() PATCHes `error_message`
--   — both columns are MISSING from the live table, so PostgREST returns
--   HTTP 400 and EVERY Supabase write now fails closed. This migration
--   unblocks the pipeline by bringing the live table up to the spec.
--
--   Live table (2026-09-29 probe, 0 rows):
--     run_id, writer_identity, source, operation, reason, table_name,
--     row_count, started_at, completed_at, failed_at, metadata
--   Missing vs spec: id, code_revision, error_message, created_at
--
-- WHAT THIS MIGRATION DOES
--   1. Adds the 4 missing columns (idempotent).
--   2. Backfills id and adds the PRIMARY KEY (spec requires it;
--      PostgREST needs a PK for reliable row addressing).
--   3. Adds UNIQUE(run_id): one audit record per write operation.
--      This also makes the complete()/fail() PATCH targeting safe —
--      without it, ?run_id=eq.X could match multiple rows.
--   4. Adds the operation CHECK constraint from the design spec.
--   5. Aligns NOT NULL with the spec (table is empty; writer always
--      provides these fields).
--   6. Enables RLS with NO public policies (default-deny). Both pipeline
--      paths use service_role (local skill credential is the secret key;
--      GitHub Actions uses SUPABASE_SERVICE_KEY), which bypasses RLS.
--      anon/authenticated get nothing. DO NOT add FORCE RLS — it would
--      break the pipelines.
--   7. Nulls out the misleading _written_at on historical rows in the
--      three data tables (the ADD COLUMN ... DEFAULT now() stamped the
--      migration timestamp onto pre-audit rows; NULL is the honest value).
--
-- WHAT THIS MIGRATION DELIBERATELY DOES NOT DO
--   - It does NOT make _writer_identity / _run_id / _written_at NOT NULL
--     on the data tables. Historical rows predate the audit system and
--     have no provenance; inventing sentinel values would corrupt the
--     "undeclared write" detection (NULL == unaudited is the signal the
--     enforcement tests rely on). All NEW rows are guaranteed audited by
--     the fail-closed writer (commit 6bda9e4).
--   - It does NOT touch RLS on the data tables (out of scope; dashboard
--     reads depend on their current posture).
--   - It does NOT add FORCE ROW LEVEL SECURITY (would break service_role
--     pipeline writes).
--
-- ROLLBACK
--   This migration is additive except for the _written_at NULL backfill
--   (step 7), which is intentionally lossy: the stamped values were
--   wrong (migration time, not write time) and are not recoverable.
--   To roll back the schema changes, drop the added constraints/columns
--   manually; there is no automated down-migration.
-- ============================================================

-- ------------------------------------------------------------
-- 1. Add the missing columns (idempotent)
-- ------------------------------------------------------------
ALTER TABLE public.pipeline_write_audit
    ADD COLUMN IF NOT EXISTS id uuid DEFAULT gen_random_uuid();

ALTER TABLE public.pipeline_write_audit
    ADD COLUMN IF NOT EXISTS code_revision text;

ALTER TABLE public.pipeline_write_audit
    ADD COLUMN IF NOT EXISTS error_message text;

ALTER TABLE public.pipeline_write_audit
    ADD COLUMN IF NOT EXISTS created_at timestamptz DEFAULT now();

-- ------------------------------------------------------------
-- 2. Backfill id, then add the primary key (guarded)
--    The table is currently empty (0 rows on 2026-09-29), so this is
--    a no-op backfill; the guard keeps it safe if rows appear first.
-- ------------------------------------------------------------
UPDATE public.pipeline_write_audit
    SET id = gen_random_uuid()
    WHERE id IS NULL;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'pipeline_write_audit_pkey'
    ) THEN
        ALTER TABLE public.pipeline_write_audit
            ADD CONSTRAINT pipeline_write_audit_pkey PRIMARY KEY (id);
    END IF;
END $$;

-- ------------------------------------------------------------
-- 3. One audit record per run: UNIQUE(run_id)
--    Without this, complete()/fail() PATCH ?run_id=eq.X could hit
--    multiple rows. The writer generates a fresh UUID per operation.
-- ------------------------------------------------------------
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'pipeline_write_audit_run_id_key'
    ) THEN
        ALTER TABLE public.pipeline_write_audit
            ADD CONSTRAINT pipeline_write_audit_run_id_key UNIQUE (run_id);
    END IF;
END $$;

-- ------------------------------------------------------------
-- 4. Operation CHECK constraint (from the design spec)
-- ------------------------------------------------------------
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'pipeline_write_audit_operation_check'
    ) THEN
        ALTER TABLE public.pipeline_write_audit
            ADD CONSTRAINT pipeline_write_audit_operation_check
            CHECK (operation IN ('insert', 'upsert', 'delete', 'update'));
    END IF;
END $$;

-- ------------------------------------------------------------
-- 5. NOT NULL alignment with the design spec.
--    The fail-closed writer always provides these fields; the table is
--    empty, so this cannot fail on existing data. If it ever does fail,
--    that itself is a signal of corrupt audit data — investigate, do
--    not weaken the constraint.
-- ------------------------------------------------------------
ALTER TABLE public.pipeline_write_audit
    ALTER COLUMN run_id SET NOT NULL,
    ALTER COLUMN writer_identity SET NOT NULL,
    ALTER COLUMN source SET NOT NULL,
    ALTER COLUMN operation SET NOT NULL,
    ALTER COLUMN table_name SET NOT NULL,
    ALTER COLUMN started_at SET NOT NULL,
    ALTER COLUMN created_at SET NOT NULL;

-- ------------------------------------------------------------
-- 6. Indexes from the design spec (IF NOT EXISTS; the UNIQUE on
--    run_id already covers run_id lookups, so no separate index).
-- ------------------------------------------------------------
CREATE INDEX IF NOT EXISTS pipeline_write_audit_writer_idx
    ON public.pipeline_write_audit (writer_identity, started_at DESC);

CREATE INDEX IF NOT EXISTS pipeline_write_audit_table_idx
    ON public.pipeline_write_audit (table_name, started_at DESC);

CREATE INDEX IF NOT EXISTS pipeline_write_audit_source_idx
    ON public.pipeline_write_audit (source, started_at DESC);

-- ------------------------------------------------------------
-- 7. Enable RLS — default-deny for anon/authenticated.
--    Pipeline writers use service_role (local skill credential is the
--    secret key; GitHub Actions uses SUPABASE_SERVICE_KEY), which
--    bypasses RLS. No policies are created deliberately: the audit
--    trail must not be readable or writable by public keys.
--    DO NOT use FORCE ROW LEVEL SECURITY here.
-- ------------------------------------------------------------
ALTER TABLE public.pipeline_write_audit ENABLE ROW LEVEL SECURITY;

COMMENT ON TABLE public.pipeline_write_audit IS
    'Audit trail for all pipeline Supabase writes. RLS enabled with no public policies: only service_role (pipeline writers) may read/write. See docs/SUPABASE_WRITER_AUDIT.md.';

-- ------------------------------------------------------------
-- 8. Historical-row honesty backfill on the data tables.
--    ADD COLUMN ... DEFAULT now() stamped the DDL execution time onto
--    every pre-audit row as _written_at. That timestamp is the migration
--    time, not the write time — it is wrong. Rows with no writer
--    identity get NULL (unknown), which is also the "undeclared write"
--    signal the enforcement tests rely on. Idempotent: re-running
--    updates zero rows.
-- ------------------------------------------------------------
UPDATE public.source_trade_values
    SET _written_at = NULL
    WHERE _writer_identity IS NULL AND _written_at IS NOT NULL;

UPDATE public.cbs_trade_values
    SET _written_at = NULL
    WHERE _writer_identity IS NULL AND _written_at IS NOT NULL;

UPDATE public.espn_season_projections
    SET _written_at = NULL
    WHERE _writer_identity IS NULL AND _written_at IS NOT NULL;

-- ============================================================
-- VERIFICATION (run after executing, in the same SQL editor)
-- ============================================================
-- -- 1. Schema matches the spec (expect 15 rows):
-- SELECT column_name, data_type, is_nullable
--   FROM information_schema.columns
--  WHERE table_schema = 'public' AND table_name = 'pipeline_write_audit'
--  ORDER BY ordinal_position;
--
-- -- 2. Constraints present (expect pkey, run_id_key, operation_check):
-- SELECT conname, pg_get_constraintdef(oid)
--   FROM pg_constraint
--  WHERE conrelid = 'public.pipeline_write_audit'::regclass;
--
-- -- 3. RLS enabled (expect t, no policies):
-- SELECT relname, relrowsecurity, relforcerowsecurity
--   FROM pg_class WHERE relname = 'pipeline_write_audit';
-- SELECT * FROM pg_policies WHERE tablename = 'pipeline_write_audit';
--
-- -- 4. No misleading _written_at on unaudited rows (expect 0):
-- SELECT count(*) FROM public.source_trade_values
--  WHERE _writer_identity IS NULL AND _written_at IS NOT NULL;
-- SELECT count(*) FROM public.cbs_trade_values
--  WHERE _writer_identity IS NULL AND _written_at IS NOT NULL;
-- SELECT count(*) FROM public.espn_season_projections
--  WHERE _writer_identity IS NULL AND _written_at IS NOT NULL;
--
-- -- 5. End-to-end (from a shell with the service credential):
-- -- python3 pipelines/save_usatoday_references.py --dry-run  # if supported
-- -- then: SELECT run_id, writer_identity, operation, row_count,
-- --              started_at, completed_at FROM public.pipeline_write_audit
-- --       ORDER BY started_at DESC LIMIT 1;
-- ============================================================
