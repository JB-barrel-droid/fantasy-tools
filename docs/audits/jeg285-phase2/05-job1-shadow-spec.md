# JEG-285 Phase 2 — Job-1 (`source-vintage-check`) Shadow Spec

**Migration tracker item:** #1 — `source-vintage-check` (hourly) → pg_cron
**Author lane:** minimax (M3)
**Branch:** `minimax/jeg-285-job1-shadow`
**Status:** SHADOW, review-ready — **not live**. Nothing here runs until cutover.
**Ground truth for the dispatch decision:**
`pipelines/check_source_vintage.py` (the Python the GHA cron currently invokes).

## Scope of what is written

- DDL for `pipeline_cron_log` (shadow decision log) and `pipeline_cron_state`
  (last-dispatched vintages), with column comments.
- `check_source_vintages()` plpgsql function body — one source mapping per
  line of `pipelines/check_source_vintage.py:26` (CHAIN_SOURCES),
  `99-160` (per-source query construction), and `77-91` (`_derive_db_vintage`).
- Shadow `cron.schedule('vintage-check-shadow', ...)` call — hourly, logs the
  decision, never dispatches the chain.
- The 72h shadow-comparison query — joins shadow decisions against the GHA
  workflow's actual dispatches and flags any disagreement; this is what the
  tracker gate is evaluated with.
- Decision-parity walkthroughs (two scenarios) showing the Python script and
  the SQL function emit the same verdict for the same inputs.
- Fail-closed confirmation: the shadow path contains no branch which
  dispatches the chain under any input.
- Open questions for Jeremy — anything that could not be decided from the
  repo alone.

## Out of scope (this doc)

- Cutover SQL. The cutover branch in
  `docs/audits/jeg285-phase2/02-pgcron-job-specs.md:54-65` is shown as a
  commented-out template only. Cutover requires his approval and a fresh
  tracker-row update.
- Jobs 2–7 from the migration tracker. They follow the same dispatch-helper
  pattern but are not this job.
- The `gha_dispatch_log` table the 72h comparison query reads from. Its
  write-path is not this commit either; see open question Q2.
- The JEG-205 pipeline-code-hash stamp (`check_code_change()`,
  `pipelines/check_source_vintage.py:206-232`). The Python script emits
  `code_changed` alongside the per-source decision; this spec does NOT
  replicate that field in the SQL function. **Tracked in §6 Q6.**

---

## 1. DDL

### 1.1 `pipeline_cron_log` — shadow decision log

```sql
-- One row per shadow tick. Read by the 72h comparison query and by humans
-- investigating a disagreement. NEVER read by the cutover job.
create table if not exists public.pipeline_cron_log (
  -- Identifier of the cron.jobname that produced this row. For job #1 the
  -- value is always 'vintage-check-shadow'. Kept as text so future jobs
  -- (#2-7) can share the table without a schema migration.
  job_name   text        not null,

  -- Wall-clock time the shadow function completed (not when pg_cron woke
  -- the job — those can diverge if the worker is busy). timestamptz so
  -- the 72h comparison window can use `now() - interval '72 hours'`.
  checked_at timestamptz not null default now(),

  -- Full decision payload produced by check_source_vintages():
  --   {
  --     "changed": bool,
  --     "sources": {
  --       "<source>": {
  --         "current_vintage": text|null,
  --         "last_vintage":    text|null,
  --         "changed":         bool,
  --         "error":           text|null    -- present iff fail-closed
  --       }, ...
  --     }
  --   }
  -- jsonb (not json) so the comparison query can index into it without
  -- re-parsing.
  decision   jsonb       not null
);

comment on table  public.pipeline_cron_log
  is 'Shadow decision log for migration tracker items #1-7. SHADOW ONLY — never read by an authoritative path.';
comment on column public.pipeline_cron_log.job_name   is 'cron.jobname (e.g. vintage-check-shadow).';
comment on column public.pipeline_cron_log.checked_at is 'Shadow function completion time (timestamptz).';
comment on column public.pipeline_cron_log.decision   is 'Full check_source_vintages() payload: {changed, sources: {...}}.';

-- Comparison query scans the last 72h by (job_name, checked_at desc).
create index if not exists pipeline_cron_log_job_checked_idx
  on public.pipeline_cron_log (job_name, checked_at desc);
```

### 1.2 `pipeline_cron_state` — last-dispatched vintages

This is the table the existing 02-spec note refers to
(`docs/audits/jeg285-phase2/02-pgcron-job-specs.md:67-71`): one row per
chain source, holding the DB vintage at the time of the last dispatch
decision. The shadow function reads this to determine whether the current
DB vintage differs from the last-dispatched vintage.

