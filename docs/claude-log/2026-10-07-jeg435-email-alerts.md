# 2026-10-07 — JEG-435: Monitoring email alerts

Contract: build a Supabase edge function that reads monitoring state transitions
(newly bad + recovered checks), sends one Resend digest email per batch to
jeremy.burstyn@gmail.com, and tracks last-alerted state per check to suppress
repeat spam.  A pg_cron job (every 15 min) invokes it.  The alerter has its own
check_config row so a silent alerter is caught by the monitoring dashboard.

Branch: jeg435-email-alerts (PR TBD)

### Verified (check named)

- `tests.test_monitoring_alert` (26 tests): all pass against the committed
  migration SQL and edge function source.  Negative tests confirmed:
  - transition detection: broken impl (no dedup) flags persistent bad states
    on every run; correct impl does not.
  - dedup: broken impl (no alert_state update) re-flags same bad check
    on every run; correct impl suppresses after first alert.
  - recovery: broken impl (no was_bad check) flags healthy checks as recovered;
    correct impl requires the prior state to have been bad.
  - fail-closed: broken impl (returns 200 on missing key) goes silent;
    correct impl returns 503 + records a failed observation.
- `make validate` exit 0 with the new test added to the test-unit target.
- Edge function auth pattern: `--no-verify-jwt` avoids the JWT bearer issue
  that broke `live-page-synthetic` (GAP-LIVEPAGE-EDGE-401: vault
  `supabase_service_key` was stale; pg_cron job showed "succeeded" on every
  401 response).  The new function requires no bearer token from pg_cron.
- monitoring_coverage.json updated: `monitoring-alert-email-15min` and
  `monitoring_alert_email` added to `pg_cron_sql_jobs` with a note that
  the edge function self-reports (NOT via cron_check_map).
- Risk register GAP-ALERT-CHANNEL updated to reflect this PR.
- decisions.md entry jeg-435-001 added (outcome: proceeded; Jeremy's explicit
  channel decision from 2026-10-07).

### Claimed, not confirmed

- The migration has NOT been applied to iskiybsimubiujwuchsl (read-only session;
  application is a post-merge manual step).
- The edge function has NOT been deployed (same constraint).
- RESEND_API_KEY has NOT been set as a Supabase secret.
- The pg_cron job (`monitoring-alert-email-15min`) is not yet active in cron.job;
  the audit will show it as missing until the migration is applied.
- Resend sender `onboarding@resend.dev` works for owner-address sends to the
  account owner without a verified domain; this was not live-tested.
- alert_state starts empty: on first run after deploy, every check currently in a
  bad state will be in `newly_bad` and Jeremy will receive one digest email.
  After that, only new transitions fire.

Applied: none (PR branch only; post-merge steps documented in the migration file).
