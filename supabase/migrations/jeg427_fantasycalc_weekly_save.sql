-- JEG-427: FantasyCalc weekly save (12 teams, 1 QB, three scorings).
-- NOT YET APPLIED. Apply only after FantasyCalc's non-12-team fixture blocks are
-- retired (league-settings-001): promotion merges per setup and stamps one week
-- on the whole source, so a 12-team-only bake would otherwise leave week-old
-- 8/10/14-team values labelled with the new week.
select cron.schedule(
    'trigger-fantasycalc-weekly-save',
    '7 13 * * 2,5',
    $$SELECT public.dispatch_gha_workflow('fantasycalc-weekly-save.yml', '{"mode": "write"}'::jsonb)$$
);

insert into monitoring.check_config
    (check_id, check_type, cadence_seconds, grace_override_seconds,
     scheduler_owner_type, scheduler_owner_id, alert_policy)
values
    ('fantasycalc_weekly_save', 'http_status_and_content', 345600, 7200,
     'github_actions', 'fantasycalc-weekly-save.yml',
     '{"severity": "page", "what": "FantasyCalc 12-team save wrote a new bake (Tue + Fri 13:07 UTC via pg_cron trigger-fantasycalc-weekly-save)"}')
on conflict (check_id) do update set
    cadence_seconds = excluded.cadence_seconds,
    grace_override_seconds = excluded.grace_override_seconds,
    scheduler_owner_id = excluded.scheduler_owner_id,
    alert_policy = excluded.alert_policy,
    updated_at = now();