```sql
create table if not exists public.pipeline_cron_state (
  -- Chain-source key. The 7 valid values are CHAIN_SOURCES in
  -- pipelines/check_source_vintage.py:18.
  --   ('fantasycalc', 'usatoday', 'fantasypros', 'espn',
  --    'cbs', 'cbsros', 'razzball')
  -- Enforced as text + check rather than enum so the table can be reused
  -- by future jobs (see open question Q3 about reusing this table for #2-7).
  source         text        primary key
                   check (source in ('fantasycalc','usatoday','fantasypros',
                                     'espn','cbs','cbsros','razzball')),

  -- DB vintage string observed at the time of the last dispatch decision.
  -- Same string format as check_source_vintage.get_current_vintage() returns
  -- — either an ISO date ('2026-09-30') or 'Week N' (e.g. 'Week 4'). Null
  -- until the first dispatch decision lands for this source.
  last_vintage   text,

  -- Wall-clock of the last dispatch decision. Null until first dispatch.
  -- The shadow job does NOT update this column — only the cutover job does,
  -- and only when it calls dispatch_gha_workflow(). See open question Q1.
  updated_at     timestamptz
);

comment on table  public.pipeline_cron_state
  is 'Last-dispatched DB vintage per chain source. Updated by the CUTOVER job, not by the shadow job.';
comment on column public.pipeline_cron_state.source
  is 'One of CHAIN_SOURCES from pipelines/check_source_vintage.py:18.';
comment on column public.pipeline_cron_state.last_vintage
  is 'DB vintage string from check_source_vintages() at dispatch time. Same format as the Python get_current_vintage() return.';
comment on column public.pipeline_cron_state.updated_at
  is 'Dispatch decision time. Null until first dispatch.';

-- Seed all 7 chain sources with null last_vintage so the shadow function
-- never has to handle "row missing" as a separate branch.
insert into public.pipeline_cron_state (source, last_vintage, updated_at)
values
  ('fantasycalc',  null, null),
  ('usatoday',     null, null),
  ('fantasypros',  null, null),
  ('espn',         null, null),
  ('cbs',          null, null),
  ('cbsros',       null, null),
  ('razzball',     null, null)
on conflict (source) do nothing;
```

---

## 2. `check_source_vintages()` plpgsql function

The function maps every source's Python vintage comparison
(`pipelines/check_source_vintage.py:99-160`) to SQL and returns the same
JSON shape `check_all_sources()` produces
(`pipelines/check_source_vintage.py:248-280`).

