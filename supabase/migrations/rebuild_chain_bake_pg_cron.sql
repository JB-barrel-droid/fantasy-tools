-- Daily ESPN anchor refresh (risk register GAP-ESPN-ANCHOR-MANUAL).
-- The ESPN scrape (trigger-espn-sync-live, 11:30 UTC, ~25 s) saves fresh rows
-- to public.espn_season_projections and uploads the same CSV as the
-- espn-projections artifact. This run takes that CSV, re-bakes players.json
-- and rebuilds the comparison chain on it; the chain's `make validate` gates
-- the new anchor before anything is pushed to main
-- (tests/test_rebuild_chain_bake.py pins that). pg_cron is the only
-- scheduler: rebuild-chain.yml has no GitHub `schedule:`.
-- 11:45 UTC = 06:45 CDT: 15 minutes after the scrape, clear of the hourly
-- vintage-check dispatch at :00 and rebuild-chain-live at 12:17.
select cron.schedule(
    'rebuild-chain-bake-live',
    '45 11 * * *',
    $$SELECT public.dispatch_gha_workflow('rebuild-chain.yml', '{"source": "pg_cron-bake", "bake_players": "true"}'::jsonb)$$
);
