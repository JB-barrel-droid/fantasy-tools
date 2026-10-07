-- per-source-promotion-001 (2026-10-07): monitored checks for held sources.
--
-- The rebuild chain no longer fails when one source's review is 'hold'; the
-- held source keeps its last promoted section and the others publish. These
-- two checks keep that loud. rebuild-chain.yml records both on every chain
-- run via pipelines/record_chain_holds.py:
--   rebuild_chain_source_held        not ok when any source was held (warn -> yellow)
--   rebuild_chain_source_held_stale  not ok when a held source's kept section is
--                                    two or more content weeks behind (page -> red)
--
-- NOT APPLIED by the authoring session (no Supabase writes). Until it is
-- applied, the recorder's RPC insert fails the check_id foreign key and it
-- logs a ::warning; the hold is still in the run summary, the run's warning
-- annotations and comparison-chain-status.json `held`.
--
-- Reversible: delete these two check_config rows (and their observations).

begin;

insert into monitoring.check_config
    (check_id, check_type, cadence_seconds, grace_override_seconds,
     scheduler_owner_type, scheduler_owner_id, alert_policy)
values
  ('rebuild_chain_source_held', 'http_status_and_content', 21600, 1800, 'github_actions', 'rebuild-chain.yml',
   '{"severity":"warn","label":"Comparison chain: a source is held","pg_cron_job":"rebuild-chain-live","workflow":"rebuild-chain.yml","what":"no source review was held on the last chain run; a held source keeps its last promoted section (shown with its own week) while the others publish"}'),
  ('rebuild_chain_source_held_stale', 'http_status_and_content', 21600, 1800, 'github_actions', 'rebuild-chain.yml',
   '{"severity":"page","label":"Comparison chain: a source held two or more weeks","pg_cron_job":"rebuild-chain-live","workflow":"rebuild-chain.yml","what":"no held source is two or more content weeks behind; a human must clear the hold"}')
on conflict (check_id) do nothing;

commit;