```sql
create or replace function public.check_source_vintages()
returns jsonb
language plpgsql
stable                              -- read-only; safe to call from anywhere
security definer                    -- reads public.* tables as the owner
as $$
declare
  v_source       text;
  v_result       jsonb;
  v_sources      jsonb := '{}'::jsonb;
  v_any_changed  boolean := false;

  -- per-source scratch
  v_rows         jsonb;
  v_current      text;
  v_last         text;
  v_changed      boolean;
  v_err          text;
  v_dates        text[];
  v_weeks        text[];
begin
  -----------------------------------------------------------------------
  -- fantasycalc / usatoday / fantasypros / cbs
  -- All four use public.source_trade_values with
  --   source=eq.<x>&variant=eq.as_published
  -- then scope to the latest week, then the latest bake.
  -- Maps to pipelines/check_source_vintage.py:103-114 (fantasycalc/usatoday/
  -- fantasypros) and :138-145 (cbs).
  -----------------------------------------------------------------------
  foreach v_source in array array['fantasycalc','usatoday','fantasypros','cbs'] loop
    v_err := null;
    v_current := null;
    begin
      -- 1. Fetch + filter to source/variant. Fail closed on zero rows
      --    (mirrors :108-109 and :141-142).
      select coalesce(jsonb_agg(r), '[]'::jsonb) into v_rows
      from public.source_trade_values r
      where r.source = v_source and r.variant = 'as_published';

      if jsonb_array_length(v_rows) = 0 then
        raise exception 'Fail closed: source % returned zero rows', v_source;
      end if;

      -- 2. Scope to the latest week. Mixed weeks fail closed (:78-92).
      v_weeks := (
        select array_agg(w order by w)
        from (
          select distinct (r->>'week') as w
          from jsonb_array_elements(v_rows) as r
          where r->>'week' is not null
        ) s
      );
      v_weeks := array(select x from unnest(v_weeks) as x where x is not null);

      if array_length(v_weeks, 1) > 1 then
        raise exception 'Fail closed: mixed week values %', v_weeks;
      end if;

      v_rows := (
        select coalesce(jsonb_agg(r), '[]'::jsonb)
        from jsonb_array_elements(v_rows) as r
        where r->>'week' = v_weeks[1]
      );

      -- 3. Scope to the latest bake within that week (:62-69).
      --    "Latest" = max(created_at) per bake_id; tiebreak by bake_id desc.
      v_rows := (
        with parsed as (
          select
            (r->>'bake_id')    as bake_id,
            (r->>'created_at') as created_at
          from jsonb_array_elements(v_rows) as r
        ),
        best as (
          select bake_id
          from parsed
          group by bake_id
          order by max(created_at) desc, bake_id desc
          limit 1
        )
        select coalesce(jsonb_agg(r), '[]'::jsonb)
        from jsonb_array_elements(v_rows) as r
        where (r->>'bake_id') = (select bake_id from best)
      );

      -- 5. Derive vintage — for non-espn sources, _derive_db_vintage uses
      --    `source_content_date` first, then `week` (:78-92).
      v_dates := (
        select array_agg(d order by d)
        from (
          select distinct (r->>'source_content_date') as d
          from jsonb_array_elements(v_rows) as r
          where r->>'source_content_date' is not null
        ) s
      );
      v_dates := array(select x from unnest(v_dates) as x where x is not null);

      if array_length(v_dates, 1) > 1 then
        raise exception 'Fail closed: mixed source_content_date values %', v_dates;
      end if;

      if v_dates is not null and array_length(v_dates, 1) = 1 then
        v_current := v_dates[1];
      elsif v_weeks[1] is not null then
        v_current := 'Week ' || v_weeks[1];
      else
        raise exception 'Fail closed: vintage undeterminable for %', v_source;
      end if;
    exception when others then
      v_err := sqlerrm;
    end;

    -- Compare against last-dispatched vintage.
    select last_vintage into v_last
      from public.pipeline_cron_state where source = v_source;
    v_changed := (v_current is distinct from v_last);
    if v_err is not null then
      v_changed := true;     -- fail-closed: any error in this source => changed
      v_current := null;
    end if;
    if v_changed then v_any_changed := true; end if;

    v_sources := v_sources || jsonb_build_object(
      v_source,
      jsonb_build_object(
        'current_vintage', v_current,
        'last_vintage',    v_last,
        'changed',         v_changed,
        'error',           v_err
      )
    );
  end loop;

  -----------------------------------------------------------------------
  -- espn
  -- public.espn_season_projections, latest espn_snapshot_date.
  -- Maps to pipelines/check_source_vintage.py:117-120.
  -----------------------------------------------------------------------
  v_source := 'espn';
  v_err := null; v_current := null;
  begin
    select coalesce(jsonb_agg(r), '[]'::jsonb) into v_rows
    from public.espn_season_projections r;

    if jsonb_array_length(v_rows) = 0 then
      raise exception 'Fail closed: source espn returned zero rows';
    end if;

    -- :71-75 — sort unique snapshot dates desc, take latest.
    v_dates := (
      select array_agg(d order by d desc)
      from (
        select distinct (r->>'espn_snapshot_date') as d
        from jsonb_array_elements(v_rows) as r
        where r->>'espn_snapshot_date' is not null
      ) s
    );
    v_dates := array(select x from unnest(v_dates) as x where x is not null);

    if array_length(v_dates, 1) > 1 then
      raise exception 'Fail closed: mixed espn_snapshot_date values %', v_dates;
    end if;

    v_rows := (
      select coalesce(jsonb_agg(r), '[]'::jsonb)
      from jsonb_array_elements(v_rows) as r
      where r->>'espn_snapshot_date' = v_dates[1]
    );

    -- _derive_db_vintage for espn (:77-91): use espn_snapshot_date, else week.
    v_weeks := (
      select array_agg(w order by w)
      from (
        select distinct (r->>'week') as w
        from jsonb_array_elements(v_rows) as r
        where r->>'week' is not null
      ) s
    );
    v_weeks := array(select x from unnest(v_weeks) as x where x is not null);

    if array_length(v_weeks, 1) > 1 then
      raise exception 'Fail closed: mixed week values %', v_weeks;
    end if;

    if v_dates[1] is not null then
      v_current := v_dates[1];
    elsif v_weeks[1] is not null then
      v_current := 'Week ' || v_weeks[1];
    else
      raise exception 'Fail closed: vintage undeterminable for espn';
    end if;
  exception when others then
    v_err := sqlerrm;
  end;

  select last_vintage into v_last
    from public.pipeline_cron_state where source = 'espn';
  v_changed := (v_current is distinct from v_last);
  if v_err is not null then v_changed := true; v_current := null; end if;
  if v_changed then v_any_changed := true; end if;
  v_sources := v_sources || jsonb_build_object(
    'espn',
    jsonb_build_object(
      'current_vintage', v_current,
      'last_vintage',    v_last,
      'changed',         v_changed,
      'error',           v_err
    )
  );

  -----------------------------------------------------------------------
  -- cbsros
  -- public.cbs_ros_projections, latest cbs_snapshot_date.
  -- Maps to pipelines/check_source_vintage.py:147-151.
  -----------------------------------------------------------------------
  v_source := 'cbsros';
  v_err := null; v_current := null;
  begin
    select coalesce(jsonb_agg(r), '[]'::jsonb) into v_rows
    from public.cbs_ros_projections r;

    if jsonb_array_length(v_rows) = 0 then
      raise exception 'Fail closed: source cbsros returned zero rows';
    end if;

    v_dates := (
      select array_agg(d order by d desc)
      from (
        select distinct (r->>'cbs_snapshot_date') as d
        from jsonb_array_elements(v_rows) as r
        where r->>'cbs_snapshot_date' is not null
      ) s
    );
    v_dates := array(select x from unnest(v_dates) as x where x is not null);

    if array_length(v_dates, 1) > 1 then
      raise exception 'Fail closed: mixed cbs_snapshot_date values %', v_dates;
    end if;

    v_rows := (
      select coalesce(jsonb_agg(r), '[]'::jsonb)
      from jsonb_array_elements(v_rows) as r
      where r->>'cbs_snapshot_date' = v_dates[1]
    );

    -- _derive_db_vintage: cbsros uses source_content_date first, else week.
    v_dates := (
      select array_agg(d order by d)
      from (
        select distinct (r->>'source_content_date') as d
        from jsonb_array_elements(v_rows) as r
        where r->>'source_content_date' is not null
      ) s
    );
    v_dates := array(select x from unnest(v_dates) as x where x is not null);

    if array_length(v_dates, 1) > 1 then
      raise exception 'Fail closed: mixed source_content_date values %', v_dates;
    end if;

    v_weeks := (
      select array_agg(w order by w)
      from (
        select distinct (r->>'week') as w
        from jsonb_array_elements(v_rows) as r
        where r->>'week' is not null
      ) s
    );
    v_weeks := array(select x from unnest(v_weeks) as x where x is not null);

    if array_length(v_weeks, 1) > 1 then
      raise exception 'Fail closed: mixed week values %', v_weeks;
    end if;

    if v_dates[1] is not null then
      v_current := v_dates[1];
    elsif v_weeks[1] is not null then
      v_current := 'Week ' || v_weeks[1];
    else
      raise exception 'Fail closed: vintage undeterminable for cbsros';
    end if;
  exception when others then
    v_err := sqlerrm;
  end;

  select last_vintage into v_last
    from public.pipeline_cron_state where source = 'cbsros';
  v_changed := (v_current is distinct from v_last);
  if v_err is not null then v_changed := true; v_current := null; end if;
  if v_changed then v_any_changed := true; end if;
  v_sources := v_sources || jsonb_build_object(
    'cbsros',
    jsonb_build_object(
      'current_vintage', v_current,
      'last_vintage',    v_last,
      'changed',         v_changed,
      'error',           v_err
    )
  );

  -----------------------------------------------------------------------
  -- razzball
  -- public.razzball_projections, latest razzball_snapshot_date.
  -- Maps to pipelines/check_source_vintage.py:153-157.
  -----------------------------------------------------------------------
  v_source := 'razzball';
  v_err := null; v_current := null;
  begin
    select coalesce(jsonb_agg(r), '[]'::jsonb) into v_rows
    from public.razzball_projections r;

    if jsonb_array_length(v_rows) = 0 then
      raise exception 'Fail closed: source razzball returned zero rows';
    end if;

    v_dates := (
      select array_agg(d order by d desc)
      from (
        select distinct (r->>'razzball_snapshot_date') as d
        from jsonb_array_elements(v_rows) as r
        where r->>'razzball_snapshot_date' is not null
      ) s
    );
    v_dates := array(select x from unnest(v_dates) as x where x is not null);

    if array_length(v_dates, 1) > 1 then
      raise exception 'Fail closed: mixed razzball_snapshot_date values %', v_dates;
    end if;

    v_rows := (
      select coalesce(jsonb_agg(r), '[]'::jsonb)
      from jsonb_array_elements(v_rows) as r
      where r->>'razzball_snapshot_date' = v_dates[1]
    );

    -- _derive_db_vintage: razzball uses source_content_date first, else week.
    v_dates := (
      select array_agg(d order by d)
      from (
        select distinct (r->>'source_content_date') as d
        from jsonb_array_elements(v_rows) as r
        where r->>'source_content_date' is not null
      ) s
    );
    v_dates := array(select x from unnest(v_dates) as x where x is not null);

    if array_length(v_dates, 1) > 1 then
      raise exception 'Fail closed: mixed source_content_date values %', v_dates;
    end if;

    v_weeks := (
      select array_agg(w order by w)
      from (
        select distinct (r->>'week') as w
        from jsonb_array_elements(v_rows) as r
        where r->>'week' is not null
      ) s
    );
    v_weeks := array(select x from unnest(v_weeks) as x where x is not null);

    if array_length(v_weeks, 1) > 1 then
      raise exception 'Fail closed: mixed week values %', v_weeks;
    end if;

    if v_dates[1] is not null then
      v_current := v_dates[1];
    elsif v_weeks[1] is not null then
      v_current := 'Week ' || v_weeks[1];
    else
      raise exception 'Fail closed: vintage undeterminable for razzball';
    end if;
  exception when others then
    v_err := sqlerrm;
  end;

  select last_vintage into v_last
    from public.pipeline_cron_state where source = 'razzball';
  v_changed := (v_current is distinct from v_last);
  if v_err is not null then v_changed := true; v_current := null; end if;
  if v_changed then v_any_changed := true; end if;
  v_sources := v_sources || jsonb_build_object(
    'razzball',
    jsonb_build_object(
      'current_vintage', v_current,
      'last_vintage',    v_last,
      'changed',         v_changed,
      'error',           v_err
    )
  );

  -----------------------------------------------------------------------
  -- Result envelope. Same shape as check_all_sources() :248-280.
  -----------------------------------------------------------------------
  v_result := jsonb_build_object(
    'changed', v_any_changed,
    'sources', v_sources
  );
  return v_result;
end $$;

comment on function public.check_source_vintages()
  is 'Read-only check that mirrors pipelines/check_source_vintage.py:99-160 per-source logic and :248-280 envelope. Returns {changed: bool, sources: {<src>: {current_vintage, last_vintage, changed, error}}}.';
```

