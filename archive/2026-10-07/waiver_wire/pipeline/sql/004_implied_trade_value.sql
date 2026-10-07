-- 004: lottery-implied trade value.
--
-- implied_trade_value: the player's trade-chart value with the lottery
-- option EV backed in, so lottery tickets are comparable on the same 0-70
-- integer scale as the trade value chart and rank above generic waiver
-- fodder (who sit at ~0-2).
--
-- Formula (documented in lottery/README.md):
--   implied_ROS_VORP_i = chart_VORP_i + owned_option_EV_i
--   implied_trade_value_i = round(70 * implied_ROS_VORP_i / max_chart_VORP)
-- where chart_VORP_i = max(0, blend_ros_ppr_i - replacement_ros_pos) uses the
-- chart's own primary (Vegas-precedence) ROS points and its roster-model
-- replacement (12-team, 1QB/2RB/3WR/1TE/1FLEX, 6 bench, 8%-QB/TE bench mix),
-- and owned_option_EV_i is the lottery model's expected future role-change
-- value in total-VORP units. The chart's median already embeds some breakout
-- probability, so this is an upper-ish bound on the option increment.

ALTER TABLE public.lottery_valuations
    ADD COLUMN IF NOT EXISTS implied_trade_value int;

COMMENT ON COLUMN public.lottery_valuations.implied_trade_value IS
    'Lottery-implied trade value on the chart 0-70 integer scale: chart VORP + lottery option EV, rescaled by 70/max chart VORP.';

DROP VIEW IF EXISTS public.v_lottery_board;
CREATE VIEW public.v_lottery_board AS
SELECT
    v.valuation_id, v.as_of, v.player_key,
    COALESCE(p.full_name, v.player_key) AS player_name,
    v.position, v.team,
    v.lottery_score, v.option_adjusted_vorp, v.implied_trade_value,
    v.current_use_vorp, v.owned_option_ev, v.wait_ev, v.now_wait_premium,
    v.bench_cost,
    v.p1, v.p2, v.p4, v.p6,
    v.cond_vorp_pg, v.cond_points_pg, v.cond_vorp_total, v.duration_games,
    v.duration_lo, v.duration_hi,
    v.hit_window, v.hit_week_lo, v.hit_week_hi,
    v.status, v.status_detail,
    v.acquisition_risk, v.ci_low, v.ci_high,
    v.primary_mechanism, v.secondary_mechanism, v.role_trend,
    v.confidence, v.bad_variance_flag, v.bad_variance_note,
    v.roster_pct, v.availability_tier, v.availability_conf,
    v.availability_source, v.adds_24h, v.adds_7d,
    v.explanation_json, v.component_json,
    lp.name AS league_profile, lp.season, lp.teams, lp.scoring
FROM public.lottery_valuations v
LEFT JOIN public.players p ON p.id = v.player_id
JOIN public.lottery_league_profiles lp ON lp.league_profile_id = v.league_profile_id;
COMMENT ON VIEW public.v_lottery_board IS
    'Latest lottery-ticket valuations: availability tier, health status, hit windows, conditional points, lottery-implied trade value. Filter as_of = (SELECT MAX(as_of) ...) per league profile.';
