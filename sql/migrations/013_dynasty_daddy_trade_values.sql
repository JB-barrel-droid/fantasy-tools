-- Migration 013: Dynasty Daddy trade value snapshot table (JEG-674)
-- DRAFT. NOT APPLIED. Jeremy approved "a per-source table and saver" for this source on 2026-10-19 but has NOT
-- confirmed this table name or these columns. Do not apply until he does.
-- CREATE TABLE only (no drops, no alters, no deletes of existing objects).
-- Modeled on public.draftsharks_trade_values (008). RLS on, no policies: service_role only (pipeline writers).
--
-- Dynasty Daddy public player JSON, 0-9999 dynasty-framed scale, 1QB and superflex. COMPARISON AND ID BRIDGE ONLY: its
-- value aggregates FantasyCalc and KTC, so weighting it beside them double counts. Never an input to DDF Value.
-- 0 or missing = NULL, never zero. Vintage = newest most_recent_data_point in the pull.
-- FantasyPros-derived ROS ranks are excluded repo-wide and are not stored. `ids` holds sleeper/mfl/espn/yahoo/ff/ffpc/fantrax ids.
--
-- Rollback (new table, no dependents; indexes drop with it):
--   DROP TABLE IF EXISTS public.dynasty_daddy_trade_values;

CREATE TABLE IF NOT EXISTS public.dynasty_daddy_trade_values (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    player_key INTEGER NOT NULL,
    player_norm TEXT,
    pos TEXT,
    team TEXT,
    name_id TEXT,
    ids JSONB,
    dd_1qb_value NUMERIC,
    dd_1qb_rank INTEGER,
    dd_1qb_pos_rank INTEGER,
    dd_sf_value NUMERIC,
    dd_sf_rank INTEGER,
    dd_sf_pos_rank INTEGER,
    espn_ros INTEGER,
    fanduel_ros INTEGER,
    fantasyguys_ros INTEGER,
    dynasty_daddy_snapshot_date DATE NOT NULL,
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

CREATE UNIQUE INDEX IF NOT EXISTS dynasty_daddy_trade_values_player_date_uidx
    ON public.dynasty_daddy_trade_values (player_key, dynasty_daddy_snapshot_date);
CREATE INDEX IF NOT EXISTS dynasty_daddy_trade_values_snapshot_date_idx
    ON public.dynasty_daddy_trade_values (dynasty_daddy_snapshot_date DESC);

ALTER TABLE public.dynasty_daddy_trade_values ENABLE ROW LEVEL SECURITY;