### Mapping table — Python → SQL

The Python script and the SQL function must emit the same verdict for the
same inputs. This table is the contract.

| Source        | Python (`pipelines/check_source_vintage.py`) | SQL (`check_source_vintages`) |
|---------------|----------------------------------------------|-------------------------------|
| fantasycalc   | `:103-114` — `source_trade_values`, source=fantasycalc, variant=as_published → latest week → latest bake → `_derive_db_vintage` | same table, same WHERE, same scoping, same `_derive_db_vintage` mapping |
| usatoday      | same as fantasycalc with source=usatoday      | same |
| fantasypros   | same as fantasycalc with source=fantasypros   | same |
| espn          | `:117-120` — `espn_season_projections`, latest `espn_snapshot_date` → `_derive_db_vintage` (espn_snapshot_date or week) | same |
| cbs           | `:138-145` — `source_trade_values`, source=cbs, variant=as_published → latest week → latest bake → `_derive_db_vintage` | same |
| cbsros        | `:147-151` — `cbs_ros_projections`, latest `cbs_snapshot_date` → `_derive_db_vintage` (source_content_date or week) | same |
| razzball      | `:153-157` — `razzball_projections`, latest `razzball_snapshot_date` → `_derive_db_vintage` (source_content_date or week) | same |

`_derive_db_vintage` semantics (`pipelines/check_source_vintage.py:78-92`):
- For espn, read `espn_snapshot_date`; else fall back to `week`.
- For everyone else, read `source_content_date`; else fall back to `week`.
- Mixed distinct values of either column → `SystemExit('Fail closed: mixed …')`.
- Neither column populated → `SystemExit('Fail closed: vintage undeterminable …')`.
- Week fallback formats as `'Week N'`, matching Python `f"Week {weeks[0]}"`.

