## 2026-10-07 - JEG-437 item 3: GAP-GHA-SCHEDULES, three schedules to pg_cron

### Verified (check named)
- Applied migration `gha_schedules_pg_cron` (Supabase MCP, project iskiybsimubiujwuchsl);
  `select jobname, schedule, active, command from cron.job` then returned
  pages-deploy-live `30 11 * * *`, weekly-dashboard-load-live `7 16 * * *`,
  sleeper-identity-refresh-live `17 9 * * 2,4`, all active, each
  `public.dispatch_gha_workflow('<file>', '{}')`. Same schedules the GitHub crons had.
- `public.dispatch_gha_workflow` read via pg_get_functiondef: dispatches ref `main`
  and logs to monitoring.dispatch_log. All three workflows already had `workflow_dispatch:`.
- Repo: `schedule:` removed from the three workflows; config/monitoring_coverage.json
  names the pg_cron jobs; supabase/migrations/gha_schedules_pg_cron.sql is the applied SQL;
  the three check_config alert_policy texts were updated (`pg_cron_job`, `what`).
- tests/test_preview_workflow_matches_pages.py still passes (it compares build steps, not
  triggers). tests/test_gha_schedules_pg_cron.py (new, in test-unit) negative-tests: an
  added GitHub schedule, a missing workflow_dispatch, a wrong job name, a wrong cron, a
  manifest naming another scheduler (each fails the test's own `problems()`).
  `make validate` exit 0.

### Claimed, not confirmed
- Until this PR merges both schedulers fire (GitHub cron and pg_cron); all three
  workflows are idempotent, so the overlap is harmless but doubled. Also until merge,
  `pipelines/audit_monitoring_coverage.py` on main will report the three new active cron jobs
  as having no manifest entry (the manifest on main does not name them yet).
- No pg_cron run of the three jobs has been observed yet (first: pages 11:30 UTC, sleeper
  Tue/Thu 09:17 UTC on the next occurrence, weekly 16:07 UTC today).
