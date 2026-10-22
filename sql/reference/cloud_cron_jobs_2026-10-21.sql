-- REFERENCE ONLY (JEG-792 cancelled 2026-10-22; the self-host stack was removed).
-- Kept because this is the only repo record of the 20 cloud pg_cron jobs and the
-- dispatch_gha_workflow / dispatch_vintage_check bodies, read from cloud project
-- iskiybsimubiujwuchsl on 2026-10-21. Do not run it as is: the Mac-only steps
-- below (import_local.sh, cloud_cron_is_off) refer to files removed from the repo.
-- Restore them from git history (see docs/decisions.md, JEG-792 entry).
--
-- cron_and_functions.sql: workflow-dispatch functions and the 20 pg_cron jobs
-- for the self-hosted store on the Mac mini (JEG-792, lane B).
--
-- Source: read-only queries on cloud project iskiybsimubiujwuchsl, 2026-10-21:
--   SELECT pg_get_functiondef('public.dispatch_gha_workflow(text,jsonb)'::regprocedure),
--          pg_get_functiondef('public.dispatch_vintage_check()'::regprocedure);
--   SELECT jobid, jobname, schedule, active, command FROM cron.job ORDER BY jobid;
--   SELECT name, description FROM vault.secrets;   -- names only, never values
-- Function bodies below are verbatim. Job names, schedules and commands are
-- verbatim; all 20 were active on 2026-10-21.
--
-- Run AFTER import_local.sh, as a superuser, on the Mac only:
--
--   psql "$LOCAL_DATABASE_URL" -v ON_ERROR_STOP=1 \
--        -v cloud_cron_is_off=1 -f selfhost/migrate/cron_and_functions.sql
--
-- Prerequisites (lane A's image): pg_net, pg_cron (shared_preload_libraries =
-- 'pg_cron', cron.database_name = the database you restored into), and either
-- supabase_vault or the fallback vault shim in STEP 1b.
--
-- STEP 0 (Jeremy). The cloud project still runs these 20 jobs. If both the cloud
-- and the Mac schedule them, every workflow is dispatched twice. Turn the cloud
-- jobs off first (cloud write: Jeremy only), then pass -v cloud_cron_is_off=1.
-- Without that variable this file defines the functions and stops before
-- scheduling anything.
--
-- STEP 1 (Jeremy, by hand, once). Store the GitHub token in the vault BY NAME.
-- Never put the token in this file, in git, or in shell history. In psql:
--
--   \prompt 'GitHub dispatch token: ' gh_token
--   select vault.create_secret(:'gh_token', 'github_dispatch_token',
--                              'GitHub PAT for pg_cron workflow dispatch');
--   \unset gh_token
--
-- The token needs actions:write on JB-barrel-droid/fantasy-tools (the same
-- fine-grained PAT the cloud uses; create a new one if it is not at hand).
-- The cloud vault also holds 'supabase_service_key' (Edge Function auth); the
-- site does not use Edge Functions, so it is not needed here.
--
-- STEP 1b (only if supabase_vault is NOT installed locally). A minimal shim so
-- the function below can stay verbatim. The token is then stored in plain text
-- inside the Mac's database (not encrypted at rest); acceptable only because
-- the database is local to the Mac. Uncomment, run, then store the token with
--   \prompt 'GitHub dispatch token: ' gh_token
--   insert into vault.local_secrets(name, secret) values ('github_dispatch_token', :'gh_token');
--   \unset gh_token
--
-- create schema if not exists vault;
-- revoke all on schema vault from public;
-- create table if not exists vault.local_secrets (name text primary key, secret text not null,
--   created_at timestamptz not null default now());
-- revoke all on vault.local_secrets from public;
-- create or replace view vault.decrypted_secrets as
--   select name, secret as decrypted_secret from vault.local_secrets;
-- revoke all on vault.decrypted_secrets from public, anon, authenticated, service_role;

\set ON_ERROR_STOP on

-- Checks: fail early with a clear message instead of half-applying.
do $$
begin
  if not exists (select 1 from pg_extension where extname = 'pg_net') then
    raise exception 'pg_net is not installed: dispatch_gha_workflow calls net.http_post';
  end if;
  if not exists (select 1 from pg_namespace where nspname = 'vault') then
    raise exception 'no vault schema: install supabase_vault or run STEP 1b';
  end if;
  if not exists (select 1 from pg_class c join pg_namespace n on n.oid = c.relnamespace
                 where n.nspname = 'monitoring' and c.relname = 'dispatch_log') then
    raise exception 'monitoring.dispatch_log missing: run import_local.sh first';
  end if;
end $$;

