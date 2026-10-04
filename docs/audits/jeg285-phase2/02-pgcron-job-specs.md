# JEG-285 Phase 2 — pg_cron Job Specifications

Draft SQL for each scheduling migration. All jobs run in `SHADOW` mode first
(see `01-migration-tracker.md`). Nothing here is live until Jeremy approves
the cutover per the tracker gates.

## Three separate concerns — keep them separate

This doc, Job 1's shadow spec, and the JEG-322 work each touch a
distinct observation surface. Conflating them produces false-green
checks like the one JEG-323 names. The three concerns are:

1. **Source content freshness / health** — *what does the upstream
   page or feed currently look like?* Owner: `pipelines/verify_import_health.py`
   (import-health gate, `make import-health`). Lives in the seven
   pipeline source tables (`source_trade_values`,
   `espn_season_projections`, `cbs_trade_values`, `cbs_ros_projections`,
   `razzball_projections`, etc.) plus
   `data/fixtures/current/comparison-sources-data.json`. Cron: GHA
   `import-health.yml`. This is the only one of the three with a
   working repo definition today.

2. **Source-vintage change detection** — *did the source content move
   relative to the last time we dispatched a rebuild?* Owner: the
   in-flight JEG-285 Job 1, replicating
   `pipelines/check_source_vintage.py`. Backed by the planned
   `public.pipeline_cron_state` table and the new
   `public.check_source_vintages()` plpgsql function (see Job 1
   spec). Reads only the same pipeline source tables plus the state
   table. Cron: this migration's `vintage-check-shadow` (hourly),
   cutover `vintage-check`.

3. **Code-change detection (pipelines/ hash, JEG-205 path)** — *did
   the pipeline scripts that produce the fixtures change since the
   last dispatched hash?* Owner: `pipelines/check_source_vintage.py:check_code_change`
   and `.github/source-vintage-state.json`. **This stays
   GitHub-side.** It is NOT moved to pg_cron; the JEG-285 Job 1 SQL
   always emits `code_changed=false` and `code_hash=null` because
   pg_cron cannot observe the repo's filesystem. Treat the GHA
   `source-vintage-check.yml` run as the only source of truth for the
   code-hash decision.

Any future doc, runbook, or alert that needs one of these MUST cite
the matching concern above. Mixing them is the failure mode JEG-323
was created to surface.

> **JEG-323 — repo-side warning.** The function named
> `public.check_source_vintages()` is currently a **console-only stub in
> production Supabase** (returns the hard-coded `{"changed": false, "note":
> "stub"}`) and has **no definition in this repo**. There is no
> `CREATE FUNCTION check_source_vintages` body anywhere under
> `sql/migrations/` or `sql/contract/` (verified by grep and by the
> JEG-323 regression test
> `tests/test_health_function_no_hardcoded_green.py`, which scans both
> directories). It MUST NOT be cited as a working check in any docs,
> runbooks, or shadow comparisons. The JEG-323 ticket tracks its
> revoke; until that work lands, treat the function as a non-existent
> health surface. When this spec's implementation phase adds the real
> function body, the new body MUST read at least one table (FROM or
> JOIN) so the same regression guard stays green.

## Prerequisites (run once, before any job)

```sql
-- Enable pg_cron (Supabase Dashboard: Integrations -> Cron, or SQL)
create extension pg_cron with schema pg_catalog;
grant usage on schema cron to postgres;
grant all privileges on all tables in schema cron to postgres;

-- Enable pg_net for Action dispatch
create extension pg_net with schema extensions;

-- Retention: job_run_details is NEVER auto-cleaned. Keep 30 days.
select cron.schedule(
  'cron-retention-30d',
  '0 3 * * *',
  $$delete from cron.job_run_details where start_time < now() - interval '30 days'$$
);
```

Store the GitHub dispatch credentials as Postgres settings (not in job bodies):
```sql
alter database postgres set app.github_repo = 'JB-barrel-droid/fantasy-tools';
-- app.github_token set via Supabase Vault; read with
-- select decrypted_secret from vault.decrypted_secrets where name = 'github_dispatch_token';
```

## Dispatch helper (one function, reused by all jobs)

```sql
create or replace function dispatch_gha_workflow(workflow_file text, inputs jsonb default '{}')
returns bigint language plpgsql security definer as $$
declare
  req_id bigint;
  repo text := current_setting('app.github_repo');
  token text := (select decrypted_secret from vault.decrypted_secrets
                 where name = 'github_dispatch_token');
begin
  select net.http_post(
    url := format('https://api.github.com/repos/%s/actions/workflows/%s/dispatches', repo, workflow_file),
    headers := jsonb_build_object(
      'Authorization', 'Bearer ' || token,
      'Accept', 'application/vnd.github+json',
      'Content-Type', 'application/json'),
    body := jsonb_build_object('ref', 'main', 'inputs', inputs)
  ) into req_id;
  return req_id;
end $$;
```

## Job 1: source-vintage-check (hourly) — the B7 fix

