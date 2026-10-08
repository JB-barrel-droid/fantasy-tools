-- 2026-10-08 security lockdown (monitoring lane; GAP-RLS-MONITORING,
-- GAP-SUPABASE-ADVISORS). NOT APPLIED by the authoring session: the integrator
-- applies it with apply_migration (name: security_lockdown_20261008).
--
-- What the Supabase security advisor reported on 2026-10-08 10:25 UTC and what
-- this does about each finding:
--
--   ERROR rls_disabled_in_public (83 tables)      -> part 2: RLS on, reads kept
--   ERROR security_definer_view  (37 views)       -> part 3: public.* views run
--                                                    as the caller; api.* kept
--                                                    (see the note in part 3)
--   WARN  function_search_path_mutable (9)        -> part 4: pinned search_path
--   WARN  extension_in_public (pg_net)            -> not changed (see the end)
--   INFO  rls_enabled_no_policy (6)               -> intended: service-role-only
--                                                    tables; no anon/auth access
--   (2026-10-07 advisor) monitoring.* RLS off     -> part 1
--
-- The real hole, found while checking the advisor: `anon` (the publishable
-- key, which is not a secret) held INSERT/UPDATE/DELETE/TRUNCATE on all 83
-- public tables with RLS off, including source_trade_values, cbs_trade_values,
-- espn_season_projections and the other inputs the chart is built from. Anyone
-- with the publishable key could rewrite the numbers. It also held
-- INSERT/UPDATE/DELETE on the public SECURITY DEFINER views, which write
-- through as the owner and bypass RLS.
--
-- Who uses what (edge logs, 2026-10-01 .. 10-08; and pg_cron/pg_policies):
--   * every production writer (GitHub Actions, pg_cron, edge functions) uses
--     service_role (bypasses RLS) or runs as postgres (table owner; RLS is
--     not forced, so the owner bypasses it). No request with the anon or
--     publishable key wrote anything in that window.
--   * anon / publishable-key READS do happen (Jeremy's local scripts read
--     cbs_ros_projections, razzball_projections, espn_season_projections,
--     teams, games, source_trade_values). Part 2 keeps every read anon or
--     authenticated can do today, table by table, by copying the current
--     SELECT privilege into a read policy.
--   * the static site does not call Supabase from the browser.
--   * auth.users is empty, so `authenticated` has no real users.

begin;

-- ---------------------------------------------------------------------------
-- Part 1. monitoring.* : RLS on, no policies. anon/authenticated have no USAGE
-- on schema monitoring and no table grants; service_role and the SECURITY
-- DEFINER functions (owner postgres) are the only readers/writers and bypass
-- RLS. The served monitor reads public.monitoring_summary() with service_role.
-- ---------------------------------------------------------------------------
alter table monitoring.check_config         enable row level security;
alter table monitoring.check_observations   enable row level security;
alter table monitoring.check_heartbeats     enable row level security;
alter table monitoring.scheduler_heartbeats enable row level security;
revoke all on all tables in schema monitoring from anon, authenticated;

-- ---------------------------------------------------------------------------
-- Part 2. public tables: RLS on every table, a read policy wherever the role
-- can read today, and no write path for anon/authenticated at all.
-- ---------------------------------------------------------------------------
do $$
declare
  t record;
  r text;
begin
  for t in
    select c.oid, c.relname
    from pg_class c join pg_namespace n on n.oid = c.relnamespace
    where n.nspname = 'public' and c.relkind in ('r', 'p')
      -- Tables that already have RLS keep their current policies: adding a
      -- read policy there would OPEN reads RLS blocks today (e.g.
      -- pipeline_write_audit, live_page_checks).
      and not c.relrowsecurity
  loop
    foreach r in array array['anon', 'authenticated'] loop
      if has_table_privilege(r, t.oid, 'SELECT')
         and not exists (
           select 1 from pg_policies p
           where p.schemaname = 'public' and p.tablename = t.relname
             and p.cmd in ('SELECT', 'ALL')
             and (r = any(p.roles) or 'public' = any(p.roles)))
      then
        execute format(
          'create policy %I on public.%I for select to %I using (true)',
          r || '_read_20261008', t.relname, r);
      end if;
    end loop;
    execute format('alter table public.%I enable row level security', t.relname);
  end loop;
