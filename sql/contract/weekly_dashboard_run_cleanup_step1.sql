-- JEG-398 Step 1 — evidence export (SELECT only). Save all outputs before
-- any cleanup. Run in the Supabase SQL editor.

-- 1.1 Run registry: full audit record
SELECT r.run_id, r.season, r.week, r.created_at, r.is_current,
       r.source_manifest,
       (SELECT count(*) FROM public.weekly_dashboard_signals s
         WHERE s.run_id = r.run_id) AS signal_count
FROM public.weekly_dashboard_runs r
WHERE r.season = 2026 AND r.week IN (3, 4)
ORDER BY r.week, r.created_at;

-- 1.2 Per-run player_key-set hash (ordered md5 of aggregated keys).
-- Compare across the two 402-row week-3 runs: if the hashes DIFFER, STOP —
-- do not run the cleanup; the two runs disagree on week-3 truth.
SELECT r.run_id, r.week,
       md5(string_agg(s.player_key, ',' ORDER BY s.player_key)) AS player_set_hash,
       count(*) AS n_keys
FROM public.weekly_dashboard_runs r
JOIN public.weekly_dashboard_signals s USING (run_id)
WHERE r.season = 2026 AND r.week IN (3, 4)
GROUP BY r.run_id, r.week
ORDER BY r.week;

-- 1.3 Position-NULL counts per run (week-3 backfill left position NULL)
SELECT r.run_id, r.week,
       count(*) FILTER (WHERE s.position IS NULL) AS position_null_count,
       count(*) AS total
FROM public.weekly_dashboard_runs r
JOIN public.weekly_dashboard_signals s USING (run_id)
WHERE r.season = 2026 AND r.week IN (3, 4)
GROUP BY r.run_id, r.week
ORDER BY r.week;
