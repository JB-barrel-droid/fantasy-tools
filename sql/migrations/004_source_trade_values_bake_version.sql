-- 004: bake-versioned unique index on public.source_trade_values
--
-- Week-versioning practice (Jeremy 2026-10-02): a week may hold multiple
-- immutable bakes (re-ingests of revised publisher content). The upsert grain
-- gains bake_id so a new version inserts instead of overwriting the prior
-- bake. Readers select exactly one bake per week
-- (import_supabase_references._select_latest_bake); versions are never
-- blended. Rows are never deleted -- old bakes are the audit trail.
--
-- The 8-column grain index from 003 stays: the FantasyPros/FantasyCalc savers
-- still upsert on the overwrite grain until their flows are version-aware.
-- USA Today is the first versioned writer (USAT_UPSERT_CONFLICT_VERSIONED).
--
-- NULL bake_id rows (pre-versioning writes) never conflict with each other
-- under this index (Postgres treats NULLs as distinct), so the index builds
-- cleanly over history.
--
-- Apply via the Supabase SQL editor (PostgREST cannot run DDL), then:
--   NOTIFY pgrst, 'reload schema';
-- (cbsros precedent).

CREATE UNIQUE INDEX IF NOT EXISTS source_trade_values_bake_version_uidx
    ON public.source_trade_values
    (source, variant, scoring, league_teams, qb_slots, season, week, player_key, bake_id);