end
$$;

-- TRUNCATE is not subject to RLS, so the write grants go too (tables, views
-- and sequences). Reads (SELECT) are left exactly as they were.
revoke insert, update, delete, truncate, references, trigger
  on all tables in schema public from anon, authenticated;
revoke usage, update on all sequences in schema public from anon, authenticated;

-- Tables created later by postgres must not hand anon/authenticated a write
-- grant by default again.
alter default privileges for role postgres in schema public
  revoke insert, update, delete, truncate, references, trigger on tables from anon, authenticated;
alter default privileges for role postgres in schema public
  revoke usage, update on sequences from anon, authenticated;

-- ---------------------------------------------------------------------------
-- Part 3. public.* views run with the caller's rights. service_role (every
-- pipeline reader) bypasses RLS and has SELECT on every public table, so its
-- reads do not change; an anon read through a view now needs the same table
-- access a direct read needs (so a view can no longer leak public.players,
-- which anon cannot read directly).
--
-- api.* views are left SECURITY DEFINER on purpose: they are the designed,
-- read-only, security_barrier front-end surface (sql/contract/
-- api_publish_gate.sql §7, weekly_dashboard_api_view.sql); anon holds SELECT
-- only on them, never a write. Flipping them would turn the curated surface
-- off for anon. The advisor will keep listing those 11; that is the accepted
-- residual (GAP-SUPABASE-ADVISORS).
-- ---------------------------------------------------------------------------
do $$
declare v record;
begin
  for v in
    select c.relname
    from pg_class c join pg_namespace n on n.oid = c.relnamespace
    where n.nspname = 'public' and c.relkind = 'v'
  loop
    execute format('alter view public.%I set (security_invoker = true)', v.relname);
  end loop;
end
$$;

-- ---------------------------------------------------------------------------
-- Part 4. Pin search_path on the functions the advisor named. Each body was
-- read on 2026-10-08: the public ones reference public tables (and one a temp
-- table, so pg_temp stays on the path); the monitoring ones only
-- schema-qualified monitoring objects; api.gate_source_freshness public.*.
-- ---------------------------------------------------------------------------
alter function public.f_american_prob(double precision)                set search_path = public, pg_temp;
alter function public.resolve_player_identity(text, text)              set search_path = public, pg_temp;
alter function public.resolve_weekly_identities(text[])                set search_path = public, pg_temp;
alter function public.resolve_weekly_identities_strict(text[])         set search_path = public, pg_temp;
alter function public.enforce_never_blend()                            set search_path = public, pg_temp;
alter function public.validate_never_blend()                           set search_path = public, pg_temp;
alter function api.gate_source_freshness(text, uuid)                   set search_path = api, public, pg_temp;
alter function monitoring.run_evaluator_cycle(timestamptz)             set search_path = monitoring, public, pg_temp;
alter function monitoring.compute_heartbeat_state(text, boolean, integer, text, integer, integer,
    monitoring.check_type, monitoring.scheduler_owner_type, text, integer, timestamptz)
                                                                       set search_path = monitoring, public, pg_temp;

commit;

notify pgrst, 'reload schema';

-- Not changed: extension_in_public (pg_net). pg_net is not relocatable
-- (ALTER EXTENSION ... SET SCHEMA is unsupported); moving it means DROP +
-- CREATE, which drops net._http_response (the dispatch outcome history
-- monitoring.v_dispatch_outcomes joins) and breaks every pg_cron dispatch
-- mid-flight. Its callable functions live in schema `net`, not public. Low
-- risk; left as the advisor's WARN.
