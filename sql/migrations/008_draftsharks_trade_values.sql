-- Migration 008: Draft Sharks trade value chart snapshot table (JEG-620)
-- Approved by Jeremy 2026-10-15: CREATE TABLE only (no drops, no alters, no deletes of existing objects).
-- Modeled on public.razzball_projections. RLS on, no policies: service_role only (pipeline writers).
-- Applied through the Supabase MCP on 2026-10-15.
--
-- Rollback (new table, no dependents; indexes drop with it):
--   DROP TABLE IF EXISTS public.draftsharks_trade_values;

CREATE TABLE IF NOT EXISTS public.draftsharks_trade_values (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    player_key INTEGER NOT NULL,
    player_norm TEXT,
    pos TEXT,
    team TEXT,
    draftsharks_id BIGINT,
    -- Draft Sharks' own 0-100 trade value, redraft, no superflex; NULL = unpriced, never zero
    ds_redraft_no_ppr NUMERIC,
    ds_redraft_half_ppr NUMERIC,
    ds_redraft_one_ppr NUMERIC,
    -- every format (redraft/dynasty x scoring x superflex), verbatim: {format: value|null}
    ds_values JSONB,
    market_values JSONB,
    draftsharks_snapshot_date DATE,
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

CREATE UNIQUE INDEX IF NOT EXISTS draftsharks_trade_values_player_date_uidx
    ON public.draftsharks_trade_values (player_key, draftsharks_snapshot_date);
CREATE INDEX IF NOT EXISTS draftsharks_trade_values_snapshot_date_idx
    ON public.draftsharks_trade_values (draftsharks_snapshot_date DESC);

ALTER TABLE public.draftsharks_trade_values ENABLE ROW LEVEL SECURITY;
