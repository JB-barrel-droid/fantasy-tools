-- Migration 003: Razzball rest-of-season projections table (JEG-18)
-- Wires razzball through Supabase (was file-only). Run in the Supabase SQL editor
-- (PostgREST cannot run DDL). Modeled on public.cbs_ros_projections.
--
-- NOT YET RUN. Run only with explicit approval; see JEG-18 and PR #23.
-- After running: NOTIFY pgrst, 'reload schema';  (PostgREST may 404 a new table
-- until its schema cache reloads, as happened with cbs_ros_projections.)
--
-- Rollback (new table, no foreign keys or dependents; indexes drop with it):
--   DROP TABLE IF EXISTS public.razzball_projections;
-- Per-vintage cleanup:
--   DELETE FROM public.razzball_projections WHERE razzball_snapshot_date = '<date>';

CREATE TABLE IF NOT EXISTS public.razzball_projections (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    player_key INTEGER NOT NULL,
    player_norm TEXT,
    pos TEXT,
    team TEXT,
    health TEXT,
    -- Razzball's Games column is doubled (the doubling quirk): stored as reported,
    -- never used for pricing. The per-game columns below are the canonical values.
    games_reported NUMERIC,
    per_game_standard NUMERIC,
    per_game_half_ppr NUMERIC,
    per_game_ppr NUMERIC,
    -- every other snapshot row field (pg_*, share_*, ...) verbatim, so the importer
    -- can rebuild the native snapshot row exactly
    raw_stats JSONB,
    razzball_snapshot_date DATE,
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
CREATE UNIQUE INDEX IF NOT EXISTS razzball_projections_player_date_uidx
    ON public.razzball_projections (player_key, razzball_snapshot_date);

-- Lookup by snapshot date (import selects latest)
CREATE INDEX IF NOT EXISTS razzball_projections_snapshot_date_idx
    ON public.razzball_projections (razzball_snapshot_date DESC);
