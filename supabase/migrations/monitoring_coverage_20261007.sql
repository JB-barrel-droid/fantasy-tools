-- Monitoring coverage audit (2026-10-07): every scheduled pipeline gets a
-- monitoring.check_config row, a recorded observation on success AND failure,
-- evaluator coverage for "never ran" and "stopped running", and a single
-- summary the served monitor can read.
--
-- APPLIED to project iskiybsimubiujwuchsl in three parts (names below). All
-- statements are additive or replace function bodies; nothing is deleted.
--   part 1  monitoring_coverage_1_lockdown_dispatch_and_log
--   part 2  monitoring_coverage_2_checks_and_evaluator
--   part 3  monitoring_coverage_3_cron_observer_and_summary

-- ===========================================================================
-- Part 1. Lock down the dispatcher; log every dispatch so failures attribute.
-- ===========================================================================

-- public.dispatch_gha_workflow is SECURITY DEFINER and reads the GitHub token
-- from the vault. It was executable by anon/authenticated (default PUBLIC
-- execute), so anyone holding the public anon key could dispatch any workflow
-- in the repo. pg_cron runs as the owner, so nothing legitimate needs this.
revoke execute on function public.dispatch_gha_workflow(text, jsonb) from public, anon, authenticated;
revoke execute on function public.dispatch_vintage_check() from public, anon, authenticated;

create table if not exists monitoring.dispatch_log (
    req_id        bigint primary key,
    workflow_file text        not null,
    dispatched_at timestamptz not null default now()
);
create index if not exists dispatch_log_workflow_idx
    on monitoring.dispatch_log (workflow_file, dispatched_at desc);
alter table monitoring.dispatch_log enable row level security;

create or replace function public.dispatch_gha_workflow(workflow_file text, inputs jsonb default '{}'::jsonb)
 returns bigint
 language plpgsql
 security definer
 set search_path to 'public', 'pg_temp'
as $function$
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
  -- pg_net is async: cron reports "succeeded" once the request is queued, even
  -- when GitHub answers 404/422. Keep the request id so the real HTTP outcome
  -- can be joined back to the workflow (monitoring.v_dispatch_outcomes).
  insert into monitoring.dispatch_log (req_id, workflow_file) values (req_id, workflow_file)
  on conflict do nothing;
  return req_id;
end;
$function$;
revoke execute on function public.dispatch_gha_workflow(text, jsonb) from public, anon, authenticated;

create or replace view monitoring.v_dispatch_outcomes as
select l.workflow_file,
       l.req_id,
       l.dispatched_at,
       r.status_code,
       case
         when r.id is null then 'pending_or_expired'
         when r.error_msg is not null or r.status_code <> 204 then 'failed'
         else 'ok'
       end as outcome,
       case when r.id is not null and (r.error_msg is not null or r.status_code <> 204)
            then coalesce(r.error_msg, left(r.content, 200)) end as detail
from monitoring.dispatch_log l
left join net._http_response r on r.id = l.req_id;

-- ===========================================================================
-- Part 2. Check rows for every scheduled pipeline + evaluator "never ran".
-- ===========================================================================

-- The evaluator reported a check that has never been observed as 'unknown'
-- forever, so a new pipeline that never ran (or a dispatch that always fails)
-- was never flagged. Count the wait from the check's creation instead.
create or replace function monitoring.compute_heartbeat_state(p_check_id text, p_enabled boolean, p_cadence_seconds integer, p_cron_expr text, p_grace_override integer, p_latency_budget_ms integer, p_check_type monitoring.check_type, p_owner_type monitoring.scheduler_owner_type, p_owner_id text, p_active_ownership integer, p_now timestamp with time zone)
 returns table(state monitoring.heartbeat_state, state_reason text, expected_next_run_at timestamp with time zone, last_run_at timestamp with time zone, last_ok_at timestamp with time zone, last_error_at timestamp with time zone, ownership_status monitoring.ownership_status, scheduler_down boolean, latest_details jsonb)
 language plpgsql
 stable
