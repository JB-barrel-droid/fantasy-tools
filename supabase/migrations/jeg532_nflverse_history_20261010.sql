-- JEG-532 (from JEG-525 item e, part of JEG-521). Approved by Jeremy
-- 2026-10-10 ("Approve", JEG-532). Additive: two new tables and one view.
-- Applied with Supabase MCP apply_migration; drafted as
-- sql/proposed/jeg525_nflverse_history.sql (commit 918bffc).
--
-- Changes from the draft: the view is security_invoker (like
-- v_player_game_actuals), and anon/authenticated get nothing on the new
-- tables or the view (service role only).
--
-- Purpose: keep the 2015-2025 nflverse weekly history in Supabase beside
-- public.v_player_game_actuals (2024 onward, from player_game_stats), so the
-- expected-starts parameters (docs/methodology.md ES-1, MR-24) are derived
-- from the database rather than a repo file.
--
-- Shape: one row per player-week as published by nflverse (regular season,
-- QB/RB/WR/TE), the three scorings computed the same way as
-- v_player_game_actuals (std, +0.5 per reception, +1 per reception), keyed
-- by the nflverse/GSIS id. players.metadata->>'gsis_id' carries the same id
-- for 4,613 of 4,702 players, so the view below joins to player_key where a
-- match exists (null for retired players never in our players table).
-- Coordination with G4 (a): G4 (a) extends v_player_game_actuals week by
-- week from player_game_stats for the live season; this table is closed
-- history and is not written to by the weekly jobs. The union view gives the
-- derivation one read path: history up to 2023, player_game_stats from 2024.
-- 2024-2025 exists in both; the view takes player_game_stats for those years
-- (the repo test shows the hazards agree within 2 points).

create table if not exists public.nflverse_player_week_actuals (
  season      smallint    not null check (season between 1999 and 2100),
  week        smallint    not null check (week between 1 and 22),
  gsis_id     text        not null,
  player_name text        not null,
  position    text        not null check (position in ('QB', 'RB', 'WR', 'TE')),
  team        text        not null,
  actual_std  numeric(6,2) not null,
  actual_half numeric(6,2) not null,
  actual_ppr  numeric(6,2) not null,
  source      text        not null default 'nflverse stats_player_week',
  loaded_at   timestamptz not null default now(),
  primary key (season, week, gsis_id)
);

comment on table public.nflverse_player_week_actuals is
  'nflverse weekly fantasy points, regular season, QB/RB/WR/TE, 2015-2025 (JEG-525). Closed history; loaded by pipelines/load_nflverse_history.py. A 0-point row means the player dressed.';

create table if not exists public.nflverse_team_weeks (
  season    smallint not null,
  week      smallint not null,
  team      text     not null,
  loaded_at timestamptz not null default now(),
  primary key (season, team, week)
);

comment on table public.nflverse_team_weeks is
  'Weeks each NFL team played a regular-season game, 2015-2025 (nflverse schedules/games.csv). The missing week is the bye (JEG-525).';

create index if not exists nflverse_player_week_actuals_pos_season
  on public.nflverse_player_week_actuals (position, season);

alter table public.nflverse_player_week_actuals enable row level security;
alter table public.nflverse_team_weeks enable row level security;
-- No anon/authenticated policies: read by service role (pipelines) only.
revoke all on public.nflverse_player_week_actuals from anon, authenticated;
revoke all on public.nflverse_team_weeks from anon, authenticated;

create or replace view public.nflverse_v_player_week_actuals_all
with (security_invoker = true) as
select h.season, h.week, h.gsis_id, p.player_key, h.position, h.team,
       h.actual_std, h.actual_half, h.actual_ppr, 'nflverse'::text as origin
from public.nflverse_player_week_actuals h
left join public.players p on p.metadata->>'gsis_id' = h.gsis_id
where h.season < 2024
union all
select g.season, g.week, p.metadata->>'gsis_id', p.player_key, p.position, t.abbreviation,
       round(a.actual_std, 2), round(a.actual_half, 2), round(a.actual_ppr, 2), 'player_game_stats'
from public.v_player_game_actuals a
join public.games g on g.id = a.game_id
join public.players p on p.id = a.player_id
join public.teams t on t.id = a.team_id
where p.position in ('QB', 'RB', 'WR', 'TE');

revoke all on public.nflverse_v_player_week_actuals_all from anon, authenticated;

-- Verification after the load (pipelines/load_nflverse_history.py --apply
-- checks these and fails otherwise):
--   select count(*) from public.nflverse_player_week_actuals;          -- 61,977
--   select count(distinct (season, team)) from public.nflverse_team_weeks; -- 352
