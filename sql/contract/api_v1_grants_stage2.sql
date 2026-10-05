-- ============================================================
-- JEG-327 Phase B — Stage 2: anon SELECT on api.* views (APPLIED)
-- Status: APPLIED 2026-10-05 ~11:54 CDT via Supabase SQL editor (GitHub SSO).
-- Verified: anon SELECT on all 5 api views = true; anon cannot SELECT
-- public.consolidated_values; security_barrier=true on views;
-- api.player_values count = 20,865.
-- §3 (weekly) APPLIED 2026-10-05 ~12:08 CDT via SQL editor (Jeremy: "approve
-- stage 2"): CREATE api.v_current_weekly_signals, §3a REVOKE base tables,
-- §3b RLS on, §3c service_role policies, §3d view posture + anon GRANT,
-- NOTIFY pgrst reload. Verified: has_table_privilege anon=true on the api
-- view / false on both base tables; RLS on; api view returns 390 rows
-- (Week 4). Service-role ETL path on base tables confirmed intact.
-- Designed by ChatGPT lane 2026-10-04; reviewed by Roman.
-- Stage 1 (api_v1.sql) must be applied first.
-- ============================================================

BEGIN;

-- Stage 2: expose read-only anon to api.* views, while preventing bypass to public.*

-- 0) Defensive: deny anon (and PUBLIC) direct reads on base tables that feed the api.* views.
--    This ensures anon can’t bypass the views even with RLS off on public.*
REVOKE SELECT ON TABLE
  public.consolidated_values,
  public.players,
  public.product_options,
  public.product_snapshot,
  public.player_news,
  public.player_adjustments,
  public.player_review
FROM PUBLIC, anon;

-- 1) Grant anon usage on api schema and SELECT on the five contract views
GRANT USAGE ON SCHEMA api TO anon;

GRANT SELECT ON TABLE
  api.player_values,
  api.players,
  api.player_context,
  api.product_options,
  api.product_snapshot
TO anon;

-- 2) Lock view security semantics:
--    - security_invoker = false (default) => underlying object privileges and RLS
--      are checked as the view owner, not the caller (anon).
--    - security_barrier = true => prevents leaky function/predicate pushdown issues.
--    These are explicit to make intent clear and verifiable.
ALTER VIEW api.player_values      SET (security_invoker = false, security_barrier = true);
ALTER VIEW api.players            SET (security_invoker = false, security_barrier = true);
ALTER VIEW api.player_context     SET (security_invoker = false, security_barrier = true);
ALTER VIEW api.product_options    SET (security_invoker = false, security_barrier = true);
ALTER VIEW api.product_snapshot   SET (security_invoker = false, security_barrier = true);

-- 3) Weekly dashboard posture (apply when these objects exist).
--    Goal: anon reads a curated api view only. Base tables protected by RLS;
--    service_role has explicit read/write for ETL/CI. No anon or authenticated on base tables.

-- 3a) Deny direct reads from base tables (belt-and-suspenders).
REVOKE SELECT ON TABLE
  public.weekly_dashboard_runs,
  public.weekly_dashboard_signals
FROM PUBLIC, anon;

-- 3b) Enable RLS on base tables (deny-by-default until policies are defined).
ALTER TABLE IF EXISTS public.weekly_dashboard_runs     ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.weekly_dashboard_signals  ENABLE ROW LEVEL SECURITY;

-- 3c) Service-role read/write policies on base tables
--     (Drop-then-create for idempotency across replays)
DO $$
BEGIN
  -- weekly_dashboard_runs policies
  IF to_regclass('public.weekly_dashboard_runs') IS NOT NULL THEN
    DROP POLICY IF EXISTS weekly_dashboard_runs_service_read   ON public.weekly_dashboard_runs;
    DROP POLICY IF EXISTS weekly_dashboard_runs_service_write  ON public.weekly_dashboard_runs;
    DROP POLICY IF EXISTS weekly_dashboard_runs_service_update ON public.weekly_dashboard_runs;

    CREATE POLICY weekly_dashboard_runs_service_read
      ON public.weekly_dashboard_runs
      FOR SELECT
      TO service_role
      USING (true);

    CREATE POLICY weekly_dashboard_runs_service_write
      ON public.weekly_dashboard_runs
      FOR INSERT
      TO service_role
      WITH CHECK (true);

    CREATE POLICY weekly_dashboard_runs_service_update
      ON public.weekly_dashboard_runs
      FOR UPDATE
      TO service_role
      USING (true)
      WITH CHECK (true);
  END IF;

  -- weekly_dashboard_signals policies
  IF to_regclass('public.weekly_dashboard_signals') IS NOT NULL THEN
    DROP POLICY IF EXISTS weekly_dashboard_signals_service_read   ON public.weekly_dashboard_signals;
    DROP POLICY IF EXISTS weekly_dashboard_signals_service_write  ON public.weekly_dashboard_signals;
    DROP POLICY IF EXISTS weekly_dashboard_signals_service_update ON public.weekly_dashboard_signals;

    CREATE POLICY weekly_dashboard_signals_service_read
      ON public.weekly_dashboard_signals
      FOR SELECT
      TO service_role
      USING (true);

    CREATE POLICY weekly_dashboard_signals_service_write
      ON public.weekly_dashboard_signals
      FOR INSERT
      TO service_role
      WITH CHECK (true);

    CREATE POLICY weekly_dashboard_signals_service_update
      ON public.weekly_dashboard_signals
      FOR UPDATE
      TO service_role
      USING (true)
      WITH CHECK (true);
  END IF;
END
$$ LANGUAGE plpgsql;

-- 3d) v_current_weekly_signals view exposure
--     Ensure it’s an api.* view with owner-rights semantics and barrier, and anon can only SELECT the view.
--     If it doesn’t exist yet, this will fail; keep this in the file but apply when the view lands.
ALTER VIEW api.v_current_weekly_signals SET (security_invoker = false, security_barrier = true);
GRANT SELECT ON TABLE api.v_current_weekly_signals TO anon;

-- 4) Monitoring reads recommendation (no anon grants).
--    If you expose monitoring views, keep them out of api or do NOT grant anon.
--    Example (commented out – for when such objects exist):
-- REVOKE ALL ON TABLE monitoring.health_events FROM PUBLIC, anon;
-- ALTER TABLE IF EXISTS monitoring.health_events ENABLE ROW LEVEL SECURITY;
-- DO $$
-- BEGIN
--   IF to_regclass('monitoring.health_events') IS NOT NULL THEN
--     DROP POLICY IF EXISTS health_events_service_read ON monitoring.health_events;
--     CREATE POLICY health_events_service_read
--       ON monitoring.health_events
--       FOR SELECT
--       TO service_role
--       USING (true);
--   END IF;
-- END
-- $$ LANGUAGE plpgsql;

COMMIT;

-- BEGIN;
-- REVOKE SELECT ON TABLE
--   api.player_values,
--   api.players,
--   api.player_context,
--   api.product_options,
--   api.product_snapshot,
--   api.v_current_weekly_signals
-- FROM anon;

-- REVOKE USAGE ON SCHEMA api FROM anon;

-- -- Optionally revert view attributes (no functional change for anon once REVOKEd)
-- ALTER VIEW api.player_values      RESET (security_barrier);
-- ALTER VIEW api.players            RESET (security_barrier);
-- ALTER VIEW api.player_context     RESET (security_barrier);
-- ALTER VIEW api.product_options    RESET (security_barrier);
-- ALTER VIEW api.product_snapshot   RESET (security_barrier);
-- ALTER VIEW api.v_current_weekly_signals RESET (security_barrier);

-- COMMIT;
