-- JEG-414 follow-up: move CI ops artifacts off main branch.
--
-- Context: health-artifacts.yml ran ~2x/hour and committed three files to
-- main (source-import-health.json, pipeline-checkpoints.json,
-- monitoring-summary.json), causing 48+ bot commits/day, Pages deploy
-- cancellations, and rebase failures in the rebuild chain.
--
-- Fix: store the artifacts here instead. The monitor dashboard reads
-- them via the anon REST API.
--
-- (a) public.ops_artifacts: key/value store for CI-produced JSON blobs.
--     Used for pipeline-checkpoints, source-import-health, and the JEG-205
--     code-hash state that previously lived in .github/source-vintage-state.json.
-- (b) Grant SELECT on public.ops_artifacts to anon so the browser can read
--     pipeline-checkpoints and source-import-health directly.
-- (c) Grant EXECUTE on public.monitoring_summary() to anon so the browser
--     can call it directly (the function is SECURITY DEFINER and read-only;
--     granting anon is safe).
--
-- Additive only. No existing tables or functions are altered.

begin;

-- (a) -----------------------------------------------------------------------

create table if not exists public.ops_artifacts (
    name        text        primary key,   -- e.g. 'pipeline-checkpoints'
    payload     jsonb       not null,
    produced_at timestamptz not null default now()
);

comment on table public.ops_artifacts is
  'CI-produced JSON blobs previously committed to main. Written by health-artifacts.yml '
  'and source-vintage-check.yml via service_role; read by the monitor dashboard via anon.';

-- Row-level security: anon can SELECT; only service_role can INSERT/UPDATE/DELETE.
alter table public.ops_artifacts enable row level security;

do $$ begin
  if not exists (
    select 1 from pg_policies
    where tablename = 'ops_artifacts' and policyname = 'anon_select'
  ) then
    create policy anon_select on public.ops_artifacts
      for select to anon using (true);
  end if;
end $$;

do $$ begin
  if not exists (
    select 1 from pg_policies
    where tablename = 'ops_artifacts' and policyname = 'service_write'
  ) then
    create policy service_write on public.ops_artifacts
      for all to service_role using (true) with check (true);
  end if;
end $$;

-- (b) -----------------------------------------------------------------------

grant select on public.ops_artifacts to anon;
grant select on public.ops_artifacts to authenticated;

-- (c) -----------------------------------------------------------------------
-- monitoring_summary() is SECURITY DEFINER and only reads monitoring.*,
-- cron.*, and public.*. Granting anon lets the browser call it directly
-- without needing a server-side snapshot committed to main.

grant execute on function public.monitoring_summary() to anon;

commit;
