-- JEG-480: data fidelity pulse history, monitored check and schedule.
-- Additive only (approved 2026-10-08). Idempotent.
--
-- History reuses the existing fidelity tables (written once by an ECR exact-
-- match check on 2026-10-04, no writer since): one public.fidelity_runs row
-- per source per pulse run (check_name = 'fidelity_pulse'), and up to 200
-- public.fidelity_divergences rows per source per run (per player and column:
-- value_mismatch / missing / extra / outside_universe / list_churn).
-- Writer: .github/workflows/fidelity-pulse.yml (service key, RLS bypass).

begin;

alter table public.fidelity_runs
    add column if not exists check_name text,
    add column if not exists source text,
    add column if not exists status text,
    add column if not exists pulse_id uuid;

alter table public.fidelity_divergences
    add column if not exists source text,
    add column if not exists stage text,
    add column if not exists player_key bigint;

create index if not exists fidelity_runs_pulse_source_idx
    on public.fidelity_runs (check_name, source, finished_at desc);
create index if not exists fidelity_divergences_run_idx
    on public.fidelity_divergences (run_id);

-- Latest pulse row per source, and drift over time (one row per run).
create or replace view public.fidelity_pulse_latest
with (security_invoker = true) as
select distinct on (source)
       source, status, season, week, n_compared, n_diverged, n_blocked, checks, finished_at, run_id, pulse_id
  from public.fidelity_runs
 where check_name = 'fidelity_pulse'
 order by source, finished_at desc;

create or replace view public.fidelity_pulse_history
with (security_invoker = true) as
select r.finished_at, r.source, r.status, r.week, r.n_compared, r.n_diverged,
       count(d.id) filter (where d.divergence_type = 'value_mismatch') as n_value_mismatch,
       count(d.id) filter (where d.divergence_type in ('missing', 'extra')) as n_missing_or_extra,
       count(d.id) filter (where d.divergence_type = 'outside_universe') as n_outside_universe,
       r.run_id, r.pulse_id
  from public.fidelity_runs r
  left join public.fidelity_divergences d on d.run_id = r.run_id
 where r.check_name = 'fidelity_pulse'
 group by r.run_id;

revoke all on public.fidelity_pulse_latest, public.fidelity_pulse_history from anon, authenticated;

-- Monitored check: the pulse ran (red sources are still a successful run).
insert into monitoring.check_config
    (check_id, check_type, cadence_seconds, grace_override_seconds,
     scheduler_owner_type, scheduler_owner_id, alert_policy)
values
    ('fidelity_pulse', 'http_status_and_content', 10800, 3600, 'github_actions', 'fidelity-pulse.yml',
     '{"severity": "warn", "label": "Data fidelity pulse", "pg_cron_job": "fidelity-pulse-live", "workflow": "fidelity-pulse.yml", "what": "fidelity-pulse.yml compared publisher pages, Supabase and the live chart (every 3 h via pg_cron fidelity-pulse-live, and after every rebuild-chain run)"}')
on conflict (check_id) do update set
    cadence_seconds = excluded.cadence_seconds,
    grace_override_seconds = excluded.grace_override_seconds,
    scheduler_owner_id = excluded.scheduler_owner_id,
    alert_policy = excluded.alert_policy,
    updated_at = now();

-- Schedule: every 3 h at :40 UTC (clear of the :35 trade-chart probes and the
-- :50 health-artifacts run). cron.schedule upserts by name.
select cron.schedule('fidelity-pulse-live', '40 */3 * * *',
  $$SELECT public.dispatch_gha_workflow('fidelity-pulse.yml', '{}'::jsonb)$$);

commit;

-- Verify after applying:
--   select jobname, schedule, active from cron.job where jobname = 'fidelity-pulse-live';
--   select * from public.fidelity_pulse_latest;
