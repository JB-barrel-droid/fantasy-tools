-- JEG-438 stage 2: one canonical player table + per-source name mappings.
-- Applied 2026-10-07 via Supabase MCP apply_migration (jeg438_player_identity).
-- Additive only: two new tables and one view. No existing row is changed or
-- deleted. See docs/identity-model.md.
--
-- Canonical table: public.players (unchanged). player_key is the identity.
-- Cross-ids:        public.external_id_map (unchanged; sleeper/espn/yahoo/nflverse).
-- Name mappings:    public.player_name_aliases (new). How each source spells a
--                   player, mapped to player_key, with method/confidence/status.
-- Nightly counts:   public.player_identity_reconcile_runs (new).

create table if not exists public.player_name_aliases (
    id                 bigint generated always as identity primary key,
    -- the source that spells the name this way; '*' = any source
    source             text not null,
    source_player_name text not null,
    -- pipelines/lib/player_resolver.py norm_key(source_player_name); the
    -- resolver recomputes it on load, this column is the uniqueness grain
    norm_name          text not null,
    -- '' when the alias holds for any position
    position           text not null default '',
    source_player_id   text,
    player_key         bigint references public.players (player_key),
    status             text not null
        check (status in ('verified', 'provisional', 'unmatched', 'review', 'rejected')),
    method             text not null,
    confidence         numeric(4, 3) check (confidence is null or (confidence >= 0 and confidence <= 1)),
    team               text,
    candidate_keys     bigint[],
    first_seen_at      timestamptz not null default now(),
    last_seen_at       timestamptz not null default now(),
    seen_count         integer not null default 1,
    verified_at        timestamptz,
    verified_by        text,
    notes              text,
    constraint player_name_aliases_grain unique (source, norm_name, position),
    -- matched rows carry a key; unmatched rows never do (missing is null)
    constraint player_name_aliases_key_matches_status check (
        case status
            when 'verified' then player_key is not null
            when 'provisional' then player_key is not null
            when 'unmatched' then player_key is null
            else true
        end)
);

comment on table public.player_name_aliases is
    'JEG-438: how each source names a player, mapped to public.players.player_key. '
    'verified = safe to use; provisional = fuzzy temporary match (flagged, re-checked nightly); '
    'unmatched/review = no safe match yet (never guessed); rejected = a provisional match the '
    'nightly job disproved. Read by pipelines/lib/player_resolver.py via data/inputs/player_registry.json.';

create index if not exists player_name_aliases_player_key_idx on public.player_name_aliases (player_key);
create index if not exists player_name_aliases_status_idx on public.player_name_aliases (status);
create index if not exists player_name_aliases_source_id_idx
    on public.player_name_aliases (source, source_player_id) where source_player_id is not null;

create table if not exists public.player_identity_reconcile_runs (
    id            bigint generated always as identity primary key,
    run_at        timestamptz not null default now(),
    run_label     text,
    source        text not null,
    total_aliases integer not null default 0,
    verified      integer not null default 0,
    provisional   integer not null default 0,
    unmatched     integer not null default 0,
    review        integer not null default 0,
    promoted      integer not null default 0,
    queued        integer not null default 0,
    rejected      integer not null default 0,
    players_added integer not null default 0,
    xrefs_added   integer not null default 0,
    detail        jsonb not null default '{}'::jsonb
);

comment on table public.player_identity_reconcile_runs is
    'JEG-438: one row per source per nightly identity reconcile run (player-identity-reconcile.yml).';

create or replace view public.player_identity_unresolved_v as
select source,
       count(*) filter (where status = 'provisional') as provisional,
       count(*) filter (where status = 'unmatched')   as unmatched,
       count(*) filter (where status = 'review')      as review,
       count(*) filter (where status = 'verified')    as verified,
       max(last_seen_at)                              as last_seen_at
from public.player_name_aliases
group by source;

-- ---------------------------------------------------------------------------
-- Backfill: every mapping that exists today, so nothing currently matched breaks.
-- Target keys resolve to public.players exactly once (unique), else the alias
-- is stored as 'review' with its candidates, never guessed.
-- ---------------------------------------------------------------------------

-- SQL mirror of player_resolver.norm_key for this backfill only (session-local).
create or replace function pg_temp.ddf_nk(x text) returns text language sql immutable as $$
    select btrim(regexp_replace(
               regexp_replace(
                   regexp_replace(lower(coalesce(x, '')), '[''’‘`.]', '', 'g'),
                   '[^a-z0-9]+', ' ', 'g'),
               '\s+(jr|sr|ii|iii|iv|v)\s*$', ''))
$$;

-- Normalized players index (session-local temp table; keeps the joins fast).
create temp table ddf_pnk on commit drop as
    select player_key, position, pg_temp.ddf_nk(full_name) as k from public.players;
create index on ddf_pnk (k);

