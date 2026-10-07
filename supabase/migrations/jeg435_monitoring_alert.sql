-- JEG-435: email alerter for monitoring state transitions.
--
-- Decision (Jeremy, 2026-10-07): alert delivery channel = EMAIL to
-- jeremy.burstyn@gmail.com.  See docs/decisions.md entry jeg-435-001.
--
-- POST-MERGE STEPS (Jeremy must do these after the PR merges):
--
--   1. Deploy the edge function:
--      supabase functions deploy monitoring-alert-email --no-verify-jwt \
--        --project-ref iskiybsimubiujwuchsl
--
--   2. Set the one required secret:
--      supabase secrets set RESEND_API_KEY=re_... \
--        --project-ref iskiybsimubiujwuchsl
--      (Create a free Resend account at resend.com, generate an API key.
--      Resend's onboarding@resend.dev sender works for owner-address sends
--      without a verified domain — no domain setup required for a first test.)
--
-- FUNCTION AUTH (why --no-verify-jwt):
--   The previous live-page edge function used verify_jwt=true and was called
--   from pg_cron with a vault bearer token (supabase_service_key) that did
--   not match the function's JWT secret — every call returned 401 while
--   cron.job_run_details showed "succeeded".  This function is deployed with
--   --no-verify-jwt to avoid that pattern.  The function reads no user data
--   and sends only to the hard-coded owner email, so the exposure risk of
--   unauthenticated callers is low (they can trigger a state check but cannot
--   read secrets or exfiltrate data).  The invoker wrapper is still
--   REVOKE'd from anon so it cannot be called via the Postgres REST API.

-- ===========================================================================
-- 1. alert_state: one row per check; tracks the last state we emailed about.
--    Absent = never alerted (treated as 'unknown' by the edge function).
-- ===========================================================================

CREATE TABLE IF NOT EXISTS monitoring.alert_state (
    check_id           text        PRIMARY KEY,
    last_alert_status  text        NOT NULL,
    last_alerted_at    timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE monitoring.alert_state ENABLE ROW LEVEL SECURITY;

CREATE INDEX IF NOT EXISTS alert_state_alerted_at_idx
    ON monitoring.alert_state (last_alerted_at DESC);

-- ===========================================================================
-- 2. check_config row for the alerter itself.
--    The edge function self-reports by inserting into monitoring.check_observations
--    (NOT via cron_check_map, because the pg_cron job only queues a net.http_post
--    and cron.job_run_details shows "succeeded" even when the function fails).
-- ===========================================================================

INSERT INTO monitoring.check_config (
    check_id,
    enabled,
    check_type,
    cadence_seconds,
    scheduler_owner_type,
    scheduler_owner_id,
    alert_policy,
    active_ownership_count
) VALUES (
    'monitoring_alert_email',
    true,
    'http_status_and_content',
    900,  -- 15-minute cadence matches the cron schedule
    'pg_cron',
    'monitoring-alert-email-15min',
    '{"severity":"page","label":"Monitoring alert emailer","pg_cron_job":"monitoring-alert-email-15min","what":"monitoring-alert-email edge function ran without error every 15 minutes (self-reporting via check_observations; verify_jwt=false)"}',
    1
)
ON CONFLICT (check_id) DO NOTHING;

-- ===========================================================================
-- 3. Invoker wrapper: SECURITY DEFINER so cron.job runs it as the owner,
--    not as a low-privileged role.
-- ===========================================================================

CREATE OR REPLACE FUNCTION public.invoke_monitoring_alert_email()
 RETURNS bigint
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public', 'pg_temp'
AS $function$
DECLARE
  req_id bigint;
BEGIN
  SELECT net.http_post(
    url     := 'https://iskiybsimubiujwuchsl.supabase.co/functions/v1/monitoring-alert-email',
    headers := jsonb_build_object('Content-Type', 'application/json'),
    body    := '{}'::jsonb
  ) INTO req_id;
  RETURN req_id;
END;
$function$;

-- Only service_role (= pg_cron owner) may call this.
REVOKE EXECUTE ON FUNCTION public.invoke_monitoring_alert_email() FROM public, anon, authenticated;

-- ===========================================================================
-- 4. pg_cron schedule: every 15 minutes.
-- ===========================================================================

SELECT cron.schedule(
    'monitoring-alert-email-15min',
    '*/15 * * * *',
    $$SELECT public.invoke_monitoring_alert_email()$$
);
