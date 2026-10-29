-- Migration 015: rest-of-season rankings table (JEG-1198 option C)
-- DRAFT. NOT APPLIED. Jeremy picked option C on 2026-10-29 ("start with 4-5 sources, piped through
-- supabase") but has NOT approved this table. Do not apply until his own message names this migration.
-- CREATE TABLE only (no drops, no alters, no deletes of existing objects).
-- RLS on, no policies: service_role only (pipeline writers), like 008-013.
--
-- One row per (source, analyst, scoring, position, player, source vintage). ROS only: Jeremy, 2026-10-29,
-- "do not blend weekly data with ROS data, ever", so no weekly ranking goes in this table.
-- Rankings only: expert consensus and analyst ROS ranks, kept for research and review. NEVER an input to DDF Value or DDF Projections: the
-- trade-value importer (pipelines/import_supabase_references.py) does not read this table and keeps its
-- ECR hard exclusion (tests/test_ros_rankings.py).
--
-- source        fantasypros_ros_ecr (consensus, one list per scoring) | fantasypros_expert_ros (each
--               expert's own list; the consensus averages a subset of these, so use one or the other,
--               never both averaged) | yahoo_pianowski_ros
-- analyst       who made the list: "expert consensus", or the expert's name as the source prints it
-- scoring       ppr | half_ppr | standard | unstated (the page does not say)
-- pos_rank      the source's own positional rank; for a dollar list, by value, ties sharing the average
-- overall_rank  the source's overall rank when it publishes one, else NULL
-- source_value  a published number beside the rank (Yahoo dollar value), else NULL; never a trade value
-- tier          the source's tier when it publishes one, else NULL
-- rank_min/max/avg/std, experts: consensus spread when the source publishes it, else NULL
-- source_vintage the date the source says it was published or updated, never the run date
--
-- Rollback (new table, no dependents; indexes drop with it):
--   DROP TABLE IF EXISTS public.ros_rankings;

CREATE TABLE IF NOT EXISTS public.ros_rankings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source TEXT NOT NULL,
    analyst TEXT NOT NULL,
    scoring TEXT NOT NULL,
    pos TEXT NOT NULL,
    player_key INTEGER NOT NULL,
    player_name TEXT,
    team TEXT,
    pos_rank NUMERIC NOT NULL,
    overall_rank NUMERIC,
    source_value NUMERIC,
    tier INTEGER,
    rank_min NUMERIC,
    rank_max NUMERIC,
    rank_avg NUMERIC,
    rank_std NUMERIC,
    experts INTEGER,
    source_vintage DATE NOT NULL,
    source_url TEXT NOT NULL,
    season INTEGER NOT NULL,
    week INTEGER,
    pulled_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now(),
    _run_id TEXT,
    _writer_identity TEXT,
    _written_at TIMESTAMPTZ DEFAULT now(),
    CONSTRAINT ros_rankings_scoring_chk CHECK (scoring IN ('ppr', 'half_ppr', 'standard', 'unstated')),
    CONSTRAINT ros_rankings_pos_chk CHECK (pos IN ('QB', 'RB', 'WR', 'TE'))
);

CREATE UNIQUE INDEX IF NOT EXISTS ros_rankings_grain_uidx
    ON public.ros_rankings (source, analyst, scoring, pos, player_key, source_vintage);
CREATE INDEX IF NOT EXISTS ros_rankings_vintage_idx
    ON public.ros_rankings (source, source_vintage DESC);

ALTER TABLE public.ros_rankings ENABLE ROW LEVEL SECURITY;
