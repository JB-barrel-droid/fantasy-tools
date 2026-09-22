-- 002: real availability layer for the lottery board.
-- Replaces the ECR-rank availability proxy with observed ownership data.
-- roster_pct: FantasyPros ROST% (share of FP leagues rostering the player),
--   scraped from fantasypros.com/nfl/stats/{rb,wr,te}.php (free, public page).
-- availability_tier: 'available' | 'likely-owned' | 'unknown'
--   available    = roster_pct < 50  (plausibly on waivers in a typical 12-team league)
--   unknown      = 50 <= roster_pct < 70 (gray zone)
--   likely-owned = roster_pct >= 70
--   Players missing from FP pages fall back to an ECR-rank + Sleeper-trending
--   composite (source='ecr+sleeper composite'), confidence capped at Low.
-- availability_conf: High | Medium | Low (confidence in the tier call).
-- adds_24h / adds_7d: Sleeper trending-add counts (free API), supporting signal.

ALTER TABLE public.lottery_valuations
    ADD COLUMN IF NOT EXISTS roster_pct numeric,
    ADD COLUMN IF NOT EXISTS availability_tier text,
    ADD COLUMN IF NOT EXISTS availability_conf text,
    ADD COLUMN IF NOT EXISTS availability_source text,
    ADD COLUMN IF NOT EXISTS adds_24h bigint,
    ADD COLUMN IF NOT EXISTS adds_7d bigint;
CREATE INDEX IF NOT EXISTS ix_lval_avail
    ON public.lottery_valuations (league_profile_id, as_of, availability_tier, lottery_score DESC);

COMMENT ON COLUMN public.lottery_valuations.roster_pct IS
    'FantasyPros ROST%: share of FP leagues rostering the player (observed ownership).';
COMMENT ON COLUMN public.lottery_valuations.availability_tier IS
    'available | likely-owned | unknown — waiver availability call for a typical 12-team league.';

CREATE OR REPLACE VIEW public.v_lottery_board AS
SELECT
    v.valuation_id, v.as_of, v.player_key,
    COALESCE(p.full_name, v.player_key) AS player_name,
    v.position, v.team,
    v.lottery_score, v.option_adjusted_vorp,
    v.current_use_vorp, v.owned_option_ev, v.wait_ev, v.now_wait_premium,
    v.bench_cost,
    v.p1, v.p2, v.p4, v.p6,
    v.cond_vorp_pg, v.cond_vorp_total, v.duration_games,
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
    'Latest lottery-ticket valuations joined to canonical player names, incl. availability tier. Filter as_of = (SELECT MAX(as_of) ...) per league profile.';
