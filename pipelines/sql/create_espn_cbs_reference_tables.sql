-- ============================================================
-- Stage 1b: reference tables for the two gap sources (ESPN, CBS)
--
-- EXECUTED 2026-09-22 (user-approved). Tables created via the Supabase
-- Management API database/query endpoint (same backend as the SQL editor;
-- PostgREST cannot run DDL). No data loaded; tables start empty for the
-- import stage.
--
-- Design notes:
--   * Mirrors public.source_trade_values grain where the source fits it
--     (CBS trade values), so the stage-1 importer needs no special case.
--   * ESPN's saved reference is per-player ROS stat projections
--     (goals/football-signal-database-and-app/files/espn_projections.csv);
--     the table stores those stats verbatim. The chart's ESPN leg is
--     computed from them via the DDF methodology at bake time.
--   * Player identity: numeric player_key into the Supabase players table
--     (the naming authority). player_norm is a join label, never the key.
--   * Vintage: source_content_date = when the SOURCE last changed its
--     numbers. pulled_at = when we pulled it. Never confuse the two.
-- ============================================================

-- CBS (Dave Richards) trade values, mirroring source_trade_values.
CREATE TABLE IF NOT EXISTS public.cbs_trade_values (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    source text NOT NULL DEFAULT 'cbs',
    variant text NOT NULL DEFAULT 'as_published',
    -- 'as_published' = the chart's own numbers. Any fitted calibration
    -- we derive later is a separate variant and is never imported as the source.
    player_key bigint NOT NULL,
    player_norm text,
    scoring text NOT NULL,            -- 'standard' | 'half_ppr' | 'ppr' (CBS non / 0.5 / PPR columns)
    league_teams integer NOT NULL DEFAULT 12,
    qb_slots integer NOT NULL DEFAULT 1,
    season integer NOT NULL,
    week integer NOT NULL,            -- CBS article week (e.g. 2)
    position text,
    team text,
    value double precision,          -- chart-scale value as published
    native_value double precision,   -- the chart's raw number (same scale for CBS)
    source_content_date date,        -- article published date when known
    pulled_at timestamptz,
    bake_id text,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT cbs_trade_values_scoring_check
        CHECK (scoring IN ('standard', 'half_ppr', 'ppr'))
);

CREATE UNIQUE INDEX IF NOT EXISTS cbs_trade_values_grain_uidx
    ON public.cbs_trade_values (source, variant, scoring, league_teams, qb_slots, season, week, player_key);

-- ESPN season projections (Mike Clay model), stored verbatim per player.
CREATE TABLE IF NOT EXISTS public.espn_season_projections (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    player_key bigint NOT NULL,
    player_norm text,
    season integer NOT NULL,
    week integer NOT NULL,            -- designated week of the projection pull
    scoring text NOT NULL DEFAULT 'half_ppr',
    r_pass_yds double precision,
    r_pass_tds double precision,
    r_rush_yds double precision,
    r_rush_tds double precision,
    r_receptions double precision,
    r_rec_yds double precision,
    r_rec_tds double precision,
    ros_half_ppr double precision,   -- headline ROS half-PPR fantasy total
    weeks_covered text,              -- e.g. '3-18'
    espn_snapshot_date date,         -- vintage: when ESPN last changed the numbers
    pulled_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS espn_season_projections_grain_uidx
    ON public.espn_season_projections (season, week, player_key);