`check_all_sources()` semantics (`pipelines/check_source_vintage.py:248-280`):
- If `get_current_vintage` raises (any reason), record `error`, set
  `current_vintage=None`, `fixture_vintage=None`, `changed=True` — fail closed.
- Else `changed = current_vintage != fixture_vintage`.
- Returns `{sources: {<src>: {current_vintage, fixture_vintage, changed, error?}}, changed}`.

The SQL function preserves both behaviors exactly. The "fixture vintage" is
replaced by `pipeline_cron_state.last_vintage`, which the cutover job keeps
in sync (see open question Q1 for the sync mechanism).

---

## 3. The shadow `cron.schedule` call

The tracker row (`docs/audits/jeg285-phase2/01-migration-tracker.md:11`)
says: "Run pg_cron job hourly alongside GHA; compare dispatch decisions for
72h." This means the shadow job produces a decision, logs it, and **does
not** call `dispatch_gha_workflow`.

```sql
-- Run after the prerequisites block in 02-pgcron-job-specs.md:11-28.
-- This is the ONLY cron.schedule statement this spec introduces; the
-- retention-policy job (#9) and the cutover template are upstream concerns.
select cron.schedule(
  'vintage-check-shadow',
  '0 * * * *',                       -- hourly, on the hour, matches GHA
  $job$
    insert into public.pipeline_cron_log (job_name, checked_at, decision)
    values (
      'vintage-check-shadow',
      now(),
      public.check_source_vintages()
    );
  $job$
);
```

The body of the job is a single INSERT. There is no
`dispatch_gha_workflow(...)` and no `net.http_post(...)` reachable from
this code path. The only writes the shadow job performs are:
1. `insert into public.pipeline_cron_log` (audit log), and
2. nothing else — the function is `stable` and read-only.

Cutover (NOT this commit) replaces the body with the cutover template at
`docs/audits/jeg285-phase2/02-pgcron-job-specs.md:54-65`.

---

## 4. The 72h shadow-comparison query

