-- Migration 009: Fantasy Sharks rest-of-year projections snapshot table (JEG-621)
-- Approved by Jeremy 2026-10-15: CREATE TABLE only (no drops, no alters, no deletes of existing objects).
-- Modeled on public.razzball_projections. RLS on, no policies: service_role only (pipeline writers).
-- Applied through the Supabase MCP on 2026-10-15.
--
-- Fantasy Sharks publishes rest-of-year fantasy point TOTALS and no games column
-- (GAP-FANTASYSHARKS-ROS-TOTAL), so the table stores totals, not per-game values.
--
-- Rollback (new table, no dependents; indexes drop with it):
--   DROP TABLE IF EXISTS public.fantasysharks_projections;

CREATE TABLE IF NOT EXISTS public.fantasysharks_projections (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    player_key INTEGER NOT NULL,
    player_norm TEXT,
    pos TEXT,
    team TEXT,
    fantasysharks_id BIGINT,
    -- rest-of-year fantasy point totals; NULL = unprojected, never zero
    ros_total_non_ppr NUMERIC,
    ros_total_half_ppr NUMERIC,
    ros_total_ppr NUMERIC,
    fantasysharks_snapshot_date DATE,
    pulled_at TIMESTAMPTZ,
    scoring TEXT,
    season INTEGER,
    week INTEGER,
    source_content_date DATE,
    created_at TIMESTAMPTZ DEFAULT now(),
    _run_id TEXT,
    _writer_identity TEXT,
    _written_at TIMESTAMPTZ DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS fantasysharks_projections_player_date_uidx
    ON public.fantasysharks_projections (player_key, fantasysharks_snapshot_date);
CREATE INDEX IF NOT EXISTS fantasysharks_projections_snapshot_date_idx
    ON public.fantasysharks_projections (fantasysharks_snapshot_date DESC);

ALTER TABLE public.fantasysharks_projections ENABLE ROW LEVEL SECURITY;