as $function$
declare
v_grace integer;
v_latest_obs record;
v_latest_in_window record;
v_expected_next timestamptz;
v_window_start timestamptz;
v_scheduler_down boolean;
v_ownership_status monitoring.ownership_status;
v_state monitoring.heartbeat_state;
v_state_reason text;
v_latest_details jsonb;
v_created timestamptz;
begin
if not p_enabled then
return query select 'disabled'::monitoring.heartbeat_state, 'enabled=false', null::timestamptz, null::timestamptz, null::timestamptz, null::timestamptz, 'ok'::monitoring.ownership_status, false, '{}'::jsonb;
return;
end if;
if p_cadence_seconds is null and p_cron_expr is null then
return query select 'unknown'::monitoring.heartbeat_state, 'no schedule resolvable', null::timestamptz, null::timestamptz, null::timestamptz, null::timestamptz, 'ok'::monitoring.ownership_status, false, '{}'::jsonb;
return;
end if;
if p_grace_override is not null then
v_grace := greatest(120, least(1800, p_grace_override));
elsif p_cadence_seconds is not null then
v_grace := greatest(120, least(1800, ceil(1.5 * p_cadence_seconds)::int));
else
v_grace := 600;
end if;
if p_active_ownership <= 0 then
v_ownership_status := 'unknown_owner';
elsif p_active_ownership > 1 then
v_ownership_status := 'ambiguous';
else
v_ownership_status := 'ok';
end if;
select coalesce((p_now - h.last_seen_at) > make_interval(secs => h.down_grace_seconds), true)
into v_scheduler_down
from monitoring.scheduler_heartbeats h
where h.scheduler_owner_type = p_owner_type and h.scheduler_owner_id = p_owner_id;
select * into v_latest_obs from monitoring.v_check_observations o where o.check_id = p_check_id order by o.run_at desc limit 1;
if p_cadence_seconds is not null then
if v_latest_obs.run_at is null then
-- Never observed: wait one cadence from when the check was created, then
-- flag it missed (was: expected_next = now, i.e. 'unknown' forever).
select c.created_at into v_created from monitoring.check_config c where c.check_id = p_check_id;
v_expected_next := coalesce(v_created, p_now) + make_interval(secs => p_cadence_seconds);
else
v_expected_next := v_latest_obs.run_at + make_interval(secs => p_cadence_seconds);
end if;
else
v_expected_next := p_now;
end if;
v_window_start := v_expected_next - make_interval(secs => v_grace);
select * into v_latest_in_window from monitoring.v_check_observations o
where o.check_id = p_check_id and o.run_at >= v_window_start and o.run_at <= p_now
order by o.run_at desc limit 1;
if v_latest_in_window.run_at is not null and not v_latest_in_window.ok then
v_state := 'error';
v_state_reason := 'failed run in window';
v_latest_details := jsonb_build_object('http_status', v_latest_in_window.http_status, 'latency_ms', v_latest_in_window.latency_ms, 'error_code', v_latest_in_window.error_code);
elsif p_now > v_expected_next + make_interval(secs => v_grace) and v_latest_in_window.run_at is null then
v_state := 'missed';
v_state_reason := case when v_scheduler_down then 'no runs in window; scheduler_down=true' else 'no runs in window' end;
v_latest_details := jsonb_build_object('grace_seconds', v_grace);
elsif v_latest_obs.run_at is not null and v_latest_obs.ok then
if p_latency_budget_ms is not null and v_latest_obs.latency_ms is not null and v_latest_obs.latency_ms > p_latency_budget_ms then
v_state := 'degraded';
else
v_state := 'healthy';
end if;
v_state_reason := 'latest ok run (' || v_state::text || ')';
v_latest_details := jsonb_build_object('http_status', v_latest_obs.http_status, 'latency_ms', v_latest_obs.latency_ms);
elsif v_latest_obs.run_at is not null and not v_latest_obs.ok then
-- JEG-414: the latest run failed but sits before the next run's window;
-- a failing check must read red ('error'), never 'unknown'.
v_state := 'error';
v_state_reason := 'latest run failed';
v_latest_details := jsonb_build_object('http_status', v_latest_obs.http_status, 'latency_ms', v_latest_obs.latency_ms, 'error_code', v_latest_obs.error_code);
else
v_state := 'unknown';
v_state_reason := 'no observations yet';
v_latest_details := jsonb_build_object('grace_seconds', v_grace);
end if;
return query select v_state, v_state_reason, v_expected_next, v_latest_obs.run_at,
(select max(run_at) from monitoring.v_check_observations where check_id = p_check_id and ok),
(select max(run_at) from monitoring.v_check_observations where check_id = p_check_id and not ok),
v_ownership_status, coalesce(v_scheduler_down, false), v_latest_details;
end;
$function$;

