-- Migration 010: KeepTradeCut dynasty trade value snapshot table (JEG-669)
-- APPLIED 2026-10-16 to production Supabase on Jeremy's approval ("Approve as drafted: apply the migration"),
-- after he approved "a table and saver for KeepTradeCut, kept out of DDF Value". The table was empty when applied.
-- Re-running this file is a no-op (CREATE ... IF NOT EXISTS).
-- CREATE TABLE only (no drops, no alters, no deletes of existing objects).
-- Modeled on public.draftsharks_trade_values (008). RLS on, no policies: service_role only (pipeline writers).
--
-- Values are KTC's own 1-9999 DYNASTY-framed scale. 0 or missing = NULL, never zero.
-- Vintage = the run date of the pull (the page carries no chart date); `fingerprint` says whether it moved.
-- Typed columns cover 1QB and superflex, each plain and TE-premium (tep). The two further TE-premium
-- tiers (tepp, teppp), positional rank and every other field stay verbatim in ktc_values.
--
-- Rollback (new table, no dependents; indexes drop with it):
--   DROP TABLE IF EXISTS public.keeptradecut_trade_values;

CREATE TABLE IF NOT EXISTS public.keeptradecut_trade_values (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    player_key INTEGER NOT NULL,
    player_norm TEXT,
    pos TEXT,
    team TEXT,
    keeptradecut_id BIGINT,
    -- 1QB league, value on KTC's 1-9999 scale; NULL = unpriced, never zero
    ktc_1qb_value NUMERIC,
    ktc_1qb_rank INTEGER,
    ktc_1qb_tier INTEGER,
    -- superflex league
    ktc_sf_value NUMERIC,
    ktc_sf_rank INTEGER,
    ktc_sf_tier INTEGER,
    -- 1QB with the first TE-premium setting
    ktc_1qb_tep_value NUMERIC,
    ktc_1qb_tep_rank INTEGER,
    ktc_1qb_tep_tier INTEGER,
    -- superflex with the first TE-premium setting
    ktc_sf_tep_value NUMERIC,
    ktc_sf_tep_rank INTEGER,
    ktc_sf_tep_tier INTEGER,
    -- every format verbatim: {format: {value, rank, pos_rank, tier} | null}, formats 1qb, 1qb_tep, 1qb_tepp, 1qb_teppp, sf, sf_tep, ...
    ktc_values JSONB,
    keeptradecut_snapshot_date DATE NOT NULL,
    fingerprint TEXT NOT NULL,
    snapshot_ref TEXT,
    pulled_at TIMESTAMPTZ,
    season INTEGER,
    source_content_date DATE,
    created_at TIMESTAMPTZ DEFAULT now(),
    _run_id TEXT,
    _writer_identity TEXT,
    _written_at TIMESTAMPTZ DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS keeptradecut_trade_values_player_date_uidx
    ON public.keeptradecut_trade_values (player_key, keeptradecut_snapshot_date);
CREATE INDEX IF NOT EXISTS keeptradecut_trade_values_snapshot_date_idx
    ON public.keeptradecut_trade_values (keeptradecut_snapshot_date DESC);

ALTER TABLE public.keeptradecut_trade_values ENABLE ROW LEVEL SECURITY;
