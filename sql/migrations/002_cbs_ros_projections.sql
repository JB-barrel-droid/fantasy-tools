-- Migration 002: CBS Rest-of-Season projections table
-- Created 2026-10-01: wires cbsros through Supabase (was file-only).
-- Run in Supabase SQL editor. Modeled on public.espn_season_projections.

CREATE TABLE IF NOT EXISTS public.cbs_ros_projections (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    player_key INTEGER NOT NULL,
    player_norm TEXT,
    ros_standard NUMERIC,
    ros_half_ppr NUMERIC,
    ros_ppr NUMERIC,
    per_game_standard NUMERIC,
    per_game_half_ppr NUMERIC,
    per_game_ppr NUMERIC,
    gp NUMERIC,
    receptions NUMERIC,
    raw_stats JSONB,
    cbs_snapshot_date DATE,
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

-- One row per player per snapshot date (upsert key)
CREATE UNIQUE INDEX IF NOT EXISTS cbs_ros_projections_player_date_uidx
    ON public.cbs_ros_projections (player_key, cbs_snapshot_date);

-- Lookup by snapshot date (import selects latest)
CREATE INDEX IF NOT EXISTS cbs_ros_projections_snapshot_date_idx
    ON public.cbs_ros_projections (cbs_snapshot_date DESC);
