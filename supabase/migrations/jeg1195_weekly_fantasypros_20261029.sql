-- JEG-1195. APPLIED 2026-10-29 03:09 UTC on Jeremy's yes ("Approve the migration"),
-- as Supabase migration jeg1195_weekly_fantasypros_20261029. The applied SQL
-- left out the six "drop trigger/policy if exists" lines below (no-ops on the
-- fresh database); every other statement ran as written. Additive: three new tables, their triggers, four functions and one
-- login role; nothing else is touched, no existing row, view or published
-- output changes.
--
-- Purpose: Muse, signed in to FantasyPros, writes the weekly projections and
-- weekly ECR rankings pages here once a day (Jeremy 2026-10-29: "i could have
-- muse run this daily", "muse can push the data right to supabase"). Raw page
-- data only: no player_key, no merging, no derived numbers. The JEG-1195
-- weekly-input producer owns identity, freshness labels and everything
-- downstream, so each of those keeps one owner. The producer reads completed
-- batches only.
--
-- Weekly only (Jeremy 2026-10-29: "do not blend weekly data with ROS data,
-- ever"): horizon is pinned to 'week'; rest-of-season and draft pages never
-- belong here.
--
-- Muse's review (2026-10-29), folded in:
--   1. freshness: a content hash and the page's own "last updated" stamp per
--      page; a page whose hash matches the previous completed batch is flagged
--      same_as_previous by the database, never landed as a fresh pull.
--   2. completeness: a page lands only with full_list verified, its row count
--      at or above the position floor and equal to any "showing X of Y" count.
--      A failing page inserts nothing.
--   3. batch integrity: weekly_fantasypros_batches is the manifest (pages
--      expected, rows per page, completed flag). One completed batch per New
--      York day; a re-run supersedes an unfinished batch and is refused after a
--      completed one. Inserted rows are counted by the database after each page.
--   4. scoring: a page lands only with scoring_verified and the known players
--      it was checked on.
--   5. identity: fp_player_id when the markup shows one.
--   6. placeholders: dashes and other non-numeric markers land as null, never 0
--      (the writer's parse rule; numeric columns cannot hold text).
-- Muse's second review (2026-10-29), folded in:
--   7. one week per batch: a page whose heading reports a different season or
--      week from the batch's other pages is refused, and completion checks it
--      again.
--   8. page_updated_at: FantasyPros stamps are read as America/New_York (the
--      writer's parse rule; page_updated_text keeps the stamp as shown).
--   9. silence can't hide a failure: the check weekly_fantasypros_pull is
--      recorded on every completion and failure, and pg_cron job
--      weekly-fantasypros-daily-check records it again at 16:00 UTC: red when
--      the New York day has no completed batch or its latest batch failed. The
--      monitoring evaluator marks it missed if that job stops. Muse also posts
--      every run's result on JEG-1195 (Jeremy, 2026-10-29: "B").
--
-- config/monitoring_coverage.json lists the job under pg_cron_sql_jobs
-- (weekly-fantasypros-daily-check -> weekly_fantasypros_pull), added with the apply.
--
-- Auth, least privilege: Muse connects as the login role weekly_fp_writer. It
-- can INSERT pages and player rows and EXECUTE the four batch functions (not
-- the two check functions), and
-- nothing else: no SELECT, UPDATE or DELETE on any table. The previous-hash
-- lookup and the row counts run inside the database, so the role never reads.
-- Jeremy sets its password himself after applying (alter role weekly_fp_writer
-- password '...'), never in the repo; Muse connects through the Supabase pooler
-- as weekly_fp_writer.<project_ref>. Inserts must not ask for returned rows (no
-- RETURNING), since the role has no SELECT.
-- Names: <subproject>_<entity>, subproject 'weekly'.

-- ---------------------------------------------------------------------------
-- Manifest: one row per daily pull.
create table if not exists public.weekly_fantasypros_batches (
    batch_id       uuid        primary key default gen_random_uuid(),
    source         text        not null default 'fantasypros' check (source = 'fantasypros'),
    season         smallint    not null check (season between 2026 and 2100),
    -- New York calendar day of the pull, set by weekly_fp_start_batch
    pull_date      date        not null,
    pages_expected smallint    not null check (pages_expected between 1 and 64),
    started_at     timestamptz not null default now(),
    completed      boolean     not null default false,
    completed_at   timestamptz,
    -- set at completion: pages and player rows the database counted
    pages_landed   smallint,
    rows_landed    integer,
    -- set when the run fails or a re-run supersedes it
    failed_reason  text,
    failed_at      timestamptz,
    constraint weekly_fantasypros_batches_state check (
        not (completed and failed_reason is not null)
        and (completed = (completed_at is not null))
        and ((failed_reason is null) = (failed_at is null)))
);

comment on table public.weekly_fantasypros_batches is
    'JEG-1195: manifest of Muse''s daily FantasyPros weekly pulls. Only completed batches are usable; one completed batch per New York day.';

-- a re-run never silently creates a duplicate day
create unique index if not exists weekly_fantasypros_batches_one_per_day
    on public.weekly_fantasypros_batches (source, pull_date) where completed;

-- ---------------------------------------------------------------------------
-- One row per page per batch, written before that page's player rows.
create table if not exists public.weekly_fantasypros_pages (
    batch_id          uuid        not null references public.weekly_fantasypros_batches (batch_id),
    source            text        not null default 'fantasypros' check (source = 'fantasypros'),
    horizon           text        not null default 'week' check (horizon = 'week'),
    page_kind         text        not null check (page_kind in ('projections', 'ecr')),
    position          text        not null check (position in ('QB', 'RB', 'WR', 'TE')),
    scoring_format    text        not null check (scoring_format in ('standard', 'half_ppr', 'full_ppr')),
    season            smallint    not null check (season between 2026 and 2100),
    -- the week printed in the page heading, never the week requested
    week              smallint    not null check (week between 1 and 18),
    page_url          text        not null,
    page_heading      text        not null,
    -- the page's own "last updated" stamp: text as shown, and parsed when it parses
    page_updated_text text,
    page_updated_at   timestamptz,
    -- sha256 hex of the page's player table as read (spec in the JEG-1195 packet)
    content_hash      text        not null check (content_hash ~ '^[0-9a-f]{64}$'),
    -- set by the database: true when the hash equals this page in the previous
    -- completed batch, which is named in previous_batch_id
    same_as_previous  boolean     not null default false,
    previous_batch_id uuid,
    -- "showing X of Y" as shown, when the page shows it
    shown_count       integer     check (shown_count >= 0),
    total_count       integer     check (total_count >= 0),
    -- player rows read from the page and about to be inserted
    rows_expected     integer     not null,
    -- only verified pages land
    full_list         boolean     not null check (full_list),
    scoring_verified  boolean     not null check (scoring_verified),
    -- the known players the scoring check used, with the values compared
    scoring_check     jsonb       not null check (jsonb_typeof(scoring_check) = 'array'
                                                  and jsonb_array_length(scoring_check) >= 3),
    pulled_at         timestamptz not null,
    inserted_at       timestamptz not null default now(),
    -- set by weekly_fp_finish_page: rows the database counted
    rows_inserted     integer,
    verified_at       timestamptz,
    primary key (batch_id, page_kind, position, scoring_format),
    -- completeness floor per position: a top-10 render or a truncated list fails
    constraint weekly_fantasypros_pages_floor check (rows_expected >= case position
        when 'QB' then 20 when 'RB' then 40 when 'WR' then 60 when 'TE' then 25 end),
    -- "showing X of Y": both or neither, every player shown, every row read
    constraint weekly_fantasypros_pages_shown check (
        (shown_count is null and total_count is null)
        or (shown_count = total_count and rows_expected = shown_count)),
    constraint weekly_fantasypros_pages_verified check (
        (rows_inserted is null) = (verified_at is null)
        and (rows_inserted is null or rows_inserted = rows_expected))
);

comment on table public.weekly_fantasypros_pages is
    'JEG-1195: one row per FantasyPros weekly page per batch: hash, last-updated stamp, completeness and scoring checks, and the database''s own row count. same_as_previous pages are not fresh pulls.';

-- ---------------------------------------------------------------------------
-- One row per player per page.
create table if not exists public.weekly_fantasypros_raw (
    id             bigint generated always as identity primary key,
    batch_id       uuid        not null,
    page_kind      text        not null,
    position       text        not null,
    scoring_format text        not null,
    -- FantasyPros' own player id when the markup shows one
    fp_player_id   text,
    player_name    text        not null,
    team           text,
    -- ECR rows: the rank and spread columns as shown; null on projection rows
    ecr_rank       integer,
    ecr_best       integer,
    ecr_worst      integer,
    ecr_avg        numeric(6,2),
    ecr_std        numeric(6,2),
    -- projection rows: FPTS as shown; null on ECR rows. A blank cell or a dash
    -- stays null, never 0.
    fpts           numeric(6,2),
    -- the page's other columns exactly as shown: {"header": "value", ...}
    raw_columns    jsonb       not null default '{}'::jsonb,
    inserted_at    timestamptz not null default now(),
    constraint weekly_fantasypros_raw_page foreign key (batch_id, page_kind, position, scoring_format)
        references public.weekly_fantasypros_pages (batch_id, page_kind, position, scoring_format),
    constraint weekly_fantasypros_raw_kind_fields check (
        (page_kind = 'ecr' and ecr_rank is not null and fpts is null)
        or (page_kind = 'projections' and ecr_rank is null)),
    -- a re-sent row in the same page is a no-op (insert ... on conflict do nothing);
    -- the page's row count then comes up short and the page fails
    constraint weekly_fantasypros_raw_key unique nulls not distinct
        (batch_id, page_kind, position, scoring_format, fp_player_id, player_name, team)
);

comment on table public.weekly_fantasypros_raw is
    'JEG-1195: raw FantasyPros weekly projections and weekly ECR rows, written daily by Muse (role weekly_fp_writer). Weekly only, never rest of season. No player_key; the weekly-input producer resolves identity. Append-only. Read through completed batches only.';

create index if not exists weekly_fantasypros_pages_lookup_idx
    on public.weekly_fantasypros_pages (page_kind, position, scoring_format, inserted_at);
create index if not exists weekly_fantasypros_raw_fp_player_idx
    on public.weekly_fantasypros_raw (fp_player_id) where fp_player_id is not null;

-- ---------------------------------------------------------------------------
-- Guards. Trigger functions run as the owner so the writer never needs SELECT.

-- a page lands only into an open batch of the same season; the database sets
-- the stale flag and clears anything only the database may set
create or replace function public.weekly_fantasypros_pages_before_insert()
returns trigger language plpgsql security definer set search_path = public, pg_temp as $$
declare
    b record;
    prev record;
begin
    select * into b from public.weekly_fantasypros_batches where batch_id = new.batch_id;
    if not found then
        raise exception 'weekly_fantasypros_pages: batch % does not exist', new.batch_id;
    end if;
    if b.completed or b.failed_reason is not null then
        raise exception 'weekly_fantasypros_pages: batch % is closed', new.batch_id;
    end if;
    if new.season <> b.season then
        raise exception 'weekly_fantasypros_pages: season % does not match batch season %', new.season, b.season;
    end if;
    -- one week per batch: every page heading reports the same season and week
    if exists (select 1 from public.weekly_fantasypros_pages
                where batch_id = new.batch_id and (season, week) <> (new.season, new.week)) then
        raise exception 'weekly_fantasypros_pages: week % differs from the other pages in batch %',
            new.week, new.batch_id;
    end if;

    select p.batch_id, p.content_hash into prev
      from public.weekly_fantasypros_pages p
      join public.weekly_fantasypros_batches pb on pb.batch_id = p.batch_id
     where pb.completed and pb.source = b.source
       and p.page_kind = new.page_kind and p.position = new.position
       and p.scoring_format = new.scoring_format
     order by pb.completed_at desc
     limit 1;
    new.previous_batch_id := prev.batch_id;
    new.same_as_previous := coalesce(prev.content_hash = new.content_hash, false);
    new.rows_inserted := null;
    new.verified_at := null;
    new.inserted_at := now();
    return new;
end;
$$;

drop trigger if exists weekly_fantasypros_pages_insert on public.weekly_fantasypros_pages;
create trigger weekly_fantasypros_pages_insert
    before insert on public.weekly_fantasypros_pages
    for each row execute function public.weekly_fantasypros_pages_before_insert();

-- a page changes once, when its count is recorded; never deleted
create or replace function public.weekly_fantasypros_pages_guard()
returns trigger language plpgsql as $$
begin
    if tg_op = 'DELETE' then
        raise exception 'weekly_fantasypros_pages is append-only (DELETE).';
    end if;
    if old.verified_at is not null
       or (to_jsonb(new) - 'rows_inserted' - 'verified_at')
          is distinct from (to_jsonb(old) - 'rows_inserted' - 'verified_at') then
        raise exception 'weekly_fantasypros_pages: only an unverified page''s row count may be recorded.';
    end if;
    return new;
end;
$$;

drop trigger if exists weekly_fantasypros_pages_no_change on public.weekly_fantasypros_pages;
create trigger weekly_fantasypros_pages_no_change
    before update or delete on public.weekly_fantasypros_pages
    for each row execute function public.weekly_fantasypros_pages_guard();

-- player rows land only on a page not yet counted, in an open batch
create or replace function public.weekly_fantasypros_raw_before_insert()
returns trigger language plpgsql security definer set search_path = public, pg_temp as $$
begin
    if not exists (
        select 1
          from public.weekly_fantasypros_pages p
          join public.weekly_fantasypros_batches b on b.batch_id = p.batch_id
         where p.batch_id = new.batch_id and p.page_kind = new.page_kind
           and p.position = new.position and p.scoring_format = new.scoring_format
           and p.verified_at is null and not b.completed and b.failed_reason is null) then
        raise exception 'weekly_fantasypros_raw: page is missing, already counted, or its batch is closed';
    end if;
    new.inserted_at := now();
    return new;
end;
$$;

drop trigger if exists weekly_fantasypros_raw_insert on public.weekly_fantasypros_raw;
create trigger weekly_fantasypros_raw_insert
    before insert on public.weekly_fantasypros_raw
    for each row execute function public.weekly_fantasypros_raw_before_insert();

-- append-only: no update, no delete (truncate stays an admin act)
create or replace function public.weekly_fantasypros_raw_append_only()
returns trigger language plpgsql as $$
begin
    raise exception 'weekly_fantasypros_raw is append-only (%).', tg_op;
end;
$$;

drop trigger if exists weekly_fantasypros_raw_no_change on public.weekly_fantasypros_raw;
create trigger weekly_fantasypros_raw_no_change
    before update or delete on public.weekly_fantasypros_raw
    for each row execute function public.weekly_fantasypros_raw_append_only();

-- a batch closes once (completed or failed); its identity never changes
create or replace function public.weekly_fantasypros_batches_guard()
returns trigger language plpgsql as $$
begin
    if tg_op = 'DELETE' then
        raise exception 'weekly_fantasypros_batches is append-only (DELETE).';
    end if;
    if old.completed or old.failed_reason is not null then
        raise exception 'weekly_fantasypros_batches: batch % is closed', old.batch_id;
    end if;
    if (new.batch_id, new.source, new.season, new.pull_date, new.pages_expected, new.started_at)
       is distinct from (old.batch_id, old.source, old.season, old.pull_date, old.pages_expected, old.started_at) then
        raise exception 'weekly_fantasypros_batches: identity columns are fixed';
    end if;
    return new;
end;
$$;

drop trigger if exists weekly_fantasypros_batches_no_change on public.weekly_fantasypros_batches;
create trigger weekly_fantasypros_batches_no_change
    before update or delete on public.weekly_fantasypros_batches
    for each row execute function public.weekly_fantasypros_batches_guard();

-- ---------------------------------------------------------------------------
-- The writer's four calls.

-- open today's batch; refuses when today already has a completed batch, and
-- marks an unfinished batch from today as superseded
create or replace function public.weekly_fp_start_batch(p_season smallint, p_pages_expected smallint)
returns uuid language plpgsql security definer set search_path = public, pg_temp as $$
declare
    v_day date := (now() at time zone 'America/New_York')::date;
    v_done uuid;
    v_id uuid;
begin
    select batch_id into v_done from public.weekly_fantasypros_batches
     where source = 'fantasypros' and pull_date = v_day and completed;
    if found then
        raise exception 'weekly_fp_start_batch: % already has a completed batch (%)', v_day, v_done;
    end if;
    update public.weekly_fantasypros_batches
       set failed_reason = 'superseded by a re-run', failed_at = now()
     where source = 'fantasypros' and pull_date = v_day
       and not completed and failed_reason is null;
    insert into public.weekly_fantasypros_batches (season, pull_date, pages_expected)
    values (p_season, v_day, p_pages_expected)
    returning batch_id into v_id;
    return v_id;
end;
$$;

-- count a page's rows after its inserts, in the same transaction; a short or
-- long count raises, so the whole page rolls back and nothing lands. Returns
-- the count and the stale flag, since the writer cannot read them.
create or replace function public.weekly_fp_finish_page(
    p_batch_id uuid, p_page_kind text, p_position text, p_scoring_format text)
returns jsonb language plpgsql security definer set search_path = public, pg_temp as $$
declare
    v_expected integer;
    v_stale boolean;
    v_count integer;
begin
    select rows_expected, same_as_previous into v_expected, v_stale from public.weekly_fantasypros_pages
     where batch_id = p_batch_id and page_kind = p_page_kind
       and position = p_position and scoring_format = p_scoring_format
       and verified_at is null;
    if not found then
        raise exception 'weekly_fp_finish_page: no unverified page % % % in batch %',
            p_page_kind, p_position, p_scoring_format, p_batch_id;
    end if;
    select count(*) into v_count from public.weekly_fantasypros_raw
     where batch_id = p_batch_id and page_kind = p_page_kind
       and position = p_position and scoring_format = p_scoring_format;
    if v_count <> v_expected then
        raise exception 'weekly_fp_finish_page: % % % has % rows, expected %',
            p_page_kind, p_position, p_scoring_format, v_count, v_expected;
    end if;
    update public.weekly_fantasypros_pages
       set rows_inserted = v_count, verified_at = now()
     where batch_id = p_batch_id and page_kind = p_page_kind
       and position = p_position and scoring_format = p_scoring_format;
    return jsonb_build_object('rows_inserted', v_count, 'rows_expected', v_expected,
                              'same_as_previous', v_stale);
end;
$$;

-- record the weekly_fantasypros_pull check; never blocks the caller
create or replace function public.weekly_fp_record_check(p_ok boolean, p_error_code text, p_source text)
returns void language plpgsql security definer set search_path = public, pg_temp as $$
begin
    insert into monitoring.check_observations (check_id, run_at, ok, content_ok, error_code, source)
    values ('weekly_fantasypros_pull', clock_timestamp(), p_ok, p_ok, p_error_code, p_source)
    on conflict do nothing;
end;
$$;

-- close a batch as complete: every expected page landed, was counted, and
-- reports the same season and week. Returns what the run's comment needs.
create or replace function public.weekly_fp_complete_batch(p_batch_id uuid)
returns jsonb language plpgsql security definer set search_path = public, pg_temp as $$
declare
    b record;
    v_pages integer;
    v_open integer;
    v_rows integer;
    v_weeks integer;
    v_stale jsonb;
begin
    select * into b from public.weekly_fantasypros_batches where batch_id = p_batch_id;
    if not found or b.completed or b.failed_reason is not null then
        raise exception 'weekly_fp_complete_batch: batch % is missing or closed', p_batch_id;
    end if;
    select count(*), count(*) filter (where verified_at is null), coalesce(sum(rows_inserted), 0)
      into v_pages, v_open, v_rows
      from public.weekly_fantasypros_pages where batch_id = p_batch_id;
    if v_open > 0 or v_pages <> b.pages_expected then
        raise exception 'weekly_fp_complete_batch: % of % pages counted (% uncounted)',
            v_pages - v_open, b.pages_expected, v_open;
    end if;
    select count(distinct (season, week)) into v_weeks
      from public.weekly_fantasypros_pages where batch_id = p_batch_id;
    if v_weeks <> 1 then
        raise exception 'weekly_fp_complete_batch: pages report % different weeks', v_weeks;
    end if;
    select coalesce(jsonb_agg(jsonb_build_object('page_kind', page_kind, 'position', position,
                                                 'scoring_format', scoring_format)
                              order by page_kind, position, scoring_format), '[]'::jsonb)
      into v_stale
      from public.weekly_fantasypros_pages where batch_id = p_batch_id and same_as_previous;
    update public.weekly_fantasypros_batches
       set completed = true, completed_at = now(), pages_landed = v_pages, rows_landed = v_rows
     where batch_id = p_batch_id;
    perform public.weekly_fp_record_check(true, null, 'weekly_fp_writer');
    return jsonb_build_object(
        'season', b.season,
        'week', (select max(week) from public.weekly_fantasypros_pages where batch_id = p_batch_id),
        'pages_landed', v_pages, 'rows_landed', v_rows, 'same_as_previous', v_stale);
end;
$$;

-- close a batch as failed, with the reason; its rows stay but are never used
create or replace function public.weekly_fp_fail_batch(p_batch_id uuid, p_reason text)
returns void language plpgsql security definer set search_path = public, pg_temp as $$
begin
    if coalesce(btrim(p_reason), '') = '' then
        raise exception 'weekly_fp_fail_batch: a reason is required';
    end if;
    update public.weekly_fantasypros_batches
       set failed_reason = left(p_reason, 1000), failed_at = now()
     where batch_id = p_batch_id and not completed and failed_reason is null;
    if not found then
        raise exception 'weekly_fp_fail_batch: batch % is missing or closed', p_batch_id;
    end if;
    perform public.weekly_fp_record_check(false, 'BATCH_FAILED', 'weekly_fp_writer');
end;
$$;

-- the database's own daily check, so a run that never happens still shows red:
-- ok only when the New York day has a completed batch
create or replace function public.weekly_fp_record_daily_check()
returns void language plpgsql security definer set search_path = public, pg_temp as $$
declare
    v_day date := (now() at time zone 'America/New_York')::date;
    v_latest record;
begin
    if exists (select 1 from public.weekly_fantasypros_batches
                where source = 'fantasypros' and pull_date = v_day and completed) then
        perform public.weekly_fp_record_check(true, null, 'pg_cron');
        return;
    end if;
    select completed, failed_reason into v_latest from public.weekly_fantasypros_batches
     where source = 'fantasypros' and pull_date = v_day
     order by started_at desc limit 1;
    perform public.weekly_fp_record_check(false,
        case when not found then 'NO_BATCH_TODAY'
             when v_latest.failed_reason is not null then 'LATEST_BATCH_FAILED'
             else 'BATCH_NOT_COMPLETED' end,
        'pg_cron');
end;
$$;

insert into monitoring.check_config
    (check_id, check_type, cadence_seconds, grace_override_seconds,
     scheduler_owner_type, scheduler_owner_id, alert_policy)
values
    ('weekly_fantasypros_pull', 'http_status_and_content', 86400, 1800,
     'pg_cron', 'weekly-fantasypros-daily-check',
     '{"severity": "warn", "what": "Muse''s daily FantasyPros weekly pull completed for the New York day (public.weekly_fantasypros_batches); checked 16:00 UTC by pg_cron weekly-fantasypros-daily-check and on every completion or failure. Research input, no published value depends on it"}')
on conflict (check_id) do update set
    cadence_seconds = excluded.cadence_seconds,
    grace_override_seconds = excluded.grace_override_seconds,
    scheduler_owner_type = excluded.scheduler_owner_type,
    scheduler_owner_id = excluded.scheduler_owner_id,
    alert_policy = excluded.alert_policy,
    updated_at = now();

-- Rollback for the check: select cron.unschedule('weekly-fantasypros-daily-check');
-- delete from monitoring.check_config where check_id = 'weekly_fantasypros_pull'
-- (after its observations).
select cron.schedule('weekly-fantasypros-daily-check', '0 16 * * *',
                     $$select public.weekly_fp_record_daily_check()$$);

-- ---------------------------------------------------------------------------
-- Access.
alter table public.weekly_fantasypros_batches enable row level security;
alter table public.weekly_fantasypros_pages enable row level security;
alter table public.weekly_fantasypros_raw enable row level security;
revoke all on public.weekly_fantasypros_batches, public.weekly_fantasypros_pages,
              public.weekly_fantasypros_raw from anon, authenticated;

revoke all on function
    public.weekly_fp_start_batch(smallint, smallint),
    public.weekly_fp_finish_page(uuid, text, text, text),
    public.weekly_fp_complete_batch(uuid),
    public.weekly_fp_fail_batch(uuid, text),
    public.weekly_fp_record_check(boolean, text, text),
    public.weekly_fp_record_daily_check(),
    public.weekly_fantasypros_pages_before_insert(),
    public.weekly_fantasypros_raw_before_insert(),
    public.weekly_fantasypros_pages_guard(),
    public.weekly_fantasypros_raw_append_only(),
    public.weekly_fantasypros_batches_guard()
  from public, anon, authenticated;

-- Muse's login role. No password here; Jeremy sets it after applying.
do $$
begin
    if not exists (select 1 from pg_roles where rolname = 'weekly_fp_writer') then
        create role weekly_fp_writer login noinherit nocreatedb nocreaterole nobypassrls;
    end if;
end;
$$;

revoke all on all tables in schema public from weekly_fp_writer;
grant usage on schema public to weekly_fp_writer;
grant insert on public.weekly_fantasypros_pages, public.weekly_fantasypros_raw to weekly_fp_writer;
grant execute on function
    public.weekly_fp_start_batch(smallint, smallint),
    public.weekly_fp_finish_page(uuid, text, text, text),
    public.weekly_fp_complete_batch(uuid),
    public.weekly_fp_fail_batch(uuid, text)
  to weekly_fp_writer;

drop policy if exists weekly_fantasypros_pages_writer_insert on public.weekly_fantasypros_pages;
create policy weekly_fantasypros_pages_writer_insert on public.weekly_fantasypros_pages
    for insert to weekly_fp_writer
    with check (source = 'fantasypros' and horizon = 'week');

drop policy if exists weekly_fantasypros_raw_writer_insert on public.weekly_fantasypros_raw;
create policy weekly_fantasypros_raw_writer_insert on public.weekly_fantasypros_raw
    for insert to weekly_fp_writer
    with check (true);
