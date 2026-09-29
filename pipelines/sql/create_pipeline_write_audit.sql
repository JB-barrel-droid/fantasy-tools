-- ============================================================
-- Pipeline Write Audit Table
--
-- Every Supabase write operation by a pipeline must create an audit
-- record in this table. This provides:
--   * Data provenance (who wrote what, when, why)
--   * Debugging capability (trace write failures)
--   * Compliance audit trail
--   * Detection of unauthorized writes
--
-- Design notes:
--   * Append-only: records are never deleted. completed_at/failed_at
--     are set once when the operation finishes.
--   * run_id is a UUID string, unique per write operation (not per row).
--   * For batch writes, one audit record covers the entire batch.
--   * The metadata JSONB field stores operation-specific context
--     (vintage dates, filters applied, source URLs, etc.).
--
-- EXECUTE via the Supabase Management API database/query endpoint
-- (same backend as the SQL editor; PostgREST cannot run DDL).
-- ============================================================

CREATE TABLE IF NOT EXISTS public.pipeline_write_audit (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id text NOT NULL,
    writer_identity text NOT NULL,
    code_revision text,
    source text NOT NULL,
    operation text NOT NULL,
    reason text,
    table_name text NOT NULL,
    row_count integer,
    started_at timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz,
    failed_at timestamptz,
    error_message text,
    metadata jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT pipeline_write_audit_operation_check
        CHECK (operation IN ('insert', 'upsert', 'delete', 'update'))
);

-- Index for looking up a specific run
CREATE INDEX IF NOT EXISTS pipeline_write_audit_run_id_idx
    ON public.pipeline_write_audit (run_id);

-- Index for writer history (most recent first)
CREATE INDEX IF NOT EXISTS pipeline_write_audit_writer_idx
    ON public.pipeline_write_audit (writer_identity, started_at DESC);

-- Index for table history (most recent first)
CREATE INDEX IF NOT EXISTS pipeline_write_audit_table_idx
    ON public.pipeline_write_audit (table_name, started_at DESC);

-- Index for source history
CREATE INDEX IF NOT EXISTS pipeline_write_audit_source_idx
    ON public.pipeline_write_audit (source, started_at DESC);

-- Comment the table for documentation
COMMENT ON TABLE public.pipeline_write_audit IS
    'Audit trail for all pipeline Supabase writes. Every write operation must create a record here via pipelines/lib/writer_audit.py.';