The tracker gate ("72h of identical dispatch decisions, zero missed
triggers") is evaluated by joining `pipeline_cron_log` rows against the
GHA workflow's actual dispatch timestamps and flagging any disagreement.

This query assumes the existence of a `public.gha_dispatch_log` table —
see open question Q2. If Jeremy chooses a different source for GHA-truth
(e.g. an external audit trail), the JOIN target changes but the comparison
logic is the same.

```sql
-- 72h shadow-vs-GHA comparison. Run on-demand by the cutover reviewer.
-- Returns one row per shadow tick in the last 72h with a verdict column:
--   'agree'         — shadow would-have-dispatched == GHA dispatched
--   'shadow_extra'  — shadow would dispatch, GHA did not
--   'gha_extra'     — GHA dispatched, shadow would not
--   'no_gha_log'    — no GHA dispatch in the window; cannot verify
with shadow_decisions as (
  select
    checked_at,
    (decision->>'changed')::bool as would_dispatch
  from public.pipeline_cron_log
  where job_name = 'vintage-check-shadow'
    and checked_at >= now() - interval '72 hours'
),
gha_dispatches as (
  select
    dispatched_at,
    workflow_file
  from public.gha_dispatch_log
  where workflow_file = 'source-vintage-check.yml'
    and dispatched_at >= now() - interval '72 hours'
),
bucketed as (
  select
    date_trunc('hour', s.checked_at) as hour_bucket,
    s.would_dispatch,
    exists (
      select 1 from gha_dispatches g
      where date_trunc('hour', g.dispatched_at) = date_trunc('hour', s.checked_at)
    ) as gha_in_hour
  from shadow_decisions s
)
select
  hour_bucket,
  would_dispatch,
  gha_in_hour,
  case
    when would_dispatch and  gha_in_hour then 'agree'
    when would_dispatch and not gha_in_hour then 'shadow_extra'
    when not would_dispatch and gha_in_hour then 'gha_extra'
    else 'no_gha_log'
  end as verdict
from bucketed
order by hour_bucket desc;

-- Cutover gate summary:
--   pass  iff count(*) filter (where verdict in ('gha_extra','shadow_extra')) = 0
--          AND count(*) filter (where verdict = 'no_gha_log') = 0   -- zero missed triggers
--   fail  otherwise.
--
-- Equivalent single-pass form:
select
  count(*) filter (where verdict in ('gha_extra','shadow_extra')) as disagreements,
  count(*) filter (where verdict = 'no_gha_log')                  as missed_triggers,
  count(*)                                                        as shadow_ticks
from (
  select
    case
      when s.would_dispatch and  g.dispatched_at is not null then 'agree'
      when s.would_dispatch and g.dispatched_at is null     then 'shadow_extra'
      when not s.would_dispatch and g.dispatched_at is not null then 'gha_extra'
      else 'no_gha_log'
    end as verdict
  from shadow_decisions s
  left join lateral (
    select min(g2.dispatched_at) as dispatched_at
    from gha_dispatches g2
    where date_trunc('hour', g2.dispatched_at) = date_trunc('hour', s.checked_at)
  ) g on true
) v;
```

The pass condition is **both** counters zero: no disagreements AND no
hours where GHA failed to log a dispatch the shadow expected.

---

## 5. Verification — decision-parity walkthroughs

Two scenarios walked through both the Python script
(`pipelines/check_source_vintage.py`) and the SQL function above. The
inputs are the same in both runs; the verdicts must match.

### Scenario A — vintage changed → dispatch

**Fixture / state at t0:**

`pipeline_cron_state` (initial seed from §1.2):
| source       | last_vintage |
|--------------|--------------|
| fantasycalc  | `2026-09-29` |
| usatoday     | `2026-09-29` |
| fantasypros  | `2026-09-29` |
| espn         | `2026-09-30` |
| cbs          | `2026-09-29` |
| cbsros       | `2026-09-30` |
| razzball    | `2026-10-01` |

**DB at t1 (one source has new data):**
- `source_trade_values` where `source='fantasycalc'`,
  `variant='as_published'` now has rows where `source_content_date='2026-09-30'`,
  `week=5`, `bake_id='bake-2026-09-30T12'` (newer than the previous latest).
- Every other source unchanged from the state in `pipeline_cron_state`.

**Python run:**
- `check_source_vintage.get_current_vintage('fantasycalc')` (`:103-114`):
  filters `source=fantasycalc&variant=as_published` → latest week=5 →
  latest bake `'bake-2026-09-30T12'` → `_derive_db_vintage` finds
  `source_content_date='2026-09-30'` → returns `'2026-09-30'`.
- For every other source, `_derive_db_vintage` returns the same string as
  `pipeline_cron_state.last_vintage` (no DB rows moved).
- `check_all_sources()` (`:248-280`): fantasycalc
  `current='2026-09-30' != fixture='2026-09-29'` → `changed=True`; every
  other source `changed=False`.
- Returns `{changed: True, sources: {fantasycalc: {changed: True, ...}, ...}}`.

**SQL run:**
- `check_source_vintages()` fantasycalc branch (mirror of `:103-114`): SELECT
  from `source_trade_values` WHERE source='fantasycalc' AND
  variant='as_published' → row count > 0 → distinct weeks=[5] → distinct
  `source_content_date`=['2026-09-30'] → `v_current := '2026-09-30'`.
- Lookup `pipeline_cron_state.last_vintage` for fantasycalc → `'2026-09-29'`.
- `v_changed := ('2026-09-30' is distinct from '2026-09-29') = true`.
  `v_any_changed := true`.
- Every other source branch: `current = last_vintage` → `v_changed = false`.
- Returns `{changed: true, sources: {fantasycalc:
  {current_vintage:'2026-09-30', last_vintage:'2026-09-29', changed:true,
  error:null}, ...}}`.

**Verdict:** Python `{changed: True, …}` and SQL `{changed: true, …}` agree.

### Scenario B — vintage unchanged → no dispatch

**Same fixture / state as Scenario A.**

**DB at t1:** zero new rows since t0. `source_trade_values`,
`espn_season_projections`, `cbs_ros_projections`, `razzball_projections`
all unchanged.

**Python run:**
- Every source's `_derive_db_vintage` returns the same string as
  `pipeline_cron_state.last_vintage`.
- `changed=False` per source.
- `check_all_sources()` returns `{changed: False, sources: {<src>:
  {changed: False, current_vintage==fixture_vintage, ...}}}`.

**SQL run:**
- Every source's branch returns `v_current = last_vintage` →
  `v_changed = false`.
- `v_any_changed` stays false.
- Returns `{changed: false, sources: {<src>: {current_vintage:==last_vintage,
  changed:false, error:null}, ...}}`.

**Verdict:** Both agree on `{changed: False, …}`.

### Fail-closed confirmation

The shadow job contains no branch which dispatches the chain under any input.

- The shadow `cron.schedule` body (§3) is a single INSERT into
  `pipeline_cron_log`. The body contains no reference to
  `dispatch_gha_workflow`, `net.http_post`, or `repository_dispatch`.
- `check_source_vintages()` (§2) is declared `stable` — it cannot perform
  DML or DDL. Its only reads are `public.source_trade_values`,
  `public.espn_season_projections`, `public.cbs_ros_projections`,
  `public.razzball_projections`, and `public.pipeline_cron_state`. None of
  these trigger a dispatch.
- A fail-closed path inside a source branch (the `exception when others`
  blocks) sets `v_err := sqlerrm` and `v_changed := true`. The result is
  returned to the caller; the caller (the cron body) writes it to
  `pipeline_cron_log` and exits. No dispatch path is reached.
- The cutover template at
  `docs/audits/jeg285-phase2/02-pgcron-job-specs.md:54-65` is shown
  commented-out and is not part of this commit.

Net effect: the shadow job physically cannot dispatch the chain. The only
state mutation the shadow job performs is the INSERT into
`pipeline_cron_log` — the audit log the 72h comparison reads from.

---

## 6. Open questions for Jeremy

- **Q1. `pipeline_cron_state.last_vintage` sync mechanism.** The Python
  script compares DB vintage against the fixture vintage stored at
  `data/fixtures/current/comparison-sources-data.json`
  (`pipelines/check_source_vintage.py:13-14`). The SQL function compares
  against `pipeline_cron_state.last_vintage` instead. These are
  *equivalent in steady state* (see §2 mapping table) but diverge if the
  rebuild chain updates the fixture without dispatching, or vice versa.
  This spec assumes the cutover job — when it actually fires
  `dispatch_gha_workflow(...)` — also writes the just-observed
  `current_vintage` into `pipeline_cron_state`. **Need confirmation that
  this write is part of the cutover PR**, or a preferred alternative
  (e.g. a post-rebuild trigger that copies the fixture vintage into the
  table).

- **Q2. `gha_dispatch_log` source of truth for the 72h comparison query.**
  §4 assumes a `public.gha_dispatch_log(workflow_file, dispatched_at)`
  table populated by a webhook from GHA. Alternatives: (a) the GitHub
  REST API polled from a separate cron, (c) the existing
  `pipeline_checkpoints` artifacts if they already record GHA dispatch
  timestamps (UNVERIFIED — needs a search). **Need to pick one before
  cutover; the shadow spec does not require the table to exist yet** —
  the comparison query is the gate evaluation, not the shadow itself.

- **Q3. Reuse of `pipeline_cron_log` and `pipeline_cron_state` by jobs #2–7.**
  The migration tracker lists seven jobs that all produce similar
  decision logs (six of them dispatch-only — see
  `docs/audits/jeg285-phase2/02-pgcron-job-specs.md:76-105`). This spec
  uses `job_name` as a free-text discriminator and adds a CHECK
  constraint on `pipeline_cron_state.source`. **Confirm both tables are
  meant to be shared across the seven jobs**, or whether jobs #2–7 get
  their own per-job tables.

- **Q4. `pipeline_cron_state.last_vintage` initial seed vs first-shadow
  disagreement.** The seed in §1.2 sets every `last_vintage` to `NULL`.
  On the first shadow tick, `v_current is distinct from NULL` is `true`
  for every source → `v_any_changed = true` → the comparison query's
  `shadow_extra` counter fires for the first 72h. **Is this the intended
  behavior**, or should the first tick be a "warm-up" excluded from the
  gate? (Possible answer: seed `last_vintage` from the fixture at deploy
  time — but that requires reading the file at deploy time, which the
  brief explicitly forbids for the shadow phase.)

- **Q5. `STABLE` mark on `check_source_vintages()` inside `cron.schedule`
  body.** pg_cron executes the body as plain SQL inside a single
  transaction. The function is `STABLE` (read-only), but the cron body
  wraps it in an INSERT into `pipeline_cron_log`. This is fine — STABLE
  forbids writes from inside the function, not from outside it. **Confirm
  pg_cron's transaction semantics match this expectation** (one open
  transaction per scheduled tick; the INSERT and the function call share
  it). UNVERIFIED in the repo — I did not find a pg_cron transactional
  semantic doc to cite.

