-- 005: lottery normalization (chart + incremental edge).
--
-- base_option_ev: the lottery model's expected role-change value recomputed
--   with consensus (base-rate) hazards — the role-change expectation the
--   trade chart's median already prices. The reportable lottery edge is
--   max(0, owned_option_ev - base_option_ev).
-- chart_trade_value / lottery_edge_tv: the 0-70 integer legs behind
--   implied_trade_value (= chart leg + edge leg), so the dashboard can show
--   the "12 base + 2 edge" decomposition instead of one blended number.

ALTER TABLE public.lottery_valuations
    ADD COLUMN IF NOT EXISTS base_option_ev double precision;
ALTER TABLE public.lottery_valuations
    ADD COLUMN IF NOT EXISTS chart_trade_value int;
ALTER TABLE public.lottery_valuations
    ADD COLUMN IF NOT EXISTS lottery_edge_tv int;

COMMENT ON COLUMN public.lottery_valuations.base_option_ev IS
    'Consensus (base-rate hazards, model adjustments neutralized) expected role-change value, total-VORP units. The chart median already prices roughly this much.';
COMMENT ON COLUMN public.lottery_valuations.chart_trade_value IS
    'Trade-chart leg of the implied value: chart VORP on the 0-70 integer scale.';
COMMENT ON COLUMN public.lottery_valuations.lottery_edge_tv IS
    'Lottery leg of the implied value: max(0, owned_option_ev - base_option_ev) on the 0-70 integer scale.';

DROP VIEW IF EXISTS public.v_lottery_board;
DROP VIEW IF EXISTS public.v_lottery_board;
CREATE VIEW public.v_lottery_board AS
SELECT
    v.valuation_id, v.as_of, v.player_key,
    COALESCE(p.full_name, v.player_key) AS player_name,
    v.position, v.team,
    v.lottery_score, v.option_adjusted_vorp, v.implied_trade_value,
    v.chart_trade_value, v.lottery_edge_tv,
    v.current_use_vorp, v.owned_option_ev, v.base_option_ev, v.wait_ev, v.now_wait_premium,
    v.bench_cost,
    v.p1, v.p2, v.p4, v.p6,
    v.cond_vorp_pg, v.cond_points_pg, v.cond_vorp_total, v.duration_games,
    v.duration_lo, v.duration_hi,
    v.hit_window, v.hit_week_lo, v.hit_week_hi,
    v.status, v.status_detail,
    v.acquisition_risk, v.ci_low, v.ci_high,
    v.primary_mechanism, v.secondary_mechanism, v.role_trend,
    v.n_paths, v.two_paths, v.starter_name,
    v.confidence, v.bad_variance_flag, v.bad_variance_note,
    v.roster_pct, v.availability_tier, v.availability_conf,
    v.availability_source, v.adds_24h, v.adds_7d,
    v.explanation_json, v.component_json,
    lp.name AS league_profile, lp.season, lp.teams, lp.scoring
FROM public.lottery_valuations v
LEFT JOIN public.players p ON p.id = v.player_id
JOIN public.lottery_league_profiles lp ON lp.league_profile_id = v.league_profile_id;
COMMENT ON VIEW public.v_lottery_board IS
    'Latest lottery-ticket valuations: availability tier, health status, hit windows, conditional points, lottery-implied trade value (chart leg + normalized lottery edge). Filter as_of = (SELECT MAX(as_of) ...) per league profile.';
