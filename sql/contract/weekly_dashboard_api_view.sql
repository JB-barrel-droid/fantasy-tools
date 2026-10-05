-- Weekly dashboard frontend contract view (JEG-327).
--
-- Mirrors public.v_current_weekly_signals in the api schema so the public
-- frontend reads one versioned surface without knowing the base tables.
-- Column-for-column identical to public.v_current_weekly_signals.
--
-- STAGED — DO NOT APPLY without Jeremy's explicit "approve Stage 2".
-- Apply via the Supabase SQL editor (browser, SSO), then run:
--     NOTIFY pgrst, 'reload schema';
-- The read posture (security_invoker=false, security_barrier=true, anon
-- SELECT on the view only) already lives in section 3d of
-- sql/contract/api_v1_grants_stage2.sql and is applied with the same nod.

CREATE OR REPLACE VIEW api.v_current_weekly_signals AS
SELECT
  r.season,
  r.week,
  s.run_id,
  r.created_at AS run_created_at,
  r.source_manifest,
  s.player_key,
  s.position,
  s.team,
  s.signal,
  s.created_at AS signal_created_at
FROM public.weekly_dashboard_runs r
JOIN public.weekly_dashboard_signals s ON s.run_id = r.run_id
WHERE r.is_current;
