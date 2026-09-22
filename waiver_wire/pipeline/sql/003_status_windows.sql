-- 003: health status + hit windows + conditional points for the lottery board.
--
-- status / status_detail: IR | PUP | Out | Doubtful | Questionable | Inactive
--   | Healthy, from 2026 nflverse roster status (RES=R-code -> IR, P-code ->
--   PUP) with the weekly injury report overlaid on active-roster players.
--   An IR stash is a different proposition than a plug-and-play add: players
--   stay scored but render with an IR badge.
-- cond_points_pg: conditional full-PPR points/game if the breakout hits
--   (replacement level + conditional VORP/g) — the plain-language number.
-- hit_window / hit_week_lo / hit_week_hi: interquartile range (middle 50%)
--   of the season-extended first-breakout-time distribution, as NFL weeks.
-- duration_lo / duration_hi: p25/p75 of the valuable-role duration
--   distribution (empirical absence mixture for contingent, geometric role
--   survival for emergent/ambiguous).

ALTER TABLE public.lottery_valuations
    ADD COLUMN IF NOT EXISTS status text,
    ADD COLUMN IF NOT EXISTS status_detail text,
    ADD COLUMN IF NOT EXISTS cond_points_pg numeric,
    ADD COLUMN IF NOT EXISTS hit_window text,
    ADD COLUMN IF NOT EXISTS hit_week_lo int,
    ADD COLUMN IF NOT EXISTS hit_week_hi int,
    ADD COLUMN IF NOT EXISTS duration_lo numeric,
    ADD COLUMN IF NOT EXISTS duration_hi numeric;

COMMENT ON COLUMN public.lottery_valuations.status IS
    'IR | PUP | Out | Doubtful | Questionable | Inactive | Healthy (2026 nflverse).';
COMMENT ON COLUMN public.lottery_valuations.cond_points_pg IS
    'Conditional full-PPR points/game if the breakout hits (replacement + cond VORP/g).';
COMMENT ON COLUMN public.lottery_valuations.hit_window IS
    'IQR of first-breakout-time distribution, e.g. Weeks 3-6.';

DROP VIEW IF EXISTS public.v_lottery_board;
CREATE VIEW public.v_lottery_board AS
SELECT
    v.valuation_id, v.as_of, v.player_key,
    COALESCE(p.full_name, v.player_key) AS player_name,
    v.position, v.team,
    v.lottery_score, v.option_adjusted_vorp,
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
    'Latest lottery-ticket valuations: availability tier, health status, hit windows, conditional points. Filter as_of = (SELECT MAX(as_of) ...) per league profile.';