- **Q6. JEG-205 `code_changed` field.** The Python script additionally
  computes a `pipelines/` SHA-256 hash and emits `code_changed`,
  `code_hash`, `code_change_reason` (`pipelines/check_source_vintage.py:191-233`,
  `:254-256`). This spec's `check_source_vintages()` does NOT emit these
  fields — it is a SQL function, and computing a deterministic
  pipelines/ hash from inside Postgres requires `pg_read_file()` plus a
  manifest of file paths, which is out of scope for a SHADOW-only deliverable.
  **Confirm whether the cutover job's `dispatch_gha_workflow()` call must
  be conditioned on `code_changed` as well**, or whether the SQL shadow
  covering the per-source vintage decision is sufficient for the tracker
  gate ("72h of identical dispatch decisions"). The Python script
  treats `code_changed=True` as a dispatch trigger (`:255`); a SQL-only
  shadow cannot match that without re-implementing the hash.

---

## 7. What is UNVERIFIED in this spec

The brief says: "anything else is marked UNVERIFIED — never fabricate."
What I could not verify against the repo:

1. **The exact column types in the source tables.** I read
   `pipelines/check_source_vintage.py:27-35` for the column names
   (`source`, `variant`, `week`, `bake_id`, `created_at`,
   `source_content_date`, `espn_snapshot_date`, `cbs_snapshot_date`,
   `razzball_snapshot_date`) and the Python comparison logic, but not the
   Postgres column types. The SQL function casts via `::text` to be safe,
   but a stricter DDL on `pipeline_cron_state` (e.g.
   `last_vintage text check (last_vintage ~ '^\d{4}-\d{2}-\d{2}$|^Week \d+$')`)
   would need the upstream types verified. **Left as `text` for now.**