Replaces `.github/workflows/source-vintage-check.yml` cron. The vintage
comparison moves into SQL; on change it dispatches the rebuild chain.

```sql
-- Shadow: log the decision without dispatching
select cron.schedule(
  'vintage-check-shadow',
  '0 * * * *',
  $$
  insert into pipeline_cron_log (job_name, checked_at, decision)
  select 'vintage-check-shadow', now(),
         check_source_vintages();  -- returns jsonb {changed: bool, ...}
  $$
);
-- Cutover: dispatch on change
-- select cron.schedule(
--   'vintage-check',
--   '0 * * * *',
--   $$
--   select case when (check_source_vintages()->>'changed')::bool
--     then dispatch_gha_workflow('rebuild-chain.yml',
--            jsonb_build_object('source', 'pg-cron-vintage-check'))
--     else null end;
--   $$
-- );
```

Note: `check_source_vintages()` is a plpgsql function to be written in the
implementation phase. It replicates `pipelines/check_source_vintage.py`:
compare each source's latest Supabase vintage against the last-dispatched
vintage stored in a `pipeline_cron_state` table.

> **JEG-323 — repo-side warning.** The function named
> `public.check_source_vintages()` is currently a **console-only stub in
> production Supabase** (returns the hard-coded `{"changed": false, "note":
> "stub"}`) and has **no definition in this repo**. There is no
> `CREATE FUNCTION check_source_vintages` body anywhere under
> `sql/migrations/` or `sql/contract/` (verified by grep and by the
> JEG-323 regression test
> `tests/test_health_function_no_hardcoded_green.py`, which scans both
> directories). It MUST NOT be cited as a working check in any docs,
> runbooks, or shadow comparisons. The JEG-323 ticket tracks its
> revoke; until that work lands, treat the function as a non-existent
> health surface. When this spec's implementation phase adds the real
> function body, the new body MUST read at least one table (FROM or
> JOIN) so the same regression guard stays green.

## Jobs 2–6: Action triggers (dispatch-only)

These replace the GHA cron schedules. The compute stays on Actions; pg_cron
only fires the dispatch. All follow the same pattern — shadow first.

```sql
-- rebuild-chain: every 6h at :17 (matches '17 */6 * * *')
select cron.schedule('trigger-rebuild-chain-shadow', '17 */6 * * *',
  $$select log_dispatch_intent('rebuild-chain.yml')$$);

-- player-trace-rebuild: every 6h at :47 (matches '47 */6 * * *')
select cron.schedule('trigger-player-trace-shadow', '47 */6 * * *',
  $$select log_dispatch_intent('player-trace-rebuild.yml')$$);

-- espn-supabase-sync: daily 11:30 UTC (matches '30 11 * * *')
select cron.schedule('trigger-espn-sync-shadow', '30 11 * * *',
  $$select log_dispatch_intent('espn-supabase-sync.yml')$$);

-- cbsros-supabase-sync: weekly Wed 11:00 UTC (matches '0 11 * * 3')
select cron.schedule('trigger-cbsros-sync-shadow', '0 11 * * 3',
  $$select log_dispatch_intent('cbsros-supabase-sync.yml')$$);

-- fantasycalc-drift: daily 11:45 UTC (matches '45 11 * * *')
select cron.schedule('trigger-fcalc-drift-shadow', '45 11 * * *',
  $$select log_dispatch_intent('fantasycalc-drift.yml')$$);
```

`log_dispatch_intent()` writes to `pipeline_cron_log` without dispatching.
Cutover swaps it for `dispatch_gha_workflow(...)` per the tracker gates.

## Job 7: live-page-synthetic (daily) — full Edge Function move

No Action involved. pg_cron calls the Edge Function directly.

```sql
select cron.schedule(
  'live-page-synthetic',
  '0 6 * * *',
  $$
  select net.http_post(
    url := 'https://<project-ref>.supabase.co/functions/v1/live-page-synthetic',
    headers := jsonb_build_object(
      'Authorization', 'Bearer ' || (select decrypted_secret
        from vault.decrypted_secrets where name = 'edge_function_secret'),
      'Content-Type', 'application/json'),
    body := jsonb_build_object('url',
      'https://jb-barrel-droid.github.io/fantasy-tools/')
  );
  $$
);
```

The Edge Function (TypeScript, to be written) fetches the page, extracts the
build tag, compares against HEAD~1, and writes the verdict to a
`live_page_checks` table. Budget: well under the 2s CPU cap (one fetch +
string parse).

## Monitoring

```sql
-- Recent runs, most recent first
select jobname, status, start_time, end_time
from cron.job_run_details
join cron.job using (jobid)
order by start_time desc limit 20;

-- Dispatch log (shadow + live)
select * from pipeline_cron_log order by checked_at desc limit 20;
```

## Tables to create (implementation phase)

- `pipeline_cron_log (job_name text, checked_at timestamptz, decision jsonb)`
- `pipeline_cron_state (key text primary key, value jsonb, updated_at timestamptz)`
- `live_page_checks (checked_at timestamptz, build_tag text, verdict text, detail jsonb)`
