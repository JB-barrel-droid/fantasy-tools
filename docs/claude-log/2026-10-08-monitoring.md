## 2026-10-08 - Monitoring tidy (fix/monitoring-tidy)

Contract: security first (RLS on monitoring.*, every Supabase security advisor
finding fixed or explained); monitor shows its real state and its own
staleness; re-check the 2026-10-07 reds; GitHub schedules to pg_cron; an alert
channel for real failures; resolve GAP-015, GAP-042, GAP-046. Staleness and
monitoring warn, never block deploys. Nothing applied to Supabase by this
session: SQL is in two migration files for the integrator.

### Found
- `anon` (the publishable key) held INSERT/UPDATE/DELETE/TRUNCATE on all 83
  public tables with RLS off, chart inputs included, and write grants on the 28
  public SECURITY DEFINER views. No anon write in the edge logs 2026-10-01..08;
  every writer is service_role or postgres.
- The 9 monitoring pg_cron jobs were switched off ~16:00 UTC 2026-10-07
  (Jeremy, pre-launch; confirmed by the integrator). So the evaluator stopped
  and the served monitor files froze at 2026-10-07 15:41 UTC. The page already
  said so (red, "snapshot is N min old").

### Verified (check named)
- Advisor: `get_advisors(security)` 2026-10-08 10:25 UTC: 83 rls_disabled_in_public,
  37 security_definer_view, 9 function_search_path_mutable, pg_net in public,
  6 rls_enabled_no_policy. Grants: `information_schema.role_table_grants` for
  public.players (anon: INSERT/UPDATE/DELETE/TRUNCATE, no SELECT).
- Traffic: `query_logs` edge_logs grouped by key/role per day, 10-01..10-08:
  non-service-role writes = none; anon/publishable reads of
  cbs_ros_projections, razzball_projections, espn_season_projections, teams,
  games, source_trade_values (Jeremy's local Python, Comcast IP) and probes.
- Read preservation dry run (read-only SELECT of the migration's selection):
  77 anon + 83 authenticated read policies, only on tables with RLS off today;
  the 6 tables anon cannot read today get none.
- `monitoring_security_posture` body run read-only on the live DB:
  tables_without_rls 87, anon_or_auth_write_grants 228, public_definer_views 28,
  mutable_search_path_functions 9 (the advisor's same 9), so ok=false today.
- Both migrations parse (pglast 8.3, `parse_sql`; plpgsql bodies via
  `parse_plpgsql` except one DO block where pglast's slice was cut; read by eye).
  compute_heartbeat_state body compared to `pg_get_functiondef` live: identical
  apart from comments, before the two edits.
- Observed reds re-checked (v_check_observations + gh run list): rebuild_chain
  ok 10:01 UTC, cbsros_supabase_sync ok 08:48 (run 37752268019),
  usatoday_trade_chart_ingest ok 10-07 21:20, weekly_dashboard_load retired by
  the producers lane. Banner red = evaluator off, not pipelines.
- Retired jobs have no readers: repo grep for gate_audits / ops.health /
  run_health_checks / audit_publish_gate (none outside SQL definitions);
  pg_depend: no views on ops.health / ops.gate_audit; ops.gate_audit has 0 rows.
- pg_cron dispatch lag 1-2 s (run createdAt vs cron minute: source-vintage
  10:00:01, 09:00:02; sleeper 09:17:01; espn 11:30:01 on 10-07).
- Tests that fail on origin/main and pass here: test_gha_schedules_pg_cron
  (pages.yml schedule), test_monitoring_coverage (page limit 60 != 720,
  producer/security in summary), test_promote_section GAP-015 tests;
  test_monitor_alerts and test_security_lockdown_migration include mutation
  guards (dedup removed, threshold removed, each lockdown rule removed).
- `make sync` then `make validate` exit 0. `make test-unit` stops at
  tests.test_adjustment_inputs (missing data pin), which fails identically on
  origin/main; the 9 later failures I ran individually also fail on a clean
  origin/main checkout (tests-hygiene lane).

### Claimed, not confirmed
- The migrations have not run against Postgres; the integrator's apply is the
  first execution. Expected after both: advisor shows only 11 api.* definer
  views, pg_net in public, and the INFO no-policy rows; posture ok=true.
- `public.monitoring_refresh_summary()` / the 6-hourly run / the first
  `ops-alert` issue have not run. CBS trade values were 9 days since landing
  today; at the 10-day threshold a `source-stuck-cbs` issue opens on the first
  run after 2026-10-09 ~22:44 UTC unless Week 5 lands.
- GitHub emails the repo owner for the bot-opened issue because of the
  @mention; not observed yet.
- trigger-cbsros-sync-retry was added to the manifest so the coverage audit
  does not flag it; its migration lives on the cbsros lane's branch.
