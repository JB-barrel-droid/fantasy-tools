## 2026-10-26 - JEG-976 render-sweep coverage guard demoted to a warning

Contract: per Jeremy's 2026-10-26 decisions on JEG-976, move tests.test_render_sweep_coverage out of test-core (so `make validate`, the deploy gate, no longer runs it) into the non-blocking test-unit-modules list, and do the repo bookkeeping for the now-applied pg_cron job render-sweep-daily (jobid 47). The test's assertions are unchanged. No production database change was made by this session.

### Verified (check named)
- `make -n test-core | grep -c render_sweep_coverage` printed 0, and `make -n test-unit-modules | grep render_sweep_coverage` shows the line: the guard is out of the gate and in the unit list.
- `python3 -m unittest tests.test_render_sweep_coverage tests.test_run_suite tests.test_validate_runner tests.test_preview_workflow_matches_pages tests.test_monitoring_coverage tests.test_gha_schedules_pg_cron`: 68 tests OK, including the coverage test's own negative tests (an unwired render module fails it).
- No expectation in any of those tests needed changing; none pinned the rule Jeremy changed.
- `make validate` exit 0 (log has no test_render_sweep_coverage line; ran 2026-10-26 on this branch).

### Claimed, not confirmed
- The render-sweep-daily job's first run (due 2026-10-26 07:47 UTC) dispatching render-sweep.yml: not checked here (Jeremy's comment says he will check).
- That jobid 47 exists in production as described: taken from Jeremy's ticket comment, not queried.
- render-sweep-daily is listed in config/monitoring_coverage.json with `records: []` because the workflow records no monitoring.check_config check and adding one is a production schema change not approved.
