-- 005_starter_paths.sql — starter identity, multi-path model, path sentences.
-- Applied 2026-09-13 via the Supabase Management API (see bin/mgmt.py).
-- Additive: no existing columns touched.

alter table public.lottery_valuations
  add column if not exists starter_name text;
alter table public.lottery_valuations
  add column if not exists two_paths boolean not null default false;
alter table public.lottery_valuations
  add column if not exists n_paths int not null default 1;

-- one row per live path per candidate; the dashboard's "two ways to win"
-- badge is: select player_key ... group by player_key
--            having count(*) filter (where breakout_p4 >= 0.10) >= 2
create table if not exists public.lottery_paths (
    path_id uuid primary key default gen_random_uuid(),
    model_run_id uuid references public.lottery_model_runs(model_run_id),
    player_id uuid references public.players(id),
    player_key text not null,
    league_profile_id uuid references public.lottery_league_profiles(league_profile_id),
    as_of timestamptz not null default now(),
    mechanism text not null,          -- contingent | emergent | ambiguous | signing
    path_rank int not null,           -- 1 = lead path by EV contribution
    breakout_p1 numeric, breakout_p2 numeric,
    breakout_p4 numeric, breakout_p6 numeric,
    cond_vorp_pg numeric,             -- conditional VORP/game on this path
    cond_points_pg numeric,           -- replacement + cond VORP (full PPR)
    usable_value numeric,             -- cond VORP x usable games (VORP units)
    ev_contribution numeric,          -- P6 x usable_value x q
    duration_exp numeric, duration_lo numeric, duration_hi numeric,
    path_to_relevance text,           -- one concrete catalyst sentence
    blocker text,                     -- short noun phrase
    starter_name text,                 -- contingent only
    starter_injury_sentence text,      -- contingent only
    acquisition_risk numeric
);
create index if not exists lottery_paths_player
  on public.lottery_paths (player_key, as_of desc);
create index if not exists lottery_paths_badge
  on public.lottery_paths (league_profile_id, as_of desc)
  where breakout_p4 >= 0.10;

-- v_lottery_board: existing column order preserved; new columns appended.
create or replace view public.v_lottery_board as
select v.valuation_id, v.as_of, v.player_key,
       coalesce(p.full_name, v.player_key) as player_name,
       v."position", v.team, v.lottery_score, v.option_adjusted_vorp,
       v.implied_trade_value, v.current_use_vorp, v.owned_option_ev,
       v.wait_ev, v.now_wait_premium, v.bench_cost,
       v.p1, v.p2, v.p4, v.p6,
       v.cond_vorp_pg, v.cond_points_pg, v.cond_vorp_total,
       v.duration_games, v.duration_lo, v.duration_hi,
       v.hit_window, v.hit_week_lo, v.hit_week_hi,
       v.status, v.status_detail, v.acquisition_risk,
       v.ci_low, v.ci_high, v.primary_mechanism, v.secondary_mechanism,
       v.role_trend, v.confidence,
       v.bad_variance_flag, v.bad_variance_note,
       v.roster_pct, v.availability_tier, v.availability_conf,
       v.availability_source, v.adds_24h, v.adds_7d,
       v.explanation_json, v.component_json,
       lp.name as league_profile, lp.season, lp.teams, lp.scoring,
       v.starter_name, v.two_paths, v.n_paths
from lottery_valuations v
left join players p on p.id = v.player_id
join lottery_league_profiles lp on lp.league_profile_id = v.league_profile_id;
