-- JEG-944 (parent JEG-943): store every source's forward projections each week.
-- Decided by Jeremy 2026-10-23: "start storing CBS ROS and Razzball week-ahead
-- projections now (every week, append-only, with the capture timestamp and
-- source week)", widened the same day: "We should be saving projections for all
-- weeks ahead, not just one week ahead."
--
-- One new table, nothing else. No view, function or published output reads it;
-- it exists so each source can later be scored against actuals (JEG-945).
-- Rows are written by pipelines/save_espn_weekly.py (espn, every future week),
-- pipelines/save_cbsros_references.py (cbs: ROS, current week, next week) and
-- pipelines/save_razzball_references.py (razzball: ROS only), and once by
-- pipelines/backfill_projection_captures.py (week-history ROS values).
-- Name: <subproject>_<entity> with subproject 'source' (cross-source), as
-- source_trade_values.

create table if not exists public.source_projection_captures (
    id            bigint generated always as identity primary key,
    source        text        not null check (source in ('espn', 'cbs', 'razzball')),
    season        smallint    not null,
    -- the chain's content week when the capture was taken (pipelines/nfl_week.py)
    source_week   smallint    not null check (source_week between 1 and 18),
    capture_at    timestamptz not null,
    horizon       text        not null check (horizon in ('week', 'ros')),
    -- week the projection is for; 0 = rest of season (horizon 'ros')
    target_week   smallint    not null check (target_week between 0 and 18),
    player_key    bigint      not null references public.players (player_key),
    scoring_format text       not null check (scoring_format in ('standard', 'half_ppr', 'full_ppr')),
    -- points: the source's total for target_week, or its ROS total; null when the
    -- source gives per-game only. ppg: per-game, null when the source gives only a
    -- week total. games: games behind a ROS total/ppg when published.
    points        numeric(8,2),
    ppg           numeric(8,3),
    games         numeric(5,2),
    basis         text        not null,
    batch_id      uuid,
    constraint source_projection_captures_horizon_week check (
        (horizon = 'ros' and target_week = 0) or (horizon = 'week' and target_week between 1 and 18)),
    constraint source_projection_captures_has_value check (points is not null or ppg is not null),
    -- one capture per source per content week: the first run of a week wins and a
    -- later run the same week is a no-op (insert ... on conflict do nothing).
    constraint source_projection_captures_key unique
        (source, season, source_week, horizon, target_week, player_key, scoring_format)
);

comment on table public.source_projection_captures is
    'JEG-944: append-only history of what ESPN (every future week), CBS (ROS, current week, next week) and Razzball (ROS) projected, per capture week and target week. Not read by any published output. Service role only.';

create index if not exists source_projection_captures_lookup_idx
    on public.source_projection_captures (source, season, source_week, horizon);
create index if not exists source_projection_captures_player_idx
    on public.source_projection_captures (player_key, season, target_week);

-- append-only: no update, no delete (truncate stays an admin act)
create or replace function public.source_projection_captures_append_only()
returns trigger language plpgsql as $$
begin
    raise exception 'source_projection_captures is append-only (%).', tg_op;
end;
$$;

drop trigger if exists source_projection_captures_no_change on public.source_projection_captures;
create trigger source_projection_captures_no_change
    before update or delete on public.source_projection_captures
    for each row execute function public.source_projection_captures_append_only();

alter table public.source_projection_captures enable row level security;
revoke all on public.source_projection_captures from anon, authenticated;
