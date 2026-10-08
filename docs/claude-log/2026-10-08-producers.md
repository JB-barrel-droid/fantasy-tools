# 2026-10-08 producers lane (fix/producers-tidy)

Rows: GAP-FC-PRODUCER, GAP-MUSE-OFF-PULLERS, GAP-USAT-FIRECRAWL, GAP-030
(closed), GAP-036 / GAP-009 / GAP-010 (already closed, confirmed), plus the
integrator's three paused pg_cron jobs. Retry slots (item 5) were dropped
mid-session: the refresh-cadence lane owns schedules and retries now.

## Verified (check named)

- **FantasyCalc CI producer exists and works.** `cron.job` row 22
  `trigger-fantasycalc-weekly-save` (`7 13 * * 2,5`, active) dispatches
  `fantasycalc-weekly-save.yml` mode=write. Run 37478103839 (manual dispatch
  2026-10-06 14:20) wrote `fcwk5_2026-10-06_v1` (SQL: 195 rows x 3 scorings,
  12 teams, max value 70.0, native ~10700). Its failed step was only the
  monitoring record (409, check_config row created at 14:22). `cron.job_run_details`
  has no rows for job 22: it has never fired; first slot Fri 2026-10-09 13:07.
- **Week-4 raw natives still present** (SQL): 2,364 week-4 rows, bake_id NULL,
  value = native_value, 8/10/12/14 teams, written 2026-10-05 15:02. Writer:
  `pipelines/refresh_fantasycalc_supabase.py` (hardcoded WEEK=4, value=native).
- **Repair SQL** `supabase/migrations/fc_week4_value_repair.sql`: values from
  `save_usatoday_references.apply_reindex` (the saver's own call) over the 591
  live 12-team natives, 0 review rows; the 591 ids' md5 matches the live
  broken-row set (SQL md5 = local md5 = 5f2255...9202). Not applied (lane is
  read-only). tests/test_fc_week4_value_repair_sql.py: 6 tests, 5 negative.
- **History lane check:** history-backfill confirmed its week history reads
  only `native_value` (12-team), and week 4 is frozen in data/history; the
  repair leaves native_value untouched.
- **USA Today chain:** new tests fail on origin/main code (3 failures:
  relay soft wall falls through, all-soft-walled is SOURCE_BLOCKED and named,
  workflow passes FIRECRAWL_API_KEY) and pass on the branch.
- **Stale pin fixed:** `test_migration_dispatches_this_workflow_in_write_mode`
  was red on origin/main (pinned literal `source: [cbs, usatoday]`; the
  matrix gained fantasypros). Rewritten to the rule (every recorded matrix
  source has a check_config row); negative-tested by dropping the
  fantasypros record exclusion (fails).
- **Prediction markets has no reader:** grep of app/trade-value-chart/assets/*.js,
  app/v2/*.js and index.html (inline JSON stripped) finds no pm_* /
  prediction / Kalshi reference; the health panel's `order` list omits
  prediction_markets. Removed from bake_players.py, dataset_status.py,
  check_reference_freshness.py; CSV deleted. Two reference-freshness pinned
  counts drop by one (7->6, 6->5) because the players.pm_snapshot item no
  longer exists; tests/test_kdst_coverage_contract.py `test_kdst_no_pm_data`
  deleted (it asserted its own literal dict, nothing from the bake);
  test_ppg_tie_parity field list drops pm_ppg / pm_filled_ppg (fields gone).
- **Chart numbers cannot move:** the only chart-adjacent change is removing
  players.json fields no JS reads (grep above). No 12-combo sweep run.
- **Razzball (GAP-030):** SQL vintages 2026-10-07 (682), 10-06 (672), 10-01
  (692); fixture razzball section vintage 2026-10-07; chain bake passes
  --razzball-snapshot (rebuild-chain.yml line 127).
- **Paused jobs:** player-trace.json is read by the served
  dist/modules/dashboard.html (Player Trace section) -> re-enable daily 12:47.
  fantasycalc-drift: monitoring only, superseded by the Tue+Fri save -> manual.
  weekly-dashboard-load: no site/chain reader (grep), GitHub `schedule:` still
  firing and failing daily (exit 2, runs on 10-06 and 10-07) -> manual,
  schedule removed. tests/test_producers_schedule_tidy.py: 5 tests, 4 negative.
- `make sync` + `make validate` exit 0 on the branch. Out-of-gate reds in
  test-unit (test_adjustment_inputs, test_consolidated_write_fields,
  test_guard_harness_recorded, test_jeg68, test_jeg69, test_razzball_monitor_coverage,
  test_source_freshness, test_no_failopen_workflows, test_jeg137_card_script_order)
  are red on origin/main too (stash check).

## Claimed, not confirmed

- Firecrawl's live API shape (`/v1/scrape`, `data.rawHtml`) is tested only
  against a mocked response; no key exists.
- The weekly-save Friday run (first scheduled fire) has not happened yet.
- Retired check rows: the migration deletes their observations; I did not
  check whether any dashboard history view wants them.
- Sleeper identity row in docs/watchdog.md ("identity base") is from the
  workflow name, not a read of its writer.