-- Existing rows: add the pg_cron job + workflow + a short label to alert_policy
-- (merge only; severity and wording stay).
update monitoring.check_config set alert_policy = alert_policy || jsonb_build_object('pg_cron_job','trigger-fantasycalc-drift-live','workflow','fantasycalc-drift.yml','label','FantasyCalc drift vs Supabase') where check_id = 'fantasycalc_native_drift';
update monitoring.check_config set alert_policy = alert_policy || jsonb_build_object('pg_cron_job','trigger-fantasycalc-weekly-save','workflow','fantasycalc-weekly-save.yml','label','FantasyCalc weekly save') where check_id = 'fantasycalc_weekly_save';
update monitoring.check_config set alert_policy = alert_policy || jsonb_build_object('pg_cron_job','health-artifacts-live','workflow','health-artifacts.yml','label','Health artifacts producer') where check_id = 'health_artifacts_producer';
update monitoring.check_config set alert_policy = alert_policy || jsonb_build_object('pg_cron_job','health-artifacts-live','workflow','health-artifacts.yml','label','Served import-health file is fresh') where check_id = 'served_import_health_fresh';
update monitoring.check_config set alert_policy = alert_policy || jsonb_build_object('pg_cron_job','health-artifacts-live','workflow','health-artifacts.yml','label','Served pipeline-checkpoints file is fresh') where check_id = 'served_pipeline_checkpoints_fresh';
update monitoring.check_config set alert_policy = alert_policy || jsonb_build_object('pg_cron_job','trade-chart-ingest-live','workflow','trade-chart-ingest.yml','label','CBS trade-chart ingest') where check_id = 'cbs_trade_chart_ingest';
update monitoring.check_config set alert_policy = alert_policy || jsonb_build_object('pg_cron_job','trade-chart-ingest-live','workflow','trade-chart-ingest.yml','label','USA Today trade-chart ingest') where check_id = 'usatoday_trade_chart_ingest';
update monitoring.check_config set alert_policy = alert_policy || jsonb_build_object('pg_cron_job','razzball-sync-live','workflow','razzball-supabase-sync.yml','label','Razzball projections sync') where check_id = 'razzball_projections_sync';

insert into monitoring.check_config
    (check_id, check_type, cadence_seconds, grace_override_seconds,
     scheduler_owner_type, scheduler_owner_id, alert_policy)
