-- JEG-438 stage 4: nightly player-identity reconcile.
-- NOT YET APPLIED. Apply right after .github/workflows/player-identity-reconcile.yml
-- is on main (a dispatch before that 404s, and the live coverage audit expects the
-- job, the check row and the manifest entry to land together).
select cron.schedule(
    'player-identity-reconcile-nightly',
    '23 8 * * *',
    $$SELECT public.dispatch_gha_workflow('player-identity-reconcile.yml', '{"mode": "write"}'::jsonb)$$
);

insert into monitoring.check_config
    (check_id, check_type, cadence_seconds, grace_override_seconds,
     scheduler_owner_type, scheduler_owner_id, alert_policy)
values
    ('player_identity_reconcile', 'http_status_and_content', 86400, 3600,
     'github_actions', 'player-identity-reconcile.yml',
     '{"severity": "warn", "label": "Player identity reconcile", "workflow": "player-identity-reconcile.yml", "pg_cron_job": "player-identity-reconcile-nightly", "what": "nightly reconcile ran green AND open player names (provisional + unmatched + review, last 14 days) stayed <= 5 per source and <= 15 total (daily 08:23 UTC via pg_cron player-identity-reconcile-nightly)"}')
on conflict (check_id) do update set
    cadence_seconds = excluded.cadence_seconds,
    grace_override_seconds = excluded.grace_override_seconds,
    scheduler_owner_id = excluded.scheduler_owner_id,
    alert_policy = excluded.alert_policy,
    updated_at = now();
