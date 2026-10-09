-- JEG-479: the two monitored checks rebuild-chain.yml records for the
-- engine-vs-reference comparison ("Record value check checks" step).
--   value_check_write  the Supabase store of both sides succeeded (page: the
--                      stored values lag the published fixture otherwise)
--   value_check_agree  the published build's comparison verdict is "agree"
--                      (warn: a disagreement holds sources; it never stops
--                      the site)
insert into monitoring.check_config
    (check_id, check_type, cadence_seconds, grace_override_seconds,
     scheduler_owner_type, scheduler_owner_id, alert_policy)
values
    ('value_check_write', 'http_status_and_content', 21600, 1800,
     'github_actions', 'rebuild-chain.yml',
     '{"severity": "page", "label": "Engine vs reference store (Supabase)", "workflow": "rebuild-chain.yml", "what": "load_value_check.py stored the engine and Python reference values of the published build in public.value_check_values (api.player_values, api.value_check_diff). Non-blocking for Pages."}'),
    ('value_check_agree', 'http_status_and_content', 21600, 1800,
     'github_actions', 'rebuild-chain.yml',
     '{"severity": "warn", "label": "Engine and Python reference agree", "workflow": "rebuild-chain.yml", "what": "value_check.py compare on the published build: every value the page shows agrees with pipelines/value_reference.py within 0.05. Red means a source is held (validationHold) or the DDF rule differs; see modules/value-check.json."}')
on conflict (check_id) do update set
    cadence_seconds = excluded.cadence_seconds,
    grace_override_seconds = excluded.grace_override_seconds,
    scheduler_owner_id = excluded.scheduler_owner_id,
    alert_policy = excluded.alert_policy,
    updated_at = now();