values
  ('rebuild_chain', 'http_status_and_content', 21600, 1800, 'github_actions', 'rebuild-chain.yml',
   '{"severity":"page","label":"Comparison chain rebuild","pg_cron_job":"rebuild-chain-live","workflow":"rebuild-chain.yml","what":"rebuild-chain.yml finished green on main (every 6h at :17 via pg_cron rebuild-chain-live); a red chain run holds the fixture"}'),
  ('player_trace_rebuild', 'http_status_and_content', 21600, 1800, 'github_actions', 'player-trace-rebuild.yml',
   '{"severity":"page","label":"Player trace rebuild","pg_cron_job":"trigger-player-trace-live","workflow":"player-trace-rebuild.yml","what":"player-trace-rebuild.yml finished green on main (every 6h at :47 via pg_cron trigger-player-trace-live)"}'),
  ('espn_supabase_sync', 'http_status_and_content', 86400, 1800, 'github_actions', 'espn-supabase-sync.yml',
   '{"severity":"page","label":"ESPN scrape to Supabase","pg_cron_job":"trigger-espn-sync-live","workflow":"espn-supabase-sync.yml","what":"ESPN scrape saved to Supabase (daily 11:30 UTC via pg_cron trigger-espn-sync-live)"}'),
  ('cbsros_supabase_sync', 'http_status_and_content', 604800, 1800, 'github_actions', 'cbsros-supabase-sync.yml',
   '{"severity":"page","label":"CBS ROS scrape to Supabase","pg_cron_job":"trigger-cbsros-sync-live","workflow":"cbsros-supabase-sync.yml","what":"CBS ROS scrape saved to Supabase (Wednesdays 11:00 UTC via pg_cron trigger-cbsros-sync-live)"}'),
  ('source_vintage_check', 'http_status_and_content', 3600, 1800, 'github_actions', 'source-vintage-check.yml',
   '{"severity":"warn","label":"Source vintage check","pg_cron_job":"vintage-check-live","workflow":"source-vintage-check.yml","what":"hourly source-vintage check ran green (pg_cron vintage-check-live)"}'),
  ('live_page_synthetic', 'http_status_and_content', 86400, 1800, 'github_actions', 'live-page-synthetic.yml',
   '{"severity":"page","label":"Live page synthetic gate","pg_cron_job":"live-page-synthetic-live","workflow":"live-page-synthetic.yml","what":"rendered check of the live site passed with the expected build tag (daily 06:00 UTC via pg_cron live-page-synthetic-live)"}'),
  ('site_deploy', 'http_status_and_content', 93600, 1800, 'github_actions', 'pages.yml',
   '{"severity":"page","label":"Site deploy (Pages)","workflow":"pages.yml","what":"pages.yml deploy finished green (every push to main, plus its own 11:30 UTC schedule: GAP-GHA-SCHEDULES)"}'),
  ('weekly_dashboard_load', 'http_status_and_content', 93600, 1800, 'github_actions', 'weekly-dashboard-load.yml',
   -- NOTE: this job exits 2 every day (no staged bundle in data/weekly) until
   -- weekly production resumes, JEG-399, so it will read red. Left at page
   -- severity on purpose; downgrading it to warn is Jeremy's call.
   '{"severity":"page","label":"Weekly dashboard load to Supabase","workflow":"weekly-dashboard-load.yml","what":"weekly-dashboard-load.yml finished green (its own 16:07 UTC GitHub schedule: GAP-GHA-SCHEDULES)"}'),
  ('sleeper_identity_refresh', 'http_status_and_content', 432000, 1800, 'github_actions', 'sleeper-identity-refresh.yml',
   '{"severity":"warn","label":"Sleeper identity refresh","workflow":"sleeper-identity-refresh.yml","what":"sleeper-identity-refresh.yml finished green (Tue + Thu 09:17 UTC on its own GitHub schedule: GAP-GHA-SCHEDULES)"}'),
  ('pgcron_ops_health_checks', 'http_status_and_content', 900, null, 'pg_cron', 'jeg379-health-checks-15min',
   '{"severity":"page","label":"Row-count and duplicate checks (ops.health)","pg_cron_job":"jeg379-health-checks-15min","what":"ops.run_health_checks() ran without error every 15 minutes"}'),
  ('pgcron_gate_audit', 'http_status_and_content', 1800, null, 'pg_cron', 'gate-audit-v1',
   '{"severity":"warn","label":"Publish gate audit","pg_cron_job":"gate-audit-v1","what":"api.audit_publish_gate ran without error every 30 minutes"}'),
  ('pgcron_monitoring_evaluator', 'http_status_and_content', 300, null, 'pg_cron', 'monitoring-evaluator-5min',
   '{"severity":"page","label":"Monitoring evaluator","pg_cron_job":"monitoring-evaluator-5min","what":"monitoring.run_evaluator_cycle ran without error every 5 minutes"}'),
  ('pgcron_retention', 'http_status_and_content', 86400, 1800, 'pg_cron', 'cron-retention-30d',
   '{"severity":"warn","label":"cron history retention","pg_cron_job":"cron-retention-30d","what":"cron.job_run_details 30-day cleanup ran without error (daily 03:00 UTC)"}')
on conflict (check_id) do nothing;

-- ===========================================================================
-- Part 3. pg_cron observer (SQL-only jobs) + single summary for the monitor.
-- ===========================================================================

-- SQL-only cron jobs have no workflow to report from; their run history in
-- cron.job_run_details is the evidence. This copies it into
-- monitoring.check_observations so the same evaluator covers them. Dispatch
-- jobs are NOT mapped here: "succeeded" only means the HTTP call was queued.
create table if not exists monitoring.cron_check_map (
    check_id text primary key references monitoring.check_config(check_id),
    jobname  text not null unique
);
alter table monitoring.cron_check_map enable row level security;
insert into monitoring.cron_check_map (check_id, jobname) values
    ('pgcron_ops_health_checks',    'jeg379-health-checks-15min'),
    ('pgcron_gate_audit',           'gate-audit-v1'),
    ('pgcron_monitoring_evaluator', 'monitoring-evaluator-5min'),
    ('pgcron_retention',            'cron-retention-30d')
on conflict do nothing;

create or replace function monitoring.record_cron_observations()
 returns integer
 language plpgsql
 security definer
 set search_path to 'monitoring', 'cron', 'public', 'pg_temp'
