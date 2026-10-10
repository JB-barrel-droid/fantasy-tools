-- JEG-521 G4: start storing what measurement needs (pipeline only, no value change).
--
-- (a) ESPN weekly actuals go into the existing public.player_game_stats (the
--     table under v_player_game_actuals) and (b) ESPN weekly projections into
--     the existing public.projection_snapshots (source 'espn' is already
--     allowed). Neither needs a schema change; both are written by
--     pipelines/save_espn_weekly.py from espn-weekly-store.yml.
-- (c) needs one new table: public.injuries keeps only the latest status per
--     player (unique on player_name, team, source), so it cannot hold a
--     history. Approved by Jeremy 2026-10-09 (JEG-521 session, "Approve the
--     table").

create table if not exists public.player_status_history (
    snapshot_date          date        not null,
    source                 text        not null default 'sleeper',
    sleeper_id             text        not null,
    player_key             bigint      references public.players (player_key),
    full_name              text,
    position               text        not null check (position in ('QB', 'RB', 'WR', 'TE')),
    team                   text,
    status                 text,
    injury_status          text,
    injury_body_part       text,
    injury_start_date      date,
    practice_participation text,
    depth_chart_position   text,
    depth_chart_order      integer,
    news_updated           timestamptz,
    fetched_at             timestamptz not null default now(),
    primary key (snapshot_date, sleeper_id)
);

comment on table public.player_status_history is
    'JEG-521 G4 (c): one row per Sleeper QB/RB/WR/TE per day (America/Chicago date), on a team or carrying an injury status. Sleeper fields unchanged. player_key null when ids and the name resolver cannot place him (kept so history is never lost). Written by pipelines/save_player_status_history.py (player-status-history.yml, pg_cron). Service role only.';

create index if not exists player_status_history_player_idx
    on public.player_status_history (player_key, snapshot_date);

alter table public.player_status_history enable row level security;
revoke all on public.player_status_history from anon, authenticated;

-- Schedules (pg_cron is the only scheduler; the workflows have no GitHub
-- schedule:). Times in UTC; CDT = UTC-5.
--   espn-weekly-store-live      12:40 daily  (07:40 CDT): actuals after the
--     last game of a week, projections captured daily (change-only).
--   espn-weekly-store-sunday    16:20 Sunday (11:20 CDT): the last
--     projections before the early kickoffs.
--   player-status-history-live  13:10 daily  (08:10 CDT).
--   player-status-history-sunday 16:30 Sunday (11:30 CDT): game-day status
--     overwrites the morning row for that date.
select cron.schedule(
    'espn-weekly-store-live',
    '40 12 * * *',
    $$SELECT public.dispatch_gha_workflow('espn-weekly-store.yml', '{"mode": "write"}'::jsonb)$$
);
select cron.schedule(
    'espn-weekly-store-sunday',
    '20 16 * * 0',
    $$SELECT public.dispatch_gha_workflow('espn-weekly-store.yml', '{"mode": "write"}'::jsonb)$$
);
select cron.schedule(
    'player-status-history-live',
    '10 13 * * *',
    $$SELECT public.dispatch_gha_workflow('player-status-history.yml', '{"mode": "write"}'::jsonb)$$
);
select cron.schedule(
    'player-status-history-sunday',
    '30 16 * * 0',
    $$SELECT public.dispatch_gha_workflow('player-status-history.yml', '{"mode": "write"}'::jsonb)$$
);

insert into monitoring.check_config
    (check_id, check_type, cadence_seconds, grace_override_seconds,
     scheduler_owner_type, scheduler_owner_id, alert_policy)
values
    ('espn_weekly_store', 'http_status_and_content', 86400, 7200,
     'github_actions', 'espn-weekly-store.yml',
     '{"severity": "warn", "what": "ESPN weekly actuals stored in player_game_stats and weekly projections in projection_snapshots (daily 12:40 UTC via pg_cron espn-weekly-store-live; JEG-521 G4)"}'),
    ('player_status_history', 'http_status_and_content', 86400, 7200,
     'github_actions', 'player-status-history.yml',
     '{"severity": "warn", "what": "Daily Sleeper status row per QB/RB/WR/TE in public.player_status_history (13:10 UTC via pg_cron player-status-history-live; JEG-521 G4)"}')
on conflict (check_id) do update set
    cadence_seconds = excluded.cadence_seconds,
    grace_override_seconds = excluded.grace_override_seconds,
    scheduler_owner_id = excluded.scheduler_owner_id,
    alert_policy = excluded.alert_policy,
    updated_at = now();
