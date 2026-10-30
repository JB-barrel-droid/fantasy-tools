-- Rollback for supabase/migrations/jeg1061_shared_rate_limit_20261030.sql (JEG-1061).
-- First unset the get-values secret DDF_SHARED_RATE_LIMIT (or set it to 0), so the
-- function stops calling edge_rate_hit; with the secret on and the function gone,
-- get-values still runs (it falls back to the in-memory limit) but logs a fallback
-- line on every fresh compute.
drop function if exists public.edge_rate_hit(text, integer, integer);
drop table if exists public.edge_rate_buckets;
notify pgrst, 'reload schema';