-- (a) the chart identity table already in Supabase (player_identities +
--     player_identity_aliases, the source of data/inputs/player_identity_map.json).
with src as (
    select case a.source when 'chart' then '*' when 'players_table' then '*' else a.source end as source,
           a.alias, i.canonical_name, i.pos
    from public.player_identity_aliases a
    join public.player_identities i on i.id = a.identity_id
),
cand as (
    select s.*,
           (select array_agg(p.player_key order by p.player_key) from ddf_pnk p
             where p.k = pg_temp.ddf_nk(s.canonical_name)
               and (s.pos is null or p.position = s.pos)) as by_canon,
           (select array_agg(p.player_key order by p.player_key) from ddf_pnk p
             where p.k = pg_temp.ddf_nk(s.alias)
               and (s.pos is null or p.position = s.pos)) as by_alias
    from src s
),
pick as (
    select c.*,
           case when cardinality(c.by_canon) = 1 then c.by_canon[1]
                when c.by_canon is null and cardinality(c.by_alias) = 1 then c.by_alias[1] end as key,
           coalesce(c.by_canon, c.by_alias) as cands
    from cand c
)
insert into public.player_name_aliases
    (source, source_player_name, norm_name, position, player_key, status, method,
     confidence, candidate_keys, verified_at, verified_by, notes)
select source, alias, pg_temp.ddf_nk(alias), coalesce(pos, ''),
       key,
       case when key is not null then 'verified' else 'review' end,
       'backfill:player_identity_aliases', case when key is not null then 1.0 end,
       cands, case when key is not null then now() end,
       case when key is not null then 'jeg438-backfill' end,
       'canonical ' || canonical_name
from pick
on conflict (source, norm_name, position) do nothing;

-- (b) saver spelling aliases (build_ddf_two_tier_leg.ALIASES, verified 2026-09-19)
--     and the JEG-438 known-unmatched names, each checked by hand against
--     public.players on 2026-10-07 (key, full_name, position).
with v(source, alias, pos, key, why) as (values
    ('*', 'Cameron Ward',        'QB', null::bigint, 'ALIASES cameron ward -> cam ward'),
    ('*', 'Cameron Skattebo',    'RB', null,         'ALIASES cameron skattebo -> cam skattebo'),
    ('*', 'Travis Etienne Jr.',  'RB', null,         'ALIASES travis etienne jr -> travis etienne'),
    ('*', 'Michael Pittman Jr.', 'WR', null,         'ALIASES michael pittman jr -> michael pittman'),
    ('*', 'Kenny Gainwell',      'RB', 785,  'JEG-438 known unmatched; players 785 Kenneth Gainwell'),
    ('*', 'Joshua Palmer',       'WR', 822,  'JEG-438 known unmatched; players 822 Josh Palmer'),
    ('*', 'Chigoziem Okonkwo',   'TE', 4247, 'JEG-438 known unmatched; players 4247 Chig Okonkwo'),
    ('*', 'Jalen Cropper',       'WR', 1268, 'JEG-438 known unmatched; players 1268 Jalen Moreno-Cropper'),
    ('*', 'J. Sturdivant',       'WR', 2201, 'JEG-438 known unmatched; players 2201 J. Michael Sturdivant'),
    ('*', 'Jalen Sturdivant',    'WR', 2201, 'JEG-438 spelling of 2201 J. Michael Sturdivant'),
    ('*', 'Mitch Trubisky',      'QB', 4214, 'JEG-438 known unmatched; players 4214 Mitchell Trubisky'),
    ('*', 'Audric Estime',       'RB', 4642, 'JEG-438 known ambiguous in Sleeper; players has exactly one: 4642')
),
k as (
    select v.*,
           coalesce(v.key,
               (select min(p.player_key) from ddf_pnk p
                 where p.k = pg_temp.ddf_nk(
                       case v.alias when 'Cameron Ward' then 'Cam Ward'
                                    when 'Cameron Skattebo' then 'Cam Skattebo'
                                    when 'Travis Etienne Jr.' then 'Travis Etienne'
                                    when 'Michael Pittman Jr.' then 'Michael Pittman' end)
                   and p.position = v.pos
                 having count(*) = 1)) as resolved
    from v
)
insert into public.player_name_aliases
    (source, source_player_name, norm_name, position, player_key, status, method,
     confidence, verified_at, verified_by, notes)
select source, alias, pg_temp.ddf_nk(alias), pos, resolved,
       case when resolved is not null then 'verified' else 'review' end,
       'backfill:manual', 1.0, now(), 'jeg438-backfill', why
from k
on conflict (source, norm_name, position) do update
    set player_key = excluded.player_key, status = excluded.status,
        method = excluded.method, notes = excluded.notes,
        verified_at = excluded.verified_at, verified_by = excluded.verified_by
    where public.player_name_aliases.status <> 'verified';