as $function$
declare v_n integer;
begin
  insert into monitoring.check_observations (check_id, run_at, ok, error_code, source)
  select m.check_id, d.start_time, d.status = 'succeeded',
         case when d.status = 'succeeded' then null else 'cron_' || d.status end,
         'pg_cron'
  from monitoring.cron_check_map m
  join cron.job j on j.jobname = m.jobname
  join cron.job_run_details d on d.jobid = j.jobid
  where d.status in ('succeeded', 'failed')
    and d.start_time > coalesce(
          (select max(o.run_at) from monitoring.check_observations o
            where o.check_id = m.check_id and o.source = 'pg_cron'),
          now() - interval '1 hour');
  get diagnostics v_n = row_count;
  return v_n;
end;
$function$;
revoke execute on function monitoring.record_cron_observations() from public, anon, authenticated;

select cron.schedule('monitoring-cron-observer-5min', '2-59/5 * * * *',
                     $$select monitoring.record_cron_observations()$$);

-- part 4 (monitoring_coverage_4_observer_self_check): the observer is itself a
-- checked job; it records its own previous run on its next pass.
insert into monitoring.check_config
    (check_id, check_type, cadence_seconds, grace_override_seconds,
     scheduler_owner_type, scheduler_owner_id, alert_policy)
values
  ('pgcron_cron_observer', 'http_status_and_content', 300, null, 'pg_cron', 'monitoring-cron-observer-5min',
   '{"severity":"page","label":"pg_cron observer","pg_cron_job":"monitoring-cron-observer-5min","what":"monitoring.record_cron_observations ran without error every 5 minutes (it records itself on its next run)"}')
on conflict (check_id) do nothing;
insert into monitoring.cron_check_map (check_id, jobname) values
    ('pgcron_cron_observer', 'monitoring-cron-observer-5min')
on conflict do nothing;