-- ---------------------------------------------------------------------------
-- Functions (verbatim from the cloud; import_local.sh already restored them,
-- this makes the file self-contained and idempotent).
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.dispatch_gha_workflow(workflow_file text, inputs jsonb DEFAULT '{}'::jsonb)
 RETURNS bigint
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public', 'pg_temp'
AS $function$
declare
  req_id bigint;
  repo text := 'JB-barrel-droid/fantasy-tools';
  token text := (select decrypted_secret from vault.decrypted_secrets where name = 'github_dispatch_token' limit 1);
begin
  if token is null then
    raise exception 'github_dispatch_token not found in vault';
  end if;
  select net.http_post(
    url := format('https://api.github.com/repos/%s/actions/workflows/%s/dispatches', repo, workflow_file),
    headers := jsonb_build_object(
      'Authorization', 'Bearer ' || token,
      'Accept', 'application/vnd.github+json',
      'Content-Type', 'application/json'),
    body := jsonb_build_object('ref', 'main', 'inputs', inputs)
  ) into req_id;
  insert into monitoring.dispatch_log (req_id, workflow_file) values (req_id, workflow_file)
  on conflict do nothing;
  return req_id;
end;
$function$;

CREATE OR REPLACE FUNCTION public.dispatch_vintage_check()
 RETURNS void
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public', 'pg_temp'
AS $function$
BEGIN
  PERFORM public.dispatch_gha_workflow('source-vintage-check.yml', '{}');
  END;
  $function$;

-- Same grants as the cloud (proacl on 2026-10-21:
-- {postgres=X/postgres,service_role=X/postgres}).
revoke all on function public.dispatch_gha_workflow(text, jsonb) from public, anon, authenticated;
revoke all on function public.dispatch_vintage_check() from public, anon, authenticated;
grant execute on function public.dispatch_gha_workflow(text, jsonb) to service_role;
grant execute on function public.dispatch_vintage_check() to service_role;

\if :{?cloud_cron_is_off}
\else
\echo 'Functions defined. NOT scheduling: turn the cloud pg_cron jobs off first (STEP 0), then re-run with -v cloud_cron_is_off=1'
\quit
\endif

do $$
begin
  if not exists (select 1 from pg_extension where extname = 'pg_cron') then
    raise exception 'pg_cron is not installed (needs shared_preload_libraries=pg_cron)';
  end if;
  if not exists (select 1 from vault.decrypted_secrets where name = 'github_dispatch_token') then
    raise exception 'github_dispatch_token is not in the vault yet: do STEP 1 first';
  end if;
end $$;

