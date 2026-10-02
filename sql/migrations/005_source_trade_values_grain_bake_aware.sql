-- 005: evolve the legacy player_norm grain to be bake-aware
--
-- Week-versioning practice (Jeremy 2026-10-02): a week may hold multiple
-- immutable bakes. The legacy unique index source_trade_values_grain on
-- (source, player_norm, scoring, league_teams, qb_slots, season, week,
-- variant) rejected the second version of any week with a 23505 duplicate-key
-- error (the upsert arbitrates only the index it names, so the legacy
-- player_norm grain still fired -- risk-register GAP-023).
--
-- This evolves the grain instead of dropping it: bake_id joins the column
-- list, so the ambiguous-name deduplication protection is preserved per
-- version. The new grain is strictly finer than the old, so the CREATE
-- cannot fail on existing rows; NULL bake_ids (pre-versioning writes) never
-- conflict with each other under Postgres unique semantics.
--
-- Resolves GAP-023 by evolution, not removal.
--
-- Apply via the Supabase SQL editor (PostgREST cannot run DDL), then:
--   NOTIFY pgrst, 'reload schema';

-- The legacy grain is a UNIQUE constraint; dropping it also removes its index.
ALTER TABLE public.source_trade_values
    DROP CONSTRAINT IF EXISTS source_trade_values_grain;
CREATE UNIQUE INDEX IF NOT EXISTS source_trade_values_grain
    ON public.source_trade_values
    (source, player_norm, scoring, league_teams, qb_slots, season, week, variant, bake_id);
