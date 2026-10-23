-- JEG-949 (child of JEG-943). PROPOSED, NOT APPLIED. Applying it needs Jeremy's
-- OK (multiple choice in the PR). Additive: one new table, nothing else touched,
-- no existing row or view changes, so no shown value can move.
--
-- Purpose: one-hop sleeper_id -> player_key / gsis_id lookup for the Sleeper
-- (RotoWire) weekly projection history, so research reads it from the database
-- instead of re-deriving it. public.players carries sleeper_id in metadata for
-- only 57 of 4,702 rows and gsis_id for 4,613, and Sleeper itself no longer
-- supplies gsis_id for most current players, so the chain is built outside the
-- DB (pipelines/sleeper_projection_idmap.py: Sleeper gsis, DynastyProcess ids by
-- sleeper/sportradar/espn id, every answering layer must agree) and stored here.
--
-- Rows: data/inputs/sleeper_projection_idmap.csv (1,275 rows on 2026-10-23:
-- 902 matched, 367 gsis_not_in_players = retired before 2025, 2 conflict,
-- 4 unmapped). player_key is null unless status = 'matched'. Loading is a
-- separate, also-unapplied step (service role only).

create table if not exists public.sleeper_player_ids (
  sleeper_id            text primary key,
  gsis_id               text,
  player_key            bigint references public.players (player_key),
  status                text   not null check (status in ('matched', 'gsis_not_in_players', 'conflict', 'unmapped', 'name_review')),
  gsis_source           text,
  suggested_player_key  bigint,   -- exact name+position candidate for human review; never used for joins
  source_name           text   not null,
  source_position       text,
  loaded_at             timestamptz not null default now(),
  check ((status = 'matched') = (player_key is not null))
);

comment on table public.sleeper_player_ids is
  'Sleeper player id to player_key / nflverse gsis_id for the Sleeper (RotoWire) weekly projection history (JEG-949). player_key only where the gsis id matches public.players and the last name agrees; conflicts and unmapped players stay null.';

create index if not exists sleeper_player_ids_gsis on public.sleeper_player_ids (gsis_id);

alter table public.sleeper_player_ids enable row level security;
revoke all on public.sleeper_player_ids from anon, authenticated;
-- Service role only, like nflverse_player_week_actuals.