-- ---------------------------------------------------------------------------
-- The 20 pg_cron jobs (cron.schedule upserts by name, so re-running is safe).
-- Times are UTC, as on the cloud. Tags:
--   [chain]       rebuild chain, savers, probes, identity, fidelity, deploy
--   [dashboard]   weekly store, status history, player trace
--   [monitoring]  exists for the retired monitoring lane; keep or drop is
--                 Jeremy's call (no job exists for another app)
--   [housekeeping]
-- ---------------------------------------------------------------------------
-- jobid 1  [housekeeping] trims pg_cron's own run log
select cron.schedule('cron-retention-30d', '0 3 * * *', $cmd$delete from cron.job_run_details where start_time < now() - interval '30 days'$cmd$);
-- jobid 11 [dashboard] player trace page
select cron.schedule('trigger-player-trace-live', '47 12 * * *', $cmd$SELECT public.dispatch_gha_workflow('player-trace-rebuild.yml', '{}'::jsonb)$cmd$);
-- jobid 15 [monitoring] live-page synthetic check (writes public.live_page_checks / check_observations)
select cron.schedule('live-page-synthetic-live', '15 12 * * *', $cmd$SELECT public.dispatch_gha_workflow('live-page-synthetic.yml', '{}'::jsonb)$cmd$);
-- jobid 16 [chain] source vintage check, hourly
select cron.schedule('vintage-check-live', '0 * * * *', $cmd$SELECT public.dispatch_vintage_check()$cmd$);
-- jobid 22 [chain] FantasyCalc saver
select cron.schedule('trigger-fantasycalc-weekly-save', '7 13 * * 2,5', $cmd$SELECT public.dispatch_gha_workflow('fantasycalc-weekly-save.yml', '{"mode": "write"}'::jsonb)$cmd$);
-- jobid 23 [monitoring] health artifacts / monitoring summary for the ops page
select cron.schedule('health-artifacts-live', '50 */6 * * *', $cmd$SELECT public.dispatch_gha_workflow('health-artifacts.yml', '{}'::jsonb)$cmd$);
-- jobid 27 [chain] site build and deploy
select cron.schedule('pages-deploy-live', '30 11 * * *', $cmd$SELECT public.dispatch_gha_workflow('pages.yml', '{}'::jsonb)$cmd$);
-- jobid 29 [chain] Sleeper identity refresh
select cron.schedule('sleeper-identity-refresh-live', '17 9 * * 2,4', $cmd$SELECT public.dispatch_gha_workflow('sleeper-identity-refresh.yml', '{}'::jsonb)$cmd$);
-- jobid 30 [chain] rebuild chain with bake
select cron.schedule('rebuild-chain-bake-live', '45 11 * * *', $cmd$SELECT public.dispatch_gha_workflow('rebuild-chain.yml', '{"source": "pg_cron-bake", "bake_players": "true"}'::jsonb)$cmd$);
-- jobid 32 [chain] source probe: FantasyCalc
select cron.schedule('source-probe-fantasycalc', '5 * * * *', $cmd$SELECT public.dispatch_gha_workflow('source-probe.yml', '{"sources": "fantasycalc"}'::jsonb)$cmd$);
-- jobid 33 [chain] source probe: projections
select cron.schedule('source-probe-projections', '25 3-23/4 * * *', $cmd$SELECT public.dispatch_gha_workflow('source-probe.yml', '{"sources": "espn,cbsros,razzball"}'::jsonb)$cmd$);
-- jobid 34 [chain] source probe: trade charts, Mon-Thu
select cron.schedule('source-probe-trade-charts', '35 */3 * * 1-4', $cmd$SELECT public.dispatch_gha_workflow('source-probe.yml', '{"sources": "cbs,usatoday,fantasypros"}'::jsonb)$cmd$);
-- jobid 35 [chain] source probe: trade charts, Fri-Sun
select cron.schedule('source-probe-trade-charts-weekend', '35 0,12 * * 0,5,6', $cmd$SELECT public.dispatch_gha_workflow('source-probe.yml', '{"sources": "cbs,usatoday,fantasypros"}'::jsonb)$cmd$);
-- jobid 36 [chain] identity reconcile
select cron.schedule('player-identity-reconcile-nightly', '30 7 * * *', $cmd$SELECT public.dispatch_gha_workflow('player-identity-reconcile.yml', '{"mode": "write"}'::jsonb)$cmd$);
-- jobid 37 [chain] fidelity pulse
select cron.schedule('fidelity-pulse-live', '40 */3 * * *', $cmd$SELECT public.dispatch_gha_workflow('fidelity-pulse.yml', '{}'::jsonb)$cmd$);
-- jobid 38 [dashboard] ESPN weekly store, daily
select cron.schedule('espn-weekly-store-live', '40 12 * * *', $cmd$SELECT public.dispatch_gha_workflow('espn-weekly-store.yml', '{"mode": "write"}'::jsonb)$cmd$);
-- jobid 39 [dashboard] ESPN weekly store, Sunday
select cron.schedule('espn-weekly-store-sunday', '20 16 * * 0', $cmd$SELECT public.dispatch_gha_workflow('espn-weekly-store.yml', '{"mode": "write"}'::jsonb)$cmd$);
-- jobid 40 [dashboard] player status history, daily
select cron.schedule('player-status-history-live', '10 13 * * *', $cmd$SELECT public.dispatch_gha_workflow('player-status-history.yml', '{"mode": "write"}'::jsonb)$cmd$);
-- jobid 41 [dashboard] player status history, Sunday
select cron.schedule('player-status-history-sunday', '30 16 * * 0', $cmd$SELECT public.dispatch_gha_workflow('player-status-history.yml', '{"mode": "write"}'::jsonb)$cmd$);
-- jobid 46 [chain] source probe: DraftSharks, FantasySharks
select cron.schedule('source-probe-sharks', '45 4,16 * * *', $cmd$SELECT public.dispatch_gha_workflow('source-probe.yml', '{"sources": "draftsharks,fantasysharks"}'::jsonb)$cmd$);

-- Check: exactly these 20 names are scheduled.
do $$
declare n int;
begin
  select count(*) into n from cron.job where jobname in (
    'cron-retention-30d','trigger-player-trace-live','live-page-synthetic-live','vintage-check-live',
    'trigger-fantasycalc-weekly-save','health-artifacts-live','pages-deploy-live',
    'sleeper-identity-refresh-live','rebuild-chain-bake-live','source-probe-fantasycalc',
    'source-probe-projections','source-probe-trade-charts','source-probe-trade-charts-weekend',
    'player-identity-reconcile-nightly','fidelity-pulse-live','espn-weekly-store-live',
    'espn-weekly-store-sunday','player-status-history-live','player-status-history-sunday',
    'source-probe-sharks');
  if n <> 20 then
    raise exception 'expected 20 scheduled jobs, found %', n;
  end if;
  raise notice 'scheduled 20 pg_cron jobs';
end $$;
