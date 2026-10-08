-- GAP-038 (2026-10-08): re-enable the scheduled live-page synthetic.
--
-- pg_cron `live-page-synthetic-live` dispatches .github/workflows/live-page-synthetic.yml,
-- which renders the live root (every v2 tab), /v2/, /classic/ and the 404 page
-- and records check `live_page_synthetic` in monitoring.check_observations.
-- It was switched off on 2026-10-07 with Jeremy's pre-launch cut of nine
-- monitoring jobs; verified read-only 2026-10-08: active=false, zero
-- live_page_synthetic observations ever recorded.
--
-- Cadence: daily 12:15 UTC, 45 minutes after `pages-deploy-live` (11:30 UTC),
-- so the check sees the day's scheduled deploy. Apply only with Jeremy's /
-- the integrator's OK (it reverses part of the 2026-10-07 cut).
select cron.alter_job(
    (select jobid from cron.job where jobname = 'live-page-synthetic-live'),
    schedule := '15 12 * * *',
    active := true);

-- Keep the monitor's description of the check in step with the schedule.
update monitoring.check_config
   set alert_policy = alert_policy || jsonb_build_object('what',
         'rendered check of the live site passed with the expected build tag (daily 12:15 UTC via pg_cron live-page-synthetic-live)'),
       updated_at = now()
 where check_id = 'live_page_synthetic';
