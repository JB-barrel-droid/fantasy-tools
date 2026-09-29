-- ============================================================
-- Add standard audit columns to pipeline-written tables
--
-- These columns track data provenance for every row:
--   * _writer_identity: Which script/module wrote the row
--   * _run_id: Unique ID of the write operation (links to pipeline_write_audit)
--   * _written_at: When the row was written
--
-- The underscore prefix distinguishes audit columns from domain columns.
--
-- EXECUTE via the Supabase Management API database/query endpoint
-- (same backend as the SQL editor; PostgREST cannot run DDL).
-- ============================================================

-- CBS trade values
ALTER TABLE IF EXISTS public.cbs_trade_values
    ADD COLUMN IF NOT EXISTS _writer_identity text,
    ADD COLUMN IF NOT EXISTS _run_id text,
    ADD COLUMN IF NOT EXISTS _written_at timestamptz DEFAULT now();

-- ESPN season projections
ALTER TABLE IF EXISTS public.espn_season_projections
    ADD COLUMN IF NOT EXISTS _writer_identity text,
    ADD COLUMN IF NOT EXISTS _run_id text,
    ADD COLUMN IF NOT EXISTS _written_at timestamptz DEFAULT now();

-- Source trade values (generic)
ALTER TABLE IF EXISTS public.source_trade_values
    ADD COLUMN IF NOT EXISTS _writer_identity text,
    ADD COLUMN IF NOT EXISTS _run_id text,
    ADD COLUMN IF NOT EXISTS _written_at timestamptz DEFAULT now();

-- Players (if written by pipeline)
ALTER TABLE IF EXISTS public.players
    ADD COLUMN IF NOT EXISTS _writer_identity text,
    ADD COLUMN IF NOT EXISTS _run_id text,
    ADD COLUMN IF NOT EXISTS _written_at timestamptz DEFAULT now();

-- Comments for documentation
COMMENT ON COLUMN public.cbs_trade_values._writer_identity IS
    'Pipeline script that wrote this row (e.g., save_espn_cbs_references.py)';
COMMENT ON COLUMN public.cbs_trade_values._run_id IS
    'Links to pipeline_write_audit.run_id for this write operation';
COMMENT ON COLUMN public.cbs_trade_values._written_at IS
    'Timestamp when this row was written by the pipeline';
