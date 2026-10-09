-- JEG-482 (2026-10-09): drop the 70 cap on Indexed values.
--
-- Jeremy approved 2026-10-09: Indexed (view = 'combo_reindexed') is a pure
-- order-preserving rescale with no cap. One-factor Indexed values can exceed
-- 70 (Week 5 FantasyCalc full PPR tops at 78.6), and the CHECK made the
-- chain's consolidated_values_write step refuse the whole write.
-- pipelines/build_consolidated_values.py no longer pre-flights against 70.
--
-- ALREADY APPLIED to production (project iskiybsimubiujwuchsl) on 2026-10-09
-- as migration jeg482_drop_indexed_cap_70. This file is the record only.
--
-- Original constraint (supabase/migrations/jeg377_jeg380_api_mirror.sql):
--   ck_combo_reindexed_cap CHECK (view <> 'combo_reindexed' OR value <= 70)

alter table public.consolidated_values drop constraint if exists ck_combo_reindexed_cap;
