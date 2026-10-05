-- JEG-397: anon-facing weekly contract.
-- (1) api.v_current_weekly_signals — explicit field allowlist. No raw
--     source_manifest (it leaks absolute bundle_path + loader fingerprints),
--     no engine-internal per-stat JSON (fds_projection_stats,
--     fds_stat_sources, vegas_stats_used).
-- (2) api.weekly_dashboard_status — exactly one row, always, even with zero
--     runs: published season/week, bundle build time, publication time,
--     signal count, has_current.
-- Signal fields are extracted as text (->>) — robust against NULLs and
-- future type drift; the board is a display surface.
-- Manifest key: new loader writes bundle_built_at; older runs used built_at.
-- Apply via the Supabase SQL editor, then: NOTIFY pgrst, 'reload schema';

-- (1) Allowlisted signals view (replaces the mirror of the public view).
CREATE OR REPLACE VIEW api.v_current_weekly_signals
WITH (security_invoker = false, security_barrier = true)
AS
SELECT r.season,
       r.week,
       r.run_id,
       r.created_at AS run_created_at,  -- proxy for publication time (no published_at column; see JEG-397)
       COALESCE(r.source_manifest ->> 'bundle_built_at',
                r.source_manifest ->> 'built_at')::timestamptz AS bundle_built_at,
       s.player_key,
       s.position,
       s.team,
       s.signal ->> 'name'            AS name,
       s.signal ->> 'direction'       AS direction,
       s.signal ->> 'delta'           AS delta,
       s.signal ->> 'abs_delta'       AS abs_delta,
       s.signal ->> 'pts_delta_adj'   AS pts_delta_adj,
       s.signal ->> 'pts_delta_ppr'   AS pts_delta_ppr,
       s.signal ->> 'post_worthy'     AS post_worthy,
       s.signal ->> 'worthy_reason'   AS worthy_reason,
       s.signal ->> 'vegas_std'       AS vegas_std,
       s.signal ->> 'vegas_half'      AS vegas_half,
       s.signal ->> 'vegas_ppr'       AS vegas_ppr,
       s.signal ->> 'expert_std'      AS expert_std,
       s.signal ->> 'expert_half'     AS expert_half,
       s.signal ->> 'expert_ppr'      AS expert_ppr,
       s.signal ->> 'espn_std'        AS espn_std,
       s.signal ->> 'espn_half'       AS espn_half,
       s.signal ->> 'espn_ppr'        AS espn_ppr,
       s.signal ->> 'vegas_pos_rank'  AS vegas_pos_rank,
       s.signal ->> 'ecr_pos_rank'    AS ecr_pos_rank,
       s.signal ->> 'ecr_official'    AS ecr_official,
       s.signal ->> 'n_pos'           AS n_pos,
       s.signal ->> 'pos_level_gap'   AS pos_level_gap,
       s.signal ->> 'td_p_yes'        AS td_p_yes,
       s.signal ->> 'expert_td_exp'   AS expert_td_exp,
       s.signal ->> 'vegas_leg'       AS vegas_leg,
       s.signal ->> 'coverage_ok'     AS coverage_ok,
       s.signal ->> 'vegas_provenance' AS vegas_provenance,
       s.signal ->> 'injury_flag'     AS injury_flag,
       s.signal ->> 'injury_note'     AS injury_note,
       s.created_at AS signal_created_at
FROM public.weekly_dashboard_runs r
JOIN public.weekly_dashboard_signals s ON s.run_id = r.run_id
WHERE r.is_current;

REVOKE ALL ON api.v_current_weekly_signals FROM PUBLIC;
GRANT SELECT ON api.v_current_weekly_signals TO anon;

-- (2) One-row freshness contract. Aggregate anchor => exactly one row even
-- when the runs table is empty. Never exposes the manifest.
CREATE OR REPLACE VIEW api.weekly_dashboard_status
WITH (security_invoker = false, security_barrier = true)
AS
SELECT max(r.created_at) FILTER (WHERE r.is_current) AS run_created_at,
       COALESCE(max(r.source_manifest ->> 'bundle_built_at') FILTER (WHERE r.is_current),
                max(r.source_manifest ->> 'built_at') FILTER (WHERE r.is_current)
               )::timestamptz AS bundle_built_at,
       (max(r.created_at) FILTER (WHERE r.is_current) IS NOT NULL) AS has_current,
       max(r.season) FILTER (WHERE r.is_current) AS season,
       max(r.week)   FILTER (WHERE r.is_current) AS week,
       COALESCE(sum((SELECT count(*)
                     FROM public.weekly_dashboard_signals s
                     WHERE s.run_id = r.run_id)) FILTER (WHERE r.is_current), 0) AS signal_count,
       (SELECT count(*) FROM public.weekly_dashboard_runs r2
        WHERE r2.is_current) AS current_run_count,
       max(r.created_at) AS latest_run_created_at
FROM public.weekly_dashboard_runs r;

REVOKE ALL ON api.weekly_dashboard_status FROM PUBLIC;
GRANT SELECT ON api.weekly_dashboard_status TO anon;
