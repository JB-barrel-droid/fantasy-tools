-- JEG-438: the verified player-name alias list moves into Supabase, and the
-- nightly identity reconcile gets its schedule and monitored check.
--
-- NOT APPLIED. Needs Jeremy's approval before it runs on production
-- (iskiybsimubiujwuchsl). No DDL: public.player_name_aliases already exists
-- (jeg438 stage 2, 18 columns, grain (source, norm_name, position)).
--
-- 1. Curated aliases. One row per entry of data/inputs/player_aliases.json:
--    source '*', status 'verified', method 'curated'. norm_name is
--    canonical_players.norm_player_name(alias), the form lib/player_aliases
--    matches on. Once these rows exist, lib/player_aliases.load() reads them
--    (when Supabase credentials are present) instead of the JSON; the two
--    hold the same list (tests/test_player_alias_table.py pins this file to
--    the JSON, reconcile_player_identity.py reports drift), so no value moves.
--    Adding an alias later = a row here with method 'curated' AND the JSON
--    entry, in one PR.
-- 2. pg_cron player-identity-reconcile-nightly (07:30 UTC) dispatches
--    player-identity-reconcile.yml mode=write.
-- 3. monitoring.check_config row player_identity_reconcile (daily, 2 h grace).

insert into public.player_name_aliases
    (source, source_player_name, norm_name, position, player_key, status, method,
     confidence, verified_at, verified_by, notes)
select '*', v.alias, v.norm_name, v.pos, v.player_key, 'verified', 'curated',
       1, now(), 'jeg438-curated', v.verified
from (values
    ('Cameron Ward', 'cameron ward', 'QB', 697, '2026-09-19; re-checked 2026-10-08 public.players (one row; no ''Cameron Ward'' row)'),
    ('Cameron Skattebo', 'cameron skattebo', 'RB', 3664, '2026-09-19; re-checked 2026-10-08 public.players (one row; no ''Cameron Skattebo'' row)'),
    ('Travis Etienne Jr.', 'travis etienne', 'RB', 810, '2026-09-19; re-checked 2026-10-08 public.players (one row; Trevor Etienne 3024 is a different player)'),
    ('Michael Pittman Jr.', 'michael pittman', 'WR', 561, '2026-09-19; re-checked 2026-10-08 public.players (one row)'),
    ('Kenny Gainwell', 'kenneth gainwell', 'RB', 785, '2026-10-07 FantasyPros Week 5 / FantasyCalc review rows; re-checked 2026-10-08 public.players (one row)'),
    ('Joshua Palmer', 'joshua palmer', 'WR', 822, '2026-10-08 Razzball review row; public.players one row (Trey Palmer 1347, Tejhaun Palmer 3425 are different players)'),
    ('Drew Ogletree', 'andrew ogletree', 'TE', 920, '2026-10-08 Razzball review row; public.players one row'),
    ('Chigoziem Okonkwo', 'chigoziem okonkwo', 'TE', 4247, '2026-10-08 Razzball / CBS ROS review row; public.players one Okonkwo row'),
    ('Mitch Trubisky', 'mitch trubisky', 'QB', 4214, '2026-10-08 Razzball / CBS ROS review row; public.players one Trubisky row'),
    ('Jalen Cropper', 'jalen cropper', 'WR', 1268, '2026-10-08 Razzball review row (JEG-438); public.players one Cropper row (1268, gsis 00-0038740); Sleeper 11506 ''Jalen Cropper'' is the same player: Fresno State WR, 2023 class (years_exp 3); no other Cropper in public.players or the Sleeper base'),
    ('J. Sturdivant', 'j sturdivant', 'WR', 2201, '2026-10-08 Razzball review row (JEG-438); public.players one Sturdivant row (2201, GB WR, gsis 00-0040948); Sleeper 13770 has the same full name; no other Sturdivant'),
    -- added 2026-10-08 (GAP-CBSROS-NICKNAME-MISSES); applied to production as a
    -- data-only insert of these two rows after validate.
    ('Christopher Brooks', 'christopher brooks', 'RB', 2515, '2026-10-08 CBS ROS saver no_match (run 37800639004); public.players one Brooks RB with a Chris/Christopher first name (2515, GB); Sleeper ''Chris Brooks'''),
    ('Zonovan Knight', 'zonovan knight', 'RB', 868, '2026-10-08 CBS ROS saver no_match (run 37800639004); public.players one Knight RB (868 ''Bam Knight''); Sleeper ''Zonovan Knight'' RB, same 2022 class')
) as v(alias, norm_name, pos, player_key, verified)
on conflict (source, norm_name, position) do update set
    source_player_name = excluded.source_player_name,
    player_key = excluded.player_key,
    status = 'verified',
    method = 'curated',
    confidence = 1,
    candidate_keys = null,
    verified_at = excluded.verified_at,
    verified_by = excluded.verified_by,
    notes = excluded.notes,
    last_seen_at = now();

select cron.schedule(
    'player-identity-reconcile-nightly',
    '30 7 * * *',
    $$SELECT public.dispatch_gha_workflow('player-identity-reconcile.yml', '{"mode": "write"}'::jsonb)$$
);

insert into monitoring.check_config
    (check_id, check_type, cadence_seconds, grace_override_seconds,
     scheduler_owner_type, scheduler_owner_id, alert_policy)
values
    ('player_identity_reconcile', 'http_status_and_content', 86400, 7200,
     'github_actions', 'player-identity-reconcile.yml',
     '{"severity": "page", "what": "Nightly player-identity reconcile ran (pg_cron player-identity-reconcile-nightly 07:30 UTC); content_ok false when a source has more than 5 open player names seen in the last 8 days or the curated aliases drift from data/inputs/player_aliases.json"}')
on conflict (check_id) do update set
    cadence_seconds = excluded.cadence_seconds,
    grace_override_seconds = excluded.grace_override_seconds,
    scheduler_owner_id = excluded.scheduler_owner_id,
    alert_policy = excluded.alert_policy,
    updated_at = now();