-- Re-point the daily live-page check at the workflow. The Supabase edge
-- function it called answered 401 on every run (its bearer secret does not
-- match the function's service-role key), and the job still showed
-- "succeeded"; public.live_page_checks has never had a row.
select cron.alter_job(
    (select jobid from cron.job where jobname = 'live-page-synthetic-live'),
    command := $$SELECT public.dispatch_gha_workflow('live-page-synthetic.yml', '{}'::jsonb)$$);

-- Single read contract for the served monitor (service_role only; the CI
-- producer snapshots it into modules/monitoring-summary.json).
create or replace function public.monitoring_summary()
 returns jsonb
 language plpgsql
 stable
 security definer
 set search_path to 'monitoring', 'public', 'cron', 'pg_temp'
as $function$
declare
  v_now        timestamptz := now();
  v_checks     jsonb;
  v_dispatch   jsonb;
  v_eval_last  timestamptz;
  v_eval_stale boolean;
  v_red        integer;
  v_yellow     integer;
  v_green      integer;
  v_total      integer;
  v_dispatch_failed integer;
  v_overall    text;
  v_headline   text;
begin
  select max(updated_at) into v_eval_last from monitoring.check_heartbeats;
  v_eval_stale := v_eval_last is null or v_eval_last < v_now - interval '15 minutes';

  select coalesce(jsonb_agg(row_to_json(t)::jsonb order by
           case t.status when 'red' then 0 when 'yellow' then 1 else 2 end, t.check_id), '[]'::jsonb)
    into v_checks
  from (
    select c.check_id,
           coalesce(c.alert_policy->>'label', c.check_id) as label,
           c.alert_policy->>'what' as what,
           coalesce(c.alert_policy->>'severity', 'warn') as severity,
           c.scheduler_owner_type::text as owner_type,
           c.scheduler_owner_id as owner_id,
           c.alert_policy->>'pg_cron_job' as pg_cron_job,
           c.alert_policy->>'workflow' as workflow,
           c.cadence_seconds,
           coalesce(h.state::text, 'unknown') as state,
           h.state_since, h.last_run_at, h.last_ok_at, h.last_error_at, h.expected_next_run_at,
           o.run_at as obs_run_at, o.ok as obs_ok, o.error_code as obs_error_code,
           case
             when not c.enabled then 'off'
             when h.state = 'healthy' then 'green'
             when h.state = 'degraded' then 'yellow'
             when h.state in ('error', 'missed') and coalesce(c.alert_policy->>'severity', 'warn') = 'page' then 'red'
             when h.state in ('error', 'missed') then 'yellow'
             else 'yellow'
           end as status,
           case
             when not c.enabled then 'disabled'
             when h.state is null or h.state = 'unknown' then 'waiting for the first recorded run'
             when h.state = 'healthy' then 'last run ok'
             when h.state = 'degraded' then 'last run ok but slow'
             when h.state = 'error' then 'last run failed' || coalesce(' (' || o.error_code || ')', '')
             when h.state = 'missed' then 'no run recorded since ' || to_char(coalesce(h.last_run_at, c.created_at) at time zone 'UTC', 'YYYY-MM-DD HH24:MI "UTC"')
             else h.state::text
           end as reason
    from monitoring.check_config c
    left join monitoring.check_heartbeats h on h.check_id = c.check_id
    left join lateral (
      select x.run_at, x.ok, x.error_code
      from monitoring.v_check_observations x
      where x.check_id = c.check_id
      order by x.run_at desc limit 1
    ) o on true
  ) t;

  select coalesce(jsonb_agg(row_to_json(d)::jsonb order by d.jobname), '[]'::jsonb)
    into v_dispatch
  from (
    select j.jobname, j.schedule, j.active,
           lr.status as last_status, lr.start_time as last_start,
           wf.workflow_file as dispatches,
           dl.outcome as dispatch_outcome, dl.status_code as dispatch_http_status,
           dl.detail as dispatch_detail, dl.dispatched_at as dispatched_at,
           case
             when lr.status = 'failed' then 'red'
             when dl.outcome = 'failed' then 'red'
             when not j.active then 'yellow'
             else 'green'
           end as status
    from cron.job j
    left join lateral (
      select r.status, r.start_time from cron.job_run_details r
      where r.jobid = j.jobid and r.status in ('succeeded', 'failed')
      order by r.start_time desc limit 1
    ) lr on true
    left join lateral (
      select coalesce(
               substring(j.command from 'dispatch_gha_workflow\(''([^'']+)'''),
               case when j.command like '%dispatch_vintage_check%' then 'source-vintage-check.yml' end
             ) as workflow_file
    ) wf on true
    left join lateral (
      select v.outcome, v.status_code, v.detail, v.dispatched_at
      from monitoring.v_dispatch_outcomes v
      where v.workflow_file = wf.workflow_file and v.outcome <> 'pending_or_expired'
      order by v.dispatched_at desc limit 1
    ) dl on true
  ) d;

  select count(*) filter (where e->>'status' = 'red'),
         count(*) filter (where e->>'status' = 'yellow'),
         count(*) filter (where e->>'status' = 'green'),
         count(*) filter (where e->>'status' <> 'off')
    into v_red, v_yellow, v_green, v_total
  from jsonb_array_elements(v_checks) e;

  select count(*) into v_dispatch_failed
  from jsonb_array_elements(v_dispatch) e where e->>'status' = 'red';

  v_overall := case
    when v_eval_stale or v_red > 0 or v_dispatch_failed > 0 then 'red'
    when v_yellow > 0 then 'yellow'
    else 'green'
  end;
  v_headline := case
    when v_eval_stale then 'Monitor evaluator has not run since ' || coalesce(to_char(v_eval_last at time zone 'UTC', 'YYYY-MM-DD HH24:MI "UTC"'), 'ever') || ': treat everything as unknown'
    when v_overall = 'green' then 'Everything is working: ' || v_total || ' of ' || v_total || ' checks passing'
    else (v_red + v_dispatch_failed) || ' failing, ' || v_yellow || ' need attention, ' || v_green || ' of ' || v_total || ' checks passing'
  end;

  return jsonb_build_object(
    'schema', 'ddf-monitoring-summary-v1',
    'generated_at', v_now,
    'overall', v_overall,
    'headline', v_headline,
    'evaluator_last_run', v_eval_last,
    'evaluator_stale', v_eval_stale,
    'counts', jsonb_build_object('total', v_total, 'green', v_green, 'yellow', v_yellow, 'red', v_red, 'dispatch_failed', v_dispatch_failed),
    'checks', v_checks,
    'cron_jobs', v_dispatch
  );
end;
$function$;
revoke execute on function public.monitoring_summary() from public, anon, authenticated;
grant execute on function public.monitoring_summary() to service_role;
