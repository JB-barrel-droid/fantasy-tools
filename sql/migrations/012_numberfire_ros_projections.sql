-- Migration 012: NumberFire / FanDuel Research ROS projection snapshot table (JEG-684)
-- DRAFT. NOT APPLIED. Jeremy approved "a per-source table and saver" for this source on 2026-10-19 but has NOT
-- confirmed this table name or these columns. Do not apply until he does.
-- CREATE TABLE only (no drops, no alters, no deletes of existing objects).
-- Modeled on public.fantasysharks_projections (009). RLS on, no policies: service_role only (pipeline writers).
--
-- NumberFire rest-of-season per-stat projections (QB/RB/WR/TE), stored raw so they can be rescored. NULL = unprojected,
-- never zero (the source zero-fills depth rows). Vintage = the run date of the pull (the payload carries no date).
-- fantasy_points is the source's own total under UNSTATED scoring (about half-PPR): audit only, never a scored value.
--
-- Rollback (new table, no dependents; indexes drop with it):
--   DROP TABLE IF EXISTS public.numberfire_ros_projections;

CREATE TABLE IF NOT EXISTS public.numberfire_ros_projections (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    player_key INTEGER NOT NULL,
    player_norm TEXT,
    pos TEXT,
    team TEXT,
    numberfire_id BIGINT,
    pass_cmp NUMERIC,
    pass_att NUMERIC,
    pass_yd NUMERIC,
    pass_td NUMERIC,
    pass_int NUMERIC,
    rush_att NUMERIC,
    rush_yd NUMERIC,
    rush_td NUMERIC,
    rec NUMERIC,
    tgt NUMERIC,
    rec_yd NUMERIC,
    rec_td NUMERIC,
    fantasy_points NUMERIC,
    pos_rank INTEGER,
    overall_rank INTEGER,
    source_url TEXT,
    numberfire_snapshot_date DATE NOT NULL,
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

CREATE UNIQUE INDEX IF NOT EXISTS numberfire_ros_projections_player_date_uidx
    ON public.numberfire_ros_projections (player_key, numberfire_snapshot_date);
CREATE INDEX IF NOT EXISTS numberfire_ros_projections_snapshot_date_idx
    ON public.numberfire_ros_projections (numberfire_snapshot_date DESC);

ALTER TABLE public.numberfire_ros_projections ENABLE ROW LEVEL SECURITY;
