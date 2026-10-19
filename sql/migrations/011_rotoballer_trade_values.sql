-- Migration 011: RotoBaller weekly trade value snapshot table (JEG-671)
-- DRAFT. NOT APPLIED. Jeremy approved "a per-source table and saver" for this source on 2026-10-19 but has NOT
-- confirmed this table name or these columns. Do not apply until he does.
-- CREATE TABLE only (no drops, no alters, no deletes of existing objects).
-- Modeled on public.draftsharks_trade_values (008). RLS on, no policies: service_role only (pipeline writers).
--
-- RotoBaller's weekly 0-100 redraft-style trade value chart (QB/RB/WR/TE only). Kept out of DDF Value until its
-- fidelity pulse is green. 0 or missing = NULL, never zero. Vintage = the article's publish date.
-- Scoring and league size are NOT stated by the source: `scoring` is NULL until a methods review decides.
--
-- Rollback (new table, no dependents; indexes drop with it):
--   DROP TABLE IF EXISTS public.rotoballer_trade_values;

CREATE TABLE IF NOT EXISTS public.rotoballer_trade_values (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    player_key INTEGER NOT NULL,
    player_norm TEXT,
    pos TEXT,
    team TEXT,
    rotoballer_id BIGINT,
    -- 0-100 scale; NULL = unpriced, never zero
    rb_trade_value NUMERIC,
    rb_rank INTEGER,
    article_week INTEGER,
    scoring TEXT,
    source_url TEXT,
    rotoballer_snapshot_date DATE NOT NULL,
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

CREATE UNIQUE INDEX IF NOT EXISTS rotoballer_trade_values_player_date_uidx
    ON public.rotoballer_trade_values (player_key, rotoballer_snapshot_date);
CREATE INDEX IF NOT EXISTS rotoballer_trade_values_snapshot_date_idx
    ON public.rotoballer_trade_values (rotoballer_snapshot_date DESC);

ALTER TABLE public.rotoballer_trade_values ENABLE ROW LEVEL SECURITY;