2. **The `pipeline_checkpoints` artifact schema.** Q2 above references it
   as a possible source of GHA-truth timestamps. I did not verify whether
   it already records GHA dispatch timestamps.
3. **pg_cron transactional semantics.** Q5 above.
4. **The `vault.decrypted_secrets` integration with `pipeline_cron_state`
   writes.** I assumed the cutover job (NOT this commit) writes to
   `pipeline_cron_state` using a service-role token, not via Vault. The
   02-spec's dispatch helper reads from Vault but writes nothing.
   **Confirm the write-path for `pipeline_cron_state` at cutover time.**
5. **Fixture-side filenames under `data/fixtures/current/`.** The Python
   script's `DEFAULT_FIXTURE_PATH` is
   `data/fixtures/current/comparison-sources-data.json`
   (`pipelines/check_source_vintage.py:13-14`). I did not read that file
   end-to-end; I only needed to know the key names
   (`pipelines/check_source_vintage.py:163-172`). UNVERIFIED for me:
   whether the file also contains the `last_vintage` snapshot the SQL
   function mirrors, or whether there is drift between the two formats.

---

## 8. Sources covered (count)

| Source                                                                                                | Role in this spec |
|------------------------------------------------------------------------------------------------------|-------------------|
| `pipelines/check_source_vintage.py` lines 1-310                                                       | ground-truth dispatch decision |
| `tests/test_check_source_vintage.py` lines 1-315                                                       | ground-truth semantics (vintage-key mapping, fail-closed) |
| `docs/audits/jeg285-phase2/01-migration-tracker.md` (entire file)                                     | tracker row for item #1, shadow plan, cutover gate |
| `docs/audits/jeg285-phase2/02-pgcron-job-specs.md` (entire file)                                     | prerequisites, dispatch helper, cutover template, table list |
| `docs/audits/jeg285-phase2/04-pgcron-retention-policy.md` (sampled, lines 1-80)                        | pattern reference for docs-only review-ready deliverable |

Five source files; every factual claim in §1–§5 cites one of these by
path-and-line. §6 lists six open questions; §7 lists five items I could
not verify from the repo alone.

---

## 9. Files touched by this spec

This spec is a single new file:
- `docs/audits/jeg285-phase2/05-job1-shadow-spec.md`

No other files are modified, created, or deleted by this commit. The
SQL in §1, §2, and §3 is *specification* text, not code that runs.