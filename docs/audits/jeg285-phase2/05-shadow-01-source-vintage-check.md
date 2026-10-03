# JEG-285 — Shadow Migration #1: source-vintage-check (minimax M3)

**Lane:** minimax (M3)
**Branch:** minimax/jeg-285-shadow-01
**Tracker row:** `docs/audits/jeg285-phase2/01-migration-tracker.md` (row #1, status `NOT STARTED` → `SHADOW`)
**Spec basis:** `docs/audits/jeg285-phase2/02-pgcron-job-specs.md` Job 1 section, prerequisites block, dispatch helper
**Target:** replace the hourly GHA cron `0 * * * *` at `.github/workflows/source-vintage-check.yml:5` with a `pg_cron` job of identical cadence, log the dispatch decision without firing it, and compare tick-by-tick against the live GHA run list for 72h.

The shadow replicates the **decision** the GHA job would make, not the dispatch itself. The schedule body never calls `dispatch_gha_workflow()` and never calls `net.http_post()`; it only inserts into `pipeline_cron_log`.

## 1. What "dispatch" means today (the GHA observable)

- Schedule: `cron: '0 * * * *'` (`.github/workflows/source-vintage-check.yml:5`).
- The check step runs `pipelines/check_source_vintage.py --json` (`.github/workflows/source-vintage-check.yml:37`) and parses `changed`, `code_changed`, `code_hash` from the JSON report into step outputs (`.github/workflows/source-vintage-check.yml:41-50`).
- **Dispatch decision is true when** `changed == 'True' OR code_changed == 'True'` (`.github/workflows/source-vintage-check.yml:66`).
- When the decision is true, the dispatch step runs `gh workflow run rebuild-chain.yml -f source="source-vintage-check"` (`.github/workflows/source-vintage-check.yml:69`). That is the only post-detection side-effect on the chain. `rebuild-chain.yml` declares `source` as the only `workflow_dispatch` input at `.github/workflows/rebuild-chain.yml:18-26`, so the dispatch API would reject the call if those drifted.
- **After the fact**, the decision is observable as: a `rebuild-chain` workflow run whose `inputs.source == "source-vintage-check"` (the run page shows it under the workflow_dispatch inputs section). The `source-vintage-check.yml` run itself tells you the tick fired on schedule; the rebuild-chain run whose `source` input equals `source-vintage-check` tells you the dispatch decision was true.
- The JEG-205 code-change path additionally writes the dispatched hash to `.github/source-vintage-state.json` (the `last_code_hash` key), but only when the dispatch step itself succeeded (`.github/workflows/source-vintage-check.yml:79-92`). That file is the loop guard (exactly one dispatch per code change).

## 2. Schema additions

Two tables, both in `public`. Postgres-native types only; no Supabase-only features. The column lists match the implementation-phase sketch at `docs/audits/jeg285-phase2/02-pgcron-job-specs.md:160-164` exactly.

```sql
create table if not exists public.pipeline_cron_log (
  job_name    text        not null,
  checked_at  timestamptz not null default now(),
  decision    jsonb       not null
);

create index if not exists pipeline_cron_log_job_checked_idx
  on public.pipeline_cron_log (job_name, checked_at desc);

create table if not exists public.pipeline_cron_state (
  key         text        primary key,
  value       jsonb       not null,
  updated_at  timestamptz not null default now()
);
```

`pipeline_cron_state.key` is the source name (one of the seven in `CHAIN_SOURCES` at `pipelines/check_source_vintage.py:26`). `value` is `{"last_dispatched_vintage": "<string>"}`. No `note` column — added here would be a deviation from the spec'd shape at `02-pgcron-job-specs.md:163`.

### 2.1 Decision JSON shape

Mirrors the fields `pipelines/check_source_vintage.py:248-280` (`check_all_sources`) produces, with `code_hash` and `code_change_reason` added to match the GHA step outputs (`.github/workflows/source-vintage-check.yml:44-45`). Every shadow tick writes exactly one row.

```jsonc
{
  "changed":             <bool>,         // dispatch-decision top-level. Matches GHA step.outputs.changed.
  "code_changed":        <bool>,         // JEG-205 path. SQL default = false (see §5).
  "code_hash":           <string|null>,  // pipelines/ SHA-256. SQL default = null (see §5).
  "code_change_reason":  <string>,       // human-readable. SQL default = "unverifiable: pipelines/ hash is not SQL-observable".
  "sources": {
    "fantasycalc":  { "current_vintage": <string|null>, "fixture_vintage": <string|null>, "changed": <bool>, "error": <string|null> },
    "usatoday":     { "current_vintage": <string|null>, "fixture_vintage": <string|null>, "changed": <bool>, "error": <string|null> },
    "fantasypros":  { "current_vintage": <string|null>, "fixture_vintage": <string|null>, "changed": <bool>, "error": <string|null> },
    "espn":         { "current_vintage": <string|null>, "fixture_vintage": <string|null>, "changed": <bool>, "error": <string|null> },
    "cbs":          { "current_vintage": <string|null>, "fixture_vintage": <string|null>, "changed": <bool>, "error": <string|null> },
    "cbsros":       { "current_vintage": <string|null>, "fixture_vintage": <string|null>, "changed": <bool>, "error": <string|null> },
    "razzball":     { "current_vintage": <string|null>, "fixture_vintage": <string|null>, "changed": <bool>, "error": <string|null> }
  }
}
```

Per-source semantics replicate `pipelines/check_source_vintage.py`:
- `current_vintage` = the value `_derive_db_vintage(rows, source)` would return at `pipelines/check_source_vintage.py:77-90` (the single string left after per-source scoping).
- `fixture_vintage` = `pipeline_cron_state.value->>'last_dispatched_vintage'` for the row keyed by `src`. Day-one seed = current fixture vintage (§4).
- `changed` = `current_vintage IS DISTINCT FROM fixture_vintage`. In SQL `IS DISTINCT FROM` is NULL-safe, matching Python `!=` which returns `True` whenever one side is `None`.
- `error` populated, `current_vintage=null`, `changed=true` on fail-closed paths (Python `pipelines/check_source_vintage.py:264-274`).

## 3. `check_source_vintages()` plpgsql

Replicates `pipelines/check_source_vintage.py:248-280` (`check_all_sources`). Reads only — never writes — `pipeline_cron_state`. The code-hash branch returns the SQL default (see §5). Returns `jsonb`.

```sql
create or replace function public.check_source_vintages()
returns jsonb
language plpgsql
volatile                         -- the function reads state that changes hourly; do not mark stable.
security definer
set search_path = public, pg_temp
as $$
declare
  src text;
  cur text;
  fx  text;
  err text;
  ch  bool;
  sources_json jsonb := '{}'::jsonb;
  any_changed bool := false;
begin
  for src in
    select unnest(array['fantasycalc','usatoday','fantasypros','espn','cbs','cbsros','razzball'])
  loop
    cur := null;
    fx  := null;
    err := null;
    begin
      cur := public._source_current_vintage(src);
    exception when others then
      err := sqlerrm;
    end;
    if err is not null or cur is null then
      ch := true;                                     -- fail-closed, mirrors py:264-274
    else
      select value->>'last_dispatched_vintage'
        into fx
        from public.pipeline_cron_state
        where key = src;
      ch := cur is distinct from fx;
    end if;
    sources_json := sources_json || jsonb_build_object(
      src,
      jsonb_build_object(
        'current_vintage', cur,
        'fixture_vintage', fx,
        'changed',        ch,
        'error',          err
      )
    );
    if ch then any_changed := true; end if;
  end loop;

  return jsonb_build_object(
    'changed',             any_changed,
    'code_changed',        false,                  -- see §5
    'code_hash',           null::text,
    'code_change_reason',  'unverifiable: pipelines/ hash is not SQL-observable',
    'sources',             sources_json
  );
end $$;
```

### 3.1 `_source_current_vintage(src text)` — per-source scoping

Replicates `pipelines/check_source_vintage.py:get_current_vintage` (lines 93-145) one branch per source. The per-source table mapping at `pipelines/check_source_vintage.py:28-36` is reproduced verbatim. Returns the vintage string, or raises on fail-closed paths.

```sql
create or replace function public._source_current_vintage(src text)
returns text
language plpgsql
stable
security definer
set search_path = public, pg_temp
as $$
declare
  v_text text;
begin
  if src in ('fantasycalc','usatoday','fantasypros') then
    -- source_trade_values path (py:99-106, 114-122): filter by source + variant=as_published,
    -- then scope to latest week, then latest bake by (max(created_at), bake_id desc).
    with f as (
      select * from public.source_trade_values
      where source = src and variant = 'as_published'
    ),
    w as (
      select * from f
      where week = (select max(week) from f where week is not null)
    ),
    b as (
      select * from w
      where bake_id = (
        select bake_id from w
        order by max(created_at) over (partition by bake_id) desc nulls last,
                 bake_id::text desc
        limit 1
      )
    )
    select
      case
        when (select count(distinct source_content_date) from b where source_content_date is not null) > 1
          then null   -- fail-closed, mirrors py:82-83
        when (select count(distinct week) from b where week is not null) > 1
          then null   -- fail-closed, mirrors py:84-85
        else coalesce(
          (select source_content_date::text from b where source_content_date is not null limit 1),
          (select 'Week ' || week::text      from b where week is not null             limit 1)
        )
      end
      into v_text
    from (select 1) as one;
    if v_text is null then
      raise exception 'Fail closed: source % returned zero rows after scoping', src;
    end if;
    return v_text;

  elsif src = 'cbs' then
    -- cbs_trade_values path (py:114-122 — SOURCE_TABLES maps cbs to
    -- public.cbs_trade_values, NOT source_trade_values): filter by
    -- source='cbs' + variant=as_published, then latest week, then latest bake.
    -- Reviewer note: the first draft of this spec read cbs from
    -- source_trade_values; that table carries no cbs rows, so the shadow would
    -- have fail-closed (changed=true) on cbs every tick. Fixed on review.
    with f as (
      select * from public.cbs_trade_values
      where source = 'cbs' and variant = 'as_published'
    ),
    w as (
      select * from f
      where week = (select max(week) from f where week is not null)
    ),
    b as (
      select * from w
      where bake_id = (
        select bake_id from w
        order by max(created_at) over (partition by bake_id) desc nulls last,
                 bake_id::text desc
        limit 1
      )
    )
    select
      case
        when (select count(distinct source_content_date) from b where source_content_date is not null) > 1
          then null   -- fail-closed, mirrors py:82-83
        when (select count(distinct week) from b where week is not null) > 1
          then null   -- fail-closed, mirrors py:84-85
        else coalesce(
          (select source_content_date::text from b where source_content_date is not null limit 1),
          (select 'Week ' || week::text      from b where week is not null             limit 1)
        )
      end
      into v_text
    from (select 1) as one;
    if v_text is null then
      raise exception 'Fail closed: source % returned zero rows after scoping', src;
    end if;
    return v_text;

  elsif src = 'espn' then
    -- espn_season_projections: latest espn_snapshot_date (py:107-113).
    with f as (select * from public.espn_season_projections),
    s as (
      select * from f
      where espn_snapshot_date = (select max(espn_snapshot_date) from f where espn_snapshot_date is not null)
    )
    select espn_snapshot_date::text into v_text
      from s
      where espn_snapshot_date is not null
      limit 1;
    if v_text is null then
      raise exception 'Fail closed: source % returned zero rows after scoping', src;
    end if;
    return v_text;

  elsif src = 'cbsros' then
    -- cbs_ros_projections: latest cbs_snapshot_date (py:123-130).
    with f as (select * from public.cbs_ros_projections),
    s as (
      select * from f
      where cbs_snapshot_date = (select max(cbs_snapshot_date) from f where cbs_snapshot_date is not null)
    )
    select cbs_snapshot_date::text into v_text
      from s
      where cbs_snapshot_date is not null
      limit 1;
    if v_text is null then
      raise exception 'Fail closed: source % returned zero rows after scoping', src;
    end if;
    return v_text;

  elsif src = 'razzball' then
    -- razzball_projections: latest razzball_snapshot_date (py:131-138).
    with f as (select * from public.razzball_projections),
    s as (
      select * from f
      where razzball_snapshot_date = (select max(razzball_snapshot_date) from f where razzball_snapshot_date is not null)
    )
    select razzball_snapshot_date::text into v_text
      from s
      where razzball_snapshot_date is not null
      limit 1;
    if v_text is null then
      raise exception 'Fail closed: source % returned zero rows after scoping', src;
    end if;
    return v_text;

  else
    raise exception 'Fail closed: unknown source %', src;
  end if;
end $$;
```

Notes on parity with the Python:

- The single-bake fast path at `pipelines/check_source_vintage.py:60-63` is preserved by the `order by ... limit 1` over `week_scoped`: when `week_scoped` has only one `bake_id`, the `max(created_at) over (partition by bake_id)` collapses to that bake and the tiebreak (`bake_id::text desc`) selects it deterministically.
- The "no created_at anywhere" fallback at `pipelines/check_source_vintage.py:64-65` returns the first bake encountered; SQL's `order by ... desc nulls last, bake_id::text desc limit 1` produces a deterministic but **different** first-bake than Python's `next(iter(bakes))`. Flagged in §6 (open question Q2) — this is a known blind-spot signature, not a defect, because the all-NULL `created_at` case should be vanishingly rare in production and the dispatch outcome (`changed=true` only when the SQL `current_vintage` differs from the seeded fixture vintage) is dominated by the date string, not by which bake is chosen.
- The date-vs-week fallback at `pipelines/check_source_vintage.py:86-89` is preserved: if `source_content_date` is null, `'Week ' || week::text` is returned.
- Mix-dates and mix-weeks fail-closed branches (`pipelines/check_source_vintage.py:82-83`, `84-85`) are preserved by raising in the caller (`check_source_vintages`); the shadow records `error=sqlerrm, current_vintage=null, changed=true` for that source.

## 4. Shadow schedule (paste-ready, side-effect-free)

```sql
-- Prerequisites (run once, before any pg_cron job).
-- Verbatim from docs/audits/jeg285-phase2/02-pgcron-job-specs.md:9-24.
create extension if not exists pg_cron with schema pg_catalog;
grant usage on schema cron to postgres;
grant all privileges on all tables in schema cron to postgres;
create extension if not exists pg_net with schema extensions;
-- Retention is already live per tracker row #9; do not re-schedule.

-- Shadow schedule. Idempotent on the job name.
select cron.schedule(
  'vintage-check-shadow',
  '0 * * * *',
  $$
  insert into public.pipeline_cron_log (job_name, checked_at, decision)
  values ('vintage-check-shadow', now(), public.check_source_vintages());
  $$
);
```

**Side-effect guarantee, restated for the reviewer.** The schedule body:
- inserts exactly one row into `public.pipeline_cron_log`;
- reads `public.source_trade_values`, `public.espn_season_projections`, `public.cbs_trade_values`, `public.cbs_ros_projections`, `public.razzball_projections`, and `public.pipeline_cron_state`;
- does NOT call `dispatch_gha_workflow(...)` (the helper from `02-pgcron-job-specs.md:36-54` is for the cutover path only);
- does NOT call `net.http_post(...)`;
- does NOT update `public.pipeline_cron_state` outside the explicit seed at §4.1.

The dispatch helper exists in the same schema and is reachable, but `vintage-check-shadow` never references it.

### 4.1 Day-one seed for `pipeline_cron_state`

`pipeline_cron_state` carries "last dispatched vintage per source", which is what `pipelines/check_source_vintage.py:check_all_sources` (`py:248-280`) compares `current_vintage` against at each tick. The Python source of that stamp is `data/fixtures/current/comparison-sources-data.json` — read via `get_fixture_vintage` at `pipelines/check_source_vintage.py:161-174`, which selects the per-source key from `FIXTURE_VINTAGE_KEYS` at `pipelines/check_source_vintage.py:150-158`.

Snapshot the seven fixture values into `pipeline_cron_state` BEFORE the schedule first runs. The literal values must be read from the live fixture at the moment the shadow is enabled; this spec intentionally does not embed them. Placeholders below show the format only.

```sql
-- Read these seven strings from data/fixtures/current/comparison-sources-data.json
-- using the FIXTURE_VINTAGE_KEYS map at pipelines/check_source_vintage.py:150-158:
--   fantasycalc/usatoday/fantasypros/cbs  → sources.<src>.content_vintage
--   espn                                  → sources.espn.espn_snapshot
--   cbsros/razzball                       → sources.<src>.vintage
insert into public.pipeline_cron_state (key, value, updated_at) values
  ('fantasycalc', jsonb_build_object('last_dispatched_vintage', '<content_vintage from fixture>'), now()),
  ('usatoday',    jsonb_build_object('last_dispatched_vintage', '<content_vintage from fixture>'), now()),
  ('fantasypros', jsonb_build_object('last_dispatched_vintage', '<content_vintage from fixture>'), now()),
  ('espn',        jsonb_build_object('last_dispatched_vintage', '<espn_snapshot from fixture>'),   now()),
  ('cbs',         jsonb_build_object('last_dispatched_vintage', '<content_vintage from fixture>'), now()),
  ('cbsros',      jsonb_build_object('last_dispatched_vintage', '<vintage from fixture>'),         now()),
  ('razzball',    jsonb_build_object('last_dispatched_vintage', '<vintage from fixture>'),         now())
on conflict (key) do update set
  value      = excluded.value,
  updated_at = excluded.updated_at;
```

The seed is a one-shot at shadow enablement. The shadow never writes to `pipeline_cron_state` afterwards. Cutover (not this spec) is the path that updates it after a dispatch, mirroring the GHA path where the rebuilt fixture is the new "last dispatched" stamp.

## 5. UNVERIFIED items

1. **`code_changed` / `code_hash` / `code_change_reason` are not SQL-observable.** `pipelines/check_source_vintage.py:compute_pipelines_code_hash` (lines 177-203) walks `pipelines/` and SHA-256s the bytes; `check_code_change` (lines 206-231) compares against `.github/source-vintage-state.json`. Neither is reachable from Postgres: there is no filesystem access for the repo from pg_cron, and the GHA state file is only meaningful when paired with the dispatch step at `.github/workflows/source-vintage-check.yml:79-92`. The SQL shadow emits `code_changed=false, code_hash=null, code_change_reason='unverifiable: pipelines/ hash is not SQL-observable'` on every tick. **Implication:** when GHA fires the dispatch on a JEG-205 code change, the shadow will record `changed=false`. That is a known blind-spot signature, not a defect. The 72h comparison treats it as expected noise and isolates it in §7 step 3.

2. **Mix-dates fail-closed at `_derive_db_vintage`** (`pipelines/check_source_vintage.py:82-83`, `84-85`) raises in the SQL helper; the caller captures `sqlerrm` and sets `changed=true`. Parity is preserved.

3. **No SQL-observable equivalent for "the fixture moved".** When `data/fixtures/current/comparison-sources-data.json` is rewritten by a successful `rebuild-chain` run, the Python check picks up the new vintage on its next tick because it reads the file from disk (`pipelines/check_source_vintage.py:259-261`). The SQL shadow reads from `pipeline_cron_state`, which is only seeded once (§4.1). Until cutover, the reviewer must manually re-seed `pipeline_cron_state` if they want the shadow to track fixture movements. Flagged as Q3.

4. **No SQL-observable equivalent for `get_fixture_vintage`'s `vintage` fallback** (`pipelines/check_source_vintage.py:173-174`). The seed step uses the canonical `FIXTURE_VINTAGE_KEYS` key per source, so the fallback does not apply at seed time. If a future fixture drift puts data under the fallback key only, the shadow will diverge — but the Python check would diverge the same way (`get_fixture_vintage` returns the canonical key first, the fallback only triggers when the canonical key is absent, in which case both paths miss it).

## 6. Cutover (reference only — NOT enabled in this spec)

From `02-pgcron-job-specs.md:73-83`:

```sql
-- DO NOT RUN until the 72h shadow gate has passed.
select cron.schedule(
  'vintage-check',
  '0 * * * *',
  $$
  select case when (public.check_source_vintages()->>'changed')::bool
    then public.dispatch_gha_workflow(
      'rebuild-chain.yml',
      jsonb_build_object('source','pg-cron-vintage-check'))
    else null end;
  $$
);
```

Cutover additionally writes the just-dispatched vintage into `pipeline_cron_state` (key = `<source>`, value = `{last_dispatched_vintage: <new>}`), mirroring the GHA path where the rebuilt fixture becomes the next tick's stamp (`rebuild-chain.yml:93-99` writes the rebuilt fixture, and the next `source-vintage-check` tick reads it).

## 7. 72-hour comparison recipe

Inputs:
- GHA: workflow runs at `https://github.com/JB-barrel-droid/fantasy-tools/actions/workflows/source-vintage-check.yml`. Each run is one tick. The decision is observable as a `rebuild-chain` run with `inputs.source == "source-vintage-check"` triggered within the same hour (the dispatch API call is at `.github/workflows/source-vintage-check.yml:69`). For automation, export via `GET /repos/JB-barrel-droid/fantasy-tools/actions/workflows/source-vintage-check.yml/runs?created=>=NOW-72h`.
- Shadow: rows in `public.pipeline_cron_log` where `job_name = 'vintage-check-shadow'`, ordered by `checked_at`.

### 7.1 Step 1 — align ticks to the UTC hour boundary

```sql
select date_trunc('hour', checked_at) as tick_at,
       (decision->>'changed')::bool    as shadow_changed,
       decision->'sources'             as shadow_sources
  from public.pipeline_cron_log
  where job_name = 'vintage-check-shadow'
    and checked_at >= now() - interval '72 hours'
  order by tick_at;
```

GHA runs are bucketed the same way (`date_trunc('hour', started_at)`).

### 7.2 Step 2 — agreement table

```sql
with shadow as (
  select date_trunc('hour', checked_at) as tick_at,
         (decision->>'changed')::bool    as shadow_changed,
         decision->'sources'             as sources
  from public.pipeline_cron_log
  where job_name = 'vintage-check-shadow'
    and checked_at >= now() - interval '72 hours'
),
gha as (
  -- Build this set from the Actions API export:
  --   tick_at timestamptz, gha_changed bool
  -- where gha_changed = true iff a rebuild-chain run with
  -- inputs.source = "source-vintage-check" was triggered from a
  -- source-vintage-check run that started in this hour bucket.
  select * from (values
    -- ('2026-10-03 14:00:00+00', true),
    -- ('2026-10-03 15:00:00+00', false),
    -- ...
  ) as g(tick_at timestamptz, gha_changed bool)
)
select coalesce(s.tick_at, g.tick_at)                               as tick_at,
       s.shadow_changed,
       g.gha_changed,
       case
         when s.shadow_changed is null then 'shadow missed'
         when g.gha_changed     is null then 'GHA missed'
         when s.shadow_changed <> g.gha_changed then 'MISMATCH'
         else 'match'
       end                                                       as verdict,
       s.sources
from shadow s
full outer join gha g using (tick_at)
order by tick_at;
```

### 7.3 Step 3 — failure-mode detection

- **False positive** (shadow fired when GHA did not): `verdict = 'MISMATCH'` AND `shadow_changed = true` AND `gha_changed = false`. Inspect the `sources` jsonb for the source whose `changed = true`. Two likely causes: (a) stale `pipeline_cron_state` row (a fixture movement was not re-seeded — see §5 item 3), (b) a per-source semantic drift between SQL and Python (`current_vintage` reads differ on edge cases). The latter blocks cutover.
- **Missed trigger** (GHA fired when shadow did not): `verdict = 'MISMATCH'` AND `gha_changed = true` AND `shadow_changed = false`. Two causes: (a) the **expected JEG-205 code-change blind spot** — `code_change_reason = 'unverifiable: pipelines/ hash is not SQL-observable'` in the same shadow row, confirm by checking whether the corresponding GHA run pushed a `.github/source-vintage-state.json` commit in the same hour; (b) a real semantic divergence — escalate.
- **Tick drift** (`shadow missed` or `GHA missed`): inspect `cron.job_run_details` for skipped runs and `pg_stat_activity` for long transactions. A missed GHA tick on a US holiday/working-hour boundary is not unusual; a missed shadow tick is a pg_cron health problem.

### 7.4 Pass criterion (tracker row #1)

"72h of identical dispatch decisions, zero missed triggers" (`docs/audits/jeg285-phase2/01-migration-tracker.md:14`). Mapped to the verdict column above:

- Every aligned tick where both sides produced a row is `match` → pass on identity. Mismatches tagged with the JEG-205 blind-spot signature (`code_change_reason` matches) are excluded from the identity calculation by §5 item 1 and counted separately; they do not block cutover.
- No `GHA missed` rows → pass on cadence (zero missed triggers).
- Any other mismatch, or a tick where the shadow was missed, is a fail and blocks cutover until resolved.

## 8. Rollback

```sql
-- 1. Stop the schedule. cron.unschedule is idempotent on the job name.
select cron.unschedule('vintage-check-shadow');

-- 2. Drop the tables (only after the schedule is unscheduled and 72h comparison is closed).
drop table if exists public.pipeline_cron_log;
drop table if exists public.pipeline_cron_state;
```

Both tables are additive and not referenced by any other scheduled job (`docs/audits/jeg285-phase2/02-pgcron-job-specs.md:90-117` is the rest of the migration set; none of those jobs read these tables). The retention job `cron-retention-30d` (`02-pgcron-job-specs.md:18-23`) cleans only `cron.job_run_details`. Dropping the two tables is safe.

## 9. Open questions for Jeremy

1. **JEG-205 code-change path** (§5 item 1). Two options to consider before cutover:
   - (a) Accept the blind-spot signature as expected noise (current spec). Mismatches tagged with `code_change_reason = 'unverifiable: pipelines/ hash is not SQL-observable'` are filtered out of the identity calculation in §7.4.
   - (b) Have the GHA workflow additionally write the pipelines/ hash to a new Supabase table on every dispatch (mirroring the `.github/source-vintage-state.json` write at `.github/workflows/source-vintage-check.yml:79-92`), and have the SQL shadow read it. Adds one GHA step and one SQL read; eliminates the blind spot. **Recommendation:** keep (a) for shadow #1 to minimise new moving parts; revisit if any MISMATCH in the 72h window traces back to the blind spot.
2. **`created_at` all-NULL bake selection.** `_select_latest_bake` (`pipelines/check_source_vintage.py:57-67`) returns `next(iter(bakes))` when no row has a `created_at`; the SQL `order by ... desc nulls last, bake_id::text desc limit 1` may pick a different bake in that corner. In production every `source_trade_values` row has a `created_at` (the table is written by the audit-stamped import path), so the case is theoretical. If the 72h window shows a MISMATCH whose only difference is the chosen `bake_id` and the `current_vintage` strings are identical, this is the cause — switch the SQL to `next(iter(...))` semantics by switching the tiebreak to `bake_id::text asc` and document the deviation.
3. **Fixture-movement re-seed cadence.** Until cutover, the reviewer must re-seed `pipeline_cron_state` whenever `data/fixtures/current/comparison-sources-data.json` is rewritten by a successful rebuild-chain run. Options: (i) add a one-line update query to the chain's commit step so every fixture rewrite bumps `pipeline_cron_state`; (ii) re-seed weekly by hand; (iii) ignore, accept that the shadow will report `changed=true` after every dispatch (the GHA path resets to `changed=false` after the dispatch, because the fixture rewrite is what it reads; the SQL shadow won't, until the seed catches up).
4. **Schedule drift.** `pg_cron` schedules are evaluated in the database's timezone, which Supabase sets to UTC by default. The GHA schedule `cron: '0 * * * *'` (`source-vintage-check.yml:5`) is also UTC. Confirmed identical cadence. No `America/Chicago` translation is needed; if the dashboard monitor ever needs local-time alignment, document it here.