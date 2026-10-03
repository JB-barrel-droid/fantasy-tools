# JEG-285 Phase 2 — Webhook Notification Design

Fixes the "no notify on red chain" gap (Phase 1 finding). When the rebuild
chain goes red, the system tells someone — currently red chains are found by
audits, not by the system.

## Decision needed from Jeremy

**Webhook URL** — Slack incoming webhook or Discord webhook. (SMTP ports
25/587 are blocked on Edge Functions, so direct email is out; a third-party
email API is overkill for this.)

## Design

Database webhooks are async Postgres triggers via pg_net — non-blocking, so
they never slow down the write path. Retry behavior is undocumented; treat
delivery as best-effort and keep the monitor dashboard as the source of truth.

### Trigger: chain status goes red

```sql
create or replace function notify_chain_red()
returns trigger language plpgsql as $$
declare
  webhook_url text := (select decrypted_secret from vault.decrypted_secrets
                       where name = 'alerts_webhook_url');
begin
  if NEW.status = 'red' and (OLD.status is distinct from 'red') then
    perform net.http_post(
      url := webhook_url,
      body := jsonb_build_object(
        'text', format(
          ':red_circle: Trade-value chain RED at %s. Source: %s. Detail: %s. Run: %s',
          NEW.checked_at, NEW.failing_source, NEW.failure_reason, NEW.run_url))
    );
  end if;
  return NEW;
end $$;

create trigger chain_red_notify
  after insert or update on comparison_chain_status
  for each row execute function notify_chain_red();
```

Fires only on the transition *into* red (not on every red row), so one
incident = one alert. Recovery (red → green) optionally posts a ✅.

### What gets alerted

| Event | Severity | Rationale |
|---|---|---|
| Chain status → red | Alert | The core gap from Phase 1 |
| Chain red for >2 consecutive runs | Alert (repeat) | Escalation, not just the first |
| Source import → failed (red) | Alert | Mirrors the dashboard-push FLAG rules |
| Source import → warning (yellow) | No alert | Jeremy's threshold directive 2026-10-03: minor drift never pages |
| Chain recovers red → green | Info | Closes the loop |

### What does NOT get alerted

- Yellow/warning states (threshold policy)
- Successful runs
- Shadow-mode dispatch intents
- Stale-but-expected states (e.g., CBS/USA Today awaiting publication)

## Reliability notes

- pg_net responses are kept 6 hours in `net._http_response`; failed deliveries
  are inspectable via `select * from net._http_response where status_code >= 400
  or error_msg is not null`.
- The `pipeline_cron_log` table records every dispatch intent; if a webhook
  fails silently, the log + dashboard still show the red state.
- Do not build retry logic into the trigger — keep it simple, keep the
  dashboard as the source of truth.

## Implementation checklist

- [ ] Jeremy provides webhook URL → stored in Vault as `alerts_webhook_url`
- [ ] `comparison_chain_status` table/trigger created
- [ ] Test: force a red transition in shadow, verify one alert fires
- [ ] Test: second consecutive red does not double-fire
- [ ] Document the alert format in the runbook (Phase 5)
