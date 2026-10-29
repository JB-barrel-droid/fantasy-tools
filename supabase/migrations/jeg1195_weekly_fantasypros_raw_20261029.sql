-- JEG-1195. PROPOSED, NOT APPLIED. Applying it needs Jeremy's yes naming this
-- migration. Additive: one new table, one trigger, one login role; nothing else
-- is touched, no existing row, view or published output changes.
--
-- Purpose: Muse, signed in to FantasyPros, writes the weekly projections and
-- weekly ECR rankings pages here once a day (Jeremy 2026-10-29: "i could have
-- muse run this daily", "muse can push the data right to supabase"). Raw page
-- data only: no player_key, no merging, no derived numbers. The JEG-1195
-- weekly-input producer owns identity, freshness labels and everything
-- downstream, so each of those keeps one owner.
--
-- Weekly only (Jeremy 2026-10-29: "do not blend weekly data with ROS data,
-- ever"): horizon is pinned to 'week'; rest-of-season and draft pages never
-- belong here.
--
-- Auth, least privilege: Muse connects as the login role weekly_fp_writer,
-- which can only INSERT into this table. It cannot read, update or delete
-- anything, here or elsewhere. Jeremy sets its password himself after applying
-- (alter role weekly_fp_writer password '...'), never in the repo; Muse
-- connects through the Supabase pooler as weekly_fp_writer.<project_ref>.
-- Inserts must not ask for returned rows (no RETURNING), since the role has no
-- SELECT.
-- Name: <subproject>_<entity>, subproject 'weekly'.

create table if not exists public.weekly_fantasypros_raw (
    id             bigint generated always as identity primary key,
    -- one uuid per daily pull, shared by every row of that pull
    batch_id       uuid        not null,
    source         text        not null default 'fantasypros' check (source = 'fantasypros'),
    horizon        text        not null default 'week' check (horizon = 'week'),
    page_kind      text        not null check (page_kind in ('projections', 'ecr')),
    season         smallint    not null check (season between 2026 and 2100),
    -- the week printed in the page heading, never the week requested
    week           smallint    not null check (week between 1 and 18),
    position       text        not null check (position in ('QB', 'RB', 'WR', 'TE')),
    scoring_format text        not null check (scoring_format in ('standard', 'half_ppr', 'full_ppr')),
    page_url       text        not null,
    -- true only when the page showed every player (signed in), not the top 10
    full_list      boolean     not null,
    player_name    text        not null,
    team           text,
    -- ECR rows: the rank and spread columns as shown; null on projection rows
    ecr_rank       integer,
    ecr_best       integer,
    ecr_worst      integer,
    ecr_avg        numeric(6,2),
    ecr_std        numeric(6,2),
    -- projection rows: FPTS as shown; null on ECR rows. A blank cell stays null,
    -- never 0.
    fpts           numeric(6,2),
    -- the page's other columns exactly as shown: {"header": "value", ...}
    raw_columns    jsonb       not null default '{}'::jsonb,
    pulled_at      timestamptz not null,
    inserted_at    timestamptz not null default now(),
    constraint weekly_fantasypros_raw_kind_fields check (
        (page_kind = 'ecr' and ecr_rank is not null and fpts is null)
        or (page_kind = 'projections' and ecr_rank is null)),
    -- a re-sent row in the same pull is a no-op (insert ... on conflict do nothing)
    constraint weekly_fantasypros_raw_key unique nulls not distinct
        (batch_id, page_kind, position, scoring_format, player_name, team)
);

comment on table public.weekly_fantasypros_raw is
    'JEG-1195: raw FantasyPros weekly projections and weekly ECR pages, written daily by Muse (insert-only role weekly_fp_writer). Weekly only, never rest of season. No player_key; the weekly-input producer resolves identity. Append-only.';

create index if not exists weekly_fantasypros_raw_week_idx
    on public.weekly_fantasypros_raw (season, week, page_kind, scoring_format, pulled_at);

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

alter table public.weekly_fantasypros_raw enable row level security;
revoke all on public.weekly_fantasypros_raw from anon, authenticated;

-- Muse's insert-only login role. No password here; Jeremy sets it after applying.
do $$
begin
    if not exists (select 1 from pg_roles where rolname = 'weekly_fp_writer') then
        create role weekly_fp_writer login noinherit nocreatedb nocreaterole nobypassrls;
    end if;
end;
$$;

revoke all on all tables in schema public from weekly_fp_writer;
grant usage on schema public to weekly_fp_writer;
grant insert on public.weekly_fantasypros_raw to weekly_fp_writer;

drop policy if exists weekly_fantasypros_raw_writer_insert on public.weekly_fantasypros_raw;
create policy weekly_fantasypros_raw_writer_insert on public.weekly_fantasypros_raw
    for insert to weekly_fp_writer
    with check (source = 'fantasypros' and horizon = 'week');
